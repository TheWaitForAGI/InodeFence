"""Logical archive inputs; paths are untrusted text, never filesystem Paths."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from .serialization import canonical_json


class EntryType(StrEnum):
    REGULAR = "regular"
    DIRECTORY = "directory"
    HARDLINK = "hardlink"
    SYMLINK = "symlink"


def _validate_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError(f"{field} must be nonempty text without NUL")
    # The initial builder uses strict UTF-8. Reject surrogate code points early.
    value.encode("utf-8", "strict")


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    """An ordered TAR operation. Duplicate/raw paths and unresolved links are valid.

    Only regular entries have bytes content (including b''); links require a
    target. Permissions include special bits. USTAR length limits belong to the
    builder, allowing future encodings without changing the logical model.
    """

    path: str
    entry_type: EntryType
    content: bytes | None = None
    link_target: str | None = None
    mode: int = 0o644

    def __post_init__(self) -> None:
        _validate_text(self.path, "path")
        if not isinstance(self.entry_type, EntryType):
            raise ValueError("entry_type must be an EntryType")
        if type(self.mode) is not int or not 0 <= self.mode <= 0o7777:
            raise ValueError("mode must be an integer permission mask in 0..0o7777")
        if self.entry_type == EntryType.REGULAR:
            if not isinstance(self.content, bytes) or self.link_target is not None:
                raise ValueError("regular entries require bytes content and no link target")
        elif self.content is not None:
            raise ValueError("only regular entries may have content")
        if self.entry_type in (EntryType.HARDLINK, EntryType.SYMLINK):
            if self.link_target is None:
                raise ValueError("link entries require a link target")
            _validate_text(self.link_target, "link_target")
        elif self.link_target is not None:
            raise ValueError("only link entries may have a link target")


@dataclass(frozen=True, slots=True)
class ArchiveCase:
    """One target-independent input; sequence order and duplicates are significant."""

    entries: tuple[ArchiveEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or not all(
            isinstance(entry, ArchiveEntry) for entry in self.entries
        ):
            raise ValueError("entries must be a tuple of ArchiveEntry objects")

    @property
    def case_id(self) -> str:
        """Content address of the versioned logical representation, not a run ID."""
        return sha256(canonical_json(self).encode("utf-8")).hexdigest()
