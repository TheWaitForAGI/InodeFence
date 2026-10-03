"""Filesystem observation data, independent of targets and security judgments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FilesystemObjectType(Enum):
    """Observed filesystem kinds, distinct from logical archive entry types.

    Hardlinks share object identity rather than forming a separate object kind.
    OTHER represents kinds outside regular files, directories, and symlinks.
    """

    REGULAR = "regular"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


@dataclass(frozen=True)
class ObjectSnapshot:
    """Supplied facts about one filesystem object, without observation or validation.

    relative_path records a path relative to the observer's observation root;
    its supplied string is preserved without normalization or safety checks.
    object_type records the observed kind. st_dev and st_ino record device and
    inode identity; st_nlink records the link count. mode holds the raw stat mode
    including type and permission bits, and size holds the observed byte size.
    symlink_target holds a raw readlink-style string without resolving it.
    content_hash holds an optionally supplied hash string without computing it
    or requiring any algorithm or format. Both optional fields default to None.
    Numeric ranges and field combinations are not checked. Identity comparison
    and Security Contract judgments belong to later consumers.
    """

    relative_path: str
    object_type: FilesystemObjectType
    st_dev: int
    st_ino: int
    st_nlink: int
    mode: int
    size: int
    symlink_target: str | None = None
    content_hash: str | None = None


class SnapshotPhase(Enum):
    """Observation timing before (PRE) or after (POST) extractor execution."""

    PRE = "pre"
    POST = "post"


@dataclass(frozen=True)
class StateSnapshot:
    """Supplied sandbox object snapshots at one phase of extractor execution.

    extraction_objects holds observations inside the extraction root.
    protected_objects holds observations of controlled sentinel/protected objects
    outside that root, within the disposable sandbox.
    Both collections are supplied as tuples and preserved unchanged, including
    empty tuples, order, duplicate paths/identities, and overlap between them.
    Phase/content combinations are not validated. This model does not access the
    filesystem, normalize paths, compare identities or phases, or judge security.
    """

    phase: SnapshotPhase
    extraction_objects: tuple[ObjectSnapshot, ...]
    protected_objects: tuple[ObjectSnapshot, ...]
