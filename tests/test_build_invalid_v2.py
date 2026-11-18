"""v2 U2: build-invalid steps, report schema 5, the v2 reader and the v2 abort classifier.

Synthetic only (no Docker). Covers W4's conditions for U2:
* ABORT (default) never calls the builder from the loop; registered behaviour unchanged
  (the byte-level proof is the two registered-arm golden files).
* RECORD turns an unrepresentable child into a BuildInvalidStep: one budget unit, reward 0,
  no corpus, never produced/observed, never a seed.
* The step model's canonical JSON carries none of the new record keys.
* Reader regression: the summariser the preregistration names (``rds_report``, pinned here
  to its bed077a blob) reads a schema-5 report with build-invalid records (a) without error,
  (b) with the same vocabulary pools as without those records (an empty ``name_segments``
  list is not a missing key), (c) counting each as one execution with no violation.
* ``rds_report_v2`` reports them as their own category and reads schema-4 records.
* Comparing a schema-4 and a schema-5 report is refused (intended).
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
from pathlib import Path
from typing import Any

import pytest

import inodefence.effect_campaign as effect_campaign
from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.effect_campaign import (
    BuildInvalidPolicy,
    BuildInvalidStep,
    EffectCampaignResult,
    run_effect_campaign,
)
from inodefence.effect_demo import (
    DEMO_REPORT_SCHEMA,
    STEP_RECORD_SCHEMA,
    _require_comparable,
    effect_campaign_report,
)
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation import rds_report
from inodefence.evaluation.abort_classification import InvalidReason, classify_abort_reason
from inodefence.evaluation.abort_classification_v2 import (
    BUILD_INVALID,
    classify_abort_reason_v2,
    is_build_invalid_reason,
)
from inodefence.evaluation.rds import RdsArm, RdsCellConfig, RVariant, VocabularyMode
from inodefence.evaluation.rds_report import ReportFormatError
from inodefence.evaluation.rds_report_v2 import (
    check_report_config_v2,
    input_structure,
    mutation_chain_length,
    step_outcome,
    summarize_report_records_v2,
)
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, canonical_json
from inodefence.structure_class import class_record

# Git blob id of src/inodefence/evaluation/rds_report.py at the run SHA bed077a. The file
# is byte-identical on main (the preregistration names it), so importing the current
# module runs the E-version summariser.
RDS_REPORT_BED077A_BLOB = "e58467dcc417ff8d7639c5885a1c2e4ef3811485"

BUDGET = 40
SEED = 777
ARMS = {
    "R": (RdsArm.R, RVariant.SEED_RESTART),
    "D": (RdsArm.D, RVariant.WALK),
    "S-u": (RdsArm.S_U, RVariant.WALK),
}


def _cell(arm: str, mode: VocabularyMode = VocabularyMode.OBSERVED_NAMES) -> RdsCellConfig:
    rds_arm, variant = ARMS[arm]
    return RdsCellConfig(rds_arm, SEED, BUDGET, mode, variant)


_SEED_IDS = frozenset(case.case_id for case in minimal_seed_corpus())


def _refuses(case: ArchiveCase) -> bool:
    """Deterministic stand-in for 'the builder cannot represent this child'.

    A seed (or a no-op child equal to one) always builds, as with the real builder.
    """
    if case.case_id in _SEED_IDS:
        return False
    return int(hashlib.sha256(case.case_id.encode()).hexdigest(), 16) % 3 == 0


@pytest.fixture
def refusing_builder(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make the loop's pre-check refuse about a third of children (seeds are not checked)."""
    checked: list[str] = []

    def build(case: ArchiveCase) -> bytes:
        checked.append(case.case_id)
        if _refuses(case):
            raise ValueError("entry 0 cannot be represented in USTAR: synthetic refusal")
        return build_tar(case)

    monkeypatch.setattr(effect_campaign, "build_tar", build)
    return checked


