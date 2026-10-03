"""Immutable filesystem facts and portable relation models."""

from dataclasses import dataclass
from enum import StrEnum


class ObjectType(StrEnum):
    REGULAR = "regular"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


class Region(StrEnum):
    EXTRACTION = "extraction"
    EXTERNAL = "external"


class SnapshotPhase(StrEnum):
    BEFORE = "before"
    AFTER = "after"


def validate_observed_path(path: str) -> None:
    """Observed names are sandbox-relative, unlike raw archive input paths."""
    if not isinstance(path, str) or not path or "\0" in path or path.startswith("/"):
        raise ValueError("observed paths must be nonempty sandbox-relative text")
    if path != "." and any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError("observed paths must use canonical relative components")


def path_region(path: str) -> Region:
    return (
        Region.EXTRACTION if path == "extract" or path.startswith("extract/") else Region.EXTERNAL
    )


@dataclass(frozen=True, slots=True)
class ObjectSnapshot:
    """An existing lstat object; absence is represented by a missing snapshot path.

    Identity is the symlink's own identity, never its referent. atime is omitted
    because observation itself can read a file. Times are raw evidence only.
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
            not self.symlink_target or "\0" in self.symlink_target
        ):
            raise ValueError("invalid observed symlink target")
        if (self.object_type == ObjectType.REGULAR) != (self.content_digest is not None):
            raise ValueError("only regular files require a content digest")
        if self.content_digest is not None and (
            len(self.content_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.content_digest)
        ):
            raise ValueError("content_digest must be a lowercase SHA-256 hex digest")

    @property
    def identity(self) -> tuple[int, int]:
        return self.st_dev, self.st_ino

    @property
    def region(self) -> Region:
        return path_region(self.path)


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    """Complete reachable sandbox tree, with no traversal through symlinks.

    protected_paths are retained even when a sentinel disappears. An IO error is
    not absence: the observer raises instead of returning an incomplete snapshot.
    """

    sandbox_root: str
    phase: SnapshotPhase
    objects: tuple[ObjectSnapshot, ...]
    protected_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.sandbox_root.startswith("/") or not isinstance(self.phase, SnapshotPhase):
            raise ValueError("snapshot requires an absolute root and explicit phase")
        if not isinstance(self.objects, tuple) or not all(
            isinstance(obj, ObjectSnapshot) for obj in self.objects
        ):
            raise ValueError("objects must be a tuple of ObjectSnapshot objects")
        paths = tuple(obj.path for obj in self.objects)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("snapshot objects must have unique sorted paths")
        if not isinstance(self.protected_paths, tuple) or self.protected_paths != tuple(
            sorted(set(self.protected_paths))
        ):
            raise ValueError("protected paths must be a unique sorted tuple")
        for path in self.protected_paths:
            validate_observed_path(path)
            if path_region(path) != Region.EXTERNAL or path == ".":
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


@dataclass(frozen=True, slots=True)
class StateChange:
    """Observed creation/deletion/change, retaining both sides as evidence."""

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
        if (
            not isinstance(self.fields, tuple)
            or not self.fields
            or not all(isinstance(field, ChangeField) for field in self.fields)
            or self.fields != tuple(field for field in ChangeField if field in self.fields)
        ):
            raise ValueError("change fields must be unique enums in schema order")
        absent = self.before is None or self.after is None
        if absent != (self.fields == (ChangeField.EXISTENCE,)):
            raise ValueError("existence changes must have one absent side")
        if not absent and (ChangeField.EXISTENCE in self.fields or self.before == self.after):
            raise ValueError("an existing-object change requires different observations")


@dataclass(frozen=True, slots=True)
class SignatureObject:
    path: str
    object_type: ObjectType
    mode: int
    st_nlink: int
    size: int | None
    content_digest: str | None
    symlink_target: str | None


@dataclass(frozen=True, slots=True)
class ExternalEffect:
    path: str
    fields: tuple[ChangeField, ...]


@dataclass(frozen=True, slots=True)
class StateSignature:
    """Initial schema, not a validated feedback policy. No raw identity/times.

    Directory sizes are omitted because they depend on allocation/layout.
    Effect labels retain changes in identity/metadata without their volatile
    values. This schema must be versioned when later ablations change it.
    """

    schema_version: int
    objects: tuple[SignatureObject, ...]
    identity_groups: tuple[tuple[str, ...], ...]
    external_effects: tuple[ExternalEffect, ...]
    protected_paths: tuple[str, ...]
