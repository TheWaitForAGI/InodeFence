"""node-tar ``EffectEventTrace`` -> v1 boundary-attempt frame projection.

Pins ``feedback.boundary_attempt_frame.boundary_attempt_frame_from_effect_trace``: the projection
that makes node-tar (via its existing effect producer's trace) emit the standard
``inodefence-boundary-attempt-v1`` frame, so the M3.1 boundary-attempt gradient can consume node-tar
through the same normalizer a generality extractor (decompress) uses.

The central property is an *observational equivalence*: because the projection reads target regions
only from the event's observed affected paths (never resolving a link the extractor did not follow),
for SUCCEEDED link operations

    frame_boundary_attempt_keys(project(trace)) == boundary_attempt_keys(trace)
                                                   | external_resolve_keys(trace)

exactly -- the v1-frame path yields the same keys as node-tar's direct M3.1 trace derivations. The
one documented gap is outcome granularity: the frame's coarse ``outcome`` collapses the rarer
non-SUCCEEDED ``OperationOutcome`` values, which the rejected-attempt test makes explicit.

In-memory synthetic traces only -- no Docker -- so it runs in ``make check``. Additive; the oracle,
model and ``effect.py`` derivations are unchanged.
"""

from typing import Any, NamedTuple, cast

import pytest

from inodefence.effect_synthetic import _edge, _lifecycle, _provenance, _snapshots
from inodefence.feedback.boundary_attempt_frame import (
    FRAME_FORMAT,
    boundary_attempt_frame_from_effect_trace,
    frame_boundary_attempt_keys,
)
from inodefence.feedback.effect import boundary_attempt_keys, external_resolve_keys
from inodefence.model import (
    ArchiveEntryReference,
    AssociationKind,
    BoundaryAttemptShape,
    BoundaryAttemptSignature,
    CausalRelationKind,
    EffectClass,
    EffectEventTrace,
    EffectEvidenceStrength,
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EntryLifecycleKind,
    EntryType,
    ExternalResolveSignature,
    FilesystemEffectEvent,
    MonotonicInterval,
    ObservedOperationType,
    OperationOutcome,
    RawEvidenceReference,
    Region,
)


class _Spec(NamedTuple):
    path: str
    entry_type: EntryType
    link_target: str | None
    operation: ObservedOperationType
    effect_class: EffectClass
    affected_paths: tuple[str, ...]
    outcome: OperationOutcome


def _event(reference: ArchiveEntryReference, spec: _Spec, start: int) -> FilesystemEffectEvent:
    completion = start + 1
    return FilesystemEffectEvent(
        start,
        completion,
        reference,
        AssociationKind.ASYNC_CONTEXT,
        spec.effect_class,
        EffectEvidenceStrength.OPERATION_RESULT,
        spec.affected_paths,
        spec.operation,
        MonotonicInterval(start * 10, start * 10 + 1),
        MonotonicInterval(completion * 10, completion * 10 + 1),
        spec.outcome,
        (),  # object evidence is not read by the key derivations; empty is valid.
        "synthetic",
        f"operation-{start}",
        RawEvidenceReference("synthetic", f"effect-{completion}"),
    )


def _trace(*specs: _Spec) -> EffectEventTrace:
    """Build one COMPLETE trace with an observed effect event per spec (sequences 4*i..4*i+3)."""
    before, after = _snapshots()
    references: list[ArchiveEntryReference] = []
    lifecycle = []
    effects = []
    edges = []
    for index, spec in enumerate(specs):
        reference = ArchiveEntryReference(index, spec.path, spec.entry_type, spec.link_target)
        references.append(reference)
        read, work, start, completion = 4 * index, 4 * index + 1, 4 * index + 2, 4 * index + 3
        lifecycle.extend(
            (
                _lifecycle(read, reference, EntryLifecycleKind.READ),
                _lifecycle(work, reference, EntryLifecycleKind.EFFECT_WORK_STARTED),
            )
        )
        event = _event(reference, spec, start)
        effects.append(event)
        edges.extend(
            (
                _edge(work, start, CausalRelationKind.ENTRY_CONTEXT_PROPAGATION, "context"),
                _edge(
                    start,
                    completion,
                    CausalRelationKind.OPERATION_INTERVAL,
                    event.correlation_id,
                ),
            )
        )
    last = 4 * len(specs) - 1
    return EffectEventTrace(
        before,
        tuple(references),
        tuple(lifecycle),
        tuple(effects),
        tuple(edges),
        (),
        after,
        EffectStreamCompleteness.COMPLETE,
        EffectTargetTermination.SUCCESS,
        _provenance(),
        last,
        last,
        last,
        (),
    )


