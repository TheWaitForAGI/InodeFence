"""Snapshot-supported C0/C1/C2 candidates; no input-pattern or exit-code gates."""

from inodefence.model import (
    ChangeField,
    ContractId,
    IdentityEvidence,
    Region,
    StateSnapshot,
    ViolationResult,
)
from inodefence.model.filesystem import path_region
from inodefence.observer import compare_states

_SNAPSHOT_LIMITS = (
    "Only persistent sandbox state is covered; transient operations are not traced.",
    "Device/inode equality is an observation-time proxy; inode reuse is not distinguishable.",
)


def evaluate_contracts(before: StateSnapshot, after: StateSnapshot) -> tuple[ViolationResult, ...]:
    """Apply the initial policy: all specified sentinels are protected.

    C0 covers external namespace evidence, excluding harness-owned paths. All
    unreserved paths outside extract/ count, including root-level escapes.
    A content change through an internal alias
    does not establish use of an external path; C2 records that effect separately.
    C1 forbids any post-state inside/sentinel identity sharing. The runner starts
    with an empty extraction directory and no permitted cross-boundary aliases.
    Target rejection, failure and success all use exactly the same observations.
    """
    changes = compare_states(before, after)
    if not before.protected_paths or any(
        before.get(path) is None for path in before.protected_paths
    ):
        raise ValueError("oracle requires initially existing protected sentinels")
    namespace_fields = {ChangeField.EXISTENCE, ChangeField.IDENTITY, ChangeField.OBJECT_TYPE}
    boundary_evidence = tuple(
        change
        for change in changes
        if path_region(change.path) == Region.EXTERNAL
        and namespace_fields.intersection(change.fields)
    )
    identity_evidence = []
    for obj in after.objects:
        if obj.region != Region.EXTRACTION:
            continue
        for path in after.protected_paths:
            sentinel = after.get(path)
            if sentinel is not None and obj.identity == sentinel.identity:
                identity_evidence.append(IdentityEvidence(obj.path, path, *obj.identity))
    effect_evidence = tuple(change for change in changes if change.path in before.protected_paths)
    return (
        ViolationResult(
            ContractId.C0,
            bool(boundary_evidence),
            boundary_evidence,
            "Persistent external namespace creation/deletion/replacement observed."
            if boundary_evidence
            else "No persistent external namespace change observed.",
            _SNAPSHOT_LIMITS
            + ("External path use without namespace changes requires operation tracing.",),
        ),
        ViolationResult(
            ContractId.C1,
            bool(identity_evidence),
            tuple(identity_evidence),
            "Extraction objects share lstat identity with protected sentinels."
            if identity_evidence
            else "No extraction/sentinel lstat identity sharing observed.",
            _SNAPSHOT_LIMITS + ("Symlink referent identity is not inferred from lstat identity.",),
        ),
        ViolationResult(
            ContractId.C2,
            bool(effect_evidence),
            effect_evidence,
            "Protected sentinel existence/content/identity/metadata changed."
            if effect_evidence
            else "No protected sentinel change observed.",
            _SNAPSHOT_LIMITS + ("atime is excluded because observation may itself read files.",),
        ),
    )
