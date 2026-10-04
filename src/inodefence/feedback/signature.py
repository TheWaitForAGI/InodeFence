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
    """Normalize extraction/external state, excluding harness input artifacts.

    Raw snapshots remain complete evidence. Object and identity-group scope is
    identical so excluded harness names cannot leave dangling relations.
    Every link target is tagged: run:<suffix> for an absolute run-root prefix,
    literal:<raw target> otherwise. The disjoint tags avoid token collisions. This is text
    normalization, not symlink resolution; no target reachability is asserted.
    Absolute paths elsewhere retain their spelling. Identity numbers, timestamp
    values, uid/gid, nonregular nlink and sizes are excluded. External change
    labels still record metadata effects without their raw values.
    """
    scoped_objects = tuple(obj for obj in after.objects if obj.region != Region.HARNESS)
    nodes = []
    for obj in scoped_objects:
        target = obj.symlink_target
        if target is not None:
            if target == after.sandbox_root or target.startswith(after.sandbox_root + "/"):
                target = "run:" + target[len(after.sandbox_root) :]
            else:
                target = "literal:" + target
        nodes.append(
            SignatureObject(
                obj.path,
                obj.object_type,
                obj.mode,
                obj.st_nlink if obj.object_type == ObjectType.REGULAR else None,
                obj.size if obj.object_type == ObjectType.REGULAR else None,
                obj.content_digest,
                target,
            )
        )
    scoped_paths = {obj.path for obj in scoped_objects}
    groups = []
    for raw_group in after.identity_groups():
        group = tuple(path for path in raw_group if path in scoped_paths)
        if len(group) > 1:
            groups.append(group)
    effects = tuple(
        ExternalEffect(change.path, change.fields)
        for change in compare_states(before, after)
        if path_region(change.path) == Region.EXTERNAL
    )
    return StateSignature(3, tuple(nodes), tuple(sorted(groups)), effects, after.protected_paths)
