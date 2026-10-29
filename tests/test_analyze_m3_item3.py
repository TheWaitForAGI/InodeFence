"""item-3 primary-metric roll-up: re-derivation fidelity + aggregation.

The load-bearing test is ``test_record_rederivation_matches_canonical_keys``: it builds
a real ``EffectEventTrace``, serializes it through the SAME projection the evidence used
(``effect_demo._trace_report``), and asserts the script's projection re-derivation
produces exactly the canonical ``feedback.effect.{boundary_attempt_keys,
external_resolve_keys}``. If the projection ever dropped a field the predicates read, or
the re-derivation drifted, this fails.
"""

from scripts.analyze_m3_item3 import (
    analyze_cell,
    boundary_attempt_keys_from_record,
    external_resolve_keys_from_record,
)

from inodefence.effect_demo import _trace_report
from inodefence.effect_synthetic import (
    _edge,
    _lifecycle,
    _observation,
    _provenance,
    _snapshots,
    synthetic_effect_result,
)
from inodefence.feedback import boundary_attempt_keys, external_resolve_keys
from inodefence.feedback.signature import state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ArchiveEntryReference,
    AssociationKind,
    CausalRelationKind,
    EffectClass,
    EffectEventTrace,
    EffectEvidenceStrength,
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
    RunResult,
)
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts

HARDLINK_CASE = ArchiveCase((ArchiveEntry("link", EntryType.HARDLINK, link_target="a.txt"),))


def _external_link_result(
    *,
    link_target: str,
    outcome: OperationOutcome,
    target_path: str = "outside/sentinel",
    termination: ExecutionStatus = ExecutionStatus.REJECTED,
) -> EffectRunResult:
    """One clean trace whose single hardlink LINK op targets outside the extraction root."""
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
        ExecutionResult(
            "synthetic",
            "1",
            ("synthetic",),
            termination,
            0 if termination == ExecutionStatus.SUCCESS else 2,
            "",
            "",
            0.01,
        ),
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )
    return EffectRunResult(base, trace)


def _assert_rederivation_matches(result: EffectRunResult) -> None:
    serialized = _trace_report(result)
    assert boundary_attempt_keys_from_record(serialized) == set(boundary_attempt_keys(result.trace))
    assert external_resolve_keys_from_record(serialized) == set(external_resolve_keys(result.trace))


def test_record_rederivation_matches_canonical_keys() -> None:
    # Escaping external hardlink at several shapes/outcomes, plus a benign in-root hardlink.
    _assert_rederivation_matches(
        _external_link_result(link_target="../outside/sentinel", outcome=OperationOutcome.NOT_FOUND)
    )
    _assert_rederivation_matches(
        _external_link_result(link_target="/etc/elsewhere", outcome=OperationOutcome.ACCESS_DENIED)
    )
    _assert_rederivation_matches(
        _external_link_result(
            link_target="../../deep/x",
            outcome=OperationOutcome.SUCCEEDED,
            termination=ExecutionStatus.SUCCESS,
        )
    )
    _assert_rederivation_matches(synthetic_effect_result(HARDLINK_CASE))


def test_benign_trace_yields_no_boundary_or_external_keys() -> None:
    serialized = _trace_report(synthetic_effect_result(HARDLINK_CASE))
    assert boundary_attempt_keys_from_record(serialized) == frozenset()
    assert external_resolve_keys_from_record(serialized) == frozenset()


def test_non_hardlink_link_target_gives_external_resolve_but_no_attempt() -> None:
    # external_resolve credits any LINK op resolving external; boundary_attempt needs a
    # hardlink trigger with an escaping link_target. A record missing the entry type must
    # therefore yield an external key but no attempt key.
    serialized = _trace_report(
        _external_link_result(link_target="a.txt", outcome=OperationOutcome.NOT_FOUND)
    )
    # link_target "a.txt" does not escape -> no attempt key, but target_path is external.
    assert boundary_attempt_keys_from_record(serialized) == frozenset()
    assert len(external_resolve_keys_from_record(serialized)) == 1


def test_analyze_cell_rate_first_and_terminal_c1() -> None:
    attempt = _trace_report(
        _external_link_result(link_target="../outside/x", outcome=OperationOutcome.NOT_FOUND)
    )
    benign = _trace_report(synthetic_effect_result(HARDLINK_CASE))
    steps = [
        {"trace": benign, "oracle": {"C0": False, "C1": False, "C2": False}},
        {"trace": attempt, "oracle": {"C0": False, "C1": False, "C2": False}},
        {"trace": benign, "oracle": {"C0": False, "C1": True, "C2": False}},
    ]
    result = analyze_cell(steps)
    assert result["executions"] == 3
    assert result["boundary_attempt"]["executions_with_key"] == 1
    assert result["boundary_attempt"]["rate"] == 1 / 3
    assert result["boundary_attempt"]["executions_to_first"] == 2
    assert result["external_resolve"]["executions_with_key"] == 1
    assert result["terminal_c1_steps"] == [3]
