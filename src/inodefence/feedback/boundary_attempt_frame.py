"""Project an extractor trace to the boundary-attempt v1 frame, and normalize that frame to keys.

This module is the ``inodefence-boundary-attempt-v1`` hub -- the common set-signal interface that
lets the M3.1 boundary-attempt gradient (``EffectNoveltyIndex``) generalize across extractors. It
holds both directions of that interface:

  * ``boundary_attempt_frame_from_effect_trace`` -- PROJECTION. node-tar's existing effect producer
    yields an ``EffectEventTrace``; this projects it to a v1 frame (the unordered attempt SET), so
    node-tar becomes the first real extractor emitting the standard frame. Observed-only: an
    attempt's target region comes from the event's observed affected-path regions, never by
    resolving a link the extractor did not follow, so it adds no inference the trace lacks. As a
    result ``frame_boundary_attempt_keys(project(trace))`` equals the node-tar trace derivations
    ``effect.boundary_attempt_keys(trace)`` + ``external_resolve_keys(trace)`` (for SUCCEEDED link
    ops; the frame's coarse outcome collapses the rarer non-SUCCEEDED ``OperationOutcome`` values).
  * ``frame_boundary_attempt_keys`` -- NORMALIZATION. maps any v1 frame (node-tar's here, or a
    decompress fs-wrap frame, per M4) onto the EXISTING M3.1 signatures.

A generality extractor (decompress, per M4) emits an ``inodefence-boundary-attempt-v1`` frame --
an unordered SET of per-operation attempts observed during extraction (see
``experiments/repro/decompress_effect_probe/fswrap_probe.cjs`` and that probe's feasibility
notes; the full ordered, entry-correlated entry-completion boundary is NOT feasible, so this is
the feasible set-based subset). This module maps that frame onto the EXISTING M3.1 feedback
signatures so the boundary-attempt gradient (``EffectNoveltyIndex``) generalizes to a second
extractor. It reuses ``effect._escape_shape`` so the escape bucketing is identical to the
node-tar trace derivation; it adds no new signature type and plants no answer (region/shape only,
never a path, protected object, sentinel, tail, CVE or PoC -- target-agnostic, D005).

It mirrors the two node-tar derivations in ``effect.py``:
  * BOUNDARY_ESCAPE_ATTEMPT (lexical): a link whose raw target is absolute or leads with ``..``
    and whose observed target region is outside the extraction root.
  * OBSERVED_EXTERNAL_RESOLVE (region): a link whose observed target region is EXTERNAL,
    regardless of the raw text -- so it credits a CWD-relative hardlink escape (``os.link`` of a
    plain relative name) that the lexical key misses, which is exactly decompress's case. Here it
    also covers symlink operations (``effect.external_resolve_keys`` currently reads LINK events
    only; the frame observes both link kinds, and the signature type already admits either).

This is the set the Observation lane wires to M3.1; it is standalone (not yet invoked by the
decompress adapter, which integrates after M4.2 merges). Additive: no oracle/model/effect change.
"""

from ..model import (
    BoundaryAttemptSignature,
    EffectClass,
    EffectEventTrace,
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    EntryType,
    ExternalResolveSignature,
    ObservedOperationType,
    OperationOutcome,
    Region,
)
from ..model.filesystem import path_region
from .effect import _escape_shape, _feedback_key_sort_key

FRAME_FORMAT = "inodefence-boundary-attempt-v1"

_ENTRY_TYPE = {
    "hardlink": EntryType.HARDLINK,
    "symlink": EntryType.SYMLINK,
    "regular": EntryType.REGULAR,
    "dir": EntryType.DIRECTORY,
}
_OPERATION = {
    "hardlink": ObservedOperationType.LINK,
    "symlink": ObservedOperationType.SYMLINK,
    "regular": ObservedOperationType.WRITE,
    "dir": ObservedOperationType.MKDIR,
}
# Coarse frame outcome -> OperationOutcome. BoundaryAttemptSignature (unlike a realized effect)
# admits any outcome, so a cleanly refused attempt still yields a key.
_OUTCOME = {
    "created": OperationOutcome.SUCCEEDED,
    "refused": OperationOutcome.INVALID,
    "io_error": OperationOutcome.OTHER_ERROR,
}
_LINK_OPERATIONS = ("hardlink", "symlink")


