"""Initial stable state normalization, with no corpus or selection policy."""

from inodefence.model import (
    ExternalEffect,
    ObjectType,
    Region,
    SignatureObject,
    StateSignature,
    StateSnapshot,
)
from inodefence.model.filesystem import path_region
from inodefence.observer import compare_states


def state_signature(before: StateSnapshot, after: StateSnapshot) -> StateSignature:
    """Represent paths, same-object groups, textual links and external changes.

    Absolute link text under this run gets a literal $RUN prefix. This is text
    normalization, not symlink resolution; no target reachability is asserted.
    Absolute paths elsewhere retain their spelling. Identity numbers, timestamp
    values, uid/gid and allocation-dependent directory sizes are excluded.
    """
    nodes = []
    for obj in after.objects:
        target = obj.symlink_target
        if target is not None and (
            target == after.sandbox_root or target.startswith(after.sandbox_root + "/")
        ):
            target = "$RUN" + target[len(after.sandbox_root) :]
        nodes.append(
            SignatureObject(
                obj.path,
                obj.object_type,
                obj.mode,
                obj.st_nlink,
                obj.size if obj.object_type == ObjectType.REGULAR else None,
                obj.content_digest,
                target,
            )
        )
    effects = tuple(
        ExternalEffect(change.path, change.fields)
        for change in compare_states(before, after)
        if path_region(change.path) == Region.EXTERNAL
    )
    return StateSignature(1, tuple(nodes), after.identity_groups(), effects, after.protected_paths)
