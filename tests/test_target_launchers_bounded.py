"""D049 condition 3: the python-tarfile, decompress and oras-go controller launchers.

Each launcher runs end to end against an inert fake ``docker`` and ``python`` on a closed PATH
(the pattern of ``tests/test_local_node_tar_smoke.py``). Checked here:

* every host Docker call goes through ``scripts/bounded_cleanup_command.py`` with a deadline, and
  only the campaign itself (``python -m scripts.container_host``) is unbounded;
* the controller's ``docker run`` arguments are the isolation the launcher always had, plus only
  the owner label. 격리 완화 플래그 부재는 인자 전체 고정으로 확인한다(가드 R5가 플래그 문자열을
  테스트에 적는 것을 막음): the whole argument list is compared, so any argument beyond the
  allowed ones fails the test;
* cleanup removes only what carries this run's owner label, and a cleanup that fails, times out or
  cannot confirm removal turns a successful exit into 125, while a failed run keeps its status.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPO_ROOT = SCRIPTS.parent
OWNER = "test-owner"
LABEL = f"org.inodefence.launcher-owner={OWNER}"
CONTAINER_ID = "a" * 64


@dataclass(frozen=True)
class Launcher:
    script: str
    controller: str
    volume: str
    env: dict[str, str]
    passed_line: bool  # prints "PASSED: ..." on success


LAUNCHERS = {
    "python-tarfile": Launcher(
        "local_python_tarfile_explore.sh",
        "inodefence-python-tarfile-controller-test",
        "inodefence-python-tarfile-runtime-test",
        {
            "EXPLORE_IMAGE": "inodefence-python-tarfile:test",
            "RUNTIME_VERSION": "3.12.16",
            "EXTRACTION_FILTER": "data",
        },
        passed_line=False,
    ),
    "decompress": Launcher(
        "local_decompress_selfdiscover.sh",
        "inodefence-decompress-controller-test",
        "inodefence-decompress-runtime-test",
        {},
        passed_line=True,
    ),
    "oras-go": Launcher(
        "local_oras_go_selfdiscover.sh",
        "inodefence-oras-go-controller-test",
        "inodefence-oras-go-runtime-test",
        {},
        passed_line=True,
    ),
}

FAKE_DOCKER = """#!/bin/bash
[ "$1" = --context ] || exit 99
shift 2
printf '%s\\n' "$*" >> "$FAKE_LOG"
printf '%s\\0' "$@" > "$ARGV_DIR/$(/usr/bin/date +%s%N)"
if [ "$TIMEOUT_OPERATION" = "$1 $2" ]; then /usr/bin/sleep 30; fi
case "$1 $2" in
  "container inspect")
    if [ "$INSPECT_UNKNOWN" = 1 ] && [ -s "$STATE/controller" ]; then
      echo daemon-unreachable >&2; exit 1
    fi
    if [ "$3" = --format ] && [ -s "$STATE/controller" ]; then
      printf '%s %s\\n' "$CONTAINER_ID" "$CONTAINER_OWNER"; exit 0
    fi
    echo "Error: No such object: ${!#}" >&2; exit 1 ;;
  "volume inspect")
    if [ "$INSPECT_UNKNOWN" = 1 ] && [ -s "$STATE/volume" ]; then
      echo daemon-unreachable >&2; exit 1
    fi
    if [ "$3" = --format ] && [ -s "$STATE/volume" ]; then
      printf '%s\\n' "$VOLUME_OWNER"; exit 0
    fi
    echo "Error: No such volume: ${!#}" >&2; exit 1 ;;
  "volume create") echo 1 > "$STATE/volume" ;;
  "run -d") echo 1 > "$STATE/controller" ;;
  "exec "*)
    if [ "$3" = sh ]; then
      if [ "$EVIDENCE_PRESENT" = 1 ]; then printf PRESENT; else printf ABSENT; fi
    fi
    exit 0 ;;
  "cp "*) [ "$COPY_ERROR" = 0 ] || exit "$COPY_ERROR"; printf evidence > "$3" ;;
  "rm -f") [ "$CONTROLLER_ERROR" != 0 ] || : > "$STATE/controller"; exit "$CONTROLLER_ERROR" ;;
  "volume rm") [ "$VOLUME_ERROR" != 0 ] || : > "$STATE/volume"; exit "$VOLUME_ERROR" ;;