def frame_boundary_attempt_keys(frame: object) -> tuple[EffectFeedbackKey, ...]:
    """Derive the boundary-attempt and external-resolve feedback keys from a v1 frame.

    Returns a canonically sorted, de-duplicated tuple of ``EffectFeedbackKey``. Rejects a frame
    whose ``format`` is not ``inodefence-boundary-attempt-v1``. Non-link or extraction-region
    attempts contribute no key.
    """
    if not isinstance(frame, dict) or frame.get("format") != FRAME_FORMAT:
        raise ValueError(f"expected an {FRAME_FORMAT} frame")
    attempts = frame.get("attempts")
    if not isinstance(attempts, list):
        raise ValueError("boundary-attempt frame requires an attempts list")

    keys: set[EffectFeedbackKey] = set()
    for attempt in attempts:
        operation = attempt.get("operation")
        if operation not in _LINK_OPERATIONS:
            continue
        target_region = attempt.get("target_region")
        if target_region not in (Region.EXTERNAL.value, Region.HARNESS.value):
            continue
        region = Region(target_region)
        # Lexical escape attempt (absolute or leading `..`); a CWD-relative escape has no shape.
        shape = _escape_shape(attempt.get("target_raw") or "")
        if shape is not None:
            keys.add(
                EffectFeedbackKey(
                    EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT,
                    BoundaryAttemptSignature(
                        _ENTRY_TYPE[operation],
                        region,
                        _OUTCOME.get(attempt.get("outcome"), OperationOutcome.OTHER_ERROR),
                        shape,
                    ),
                )
            )
        # Region key: covers the CWD-relative hardlink escape the lexical key misses.
        if region == Region.EXTERNAL:
            keys.add(
                EffectFeedbackKey(
                    EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE,
                    ExternalResolveSignature(_OPERATION[operation], Region.EXTERNAL),
                )
            )
    return tuple(sorted(keys, key=_feedback_key_sort_key))


# --- Projection: node-tar EffectEventTrace -> v1 frame ---------------------------------------
#
# node-tar's effect producer already yields an EffectEventTrace; this projects it to the v1 frame
# so node-tar emits the same set-signal frame a generality extractor does. Observed-only: it reads
# the regions of each event's observed affected paths and never resolves a link not followed.
_OPERATION_FROM_OBSERVED = {
    ObservedOperationType.LINK: "hardlink",
    ObservedOperationType.SYMLINK: "symlink",
    ObservedOperationType.OPEN: "regular",
    ObservedOperationType.WRITE: "regular",
    ObservedOperationType.WRITEV: "regular",
    ObservedOperationType.MKDIR: "dir",
}
# Observed OperationOutcome -> coarse v1 outcome, the inverse of _OUTCOME for the round-trippable
# values: SUCCEEDED/OTHER_ERROR map back exactly, and the rarer rejections (already_exists/
# not_found/access_denied/invalid) all coarsen to "refused" (-> INVALID). node-tar boundary
# attempts observe SUCCEEDED, so the projected key's outcome matches the trace derivation there.
_FRAME_OUTCOME = {
    OperationOutcome.SUCCEEDED: "created",
    OperationOutcome.OTHER_ERROR: "io_error",
}


def boundary_attempt_frame_from_effect_trace(trace: EffectEventTrace) -> dict[str, object]:
    """Project a node-tar ``EffectEventTrace`` onto an ``inodefence-boundary-attempt-v1`` frame.

    Maps each object-creating filesystem effect event to a v1 attempt record. Observed-only: an
    attempt's ``target_region`` / ``target_resolved_absolute`` come from the event's observed
    non-extraction affected paths (``path_region``), exactly as ``effect.boundary_attempt_keys``
    reads them -- never by lexically resolving a symlink target the extractor did not follow. So a
    node-tar escaping hardlink (an observed external affected path) maps to the same key pair the
    M3.1 trace derivation produces, and a symlink node-tar merely created (inode in the extraction
    root, target not followed) carries ``target_region == "n/a"`` and forms no key -- matching the
    LINK-only reach of the trace derivation. Metadata/teardown operations (chmod, close, unlink,
    ...) are not create attempts and are dropped. Additive; reads the trace only.
    """
    if not isinstance(trace, EffectEventTrace):
        raise ValueError("boundary-attempt frame projection requires an EffectEventTrace")

    attempts: list[dict[str, object]] = []
    for event in trace.effect_events:
        operation = _OPERATION_FROM_OBSERVED.get(event.operation)
        if operation is None:
            continue
        extraction_paths = [p for p in event.affected_paths if path_region(p) == Region.EXTRACTION]
        external_paths = [p for p in event.affected_paths if path_region(p) != Region.EXTRACTION]
        created_path = (
            extraction_paths[0]
            if extraction_paths
            else (event.affected_paths[0] if event.affected_paths else None)
        )
        target_resolved = external_paths[0] if external_paths else None
        attempts.append(
            {
                "operation": operation,
                "created_path": created_path,
                "created_region": (
                    path_region(created_path).value if created_path is not None else None
                ),
                "target_raw": event.entry.link_target,
                "target_resolved_absolute": target_resolved,
                "target_region": (
                    path_region(target_resolved).value if target_resolved is not None else "n/a"
                ),
                "aliases_external_object": (
                    event.effect_class == EffectClass.HARDLINK_IDENTITY_RELATION_CREATION
                    and target_resolved is not None
                ),
                "outcome": _FRAME_OUTCOME.get(event.outcome, "refused"),
            }
        )

    sources = trace.provenance.sources
    extractor = (
        f"{sources[0].source_id}@{sources[0].version}"
        if sources
        else trace.provenance.configuration_id
    )
    return {
        "format": FRAME_FORMAT,
        "schema_version": 1,
        "extractor": extractor,
        "extraction_root_absolute": trace.before.sandbox_root,
        "attempts": attempts,
    }
