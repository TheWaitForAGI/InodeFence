"""v2 reader of controller-path demo reports: build-invalid steps as their own category.

``rds_report`` is the implementation the preregistration names; it stays byte-identical
on ``main`` (W4 rule: a file the preregistration points at is never edited, v2 reads
through a new module). It already reads report schema 5 without change: a build-invalid
record carries empty ``oracle``/``feedback``/``trace`` mappings and empty
``name_segments`` lists, so it counts there as one execution with no violation and
leaves the vocabulary pool as it was.

This module wraps it for v2 analysis:

* :func:`summarize_report_records_v2` -- the same per-cell summary over every record
  (a build-invalid step spends one budget unit, so it stays in the ``t_first``
  denominator), plus the build-invalid steps as their own count rather than folded
  into "no violation", and the archive formats the executed steps recorded.
* :func:`check_report_config_v2` -- ``rds_report.check_report_config`` plus the v2
  config keys (``build_invalid``, ``builder_format``).

Schema-4 records (no ``outcome``) read as executed steps; a record without
``archive_format`` makes the format set unverifiable, never assumed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from inodefence.evaluation.rds import FIXED_BASELINE_MODES, RdsCellConfig, VocabularyMode
from inodefence.evaluation.rds_report import (
    ReportFormatError,
    ReportSummary,
    check_report_config,
    summarize_report_records,
    vocabulary_pools_from_records,
)
from inodefence.mutator.policy import RECORDS_BUILD_INVALID, MutationPolicy

OUTCOME_EXECUTED = "executed"
OUTCOME_BUILD_INVALID = "build-invalid"
_OUTCOMES = (OUTCOME_EXECUTED, OUTCOME_BUILD_INVALID)


def step_outcome(record: Mapping[str, Any]) -> str:
    """``executed`` or ``build-invalid``; a record without ``outcome`` (schema 4) executed."""
    outcome = record.get("outcome", OUTCOME_EXECUTED)
    if outcome not in _OUTCOMES:
        raise ReportFormatError(f"step {record.get('index')} has unknown outcome {outcome!r}")
    return outcome


@dataclass(frozen=True, slots=True)
class ReportSummaryV2:
    """``rds_report`` summary plus the v2 categories it cannot express.

    ``base`` counts every record, so ``executions_completed`` includes build-invalid
    steps (one budget unit each) and they can never be hits. ``executed_steps`` +
    ``build_invalid_steps`` = ``base.summary.executions_completed``.
    ``archive_formats`` is the sorted set the executed records state, or ``None`` when
    any executed record does not state one (unverifiable, e.g. schema 4).
    """

    base: ReportSummary
    executed_steps: int
    build_invalid_steps: int
    archive_formats: tuple[str, ...] | None


def vocabulary_pools_from_records_v2(
    mode: VocabularyMode, records: Sequence[Mapping[str, Any]], initial_count: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``rds_report.vocabulary_pools_from_records`` that also knows the v2 modes.

    The preregistration-named reader treats any mode it does not list as accumulated;
    a v2 fixed-baseline mode is read here as fixed (step-0 BEFORE names), exactly like
    ``OBSERVED_NAMES``.
    """
    if mode in FIXED_BASELINE_MODES:
        mode = VocabularyMode.OBSERVED_NAMES
    return vocabulary_pools_from_records(mode, records, initial_count)


def mutation_chain_length(record: Mapping[str, Any]) -> int | None:
    """Operations applied to make this step's input; ``None`` for a seed.

    Reserved in schema 5 for the v2 random-chain R policy (implemented in U3):
    ``mutation_attempt.chain_length`` (m) and ``mutation_attempt.operator_chain``
    (m items ``{operator_id, applied, selected_weight}`` in application order) appear only
    under a chain policy. Without them the attempt is one operation (every existing and
    registered policy), so this returns 1.
    """
    attempt = record.get("mutation_attempt")
    if attempt is None:
        return None
    if not isinstance(attempt, Mapping):
        raise ReportFormatError(f"step {record.get('index')} mutation_attempt is not a mapping")
    if "chain_length" not in attempt and "operator_chain" not in attempt:
        return 1
    length, chain = attempt.get("chain_length"), attempt.get("operator_chain")
    if type(length) is not int or length < 1 or not isinstance(chain, list) or len(chain) != length:
        raise ReportFormatError(
            f"step {record.get('index')} chain_length and operator_chain disagree"
        )
    return length