esac
exit 0
"""

# The fake host Python: the owner token; the real bounded wrapper (logged with its deadline;
# FAKE_DEADLINE, when set, replaces the deadline so a timeout test does not wait); the campaign
# (``-m scripts.container_host``), which exits HOST_ERROR.
FAKE_PYTHON = """#!/bin/bash
case "$1" in
  -c) echo test-owner; exit 0 ;;
  */bounded_cleanup_command.py)
    printf '%s %s\\n' "$2" "${*:6}" >> "$BOUND_LOG"
    script="$1"; deadline="$2"; shift 2
    exec /usr/bin/python3 "$script" "${FAKE_DEADLINE:-$deadline}" "$@" ;;
  -m) printf '%s\\n' "$*" >> "$CAMPAIGN_LOG"; exit "$HOST_ERROR" ;;
esac
exit 97
"""


@dataclass(frozen=True)
class Run:
    result: subprocess.CompletedProcess[str]
    calls: list[str]  # Docker calls, space-joined
    argv: list[list[str]]  # Docker calls, exact argument lists (after --context <name>)
    bounded: list[str]  # "<deadline> <docker args>" per bounded call
    campaign: list[str]


#: Where each launcher publishes its controller report on the host (under INODEFENCE_EVIDENCE_DIR).
REPORT = {
    "python-tarfile": "target-explore/inodefence-python-tarfile-explore-test.json",
    "decompress": "inodefence-decompress-selfdiscover-test.json",
    "oras-go": "inodefence-oras-go-selfdiscover-test.json",
}


def run_launcher(tmp_path: Path, name: str, **overrides: str) -> Run:
    """Run one launcher with environment ``overrides``.

    ``NO_HARDLINKS="1"`` (test-only, not passed to the launcher) replaces ``ln`` with one that
    always fails, as on a filesystem without hard links.
    """
    no_hardlinks = overrides.pop("NO_HARDLINKS", "") == "1"
    launcher = LAUNCHERS[name]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("dirname", "date", "rm", "mkdir", "mktemp", "ln", "mv"):
        (bin_dir / tool).symlink_to(Path("/usr/bin") / tool)
    if no_hardlinks:
        (bin_dir / "ln").unlink()
        (bin_dir / "ln").write_text("#!/bin/bash\necho 'ln: Operation not permitted' >&2\nexit 1\n")
        (bin_dir / "ln").chmod(0o755)
    (bin_dir / "docker").write_text(FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    (bin_dir / "fake-python").write_text(FAKE_PYTHON)
    (bin_dir / "fake-python").chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    argv_dir = tmp_path / "argv"
    argv_dir.mkdir()
    env = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path),
        "FAKE_LOG": str(tmp_path / "calls"),
        "ARGV_DIR": str(argv_dir),
        "BOUND_LOG": str(tmp_path / "bounded"),
        "CAMPAIGN_LOG": str(tmp_path / "campaign"),
        "STATE": str(state),
        "INODEFENCE_DOCKER_CONTEXT": "fake",
        "INODEFENCE_EVIDENCE_DIR": str(tmp_path / "evidence"),
        "PYTHON": str(bin_dir / "fake-python"),
        "SKIP_BUILD": "1",
        "RUN_ID": "test",
        "CONTAINER_ID": CONTAINER_ID,
        "CONTAINER_OWNER": OWNER,
        "VOLUME_OWNER": OWNER,
        "CONTROLLER_ERROR": "0",
        "VOLUME_ERROR": "0",
        "HOST_ERROR": "0",
        "COPY_ERROR": "0",
        "INSPECT_UNKNOWN": "0",
        "EVIDENCE_PRESENT": "0",
        "TIMEOUT_OPERATION": "",
        **launcher.env,
        **overrides,
    }
    result = subprocess.run(
        ["/bin/bash", str(SCRIPTS / launcher.script)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    def lines(path: Path) -> list[str]:
        return path.read_text().splitlines() if path.exists() else []

    records = sorted(argv_dir.iterdir(), key=lambda path: path.name)
    argv = [path.read_text().split("\0")[:-1] for path in records]
    return Run(
        result,
        lines(tmp_path / "calls"),
        argv,
        lines(tmp_path / "bounded"),
        lines(tmp_path / "campaign"),
    )


@pytest.mark.parametrize("name", LAUNCHERS)
def test_success_removes_owned_resources_and_exits_zero(tmp_path: Path, name: str) -> None:
    launcher = LAUNCHERS[name]
    run = run_launcher(tmp_path, name)
    assert run.result.returncode == 0, (run.result.stdout, run.result.stderr)
    assert ("PASSED:" in run.result.stdout) == launcher.passed_line
    assert f"rm -f {CONTAINER_ID}" in run.calls
    assert f"volume rm {launcher.volume}" in run.calls
    assert len(run.campaign) == 1  # the campaign ran once, through scripts.container_host
    assert "INODEFENCE_CLEANUP_UNKNOWN" not in run.result.stderr


@pytest.mark.parametrize("name", LAUNCHERS)
def test_controller_arguments_are_exactly_the_allowed_list(tmp_path: Path, name: str) -> None:
    """The complete argument list of each create call: anything added or changed fails here."""
    launcher = LAUNCHERS[name]
    run = run_launcher(tmp_path, name)
    created = [argv for argv in run.argv if argv[:2] == ["run", "-d"]]
    assert created == [
        [
            "run",
            "-d",
            "--name",
            launcher.controller,
            "--label",
            LABEL,
            "--user",
            "vscode",
            "--workdir",
            "/workspaces/InodeFence",
            "--env",
            "PYTHONPATH=/workspaces/InodeFence/src",
            "--mount",
            f"type=bind,src={REPO_ROOT},dst=/workspaces/InodeFence,readonly",
            "--mount",
            f"type=volume,src={launcher.volume},dst=/var/lib/inodefence",
            "inodefence-controller:local",
            "sleep",
            "infinity",
        ]
    ]
    volumes = [argv for argv in run.argv if argv[:2] == ["volume", "create"]]
    assert volumes == [["volume", "create", "--label", LABEL, launcher.volume]]


@pytest.mark.parametrize("name", LAUNCHERS)
def test_every_docker_call_has_a_deadline(tmp_path: Path, name: str) -> None:
    run = run_launcher(tmp_path, name, EVIDENCE_PRESENT="1")
    assert run.result.returncode == 0, run.result.stderr
    # Every Docker call went through the bounded wrapper ("<deadline> <docker args>").
    assert sorted(line.split(" ", 1)[1] for line in run.bounded) == sorted(run.calls)
    deadlines = {line.split(" ", 1)[0] for line in run.bounded}
    assert deadlines <= {"30", "60", "300", "1800"}
    assert all(line.startswith("300 ") for line in run.bounded if "pip install" in line)
    assert any(line.startswith(f"60 rm -f {CONTAINER_ID}") for line in run.bounded)
    assert any(line.startswith("60 volume rm ") for line in run.bounded)
    assert any(line.startswith(f"300 cp {CONTAINER_ID}:") for line in run.bounded)


@pytest.mark.parametrize("name", LAUNCHERS)
def test_image_builds_have_the_build_deadline(tmp_path: Path, name: str) -> None:
    run = run_launcher(tmp_path, name, SKIP_BUILD="")
    assert run.result.returncode == 0, run.result.stderr
    builds = [line for line in run.bounded if line.split(" ")[1] == "build"]
    assert builds and all(line.startswith("1800 build") for line in builds)


@pytest.mark.parametrize("name", LAUNCHERS)
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"CONTROLLER_ERROR": "41"}, "FAILED cleanup: controller"),
        ({"VOLUME_ERROR": "42"}, "FAILED cleanup: volume"),
        ({"TIMEOUT_OPERATION": "rm -f", "FAKE_DEADLINE": "1"}, "cleanup command timed out"),
        ({"TIMEOUT_OPERATION": "volume rm", "FAKE_DEADLINE": "1"}, "cleanup command timed out"),
        ({"EVIDENCE_PRESENT": "1", "COPY_ERROR": "5"}, "FAILED cleanup evidence copy"),
    ],
)
def test_cleanup_failure_turns_success_into_125(
    tmp_path: Path, name: str, overrides: dict[str, str], message: str
) -> None:
    run = run_launcher(tmp_path, name, **overrides)
    assert run.result.returncode == 125, (run.result.stdout, run.result.stderr)
    assert message in run.result.stderr
    assert "PASSED:" not in run.result.stdout


@pytest.mark.parametrize("name", LAUNCHERS)
def test_failed_run_keeps_its_status_through_a_failed_cleanup(tmp_path: Path, name: str) -> None:
    run = run_launcher(tmp_path, name, HOST_ERROR="37", CONTROLLER_ERROR="41")
    assert run.result.returncode == 37, run.result.stderr
    assert "FAILED at step:" in run.result.stderr
    assert "FAILED cleanup: controller" in run.result.stderr


@pytest.mark.parametrize("name", LAUNCHERS)
def test_unanswered_cleanup_inspection_fails_closed(tmp_path: Path, name: str) -> None:
    # The daemon stops answering inspections once the run's resources exist: nothing is removed
    # on an unconfirmed owner, and the successful run ends 125.
    run = run_launcher(tmp_path, name, INSPECT_UNKNOWN="1")
    assert run.result.returncode == 125, run.result.stderr
    assert "INODEFENCE_CLEANUP_UNKNOWN" in run.result.stderr
    assert not any(call.startswith(("rm -f", "volume rm")) for call in run.calls)


@pytest.mark.parametrize("name", LAUNCHERS)
def test_replaced_controller_is_not_removed(tmp_path: Path, name: str) -> None:
    run = run_launcher(tmp_path, name, CONTAINER_OWNER="other-owner")
    assert run.result.returncode == 125
    assert "INODEFENCE_CLEANUP_UNKNOWN: controller ownership" in run.result.stderr
    assert not any(call.startswith(("rm -f ", "cp ")) for call in run.calls)


@pytest.mark.parametrize("name", LAUNCHERS)
def test_volume_of_another_owner_is_not_removed(tmp_path: Path, name: str) -> None:
    run = run_launcher(tmp_path, name, VOLUME_OWNER="other-owner")
    assert run.result.returncode == 125
    assert "INODEFENCE_CLEANUP_UNKNOWN: volume ownership" in run.result.stderr
    assert not any(call.startswith("volume rm") for call in run.calls)


@pytest.mark.parametrize("name", LAUNCHERS)
def test_evidence_is_copied_when_present(tmp_path: Path, name: str) -> None:
    run = run_launcher(tmp_path, name, EVIDENCE_PRESENT="1")
    assert run.result.returncode == 0, run.result.stderr
    assert "evidence: " in run.result.stdout
    assert any(call.startswith(f"cp {CONTAINER_ID}:") for call in run.calls)


@pytest.mark.parametrize("name", LAUNCHERS)
def test_evidence_is_published_where_hard_links_are_unavailable(tmp_path: Path, name: str) -> None:
    # An output folder on a filesystem without hard links (some FUSE or cloud mounts): the report
    # is still published (no-clobber rename), and the run succeeds.
    run = run_launcher(tmp_path, name, NO_HARDLINKS="1", EVIDENCE_PRESENT="1")
    assert run.result.returncode == 0, run.result.stderr
    report = tmp_path / "evidence" / REPORT[name]
    assert report.read_text() == "evidence"
    assert not list(report.parent.glob(".inodefence-copy.*"))


@pytest.mark.parametrize("name", LAUNCHERS)
def test_existing_evidence_is_never_overwritten(tmp_path: Path, name: str) -> None:
    report = tmp_path / "evidence" / REPORT[name]
    report.parent.mkdir(parents=True)
    report.write_text("earlier run")
    run = run_launcher(tmp_path, name, EVIDENCE_PRESENT="1")
    assert run.result.returncode == 125, run.result.stderr
    assert "evidence destination already exists" in run.result.stderr
    assert report.read_text() == "earlier run"