def _record_run(
    arm: str, mode: VocabularyMode = VocabularyMode.OBSERVED_NAMES
) -> tuple[EffectCampaignResult, list[str]]:
    produced: list[str] = []

    def produce(case: ArchiveCase) -> Any:
        produced.append(case.case_id)
        return synthetic_effect_result(case)

    config = dataclasses.replace(
        _cell(arm, mode).campaign_config(), build_invalid=BuildInvalidPolicy.RECORD
    )
    return run_effect_campaign(minimal_seed_corpus(), produce, config), produced


def test_default_policy_is_abort_and_never_calls_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(case: ArchiveCase) -> bytes:
        raise AssertionError("ABORT must not pre-build")

    monkeypatch.setattr(effect_campaign, "build_tar", forbidden)
    config = _cell("D").campaign_config()
    assert config.build_invalid is None and config.build_invalid_policy == BuildInvalidPolicy.ABORT
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    assert result.build_invalid_steps == ()
    assert len(result.steps) == BUDGET


@pytest.mark.parametrize("arm", sorted(ARMS))
def test_record_policy_records_build_invalid_steps(arm: str, refusing_builder: list[str]) -> None:
    result, produced = _record_run(arm)
    invalid = result.build_invalid_steps
    assert invalid, "the refusing builder must produce build-invalid steps"
    assert len(result.steps) + len(invalid) == BUDGET
    assert sorted(s.index for s in (*result.steps, *invalid)) == list(range(BUDGET))
    seeds = len(minimal_seed_corpus())
    for step in invalid:
        assert step.index >= seeds
        assert step.scheduler_evidence.reward == 0
        assert step.case_id not in result.retained_case_ids
        assert "cannot be represented in USTAR" in step.reason
    # The producer ran exactly the executed steps, in order (never a build-invalid child).
    assert produced == [s.result.base_result.case.case_id for s in result.steps]
    # Executed children were all accepted by the pre-check.
    assert not any(_refuses(s.result.base_result.case) for s in result.steps[seeds:])


def test_record_policy_streams_build_invalid_to_observer(refusing_builder: list[str]) -> None:
    seen: list[BuildInvalidStep] = []
    config = dataclasses.replace(
        _cell("S-u").campaign_config(), build_invalid=BuildInvalidPolicy.RECORD
    )
    result = run_effect_campaign(
        minimal_seed_corpus(), synthetic_effect_result, config, on_build_invalid=seen.append
    )
    assert tuple(seen) == result.build_invalid_steps


def test_build_invalid_steps_require_record_policy(refusing_builder: list[str]) -> None:
    result, _ = _record_run("R")
    with pytest.raises(ValueError, match="RECORD"):
        dataclasses.replace(result, config=_cell("R").campaign_config())


def test_step_canonical_json_has_no_record_keys(refusing_builder: list[str]) -> None:
    result, _ = _record_run("D")
    text = canonical_json(result.steps[-1])
    assert '"schema_version":2' in text
    for key in ("step_record_schema", "build_invalid_reason", "build_invalid"):
        assert f'"{key}"' not in text


def _report(arm: str, mode: VocabularyMode = VocabularyMode.OBSERVED_NAMES) -> dict[str, Any]:
    result, _ = _record_run(arm, mode)
    return effect_campaign_report(result, "synthetic")


def test_schema5_report_records(refusing_builder: list[str]) -> None:
    report = _report("D")
    assert report["demo_report_schema"] == DEMO_REPORT_SCHEMA == 5
    assert report["config"]["build_invalid"] == "record"
    assert report["config"]["builder_format"] == BUILDER_FORMAT
    steps = report["steps"]
    assert [step["index"] for step in steps] == list(range(BUDGET))
    assert all(step["step_record_schema"] == STEP_RECORD_SCHEMA for step in steps)
    invalid = [step for step in steps if step["outcome"] == "build-invalid"]
    assert invalid
    for step in invalid:
        assert step["oracle"] == {} and step["trace"] == {}
        assert step["name_segments"] == {"before": [], "observed": []}
        assert step["validity"] == "invalid" and step["invalid_reason"] == "build_invalid"
        assert step["feedback"]["retained"] is False
        assert step["selection"]["operator_weights"]["reward"] == 0
    executed = [step for step in steps if step["outcome"] == "executed"]
    assert {step["archive_format"] for step in executed} == {"ustar"}


