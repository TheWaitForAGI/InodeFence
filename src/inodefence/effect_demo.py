"""Producer-independent demo report for one effect campaign (P0-5).

The report is derived only from an EffectCampaignResult, so the same function
serves the synthetic entrypoint and a later in-controller native run. It holds
no timestamps or host paths: identical campaigns render byte-identical JSON.
"""

import json
from collections.abc import Mapping
from typing import Any

from inodefence.effect_campaign import EffectCampaignResult, EffectCampaignStep
from inodefence.effect_synthetic import SYNTHETIC_MECHANISM
from inodefence.model import (
    EffectObjectObservation,
    EffectObservationStatus,
    EffectRunResult,
    canonical_json,
)
from inodefence.mutation_scheduler import WeightSnapshot

DEMO_REPORT_SCHEMA = 1
POLICY_COMPARISON_SCHEMA = 1


def _model(value: object) -> object:
    return json.loads(canonical_json(value))


def _weights(weights: WeightSnapshot) -> dict[str, int]:
    return {operator.value: weight for operator, weight in weights}


def _step_report(step: EffectCampaignStep) -> dict[str, object]:
    base = step.result.base_result
    feedback = step.feedback
    attempt = step.mutation_attempt
    evidence = step.scheduler_evidence
    return {
        "index": step.index,
        "origin": step.origin.value,
        "case_id": base.case.case_id,
        "parent_case_id": step.parent_case_id,
        "oracle": {verdict.contract_id.value: verdict.violated for verdict in base.violations},
        "feedback": {
            "new_effect_keys": [_model(key) for key in feedback.new_effect_keys],
            "new_violation_fingerprints": [
                _model(item) for item in feedback.new_violation_fingerprints
            ],
            "effect_novel": feedback.effect_novel,
            "full_state_novel": feedback.full_state_novel,
            "contract_violated": feedback.contract_violated,
            "feedback_eligible": feedback.feedback_eligible,
            "admission_eligible": feedback.admission_eligible,
            "retained": feedback.retained,
            "trace_completeness": feedback.trace_completeness.value,
            "trace_termination": feedback.trace_termination.value,
        },
        "mutation_attempt": None
        if attempt is None
        else {
            "operator_id": attempt.operator_id.value,
            "mutation_policy": attempt.mutation_policy.value,
            "applied": attempt.applied,
        },
        "scheduler_evidence": None
        if evidence is None
        else {
            "selected_operator_id": evidence.selected_operator_id.value,
            "weights_before": _weights(evidence.weights_before),
            "selected_weight": evidence.selected_weight,
            "reward": evidence.reward,
            "weights_after": _weights(evidence.weights_after),
        },
    }


def effect_campaign_report(result: EffectCampaignResult, producer: str) -> dict[str, object]:
    """Summarize each loop step: oracle, feedback keys, chosen operator and why.

    `producer` labels where EffectRunResults came from (e.g. "synthetic"); the
    report never upgrades synthetic results to native evidence.
    """
    if not isinstance(producer, str) or not producer:
        raise ValueError("demo report requires a producer label")
    config = result.config
    return {
        "demo_report_schema": DEMO_REPORT_SCHEMA,
        "producer": producer,
        "mutation_policy": config.mutation_policy.value,
        "config": {
            "random_seed": config.random_seed,
            "execution_budget": config.execution_budget,
            "search_policy": config.search_policy.value,
            "mutation_policy": config.mutation_policy.value,
        },
        "initial_case_ids": list(result.initial_case_ids),
        "steps": [_step_report(step) for step in result.steps],
        "final_search_stats": _model(result.final_search_stats),
        "retained_case_ids": list(result.retained_case_ids),
    }


def render_effect_campaign_report(report: dict[str, object]) -> str:
    """Stable text encoding used for byte-identical reproduction checks."""
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


# Conditions that must match for two demo reports to differ only by search policy.
_SHARED_CONFIG = ("random_seed", "execution_budget", "mutation_policy")


def _require_comparable(left: Mapping[str, Any], right: Mapping[str, Any]) -> None:
    for field in ("demo_report_schema", "producer", "initial_case_ids"):
        if left[field] != right[field]:
            raise ValueError(f"reports differ in {field}; only search_policy may differ")
    for field in _SHARED_CONFIG:
        if left["config"][field] != right["config"][field]:
            raise ValueError(f"reports differ in config.{field}; only search_policy may differ")
    if len(left["steps"]) != len(right["steps"]):
        raise ValueError("reports differ in step count")


def _corpus_before_steps(report: Mapping[str, Any]) -> list[list[str]]:
    """Retained case IDs before each step, rebuilt from the recorded `retained` flags."""
    corpus: list[str] = []
    before: list[list[str]] = []
    for step in report["steps"]:
        before.append(list(corpus))
        if step["feedback"]["retained"]:
            corpus.append(step["case_id"])
    return before


