"""Snapshot-supported C0/C1/C2 candidates; no input-pattern or exit-code gates."""

from inodefence.model import (
    BoundaryIdentityEvidence,
    ChangeField,
    ContractId,
    IdentityEvidence,
    Region,
    StateChange,
    StateSnapshot,
    ViolationResult,
)
from inodefence.model.filesystem import is_extraction_path
from inodefence.observer import compare_states

_SNAPSHOT_LIMITS = (
    "Only persistent sandbox state is covered; transient operations are not traced.",
    "Device/inode equality is an observation-time proxy; inode reuse is not distinguishable.",
)
_C0_NAMESPACE_FIELDS = frozenset(
    (ChangeField.EXISTENCE, ChangeField.IDENTITY, ChangeField.OBJECT_TYPE)
)


def _is_c0_namespace_transition(change: StateChange) -> bool:
    """Check boundary evidence regardless of the path's normalization role.

    Content/metadata-only changes do not establish direct external path use.
    HARNESS is a signature scope, not permission to mutate the namespace.
    """
    return not is_extraction_path(change.path) and bool(
        _C0_NAMESPACE_FIELDS.intersection(change.fields)
    )


def evaluate_contracts(before: StateSnapshot, after: StateSnapshot) -> tuple[ViolationResult, ...]:
    """Apply the initial policy: all specified sentinels are protected.

    C0 covers namespace transitions outside extract/, including HARNESS paths.
    All setup must precede BEFORE; harness bookkeeping must follow AFTER.
    Snapshots cannot attribute actors if that lifecycle contract is violated.
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
    boundary_evidence = tuple(change for change in changes if _is_c0_namespace_transition(change))
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
            "Persistent namespace creation/deletion/replacement outside extraction root observed."
            if boundary_evidence
            else "No persistent namespace change outside extraction root observed.",
            _SNAPSHOT_LIMITS
            + (
                "External path use without namespace changes requires operation tracing.",
                "Snapshots do not identify actors; target attribution requires no harness "
                "namespace writes between captures.",
            ),
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


def generalized_identity_confinement(
    after: StateSnapshot,
) -> tuple[BoundaryIdentityEvidence, ...]:
    """Additive C1 generalization: extraction objects aliasing any outside object.

    The initial C1 in evaluate_contracts compares extraction objects only with
    the protected external sentinels. This detector reports every extraction
    object whose post-state (st_dev, st_ino) is shared with any non-extraction
    object, including harness objects such as archive/input.tar and non-sentinel
    external objects. It is strictly additive: it does not call or modify
    evaluate_contracts and never changes the C0/C1/C2 ViolationResult tuple, so
    callers consume this evidence independently of the existing verdict.

    Same-region (extraction/extraction) aliasing is intentionally excluded: that
    is benign internal sharing, not a boundary escape. Device/inode equality is
    an observation-time proxy and does not distinguish inode reuse, matching the
    C1 limitation. Symlinks compare their own lstat identity, not a referent.
    """
    evidence = [
        BoundaryIdentityEvidence(internal.path, external.path, *internal.identity)
        for internal in after.objects
        if internal.region == Region.EXTRACTION
        for external in after.objects
        if external.region != Region.EXTRACTION and internal.identity == external.identity
    ]
    return tuple(sorted(evidence, key=lambda item: (item.internal_path, item.external_path)))
