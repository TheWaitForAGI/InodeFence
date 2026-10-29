"""Ordered boundary-approach gradient over intermediate transitions (additive).

These tests exercise the pure derivation only. The gradient is transition evidence,
never a C0/C1/C2 verdict; it reuses the same region/field classification as
`transition_signature`, is strictly additive (no oracle, fixture or N01 path is
touched) and is answer-agnostic (a protected/sentinel object never raises a rung).
Synthetic checkpoints follow the builders in `test_transition_model.py`.
"""

from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.feedback.transition_gradient import (
    _PROXIMITY_ORDER,
    max_proximity,
    proximity_rank,
    trace_proximity,
    transition_proximities,
    transition_proximity,
)
from inodefence.model import (
    ArchiveEntryReference,
    EntryCheckpoint,
    EntryType,
    ObjectSnapshot,
    ObjectType,
    ObservationKind,
    ObservationPoint,
    SnapshotPhase,
    StateSnapshot,
    TraceCompleteness,
    TraceTermination,
    TransitionBoundaryProximity,
    TransitionTrace,
    derive_transition,
)

_P = TransitionBoundaryProximity


def _digest(value: bytes = b"x") -> str:
    return sha256(value).hexdigest()


def _object(
    path: str,
    *,
    kind: ObjectType = ObjectType.REGULAR,
    dev: int = 1,
    ino: int = 1,
    nlink: int = 1,
    mode: int = 0o644,
    content: bytes = b"x",
    target: str | None = None,
) -> ObjectSnapshot:
    return ObjectSnapshot(
        path,
        kind,
        dev,
        ino,
        nlink,
        mode,
        1,
        1000,
        1000,
        1,
        1,
        target,
        _digest(content) if kind == ObjectType.REGULAR else None,
    )


def _checkpoint(
    index: int,
    objects: tuple[ObjectSnapshot, ...],
    entry: ArchiveEntryReference | None = None,
    *,
    protected: tuple[str, ...] = ("outside/sentinel",),
) -> EntryCheckpoint:
    point = ObservationPoint(
        ObservationKind.BEFORE if entry is None else ObservationKind.ENTRY_BOUNDARY,
        entry,
    )
    return EntryCheckpoint(
        index,
        point,
        "/var/lib/inodefence/core-run-gradient",
        tuple(sorted(objects, key=lambda obj: obj.path)),
        protected,
        10,
        15,
    )


def _after(checkpoint: EntryCheckpoint) -> StateSnapshot:
    return StateSnapshot(
        checkpoint.sandbox_root,
        SnapshotPhase.AFTER,
        checkpoint.objects,
        checkpoint.protected_paths,
    )


_SENTINEL = _object("outside/sentinel", ino=90)
_ENTRY = ArchiveEntryReference(0, "x", EntryType.REGULAR, None)


def _transition(before_objects, after_objects, entry=_ENTRY):
    before = _checkpoint(0, before_objects)
    current = _checkpoint(1, after_objects, entry)
    return derive_transition(before, current, 0)


# --- rank vocabulary -------------------------------------------------------


def test_proximity_order_covers_every_member_once_ascending() -> None:
    assert set(_PROXIMITY_ORDER) == set(TransitionBoundaryProximity)
    assert len(_PROXIMITY_ORDER) == len(set(_PROXIMITY_ORDER))
    assert _PROXIMITY_ORDER == (
        _P.NONE,
        _P.EXTERNAL_NAMESPACE,
        _P.CROSS_BOUNDARY_IDENTITY,
    )


def test_rank_is_monotone_and_bounded() -> None:
    ranks = [proximity_rank(member) for member in _PROXIMITY_ORDER]
    assert ranks == [0, 1, 2]
    assert proximity_rank(_P.CROSS_BOUNDARY_IDENTITY) > proximity_rank(_P.EXTERNAL_NAMESPACE)
    with pytest.raises(ValueError, match="TransitionBoundaryProximity"):
        proximity_rank("cross_boundary_identity")  # type: ignore[arg-type]


def test_max_proximity_picks_highest_rank_and_defaults_to_none() -> None:
    mixed = (_P.EXTERNAL_NAMESPACE, _P.CROSS_BOUNDARY_IDENTITY, _P.NONE)
    assert max_proximity(mixed) == _P.CROSS_BOUNDARY_IDENTITY
    assert max_proximity(()) == _P.NONE


# --- single-transition rungs ----------------------------------------------


def test_extraction_only_transition_is_none() -> None:
    # A new extraction object plus a content change, all inside extract/.
    before = (_SENTINEL, _object("extract/a", ino=10))
    after = (_SENTINEL, _object("extract/a", ino=10, content=b"new"), _object("extract/b", ino=11))
    assert transition_proximity(_transition(before, after)) == _P.NONE


def test_external_namespace_rung_for_object_created_outside_root() -> None:
    # A new EXTERNAL object appears: existence change outside extract/, no identity.
    before = (_SENTINEL, _object("extract/a", ino=10))
    after = (_SENTINEL, _object("extract/a", ino=10), _object("outside/newfile", ino=50))
    assert transition_proximity(_transition(before, after)) == _P.EXTERNAL_NAMESPACE


def test_cross_boundary_identity_outranks_external_namespace() -> None:
    # extract/a comes to share identity with a NON-protected external object.
    before = (_SENTINEL, _object("extract/a", ino=10), _object("outside/other", ino=50))
    after = (
        _SENTINEL,
        _object("extract/a", ino=50, nlink=2),
        _object("outside/other", ino=50, nlink=2),
    )
    transition = _transition(before, after)
    assert transition.identity_groups_created == (("extract/a", "outside/other"),)
    assert transition_proximity(transition) == _P.CROSS_BOUNDARY_IDENTITY


