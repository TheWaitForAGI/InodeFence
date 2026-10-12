"""Normalized transition keys; raw checkpoints remain separate evidence."""

from inodefence.model import (
    ChangeField,
    FilesystemTransition,
    IdentityRelationEffect,
    Region,
    RelationDeltaKind,
    TransitionFeedbackKey,
    TransitionObjectEffect,
    TransitionOrdinalClass,
    TransitionSequenceKey,
    TransitionSignature,
    TransitionTrace,
)
from inodefence.model.filesystem import is_extraction_path, path_region

_NAMESPACE_FIELDS = frozenset(
    (ChangeField.EXISTENCE, ChangeField.IDENTITY, ChangeField.OBJECT_TYPE)
)


def _ordinal_class(entry_index: int) -> TransitionOrdinalClass:
    if entry_index == 0:
        return TransitionOrdinalClass.FIRST
    if entry_index <= 3:
        return TransitionOrdinalClass.EARLY
    return TransitionOrdinalClass.LATE


def _object_key(
    item: TransitionObjectEffect,
) -> tuple[str, str, str, tuple[str, ...], bool]:
    return (
        item.region.value,
        item.before_type.value if item.before_type is not None else "",
        item.after_type.value if item.after_type is not None else "",
        tuple(field.value for field in item.fields),
        item.protected,
    )


def _relation_effects(transition: FilesystemTransition) -> tuple[IdentityRelationEffect, ...]:
    effects = []
    for kind, groups in (
        (RelationDeltaKind.CREATED, transition.identity_groups_created),
        (RelationDeltaKind.REMOVED, transition.identity_groups_removed),
    ):
        for group in groups:
            effects.append(
                IdentityRelationEffect(
                    kind,
                    tuple(sorted((path_region(path) for path in group), key=lambda r: r.value)),
                )
            )
    return tuple(sorted(effects))


def transition_signature(transition: FilesystemTransition) -> TransitionSignature:
    """Project raw deltas to relation classes without allocation/run identity.

    Exact paths, device/inode values, timestamps, runtime IDs, target versions,
    archive hashes and process timing are excluded. Repeated structural effects
    remain repeated tuple members so their multiplicity is not lost.
    """
    if not isinstance(transition, FilesystemTransition):
        raise ValueError("transition signature requires a FilesystemTransition")
    object_effects = tuple(
        sorted(
            (
                TransitionObjectEffect(
                    path_region(change.path),
                    change.before.object_type if change.before is not None else None,
                    change.after.object_type if change.after is not None else None,
                    change.fields,
                    change.path
                    in {effect.path for effect in transition.protected_external_effects},
                )
                for change in transition.changes
            ),
            key=_object_key,
        )
    )
    relation_effects = _relation_effects(transition)
    external_fields = tuple(sorted(effect.fields for effect in transition.external_effects))
    outside_namespace = any(
        not is_extraction_path(change.path) and bool(_NAMESPACE_FIELDS.intersection(change.fields))
        for change in transition.changes
    )
    identity_appeared = any(
        Region.EXTRACTION in effect.member_regions and Region.EXTERNAL in effect.member_regions
        for effect in relation_effects
        if effect.kind == RelationDeltaKind.CREATED
    )
    protected_effect = any(effect.protected for effect in object_effects)
    return TransitionSignature(
        1,
        transition.trigger.entry_type,
        _ordinal_class(transition.trigger.entry_index),
        object_effects,
        relation_effects,
        external_fields,
        outside_namespace,
        identity_appeared,
        protected_effect,
    )


def transition_key(transition: FilesystemTransition) -> TransitionFeedbackKey:
    return TransitionFeedbackKey(transition_signature(transition))


def transition_keys(trace: TransitionTrace) -> tuple[TransitionFeedbackKey, ...]:
    if not isinstance(trace, TransitionTrace):
        raise ValueError("transition keys require a TransitionTrace")
    return tuple(transition_key(transition) for transition in trace.transitions)


def transition_sequence_key(trace: TransitionTrace) -> TransitionSequenceKey:
    """Auxiliary ordered pattern; callers must not use prefixes as unbounded keys."""
    return TransitionSequenceKey(transition_keys(trace))
