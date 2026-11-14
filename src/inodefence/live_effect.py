"""Adapter: one step of the effect loop (``run_effect_campaign``, node-tar) -> a neutral LiveStep.

The verdict mapping is the one ``scripts/run_effect_demo.exploration_demo_report`` uses for its
``case_records``: a step whose target run did not succeed has no verdicts (``None``), otherwise
each contract's value is the oracle's ``violated`` flag for it. Using the same rule keeps the live
violation records consistent with the final ``result.json`` built from that report. The input TAR
is rebuilt with :func:`inodefence.builder.build_tar` only for violating steps, as the report does.

"Un-judged" uses the same rule as the result file (so the live count equals the
``unjudged_steps`` a campaign verdict is recomputed from): the target run succeeded but the oracle
gave no verdict on any contract (C0, C1 and C2 all ``None``). A run that did not succeed is an
error/timeout/rejection, never "un-judged". In the node-tar loop this coincides with the loop's
``observation_failure`` signal (an observation failure leaves every contract unjudged).
"""

from __future__ import annotations

from typing import Any

from inodefence.builder import build_tar
from inodefence.feedback.fingerprint import ViolationFingerprint, violation_fingerprints
from inodefence.live_exploration import LiveStep, fingerprint_id
from inodefence.model.results import ExecutionStatus


def effect_fingerprint_id(fingerprint: ViolationFingerprint) -> str:
    """Stable short id of one violation class (contract + its canonical evidence)."""
    return fingerprint_id(fingerprint.contract_id.value, repr(fingerprint.evidence))


def live_step_from_effect(step: Any) -> LiveStep:
    """Convert an ``EffectCampaignStep`` (attributes only) into a :class:`LiveStep`."""
    base = step.result.base_result
    status = ExecutionStatus(base.execution.status)
    contracts: dict[str, bool | None] = {"C0": None, "C1": None, "C2": None}
    fingerprints: tuple[str, ...] = ()
    observation: tuple[str, ...] = ()
    if status is ExecutionStatus.SUCCESS:
        for verdict in base.violations:
            contracts[verdict.contract_id.value] = verdict.violated
        fingerprints = tuple(
            effect_fingerprint_id(fp) for fp in violation_fingerprints(tuple(base.violations))
        )
        observation = tuple(
            f"{v.contract_id.value}: {v.explanation}" for v in base.violations if v.violated
        )
    violated = any(value is True for value in contracts.values())
    attempt = step.mutation_attempt
    return LiveStep(
        index=step.index,
        case_id=base.case.case_id,
        status=status.value,
        c0=contracts["C0"],
        c1=contracts["C1"],
        c2=contracts["C2"],
        unjudged=status is ExecutionStatus.SUCCESS
        and all(value is None for value in contracts.values()),
        parent_case_id=step.parent_case_id,
        origin=str(getattr(step.origin, "value", step.origin)),
        mutation=None if attempt is None else attempt.operator_id.value,
        mutation_applied=None if attempt is None else bool(attempt.applied),
        fingerprints=fingerprints,
        new_fingerprints=tuple(
            effect_fingerprint_id(fp) for fp in step.feedback.new_violation_fingerprints
        ),
        tar_bytes=build_tar(base.case) if violated else None,
        observation=observation,
    )