def test_rung_is_target_agnostic_across_concrete_paths_and_inodes() -> None:
    # The same rung is reached regardless of the exact external path or inode value.
    def cross(external_path: str, ino: int):
        before = (_SENTINEL, _object("extract/a", ino=10), _object(external_path, ino=ino))
        after = (
            _SENTINEL,
            _object("extract/a", ino=ino, nlink=2),
            _object(external_path, ino=ino, nlink=2),
        )
        return transition_proximity(_transition(before, after))

    assert cross("outside/alpha", 50) == _P.CROSS_BOUNDARY_IDENTITY
    assert cross("outside/beta/deep", 77) == _P.CROSS_BOUNDARY_IDENTITY


def test_rung_is_answer_agnostic_protectedness_never_raises_it() -> None:
    # A content-only effect on the DECLARED PROTECTED sentinel, via an internal alias,
    # with no identity relation and no namespace change -> the gradient stays NONE. The
    # gradient must not reward touching the protected object (C2 is the oracle's job).
    before = (_object("outside/sentinel", ino=90, content=b"old"), _object("extract/a", ino=10))
    after = (_object("outside/sentinel", ino=90, content=b"new"), _object("extract/a", ino=10))
    content_only = _transition(before, after)
    assert content_only.protected_external_effects  # the oracle would see C2 here
    assert transition_proximity(content_only) == _P.NONE

    # And when the external member of a cross-boundary alias happens to be the protected
    # sentinel, the rung is still CROSS_BOUNDARY_IDENTITY -- not elevated by protectedness.
    before2 = (_object("outside/sentinel", ino=90), _object("extract/a", ino=10))
    after2 = (
        _object("outside/sentinel", ino=90, nlink=2),
        _object("extract/a", ino=90, nlink=2),
    )
    aliased = _transition(before2, after2)
    assert aliased.identity_groups_created == (("extract/a", "outside/sentinel"),)
    assert transition_proximity(aliased) == _P.CROSS_BOUNDARY_IDENTITY


def test_transition_proximity_rejects_non_transition() -> None:
    with pytest.raises(ValueError, match="FilesystemTransition"):
        transition_proximity("not-a-transition")  # type: ignore[arg-type]


# --- trace-level gradient --------------------------------------------------


def _gradient_trace() -> TransitionTrace:
    """A three-entry trace whose intermediate rungs climb NONE -> EXTERNAL -> CROSS."""
    cp0 = _checkpoint(0, (_SENTINEL, _object("extract/a", ino=10)))
    # entry 0: add an extraction object only -> NONE
    cp1 = _checkpoint(
        1,
        (_SENTINEL, _object("extract/a", ino=10), _object("extract/b", ino=11)),
        ArchiveEntryReference(0, "a", EntryType.REGULAR, None),
    )
    # entry 1: create a NON-protected external object -> EXTERNAL_NAMESPACE
    cp2 = _checkpoint(
        2,
        (
            _SENTINEL,
            _object("extract/a", ino=10),
            _object("extract/b", ino=11),
            _object("outside/newfile", ino=50),
        ),
        ArchiveEntryReference(1, "b", EntryType.REGULAR, None),
    )
    # entry 2: extract/b comes to alias that external object -> CROSS_BOUNDARY_IDENTITY
    cp3 = _checkpoint(
        3,
        (
            _SENTINEL,
            _object("extract/a", ino=10),
            _object("extract/b", ino=50, nlink=2),
            _object("outside/newfile", ino=50, nlink=2),
        ),
        ArchiveEntryReference(2, "c", EntryType.HARDLINK, "b"),
    )
    checkpoints = (cp0, cp1, cp2, cp3)
    transitions = tuple(derive_transition(checkpoints[i], checkpoints[i + 1], i) for i in range(3))
    return TransitionTrace(
        3,
        checkpoints,
        transitions,
        _after(cp3),
        TraceCompleteness.COMPLETE,
        TraceTermination.SUCCESS,
    )


def test_trace_proximities_are_ordered_and_climb() -> None:
    trace = _gradient_trace()
    assert transition_proximities(trace) == (
        _P.NONE,
        _P.EXTERNAL_NAMESPACE,
        _P.CROSS_BOUNDARY_IDENTITY,
    )


def test_trace_proximity_is_the_closest_rung_ever_reached() -> None:
    assert trace_proximity(_gradient_trace()) == _P.CROSS_BOUNDARY_IDENTITY


def test_trace_proximity_rejects_non_trace() -> None:
    with pytest.raises(ValueError, match="TransitionTrace"):
        trace_proximity(_gradient_trace().transitions)  # type: ignore[arg-type]


def test_single_entry_trace_with_no_boundary_movement_is_none() -> None:
    cp0 = _checkpoint(0, (_SENTINEL, _object("extract/a", ino=10)))
    cp1 = _checkpoint(
        1,
        (_SENTINEL, _object("extract/a", ino=10, content=b"new")),
        ArchiveEntryReference(0, "a", EntryType.REGULAR, None),
    )
    trace = TransitionTrace(
        1,
        (cp0, cp1),
        (derive_transition(cp0, cp1, 0),),
        _after(cp1),
        TraceCompleteness.COMPLETE,
        TraceTermination.SUCCESS,
    )
    assert trace_proximity(trace) == _P.NONE
    assert transition_proximities(trace) == (_P.NONE,)


def test_replace_keeps_derivation_stable() -> None:
    # Guards that the rung is a function of the transition's evidence, not identity.
    transition = _gradient_trace().transitions[2]
    assert transition_proximity(replace(transition)) == transition_proximity(transition)
