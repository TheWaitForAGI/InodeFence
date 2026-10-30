"""The v1 boundary-attempt frame normalizes to the expected M3.1 feedback keys.

Pins ``feedback.boundary_attempt_frame.frame_boundary_attempt_keys``: the mapping from an
``inodefence-boundary-attempt-v1`` frame (what a generality extractor emits) to the existing
M3.1 ``BoundaryAttemptSignature`` / ``ExternalResolveSignature`` feedback keys the gradient
consumes. Reads only committed evidence + in-memory synthetic frames -- no Docker -- so it runs
in ``make check``. Additive; no oracle/model/effect change.
"""

import json
from pathlib import Path

from inodefence.feedback.boundary_attempt_frame import FRAME_FORMAT, frame_boundary_attempt_keys
from inodefence.feedback.effect import _feedback_key_sort_key
from inodefence.model import (
    BoundaryAttemptShape,
    BoundaryAttemptSignature,
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    EntryType,
    ExternalResolveSignature,
    ObservedOperationType,
    OperationOutcome,
    Region,
)

_COMMITTED_FRAME = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "experiments"
        / "repro"
        / "evidence"
        / "decompress_entry_effect_feasibility.json"
    ).read_text(encoding="utf-8")
)["frame"]


def _attempt(operation, target_raw, target_region, outcome="created"):
    return {
        "operation": operation,
        "created_path": "/work/extract/x",
        "created_region": "extraction",
        "target_raw": target_raw,
        "target_resolved_absolute": "/work/outside/x" if target_region != "n/a" else None,
        "target_region": target_region,
        "aliases_external_object": False,
        "outcome": outcome,
    }


def _frame(*attempts):
    return {
        "format": FRAME_FORMAT,
        "schema_version": 1,
        "extractor": "decompress@4.2.1",
        "extraction_root_absolute": "/work/extract",
        "attempts": list(attempts),
    }


def _resolve(operation):
    return EffectFeedbackKey(
        EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE,
        ExternalResolveSignature(operation, Region.EXTERNAL),
    )


def _attempt_key(entry_type, outcome, shape, region=Region.EXTERNAL):
    return EffectFeedbackKey(
        EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT,
        BoundaryAttemptSignature(entry_type, region, outcome, shape),
    )


def test_committed_decompress_frame_maps_to_expected_m31_keys() -> None:
    keys = set(frame_boundary_attempt_keys(_COMMITTED_FRAME))
    assert keys == {
        # CWD-relative hardlink (no lexical escape) -> region key only.
        _resolve(ObservedOperationType.LINK),
        # Lexical "../" symlink -> both the lexical attempt key and the region key.
        _attempt_key(EntryType.SYMLINK, OperationOutcome.SUCCEEDED, BoundaryAttemptShape.PARENT_1),
        _resolve(ObservedOperationType.SYMLINK),
    }


def test_cwd_relative_hardlink_has_no_lexical_attempt_key() -> None:
    # The decompress hardlink escape is CWD-relative, so it forms only the region-based key --
    # exactly the case OBSERVED_EXTERNAL_RESOLVE exists for.
    keys = frame_boundary_attempt_keys(
        _frame(_attempt("hardlink", "outside/sentinel.txt", "external"))
    )
    assert set(keys) == {_resolve(ObservedOperationType.LINK)}


def test_escape_shapes_and_outcomes_are_bucketed() -> None:
    keys = set(
        frame_boundary_attempt_keys(
            _frame(
                _attempt("hardlink", "/etc/passwd", "external", outcome="refused"),
                _attempt("symlink", "../../a", "harness", outcome="io_error"),
                _attempt("symlink", "../../../../a", "external"),
            )
        )
    )
    assert (
        _attempt_key(EntryType.HARDLINK, OperationOutcome.INVALID, BoundaryAttemptShape.ABSOLUTE)
        in keys
    )
    assert (
        _attempt_key(
            EntryType.SYMLINK,
            OperationOutcome.OTHER_ERROR,
            BoundaryAttemptShape.PARENT_2,
            Region.HARNESS,
        )
        in keys
    )
    assert (
        _attempt_key(
            EntryType.SYMLINK, OperationOutcome.SUCCEEDED, BoundaryAttemptShape.PARENT_3_PLUS
        )
        in keys
    )
    # Harness attempt: lexical key only (external-resolve is EXTERNAL-region only).
    assert _resolve(ObservedOperationType.SYMLINK) in keys  # from the parent_3 external symlink
    harness_resolves = [
        k for k in keys if k.kind == EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE
    ]
    assert all(
        isinstance(k.signature, ExternalResolveSignature)
        and k.signature.resolved_region == Region.EXTERNAL
        for k in harness_resolves
    )


def test_non_boundary_and_extraction_attempts_yield_no_keys() -> None:
    frame = _frame(
        _attempt("regular", None, "n/a"),
        _attempt("hardlink", "a.txt", "extraction"),
        {
            "operation": "symlink",
            "created_path": "/work/extract/s",
            "created_region": "extraction",
            "target_raw": "inside/ok.txt",
            "target_resolved_absolute": "/work/extract/inside/ok.txt",
            "target_region": "extraction",
            "aliases_external_object": False,
            "outcome": "created",
        },
    )
    assert frame_boundary_attempt_keys(frame) == ()


def test_keys_are_sorted_and_deduplicated() -> None:
    frame = _frame(
        _attempt("symlink", "../a", "external"),
        _attempt("symlink", "../a", "external"),  # duplicate -> one key pair
    )
    keys = frame_boundary_attempt_keys(frame)
    assert len(keys) == 2  # one BOUNDARY_ESCAPE_ATTEMPT + one OBSERVED_EXTERNAL_RESOLVE
    assert list(keys) == sorted(keys, key=_feedback_key_sort_key)


def test_malformed_frame_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="inodefence-boundary-attempt-v1"):
        frame_boundary_attempt_keys({"format": "something-else", "attempts": []})
    with pytest.raises(ValueError):
        frame_boundary_attempt_keys({"format": FRAME_FORMAT, "attempts": "not-a-list"})