def _selection(step: Mapping[str, Any], corpus_before: list[str]) -> dict[str, object]:
    evidence = step["scheduler_evidence"]
    return {
        "index": step["index"],
        "corpus_size_before": len(corpus_before),
        "parent_case_id": step["parent_case_id"],
        "selected_operator_id": evidence["selected_operator_id"],
        "case_id": step["case_id"],
        "weights_before": evidence["weights_before"],
        "selected_weight": evidence["selected_weight"],
        "new_effect_keys": step["feedback"]["new_effect_keys"],
        "reward": evidence["reward"],
        "weights_after": evidence["weights_after"],
    }


def _feedback_events(report: Mapping[str, Any]) -> list[dict[str, object]]:
    """Mutation steps that produced new effect keys, and what the scheduler did with them."""
    events: list[dict[str, object]] = []
    for step in report["steps"]:
        evidence = step["scheduler_evidence"]
        if evidence is None or not step["feedback"]["new_effect_keys"]:
            continue
        operator = evidence["selected_operator_id"]
        events.append(
            {
                "index": step["index"],
                "selected_operator_id": operator,
                "new_effect_key_count": len(step["feedback"]["new_effect_keys"]),
                "reward": evidence["reward"],
                "selected_weight_before": evidence["weights_before"][operator],
                "selected_weight_after": evidence["weights_after"][operator],
            }
        )
    return events


def _divergence_source(corpus_step: int | None, weights_step: int | None) -> str:
    """Upstream difference that existed at or before the first divergent step.

    weights_feedback: corpora were identical, so only scheduler weights differed.
    corpus_admission: weights were identical, so the parent pool (and the RNG draws
    over it) differed. Both differing at once cannot be separated.
    """
    if corpus_step is None and weights_step is None:
        return "unexplained"
    if corpus_step is None:
        return "weights_feedback"
    if weights_step is None:
        return "corpus_admission"
    return "corpus_admission_and_weights_feedback"


def _immediate_difference(left: Mapping[str, Any], right: Mapping[str, Any]) -> str:
    """Which recorded input of the divergent step itself differed."""
    if left["parent_case_id"] != right["parent_case_id"]:
        return "parent"
    if left["weights_before"] != right["weights_before"]:
        return "weights"
    # Same parent and weights, different operator/child: the shared RNG was already shifted.
    return "rng_desync"


