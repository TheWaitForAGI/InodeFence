"""Immutable filesystem facts and portable relation models."""

from dataclasses import dataclass
from enum import StrEnum

from ._validation import validate_sha256


class ObjectType(StrEnum):
    REGULAR = "regular"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


class Region(StrEnum):
    """Namespace role for normalization, not creator attribution or trust.

    HARNESS marks the run root and reserved archive namespace. It does not
    authorize the target to create, delete or replace objects there.
    """

    EXTRACTION = "extraction"
    HARNESS = "harness"
    EXTERNAL = "external"


class SnapshotPhase(StrEnum):
    """Bracket target execution: BEFORE after setup, AFTER before bookkeeping.

    Phase labels carry no actor provenance. The runner/adapter must keep harness
    namespace writes outside the observation window for target attribution.
    """

    BEFORE = "before"
    AFTER = "after"


def validate_observed_path(path: str) -> None:
    """Observed names are sandbox-relative, unlike raw archive input paths."""
    if not isinstance(path, str) or not path or "\0" in path or path.startswith("/"):
        raise ValueError("observed paths must be nonempty sandbox-relative text")
    if path != "." and any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError("observed paths must use canonical relative components")


def is_extraction_path(path: str) -> bool:
    """Test canonical observed namespace membership, independently of region role.

    This is a layout fact, not a security verdict or symlink resolution.
    """
    return path == "extract" or path.startswith("extract/")


def path_region(path: str) -> Region:
    """Apply the current fixed runtime-layout policy to canonical observed paths.

    Region is not an intrinsic filesystem object property.
    The run root and archive subtree belong to the harness. Every other path
    outside extract/ is external, including root-level traversal results. New
    harness artifacts must live under archive/ to share this normalization role.
    A HARNESS path is still outside the extraction boundary and is not trusted.
    """
    if is_extraction_path(path):
        return Region.EXTRACTION
    if path in (".", "archive") or path.startswith("archive/"):
        return Region.HARNESS
    return Region.EXTERNAL


@dataclass(frozen=True, slots=True)
class ObjectSnapshot:
    """An existing lstat object; absence is represented by a missing snapshot path.

    Identity is the symlink's own identity, never its referent. atime is omitted
    because observation itself can read a file. Times are raw evidence only.
    path is canonical sandbox-relative evidence, unlike raw ArchiveEntry.path.
    mode is stat.S_IMODE permission/special bits; object_type holds the kind.
    Regular content_digest is SHA-256 lowercase hexadecimal evidence. Only
    symlinks have symlink_target, preserving raw readlink text without resolution.
    Hardlinks are regular objects sharing (st_dev, st_ino), not a separate type.
    """

    path: str
    object_type: ObjectType
    st_dev: int
    st_ino: int
    st_nlink: int
    mode: int
    size: int
    uid: int
    gid: int
    mtime_ns: int
    ctime_ns: int
    symlink_target: str | None = None
    content_digest: str | None = None

    def __post_init__(self) -> None:
        validate_observed_path(self.path)
        if not isinstance(self.object_type, ObjectType):
            raise ValueError("object_type must be an ObjectType")
        if any(
            type(n) is not int or n < 0
            for n in (self.st_dev, self.st_ino, self.st_nlink, self.size, self.uid, self.gid)
        ):
            raise ValueError(
                "stat identity, count, size and ownership must be nonnegative integers"
            )
        if type(self.mode) is not int or not 0 <= self.mode <= 0o7777:
            raise ValueError("mode must be a permission mask")
        if type(self.mtime_ns) is not int or type(self.ctime_ns) is not int:
            raise ValueError("timestamps must be integer nanoseconds")
        if (self.object_type == ObjectType.SYMLINK) != (self.symlink_target is not None):
            raise ValueError("only symlinks require a symlink target")
        if self.symlink_target is not None and (
            not isinstance(self.symlink_target, str)
            or not self.symlink_target
            or "\0" in self.symlink_target
        ):
            raise ValueError("invalid observed symlink target")
        if (self.object_type == ObjectType.REGULAR) != (self.content_digest is not None):
            raise ValueError("only regular files require a content digest")
        if self.content_digest is not None:
            validate_sha256(self.content_digest)

    @property
    def identity(self) -> tuple[int, int]:
        return self.st_dev, self.st_ino

    @property
    def region(self) -> Region:
        return path_region(self.path)


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    """Full raw observation/evidence, with no traversal through symlinks.

    Includes harness artifacts and their metadata/digests, not just the objects
    used for feedback. Region classification never removes raw observations.
    protected_paths are retained even when a sentinel disappears. An IO error is
    not absence: the observer raises instead of returning an incomplete snapshot.
    Phase labels describe the execution window, not who caused each change.
    """

    sandbox_root: str
    phase: SnapshotPhase
    objects: tuple[ObjectSnapshot, ...]
    protected_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.sandbox_root, str)
            or not self.sandbox_root.startswith("/")
            or not isinstance(self.phase, SnapshotPhase)
        ):
            raise ValueError("snapshot requires an absolute root and explicit phase")
        if not isinstance(self.objects, tuple) or not all(
            isinstance(obj, ObjectSnapshot) for obj in self.objects
        ):
            raise ValueError("objects must be a tuple of ObjectSnapshot objects")
        paths = tuple(obj.path for obj in self.objects)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("snapshot objects must have unique sorted paths")
        if (
            not isinstance(self.protected_paths, tuple)
            or not all(isinstance(path, str) for path in self.protected_paths)
            or self.protected_paths != tuple(sorted(set(self.protected_paths)))
        ):
            raise ValueError("protected paths must be a unique sorted tuple")
        for path in self.protected_paths:
            validate_observed_path(path)
            if path_region(path) != Region.EXTERNAL:
                raise ValueError("sentinels must be external sandbox paths")

    def get(self, path: str) -> ObjectSnapshot | None:
        return next((obj for obj in self.objects if obj.path == path), None)

    def identity_groups(self) -> tuple[tuple[str, ...], ...]:
        """Sorted same-object groups; singleton identities convey no relation."""
        groups: dict[tuple[int, int], list[str]] = {}
        for obj in self.objects:
            groups.setdefault(obj.identity, []).append(obj.path)
        return tuple(sorted(tuple(paths) for paths in groups.values() if len(paths) > 1))


