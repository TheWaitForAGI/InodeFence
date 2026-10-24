"""Per-step JSONL of the demo loop: finished steps survive a native abort (P0-5)."""

import argparse
import json
from pathlib import Path
from typing import Any, cast

import pytest
from scripts import container_controller, run_effect_demo
from scripts.run_effect_demo import NativeDemoAborted, native_demo_report

from inodefence.effect_campaign import (
    EffectCampaignConfig,
    EffectCampaignStep,
    run_effect_campaign,
)
from inodefence.effect_demo import (
    EffectStepReporter,
    effect_campaign_report,
    render_effect_step_line,
)
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.mutator import MutationPolicy


def _steps(report: dict[str, object]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], report["steps"])


CONFIG = EffectCampaignConfig(
    random_seed=123,
    execution_budget=12,
    search_policy=EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
    mutation_policy=MutationPolicy.M1,
)


def test_on_step_sees_every_step_in_order_without_changing_the_result() -> None:
    seen: list[EffectCampaignStep] = []
    observed = run_effect_campaign(
        minimal_seed_corpus(), synthetic_effect_result, CONFIG, on_step=seen.append
    )
    plain = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)

    assert [step.index for step in seen] == list(range(CONFIG.execution_budget))
    assert tuple(seen) == observed.steps == plain.steps


def test_on_step_must_be_callable() -> None:
    with pytest.raises(ValueError, match="on_step"):
        run_effect_campaign(
            minimal_seed_corpus(),
            synthetic_effect_result,
            CONFIG,
            on_step="not callable",  # type: ignore[arg-type]
        )


def test_step_reporter_reproduces_the_report_steps_as_single_jsonl_lines() -> None:
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)
    report = effect_campaign_report(result, "synthetic")
    reporter = EffectStepReporter()

    lines = [render_effect_step_line(reporter.add(step)) for step in result.steps]

    assert [json.loads(line) for line in lines] == _steps(report)
    assert all(line.endswith("\n") and "\n" not in line[:-1] for line in lines)
    # The retained-corpus channel is rebuilt incrementally, not from the whole report.
    sizes = [
        step["selection"]["corpus_admission"]["corpus_size_before"]
        for step in _steps(report)
        if step["selection"] is not None
    ]
    assert sizes == sorted(sizes) and sizes[0] >= 1


def test_step_reporter_rejects_skipped_or_repeated_steps() -> None:
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)
    reporter = EffectStepReporter()
    reporter.add(result.steps[0])

    with pytest.raises(ValueError, match="expected step 1"):
        reporter.add(result.steps[2])
    with pytest.raises(ValueError, match="expected step 1"):
        reporter.add(result.steps[0])
    with pytest.raises(ValueError, match="EffectCampaignStep"):
        reporter.add(object())  # type: ignore[arg-type]


class _FakeTarget:
    tar_version = run_effect_demo.pinned_node_tar_version()
    node_version = "22.22.0"


class _FakeRun:
    def __init__(self, result) -> None:
        self.result = result
        self.controller_flush_verified = True
        self.transport_error = None
        self.raw_stream = b""


def test_forced_abort_leaves_the_completed_steps_with_the_sink(monkeypatch) -> None:
    """The producer fails on the 3rd case; the 2 finished steps were already delivered."""
    calls = 0

    def fake_run(case, target):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("container backend vanished")
        return _FakeRun(synthetic_effect_result(case))

    monkeypatch.setattr(
        run_effect_demo.NodeTarEffectTarget, "bind", lambda *args, **kwargs: _FakeTarget()
    )
    monkeypatch.setattr(run_effect_demo, "run_node_tar_effect_case", fake_run)
    records: list[dict[str, Any]] = []

    with pytest.raises(NativeDemoAborted) as aborted:
        native_demo_report(object(), "sha256:" + "0" * 64, budget=6, step_sink=records.append)  # type: ignore[arg-type]

    assert aborted.value.step_index == 2
    assert "OSError" in aborted.value.reason
    assert [record["index"] for record in records] == [0, 1]
    assert [record["origin"] for record in records] == ["seed", "seed"]
    assert all(record["trace"]["synthetic"] is True for record in records)


def test_controller_demo_writes_steps_jsonl_before_the_final_report(
    monkeypatch, tmp_path: Path
) -> None:
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)
    report = effect_campaign_report(result, "native")
    report.update(label="demo run")
    evidence = tmp_path / "inodefence-effect-demo-native-test.json"
    steps_path = container_controller.demo_steps_path(evidence)
    assert steps_path == tmp_path / "inodefence-effect-demo-native-test.steps.jsonl"

    def fake_native_demo_report(backend, image, *, step_sink, **options):
        for step in _steps(report)[:5]:
            step_sink(step)
        raise NativeDemoAborted(5, _steps(report)[5]["case_id"], "forced abort in test")

    monkeypatch.setattr(container_controller, "native_demo_report", fake_native_demo_report)
    args = argparse.Namespace(seed=None, budget=None, policy=None, mutation_policy=None)

    returncode = container_controller.run_native_effect_demo(object(), "img", evidence, args)  # type: ignore[arg-type]

    assert returncode == 1
    lines = steps_path.read_text(encoding="ascii").splitlines()
    assert [json.loads(line) for line in lines] == _steps(report)[:5]
    final = json.loads(evidence.read_text(encoding="ascii"))
    assert set(final) == {"label", "producer", "aborted"}
    assert final["aborted"]["step_index"] == 5
    assert "steps" not in final


def test_controller_demo_success_keeps_jsonl_equal_to_report_steps(
    monkeypatch, tmp_path: Path
) -> None:
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)
    report = effect_campaign_report(result, "native")
    report.update(label="demo run")
    evidence = tmp_path / "demo.json"

    def fake_native_demo_report(backend, image, *, step_sink, **options):
        for step in _steps(report):
            step_sink(step)
        return report

    monkeypatch.setattr(container_controller, "native_demo_report", fake_native_demo_report)
    args = argparse.Namespace(seed=None, budget=None, policy=None, mutation_policy=None)

    returncode = container_controller.run_native_effect_demo(object(), "img", evidence, args)  # type: ignore[arg-type]

    assert returncode == 0
    lines = container_controller.demo_steps_path(evidence).read_text("ascii").splitlines()
    final = json.loads(evidence.read_text(encoding="ascii"))
    assert [json.loads(line) for line in lines] == final["steps"]
    assert final["label"] == "demo run"
