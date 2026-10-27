"""Terminal summary of the demo loop: one line per step and a closing summary (P0-5)."""

import argparse
import copy
from pathlib import Path
from typing import Any, cast

import pytest
from scripts import container_controller

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_demo import (
    EffectStepReporter,
    effect_campaign_report,
    render_effect_campaign_summary,
    render_effect_step_summary,
)
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.mutator import MutationPolicy

CONFIG = EffectCampaignConfig(
    random_seed=123,
    execution_budget=12,
    search_policy=EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
    mutation_policy=MutationPolicy.M1,
)


def _report() -> dict[str, Any]:
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)
    return effect_campaign_report(result, "synthetic")


def _steps(report: dict[str, Any]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], report["steps"])


def test_step_summary_is_one_line_per_step_from_the_same_records() -> None:
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)
    reporter = EffectStepReporter()
    lines = [
        render_effect_step_summary(reporter.add(step), CONFIG.execution_budget)
        for step in result.steps
    ]

    assert len(lines) == CONFIG.execution_budget
    assert all("\n" not in line for line in lines)
    assert lines[0].startswith("step 01/12  seed")
    assert all(line.endswith("SYNTHETIC") for line in lines), "synthetic lines must say so"
    assert all("C0 ok" in line and "C1 ok" in line and "C2 ok" in line for line in lines)
    # The counter follows the record index, not the call order.
    assert [line.split()[1] for line in lines] == [f"{i:02d}/12" for i in range(1, 13)]


def test_step_summary_shows_the_operator_reward_and_weight_move() -> None:
    steps = _steps(_report())
    rewarded = next(step for step in steps if (step["scheduler_evidence"] or {}).get("reward"))
    line = render_effect_step_summary(rewarded)
    operator = rewarded["mutation_attempt"]["operator_id"]
    before = rewarded["scheduler_evidence"]["weights_before"][operator]
    after = rewarded["scheduler_evidence"]["weights_after"][operator]

    assert line.startswith(f"step {rewarded['index'] + 1:02d}  ")
    assert f"  {operator}" in line
    assert "reward 1" in line
    assert f"weight {operator} {before}->{after}" in line
    size = rewarded["selection"]["corpus_admission"]["corpus_size_before"]
    assert f"corpus {size}->{size + 1}" in line

    unrewarded = next(
        step
        for step in steps
        if step["scheduler_evidence"] and not step["scheduler_evidence"]["reward"]
    )
    plain = render_effect_step_summary(unrewarded)
    assert "reward 0" in plain
    assert "weight " not in plain


def test_step_summary_marks_a_violation_and_observation_failures() -> None:
    record = copy.deepcopy(_steps(_report())[3])
    record["oracle"]["C1"] = True
    record["trace"]["observation_failures"] = [
        {"kind": "event_loss", "message": "dropped", "sequence": 7}
    ]

    line = render_effect_step_summary(record, 12)

    assert "C1 VIOLATED" in line
    assert "C0 ok" in line and "C2 ok" in line
    assert "obs-fail 1" in line


def test_step_summary_counts_paths_that_share_an_identity() -> None:
    record = copy.deepcopy(_steps(_report())[0])
    event = record["trace"]["effect_events"][0]
    event["paths"][0]["after"] = {
        "status": "present",
        "object_type": "regular",
        "st_dev": 1,
        "st_ino": 2,
        "st_nlink": 2,
        "size": 0,
    }

    assert "nlink>1 1" in render_effect_step_summary(record)


def test_campaign_summary_counts_match_the_report() -> None:
    report = _report()
    steps = _steps(report)

    text = render_effect_campaign_summary(report)
    lines = text.splitlines()

    assert lines[0].startswith("demo summary: ")
    assert f"steps={len(steps)}" in lines[0]
    assert "SYNTHETIC (not node-tar)" in lines[0]
    assert lines[1].startswith("  termination: ")
    assert sum(
        int(part.split()[-1]) for part in lines[1].removeprefix("  termination: ").split(", ")
    ) == len(steps)
    assert lines[2] == "  oracle violations: 0 (C0 0, C1 0, C2 0)"
    unique = report["final_search_stats"]["value"]["unique_effect_keys"]
    rewarded = [
        str(step["index"] + 1) for step in steps if (step["scheduler_evidence"] or {}).get("reward")
    ]
    assert f"unique effect keys {unique}" in lines[3]
    assert f"reward steps {','.join(rewarded)}" in lines[3]
    retained = len(report["retained_case_ids"])
    initial = len(report["initial_case_ids"])
    assert f"retained corpus {retained} (initial {initial})" in lines[3]
    assert lines[4].startswith("  final weights: ")


def test_campaign_summary_rejects_an_aborted_report() -> None:
    with pytest.raises(ValueError, match="finished report"):
        render_effect_campaign_summary({"label": "demo run", "producer": "native", "aborted": {}})


def test_controller_demo_prints_each_step_and_the_summary_to_stderr(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)
    report = effect_campaign_report(result, "native")
    report.update(label="demo run", node_tar_version="7.5.22")

    def fake_native_demo_report(backend, image, *, step_sink, **options):
        for step in _steps(report):
            step_sink(step)
        return report

    monkeypatch.setattr(container_controller, "native_demo_report", fake_native_demo_report)
    args = argparse.Namespace(seed=123, budget=12, policy=None, mutation_policy=None)

    returncode = container_controller.run_native_effect_demo(
        object(),  # type: ignore[arg-type]
        "img",
        tmp_path / "demo.json",
        args,
    )

    assert returncode == 0
    err = capsys.readouterr().err
    assert "effect-demo: seed=123 budget=12" in err
    step_lines = [line for line in err.splitlines() if line.startswith("step ")]
    assert len(step_lines) == 12
    assert step_lines[0].startswith("step 01/12  seed")
    assert "demo summary: producer=native steps=12 label='demo run' node-tar=7.5.22" in err
    assert capsys.readouterr().out == ""
