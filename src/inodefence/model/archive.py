"""Logical archive data, independent of TAR encoding and filesystem operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EntryType(Enum):
    """Entry kinds supported by the initial archive model."""

    REGULAR = "regular"
    DIRECTORY = "directory"
    HARDLINK = "hardlink"
    SYMLINK = "symlink"


@dataclass(frozen=True)
class ArchiveEntry:
    """One logical entry; path and link_target retain their exact input strings.

    content holds regular-file bytes, defaulting to an empty file. link_target
    holds the target of a hardlink or symlink, defaulting to None for other kinds.
    Fields are represented without validation, normalization, or link resolution.
    """

    path: str
    entry_type: EntryType
    content: bytes = b""
    link_target: str | None = None


@dataclass(frozen=True)
class ArchiveCase:
    """One logical archive with entries supplied as a tuple in archive order.

    The tuple preserves duplicate paths and entry order, including links that
    precede their targets. An empty tuple represents an empty archive case.
    """

    entries: tuple[ArchiveEntry, ...]
