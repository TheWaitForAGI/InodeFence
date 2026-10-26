"""M3: boundary-approach *attempt* feedback (P3 arm), additive over P0/P1/P2.

The key is derived from an observed link operation whose observed target path lies
outside the extraction root (target-agnostic: trigger kind, target region, outcome
and a bounded escape shape — no path, sentinel, tail or CVE). Its one relaxation is
that the opt-in P3 arm derives it from a cleanly recorded *rejected* trace, not only
a successful one. P0/P1/P2 and the benign synthetic loop stay unchanged; the latter
is pinned by the demo sha256 in `make check`.
"""

import pytest

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_synthetic import (
    _edge,
    _lifecycle,
    _observation,
    _provenance,
    _result,
    _snapshots,
    synthetic_effect_result,
)
from inodefence.feedback import (
    EffectSearchPolicy,
    EffectSearchState,
    boundary_attempt_keys,
)
from inodefence.feedback.effect import _escape_shape
from inodefence.feedback.signature import state_signature
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ArchiveEntryReference,
    AssociationKind,
    BoundaryAttemptShape,
    BoundaryAttemptSignature,
    CausalRelationKind,
    EffectClass,
    EffectEventTrace,
    EffectEvidenceStrength,
    EffectFeedbackKeyKind,
    EffectPathEvidence,
    EffectRunResult,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EntryLifecycleKind,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    FilesystemEffectEvent,
    MonotonicInterval,
    ObservedOperationType,
    OperationOutcome,
    RawEvidenceReference,
    Region,
    RunResult,
)
from inodefence.mutator import MutationPolicy
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts

HARDLINK_CASE = ArchiveCase((ArchiveEntry("link", EntryType.HARDLINK, link_target="a.txt"),))


def _external_link_attempt_result(
    *,
    link_target: str,
    outcome: OperationOutcome,
    target_path: str = "outside/sentinel",
    termination: ExecutionStatus = ExecutionStatus.REJECTED,
) -> EffectRunResult:
    """Build one clean trace whose single link op targets outside the extraction root.

    Mirrors what the native producer/reader yield for an escaping hardlink the target
    attempted but did not realize: a LINK operation (downgraded to OPERATION_OBSERVED)
    with a non-success outcome and an external target path, in a COMPLETE trace whose
    termination matches `termination` (REJECTED by default).
    """
    entry = ArchiveEntry("link", EntryType.HARDLINK, link_target=link_target)
    case = ArchiveCase((entry,))
    reference = ArchiveEntryReference(0, entry.path, entry.entry_type, entry.link_target)
    link_path = "extract/object-0"
    before, after = _snapshots()
    read, work, start, completion = 0, 1, 2, 3
    lifecycle = (
        _lifecycle(read, reference, EntryLifecycleKind.READ),
        _lifecycle(work, reference, EntryLifecycleKind.EFFECT_WORK_STARTED),
    )
    event = FilesystemEffectEvent(
        start,
        completion,
        reference,
        AssociationKind.ASYNC_CONTEXT,
        EffectClass.OPERATION_OBSERVED,
        EffectEvidenceStrength.OPERATION_RESULT,
        (target_path, link_path),
        ObservedOperationType.LINK,
        MonotonicInterval(start * 10, start * 10 + 1),
        MonotonicInterval(completion * 10, completion * 10 + 1),
        outcome,
        (
            EffectPathEvidence(target_path, _observation(None), _observation(None)),
            EffectPathEvidence(link_path, _observation(None), _observation(None)),
        ),
        "synthetic",
        f"operation-{start}",
        RawEvidenceReference("synthetic", f"effect-{completion}"),
    )
    edges = (
        _edge(work, start, CausalRelationKind.ENTRY_CONTEXT_PROPAGATION, "context"),
        _edge(start, completion, CausalRelationKind.OPERATION_INTERVAL, event.correlation_id),
    )
    trace = EffectEventTrace(
        before,
        (reference,),
        lifecycle,
        (event,),
        edges,
        (),
        after,
        EffectStreamCompleteness.COMPLETE,
        EffectTargetTermination.REJECTED
        if termination == ExecutionStatus.REJECTED
        else EffectTargetTermination.SUCCESS,
        _provenance(),
        completion,
        completion,
        completion,
        (),
    )
    base = RunResult(
        case,
        "0" * 64,
        "ustar",
        ExecutionResult("synthetic", "1", ("synthetic",), termination, 2, "", "", 0.01),
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )
    return EffectRunResult(base, trace)


