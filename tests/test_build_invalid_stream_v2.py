"""v2 build-invalid steps through the shared launcher's step stream and the live record (D060, W4).

Synthetic only. The shared launcher streams steps through ``on_step`` into
``EffectStepReporter`` (and, with a recorder, ``live_step_from_effect``) and never passes
``on_build_invalid``; these tests drive the same objects the same way:

* the loop hands build-invalid steps to the step callback in index order, so the reporter's
  contiguity check holds and the stream has one record per budget unit;
* the live status is ``build-invalid``, never ``unjudged``; it is counted apart and the
  progress key appears only when nonzero, so a run without one is byte-identical;
* a stream report (no ``config``) proves ``record`` from its records;
* no product default or allow-listed policy records build-invalid steps.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import inodefence.effect_campaign as effect_campaign
from inodefence.builder import build_tar
from inodefence.drivers.decompress import explore as decompress_explore
from inodefence.drivers.oras_go import explore as oras_go_explore
from inodefence.effect_campaign import BuildInvalidStep, run_effect_campaign
from inodefence.effect_demo import EffectStepReporter
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.rds import (
    RdsArm,
    RdsCellConfig,
    RVariant,
    VocabularyMode,
    run_rds_cell,
)
from inodefence.evaluation.rds_report import ReportFormatError
from inodefence.evaluation.rds_report_v2 import (
    check_records_policy_v2,
    step_outcome,
    summarize_report_records_v2,
)
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.live_effect import live_step_from_effect
from inodefence.live_exploration import (
    BUILD_INVALID_STATUS,
    LiveRecorder,
    LiveRunMeta,
    LiveStep,
)
from inodefence.model import ArchiveCase
from inodefence.mutator import MutationPolicy
from inodefence.mutator.policy import RECORDS_BUILD_INVALID

V2 = MutationPolicy.V2_FREEZE3_FIXED_BASELINE
BUDGET = 40
_SEED_IDS = frozenset(case.case_id for case in minimal_seed_corpus())


@pytest.fixture
def refusing_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    def build(case: ArchiveCase) -> bytes:
        if (
            case.case_id not in _SEED_IDS
            and int(hashlib.sha256(case.case_id.encode()).hexdigest(), 16) % 3 == 0
        ):
            raise ValueError("entry 0 cannot be represented in USTAR: synthetic refusal")
        return build_tar(case)

    monkeypatch.setattr(effect_campaign, "build_tar", build)


def _v2_config() -> Any:
    cell = RdsCellConfig(
        RdsArm.S_U, 777, BUDGET, VocabularyMode.OBSERVED_NAMES_V2_FREEZE3, RVariant.WALK
    )
    return cell, cell.campaign_config()


def _stream(tmp_path: Path) -> tuple[list[dict[str, Any]], LiveRecorder, Any]:
    """What the shared launcher does: on_step -> reporter (+ live recorder), no on_build_invalid."""
    cell, config = _v2_config()
    assert config.build_invalid is None  # the launcher never sets it; the profile decides
    reporter = EffectStepReporter()
    recorder = LiveRecorder(tmp_path / "live", LiveRunMeta("synthetic", "0", 777, BUDGET))
    records: list[dict[str, Any]] = []

    def record_step(step: Any) -> None:
        records.append(reporter.add(step))
        recorder.on_step(live_step_from_effect(step))

    result = run_effect_campaign(
        minimal_seed_corpus(), synthetic_effect_result, config, on_step=record_step
    )
    recorder.close()
    return records, recorder, result


def test_stream_receives_every_budget_unit_in_order(refusing_builder: None, tmp_path: Path) -> None:
    records, _, result = _stream(tmp_path)
    assert [record["index"] for record in records] == list(range(BUDGET))
    invalid = [record for record in records if step_outcome(record) == "build-invalid"]
    assert len(invalid) == len(result.build_invalid_steps) > 0


def test_live_status_is_build_invalid_not_unjudged(refusing_builder: None, tmp_path: Path) -> None:
    records, recorder, result = _stream(tmp_path)
    snapshot = recorder.snapshot()
    invalid = len(result.build_invalid_steps)
    assert snapshot["build_invalid"] == {"steps": invalid}
    assert snapshot["unjudged"]["steps"] == 0
    assert snapshot["runs_executed"] == BUDGET
    assert sum(snapshot["terminations"].values()) == BUDGET - invalid
    live = live_step_from_effect(result.build_invalid_steps[0])
    assert live.status == BUILD_INVALID_STATUS and not live.unjudged and not live.violated


def test_build_invalid_live_step_cannot_carry_verdicts() -> None:
    with pytest.raises(ValueError, match="build-invalid"):
        LiveStep(index=5, case_id="x", status=BUILD_INVALID_STATUS, unjudged=True)


def test_progress_without_build_invalid_is_unchanged(tmp_path: Path) -> None:
    """A run with no build-invalid step writes the same progress keys as before (no new key)."""
    cell = RdsCellConfig(RdsArm.S_U, 777, BUDGET, VocabularyMode.OBSERVED_NAMES, RVariant.WALK)
    recorder = LiveRecorder(tmp_path / "live", LiveRunMeta("synthetic", "0", 777, BUDGET))
    run_effect_campaign(
        minimal_seed_corpus(),
        synthetic_effect_result,
        cell.campaign_config(),
        on_step=lambda step: recorder.on_step(live_step_from_effect(step)),
    )
    recorder.close()
    snapshot = json.loads((tmp_path / "live" / "progress.json").read_text())
    assert "build_invalid" not in snapshot
    assert set(snapshot["terminations"]) == {"success", "rejected", "failed", "timed_out"}


def test_stream_records_prove_record_policy(refusing_builder: None, tmp_path: Path) -> None:
    records, _, _ = _stream(tmp_path)
    check_records_policy_v2(records, mutation_policy=V2)
    cell, _ = _v2_config()
    summary = summarize_report_records_v2(records, cell)
    # extractor runs are counted from outcome, never from runs_executed
    assert summary.executed_steps == sum(1 for r in records if step_outcome(r) == "executed")
    with pytest.raises(ReportFormatError, match="does not record"):
        check_records_policy_v2(
            records, mutation_policy=MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE
        )
    no_schema = [dict(record) for record in records]
    del no_schema[3]["step_record_schema"]
    with pytest.raises(ReportFormatError, match="step_record_schema"):
        check_records_policy_v2(no_schema, mutation_policy=V2)
    mixed = [dict(record) for record in records]
    mixed[-1] = {
        **mixed[-1],
        "mutation_attempt": {**mixed[-1]["mutation_attempt"], "mutation_policy": "other"},
    }
    with pytest.raises(ReportFormatError, match="carry"):
        check_records_policy_v2(mixed, mutation_policy=V2)


def test_rds_cell_routes_build_invalid_away_from_typed_collector(refusing_builder: None) -> None:
    cell, _ = _v2_config()
    seen: list[Any] = []
    result = run_rds_cell(minimal_seed_corpus(), synthetic_effect_result, cell, on_step=seen.append)
    assert result.campaign.build_invalid_steps
    assert not any(isinstance(step, BuildInvalidStep) for step in seen)
    assert result.summary.executions_completed == BUDGET  # build-invalid = one budget unit
    assert not result.summary.hit or result.summary.hit_steps > 0


def test_record_policy_explicit_override_still_wins(refusing_builder: None) -> None:
    _, config = _v2_config()
    aborting = dataclasses.replace(config, build_invalid=effect_campaign.BuildInvalidPolicy.ABORT)
    assert aborting.build_invalid_policy == effect_campaign.BuildInvalidPolicy.ABORT


def test_no_product_policy_records_build_invalid() -> None:
    from scripts import run_effect_demo

    product = {
        *decompress_explore.SUPPORTED_MUTATION_POLICIES,
        decompress_explore.DEFAULT_MUTATION_POLICY,
        *oras_go_explore.SUPPORTED_MUTATION_POLICIES,
        oras_go_explore.DEFAULT_MUTATION_POLICY,
        run_effect_demo.EXPLORE_MUTATION_POLICY.value,
        run_effect_demo.HISTORICAL_MUTATION_POLICY.value,
    }
    assert not product & {policy.value for policy in RECORDS_BUILD_INVALID}
