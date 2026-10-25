"""M3 refinement: observed external-resolve rung (P3_EXTERNAL_RESOLVE_GRADIENT).

Credits an observed link operation whose resolved path is in the EXTERNAL region,
purely from `path_region` of the observed affected paths — regardless of the raw link
text, escape shape or operation outcome. Region-based and target-agnostic: the key is
(operation, region) only, never a path/name/sentinel. Additive over the attempt key;
P0/P1/P2 and the benign loop are unchanged (pinned by the demo sha256 in `make check`).
"""

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_synthetic import (
    _edge,
    _lifecycle,
    _observation,
    _provenance,
    _snapshots,
    synthetic_effect_result,
)
from inodefence.feedback import (
    EffectSearchPolicy,
    EffectSearchState,
    external_resolve_keys,
)
from inodefence.feedback.signature import state_signature
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ArchiveEntryReference,
    AssociationKind,
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
    ExternalResolveSignature,
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


def _link_result(
    *,
    target_path: str,
    outcome: OperationOutcome,
    termination: ExecutionStatus = ExecutionStatus.REJECTED,
) -> EffectRunResult:
    """One clean trace with a single link op resolving to `target_path`."""
    entry = ArchiveEntry("link", EntryType.HARDLINK, link_target="../x")
    case = ArchiveCase((entry,))
    reference = ArchiveEntryReference(0, entry.path, entry.entry_type, entry.link_target)
    link_path = "extract/object-0"
    before, after = _snapshots()
    read, work, start, completion = 0, 1, 2, 3
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
    trace = EffectEventTrace(
        before,
        (reference,),
        (
            _lifecycle(read, reference, EntryLifecycleKind.READ),
            _lifecycle(work, reference, EntryLifecycleKind.EFFECT_WORK_STARTED),
        ),
        (event,),
        (
            _edge(work, start, CausalRelationKind.ENTRY_CONTEXT_PROPAGATION, "context"),
            _edge(start, completion, CausalRelationKind.OPERATION_INTERVAL, event.correlation_id),
        ),
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


def test_external_resolve_fires_on_external_link_regardless_of_outcome() -> None:
    for outcome in (
        OperationOutcome.NOT_FOUND,
        OperationOutcome.SUCCEEDED,
        OperationOutcome.INVALID,
    ):
        keys = external_resolve_keys(_link_result(target_path="outside/x", outcome=outcome).trace)
        assert len(keys) == 1, outcome
        sig = keys[0].signature
        assert keys[0].kind == EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE
        assert isinstance(sig, ExternalResolveSignature)
        assert sig.operation == ObservedOperationType.LINK
        assert sig.resolved_region == Region.EXTERNAL


def test_external_resolve_is_region_based_not_name_based() -> None:
    # Different external paths collapse to the same (LINK, EXTERNAL) key — the rung is
    # about the region, not any specific name, so it is name-independent by construction.
    a = external_resolve_keys(
        _link_result(target_path="outside/sentinel.txt", outcome=OperationOutcome.SUCCEEDED).trace
    )
    b = external_resolve_keys(
        _link_result(target_path="ext/ref.dat", outcome=OperationOutcome.NOT_FOUND).trace
    )
    assert a == b and len(a) == 1


def test_external_resolve_does_not_fire_inside_extraction_root() -> None:
    keys = external_resolve_keys(
        _link_result(target_path="extract/src", outcome=OperationOutcome.SUCCEEDED).trace
    )
    assert keys == ()


def test_new_arm_keys_external_resolve_while_attempt_arm_does_not() -> None:
    result = _link_result(target_path="outside/x", outcome=OperationOutcome.NOT_FOUND)
    seed = (result.base_result.case,)

    old = EffectSearchState(seed, EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT).consider(result)
    new = EffectSearchState(seed, EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT).consider(result)

    kinds_old = {k.kind for k in old.new_effect_keys}
    kinds_new = {k.kind for k in new.new_effect_keys}
    assert EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE not in kinds_old
    assert EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE in kinds_new
    # the new arm is a strict superset: it also keeps the lexical attempt key.
    assert EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT in kinds_new
    assert set(old.new_effect_keys).issubset(set(new.new_effect_keys))


def test_external_resolve_campaign_is_deterministic_and_adaptive() -> None:
    config = EffectCampaignConfig(
        random_seed=123,
        execution_budget=12,
        search_policy=EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT,
        mutation_policy=MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK,
    )
    first = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    second = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    assert first == second
    mutations = first.steps[len(first.initial_case_ids) :]
    assert mutations and all(step.scheduler_evidence is not None for step in mutations)