def test_rds_report_is_the_bed077a_version() -> None:
    data = Path(rds_report.__file__).read_bytes()
    blob = hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()  # noqa: S324
    assert blob == RDS_REPORT_BED077A_BLOB


@pytest.mark.parametrize(
    "mode", [VocabularyMode.OBSERVED_NAMES, VocabularyMode.OBSERVED_NAMES_ACCUMULATED]
)
@pytest.mark.parametrize("arm", sorted(ARMS))
def test_bed077a_summariser_reads_build_invalid_records(
    arm: str, mode: VocabularyMode, refusing_builder: list[str]
) -> None:
    report = _report(arm, mode)
    steps = report["steps"]
    cell = _cell(arm, mode)
    invalid = [step for step in steps if step["outcome"] == "build-invalid"]
    executed = [step for step in steps if step["outcome"] == "executed"]
    assert invalid

    # (a) no exception
    summary = rds_report.summarize_report_records(steps, cell).summary

    # (b) pools equal to the same report without the build-invalid records ...
    initial = len(minimal_seed_corpus())
    with_invalid = rds_report.vocabulary_pools_from_records(mode, steps, initial)
    without = rds_report.vocabulary_pools_from_records(mode, executed, initial)
    assert with_invalid == without
    assert summary.vocabulary_pool_final == without[1] != ()
    # ... and an empty list is not a missing key: dropping the key voids the pools.
    broken = copy.deepcopy(steps)
    del broken[invalid[0]["index"]]["name_segments"]
    assert rds_report.vocabulary_pools_from_records(mode, broken, initial) == ((), ())

    # (c) each build-invalid record is one execution with no violation
    assert summary.executions_completed == BUDGET and summary.complete
    hits = [
        step["index"] for step in executed if step["oracle"].get("C1") or step["oracle"].get("C2")
    ]
    assert summary.hit_steps == len(hits)
    assert summary.retained_cases == sum(1 for step in executed if step["feedback"]["retained"])
    assert summary.c0_steps == sum(1 for step in executed if step["oracle"].get("C0"))


def test_v2_reader_reports_build_invalid_as_its_own_category(refusing_builder: list[str]) -> None:
    report = _report("S-u")
    steps = report["steps"]
    cell = _cell("S-u")
    summary = summarize_report_records_v2(steps, cell)
    invalid = sum(1 for step in steps if step["outcome"] == "build-invalid")
    assert summary.build_invalid_steps == invalid > 0
    assert summary.executed_steps + summary.build_invalid_steps == BUDGET
    assert summary.base.summary.executions_completed == BUDGET
    assert summary.archive_formats == ("ustar",)
    check_report_config_v2(report, cell, build_invalid="record", builder_format=BUILDER_FORMAT)
    with pytest.raises(ReportFormatError):
        check_report_config_v2(report, cell, build_invalid="abort", builder_format=BUILDER_FORMAT)
    # A report without the v2 key (e.g. schema 4, or a launcher that omits it) is refused.
    missing = copy.deepcopy(report)
    del missing["config"]["build_invalid"]
    with pytest.raises(ReportFormatError, match="build_invalid"):
        check_report_config_v2(missing, cell, build_invalid="record", builder_format=BUILDER_FORMAT)


def test_v2_reader_reads_schema4_records() -> None:
    cell = _cell("D")
    result = run_effect_campaign(
        minimal_seed_corpus(), synthetic_effect_result, cell.campaign_config()
    )
    report: dict[str, Any] = effect_campaign_report(result, "synthetic")
    steps: list[dict[str, Any]] = report["steps"]
    for step in steps:
        for key in ("step_record_schema", "archive_format", "outcome"):
            del step[key]
    summary = summarize_report_records_v2(steps, cell)
    assert summary.build_invalid_steps == 0 and summary.executed_steps == BUDGET
    assert summary.archive_formats is None  # unverifiable, never assumed
    assert step_outcome(steps[0]) == "executed"


