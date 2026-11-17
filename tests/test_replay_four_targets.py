"""`inodefence replay` for all four targets: request checks, per-target hooks, controller body.

Evidence class of these tests: unit / controlled. No Docker runs. The launcher is replaced by a
fake that writes what the controller would; the controller body runs on test backends (the local
python-tarfile worker; the decompress / oras-go backends that act out a known hard-link escape).
None of this is a native run of a real extractor, and the violating cases are constructed, not
found by exploration.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import platform
import subprocess
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import container_controller, effect_replay
from scripts import effect_replay_targets as ert

import inodefence.drivers.run_target_replay as driver
from inodefence import cli
from inodefence.builder import build_tar
from inodefence.case_replay import (
    CLASSIFICATIONS,
    INFRASTRUCTURE_FAILURE,
    NEW_VIOLATION,
    NO_VIOLATION,
    NOT_REPRODUCED,
    REPRODUCED_VIOLATION,
    UNJUDGED,
    CaseReplayError,
    ReplayInput,
    classify_round,
    load_request,
    load_result_replay_request,
    normalize_round,
    parse_replay_input,
    read_replays,
    replay_brief,
    summarize_rounds,
)
from inodefence.drivers import explore_result, launcher, replay_launch
from inodefence.drivers import run_target as rt
from inodefence.drivers.decompress import explore as decompress_explore
from inodefence.drivers.node_tar import replay as node_tar_replay
from inodefence.drivers.oras_go import replay as oras_go_replay
from inodefence.drivers.python_tarfile import adapter as rpt
from inodefence.drivers.run_target import TARGETS, PreparedTargetImage, load_adapter
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.live_exploration import LiveRecorder, LiveRunMeta, LiveStep
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, ExecutionStatus
from inodefence.target_result import (
    CaseVerdict,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
)

IMAGE = "sha256:" + "c" * 64
REPO = Path(__file__).resolve().parents[1]
RUNTIME = platform.python_version()
NODE_SETTINGS = {
    "sentinel_count": None,
    "sentinel_seed": None,
    "observer_integrity_policy": "stop",
    "profile": "full",
}
#: target -> (recorded version, recorded run_settings, what the controller must receive)
CONDITIONS = {
    "node-tar": ("7.5.23", NODE_SETTINGS, NODE_SETTINGS),
    "python-tarfile": (
        "3.12.16",
        {"runtime_version": "3.12.16", "extraction_filter": "data"},
        {"target": "python-tarfile", "runtime_version": "3.12.16", "extraction_filter": "data"},
    ),
    "decompress": (
        "@xhmikosr/decompress@11.1.4",
        {"target_version": "@xhmikosr/decompress@11.1.4"},
        {"target": "decompress", "package": "@xhmikosr/decompress", "version": "11.1.4"},
    ),
    "oras-go": (
        "2.6.2",
        {"target_version": "2.6.2"},
        {"target": "oras-go", "version": "2.6.2"},
    ),
}
BENIGN_CASE = minimal_seed_corpus()[1]
ESCAPE_CASE = ArchiveCase(
    (ArchiveEntry("evil", EntryType.HARDLINK, link_target="outside/sentinel.txt"),)
)


def _case_folder(
    tmp_path: Path,
    target: str,
    *,
    violating: bool,
    settings: dict | None = None,
    version: str | None = None,
    case: ArchiveCase = BENIGN_CASE,
) -> Path:
    """A live case folder for ``target`` (the common recorder; conditions as that target's).

    Exploration saves a case folder for violating steps only, so the normal (non-violating) folder
    is a controlled one: the recorder's folder with its recorded verdict rewritten to "no
    violation" (the input bytes and their SHA-256 are untouched).
    """
    recorded_version, recorded_settings, _ = CONDITIONS[target]
    meta = LiveRunMeta(
        target=target,
        version=version or recorded_version,
        seed=1,
        budget=10,
        image_id=IMAGE,
        engine_commit="e" * 40,
        run_settings=recorded_settings if settings is None else settings,
    )
    recorder = LiveRecorder(tmp_path / "out" / "live", meta)
    recorder.on_step(
        LiveStep(
            index=4,
            case_id=case.case_id,
            status="success",
            c0=False,
            c1=True,
            c2=False,
            fingerprints=("C1-aa",),
            tar_bytes=build_tar(case),
            observation_complete=True,
        )
    )
    folder = tmp_path / "out" / "live" / "violations" / "run-000005"
    if not violating:
        record = json.loads((folder / "case.json").read_text(encoding="utf-8"))
        record.update(c1=False, fingerprints=[], new_fingerprints=[])
        (folder / "case.json").write_text(json.dumps(record), encoding="utf-8")
    return folder


def _round(
    c1: bool = False,
    *,
    c2: bool = False,
    outcome: str = "judged",
    termination: str | None = "success",
):
    judged = outcome == "judged"
    return {
        "outcome": outcome,
        "termination": termination,
        "c0": False if judged else None,
        "c1": c1 if judged else None,
        "c2": c2 if judged else None,
        "observation_complete": True if judged else None,
        "fingerprints": ["C1-aa"] if judged and c1 else [],
        "observation": [],
        "reason": None if judged else "un-judged by the exploration rule",
    }


def _docker(argv, **kw):
    if argv[:3] == ["docker", "image", "inspect"]:
        return subprocess.CompletedProcess(argv, 0, IMAGE + "\n", "")
    raise AssertionError(argv)


def _fake_launcher(monkeypatch, rounds: list[dict], *, complete: bool = True) -> dict:
    """Replace the launcher call of BOTH host paths with one that writes the controller's files."""
    seen: dict = {}

    def run_launcher(script, args, *, runner, env, session=None, artifacts=None, **kwargs):
        line = Path(env["REPLAY_INPUT"]).read_text(encoding="utf-8")
        parsed = parse_replay_input(line)  # what the controller would accept
        seen.update(script=script, args=list(args), env=env, settings=parsed.run_settings)
        assert artifacts is not None
        report = Path(artifacts.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        numbered = [{"round": i + 1, **entry} for i, entry in enumerate(rounds)]
        report.with_suffix(".steps.jsonl").write_text(
            "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in numbered),
            encoding="utf-8",
        )
        body = {
            "schema": "inodefence-case-replay-run-v1",
            "case_id": parsed.case.case_id,
            "tar_sha256": parsed.tar_sha256,
            "image_id": env["REPLAY_IMAGE"],
            "rounds_requested": parsed.rounds,
            "rounds": numbered,
            "complete": complete,
        }
        if "target" in parsed.run_settings:
            body["target"] = parsed.run_settings["target"]
            body["target_identity"] = {"reported": "by the image"}
        if not complete:
            body["stop_reason"] = "BackendError: container runtime did not answer"
        report.write_text(json.dumps(body), encoding="utf-8")
        return subprocess.CompletedProcess([str(script), *args], 0 if complete else 1)

    monkeypatch.setattr(replay_launch, "run_launcher", run_launcher)
    monkeypatch.setattr(node_tar_replay, "run_launcher", run_launcher)
    return seen


def _normalized(rounds: list[dict]) -> list[dict]:
    return [normalize_round(raw, index + 1) for index, raw in enumerate(rounds)]


# -- every target has a hook, and every hook goes through the one replay launcher ---------------


@pytest.mark.parametrize("target", sorted(TARGETS))
def test_every_registered_target_has_a_replay_hook_and_a_conditions_check(target: str) -> None:
    adapter = load_adapter(target)
    assert adapter.replay is not None and adapter.replay_check is not None


@pytest.mark.parametrize("target", sorted(TARGETS))
def test_a_normal_case_replays_as_no_violation_on_every_target(
    target: str, tmp_path: Path, monkeypatch, capsys
) -> None:
    """Normal (non-violating) case, controlled: three clean rounds -> ``no_violation``."""
    seen = _fake_launcher(monkeypatch, [_round(), _round(), _round()])
    folder = _case_folder(tmp_path, target, violating=False)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    assert driver.main([str(folder)], runner=_docker) == 0
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before  # original untouched
    # One launcher for all four targets, in its replay mode, with the exact image id.
    assert seen["script"].name == launcher.LAUNCHERS[launcher.REPLAY_LAUNCHER_TARGET]
    assert seen["args"] == ["replay"] and seen["env"]["REPLAY_IMAGE"] == IMAGE
    assert seen["settings"] == CONDITIONS[target][2]
    (record,) = read_replays(folder)
    summary = record["summary"]
    assert summary["conclusion"] == NO_VIOLATION and summary["original_violation"] is False
    assert summary["classification"][NO_VIOLATION] == 3 and summary["verdict_match"] == 3
    assert summary["no_violation_terminations"] == {"success": 3}
    assert [entry["classification"] for entry in record["rounds"]] == [NO_VIOLATION] * 3
    assert record["original"]["source"] == "case-folder"
    assert "no violation originally; no violation again 3/3 (success 3)" in capsys.readouterr().out


@pytest.mark.parametrize("target", sorted(TARGETS))
def test_a_violating_case_is_reproduced_or_not_and_never_confused(
    target: str, tmp_path: Path, monkeypatch
) -> None:
    """Violating case, controlled (constructed record + faked rounds, not an explored finding)."""
    rounds = [
        _round(c1=True),
        _round(c1=False),
        _round(outcome="run_error", termination="timed_out"),
    ]
    _fake_launcher(monkeypatch, rounds)
    folder = _case_folder(tmp_path, target, violating=True)
    assert driver.main([str(folder)], runner=_docker) == 0
    (record,) = read_replays(folder)
    assert [entry["classification"] for entry in record["rounds"]] == [
        REPRODUCED_VIOLATION,
        NOT_REPRODUCED,
        UNJUDGED,
    ]
    summary = record["summary"]
    assert summary["conclusion"] == "partially_reproduced"
    assert (summary["judged"], summary["unjudged"], summary["same_contracts"]) == (2, 1, 1)
    # Original and replay verdicts sit side by side in the record.
    assert (record["original"]["c1"], record["rounds"][0]["c1"], record["rounds"][1]["c1"]) == (
        True,
        True,
        False,
    )


def test_each_round_points_at_its_raw_line_and_the_kept_files_are_hashed(
    tmp_path: Path, monkeypatch
) -> None:
    _fake_launcher(monkeypatch, [_round(), _round()])
    folder = _case_folder(tmp_path, "oras-go", violating=False)
    assert driver.main([str(folder), "--rounds", "2"], runner=_docker) == 0
    (record,) = read_replays(folder)
    replay_dir = folder.parent / record["dir"]
    kept = {item["file"]: item for item in record["replay"]["evidence"]}
    journal = next(name for name in kept if name.endswith(".steps.jsonl"))
    for name, item in kept.items():
        data = (replay_dir / name).read_bytes()
        assert (item["bytes"], item["sha256"]) == (len(data), sha256(data).hexdigest())
    lines = (replay_dir / journal).read_text().splitlines()
    for entry in record["rounds"]:
        assert entry["evidence"] == {"file": journal, "line": entry["round"]}
        assert json.loads(lines[entry["round"] - 1])["round"] == entry["round"]
    assert record["replay"]["runner"]["input_rewritten"] is False  # oras-go: bytes as recorded


def test_an_incomplete_replay_is_an_infrastructure_stop_not_a_verdict(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _fake_launcher(monkeypatch, [_round(c1=True)], complete=False)
    folder = _case_folder(tmp_path, "decompress", violating=True)
    assert driver.main([str(folder)], runner=_docker) == 1
    (record,) = read_replays(folder)
    assert record["replay"]["complete"] is False
    assert "container runtime did not answer" in record["replay"]["stop_reason"]
    assert len(record["rounds"]) == 1  # the finished round is kept
    assert "REPLAY INCOMPLETE" in capsys.readouterr().err


# -- per-target conditions: refused with the reason, before anything runs ------------------------


def _refused(tmp_path: Path, monkeypatch, capsys, target: str, **folder) -> str:
    def never(*args, **kwargs):
        pytest.fail("the launcher must not run")

    monkeypatch.setattr(replay_launch, "run_launcher", never)
    monkeypatch.setattr(node_tar_replay, "run_launcher", never)
    path = _case_folder(tmp_path, target, violating=True, **folder)
    assert driver.main([str(path)], runner=_docker) == 2
    assert read_replays(path) == []
    return capsys.readouterr().err


def test_python_tarfile_fully_trusted_is_refused_as_exploration_refuses_it(
    tmp_path, monkeypatch, capsys
) -> None:
    err = _refused(
        tmp_path,
        monkeypatch,
        capsys,
        "python-tarfile",
        settings={"runtime_version": "3.12.16", "extraction_filter": "fully_trusted"},
    )
    assert "REPLAY REFUSED" in err and rpt.EXPLORE_HELD_REASON in err


@pytest.mark.parametrize(
    ("target", "settings", "version", "words"),
    [
        ("python-tarfile", {"runtime_version": "3.12.16"}, None, "missing ['extraction_filter']"),
        (
            "python-tarfile",
            {"runtime_version": "3.12.16", "extraction_filter": "tar"},
            None,
            "no extraction filter 'tar'",
        ),
        (
            "python-tarfile",
            {"runtime_version": "3.12", "extraction_filter": "data"},
            "3.12",
            "exact X.Y.Z",
        ),
        (
            "python-tarfile",
            {"runtime_version": "3.12.15", "extraction_filter": "data"},
            None,
            "is not its runtime_version",
        ),
        ("decompress", {"target_version": "11.1.4"}, "11.1.4", "is not a spec"),
        (
            "decompress",
            {"target_version": "@xhmikosr/decompress@latest"},
            "@xhmikosr/decompress@latest",
            "is not a spec",
        ),
        ("decompress", {"target_version": "decompress@4.2.1"}, None, "is not its target_version"),
        ("oras-go", {"target_version": "latest"}, "latest", "exact X.Y.Z"),
        ("oras-go", {"target_version": "2.6.1"}, None, "is not its target_version"),
        ("oras-go", {}, None, "missing ['target_version']"),
        ("node-tar", {"profile": "full"}, None, "missing ['observer_integrity_policy'"),
    ],
)
def test_conditions_a_target_cannot_rerun_are_refused(
    tmp_path, monkeypatch, capsys, target, settings, version, words
) -> None:
    err = _refused(tmp_path, monkeypatch, capsys, target, settings=settings, version=version)
    assert "REPLAY REFUSED" in err and words in err


def test_dry_run_reports_the_refusal_and_the_source(tmp_path, capsys) -> None:
    folder = _case_folder(
        tmp_path,
        "python-tarfile",
        violating=True,
        settings={"runtime_version": "3.12.16", "extraction_filter": "fully_trusted"},
    )
    assert driver.main([str(folder), "--dry-run"], runner=_docker) == 2
    plan = json.loads(capsys.readouterr().out)
    assert plan["source"] == "case-folder" and plan["replay_supported"] is True
    assert "is not explored" in plan["refusal"]


def test_oras_go_counts_members_outside_its_frame_and_never_rewrites_them(tmp_path) -> None:
    outside = load_request(_case_folder(tmp_path / "a", "oras-go", violating=False))
    assert oras_go_replay.members_outside_frame(outside) == len(outside.case.entries) > 0
    framed = ArchiveCase(
        (
            ArchiveEntry("d", EntryType.DIRECTORY, mode=0o755),
            ArchiveEntry("d/ok.txt", EntryType.REGULAR, content=b"ok\n"),
        )
    )
    inside = load_request(_case_folder(tmp_path / "b", "oras-go", violating=False, case=framed))
    assert oras_go_replay.members_outside_frame(inside) == 0
    assert inside.tar_bytes == build_tar(framed)  # the request holds the recorded bytes


def test_the_settings_names_match_between_host_and_controller() -> None:
    assert node_tar_replay.NODE_TAR_SETTINGS == effect_replay.NODE_TAR_SETTINGS
    assert replay_launch.TARGET_KEY == ert.TARGET_KEY
    for target in ("python-tarfile", "decompress", "oras-go"):
        _, _, controller = CONDITIONS[target]
        assert set(controller) - {"target"} == set(ert.SETTINGS_KEYS[target])


# -- the replay launcher creates the same controller the explore launchers create ---------------


#: How the launchers that source ``scripts/launcher_bounded.sh`` create the controller:
#: ``launcher_run_controller <arguments>`` runs ``run -d --name "$CONTROLLER" --label <owner>``
#: followed by exactly those arguments (``tests/test_target_launchers_bounded.py`` checks the
#: resulting argv).
BOUNDED_RUN = "launcher_run_controller "


def _controller_run(script: str) -> list[str]:
    """The ``dk run -d`` command that creates the controller, minus the owner label."""
    text = (REPO / "scripts" / script).read_text(encoding="utf-8")
    if BOUNDED_RUN in text:
        start = text.index(BOUNDED_RUN) + len(BOUNDED_RUN)
        head = ["dk", "run", "-d", "--name", '"$CONTROLLER"']
    else:
        start = text.index('dk run -d --name "$CONTROLLER"')
        head = []
    command = text[start : text.index("sleep infinity", start)].replace("\\\n", " ").split()
    words = head + command
    return [word for word in words if not word.startswith(("--label", '"org.inodefence'))]


@pytest.mark.parametrize("target", sorted(set(launcher.LAUNCHERS) - {"node-tar"}))
def test_the_replay_launcher_creates_the_controller_exactly_as_each_explore_launcher(
    target: str,
) -> None:
    """Read-only check of the protected launchers: same user, workdir, env and two mounts.

    The replay launcher adds one ownership label (it removes only what it created); no other word
    of the command differs. The target containers are not created by any launcher but by the host
    broker, the same one in every mode.
    """
    replay = _controller_run(launcher.LAUNCHERS[launcher.REPLAY_LAUNCHER_TARGET])
    assert replay == _controller_run(launcher.LAUNCHERS[target])


def test_the_replay_mode_of_the_launcher_names_no_target_image() -> None:
    text = (REPO / "scripts" / launcher.LAUNCHERS[launcher.REPLAY_LAUNCHER_TARGET]).read_text()
    block = text[text.index('if [ "$MODE" = replay ]; then\n  step "effect-replay-case"') :]
    block = block[: block.index("\nfi\n")]
    assert '--image "$IF_REPLAY_IMAGE" --replay-input "$REPLAY_INPUT"' in block
    assert "NODE_IMAGE" not in block and "--tar-version" not in block


def test_a_replay_session_looks_for_the_replay_launchers_resources() -> None:
    session = driver.new_session("oras-go")
    assert (session.target, session.resources_target) == ("oras-go", "node-tar")

    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0)

    session.launch(
        Path("/x/local_node_tar_smoke.sh"), ["replay"], runner=runner, env={"RUN_ID": "r1"}
    )
    (record,) = session.launches
    assert (record.request.controller, record.request.volume) == (
        "inodefence-local-controller-r1",
        "inodefence-local-runtime-r1",
    )


# -- result folders: what python-tarfile / decompress / oras-go exploration writes ---------------


def _result_folder(tmp_path: Path, target: str, *, tamper: bool = False) -> Path:
    version = CONDITIONS[target][0]
    tar = build_tar(ESCAPE_CASE)
    clean = {"outcome": "judged", "termination": "success", "c0": False, "c1": False, "c2": False}
    report = {
        "case_records": [
            {"run_index": 0, **clean},
            {"run_index": 1, **clean, "c1": True, "c2": True},
        ],
        "violation_inputs": [
            {
                "run_index": 1,
                "tar_sha256": sha256(tar).hexdigest(),
                "tar_b64": base64.b64encode(tar).decode(),
            }
        ],
    }
    prepared = PreparedTargetImage(target, version, version, "img:tag", IMAGE, False)
    result, tars = explore_result.build_campaign_result(report, prepared, seed=1, budget=2)
    if target == "python-tarfile":
        result = dataclasses.replace(
            result, axes=TargetAxes(runtime_version=version, extraction_filter="data")
        )
    out = tmp_path / "out" / "run-result"
    explore_result.write_result(out, result, tars)
    if tamper:
        (out / "inputs" / "step-1.tar").write_bytes(build_tar(BENIGN_CASE))
    return out


@pytest.mark.parametrize("target", ["python-tarfile", "decompress", "oras-go"])
def test_a_saved_input_of_a_result_folder_replays_and_is_published_beside_it(
    target: str, tmp_path: Path, monkeypatch
) -> None:
    seen = _fake_launcher(monkeypatch, [_round(c1=True, c2=True)] * 2)
    result_dir = _result_folder(tmp_path, target)
    before = sorted(str(p.relative_to(result_dir)) for p in result_dir.rglob("*"))
    assert driver.main([str(result_dir), "--case", "step-1", "--rounds", "2"], runner=_docker) == 0
    assert sorted(str(p.relative_to(result_dir)) for p in result_dir.rglob("*")) == before
    assert seen["settings"] == CONDITIONS[target][2]  # the result's axes pin the same extractor
    (folder,) = result_dir.parent.glob("run-result.step-1.replay-*")
    record = json.loads((folder / "replay.json").read_text())
    assert record["original"]["source"] == "result-folder"
    assert (record["original"]["run"], record["original"]["c1"]) == ("step-1", True)
    assert record["summary"]["conclusion"] == REPRODUCED_VIOLATION
    assert record["summary"]["original_fingerprints"] == []  # the result format stores none


def test_the_only_saved_input_is_the_default_case(tmp_path: Path) -> None:
    request = load_result_replay_request(_result_folder(tmp_path, "oras-go"), None)
    assert request.original["run"] == "step-1" and request.case == ESCAPE_CASE


def test_result_folder_inputs_that_cannot_be_the_same_run_are_refused(tmp_path: Path) -> None:
    with pytest.raises(CaseReplayError, match="sha256 .* != recorded"):
        load_result_replay_request(_result_folder(tmp_path / "a", "decompress", tamper=True), None)
    result_dir = _result_folder(tmp_path / "b", "decompress")
    with pytest.raises(CaseReplayError, match="saves the input of violating steps only"):
        load_result_replay_request(result_dir, "step-0")
    with pytest.raises(CaseReplayError, match="not a case of this result"):
        load_result_replay_request(result_dir, "step-9")
    with pytest.raises(CaseReplayError, match="neither a violation case folder"):
        load_request(tmp_path)
    with pytest.raises(CaseReplayError, match="--case names an input of a result folder"):
        load_request(_case_folder(tmp_path / "c", "oras-go", violating=True), case="step-1")


def test_a_verify_result_is_refused_with_the_reason(tmp_path: Path) -> None:
    result = TargetResult(
        target="oras-go",
        axes=TargetAxes(target_version="2.6.2"),
        mode=ResultMode.FIXTURE_REGRESSION,
        observed_contracts=("C1", "C2"),
        cases=(CaseVerdict("nested_hardlink", "declined", None, False, False),),
        repro_inputs=(),
        provenance=Provenance(None, False, "img:tag", IMAGE),
    )
    (tmp_path / rt.RESULT_NAME).write_text(result.dumps())
    with pytest.raises(CaseReplayError, match="fixture-regression .verify. result"):
        load_request(tmp_path, case="nested_hardlink")


def test_a_node_tar_result_folder_is_refused_and_points_at_the_case_folder(
    tmp_path, capsys
) -> None:
    result_dir = _result_folder(tmp_path, "node-tar")
    assert driver.main([str(result_dir), "--case", "step-1"], runner=_docker) == 2
    err = capsys.readouterr().err
    assert "does not record them" in err and "live/violations/run-NNNNNN" in err


def test_the_cli_forwards_case(monkeypatch, tmp_path) -> None:
    seen = {}
    monkeypatch.setattr(cli, "_forward", lambda module, argv, kind: seen.update(argv=argv) or 0)
    assert cli.main(["replay", str(tmp_path), "--case", "step-3", "--rounds", "2"]) == 0
    assert seen["argv"] == [str(tmp_path.resolve()), "--rounds", "2", "--case", "step-3"]


# -- classes and conclusions ---------------------------------------------------------------------


def test_the_six_round_classes_are_exhaustive_and_distinct() -> None:
    violated = {"c0": False, "c1": True, "c2": None}
    clean = {"c0": False, "c1": False, "c2": False}
    rounds = _normalized(
        [
            _round(c1=True),
            _round(c1=False),
            _round(outcome="run_error", termination="failed"),
            _round(outcome="run_error", termination=None),
        ]
    )
    assert [classify_round(violated, entry) for entry in rounds] == [
        REPRODUCED_VIOLATION,
        NOT_REPRODUCED,
        UNJUDGED,
        INFRASTRUCTURE_FAILURE,
    ]
    assert [classify_round(clean, entry) for entry in rounds] == [
        NEW_VIOLATION,
        NO_VIOLATION,
        UNJUDGED,
        INFRASTRUCTURE_FAILURE,
    ]
    assert set(CLASSIFICATIONS) == {
        REPRODUCED_VIOLATION,
        NOT_REPRODUCED,
        NO_VIOLATION,
        NEW_VIOLATION,
        UNJUDGED,
        INFRASTRUCTURE_FAILURE,
    }


@pytest.mark.parametrize(
    ("original_c1", "rounds", "conclusion"),
    [
        (True, [_round(c1=True)] * 2, REPRODUCED_VIOLATION),
        (True, [_round(c1=False)] * 2, NOT_REPRODUCED),
        (True, [_round(c1=True), _round(c1=False)], "partially_reproduced"),
        (False, [_round()] * 2, NO_VIOLATION),
        (False, [_round(), _round(c1=True)], NEW_VIOLATION),
        # No judged round is never "not reproduced":
        (True, [_round(outcome="run_error", termination="timed_out")], UNJUDGED),
        (True, [_round(outcome="run_error", termination=None)], INFRASTRUCTURE_FAILURE),
        (True, [], "no_rounds"),
    ],
)
def test_the_conclusion_names_what_the_rounds_showed(original_c1, rounds, conclusion) -> None:
    original = {"c0": False, "c1": original_c1, "c2": False, "fingerprints": []}
    summary = summarize_rounds(original, _normalized(rounds))
    assert summary["conclusion"] == conclusion
    assert sum(summary["classification"].values()) == len(rounds)


def test_a_record_without_an_original_verdict_is_not_called_no_violation_originally() -> None:
    original = {"c0": None, "c1": None, "c2": None, "fingerprints": []}
    summary = summarize_rounds(original, _normalized([_round(), _round()]))
    assert summary["original_judged"] is False and summary["verdict_match"] == 0
    assert summary["conclusion"] == NO_VIOLATION
    brief = replay_brief({"replay": {"complete": True, "rounds_requested": 2}, "summary": summary})
    assert brief == "replayed 2/2: no original verdict recorded; no violation 2/2 (success 2)"


def test_the_brief_separates_infrastructure_failures_from_unjudged_rounds() -> None:
    original = {"c0": False, "c1": True, "c2": False, "fingerprints": ["C1-aa"]}
    rounds = [
        _round(c1=True),
        _round(outcome="run_error", termination="timed_out"),
        _round(outcome="run_error", termination=None),
    ]
    summary = summarize_rounds(original, _normalized(rounds))
    brief = replay_brief({"replay": {"complete": True, "rounds_requested": 3}, "summary": summary})
    assert brief == (
        "replayed 3/3: same contracts 1/1, fingerprints 1/1, un-judged 1, infrastructure failure 1"
    )


# -- the controller body (scripts.effect_replay_targets) -----------------------------------------


def test_node_tar_input_never_reaches_the_target_dispatch(tmp_path, monkeypatch) -> None:
    """``target`` absent: the node-tar path, unchanged (it stops on its own conditions check)."""

    def never(*args, **kwargs):
        pytest.fail("node-tar must not dispatch")

    monkeypatch.setattr(ert, "run_target_case_replay", never)
    replay_input = ReplayInput(BENIGN_CASE, "0" * 64, 1, {"profile": "full"})
    with pytest.raises(CaseReplayError, match="node-tar run_settings keys mismatch"):
        effect_replay.run_case_replay(None, IMAGE, tmp_path / "r.json", replay_input, None)


@pytest.mark.parametrize(
    ("settings", "words"),
    [
        ({"target": "gnu-tar"}, "replay target must be one of"),
        ({"target": "oras-go"}, "missing ['version']"),
        ({"target": "oras-go", "version": "2.6.2", "x": "y"}, "unexpected ['x']"),
        ({"target": "decompress", "package": "decompress", "version": ""}, "non-empty text"),
        (
            {
                "target": "python-tarfile",
                "extraction_filter": "fully_trusted",
                "runtime_version": "3.12.16",
            },
            "fully_trusted exploration is held",
        ),
        (
            {"target": "python-tarfile", "extraction_filter": "data", "runtime_version": "3.12"},
            "exact X.Y.Z",
        ),
    ],
)
def test_the_controller_rechecks_the_conditions(settings, words) -> None:
    with pytest.raises(CaseReplayError) as error:
        ert.target_conditions(settings)
    assert words in str(error.value)


def _run_body(tmp_path: Path, backend, image: str, case: ArchiveCase, settings: dict, rounds=2):
    tmp_path.mkdir(parents=True, exist_ok=True)
    evidence = tmp_path / "inodefence-case-replay-x.json"
    replay_input = ReplayInput(case, "0" * 64, rounds, settings)
    code = effect_replay.run_case_replay(backend, image, evidence, replay_input, None)
    journal = [
        json.loads(line) for line in evidence.with_suffix(".steps.jsonl").read_text().splitlines()
    ]
    return code, json.loads(evidence.read_text()), journal


def _python_settings(runtime: str = RUNTIME) -> dict:
    return {"target": "python-tarfile", "extraction_filter": "data", "runtime_version": runtime}


def test_python_tarfile_rounds_run_the_real_worker_through_the_exploration_pipeline(
    tmp_path: Path,
) -> None:
    """Normal case on the local test backend (the real worker file, this interpreter)."""
    from tests.test_python_tarfile_contained import IMAGE as PT_IMAGE
    from tests.test_python_tarfile_contained import _LocalBackend

    backend = _LocalBackend()
    code, report, journal = _run_body(tmp_path, backend, PT_IMAGE, BENIGN_CASE, _python_settings())
    assert code == 0 and report["complete"] is True and report["target"] == "python-tarfile"
    assert report["target_identity"]["python_version"] == RUNTIME
    assert report["rounds"] == journal and len(journal) == 2
    for entry in journal:
        assert (entry["outcome"], entry["termination"]) == ("judged", "success")
        assert (entry["c0"], entry["c1"], entry["c2"]) == (False, False, False)
        assert entry["observation_complete"] is True and entry["fingerprints"] == []
    # Each round is one fresh extraction with the recorded filter.
    extracts = [c for c in backend.commands if c[3] == "extract"]
    assert len(extracts) == 2 and all("data" in c for c in extracts)


def test_python_tarfile_stops_when_the_image_is_not_the_recorded_runtime(tmp_path: Path) -> None:
    from tests.test_python_tarfile_contained import IMAGE as PT_IMAGE
    from tests.test_python_tarfile_contained import _LocalBackend

    code, report, journal = _run_body(
        tmp_path, _LocalBackend(), PT_IMAGE, BENIGN_CASE, _python_settings("3.0.0")
    )
    assert code == 1 and report["complete"] is False and journal == []
    assert "does not match the case" in report["stop_reason"]


def test_a_python_tarfile_crash_is_an_unjudged_round_not_a_clean_one(tmp_path: Path) -> None:
    from tests.test_python_tarfile_contained import IMAGE as PT_IMAGE
    from tests.test_python_tarfile_contained import _LocalBackend

    code, report, _ = _run_body(
        tmp_path, _LocalBackend(crash=True), PT_IMAGE, BENIGN_CASE, _python_settings(), rounds=1
    )
    (entry,) = report["rounds"]
    assert code == 0 and entry["outcome"] == "run_error" and entry["termination"] == "failed"
    assert (entry["c0"], entry["c1"], entry["c2"]) == (None, None, None)
    assert "python-tarfile exploration rule" in entry["reason"]
    clean = {"c0": False, "c1": False, "c2": False}
    assert classify_round(clean, normalize_round(entry, 1)) == UNJUDGED


needs_runtime_root = pytest.mark.skipif(
    not Path("/var/lib/inodefence").is_dir(),
    reason="disposable sandbox requires the Linux runtime root (Dev Container)",
)


@needs_runtime_root
def test_decompress_rounds_reproduce_a_constructed_violation(tmp_path: Path) -> None:
    """Violating case, controlled: the test backend acts out a hard-link escape (not a real
    extractor); the pipeline, observer and oracle are the production ones."""
    from tests import test_decompress_effect_campaign as dec

    backend = dec._ExtractingBackend(dec._identity_bytes())
    settings = {"target": "decompress", "package": "decompress", "version": "4.2.1"}
    code, report, journal = _run_body(tmp_path, backend, dec._IMAGE, ESCAPE_CASE, settings)
    assert code == 0 and report["complete"] is True
    assert report["target_identity"]["package_version"] == "4.2.1"
    for entry in journal:
        assert (entry["outcome"], entry["termination"]) == ("judged", "success")
        assert (entry["c0"], entry["c1"], entry["c2"]) == (False, True, True)
        assert entry["fingerprints"] and entry["observation"]
    assert journal[0]["fingerprints"] == journal[1]["fingerprints"]  # stable across rounds
    original = {"c0": False, "c1": True, "c2": True}
    assert classify_round(original, normalize_round(journal[0], 1)) == REPRODUCED_VIOLATION


@needs_runtime_root
def test_decompress_stops_when_the_image_holds_another_package(tmp_path: Path) -> None:
    from tests import test_decompress_effect_campaign as dec

    backend = dec._ExtractingBackend(dec._identity_bytes())
    settings = {"target": "decompress", "package": "@xhmikosr/decompress", "version": "4.2.1"}
    code, report, journal = _run_body(tmp_path, backend, dec._IMAGE, ESCAPE_CASE, settings)
    assert code == 1 and journal == []
    assert "image holds decompress@4.2.1" in report["stop_reason"]


@needs_runtime_root
def test_oras_go_rounds_reproduce_a_constructed_violation(tmp_path: Path) -> None:
    from tests import test_oras_go_effect_campaign as oras

    backend = oras._ExtractingBackend(oras._identity_bytes())
    settings = {"target": "oras-go", "version": "2.6.1"}  # the image reports v2.6.1
    code, report, journal = _run_body(tmp_path / "a", backend, oras._IMAGE, ESCAPE_CASE, settings)
    assert code == 0 and report["target_identity"]["oras_go_version"] == "v2.6.1"
    assert [(e["c0"], e["c1"], e["c2"]) for e in journal] == [(False, True, True)] * 2
    other = {"target": "oras-go", "version": "2.6.2"}
    code, report, journal = _run_body(tmp_path / "b", backend, oras._IMAGE, ESCAPE_CASE, other)
    assert code == 1 and journal == [] and "image holds v2.6.1" in report["stop_reason"]


def _frame_run(status: str, *, violated: bool, frame_error: str | None):
    violations = [
        SimpleNamespace(
            contract_id=SimpleNamespace(value=name),
            violated=violated and name == "C1",
            explanation="x",
            evidence=(),
        )
        for name in ("C0", "C1", "C2")
    ]
    execution = SimpleNamespace(status=ExecutionStatus(status))
    return SimpleNamespace(
        base_result=SimpleNamespace(execution=execution, violations=violations),
        frame=None if frame_error else {},
        frame_error=frame_error,
    )


@pytest.mark.parametrize("status", ["success", "rejected", "failed", "timed_out"])
@pytest.mark.parametrize("violated", [False, True])
@pytest.mark.parametrize("frame_error", [None, "no frame"])
def test_decompress_rounds_are_judged_exactly_as_exploration_judges_a_step(
    monkeypatch, status, violated, frame_error
) -> None:
    monkeypatch.setattr(ert, "_violation_fields", lambda violations: (["fp"], ["line"]))
    run = _frame_run(status, violated=violated, frame_error=frame_error)
    step = {
        "termination": status,
        "judged": status in ("success", "rejected"),
        "oracle": {v.contract_id.value: v.violated for v in run.base_result.violations},
        "frame_error": frame_error,
    }
    entry = ert.decompress_round(run)
    assert (entry["outcome"] == "judged") == decompress_explore.step_judged(step)
    assert entry["termination"] == status
    if entry["outcome"] == "run_error":
        assert (entry["c0"], entry["c1"], entry["c2"]) == (None, None, None) and entry["reason"]


@pytest.mark.parametrize("status", ["success", "rejected", "failed", "timed_out"])
@pytest.mark.parametrize("violated", [False, True])
def test_oras_go_rounds_are_judged_exactly_as_its_exploration_record(
    monkeypatch, status, violated
) -> None:
    monkeypatch.setattr(ert, "_violation_fields", lambda violations: ([], []))
    monkeypatch.setattr("inodefence.builder.build_tar", lambda case: b"tar")
    run = _frame_run(status, violated=violated, frame_error=None)
    recorded, records, _ = container_controller.oras_go_recording_producer(lambda case: run)
    recorded(BENIGN_CASE)
    (explored,) = records
    entry = ert.oras_go_round(run)
    assert (entry["outcome"] == "run_error") == (explored["outcome"] == "run_error")
    assert (entry["c0"], entry["c1"], entry["c2"]) == (
        explored["c0"],
        explored["c1"],
        explored["c2"],
    )


def test_an_exception_in_a_round_keeps_the_finished_rounds(tmp_path: Path) -> None:
    calls = []

    def produce(case):
        calls.append(case)
        if len(calls) == 2:
            raise RuntimeError("container runtime did not answer")
        return _round()

    binders = {"oras-go": lambda backend, image, values: ert.BoundReplay(produce, {"v": "x"})}
    evidence = tmp_path / "r.json"
    replay_input = ReplayInput(BENIGN_CASE, "0" * 64, 3, {"target": "oras-go", "version": "2.6.2"})
    code = ert.run_target_case_replay(None, IMAGE, evidence, replay_input, binders=binders)
    report = json.loads(evidence.read_text())
    assert code == 1 and report["complete"] is False and len(report["rounds"]) == 1
    assert report["stop_reason"] == "RuntimeError: container runtime did not answer"
    assert len(evidence.with_suffix(".steps.jsonl").read_text().splitlines()) == 1
