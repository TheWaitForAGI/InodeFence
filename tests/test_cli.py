"""inodefence CLI: repo location, targets (table/json), doctor, summary."""

import json
from pathlib import Path

import pytest

from inodefence import cli, locate


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
    monkeypatch.setattr(locate, "_is_repo", lambda root: False)
    assert locate.repo_root() is None


def test_verify_forwards_the_regression_driver_argv(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(
        cli, "run_driver", lambda root, driver, argv: calls.append((driver, argv)) or 0
    )
    assert cli.main(["verify", "--target", "node-tar", "--version", "7.5.2", "--dry-run"]) == 0
    driver, argv = calls[0]
    assert driver == cli.VERIFY_DRIVER
    assert argv == [
        "--target",
        "node-tar",
        "--version",
        "7.5.2",
        "--dry-run",
    ]  # no --out on dry-run


def test_explore_forwards_the_exploration_driver_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list = []
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(
        cli, "run_driver", lambda root, driver, argv: calls.append((driver, argv)) or 0
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
    ]


def test_explore_without_repo_explains_and_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: None)
    assert cli.main(["explore", "--version", "latest"]) == 3
    assert "repository not found" in capsys.readouterr().err


_FAKE_SUPPORT = {
    "decompress": {
        "regression": True,
        "auto_prepare": True,
        "explore": False,
        "explore_reason": "no exploration hook for this target yet",
    },
    "node-tar": {"regression": True, "auto_prepare": True, "explore": True, "explore_reason": None},
}


def test_targets_table_lists_support_and_reasons(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(cli, "target_support", lambda root: _FAKE_SUPPORT)
    assert cli.main(["targets"]) == 0
    out = capsys.readouterr().out
    assert "node-tar" in out and "decompress" in out
    assert "no (no exploration hook for this target yet)" in out


def test_targets_json_is_machine_readable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(cli, "target_support", lambda root: _FAKE_SUPPORT)
    assert cli.main(["targets", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == _FAKE_SUPPORT


def test_targets_without_repo_explains_and_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "repo_root", lambda: None)
    assert cli.main(["targets"]) == 3
    assert "repository not found" in capsys.readouterr().err


def test_doctor_reports_each_check_and_exit_code(monkeypatch, capsys) -> None:
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
    assert "[FAIL] repository" in out and "[FAIL] Docker" in out


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
    assert "node-tar" in support and support["node-tar"]["explore"] is True
    assert support["decompress"]["explore"] is False
