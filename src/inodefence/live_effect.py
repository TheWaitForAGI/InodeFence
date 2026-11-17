"""Adapter: one step of the effect loop (``run_effect_campaign``, node-tar) -> a neutral LiveStep.

The verdict mapping follows the result-format outcome contract (``target_result``): every run
the oracle observed keeps its C0/C1/C2 verdicts whatever the exit status -- the oracle judges the
before/after snapshots, so a rejection, crash or timeout is judged, and a violation during one is
still a violation. The input TAR is rebuilt with :func:`inodefence.builder.build_tar` only for
violating steps, as the report does.

"Un-judged" follows ``CaseVerdict.is_unjudged``: the oracle was not evaluated, so C0, C1 and C2
are all ``None``. That keeps the live count equal to the ``unjudged_steps`` a campaign verdict is
recomputed from. ``observation_complete`` is ``trace.integrity_valid`` (stream complete, no
observation failure, fully flushed) -- the same definition the node-tar producer writes to the
result. A violation with an incomplete observation or a non-success end is marked
"reproduction check needed" (still a violation).
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


def effect_verdict_fields(result: Any) -> dict[str, Any]:
    """The judgment + termination fields of one ``EffectRunResult`` (attributes only).

    The single mapping shared by live recording and case replay, so the two can never disagree:
    the oracle judges the before/after snapshots whatever the exit status (a rejection, crash or
    timeout keeps its verdicts); ``observation_complete`` is ``trace.integrity_valid``.
    """
    base = result.base_result
    status = ExecutionStatus(base.execution.status)
    contracts: dict[str, bool | None] = {"C0": None, "C1": None, "C2": None}
    for verdict in base.violations:
        contracts[verdict.contract_id.value] = verdict.violated
    return {
        "termination": status.value,
        "c0": contracts["C0"],
        "c1": contracts["C1"],
        "c2": contracts["C2"],
        "fingerprints": tuple(
            effect_fingerprint_id(fp) for fp in violation_fingerprints(tuple(base.violations))
        ),
        "observation": tuple(
            f"{v.contract_id.value}: {v.explanation}" for v in base.violations if v.violated
        ),
        "observation_complete": bool(result.trace.integrity_valid),
    }


def exploration_unobserved(status: str, integrity_valid: bool, contracts: tuple) -> bool:
    """Exploration only (user decision D1, 2026-11-16): is this run NOT a judged clean negative?

    The ONE rule the node-tar exploration result record and its live progress both use, so they
    cannot disagree. A run in which the oracle saw a violation is always judged (the effect is on
    disk; it is kept, shown as "reproduction check needed"). Otherwise the run is unjudged when the
    extractor ``failed`` or ``timed_out`` (no reason to trust the post-state as a clean outcome),
    or when it reports ``success`` but its trace is not intact. A ``rejected`` run -- an explicit,
    normal refusal -- stays judged. Registered experiments never call this (they do not record
    exploration results); the loop and its feedback receive the unchanged ``EffectRunResult``.
    """
    if any(value is True for value in contracts):
        return False
    if status in (ExecutionStatus.FAILED.value, ExecutionStatus.TIMED_OUT.value):
        return True
    return status == ExecutionStatus.SUCCESS.value and not integrity_valid


def live_step_from_effect(step: Any) -> LiveStep:
    """Convert an ``EffectCampaignStep`` (attributes only) into a :class:`LiveStep`."""
    base = step.result.base_result
    fields = effect_verdict_fields(step.result)
    contracts = (fields["c0"], fields["c1"], fields["c2"])
    if exploration_unobserved(fields["termination"], fields["observation_complete"], contracts):
        contracts = (None, None, None)  # same as the result record: unjudged, no clean verdict
    violated = any(value is True for value in contracts)
    attempt = step.mutation_attempt
    return LiveStep(
        index=step.index,
        case_id=base.case.case_id,
        status=fields["termination"],
        c0=contracts[0],
        c1=contracts[1],
        c2=contracts[2],
        unjudged=all(value is None for value in contracts),
        parent_case_id=step.parent_case_id,
        origin=str(getattr(step.origin, "value", step.origin)),
        mutation=None if attempt is None else attempt.operator_id.value,
        mutation_applied=None if attempt is None else bool(attempt.applied),
        fingerprints=fields["fingerprints"],
        new_fingerprints=tuple(
            effect_fingerprint_id(fp) for fp in step.feedback.new_violation_fingerprints
        ),
        tar_bytes=build_tar(base.case) if violated else None,
        observation=fields["observation"],
        observation_complete=fields["observation_complete"],
    )