# A realistic SUCCEEDED multi-operation extraction: a lexically escaping hardlink, a CWD-relative
# hardlink escape (no ".." -> no lexical shape), a contained hardlink, an escaping symlink node-tar
# creates but does not follow, and a plain regular file.
def _escaping_hardlink(outcome: OperationOutcome = OperationOutcome.SUCCEEDED) -> _Spec:
    return _Spec(
        "escape",
        EntryType.HARDLINK,
        "../outside/sentinel",
        ObservedOperationType.LINK,
        EffectClass.HARDLINK_IDENTITY_RELATION_CREATION
        if outcome == OperationOutcome.SUCCEEDED
        else EffectClass.OPERATION_OBSERVED,
        ("outside/sentinel", "extract/escape-link"),
        outcome,
    )


_CWD_RELATIVE_HARDLINK = _Spec(
    "cwd",
    EntryType.HARDLINK,
    "outside/sentinel",  # CWD-relative, no leading ".." -> no lexical escape shape
    ObservedOperationType.LINK,
    EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
    ("outside/sentinel-cwd", "extract/cwd-link"),
    OperationOutcome.SUCCEEDED,
)
_CONTAINED_HARDLINK = _Spec(
    "contained",
    EntryType.HARDLINK,
    "a.txt",
    ObservedOperationType.LINK,
    EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
    ("extract/source", "extract/contained-link"),
    OperationOutcome.SUCCEEDED,
)
_ESCAPING_SYMLINK = _Spec(
    "evil-symlink",
    EntryType.SYMLINK,
    "../outside/evil",  # target text escapes, but node-tar only creates the inode (not followed)
    ObservedOperationType.SYMLINK,
    EffectClass.SYMLINK_CREATION,
    ("extract/evil-symlink",),
    OperationOutcome.SUCCEEDED,
)
_REGULAR_FILE = _Spec(
    "regular.txt",
    EntryType.REGULAR,
    None,
    ObservedOperationType.OPEN,
    EffectClass.NAMESPACE_CREATION,
    ("extract/regular.txt",),
    OperationOutcome.SUCCEEDED,
)


def _direct_keys(trace: EffectEventTrace) -> set[EffectFeedbackKey]:
    return set(boundary_attempt_keys(trace)) | set(external_resolve_keys(trace))


def test_projection_emits_a_valid_v1_frame() -> None:
    frame = boundary_attempt_frame_from_effect_trace(_trace(_escaping_hardlink()))

    assert frame["format"] == FRAME_FORMAT
    assert frame["schema_version"] == 1
    assert frame["extractor"] == "synthetic@1"  # honest: labels a synthetic source as synthetic
    assert frame["extraction_root_absolute"] == "/var/lib/inodefence/effect-feedback"
    attempts = frame["attempts"]
    assert isinstance(attempts, list) and len(attempts) == 1
    assert attempts[0] == {
        "operation": "hardlink",
        "created_path": "extract/escape-link",
        "created_region": "extraction",
        "target_raw": "../outside/sentinel",
        "target_resolved_absolute": "outside/sentinel",
        "target_region": "external",
        "aliases_external_object": True,
        "outcome": "created",
    }


