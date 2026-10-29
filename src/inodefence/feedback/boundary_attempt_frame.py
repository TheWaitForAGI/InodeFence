"""Normalize an extractor's boundary-attempt frame into M3.1 effect feedback keys.

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
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    EntryType,
    ExternalResolveSignature,
    ObservedOperationType,
    OperationOutcome,
    Region,
)
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
