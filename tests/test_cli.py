"""inodefence CLI: repo location, targets (table/json), doctor, summary."""

import json
from pathlib import Path

import pytest

from inodefence import cli, locate
from inodefence.drivers import repo as drivers_repo

#: The real check, kept before the autouse fixture below replaces it for faked repo roots.
_REAL_CODE_PROBLEM = cli._repository_code_problem


@pytest.fixture(autouse=True)
def _no_user_config(tmp_path_factory, monkeypatch) -> None:
    """Keep the developer's own ~/.config/inodefence and environment out of these tests."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("cfg")))  # no config.env
    monkeypatch.delenv("INODEFENCE_CONFIG", raising=False)
    monkeypatch.delenv("INODEFENCE_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("INODEFENCE_HOME", raising=False)


@pytest.fixture(autouse=True)
def _fake_repo_roots_have_code(monkeypatch) -> None:
    """Doctor tests fake ``repo_root`` with an empty folder; treat it as having the package.

    The marker-only check itself is tested below with the real :func:`cli._repository_code_problem`.
    """
    monkeypatch.setattr(cli, "_repository_code_problem", lambda root: None)


@pytest.fixture(autouse=True)
def _no_real_docker_listing(monkeypatch) -> None:
    """doctor's leftover listing would ask the host's real daemon; answer "none" instead."""
    from inodefence.drivers.runtime import health

    monkeypatch.setattr(cli, "_find_residue", lambda: health.Residue())
    # Nor the host's daemon itself: tests that need an answer set their own fake.
    monkeypatch.setattr(cli, "_docker_server", lambda: ("UNKNOWN", "not asked in tests"))
    monkeypatch.setattr(cli, "_local_images", lambda: None)


@pytest.fixture
def _docker_ok(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_docker_server", lambda: ("OK", "server 29.0.0"))
    monkeypatch.setattr(cli, "_local_images", lambda: ["inodefence-node-tar-registry:7.5.2"])


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_target.py").write_text("TARGETS = {}\n", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    return tmp_path


def test_repo_root_honours_inodefence_home(tmp_path: Path, monkeypatch) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.setenv("INODEFENCE_HOME", str(repo))
    assert locate.repo_root() == repo


def test_repo_root_rejects_a_non_repository(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INODEFENCE_HOME", str(tmp_path))  # no scripts/ or tools/
    assert locate.repo_root() is None


def test_repo_root_is_none_without_markers(monkeypatch) -> None:
    monkeypatch.delenv("INODEFENCE_HOME", raising=False)
    # The installed-location path only resolves in an editable checkout; force the not-found path.
    # The resolver lives in inodefence.drivers.repo (locate only delegates to it).
    monkeypatch.setattr(drivers_repo, "is_repo", lambda root: False)
    assert locate.repo_root() is None


def test_target_support_reads_the_registry_in_the_clone_environment() -> None:
    # A subprocess with the clone first on PYTHONPATH, as for verify/explore: the adapters import
    # the clone's experiments/repro fixtures, which are not packaged.
    root = drivers_repo.repo_root() or Path.cwd()
    support = locate.target_support(root)
    assert set(support) == {"decompress", "node-tar", "oras-go", "python-tarfile"}
    assert all(entry["regression"] is True for entry in support.values())


def test_target_support_reports_an_unreadable_registry(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    failed = subprocess.CompletedProcess([], 1, "", "Traceback\nModuleNotFoundError: experiments\n")
    monkeypatch.setattr(locate.subprocess, "run", lambda *a, **k: failed)
    repo = _make_repo(tmp_path)
    (repo / "src" / "inodefence" / "drivers").mkdir(parents=True)
    (repo / "src" / "inodefence" / "__init__.py").write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="ModuleNotFoundError: experiments"):
        locate.target_support(repo)


def test_targets_subprocess_passes_the_same_tree_invariant() -> None:
    # The CLI path (cwd = clone, clone src first) satisfies "running code = resolved repository".
    import subprocess
    import sys

    root = drivers_repo.repo_root() or Path.cwd()
    done = subprocess.run(
        [sys.executable, "-m", "inodefence.locate", "--target-support-json"],
        cwd=root,
        env=locate._driver_env(root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "node-tar" in done.stdout


def test_targets_internal_entry_refuses_code_outside_a_clone(tmp_path: Path, monkeypatch) -> None:
    # Running code not inside a clone (an installed copy run directly): refused with 3, even with
    # a clone named by INODEFENCE_HOME -- the same invariant as the drivers.
    monkeypatch.setattr(drivers_repo, "_CHECKOUT", tmp_path / "site-packages-like")
    monkeypatch.setenv("INODEFENCE_HOME", str(_make_repo(tmp_path)))
    assert locate._support_main(["--target-support-json"]) == 3
    assert locate._support_main(["--bogus"]) == 3


def _no_subprocess(*args, **kwargs):
    raise AssertionError("no subprocess may start for a repository without code")


@pytest.mark.parametrize(
    "argv",
    [
        ["targets"],
        ["verify", "--target", "node-tar", "--version", "7.5.23", "--dry-run"],
        ["explore", "--target", "node-tar", "--version", "7.5.23", "--dry-run"],
    ],
)
def test_a_marker_only_clone_is_refused_before_any_subprocess(
    tmp_path: Path, monkeypatch, capsys, argv
) -> None:
    # The user chose B (markers, no src/inodefence): never run another installed tree instead.
    monkeypatch.setenv("INODEFENCE_HOME", str(_make_repo(tmp_path)))
    monkeypatch.setattr(locate.subprocess, "run", _no_subprocess)
    assert cli.main(argv) == 3
    err = capsys.readouterr().err
    assert "no InodeFence code to run" in err and str(tmp_path) in err


def test_check_repository_code_accepts_a_real_clone() -> None:
    root = drivers_repo.repo_root() or Path.cwd()
    locate.check_repository_code(root)  # no exception: a normal clone is unaffected


def test_the_internal_registry_entry_is_not_a_user_command(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "target-support-json" not in capsys.readouterr().out


def test_locate_and_the_drivers_share_one_resolver_without_a_cycle() -> None:
    # cli -> locate -> drivers; drivers.repo is a leaf (stdlib + user_config only).
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(drivers_repo))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("inodefence")
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name.startswith("inodefence")
    }
    assert imported <= {"inodefence.user_config"}
    assert locate._MARKER_DRIVER == drivers_repo.MARKER_DRIVER == Path("scripts/run_target.py")
    assert locate.VERIFY_DRIVER == "inodefence.drivers.run_target"


def test_verify_forwards_the_regression_driver_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list = []
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(
        cli,
        "run_driver",
        lambda root, driver, argv, prog=None: calls.append((driver, argv, prog)) or 0,
    )
    out = tmp_path / "elsewhere" / "verify-out"  # creatable: the --out check passes
    argv_in = ["verify", "--target", "node-tar", "--version", "7.5.2", "--dry-run", "--out"]
    assert cli.main([*argv_in, str(out)]) == 0
    driver, argv, prog = calls[0]
    assert driver == cli.VERIFY_DRIVER and prog == "inodefence verify"
    # --out is forwarded on --dry-run too, so the plan shows where it would write (as explore).
    assert argv == ["--target", "node-tar", "--version", "7.5.2", "--dry-run", "--out", str(out)]


def test_explore_forwards_the_exploration_driver_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list = []
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(
        cli, "run_driver", lambda root, driver, argv, prog=None: calls.append((driver, argv)) or 0
    )
    assert (
        cli.main(
            [
                "explore",
                "--version",
                "latest",
                "--budget",
                "8",
                "--seed",
                "1",
                "--auto-prepare",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    driver, argv = calls[0]
    assert driver == cli.EXPLORE_DRIVER
    assert argv == [
        "--target",
        "node-tar",
        "--version",
        "latest",
        "--budget",
        "8",
        "--seed",
        "1",
        "--out",
        str(tmp_path),
        "--auto-prepare",
        "--output",
        "progress",  # the default terminal output; --quiet / --verbose change it
    ]


def test_explore_without_repo_explains_and_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: None)
    assert cli.main(["explore", "--version", "latest", "--auto-prepare"]) == 3
    err = capsys.readouterr().err
    assert "repository not found" in err and "need a clone" in err
    assert "status and summary work without it" in err  # says what still works


_FAKE_SUPPORT = {
    "decompress": {
        "regression": True,
        "auto_prepare": True,
        "explore": False,
        "explore_reason": "no exploration hook for this target yet",
        "options": [],
    },
    "node-tar": {
        "regression": True,
        "auto_prepare": True,
        "explore": True,
        "explore_reason": None,
        "options": [],
    },
    "python-tarfile": {
        "regression": True,
        "auto_prepare": True,
        "explore": False,
        "explore_reason": "no exploration hook for this target yet",
        "options": [
            {
                "name": "extraction-filter",
                "description": "filter",
                "required": False,
                "choices": ["data", "fully_trusted"],
                "single": True,
            }
        ],
    },
}


def test_targets_table_lists_support_reasons_and_options(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(cli, "target_support", lambda root: _FAKE_SUPPORT)
    assert cli.main(["targets"]) == 0
    out = capsys.readouterr().out
    assert "node-tar" in out and "decompress" in out
    assert "no (no exploration hook for this target yet)" in out
    assert "--extraction-filter?" in out  # optional target option, shown with a trailing ?


def test_explore_forwards_target_specific_options_as_extra(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(
        cli, "run_driver", lambda root, driver, argv, prog=None: calls.append(argv) or 0
    )
    assert (
        cli.main(
            [
                "explore",
                "--target",
                "python-tarfile",
                "--version",
                "latest",
                "--dry-run",
                "--extraction-filter",
                "data",
            ]
        )
        == 0
    )
    # The unknown target option flows through to the driver, which declares it from adapter.options.
    assert calls[0][-2:] == ["--extraction-filter", "data"]


@pytest.mark.parametrize(
    ("flags", "mode"),
    [([], "progress"), (["--quiet"], "quiet"), (["--verbose"], "stream")],
)
def test_explore_maps_quiet_and_verbose_to_the_drivers_output_mode(
    monkeypatch, tmp_path: Path, flags: list[str], mode: str
) -> None:
    calls: list = []
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(
        cli, "run_driver", lambda root, driver, argv, prog=None: calls.append(argv) or 0
    )
    base = ["explore", "--version", "latest", "--auto-prepare", "--out", str(tmp_path)]
    assert cli.main(base + flags) == 0
    argv = calls[0]
    assert argv[argv.index("--output") + 1] == mode and argv.count("--output") == 1


def test_explore_refuses_quiet_together_with_verbose(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.main(["explore", "--version", "latest", "--quiet", "--verbose", "--dry-run"])
    assert stop.value.code == 3  # a usage error is a refusal, as for every explore option
    assert "not allowed with" in capsys.readouterr().err


def test_unknown_flag_on_a_non_forwarding_command_is_rejected(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["targets", "--bogus"])
    assert "unrecognized arguments" in capsys.readouterr().err


def test_targets_json_is_machine_readable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(cli, "target_support", lambda root: _FAKE_SUPPORT)
    assert cli.main(["targets", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == _FAKE_SUPPORT


def test_targets_without_repo_explains_and_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: None)
    assert cli.main(["targets"]) == 3
    assert "repository not found" in capsys.readouterr().err


def test_doctor_reports_each_check_and_exit_code(monkeypatch, capsys, _docker_ok) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(cli.Path, "is_dir", lambda self: True)
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "Python 3.12" in out and "repository" in out and "Docker" in out
    assert code in (0, 1)  # depends on the interpreter running the test


def test_doctor_missing_repo_and_docker_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: None)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli.Path, "is_dir", lambda self: False)
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] repository" in out and "[FAIL] Docker CLI" in out
    assert "[UNKNOWN] Docker daemon access" in out  # not asked, so not reported as OK
    assert "[WARN] runtime directory" in out  # development-only, not a user-command failure


def test_doctor_reports_daemon_failure_and_unknown_image_readiness(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: tmp_path / "repo")
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(cli, "_docker_server", lambda: ("FAIL", "permission denied; fix"))
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] Docker daemon access: permission denied" in out
    assert "[UNKNOWN] prepared images" in out


def test_doctor_all_ok_still_says_image_readiness_is_unverified(
    monkeypatch, capsys, tmp_path: Path, _docker_ok
) -> None:
    if cli.sys.version_info[:2] != (3, 12):
        pytest.skip("doctor fails on a non-3.12 interpreter by design")
    monkeypatch.setattr(cli, "repo_root", lambda: tmp_path / "repo")
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setenv("INODEFENCE_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setattr(cli, "_runtime_check", lambda: "OK")  # host-dependent; tested below
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "[OK] Docker daemon access: server 29.0.0" in out
    # Present images are listed as present; which version each serves is said to be unchecked.
    assert "[OK] prepared images: 1 inodefence-* image(s) present: inodefence-node" in out
    assert "is not checked here" in out
    assert "[OK] output folder base (environment)" in out
    assert "no check failed" in out


def test_doctor_with_no_images_is_info_not_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(cli, "_docker_server", lambda: ("OK", "server 29.9.3"))
    monkeypatch.setattr(cli, "_local_images", lambda: [])
    cli.main(["doctor"])
    assert "[INFO] prepared images: none yet" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("value", "expected"),
    [("/tmp/zz", "[FAIL]"), ("relative/x", "[FAIL]"), ("/var/lib/inodefence/../x", "[FAIL]")],
)
def test_doctor_runtime_root_outside_the_allowed_base_is_a_fail_without_sudo_advice(
    monkeypatch, capsys, value: str, expected: str
) -> None:
    monkeypatch.setenv("INODEFENCE_RUNTIME_ROOT", value)
    assert cli._runtime_check() == "FAIL"
    out = capsys.readouterr().out
    assert out.startswith(f"{expected} runtime directory") and "not allowed" in out
    assert "sudo" not in out


def test_explicit_missing_config_file_is_an_error(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("INODEFENCE_CONFIG", str(tmp_path / "typo.env"))
    assert cli.main(["explore", "--version", "latest", "--dry-run"]) == 3
    assert "no such file" in capsys.readouterr().err
    cli.main(["doctor"])
    assert "[FAIL] user config: INODEFENCE_CONFIG=" in capsys.readouterr().out


def test_verify_dry_run_also_refuses_an_out_inside_the_repo(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    calls = _capture_driver(monkeypatch, tmp_path)
    assert (
        cli.main(["verify", "--version", "7.5.2", "--dry-run", "--out", str(tmp_path / "o")]) == 3
    )
    assert calls == []


def test_doctor_flags_an_output_base_inside_the_repo(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: tmp_path)
    monkeypatch.setenv("INODEFENCE_OUTPUT_DIR", str(tmp_path / "out"))
    cli.main(["doctor"])
    assert "[FAIL] output folder base (environment)" in capsys.readouterr().out


def _capture_driver(monkeypatch, root: Path) -> list:
    calls: list = []
    monkeypatch.setattr(cli, "repo_root", lambda: root)
    monkeypatch.setattr(
        cli, "run_driver", lambda root, driver, argv, prog=None: calls.append((driver, argv)) or 0
    )
    return calls


@pytest.mark.parametrize("folder", ["Drive", "Google Drive", "OneDrive - Org"])
def test_output_in_a_synced_looking_folder_warns(
    monkeypatch, tmp_path: Path, capsys, folder: str
) -> None:
    calls = _capture_driver(monkeypatch, tmp_path / "repo")
    monkeypatch.setenv("INODEFENCE_OUTPUT_DIR", str(tmp_path / folder / "if"))
    assert cli.main(["explore", "--version", "latest", "--auto-prepare"]) == 0
    assert calls and "cloud-synced" in capsys.readouterr().err
    cli.main(["doctor"])
    assert "[WARN] output folder base (environment)" in capsys.readouterr().out


def test_relative_out_is_resolved_against_the_callers_cwd(monkeypatch, tmp_path: Path) -> None:
    calls = _capture_driver(monkeypatch, tmp_path / "repo")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    assert cli.main(["verify", "--version", "7.5.2", "--out", "results"]) == 0
    assert cli.main(["explore", "--version", "latest", "--auto-prepare", "--out", "ex"]) == 0
    assert calls[0][1][-2:] == ["--out", str(work / "results")]
    explore_argv = calls[1][1]
    assert explore_argv[explore_argv.index("--out") + 1] == str(work / "ex")


def test_out_inside_the_repo_is_refused_before_the_driver(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = _capture_driver(monkeypatch, repo)
    monkeypatch.chdir(repo)
    assert cli.main(["verify", "--version", "7.5.2", "--out", "results"]) == 3
    assert calls == []
    assert "inside the repository" in capsys.readouterr().err


def test_default_out_follows_the_configured_output_base(monkeypatch, tmp_path: Path) -> None:
    calls = _capture_driver(monkeypatch, tmp_path / "repo")
    config = tmp_path / "config.env"
    config.write_text(f"# mine\nINODEFENCE_OUTPUT_DIR={tmp_path / 'base'}\n", encoding="utf-8")
    monkeypatch.setenv("INODEFENCE_CONFIG", str(config))
    assert cli.main(["explore", "--version", "latest", "--auto-prepare"]) == 0
    argv = calls[0][1]
    assert argv[argv.index("--out") + 1] == str(tmp_path / "base" / "inodefence-explore")


def test_explore_without_auto_prepare_explains_and_runs_nothing(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    calls = _capture_driver(monkeypatch, tmp_path / "repo")
    assert cli.main(["explore", "--version", "latest"]) == 3
    assert calls == []
    assert "--auto-prepare" in capsys.readouterr().err
    assert cli.main(["explore", "--version", "latest", "--dry-run"]) == 0  # plan needs no consent


def test_a_research_setting_in_the_user_config_is_refused(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    calls = _capture_driver(monkeypatch, tmp_path / "repo")
    config = tmp_path / "config.env"
    config.write_text("SEED=7\n", encoding="utf-8")
    monkeypatch.setenv("INODEFENCE_CONFIG", str(config))
    assert cli.main(["explore", "--version", "latest", "--auto-prepare"]) == 3
    assert calls == []
    assert "Research settings" in capsys.readouterr().err
    cli.main(["doctor"])  # doctor still runs and reports it
    assert "[FAIL] user config" in capsys.readouterr().out


def test_summary_renders_a_result_file(tmp_path: Path, capsys) -> None:
    from inodefence.target_result import (
        CaseVerdict,
        Provenance,
        ResultMode,
        TargetAxes,
        TargetResult,
        repro_input,
    )

    result = TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.2"),
        mode=ResultMode.FIXTURE_REGRESSION,
        observed_contracts=("C1", "C2"),
        cases=(CaseVerdict("toplevel_hardlink", "resolved", None, True, True),),
        repro_inputs=(repro_input("toplevel_hardlink", "inputs/a.tar", b"x"),),
        provenance=Provenance("a" * 40, False, "inodefence-node-tar-effect:7.5.2", None),
    )
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "a.tar").write_bytes(b"x")
    rp = tmp_path / "result.json"
    rp.write_text(result.dumps(), encoding="utf-8")
    assert cli.main(["summary", str(rp)]) == 0
    assert "결과 한 장 요약: node-tar 7.5.2" in capsys.readouterr().out


def test_summary_rejects_a_broken_file(tmp_path: Path, capsys) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert cli.main(["summary", str(bad)]) == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_targets_is_the_real_registry_when_repo_is_present(monkeypatch, capsys) -> None:
    # Integration: in this checkout repo_root resolves, so the real registry loads.
    root = cli.repo_root()
    if root is None:
        pytest.skip("not an editable checkout")
    assert cli.main(["targets", "--json"]) == 0
    support = json.loads(capsys.readouterr().out)
    # All four registered targets now carry an explore hook (#440 four-target explore hooks).
    assert set(support) >= {"node-tar", "decompress", "oras-go", "python-tarfile"}
    assert all(support[name]["explore"] is True for name in support)
    # Every target reports its declared options (a list, read from the adapter); it fills in on its
    # own as owners declare them, so here we assert the mechanism, not a particular option.
    assert all(isinstance(feats["options"], list) for feats in support.values())


def _write_result(folder, verdict_cases, campaign=None):
    from inodefence.target_result import (
        Provenance,
        ResultMode,
        TargetAxes,
        TargetResult,
        repro_input,
    )

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "inputs").mkdir(exist_ok=True)
    (folder / "inputs" / "a.tar").write_bytes(b"x")
    result = TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.2"),
        mode=ResultMode.CAMPAIGN if campaign else ResultMode.FIXTURE_REGRESSION,
        observed_contracts=("C1", "C2"),
        cases=verdict_cases,
        repro_inputs=(repro_input(verdict_cases[0].case_id, "inputs/a.tar", b"x"),)
        if verdict_cases
        else (),
        provenance=Provenance("a" * 40, False, "img", None),
        campaign=campaign,
    )
    (folder / "result.json").write_text(result.dumps(), encoding="utf-8")


def test_status_reads_a_finished_result_folder(tmp_path, capsys) -> None:
    from inodefence.target_result import CampaignInfo, CaseVerdict

    folder = tmp_path / "7.5.2-123-2-result"
    _write_result(
        folder,
        (
            CaseVerdict("step-0", "declined", None, False, False),
            CaseVerdict("step-1", "extracted", None, True, True),
        ),
        campaign=CampaignInfo(seed=123, budget=2, runs_to_first_violation=2),
    )
    assert cli.main(["status", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "FAIL target=node-tar version=7.5.2 runs=2 violations=1" in out
    assert "first-violation=2" in out


@pytest.mark.parametrize(
    ("statuses", "warned"),
    [(("rejected",) * 20, True), (("rejected",) * 19 + ("success",), False)],
)
def test_status_result_line_carries_the_no_extraction_warning(
    tmp_path, capsys, statuses: tuple[str, ...], warned: bool
) -> None:
    # A result-only folder (no live/): the result line gets the same warning as summary.md.
    from inodefence.target_result import JUDGED, CampaignInfo, CaseVerdict

    folder = tmp_path / "2.6.2-123-20-result"
    cases = tuple(
        CaseVerdict(f"step-{i}", JUDGED, None, False, False, status, True)
        for i, status in enumerate(statuses)
    )
    _write_result(
        folder, cases, campaign=CampaignInfo(seed=123, budget=20, runs_to_first_violation=None)
    )
    assert cli.main(["status", str(folder)]) == 0  # exit code unchanged
    out = capsys.readouterr().out
    assert " PASS " in out  # verdict unchanged
    assert ("** 추출 성공 0건(전부 rejected 20)" in out) is warned


def test_status_without_a_result_explains(tmp_path, capsys) -> None:
    assert cli.main(["status", str(tmp_path)]) == 2
    assert "no result.json" in capsys.readouterr().err


def test_status_with_an_unreadable_result_is_not_a_clean_exit(tmp_path, capsys) -> None:
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "result.json").write_text("{bad", encoding="utf-8")
    assert cli.main(["status", str(tmp_path / "bad")]) == 2
    assert "unreadable" in capsys.readouterr().err


def test_summary_to_a_missing_folder_is_an_error_not_a_traceback(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    import inodefence.target_result_summary as summary_module

    monkeypatch.setattr(summary_module, "summarize_file", lambda path, verify_inputs: "# s\n")
    out = tmp_path / "missing" / "s.md"
    assert cli.main(["summary", str(tmp_path / "r.json"), "-o", str(out)]) == 2
    assert "cannot write" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        # verify/explore/replay exit codes carry the result (2 = ERROR), so usage errors are 3.
        (["explore", "--version", "latest", "--dry-run", "--budget", "-5"], 3),
        (["explore", "--version", "latest", "--budget", "x"], 3),
        (["explore"], 3),  # --version missing
        (["verify", "--no-such-flag-is-forwarded", "--dry-run", "--out"], 3),  # --out needs a value
        # status/summary/targets/doctor keep argparse's 2 for usage errors.
        (["replay", "x", "--rounds", "0"], 3),
        (["summary"], 2),
    ],
)
def test_usage_errors_exit_code_by_command(argv: list[str], code: int) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)
    assert raised.value.code == code


def test_explore_dry_run_also_refuses_an_out_inside_the_repo(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    calls = _capture_driver(monkeypatch, tmp_path)
    assert cli.main(["explore", "--version", "latest", "--dry-run", "--out", str(tmp_path)]) == 3
    assert calls == []


@pytest.mark.parametrize("command", ["verify", "explore"])
def test_bad_target_is_a_refusal_named_after_the_command(command: str, capfd) -> None:
    # Integration (real drivers): a usage error exits 3 (2 is the ERROR verdict code) for both
    # commands, and the message names the command the user typed, not the driver file.
    if cli.repo_root() is None:
        pytest.skip("not an editable checkout")
    argv = [command, "--target", "nope", "--version", "1.0.0", "--dry-run"]
    assert cli.main(argv) == 3
    err = capfd.readouterr().err
    assert f"inodefence {command}: error: argument --target: invalid choice: 'nope'" in err
    assert "run_target" not in err


def test_verify_dry_run_plan_shows_the_out_folder(tmp_path: Path, capsys, monkeypatch) -> None:
    from inodefence.drivers import run_target

    monkeypatch.setattr(run_target, "docker_problem", lambda: "docker not consulted in this test")

    out = tmp_path / "verify-out"
    argv = ["--target", "node-tar", "--version", "7.5.2", "--dry-run", "--out", str(out)]
    assert run_target.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["out"] == str(out)
    assert run_target.main(argv[:-2]) == 0  # still optional on --dry-run
    assert json.loads(capsys.readouterr().out)["out"] is None


def test_doctor_adds_leftover_disk_and_memory_lines_and_keeps_the_old_ones(
    monkeypatch, capsys, tmp_path: Path, _docker_ok
) -> None:
    from inodefence.drivers.runtime import health

    monkeypatch.setattr(cli, "repo_root", lambda: tmp_path / "repo")
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setenv("INODEFENCE_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setattr(cli, "_runtime_check", lambda: "OK")
    leftover = health.Residue(containers=("inodefence-local-controller-x (Exited (255))",))
    monkeypatch.setattr(cli, "_find_residue", lambda: leftover)
    cli.main(["doctor"])
    out = capsys.readouterr().out
    # The existing lines are all still there, unchanged.
    assert "[OK] Docker daemon access: server 29.0.0" in out
    assert "[OK] output folder base (environment)" in out
    assert "[WARN] leftover containers / volumes (read-only; nothing is removed): " in out
    assert "inodefence-local-controller-x" in out and "nothing was removed" in out
    assert "free disk at the output folder base: " in out and "GiB free at" in out
    assert "[UNKNOWN] memory headroom for Docker: " in out and "Windows commit limit" in out
    lines = [line for line in out.splitlines() if line.startswith("[")]
    added = [
        i
        for i, line in enumerate(lines)
        if line.split("] ", 1)[1].startswith(("leftover containers", "memory headroom"))
    ]
    assert added and min(added) > lines.index(
        next(line for line in lines if "prepared images" in line)
    )


def test_doctor_does_not_list_leftovers_without_a_usable_daemon(monkeypatch, capsys) -> None:
    asked: list = []
    monkeypatch.setattr(cli, "_find_residue", lambda: asked.append(1))
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(cli, "_docker_server", lambda: ("UNKNOWN", "did not answer in 30s"))
    cli.main(["doctor"])
    out = capsys.readouterr().out
    assert not asked
    assert (
        "[UNKNOWN] leftover containers / volumes (read-only; nothing is removed): not asked" in out
    )


def test_doctor_memory_unknown_never_changes_the_exit_code(
    monkeypatch, capsys, tmp_path: Path, _docker_ok
) -> None:
    if cli.sys.version_info[:2] != (3, 12):
        pytest.skip("doctor fails on a non-3.12 interpreter by design")
    monkeypatch.setattr(cli, "repo_root", lambda: tmp_path / "repo")
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setenv("INODEFENCE_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setattr(cli, "_runtime_check", lambda: "OK")
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "[UNKNOWN] memory headroom for Docker: not checked: inside WSL the Windows commit" in out
    assert "no check failed; 1 UNKNOWN (not verified, see above)" in out


# --- PR 4: where the settings in effect come from, and the refusals doctor and commands share ---


def _repository_line(capsys) -> str:
    out = capsys.readouterr().out
    return next(line for line in out.splitlines() if "] repository (" in line)


def test_doctor_names_an_inodefence_home_that_is_not_a_clone(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    monkeypatch.setenv("INODEFENCE_HOME", str(tmp_path))  # no scripts/ or tools/
    assert cli.main(["doctor"]) == 1
    line = _repository_line(capsys)
    assert line.startswith("[FAIL] repository")
    assert f"INODEFENCE_HOME (environment) is '{tmp_path}' -> {tmp_path}, which is not" in line


def test_doctor_names_the_config_file_as_the_source_of_inodefence_home(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    config = tmp_path / "c.env"
    config.write_text(f"INODEFENCE_HOME={tmp_path / 'nope'}\n", encoding="utf-8")
    monkeypatch.setenv("INODEFENCE_CONFIG", str(config))
    cli.main(["doctor"])
    line = _repository_line(capsys)
    assert "INODEFENCE_HOME (user config file" in line and "that folder does not exist" in line


def test_doctor_says_which_clone_runs_and_what_the_environment_overrides(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    (tmp_path / "other-clone").mkdir()
    repo = _make_repo(tmp_path / "other-clone")  # a clone other than this install's checkout
    config = tmp_path / "c.env"
    config.write_text("INODEFENCE_HOME=/from/the/file\n", encoding="utf-8")
    monkeypatch.setenv("INODEFENCE_CONFIG", str(config))
    monkeypatch.setenv("INODEFENCE_HOME", str(repo))
    cli.main(["doctor"])
    line = _repository_line(capsys)
    assert line.startswith(
        f"[OK] repository (needed by targets / verify / explore / replay): {repo}"
    )
    assert "(INODEFENCE_HOME from the environment)" in line
    assert (
        "the config file's INODEFENCE_HOME=/from/the/file is overridden by the environment" in line
    )
    assert "target commands run this clone's code, not the code doctor runs from" in line


def test_doctor_fails_a_marker_only_clone_like_the_commands_do(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    # Before 0.4 doctor said OK here while every target command refused the same clone.
    monkeypatch.setattr(cli, "_repository_code_problem", _REAL_CODE_PROBLEM)
    (tmp_path / "old").mkdir()
    repo = _make_repo(tmp_path / "old")
    monkeypatch.setenv("INODEFENCE_HOME", str(repo))
    cli.main(["doctor"])
    line = _repository_line(capsys)
    assert line.startswith("[FAIL] repository") and "has no src/inodefence/drivers/" in line
    assert cli.main(["targets"]) == 3  # the same refusal
    assert "has no src/inodefence/drivers/" in capsys.readouterr().err


@pytest.mark.parametrize("source", ["environment", "file"])
def test_a_relative_output_base_is_refused_by_the_commands_as_by_doctor(
    monkeypatch, capsys, tmp_path: Path, source: str
) -> None:
    # Before 0.4 doctor said FAIL but verify / explore used <working directory>/rel/out silently.
    calls = _capture_driver(monkeypatch, tmp_path / "repo")
    if source == "environment":
        monkeypatch.setenv("INODEFENCE_OUTPUT_DIR", "rel/out")
    else:
        config = tmp_path / "c.env"
        config.write_text("INODEFENCE_OUTPUT_DIR=rel/out\n", encoding="utf-8")
        monkeypatch.setenv("INODEFENCE_CONFIG", str(config))
    monkeypatch.chdir(tmp_path)
    assert cli.main(["verify", "--version", "7.5.2", "--dry-run"]) == 3
    assert cli.main(["explore", "--version", "latest", "--dry-run"]) == 3
    assert calls == []
    err = capsys.readouterr().err
    assert err.count("error: no --out given and INODEFENCE_OUTPUT_DIR=rel/out (") == 2
    assert "is not absolute" in err
    cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "[FAIL] output folder base (" in out and "INODEFENCE_OUTPUT_DIR=rel/out (" in out
    assert "[UNKNOWN] free disk at the output folder base: not checked (see above)" in out
    # An explicit relative --out is still taken against the working directory (unchanged).
    assert cli.main(["verify", "--version", "7.5.2", "--dry-run", "--out", "x"]) == 0
    assert calls[0][1][-2:] == ["--out", str(tmp_path / "x")]


@pytest.mark.parametrize(
    ("command", "text"),
    [
        ("verify", "3 refused before anything"),
        ("explore", "2 ERROR (no verdict"),
        ("replay", "4 unsupported"),
        ("doctor", "1 a check failed"),
        ("status", "2 nothing to show"),
        ("summary", "0 written"),
    ],
)
def test_help_states_each_commands_exit_codes(command: str, text: str, capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main([command, "--help"])
    assert raised.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "exit codes:" in out and text in out


def test_help_names_defaults_and_required_options(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["explore", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "(default: node-tar;" in out and "(default: 20)" in out and "(default: 123)" in out
    assert "latest or an exact version (required)" in out
    with pytest.raises(SystemExit):
        cli.main(["verify", "--help"])
    assert "target version (required; repeatable)" in " ".join(capsys.readouterr().out.split())


def test_doctor_warns_on_a_relative_inodefence_home(monkeypatch, capsys, tmp_path: Path) -> None:
    (tmp_path / "clone").mkdir()
    _make_repo(tmp_path / "clone")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INODEFENCE_HOME", "clone")
    cli.main(["doctor"])
    line = _repository_line(capsys)
    assert line.startswith("[WARN] repository") and "INODEFENCE_HOME=clone is relative" in line


def test_doctor_names_the_running_code_and_warns_only_for_pythonpath(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    code = cli._running_code()
    monkeypatch.setattr(cli, "_docker_checks", lambda: [])  # never the host's daemon
    monkeypatch.delenv("PYTHONPATH", raising=False)
    cli.main(["doctor"])
    lines = [x for x in capsys.readouterr().out.splitlines() if x.startswith("[")]
    (line,) = [x for x in lines if "inodefence code running" in x]
    assert line == f"[INFO] inodefence code running doctor / status / summary: {code}"
    assert lines[lines.index(line) + 1].split("] ", 1)[1].startswith("runtime directory")

    monkeypatch.setenv("PYTHONPATH", str(tmp_path))  # unrelated entry: still INFO
    cli.main(["doctor"])
    assert "[INFO] inodefence code running" in capsys.readouterr().out

    monkeypatch.setenv("PYTHONPATH", str(code.parent))
    rc_with = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "[WARN] inodefence code running" in out and "loaded from PYTHONPATH entry" in out
    monkeypatch.delenv("PYTHONPATH")
    assert cli.main(["doctor"]) == rc_with  # the WARN never changes the exit code


@pytest.mark.parametrize("kind", ["file", "under-a-file", "read-only"])
def test_an_unusable_out_is_refused_before_anything_runs(
    monkeypatch, capsys, tmp_path: Path, kind: str
) -> None:
    calls = _capture_driver(monkeypatch, tmp_path / "repo")
    blocker = tmp_path / "blocker"
    if kind == "read-only":
        if cli.os.geteuid() == 0:
            pytest.skip("root can write anywhere")
        blocker.mkdir()
        blocker.chmod(0o500)
        out = blocker / "sub"
    else:
        blocker.write_text("x", encoding="utf-8")
        out = blocker if kind == "file" else blocker / "sub"
    try:
        for command in (["verify", "--version", "7.5.2"], ["explore", "--version", "latest"]):
            assert cli.main([*command, "--dry-run", "--out", str(out)]) == 3
    finally:
        if kind == "read-only":
            blocker.chmod(0o700)
    assert calls == []
    err = capsys.readouterr().err
    assert err.count("; choose another folder") == 2


def test_a_new_nested_out_under_a_writable_folder_passes(monkeypatch, tmp_path: Path) -> None:
    calls = _capture_driver(monkeypatch, tmp_path / "repo")
    out = tmp_path / "a" / "b" / "c"
    assert cli.main(["verify", "--version", "7.5.2", "--dry-run", "--out", str(out)]) == 0
    assert calls and calls[0][1][-2:] == ["--out", str(out)]


def test_doctor_fails_an_output_base_that_is_a_file(monkeypatch, capsys, tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x", encoding="utf-8")
    monkeypatch.setenv("INODEFENCE_OUTPUT_DIR", str(tmp_path / "f"))
    cli.main(["doctor"])
    assert "[FAIL] output folder base (environment)" in capsys.readouterr().out
