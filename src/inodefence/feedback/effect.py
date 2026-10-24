"""Finite effect feedback derivation; raw event order is never a novelty key."""

from collections import defaultdict
from pathlib import PurePosixPath

from inodefence.model import (
    BoundaryEscapeShape,
    CausalArchiveRelation,
    CausalMotifSignature,
    CausalRelationKind,
    EffectClass,
    EffectEventTrace,
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    EffectOrdinalClass,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EntryEffectSetSignature,
    FilesystemEffectEvent,
    IdentityRelationType,
    NormalizedEffectSignature,
    ObjectType,
    ObservedBoundaryEscapeSignature,
    Region,
    effect_is_realized,
)
from inodefence.model.filesystem import path_region


def _ordinal_class(entry_index: int) -> EffectOrdinalClass:
    if entry_index == 0:
        return EffectOrdinalClass.FIRST
    if entry_index <= 3:
        return EffectOrdinalClass.EARLY
    return EffectOrdinalClass.LATE


def effect_feedback_eligible(trace: EffectEventTrace) -> bool:
    """Initial policy: only complete, valid, successfully terminated traces contribute."""
    if not isinstance(trace, EffectEventTrace):
        raise ValueError("effect feedback eligibility requires an EffectEventTrace")
    return (
        trace.integrity_valid
        and trace.completeness == EffectStreamCompleteness.COMPLETE
        and trace.termination == EffectTargetTermination.SUCCESS
    )


def normalized_effect_signature(
    event: FilesystemEffectEvent,
    protected_paths: tuple[str, ...],
) -> NormalizedEffectSignature:
    """Project one realized effect without paths, identity values, time or source IDs."""
    if not isinstance(event, FilesystemEffectEvent) or not effect_is_realized(event):
        raise ValueError("normalized effect signature requires a realized effect event")
    if not isinstance(protected_paths, tuple) or protected_paths != tuple(
        sorted(set(protected_paths))
    ):
        raise ValueError("protected paths must be a unique sorted tuple")
    regions = tuple(path_region(path) for path in event.affected_paths)
    if event.effect_class == EffectClass.HARDLINK_IDENTITY_RELATION_CREATION:
        identity_relation = IdentityRelationType.SAME_OBJECT_CREATED
        identity_regions = regions
    elif event.effect_class == EffectClass.IDENTITY_RELATION_REMOVAL:
        identity_relation = IdentityRelationType.SAME_OBJECT_REMOVED
        identity_regions = regions
    else:
        identity_relation = IdentityRelationType.NONE
        identity_regions = ()
    return NormalizedEffectSignature(
        event.entry.entry_type,
        _ordinal_class(event.entry.entry_index),
        event.effect_class,
        regions,
        any(
            path in protected_paths and path_region(path) == Region.EXTERNAL
            for path in event.affected_paths
        ),
        identity_relation,
        identity_regions,
        event.outcome,
        event.evidence_strength,
    )


def _archive_relation(
    cause: FilesystemEffectEvent, consequence: FilesystemEffectEvent
) -> CausalArchiveRelation:
    if cause.entry.entry_index == consequence.entry.entry_index:
        return CausalArchiveRelation.SAME_ENTRY
    if cause.entry.entry_index < consequence.entry.entry_index:
        return CausalArchiveRelation.EARLIER_TO_LATER
    return CausalArchiveRelation.LATER_TO_EARLIER


def _signature_key(signature: NormalizedEffectSignature) -> tuple[object, ...]:
    return signature.sort_key()


def _feedback_key_sort_key(key: EffectFeedbackKey) -> tuple[object, ...]:
    signature = key.signature
    if isinstance(signature, NormalizedEffectSignature):
        value = (signature.sort_key(),)
    elif isinstance(signature, EntryEffectSetSignature):
        value = (tuple(effect.sort_key() for effect in signature.effects),)
    elif isinstance(signature, ObservedBoundaryEscapeSignature):
        value = (signature.sort_key(),)
    else:
        assert isinstance(signature, CausalMotifSignature)
        value = (
            signature.cause.sort_key(),
            signature.consequence.sort_key(),
            signature.relation_kind.value,
            signature.archive_relation.value,
        )
    return (key.kind.value, *value)


