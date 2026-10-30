"""M4.2 generality: external-resolve (C) and boundary-attempt (D) DECOUPLE on decompress.

Why this matters (주언's item-3 ablation): arm C = ``P3_EXTERNAL_RESOLVE_GRADIENT`` (identity
state) is meant to add a rung over arm D = ``P3_BOUNDARY_ATTEMPT_GRADIENT`` (boundary-shape
coverage). On node-tar the two channels are inseparable: every escaping input is a lexical
``../`` hardlink, so one ``fs.link`` op satisfies BOTH ``boundary_attempt_keys`` (lexical escape
shape) and ``external_resolve_keys`` (EXTERNAL resolved region). The keys co-occur on the same
op, so arms C and D steer toward the same inputs -- C and D are operationally identical (C==D) and
the D->C ablation has nothing to measure.

decompress's isolated-CWD execution model escapes differently, and that splits the channels:

  * The escaping HARDLINK target is ``outside/sentinel.txt`` -- no lexical ``..``. decompress
    resolves it with ``fs.link`` against the process working directory (the sandbox root), so an
    ``extract/`` object aliases the external sentinel. This is OBSERVED in the committed
    capability-probe evidence (``experiments/repro/evidence/decompress_hardlink.json``:
    ``extract/evil`` shares the sentinel inode, reference nlink 1 -> 2). On that op the
    external-resolve rung fires (resolved region is EXTERNAL) while the boundary-attempt key is
    SILENT (``_escape_shape("outside/sentinel.txt")`` is None) -> C WITHOUT D.

  * The observed dangling escaping SYMLINK (``slink -> ../outside/sentinel.txt``, from the
    boundary-attempt-v1 reference frame, image sha256:86ce3c7b...) is the orthogonal direction: a
    lexical escape (D-eligible) that aliases no external object (C-ineligible) -> D WITHOUT C,
    realized through the operation-generic frame path (민찬's locked wiring, gated on #177).

So C and D are ORTHOGONAL on decompress -- each channel sees boundary-relevant inputs the other
is blind to -- whereas they are identical on node-tar. The second extractor is what gives the
D->C contrast (identity-state vs coverage) something to separate.

This is an additive generality test: it exercises the UNCHANGED production derivations
(``feedback.effect``) and the UNCHANGED live arms (``EffectSearchState``). No oracle/model/feedback
change. The keys carry only (operation, region, outcome, escape-shape) -- no path, sentinel name,
CVE identifier or answer path enters any key (D005/D006).
"""

import json
from pathlib import Path

from inodefence.effect_synthetic import (
    _edge,
    _lifecycle,
    _observation,
    _provenance,
    _snapshots,
)
from inodefence.feedback import (
    EffectSearchPolicy,
    EffectSearchState,
    boundary_attempt_keys,
    external_resolve_keys,
)
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
    RunResult,
)
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts

_COMMITTED_EVIDENCE = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "repro"
    / "evidence"
    / "decompress_hardlink.json"
)


def _base_result(case: ArchiveCase, termination: ExecutionStatus) -> RunResult:
    before, after = _snapshots()
    exit_code = 0 if termination == ExecutionStatus.SUCCESS else 2
    return RunResult(
        case,
        "0" * 64,
        "ustar",
        ExecutionResult("synthetic", "1", ("synthetic",), termination, exit_code, "", "", 0.01),
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )


def _single_op_run(
    *,
    entry: ArchiveEntry,
    operation: ObservedOperationType,
    effect_class: EffectClass,
    affected_paths: tuple[str, ...],
    termination: ExecutionStatus = ExecutionStatus.SUCCESS,
    outcome: OperationOutcome = OperationOutcome.SUCCEEDED,
) -> EffectRunResult:
    """One clean, complete trace with a single observed op (the shape both key funcs read)."""
    case = ArchiveCase((entry,))
    reference = ArchiveEntryReference(0, entry.path, entry.entry_type, entry.link_target)
    read, work, start, completion = 0, 1, 2, 3
    event = FilesystemEffectEvent(
        start,
        completion,
        reference,
        AssociationKind.ASYNC_CONTEXT,
        effect_class,
        EffectEvidenceStrength.OPERATION_RESULT,
        affected_paths,
        operation,
        MonotonicInterval(start * 10, start * 10 + 1),
        MonotonicInterval(completion * 10, completion * 10 + 1),
        outcome,
        tuple(
            EffectPathEvidence(p, _observation(None), _observation(None)) for p in affected_paths
        ),
        "synthetic",
        f"operation-{start}",
        RawEvidenceReference("synthetic", f"effect-{completion}"),
    )
    before, after = _snapshots()
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
        EffectTargetTermination.SUCCESS
        if termination == ExecutionStatus.SUCCESS
        else EffectTargetTermination.REJECTED,
        _provenance(),
        completion,
        completion,
        completion,
        (),
    )
    return EffectRunResult(_base_result(case, termination), trace)