def input_structure(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The step's static input-structure class, or ``None`` when not recorded.

    Reserved in schema 5 (``input_structure``, one object per step, separate from the
    verdict); the classifier and its values come in U3. A missing key means "not
    recorded", never "no structure".
    """
    value = record.get("input_structure")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ReportFormatError(f"step {record.get('index')} input_structure is not a mapping")
    return value


def summarize_report_records_v2(
    records: Sequence[Mapping[str, Any]],
    config: RdsCellConfig,
    *,
    aborted_at_step: int | None = None,
    abort_reason: str | None = None,
    sentinel_set: Mapping[str, object] | None = None,
) -> ReportSummaryV2:
    steps = tuple(records)
    outcomes = [step_outcome(step) for step in steps]
    for step, outcome in zip(steps, outcomes, strict=True):
        if outcome == OUTCOME_BUILD_INVALID and (
            step.get("oracle") or step.get("oracle_fingerprints") or step.get("origin") == "seed"
        ):
            raise ReportFormatError(
                f"build-invalid step {step.get('index')} carries a verdict or is a seed"
            )
    base = summarize_report_records(
        steps,
        config,
        aborted_at_step=aborted_at_step,
        abort_reason=abort_reason,
        sentinel_set=sentinel_set,
    )
    executed = [
        step for step, outcome in zip(steps, outcomes, strict=True) if outcome == OUTCOME_EXECUTED
    ]
    formats = [step.get("archive_format") for step in executed]
    archive_formats = (
        tuple(sorted({str(item) for item in formats}))
        if all(isinstance(item, str) and item for item in formats)
        else None
    )
    return ReportSummaryV2(
        base,
        len(executed),
        len(steps) - len(executed),
        archive_formats,
    )


def check_records_policy_v2(
    records: Sequence[Mapping[str, Any]], *, mutation_policy: MutationPolicy
) -> None:
    """Build settings of a report without ``config`` (the shared launcher's stream report).

    The shared launcher cannot override ``build_invalid``; it follows the mutation policy's
    profile. So the records prove the setting: every mutation record carries the planned v2
    policy id, that id is in ``RECORDS_BUILD_INVALID``, and every record has
    ``step_record_schema`` (schema 5). Refuses otherwise.
    """
    if mutation_policy not in RECORDS_BUILD_INVALID:
        raise ReportFormatError(f"{mutation_policy.value} does not record build-invalid steps")
    steps = tuple(records)
    if not steps:
        raise ReportFormatError("no step records to check")
    missing = [step.get("index") for step in steps if "step_record_schema" not in step]
    if missing:
        raise ReportFormatError(f"step records without step_record_schema: {missing[:5]}")
    policies = {
        step["mutation_attempt"].get("mutation_policy")
        for step in steps
        if isinstance(step.get("mutation_attempt"), Mapping)
    }
    if policies != {mutation_policy.value}:
        raise ReportFormatError(
            f"mutation records carry {sorted(map(str, policies))}, planned {mutation_policy.value}"
        )


def check_report_config_v2(
    report: Mapping[str, Any],
    config: RdsCellConfig,
    *,
    build_invalid: str,
    builder_format: str,
) -> None:
    """Refuse a report that is not the planned cell or not the planned v2 build settings.

    A report without the v2 keys (schema 4) is refused: v2 analysis does not assume them.
    """
    check_report_config(report, config)
    recorded = report.get("config")
    if not isinstance(recorded, Mapping):
        raise ReportFormatError("report has no config to check")
    expected = {"build_invalid": build_invalid, "builder_format": builder_format}
    differences = {
        key: (recorded.get(key), value)
        for key, value in expected.items()
        if recorded.get(key) != value
    }
    if differences:
        raise ReportFormatError(f"report v2 config differs from the planned cell: {differences}")