def effect_feedback_keys(trace: EffectEventTrace) -> tuple[EffectFeedbackKey, ...]:
    """Derive the unique finite key set from one feedback-eligible trace.

    Callback count and observed delivery order cannot change tuple membership or order.
    """
    if not isinstance(trace, EffectEventTrace):
        raise ValueError("effect feedback keys require an EffectEventTrace")
    if not effect_feedback_eligible(trace):
        return ()

    realized = tuple(event for event in trace.effect_events if effect_is_realized(event))
    signatures = {
        event: normalized_effect_signature(event, trace.before.protected_paths)
        for event in realized
    }
    keys: set[EffectFeedbackKey] = {
        EffectFeedbackKey(EffectFeedbackKeyKind.INDIVIDUAL_EFFECT, signature)
        for signature in signatures.values()
    }

    by_entry: dict[int, set[NormalizedEffectSignature]] = defaultdict(set)
    for event, signature in signatures.items():
        by_entry[event.entry.entry_index].add(signature)
    for entry_index, entry_signatures in by_entry.items():
        reference = trace.archive_entries[entry_index]
        relation = EntryEffectSetSignature(
            reference.entry_type,
            _ordinal_class(reference.entry_index),
            tuple(sorted(entry_signatures, key=_signature_key)),
        )
        keys.add(EffectFeedbackKey(EffectFeedbackKeyKind.ENTRY_EFFECT_SET, relation))

    by_completion = {event.completion_sequence: event for event in realized}
    by_start = {event.start_sequence: event for event in realized}
    motif_relations = {
        CausalRelationKind.HANDLE_PROVENANCE,
        CausalRelationKind.EXPLICIT_OPERATION_DEPENDENCY,
        CausalRelationKind.IDENTITY_PROVENANCE,
    }
    for edge in trace.causal_relations:
        if edge.kind not in motif_relations:
            continue
        cause = by_completion.get(edge.predecessor_sequence)
        consequence = by_start.get(edge.successor_sequence)
        if cause is None or consequence is None:
            continue
        motif = CausalMotifSignature(
            signatures[cause],
            signatures[consequence],
            edge.kind,
            _archive_relation(cause, consequence),
        )
        keys.add(EffectFeedbackKey(EffectFeedbackKeyKind.CAUSAL_MOTIF, motif))

    return tuple(sorted(keys, key=_feedback_key_sort_key))


def _boundary_escape_shape(object_path: str, symlink_target: str) -> BoundaryEscapeShape | None:
    """Classify an observed symlink's raw target by how it escapes the extraction root.

    Resolves the raw text against the symlink's own observed directory (both are
    observed state, never the archive input). Returns None when it stays inside
    `extract/`. Absolute targets are ABSOLUTE; otherwise the leading `..` depth is
    bucketed. No concrete path, protected object or CVE is referenced.
    """
    if not symlink_target:
        return None
    if symlink_target.startswith("/"):
        return BoundaryEscapeShape.ABSOLUTE
    resolved: list[str] = [part for part in PurePosixPath(object_path).parent.parts]
    for segment in symlink_target.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if resolved and resolved[-1] != "..":
                resolved.pop()
            else:
                resolved.append("..")
        else:
            resolved.append(segment)
    if resolved and resolved[0] == "extract":
        return None
    depth = 0
    for segment in symlink_target.split("/"):
        if segment == "..":
            depth += 1
        elif segment in ("", "."):
            continue
        else:
            break
    if depth <= 1:
        return BoundaryEscapeShape.PARENT_1
    if depth == 2:
        return BoundaryEscapeShape.PARENT_2
    return BoundaryEscapeShape.PARENT_3_PLUS


def observed_boundary_escape_keys(trace: EffectEventTrace) -> tuple[EffectFeedbackKey, ...]:
    """Observed boundary-approach keys: extraction symlinks whose target escapes root.

    Derived only from eligible (complete, valid, successful) traces and from observed
    objects (`ObjectSnapshot.symlink_target`), so it respects the same fail-closed gate
    as the other effect keys and never rewards an uncleanly-observed or rejected run.
    Target-agnostic: object kind, region and a bounded escape shape only.
    """
    if not isinstance(trace, EffectEventTrace):
        raise ValueError("observed boundary escape keys require an EffectEventTrace")
    if not effect_feedback_eligible(trace):
        return ()
    keys: set[EffectFeedbackKey] = set()
    for event in trace.effect_events:
        if not effect_is_realized(event) or event.effect_class != EffectClass.SYMLINK_CREATION:
            continue
        for item in event.object_evidence:
            obj = item.after.object
            if obj is None or obj.object_type != ObjectType.SYMLINK or obj.symlink_target is None:
                continue
            region = path_region(obj.path)
            if region != Region.EXTRACTION:
                continue
            shape = _boundary_escape_shape(obj.path, obj.symlink_target)
            if shape is None:
                continue
            keys.add(
                EffectFeedbackKey(
                    EffectFeedbackKeyKind.OBSERVED_BOUNDARY_ESCAPE,
                    ObservedBoundaryEscapeSignature(ObjectType.SYMLINK, region, shape),
                )
            )
    return tuple(sorted(keys, key=_feedback_key_sort_key))