def _hardlink_run(*, link_target: str) -> EffectRunResult:
    """An observed hardlink op resolving to the external sentinel region."""
    return _single_op_run(
        entry=ArchiveEntry("evil", EntryType.HARDLINK, link_target=link_target),
        operation=ObservedOperationType.LINK,
        effect_class=EffectClass.OPERATION_OBSERVED,
        affected_paths=("outside/sentinel.txt", "extract/evil"),
    )


def _symlink_run(*, link_target: str) -> EffectRunResult:
    """An observed dangling symlink op: link inode created in extraction, target unresolved."""
    return _single_op_run(
        entry=ArchiveEntry("slink", EntryType.SYMLINK, link_target=link_target),
        operation=ObservedOperationType.SYMLINK,
        effect_class=EffectClass.SYMLINK_CREATION,
        affected_paths=("extract/slink",),
    )


def test_node_tar_lexical_hardlink_cofires_c_and_d() -> None:
    """node-tar grammar: a lexical ``../`` hardlink fires BOTH channels on one op (C and D).

    The single op satisfies D (escape shape ``PARENT_1``) and C (EXTERNAL resolved region), so the
    two arms are inseparable here -- the D->C ablation has nothing to measure on node-tar.
    """
    trace = _hardlink_run(link_target="../outside/sentinel.txt").trace
    d = boundary_attempt_keys(trace)
    c = external_resolve_keys(trace)
    assert len(d) == 1 and d[0].kind == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT
    assert len(c) == 1 and c[0].kind == EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE


def test_decompress_cwd_hardlink_fires_c_without_d() -> None:
    """decompress grammar: the CWD-relative hardlink fires C (external resolve) with D SILENT.

    ``outside/sentinel.txt`` has no lexical ``..`` so ``_escape_shape`` is None and the
    boundary-attempt key never forms, yet the op resolves to the EXTERNAL region so the
    external-resolve rung fires. The UNCHANGED keys decouple -- node-tar cannot show this.
    """
    trace = _hardlink_run(link_target="outside/sentinel.txt").trace
    assert boundary_attempt_keys(trace) == ()  # D blind: no lexical escape shape
    c = external_resolve_keys(trace)
    assert len(c) == 1 and c[0].kind == EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE


def test_live_arms_diverge_on_decompress_cwd_hardlink() -> None:
    """Gradient steer smoke: only arm C admits a boundary key on the decompress CWD hardlink.

    Arm A (P1) and arm D (P3_BOUNDARY) are structurally blind to the CWD-relative external
    resolve; arm C (P3_EXTERNAL) admits an OBSERVED_EXTERNAL_RESOLVE key -- a rung D cannot reach
    on this input. On node-tar this divergence is impossible, because the lexical hardlink always
    hands D a co-occurring boundary-attempt key.
    """
    run = _hardlink_run(link_target="outside/sentinel.txt")
    seed = (run.base_result.case,)

    kinds_a = {
        key.kind
        for key in EffectSearchState(seed, EffectSearchPolicy.P1_EFFECT_RETENTION)
        .consider(run)
        .new_effect_keys
    }
    kinds_d = {
        key.kind
        for key in EffectSearchState(seed, EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT)
        .consider(run)
        .new_effect_keys
    }
    kinds_c = {
        key.kind
        for key in EffectSearchState(seed, EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT)
        .consider(run)
        .new_effect_keys
    }

    assert EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE not in kinds_a
    assert EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE not in kinds_d  # arm D is blind
    assert EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE in kinds_c  # arm C sees the rung
    # the boundary-attempt channel is silent for every arm on the CWD-relative escape:
    assert EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT not in kinds_d
    assert EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT not in kinds_c


def test_decompress_symlink_is_silent_on_the_link_only_trace_path() -> None:
    """The trace-path keys are LINK-gated, so the observed escaping SYMLINK fires neither.

    The dangling escaping symlink is the orthogonal decoupling direction (lexical escape, no
    external object aliased -> D without C), but ``boundary_attempt_keys`` and
    ``external_resolve_keys`` both require ``operation == LINK``. Realizing D-without-C is the
    operation-generic frame path (the locked ``inodefence-boundary-attempt-v1`` wiring), gated on
    #177; this pins the trace-path limitation so the gap is explicit, not hidden.
    """
    trace = _symlink_run(link_target="../outside/sentinel.txt").trace
    assert boundary_attempt_keys(trace) == ()
    assert external_resolve_keys(trace) == ()


def test_decompress_fixture_matches_committed_observation() -> None:
    """The CWD-relative target used above is the one really observed (no lexical ``..``)."""
    evidence = json.loads(_COMMITTED_EVIDENCE.read_text(encoding="utf-8"))
    (entry,) = evidence["entries"]
    assert entry["type"] == "link"  # a hardlink
    assert entry["linkname"] == "outside/sentinel.txt"
    assert ".." not in entry["linkname"]  # escapes via the process CWD, not lexically
    assert evidence["per_role"]["affected"]["verdict"]["c1_identity_shared"] is True
