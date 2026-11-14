"""run_target_explore host driver: report -> common campaign result (no docker; fakes)."""

from __future__ import annotations

import base64
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import scripts.run_target_explore as rte

from inodefence.target_result import Verdict, load_target_result

TAR = b"ustar-ish bytes for a violating case"


def _prepared(version: str = "7.5.23", requested: str = "latest") -> rte.PreparedNodeTar:
    return rte.PreparedNodeTar(
        requested, version, f"inodefence-node-tar-registry:{version}", "sha256:" + "a" * 64, True
    )


def _report(*, runs: int, violating_index: int | None) -> dict:
    records = [
        {"run_index": i, "outcome": "extracted", "c0": False, "c1": False, "c2": False}
        for i in range(runs)
    ]
    violation_inputs = []
    if violating_index is not None:
        records[violating_index] = {
            "run_index": violating_index,
            "outcome": "extracted",
            "c0": False,
            "c1": True,
            "c2": True,
        }
        violation_inputs.append(
            {
                "run_index": violating_index,
                "tar_sha256": sha256(TAR).hexdigest(),
                "tar_b64": base64.b64encode(TAR).decode(),
            }
        )
    return {"demo_report_schema": 4, "case_records": records, "violation_inputs": violation_inputs}


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.run_target as rt

    monkeypatch.setattr(
        rt, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )


def test_violating_run_writes_result_with_only_violating_inputs(tmp_path: Path) -> None:
    result, tar_files = rte.build_campaign_result(
        _report(runs=5, violating_index=2), _prepared(), seed=1, budget=5
    )
    assert result.verdict is Verdict.FAIL
    assert result.executed == 5  # cases[] lists every run
    assert result.violating_cases == ("step-2",)  # only the violating case flagged
    assert result.campaign is not None and result.campaign.runs_to_first_violation == 3  # 1-based
    assert list(tar_files) == ["inputs/step-2.tar"]  # only the violating input saved
    assert tar_files["inputs/step-2.tar"] == TAR
    # the saved result round-trips through the strict reader after writing
    path = rte.write_result(tmp_path / "r", result, tar_files)
    reread = load_target_result(path)
    assert reread.executed == 5 and reread.provenance.image_id == "sha256:" + "a" * 64


def test_no_violation_writes_result_with_empty_inputs(tmp_path: Path) -> None:
    result, tar_files = rte.build_campaign_result(
        _report(runs=4, violating_index=None), _prepared(), seed=1, budget=4
    )
    assert result.verdict is Verdict.PASS
    assert result.executed == 4 and result.violating_cases == ()
    assert result.campaign is not None and result.campaign.runs_to_first_violation is None
    assert tar_files == {}
    path = rte.write_result(tmp_path / "r", result, tar_files)
    assert not any((tmp_path / "r" / "inputs").iterdir())  # inputs/ is empty, no violation
    assert "no" not in load_target_result(path).violating_cases  # (sanity: nothing violated)


def test_tampered_violation_input_is_rejected() -> None:
    report = _report(runs=3, violating_index=1)
    report["violation_inputs"][0]["tar_b64"] = base64.b64encode(b"different bytes").decode()
    with pytest.raises(ValueError, match="SHA-256"):
        rte.build_campaign_result(report, _prepared(), seed=1, budget=3)


def test_dry_run_prepares_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbid(*_: object, **__: object) -> object:
        raise AssertionError("dry-run must not prepare or run")

    monkeypatch.setattr(rte, "ensure_image", forbid)
    monkeypatch.setattr(rte, "run_controller", forbid)
    assert rte.main(["--version", "latest", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["note"].startswith("dry-run")


def test_real_run_requires_auto_prepare(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rte, "ensure_image", lambda *a, **k: _prepared())
    with pytest.raises(SystemExit):
        rte.main(["--version", "latest"])  # no --auto-prepare


def test_main_wires_prepare_controller_and_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rte, "ensure_image", lambda spec, **k: _prepared(requested=spec))

    def fake_controller(prepared: Any, *, out: Path, run_id: str, **k: Any) -> Path:
        path = rte.controller_report_path(out, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_report(runs=3, violating_index=0)), encoding="utf-8")
        return path

    monkeypatch.setattr(rte, "run_controller", fake_controller)
    code = rte.main(
        [
            "--version",
            "latest",
            "--auto-prepare",
            "--seed",
            "1",
            "--budget",
            "3",
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 1  # a violation -> exit 1
    (result_json,) = tmp_path.rglob("result.json")
    assert load_target_result(result_json).verdict is Verdict.FAIL
    assert (result_json.parent / "inputs" / "step-0.tar").read_bytes() == TAR
