"""run_target: node-tar adapter -> inodefence-target-result-v1 files (no docker; run_one mocked)."""

import json
from pathlib import Path
from typing import Any

import pytest
import scripts.regression_check as rc
import scripts.run_target as rt

from inodefence.target_result import RUN_ERROR, Provenance, Verdict, load_target_result

SHARED = {
    "declined": None,
    "shared_identity": ["extract/link"],
    "reference_before": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
    "reference_after": {"ino": "5", "nlink": 2, "size": 10, "type": "reg"},
}
DECLINED = {
    "declined": {"code": "TAR_ENTRY_ERROR", "message": "linkpath escapes extraction directory"},
    "shared_identity": [],
    "reference_before": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
    "reference_after": {"ino": "5", "nlink": 1, "size": 10, "type": "reg"},
}


def _fake_run_one(raw_by_version: dict[str, dict[str, Any]]):
    def run_one(release: str, tar_b64: str) -> dict[str, Any]:
        return raw_by_version[release]

    return run_one


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rt, "engine_provenance", lambda image: Provenance("b" * 40, False, image, "sha256:abc")
    )


def test_pair_writes_common_results_with_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt.cri, "run_one", _fake_run_one({"7.5.2": SHARED, "7.5.3": DECLINED}))
    code = rt.main(
        ["--target", "node-tar", "--version", "7.5.2", "--version", "7.5.3", "--out", str(tmp_path)]
    )
    assert code == 1  # worst verdict across versions: FAIL

    affected = load_target_result(tmp_path / "node-tar-7.5.2" / "result.json")
    fixed = load_target_result(tmp_path / "node-tar-7.5.3" / "result.json")
    assert affected.verdict is Verdict.FAIL and fixed.verdict is Verdict.PASS
    assert affected.axes.target_version == "7.5.2" and affected.axes.extraction_filter is None
    assert affected.observed_contracts == ("C1", "C2")
    names = [f.name for f in rc.build_fixtures()]
    assert [c.case_id for c in affected.cases] == names
    assert all(c.c0 is None for c in affected.cases)  # C0 not observed on this path
    assert {(c.c1, c.c2) for c in affected.cases} == {(True, True)}
    assert {(c.outcome, c.c1, c.c2) for c in fixed.cases} == {("declined", False, False)}
    assert affected.provenance.image_ref == "inodefence-node-tar-effect:7.5.2"

    # The saved inputs are exactly the regression fixtures; raw observations are kept unchanged.
    fixture = rc.build_fixtures()[0]
    saved = tmp_path / "node-tar-7.5.2" / "inputs" / f"{fixture.name}.tar"
    assert saved.read_bytes() == fixture.tar
    raw = json.loads((tmp_path / "node-tar-7.5.3" / "raw" / f"{fixture.name}.json").read_text())
    assert raw == DECLINED

    out = capsys.readouterr().out
    assert "TARGET-RUN FAIL target=node-tar version=7.5.2" in out
    assert "TARGET-RUN PASS target=node-tar version=7.5.3" in out


def test_unobservable_case_is_error_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = {"_run_error": True, "_rc": 125, "_stderr": "no such image"}
    monkeypatch.setattr(rt.cri, "run_one", _fake_run_one({"9.9.9": broken}))
    assert rt.main(["--target", "node-tar", "--version", "9.9.9", "--out", str(tmp_path)]) == 2
    result = load_target_result(tmp_path / "node-tar-9.9.9" / "result.json")
    assert result.verdict is Verdict.ERROR
    assert {(c.outcome, c.c1, c.c2) for c in result.cases} == {(RUN_ERROR, None, None)}


def test_missing_reference_state_is_error() -> None:
    raw = {"declined": None, "shared_identity": [], "reference_before": None}
    case = rt._node_tar_case(rc.build_fixtures()[0], raw)
    assert case.verdict.outcome == RUN_ERROR and case.verdict.c2 is None


def test_refuses_to_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt.cri, "run_one", _fake_run_one({"7.5.3": DECLINED}))
    args = ["--target", "node-tar", "--version", "7.5.3", "--out", str(tmp_path)]
    assert rt.main(args) == 0
    with pytest.raises(SystemExit):
        rt.main(args)


def test_dry_run_runs_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*_: object) -> dict[str, Any]:
        raise AssertionError("dry-run must not run a container")

    monkeypatch.setattr(rt.cri, "run_one", forbidden)
    assert rt.main(["--target", "node-tar", "--version", "7.5.2", "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["versions"]["7.5.2"]["image"] == "inodefence-node-tar-effect:7.5.2"
    assert len(plan["versions"]["7.5.2"]["would_run"]) == len(rc.build_fixtures())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--target", "node-tar", "--version", "latest", "--dry-run"],
        ["--target", "node-tar", "--version", "7.5.2", "--version", "7.5.2", "--dry-run"],
        ["--target", "gnu-tar", "--version", "1.35", "--dry-run"],
        ["--target", "node-tar", "--version", "7.5.2"],  # no --out
    ],
)
def test_rejects_bad_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        rt.main(argv)
