"""The offline replay planner extracts a report's knobs and checks the docker-free parts."""

import json
from pathlib import Path

import pytest
from scripts import replay_report
from scripts.replay_report import build_plan, dry_run_problems, main

_CID = "a" * 64


def _write(path: Path, report: dict) -> Path:
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def _report(**overrides: object) -> dict:
    report: dict = {
        "label": "demo run",
        "producer": "native",
        "node_tar_version": "7.5.22",
        "image_id": "sha256:" + "0" * 64,
        "config": {
            "random_seed": 123,
            "execution_budget": 2,
            "search_policy": "effect-feedback-v2-or-violation-v1-adaptive-mutation-v1",
            "mutation_policy": "uniform-generic-m1-v1",
        },
        "steps": [{"case_id": _CID}, {"case_id": "b" * 64}],
        "initial_case_ids": [_CID],
        "retained_case_ids": ["b" * 64],
    }
    report.update(overrides)
    return report


def test_build_plan_extracts_knobs_and_command(tmp_path: Path) -> None:
    plan = build_plan(_write(tmp_path / "r.json", _report()))
    assert plan.seed == 123 and plan.budget == 2
    assert plan.make_target == "demo"
    assert plan.command() == (
        "make demo DEMO_SEED=123 DEMO_BUDGET=2 "
        "DEMO_POLICY=effect-feedback-v2-or-violation-v1-adaptive-mutation-v1 "
        "DEMO_MUTATION_POLICY=uniform-generic-m1-v1"
    )
    assert len(plan.case_ids) == 2


def test_historical_report_uses_historical_target_with_tar_version(tmp_path: Path) -> None:
    plan = build_plan(_write(tmp_path / "r.json", _report(label="demo run historical")))
    assert plan.make_target == "demo-native-historical"
    assert "TAR_VERSION=7.5.22" in plan.command()


def test_dry_run_clean_without_recipe(tmp_path: Path) -> None:
    report = _report()
    report.pop("image_id")
    plan = build_plan(_write(tmp_path / "r.json", report))
    assert plan.recipe_sha256 is None
    assert dry_run_problems(plan) == []


def test_dry_run_flags_recipe_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = _report(image_recipe={"recipe_sha256": "f" * 64, "tar_version": "7.5.22"})
    monkeypatch.setattr(replay_report, "compare_report", lambda _p: ["recipe_sha256 differs"])
    plan = build_plan(_write(tmp_path / "r.json", report))
    problems = dry_run_problems(plan)
    assert any("recipe binding: recipe_sha256 differs" in item for item in problems)


def test_dry_run_flags_bad_fields_and_sequence(tmp_path: Path) -> None:
    report = _report(image_id="not-a-digest")
    report["config"]["random_seed"] = "x"
    report["steps"] = [{"case_id": "short"}]
    report["config"]["execution_budget"] = 2
    report["retained_case_ids"] = ["c" * 64]
    plan = build_plan(_write(tmp_path / "r.json", report))
    problems = dry_run_problems(plan)
    assert any("random_seed" in p for p in problems)
    assert any("not a sha256 digest" in p for p in problems)
    assert any("not 64-hex" in p for p in problems)
    assert any("count" in p for p in problems)
    assert any("retained_case_ids" in p for p in problems)


def test_sequence_fingerprint_is_order_sensitive(tmp_path: Path) -> None:
    a = build_plan(_write(tmp_path / "a.json", _report())).sequence_fingerprint
    reversed_report = _report(steps=[{"case_id": "b" * 64}, {"case_id": _CID}])
    b = build_plan(_write(tmp_path / "b.json", reversed_report)).sequence_fingerprint
    assert a != b


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _report()
    report.pop("image_id")
    good = _write(tmp_path / "good.json", report)
    assert main(["--report", str(good)]) == 0
    bad_report = _report()
    bad_report["steps"] = []
    bad = _write(tmp_path / "bad.json", bad_report)
    assert main(["--report", str(bad), "--json"]) == 1
    out = capsys.readouterr().out
    assert "problems" in out