def test_frame_path_equals_direct_derivation_for_succeeded_multi_op_trace() -> None:
    # The central observational-equivalence property: node-tar's v1-frame path yields exactly the
    # keys its direct M3.1 trace derivation does, across every operation kind in one trace.
    trace = _trace(
        _escaping_hardlink(),
        _CWD_RELATIVE_HARDLINK,
        _CONTAINED_HARDLINK,
        _ESCAPING_SYMLINK,
        _REGULAR_FILE,
    )

    framed = set(frame_boundary_attempt_keys(boundary_attempt_frame_from_effect_trace(trace)))

    assert framed == _direct_keys(trace)
    # And concretely: the lexical escape key (from the ".." hardlink) plus the region key (shared by
    # both the lexical and the CWD-relative hardlink escapes, deduplicated).
    assert framed == {
        EffectFeedbackKey(
            EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT,
            BoundaryAttemptSignature(
                EntryType.HARDLINK,
                Region.EXTERNAL,
                OperationOutcome.SUCCEEDED,
                BoundaryAttemptShape.PARENT_1,
            ),
        ),
        EffectFeedbackKey(
            EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE,
            ExternalResolveSignature(ObservedOperationType.LINK, Region.EXTERNAL),
        ),
    }


def test_symlink_not_followed_yields_no_key_matching_link_only_derivation() -> None:
    # node-tar creates an escaping symlink's inode inside the root but does not follow it, so no
    # external path is observed -> target_region "n/a" -> no key, exactly as the LINK-only trace
    # derivation (which never inspects SYMLINK events) produces nothing.
    trace = _trace(_ESCAPING_SYMLINK)
    frame = boundary_attempt_frame_from_effect_trace(trace)

    assert frame["attempts"] == [
        {
            "operation": "symlink",
            "created_path": "extract/evil-symlink",
            "created_region": "extraction",
            "target_raw": "../outside/evil",
            "target_resolved_absolute": None,
            "target_region": "n/a",
            "aliases_external_object": False,
            "outcome": "created",
        }
    ]
    assert frame_boundary_attempt_keys(frame) == ()
    assert _direct_keys(trace) == set()


def test_rejected_attempt_matches_direct_key_except_coarsened_outcome() -> None:
    # The documented gap: the frame's coarse outcome collapses NOT_FOUND to "refused" -> INVALID.
    # Every other dimension of the lexical attempt key still matches, and the region key (which is
    # outcome-independent) matches exactly.
    trace = _trace(_escaping_hardlink(OperationOutcome.NOT_FOUND))
    direct = _direct_keys(trace)
    framed = set(frame_boundary_attempt_keys(boundary_attempt_frame_from_effect_trace(trace)))

    resolve = EffectFeedbackKey(
        EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE,
        ExternalResolveSignature(ObservedOperationType.LINK, Region.EXTERNAL),
    )
    assert resolve in direct and resolve in framed

    [direct_attempt] = [
        k for k in direct if k.kind == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT
    ]
    [framed_attempt] = [
        k for k in framed if k.kind == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT
    ]
    direct_sig = direct_attempt.signature
    framed_sig = framed_attempt.signature
    assert isinstance(direct_sig, BoundaryAttemptSignature)
    assert isinstance(framed_sig, BoundaryAttemptSignature)
    # Same trigger kind / region / escape shape:
    assert direct_sig.trigger_entry_type == framed_sig.trigger_entry_type
    assert direct_sig.target_region == framed_sig.target_region
    assert direct_sig.escape_shape == framed_sig.escape_shape
    # Coarsened outcome: the trace preserves NOT_FOUND; the v1 frame can only say "refused".
    assert direct_sig.operation_outcome == OperationOutcome.NOT_FOUND
    assert framed_sig.operation_outcome == OperationOutcome.INVALID


def test_projection_rejects_non_trace_input() -> None:
    # Defensive guard mirrors the typed trace derivations in effect.py; cast past the type checker
    # to exercise it at runtime.
    with pytest.raises(ValueError, match="EffectEventTrace"):
        boundary_attempt_frame_from_effect_trace(cast(Any, {"effect_events": []}))