def test_v2_reader_refuses_unknown_outcome_and_verdict_on_build_invalid(
    refusing_builder: list[str],
) -> None:
    steps = _report("R")["steps"]
    cell = _cell("R")
    bad = copy.deepcopy(steps)
    bad[-1]["outcome"] = "skipped"
    with pytest.raises(ReportFormatError, match="unknown outcome"):
        summarize_report_records_v2(bad, cell)
    bad = copy.deepcopy(steps)
    index = next(step["index"] for step in bad if step["outcome"] == "build-invalid")
    bad[index]["oracle"] = {"C0": True}
    with pytest.raises(ReportFormatError, match="verdict"):
        summarize_report_records_v2(bad, cell)


def test_schema4_and_schema5_reports_are_not_compared(refusing_builder: list[str]) -> None:
    report = _report("D")
    older = copy.deepcopy(report)
    older["demo_report_schema"] = 4
    with pytest.raises(ValueError, match="demo_report_schema"):
        _require_comparable(report, older)


def _long_link_case() -> ArchiveCase:
    return ArchiveCase(
        (ArchiveEntry("a", EntryType.SYMLINK, link_target="x/" * 60),),
    )


def test_v2_classifier_names_builder_refusals() -> None:
    with pytest.raises(ValueError) as caught:
        build_tar(_long_link_case())
    reason = f"builtins.ValueError: {caught.value}"
    assert is_build_invalid_reason(reason)
    assert classify_abort_reason_v2(reason) == BUILD_INVALID
    assert classify_abort_reason_v2("x USTAR name/prefix split would change the raw path") == (
        BUILD_INVALID
    )
    # The registered classifier is unchanged: still "other".
    assert classify_abort_reason(reason) == InvalidReason.OTHER
    assert BUILD_INVALID not in {item.value for item in InvalidReason}
    # Everything else delegates.
    assert classify_abort_reason_v2("trusted Docker broker disconnected") == "broker"
    assert classify_abort_reason_v2("") == "other"


def test_reserved_chain_slots_read_as_not_recorded_and_structure_is_recorded() -> None:
    cell = _cell("D")
    result = run_effect_campaign(
        minimal_seed_corpus(), synthetic_effect_result, cell.campaign_config()
    )
    report: dict[str, Any] = effect_campaign_report(result, "synthetic")
    steps: list[dict[str, Any]] = report["steps"]
    seeds = len(minimal_seed_corpus())
    assert [mutation_chain_length(step) for step in steps[:seeds]] == [None] * seeds
    assert {mutation_chain_length(step) for step in steps[seeds:]} == {1}
    # U2 reserved the slot (asserted absent); v2 U3/C8 fills it on every step. Replaced here by
    # agreement (IF-H4-CORE, 2026-11-18): the slot is recorded and the reader reads it.
    cases = [step.result.base_result.case for step in result.steps]
    assert [input_structure(step) for step in steps] == [class_record(case) for case in cases]
    assert (
        input_structure({}) is None
    )  # an older record without the key still reads as not recorded
    for step in steps[seeds:]:
        assert "chain_length" not in step["mutation_attempt"]
        assert "operator_chain" not in step["mutation_attempt"]
    chained = copy.deepcopy(steps[seeds])
    chained["mutation_attempt"]["chain_length"] = 2
    chained["mutation_attempt"]["operator_chain"] = [
        {"operator_id": "a", "applied": True, "selected_weight": 1},
        {"operator_id": "b", "applied": False, "selected_weight": 1},
    ]
    assert mutation_chain_length(chained) == 2
    chained["mutation_attempt"]["chain_length"] = 3
    with pytest.raises(ReportFormatError, match="disagree"):
        mutation_chain_length(chained)
    assert input_structure({"input_structure": {"class": "x"}}) == {"class": "x"}
