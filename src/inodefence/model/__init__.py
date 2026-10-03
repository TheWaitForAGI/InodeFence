"""Shared data representations for InodeFence."""

from inodefence.model.archive import ArchiveCase, ArchiveEntry, EntryType
from inodefence.model.execution import ExecutionResult
from inodefence.model.filesystem import (
    FilesystemObjectType,
    ObjectSnapshot,
    SnapshotPhase,
    StateSnapshot,
)

__all__ = [
    "ArchiveCase",
    "ArchiveEntry",
    "EntryType",
    "ExecutionResult",
    "FilesystemObjectType",
    "ObjectSnapshot",
    "SnapshotPhase",
    "StateSnapshot",
]