def compare_effect_campaign_reports(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> dict[str, object]:
    """Align two demo reports by step and locate where mutation selection first diverges.

    Both reports must share producer, seed, budget, mutation policy and initial
    cases, so the search policy is the only configured difference. A selection is
    (parent, operator, child); steps are compared by index, so match ratios after
    the first divergence compare unrelated lineages. The corpus/weights difference
    steps name the first mutation step whose parent pool (retained cases so far) or
    weights_before differed.
    """
    _require_comparable(left, right)
    left_corpus = _corpus_before_steps(left)
    right_corpus = _corpus_before_steps(right)
    mutation_steps = operator_matches = selection_matches = 0
    corpus_step: int | None = None
    weights_step: int | None = None
    operator_step: int | None = None
    divergence: dict[str, object] | None = None
    for position, (left_step, right_step) in enumerate(
        zip(left["steps"], right["steps"], strict=True)
    ):
        if (left_step["scheduler_evidence"] is None) != (right_step["scheduler_evidence"] is None):
            raise ValueError(f"step {position} is a seed step in only one report")
        if left_step["scheduler_evidence"] is None:
            if left_step["case_id"] != right_step["case_id"]:
                raise ValueError(f"seed step {position} differs between reports")
            continue
        mutation_steps += 1
        left_selection = _selection(left_step, left_corpus[position])
        right_selection = _selection(right_step, right_corpus[position])
        if corpus_step is None and left_corpus[position] != right_corpus[position]:
            corpus_step = position
        if weights_step is None and (
            left_selection["weights_before"] != right_selection["weights_before"]
        ):
            weights_step = position
        same_operator = (
            left_selection["selected_operator_id"] == right_selection["selected_operator_id"]
        )
        same_selection = same_operator and all(
            left_selection[field] == right_selection[field]
            for field in ("parent_case_id", "case_id")
        )
        operator_matches += same_operator
        selection_matches += same_selection
        if operator_step is None and not same_operator:
            operator_step = position
        if divergence is None and not same_selection:
            divergence = {
                "step": position,
                "immediate_difference": _immediate_difference(left_selection, right_selection),
                "source": _divergence_source(corpus_step, weights_step),
                "first_corpus_difference_step": corpus_step,
                "first_weights_difference_step": weights_step,
                "left": left_selection,
                "right": right_selection,
            }
    return {
        "policy_comparison_schema": POLICY_COMPARISON_SCHEMA,
        "producer": left["producer"],
        "shared_config": {field: left["config"][field] for field in _SHARED_CONFIG},
        "left_policy": left["config"]["search_policy"],
        "right_policy": right["config"]["search_policy"],
        "seed_steps": len(left["steps"]) - mutation_steps,
        "mutation_steps": mutation_steps,
        "operator_match_steps": operator_matches,
        "selection_match_steps": selection_matches,
        "operator_match_ratio": _ratio(operator_matches, mutation_steps),
        "selection_match_ratio": _ratio(selection_matches, mutation_steps),
        "first_divergence": divergence,
        "first_operator_divergence_step": operator_step,
        "first_corpus_difference_step": corpus_step,
        "first_weights_difference_step": weights_step,
        "operator_sequences": {
            "left": _operator_sequence(left),
            "right": _operator_sequence(right),
        },
        "feedback_events": {"left": _feedback_events(left), "right": _feedback_events(right)},
    }


def _ratio(matches: int, total: int) -> float | None:
    return None if total == 0 else round(matches / total, 4)


def _operator_sequence(report: Mapping[str, Any]) -> list[str | None]:
    return [
        None
        if step["scheduler_evidence"] is None
        else step["scheduler_evidence"]["selected_operator_id"]
        for step in report["steps"]
    ]


# Value-origin labels; each maps to an existing model field, none is a new evidence kind.
TRACE_LEGEND = (
    ("archive", "TAR가 선언한 값(ArchiveEntryReference). 파일시스템 관찰 아님."),
    (
        "observed",
        "evidence source가 실행 중 기록한 값: operation·outcome, 작업 전/후 lstat 결과 "
        "(EffectObservationStatus present/absent, present일 때 dev:ino).",
    ),
    ("not_observed", "source가 그 시점 lstat을 기록하지 못함(status not_observed). 값 없음."),
    (
        "derived",
        "InodeFence가 observed 값에서 분류한 effect_class. evidence_strength 원문 병기; "
        "operation_result는 상태 변화가 확인되지 않았다는 뜻.",
    ),
)


def _observation_text(phase: str, observation: EffectObjectObservation) -> str:
    if observation.status == EffectObservationStatus.NOT_OBSERVED:
        return f"{phase} [not_observed]"
    if observation.object is None:
        return f"{phase} [observed] absent"
    obj = observation.object
    return f"{phase} [observed] present {obj.object_type.value} dev:ino {obj.st_dev}:{obj.st_ino}"


def render_effect_trace(result: EffectRunResult) -> str:
    """Human-readable entry-order trace with each value's origin label.

    Only fields already in EffectRunResult are printed; the label states where a
    value came from (TAR, source observation, or InodeFence classification).
    Synthetic traces get a header saying their values are not observations.
    """
    if not isinstance(result, EffectRunResult):
        raise ValueError("trace rendering requires an EffectRunResult")
    trace = result.trace
    execution = result.base_result.execution
    sources = trace.provenance.sources
    lines = []
    if any(source.mechanism == SYNTHETIC_MECHANISM for source in sources):
        lines.append(
            "SYNTHETIC — 관찰값 아님: synthetic producer가 만든 값이며 node-tar 실행 증거가 아니다"
        )
    lines.append(
        f"extractor: {execution.target_id} {execution.target_version} "
        f"| status {execution.status.value} | completeness {trace.completeness.value} "
        f"| termination {trace.termination.value}"
    )
    lines.append(
        "sources: " + ", ".join(f"{s.source_id} ({s.mechanism} {s.version})" for s in sources)
    )
    failures = trace.observation_failures
    lines.append(
        "observation_failures: "
        + (", ".join(f"{f.kind.value}: {f.message}" for f in failures) if failures else "none")
    )
    lines.append("legend:")
    lines.extend(f"  [{label}] {meaning}" for label, meaning in TRACE_LEGEND)
    for entry in trace.archive_entries:
        link = f" link={entry.link_target}" if entry.link_target is not None else ""
        lines.append(
            f"entry {entry.entry_index} [archive] path={entry.path} "
            f"type={entry.entry_type.value}{link}"
        )
        events = sorted(
            (event for event in trace.effect_events if event.entry == entry),
            key=lambda event: event.start_sequence,
        )
        if not events:
            lines.append("  (no effect event recorded)")
        for event in events:
            lines.append(
                f"  effect seq {event.start_sequence}-{event.completion_sequence} "
                f"[observed] op={event.operation.value} outcome={event.outcome.value}"
            )
            lines.append(
                f"    [derived] class={event.effect_class.value} "
                f"strength={event.evidence_strength.value}"
            )
            evidence = {item.path: item for item in event.object_evidence}
            for path in event.affected_paths:
                item = evidence.get(path)
                if item is None:
                    lines.append(f"    path {path} [not_observed] no object evidence")
                    continue
                lines.append(
                    f"    path {path} {_observation_text('before', item.before)} "
                    f"-> {_observation_text('after', item.after)}"
                )
    return "\n".join(lines) + "\n"