class ChangeField(StrEnum):
    EXISTENCE = "existence"
    OBJECT_TYPE = "object_type"
    IDENTITY = "identity"
    NLINK = "st_nlink"
    MODE = "mode"
    SIZE = "size"
    UID = "uid"
    GID = "gid"
    MTIME = "mtime_ns"
    CTIME = "ctime_ns"
    SYMLINK_TARGET = "symlink_target"
    CONTENT = "content_digest"


def validate_change_fields(fields: tuple[ChangeField, ...]) -> None:
    """Require nonempty, immutable field labels in their canonical schema order."""
    if (
        not isinstance(fields, tuple)
        or not fields
        or not all(isinstance(field, ChangeField) for field in fields)
        or fields != tuple(field for field in ChangeField if field in fields)
    ):
        raise ValueError("change fields must be unique enums in schema order")


def observed_change_fields(
    before: ObjectSnapshot | None, after: ObjectSnapshot | None
) -> tuple[ChangeField, ...]:
    """Exact raw difference labels; creation/deletion carries only EXISTENCE."""
    if before is None and after is None:
        return ()
    if before is None or after is None:
        return (ChangeField.EXISTENCE,)
    return tuple(
        field
        for field in ChangeField
        if field != ChangeField.EXISTENCE
        and getattr(before, field.value) != getattr(after, field.value)
    )


@dataclass(frozen=True, slots=True)
class StateChange:
    """Observed change with exact field labels, retaining both sides as evidence."""

    path: str
    before: ObjectSnapshot | None
    after: ObjectSnapshot | None
    fields: tuple[ChangeField, ...]

    def __post_init__(self) -> None:
        validate_observed_path(self.path)
        if self.before is None and self.after is None:
            raise ValueError("a change requires at least one observed object")
        for obj in (self.before, self.after):
            if obj is not None and (not isinstance(obj, ObjectSnapshot) or obj.path != self.path):
                raise ValueError("change observations must match the changed path")
        validate_change_fields(self.fields)
        absent = self.before is None or self.after is None
        if absent != (self.fields == (ChangeField.EXISTENCE,)):
            raise ValueError("existence changes must have one absent side")
        if not absent and (ChangeField.EXISTENCE in self.fields or self.before == self.after):
            raise ValueError("an existing-object change requires different observations")
        if self.fields != observed_change_fields(self.before, self.after):
            raise ValueError("change fields must exactly match the before/after observations")


