"""Producer-independent demo report for one effect campaign (P0-5).

The report is derived only from an EffectCampaignResult, so the same function
serves the synthetic entrypoint and a later in-controller native run. It holds
no timestamps or host paths: identical campaigns render byte-identical JSON.
"""

import json

from inodefence.effect_campaign import EffectCampaignResult, EffectCampaignStep
from inodefence.model import canonical_json
from inodefence.mutation_scheduler import WeightSnapshot

DEMO_REPORT_SCHEMA = 1


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
