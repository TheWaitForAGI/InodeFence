"""M4.2 generality: external-resolve (C) and boundary-attempt (D) DECOUPLE on decompress.

Why this matters (주언's item-3 ablation): arm C = ``P3_EXTERNAL_RESOLVE_GRADIENT`` (identity
state) is meant to add a rung over arm D = ``P3_BOUNDARY_ATTEMPT_GRADIENT`` (boundary-shape
coverage). On node-tar the two channels are inseparable: every escaping input is a lexical
``../`` hardlink, so one ``fs.link`` op satisfies BOTH ``boundary_attempt_keys`` (lexical escape
shape) and ``external_resolve_keys`` (EXTERNAL resolved region). The keys co-occur on the same
op, so arms C and D steer toward the same inputs -- C and D are operationally identical (C==D) and
the D->C ablation has nothing to measure.

decompress's isolated-CWD execution model escapes differently, and that splits the channels. The
splitting is driven by the ESCAPE MECHANISM (lexical ``..`` vs CWD-relative), not by the entry
type, because the keys read a region and a shape, not an entry kind:

  * CWD-relative external escape -> C WITHOUT D. decompress's escaping HARDLINK target is
    ``outside/sentinel.txt`` (no lexical ``..``); ``fs.link`` resolves it against the process
    working directory, so an ``extract/`` object aliases the external sentinel. OBSERVED in
    ``experiments/repro/evidence/decompress_hardlink.json`` (``extract/evil`` shares the sentinel
    inode, nlink 1 -> 2). The op resolves to the EXTERNAL region (C fires) but
    ``_escape_shape("outside/sentinel.txt")`` is None (D silent) -> C alone. This is the rung
    arm C adds that arm D cannot reach, and it is impossible on node-tar's lexical ``../`` grammar.

  * Lexical external escape -> C AND D co-fire (NOT a D-without-C case). decompress's observed
    escaping SYMLINK ``slink -> ../outside/sentinel.txt`` (the boundary-attempt-v1 frame, image
    sha256:86ce3c7b...) has a lexical escape shape (D fires) AND a target region the fs-wrap frame
    records as EXTERNAL (C fires, region-based -- ``frame_boundary_attempt_keys`` credits C on the
    region regardless of ``aliases_external_object``, which is False for a dangling symlink). So
    the lexical symlink does NOT separate C from D; it co-fires both, exactly like a node-tar
    lexical hardlink. (A D-without-C input would need a lexical escape whose target region is
    HARNESS, not EXTERNAL -- i.e. not the external-sentinel attack.)

So on decompress arm C is a strict superset of arm D on external escapes: the CWD-relative escape
gives C a rung D is blind to, while lexical escapes co-fire both. That asymmetry (absent on
node-tar, where every escape is lexical -> C == D) is what gives the D->C ablation signal.

Two key spaces exercised here, both UNCHANGED and additive:
  * trace-path keys ``effect.boundary_attempt_keys`` / ``external_resolve_keys`` -- LINK-only (the
    node-tar arms; FROZEN). They fire on the CWD hardlink (C alone) and are silent on any SYMLINK
    op (operation gate).
  * the canonical op-generic normalizer ``boundary_attempt_frame.frame_boundary_attempt_keys``
    (#179, main) -- reads a v1 frame, so it credits both LINK and SYMLINK attempts. Fed the real
    committed decompress frame it yields: CWD hardlink -> C alone; lexical symlink -> C and D.

The keys carry only (operation, region, outcome, escape-shape) -- no path, sentinel name, CVE
identifier or answer path (D005/D006). No oracle/model/feedback change.
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
from inodefence.feedback.boundary_attempt_frame import (
    FRAME_FORMAT,
    frame_boundary_attempt_keys,
)
from inodefence.feedback.signature import state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ArchiveEntryReference,
    AssociationKind,
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
    ExternalResolveSignature,
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
# The real decompress 4.2.1 fs-wrap boundary-attempt-v1 frame (image sha256:86ce3c7b...), observed
# by experiments/repro/decompress_entry_effect_feasibility.py. Holds one frame of three attempts:
# a CWD-relative escaping hardlink, a lexical escaping symlink, and a benign regular write.
_COMMITTED_FRAME = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "repro"
    / "evidence"
    / "decompress_entry_effect_feasibility.json"
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
    """The trace-path keys are LINK-gated, so a SYMLINK op fires neither of them.

    ``boundary_attempt_keys`` and ``external_resolve_keys`` both require ``operation == LINK``, so
    they are structurally silent on any SYMLINK op -- this is the LINK-only reach of the node-tar
    arms. The op-generic view of the same symlink lives in the frame normalizer
    (``frame_boundary_attempt_keys``), exercised below; this pins the trace-path gate so the
    LINK-only limitation is explicit, not hidden.
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


