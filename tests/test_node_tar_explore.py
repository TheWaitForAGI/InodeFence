"""node_tar_explore: loop report -> common campaign result, and the explore hook (no docker)."""

from __future__ import annotations

import base64
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import scripts.node_tar_explore as nte
from scripts.run_target import ExploreOptions, PreparedTargetImage

from inodefence.target_result import Verdict, load_target_result

TAR = b"ustar-ish bytes for a violating case"


def _prepared(version: str = "7.5.23", requested: str = "latest") -> PreparedTargetImage:
    return PreparedTargetImage(
        "node-tar", requested, version, f"inodefence-node-tar-registry:{version}",
        "sha256:" + "a" * 64, True,
    )  # fmt: skip


def _report(*, runs: int, violating_index: int | None) -> dict:
    records = [
        {"run_index": i, "outcome": "extracted", "c0": False, "c1": False, "c2": False}
        for i in range(runs)
    ]
    violation_inputs: list[dict] = []
    if violating_index is not None:
        records[violating_index] = {
            "run_index": violating_index, "outcome": "extracted",
            "c0": False, "c1": True, "c2": True,
        }  # fmt: skip
        violation_inputs.append(
            {
                "run_index": violating_index,
                "tar_sha256": sha256(TAR).hexdigest(),
                "tar_b64": base64.b64encode(TAR).decode(),
            }  # fmt: skip
        )
    return {"demo_report_schema": 4, "case_records": records, "violation_inputs": violation_inputs}


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.run_target as rt

    monkeypatch.setattr(
        nte, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )


def test_violating_run_writes_result_with_only_violating_inputs(tmp_path: Path) -> None:
    result, tar_files = nte.build_campaign_result(
        _report(runs=5, violating_index=2), _prepared(), seed=1, budget=5
    )
    assert result.verdict is Verdict.FAIL
    assert result.executed == 5  # cases[] lists every run
    assert result.violating_cases == ("step-2",)
    assert result.campaign is not None and result.campaign.runs_to_first_violation == 3
    assert list(tar_files) == ["inputs/step-2.tar"] and tar_files["inputs/step-2.tar"] == TAR
    path = nte.write_result(tmp_path / "r", result, tar_files)
    reread = load_target_result(path)
    assert reread.executed == 5 and reread.provenance.image_id == "sha256:" + "a" * 64


def test_no_violation_writes_result_with_empty_inputs(tmp_path: Path) -> None:
    result, tar_files = nte.build_campaign_result(
        _report(runs=4, violating_index=None), _prepared(), seed=1, budget=4
    )
    assert result.verdict is Verdict.PASS and result.executed == 4
    assert result.campaign is not None and result.campaign.runs_to_first_violation is None
    assert tar_files == {}
    path = nte.write_result(tmp_path / "r", result, tar_files)
    assert not any((tmp_path / "r" / "inputs").iterdir())
    assert load_target_result(path).violating_cases == ()


def test_tampered_violation_input_is_rejected() -> None:
    report = _report(runs=3, violating_index=1)
    report["violation_inputs"][0]["tar_b64"] = base64.b64encode(b"different bytes").decode()
    with pytest.raises(ValueError, match="SHA-256"):
        nte.build_campaign_result(report, _prepared(), seed=1, budget=3)


def test_hook_runs_the_controller_and_writes_result_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_controller(prepared: Any, *, out: Path, run_id: str, **k: Any) -> Path:
        path = nte.controller_report_path(out, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_report(runs=4, violating_index=0)), encoding="utf-8")
        return path

    monkeypatch.setattr(nte, "run_controller", fake_controller)
    outcome = nte.explore(_prepared(), ExploreOptions(budget=4, seed=1, out=tmp_path))
    assert outcome.verdict == "FAIL" and outcome.runs == 4 and outcome.violations == 1
    assert load_target_result(outcome.result_path).verdict is Verdict.FAIL
    assert (outcome.result_path.parent / "inputs" / "step-0.tar").read_bytes() == TAR
    assert (outcome.result_path.parent / "summary.md").is_file()


def test_hook_rejects_budget_below_the_seed_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(nte, "run_controller", lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(ValueError, match="seed count"):
        nte.explore(_prepared(), ExploreOptions(budget=nte.MIN_BUDGET - 1, seed=1, out=tmp_path))
