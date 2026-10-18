"""Derive v3 namespace-rebinding composites and additive finite feedback."""

from inodefence.model import (
    EffectClass,
    EffectEventTrace,
    EffectFeedbackProjectionV3,
    EffectOrdinalClass,
    EffectPathEvidence,
    EffectStreamCompleteness,
    EffectTargetTermination,
    FilesystemEffectEvent,
    NamespaceRebindingFeedbackKey,
    NamespaceRebindingSequence,
    NamespaceRebindingSignature,
    RebindingCreationKind,
    RebindingEvidenceLevel,
    RebindingFeedbackKeyKind,
    RebindingOperationDependency,
    Region,
    effect_is_realized,
)
from inodefence.model.filesystem import path_region

from .effect import effect_feedback_keys


def _ordinal_class(entry_index: int) -> EffectOrdinalClass:
    if entry_index == 0:
        return EffectOrdinalClass.FIRST
    if entry_index <= 3:
        return EffectOrdinalClass.EARLY
    return EffectOrdinalClass.LATE


def _creation_destination(
    event: FilesystemEffectEvent,
) -> tuple[str, EffectPathEvidence, RebindingCreationKind, str | None] | None:
    if event.effect_class == EffectClass.NAMESPACE_CREATION and len(event.object_evidence) == 1:
        evidence = event.object_evidence[0]
        return evidence.path, evidence, RebindingCreationKind.OBJECT, None
    if event.effect_class == EffectClass.SYMLINK_CREATION and len(event.object_evidence) == 1:
        evidence = event.object_evidence[0]
        return evidence.path, evidence, RebindingCreationKind.SYMLINK, None
    if (
        event.effect_class == EffectClass.HARDLINK_IDENTITY_RELATION_CREATION
        and len(event.object_evidence) == 2
    ):
        source, destination = event.object_evidence
        return (
            destination.path,
            destination,
            RebindingCreationKind.HARDLINK_RELATION,
            source.path,
        )
    return None


_BINDING_CLASSES = {
    EffectClass.NAMESPACE_CREATION,
    EffectClass.NAMESPACE_REMOVAL,
    EffectClass.NAMESPACE_REPLACEMENT,
    EffectClass.SYMLINK_CREATION,
    EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
    EffectClass.IDENTITY_RELATION_REMOVAL,
}


def _touches_path(event: FilesystemEffectEvent, path: str) -> bool:
    return event.effect_class in _BINDING_CLASSES and path in event.affected_paths


def _has_intervening_binding(
    trace: EffectEventTrace,
    removal: FilesystemEffectEvent,
    creation: FilesystemEffectEvent,
    path: str,
) -> bool:
    for event in trace.effect_events:
        if event.correlation_id in (removal.correlation_id, creation.correlation_id) or not (
            effect_is_realized(event)
        ):
            continue
        if not _touches_path(event, path):
            continue
        if (
            event.start_sequence < creation.start_sequence
            and event.completion_sequence > removal.completion_sequence
        ):
            return True
    return False


