"""Ordered boundary-approach gradient over intermediate transitions.

The normalized `transition_signature` records three *unordered* structural flags
(outside-namespace, internal/external identity, protected effect). Novelty
admission over those flags answers only "is this transition class new?"; it gives
adaptive search no way to say one intermediate sequence got *closer* to a boundary
violation than another. The final BEFORE/AFTER C0/C1/C2 oracle is likewise
all-or-nothing, so a refused escaping attempt that never realizes a violation looks
identical to an input that never approached the boundary at all.

This module derives a single comparable rung per transition, and the closest rung a
whole trace ever reached, so the effect-adaptive scheduler can reward *approaching*
the boundary -- the same gradient the effect path already gets from
`boundary_attempt_keys`/`external_resolve_keys`, but on the richer per-entry
transition signal a native entry-completion boundary exposes.

Everything here is strictly additive and target-agnostic. It reuses the exact
region/field classification already proven in `transition_signature`, derives a rung
only from `Region` classes, `ChangeField` categories and the declared-protected
marker in the generic model, and reads no concrete path, raw device/inode value,
timestamp, sentinel, CVE or PoC. A rung is transition evidence, never a C0/C1/C2
verdict and never a vulnerability. The caller owns trace eligibility (completeness
and termination); these functions assume nothing about them, exactly like the
effect-path attempt keys.
"""

from inodefence.model import (
    ChangeField,
    FilesystemTransition,
    Region,
    TransitionBoundaryProximity,
    TransitionTrace,
)
from inodefence.model.filesystem import is_extraction_path, path_region

_NAMESPACE_FIELDS = frozenset(
    (ChangeField.EXISTENCE, ChangeField.IDENTITY, ChangeField.OBJECT_TYPE)
)

# Canonical ascending-severity order; rank is the index into this tuple. Declared
# explicitly (not taken from enum member order) so the gradient is robust to a later
# reordering of the enum definition. A test asserts it covers every member once.
_PROXIMITY_ORDER: tuple[TransitionBoundaryProximity, ...] = (
    TransitionBoundaryProximity.NONE,
    TransitionBoundaryProximity.EXTERNAL_NAMESPACE,
    TransitionBoundaryProximity.CROSS_BOUNDARY_IDENTITY,
    TransitionBoundaryProximity.PROTECTED_EFFECT,
)


def proximity_rank(proximity: TransitionBoundaryProximity) -> int:
    """Return the bounded integer rank (0..3) of a proximity rung.

    This is the comparable scalar the gradient contributes: a higher rank means a
    more boundary-committed intermediate observation, nothing more.
    """
    if not isinstance(proximity, TransitionBoundaryProximity):
        raise ValueError("proximity rank requires a TransitionBoundaryProximity")
    return _PROXIMITY_ORDER.index(proximity)


def max_proximity(
    proximities: tuple[TransitionBoundaryProximity, ...],
) -> TransitionBoundaryProximity:
    """Return the highest-rank rung in an iterable, or NONE when empty."""
    return max(
        proximities,
        key=proximity_rank,
        default=TransitionBoundaryProximity.NONE,
    )


def _has_cross_boundary_identity(transition: FilesystemTransition) -> bool:
    """A newly created identity group whose members span EXTRACTION and EXTERNAL.

    Mirrors the `internal_external_identity_appeared` flag in `transition_signature`:
    region membership of the created group's paths only, no raw inode value.
    """
    for group in transition.identity_groups_created:
        regions = {path_region(path) for path in group}
        if Region.EXTRACTION in regions and Region.EXTERNAL in regions:
            return True
    return False


def _has_external_namespace(transition: FilesystemTransition) -> bool:
    """A namespace field changed on a path outside the extraction root.

    Mirrors the `outside_namespace_transition` flag in `transition_signature`:
    region-based (HARNESS or EXTERNAL, matching C0's scope), target-agnostic.
    """
    return any(
        not is_extraction_path(change.path) and bool(_NAMESPACE_FIELDS.intersection(change.fields))
        for change in transition.changes
    )


def transition_proximity(transition: FilesystemTransition) -> TransitionBoundaryProximity:
    """The maximum-severity boundary-approach rung reached by one transition.

    Checked from the highest rung down, returning the first condition that holds, so
    the result is the greatest rung present (the rungs are not a strict nesting). A
    protected external effect is the realized-C2 shape; a cross-boundary identity
    relation is the C1 shape against any external object; an external namespace change
    is the C0 shape. Returns NONE for extraction-only or empty transitions.
    """
    if not isinstance(transition, FilesystemTransition):
        raise ValueError("transition proximity requires a FilesystemTransition")
    if transition.protected_external_effects:
        return TransitionBoundaryProximity.PROTECTED_EFFECT
    if _has_cross_boundary_identity(transition):
        return TransitionBoundaryProximity.CROSS_BOUNDARY_IDENTITY
    if _has_external_namespace(transition):
        return TransitionBoundaryProximity.EXTERNAL_NAMESPACE
    return TransitionBoundaryProximity.NONE


def transition_proximities(
    trace: TransitionTrace,
) -> tuple[TransitionBoundaryProximity, ...]:
    """Per-transition rungs in archive order (auxiliary ordered evidence).

    The ordered sequence is diagnostic; v-next admission/reward should use the single
    `trace_proximity` scalar, not a growing prefix, to keep the key space finite.
    """
    if not isinstance(trace, TransitionTrace):
        raise ValueError("transition proximities require a TransitionTrace")
    return tuple(transition_proximity(transition) for transition in trace.transitions)


def trace_proximity(trace: TransitionTrace) -> TransitionBoundaryProximity:
    """The closest the whole intermediate sequence ever got: max rung over transitions.

    This is the comparable gradient value for the trace. A trace whose completed
    transitions never leave the extraction root is NONE even if its final AFTER
    snapshot later shows an external effect; the gradient measures the observed
    intermediate approach, not the final state (which the C0/C1/C2 oracle owns).
    """
    return max_proximity(transition_proximities(trace))