@pytest.mark.parametrize(
    "link_target, expected",
    [
        ("../outside/x", BoundaryAttemptShape.PARENT_1),
        ("./../outside/x", BoundaryAttemptShape.PARENT_1),
        ("../../x", BoundaryAttemptShape.PARENT_2),
        ("../../../deep/x", BoundaryAttemptShape.PARENT_3_PLUS),
        ("/etc/passwd", BoundaryAttemptShape.ABSOLUTE),
        ("a.txt", None),
        ("sub/file", None),
        ("", None),
    ],
)
def test_escape_shape_classifies_only_escaping_targets(link_target, expected):
    assert _escape_shape(link_target) == expected


def test_benign_synthetic_hardlink_yields_no_boundary_key() -> None:
    # The stock synthetic hardlink links two in-extract paths, so nothing escapes.
    assert boundary_attempt_keys(_result(HARDLINK_CASE).trace) == ()


def test_rejected_external_link_attempt_yields_one_boundary_key() -> None:
    result = _external_link_attempt_result(
        link_target="../outside/sentinel", outcome=OperationOutcome.NOT_FOUND
    )

    keys = boundary_attempt_keys(result.trace)

    assert len(keys) == 1
    signature = keys[0].signature
    assert keys[0].kind == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT
    assert isinstance(signature, BoundaryAttemptSignature)
    assert signature.trigger_entry_type == EntryType.HARDLINK
    assert signature.target_region == Region.EXTERNAL
    assert signature.operation_outcome == OperationOutcome.NOT_FOUND
    assert signature.escape_shape == BoundaryAttemptShape.PARENT_1


def test_p3_keys_the_rejected_attempt_while_p2_fails_closed() -> None:
    result = _external_link_attempt_result(
        link_target="../outside/sentinel", outcome=OperationOutcome.NOT_FOUND
    )
    seed = (result.base_result.case,)

    p2 = EffectSearchState(seed, EffectSearchPolicy.P2_EFFECT_ADAPTIVE).consider(result)
    p3 = EffectSearchState(seed, EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT).consider(result)

    # P2 fails closed on the rejected trace: no eligibility, no keys, no admission.
    assert not p2.feedback_eligible
    assert p2.new_effect_keys == () and not p2.admission_eligible
    # P3 relaxes the gate: the cleanly recorded rejection contributes one boundary key,
    # the arm admits the case, and the key is a BOUNDARY_ESCAPE_ATTEMPT.
    assert p3.feedback_eligible and p3.effect_novel and p3.admission_eligible
    boundary = [
        k for k in p3.new_effect_keys if k.kind == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT
    ]
    assert len(boundary) == 1


def test_p3_distinguishes_outcomes_but_not_tails() -> None:
    # Different missing external tails at the same shape/outcome collapse to one key
    # (no tail proximity encoded); a different outcome is a distinct key.
    first_result = _external_link_attempt_result(
        link_target="../outside/ghost", outcome=OperationOutcome.NOT_FOUND
    )
    state = EffectSearchState(
        (first_result.base_result.case,), EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT
    )
    first = state.consider(first_result)
    second = state.consider(
        _external_link_attempt_result(
            link_target="../outside/other", outcome=OperationOutcome.NOT_FOUND
        )
    )
    third = state.consider(
        _external_link_attempt_result(
            link_target="../outside/dir", outcome=OperationOutcome.ACCESS_DENIED
        )
    )
    assert first.effect_novel  # first NOT_FOUND external parent_1 attempt
    assert not second.effect_novel  # same key: different tail is not new
    assert third.effect_novel  # different outcome is a new key


def test_p3_benign_success_trace_matches_p2_keys() -> None:
    # On a benign success trace with no escaping link, P3 derives exactly P2's keys.
    benign = synthetic_effect_result(HARDLINK_CASE)
    p2 = EffectSearchState((HARDLINK_CASE,), EffectSearchPolicy.P2_EFFECT_ADAPTIVE).consider(benign)
    p3 = EffectSearchState(
        (HARDLINK_CASE,), EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT
    ).consider(benign)
    assert set(p2.new_effect_keys) == set(p3.new_effect_keys)
    assert all(k.kind != EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT for k in p3.new_effect_keys)


def test_p3_campaign_is_deterministic_and_adaptive() -> None:
    config = EffectCampaignConfig(
        random_seed=123,
        execution_budget=12,
        search_policy=EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT,
        mutation_policy=MutationPolicy.M1,
    )

    first = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    second = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)

    assert first == second
    mutations = first.steps[len(first.initial_case_ids) :]
    assert mutations and all(step.scheduler_evidence is not None for step in mutations)