@dataclass(frozen=True, slots=True)
class SignatureObject:
    """A security-state object; nlink/size/digest apply only to regular files.

    Nonregular nlink is None: directory counts depend on filesystem semantics.
    Symlink text is tagged as run:<raw suffix> or literal:<raw target> in v3;
    no referent is inferred.
    """

    path: str
    object_type: ObjectType
    mode: int
    st_nlink: int | None
    size: int | None
    content_digest: str | None
    symlink_target: str | None

    def __post_init__(self) -> None:
        validate_observed_path(self.path)
        if path_region(self.path) == Region.HARNESS:
            raise ValueError("signature objects must be in extraction/external scope")
        if not isinstance(self.object_type, ObjectType):
            raise ValueError("object_type must be an ObjectType")
        if type(self.mode) is not int or not 0 <= self.mode <= 0o7777:
            raise ValueError("mode must be a permission mask")
        if self.object_type == ObjectType.REGULAR:
            if any(type(value) is not int or value < 0 for value in (self.st_nlink, self.size)):
                raise ValueError("regular signature count and size must be nonnegative integers")
            validate_sha256(self.content_digest)
        elif any(value is not None for value in (self.st_nlink, self.size, self.content_digest)):
            raise ValueError("only regular signature objects have count/size/digest")
        if self.object_type == ObjectType.SYMLINK:
            target = self.symlink_target
            if not isinstance(target, str) or "\0" in target:
                raise ValueError("signature symlink requires tagged target text")
            if target.startswith("run:"):
                if target[4:] and not target[4:].startswith("/"):
                    raise ValueError("run target suffix must be empty or start with a slash")
            elif not target.startswith("literal:") or not target[8:]:
                raise ValueError("signature symlink requires tagged target text")
        elif self.symlink_target is not None:
            raise ValueError("only symlinks have a signature target")


@dataclass(frozen=True, slots=True)
class ExternalEffect:
    path: str
    fields: tuple[ChangeField, ...]

    def __post_init__(self) -> None:
        validate_observed_path(self.path)
        if path_region(self.path) != Region.EXTERNAL:
            raise ValueError("external effects require external paths")
        validate_change_fields(self.fields)


@dataclass(frozen=True, slots=True)
class StateSignature:
    """Normalized security state for future feedback/corpus, not raw evidence.

    Schema v3 tags symlink targets to distinguish run anchors from literals.
    Like v2, it excludes harness objects and projects identity groups onto the
    same scope, dropping singleton groups. Neither ArchiveCase identity nor TAR
    artifact identity is included. No raw device/inode or timestamp values.
    Nonregular nlink and size are omitted to avoid filesystem allocation noise.
    Effect labels retain changes in identity/metadata without their volatile
    values; raw nlink change labels remain external-effect evidence. This is an
    initial representation, not a validated feedback selection policy.
    """

    schema_version: int
    objects: tuple[SignatureObject, ...]
    identity_groups: tuple[tuple[str, ...], ...]
    external_effects: tuple[ExternalEffect, ...]
    protected_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 3:
            raise ValueError("StateSignature requires schema version 3")
        if not isinstance(self.objects, tuple) or not all(
            isinstance(obj, SignatureObject) for obj in self.objects
        ):
            raise ValueError("signature objects must be a tuple of SignatureObject records")
        paths = tuple(obj.path for obj in self.objects)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("signature objects must have unique sorted paths")
        if not isinstance(self.identity_groups, tuple) or not all(
            isinstance(group, tuple) and all(isinstance(path, str) for path in group)
            for group in self.identity_groups
        ):
            raise ValueError("identity groups must be tuples of path tuples")
        if self.identity_groups != tuple(sorted(set(self.identity_groups))):
            raise ValueError("identity groups must be unique and sorted")
        grouped_paths: set[str] = set()
        for group in self.identity_groups:
            if len(group) < 2 or group != tuple(sorted(set(group))):
                raise ValueError("identity groups require unique sorted nonsingleton paths")
            if not set(group) <= set(paths) or grouped_paths.intersection(group):
                raise ValueError("identity groups must partition paths in signature scope")
            grouped_paths.update(group)
        if not isinstance(self.external_effects, tuple) or not all(
            isinstance(effect, ExternalEffect) for effect in self.external_effects
        ):
            raise ValueError("external effects must be a tuple of ExternalEffect records")
        effects = tuple(effect.path for effect in self.external_effects)
        if effects != tuple(sorted(set(effects))):
            raise ValueError("external effects must have unique sorted paths")
        if (
            not isinstance(self.protected_paths, tuple)
            or not all(isinstance(path, str) for path in self.protected_paths)
            or self.protected_paths != tuple(sorted(set(self.protected_paths)))
        ):
            raise ValueError("protected paths must be a unique sorted tuple of text")
        for path in self.protected_paths:
            validate_observed_path(path)
            if path_region(path) != Region.EXTERNAL:
                raise ValueError("sentinels must be external sandbox paths")