# --- op-generic canonical frame keys on the REAL observed decompress frame -------------------
#
# frame_boundary_attempt_keys (#179, main) reads a v1 frame, so it credits SYMLINK as well as LINK
# attempts -- the op-generic path the campaign uses. Fed the committed real-decompress frame it
# shows the TRUE decoupling: the CWD-relative hardlink fires C alone, while the lexical symlink
# co-fires C AND D (correcting an earlier mis-read that called the symlink a D-without-C case).


def _observed_frame() -> dict:
    frame = json.loads(_COMMITTED_FRAME.read_text(encoding="utf-8"))["frame"]
    assert frame["format"] == FRAME_FORMAT
    return frame


def _single_attempt_frame(frame: dict, operation: str) -> dict:
    (attempt,) = [a for a in frame["attempts"] if a["operation"] == operation]
    return {**frame, "attempts": [attempt]}


def _kinds(keys: tuple) -> set:
    return {key.kind for key in keys}


def test_canonical_frame_keys_cwd_hardlink_fires_c_without_d() -> None:
    """On the REAL observed frame, the CWD-relative hardlink fires C alone (op-generic path)."""
    frame = _observed_frame()
    (hardlink,) = [a for a in frame["attempts"] if a["operation"] == "hardlink"]
    assert hardlink["target_raw"] == "outside/sentinel.txt"  # no lexical ".."
    assert hardlink["target_region"] == "external"
    kinds = _kinds(frame_boundary_attempt_keys(_single_attempt_frame(frame, "hardlink")))
    assert EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE in kinds  # C
    assert EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT not in kinds  # D silent -> C-without-D


def test_canonical_frame_keys_lexical_symlink_cofires_c_and_d() -> None:
    """On the REAL observed frame, the lexical symlink co-fires C AND D (corrects D-without-C).

    ``frame_boundary_attempt_keys`` credits C on the EXTERNAL target region regardless of
    ``aliases_external_object`` (False for this dangling symlink), and D on the lexical escape
    shape. So the lexical external symlink does NOT separate C from D -- it co-fires both, like a
    node-tar lexical hardlink. The decoupling comes from the CWD-relative escape, not the symlink.
    """
    frame = _observed_frame()
    (symlink,) = [a for a in frame["attempts"] if a["operation"] == "symlink"]
    assert symlink["target_raw"] == "../outside/sentinel.txt"  # lexical escape
    assert symlink["target_region"] == "external"
    assert symlink["aliases_external_object"] is False  # dangling, yet C still fires (region-based)
    kinds = _kinds(frame_boundary_attempt_keys(_single_attempt_frame(frame, "symlink")))
    assert EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE in kinds  # C (region)
    assert EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT in kinds  # D (lexical shape)


def test_canonical_frame_keys_benign_regular_fires_nothing() -> None:
    """The benign regular write (target region n/a) forms no boundary key."""
    frame = _observed_frame()
    assert frame_boundary_attempt_keys(_single_attempt_frame(frame, "regular")) == ()


def test_canonical_frame_full_observed_frame_separates_arm_c_from_arm_d() -> None:
    """The whole observed frame: C fires for both link kinds; D fires only for the lexical symlink.

    So arm C (boundary + external-resolve) gains the hardlink's external-resolve rung that arm D
    (boundary only) never sees, while both see the symlink's boundary key -> arm C is a strict
    superset of arm D on this frame. That asymmetry is the measurable D->C signal.
    """
    keys = frame_boundary_attempt_keys(_observed_frame())
    external_ops = {
        key.signature.operation
        for key in keys
        if isinstance(key.signature, ExternalResolveSignature)
    }
    boundary_sigs = [
        key.signature for key in keys if isinstance(key.signature, BoundaryAttemptSignature)
    ]
    assert external_ops == {
        ObservedOperationType.LINK,  # the CWD hardlink -- the rung D is blind to
        ObservedOperationType.SYMLINK,  # the lexical symlink
    }
    assert len(boundary_sigs) == 1
    assert boundary_sigs[0].trigger_entry_type == EntryType.SYMLINK