def derive_namespace_rebinding_sequences(
    trace: EffectEventTrace,
    dependencies: tuple[RebindingOperationDependency, ...],
) -> tuple[NamespaceRebindingSequence, ...]:
    """Derive only direct, same-entry/path, conflict-free verified chains."""
    if not isinstance(trace, EffectEventTrace):
        raise ValueError("rebinding derivation requires an EffectEventTrace")
    if not isinstance(dependencies, tuple) or not all(
        isinstance(dependency, RebindingOperationDependency) for dependency in dependencies
    ):
        raise ValueError("rebinding derivation requires typed dependencies")
    if (
        not trace.integrity_valid
        or trace.completeness != EffectStreamCompleteness.COMPLETE
        or trace.termination != EffectTargetTermination.SUCCESS
    ):
        return ()
    if len({dependency.dependency_id for dependency in dependencies}) != len(dependencies):
        raise ValueError("rebinding dependency IDs must be unique")
    endpoint_pairs = {
        (dependency.predecessor_correlation_id, dependency.successor_correlation_id)
        for dependency in dependencies
    }
    if len(endpoint_pairs) != len(dependencies):
        raise ValueError("rebinding dependency endpoint pairs must be unique")
    raw_records = {
        (dependency.source_id, dependency.raw_evidence.record_id) for dependency in dependencies
    }
    if len(raw_records) != len(dependencies):
        raise ValueError("rebinding dependency raw references must be unique")
    if any(
        dependency.v2_raw_stream_sha256 != trace.provenance.raw_stream_sha256
        for dependency in dependencies
    ):
        raise ValueError("rebinding dependency refers to a different v2 raw stream")

    by_correlation = {event.correlation_id: event for event in trace.effect_events}
    if len(by_correlation) != len(trace.effect_events):
        raise ValueError("rebinding derivation requires unique operation correlations")
    sequences: list[NamespaceRebindingSequence] = []
    for dependency in dependencies:
        removal = by_correlation.get(dependency.predecessor_correlation_id)
        creation = by_correlation.get(dependency.successor_correlation_id)
        if removal is None or creation is None:
            raise ValueError("rebinding dependency references an unknown operation")
        if (
            dependency.predecessor_completion_sequence != removal.completion_sequence
            or dependency.successor_start_sequence != creation.start_sequence
        ):
            raise ValueError("rebinding dependency sequence differs from its operations")
        if dependency.kind.value != "producer_branch_continuation":
            raise ValueError("rebinding requires producer branch-continuation provenance")
        if removal.completion_sequence >= creation.start_sequence:
            raise ValueError("rebinding endpoint operations are not globally ordered")

        if (
            removal.entry != creation.entry
            or removal.effect_class != EffectClass.NAMESPACE_REMOVAL
            or not effect_is_realized(removal)
            or len(removal.object_evidence) != 1
        ):
            continue
        creation_candidate = _creation_destination(creation)
        if creation_candidate is None or not effect_is_realized(creation):
            continue
        destination_path, creation_evidence, creation_kind, hardlink_source = creation_candidate
        removal_evidence = removal.object_evidence[0]
        if removal_evidence.path != destination_path:
            continue
        if (
            removal_evidence.before.object is None
            or removal_evidence.after.object is not None
            or creation_evidence.before.object is not None
            or creation_evidence.after.object is None
        ):
            continue
        if _has_intervening_binding(trace, removal, creation, destination_path):
            continue
        sequences.append(
            NamespaceRebindingSequence(
                removal.entry,
                destination_path,
                removal,
                creation,
                removal_evidence,
                creation_evidence,
                dependency,
                creation_kind,
                hardlink_source,
            )
        )
    return tuple(
        sorted(
            sequences,
            key=lambda item: (
                item.removal.completion_sequence,
                item.creation.start_sequence,
                item.dependency.dependency_id,
            ),
        )
    )


def namespace_rebinding_signature(
    sequence: NamespaceRebindingSequence,
    protected_paths: tuple[str, ...],
) -> NamespaceRebindingSignature:
    if not isinstance(sequence, NamespaceRebindingSequence):
        raise ValueError("rebinding signature requires a verified sequence")
    if not isinstance(protected_paths, tuple) or protected_paths != tuple(
        sorted(set(protected_paths))
    ):
        raise ValueError("protected paths must be a unique sorted tuple")
    destination_region = path_region(sequence.destination_path)
    source_region = (
        None
        if sequence.hardlink_source_path is None
        else path_region(sequence.hardlink_source_path)
    )
    return NamespaceRebindingSignature(
        sequence.entry.entry_type,
        _ordinal_class(sequence.entry.entry_index),
        destination_region,
        sequence.destination_path in protected_paths and destination_region == Region.EXTERNAL,
        sequence.before_object_type,
        sequence.after_object_type,
        sequence.creation_kind,
        source_region,
        RebindingEvidenceLevel.DEPENDENCY_VERIFIED_STATE_CHANGE_VERIFIED,
    )


def effect_feedback_projection_v3(
    trace: EffectEventTrace,
    dependencies: tuple[RebindingOperationDependency, ...],
) -> EffectFeedbackProjectionV3:
    """Return unchanged v2 keys plus unique finite rebinding keys."""
    v2_keys = effect_feedback_keys(trace)
    sequences = derive_namespace_rebinding_sequences(trace, dependencies)
    signatures = {
        namespace_rebinding_signature(sequence, trace.before.protected_paths)
        for sequence in sequences
    }
    rebinding_keys = tuple(
        NamespaceRebindingFeedbackKey(
            RebindingFeedbackKeyKind.NAMESPACE_REBINDING_SEQUENCE, signature
        )
        for signature in sorted(signatures, key=lambda item: item.sort_key())
    )
    return EffectFeedbackProjectionV3(v2_keys, rebinding_keys)
