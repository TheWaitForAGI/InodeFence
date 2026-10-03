"""Shared data representations for InodeFence."""

from inodefence.model.archive import ArchiveCase, ArchiveEntry, EntryType
from inodefence.model.execution import ExecutionResult
from inodefence.model.filesystem import FilesystemObjectType, ObjectSnapshot

__all__ = [
    "ArchiveCase",
    "ArchiveEntry",
    "EntryType",
    "ExecutionResult",
    "FilesystemObjectType",
    "ObjectSnapshot",
]
