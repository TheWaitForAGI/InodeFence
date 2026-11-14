"""Read a TAR written by :func:`inodefence.builder.build_tar` back into the ArchiveCase it encodes.

Replaying one saved input needs the logical case again: every execution path (for example
``effect_pipeline.run_node_tar_effect_case``) takes an :class:`ArchiveCase` and builds the TAR
itself. This module is the inverse of the builder, and it is deliberately strict:

- it parses the USTAR headers directly (name + prefix with the builder's own joining rule, mode,
  size, type flag, link name) instead of using :mod:`tarfile`'s reader, which normalizes names on
  read (for example it strips a directory's trailing slashes) and would silently change the input;
- it never extracts anything; it only reads bytes;
- it accepts a result only if re-encoding it with ``build_tar`` gives the **exact same bytes**,
  and, when given, the same ``case_id``. Anything else -- a TAR the builder did not write, a
  damaged file, a different input -- is refused with the reason, never "close enough".

The size limits bound an untrusted input (they are checked before any parsing work); the path and
link limits are what a USTAR header can hold at all.
"""

from __future__ import annotations

from hashlib import sha256

from inodefence.builder import build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType

BLOCK = 512
#: Upper bound on a replay input. Exploration inputs are a few KiB; the cap keeps the controller's
#: one-line stdin input (base64, so x4/3) well under its 16 MiB read limit.
MAX_TAR_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 4096
#: USTAR can hold at most a 155-byte prefix + "/" + 100-byte name, and a 100-byte link name.
MAX_PATH_BYTES = 256
MAX_LINK_BYTES = 100

_TYPES = {
    b"0": EntryType.REGULAR,
    b"\0": EntryType.REGULAR,
    b"5": EntryType.DIRECTORY,
    b"1": EntryType.HARDLINK,
    b"2": EntryType.SYMLINK,
}


class TarReadError(ValueError):
    """The bytes are not a TAR this builder produced (or not the expected input)."""


def _field(block: bytes, start: int, end: int) -> bytes:
    return block[start:end].split(b"\0", 1)[0]


def _octal(block: bytes, start: int, end: int, what: str, index: int) -> int:
    raw = _field(block, start, end).strip(b" ")
    try:
        return int(raw or b"0", 8)
    except ValueError as error:
        raise TarReadError(f"entry {index}: {what} is not an octal number") from error


def _text(raw: bytes, what: str, index: int) -> str:
    try:
        return raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise TarReadError(f"entry {index}: {what} is not strict UTF-8") from error


def read_builder_tar(data: bytes, *, expected_case_id: str | None = None) -> ArchiveCase:
    """Return the ArchiveCase whose ``build_tar`` is exactly ``data``; refuse anything else."""
    if not isinstance(data, bytes | bytearray):
        raise TarReadError("TAR input must be bytes")
    data = bytes(data)
    if not data or len(data) % BLOCK:
        raise TarReadError("not a TAR: size is not a non-zero multiple of 512")
    if len(data) > MAX_TAR_BYTES:
        raise TarReadError(f"TAR is {len(data)} bytes, above the {MAX_TAR_BYTES}-byte limit")
    entries: list[ArchiveEntry] = []
    offset = 0
    while offset + BLOCK <= len(data):
        block = data[offset : offset + BLOCK]
        if block == bytes(BLOCK):
            break  # end-of-archive marker; the round-trip check verifies the padding after it
        index = len(entries)
        if index >= MAX_ENTRIES:
            raise TarReadError(f"more than {MAX_ENTRIES} entries")
        if block[257:263] != b"ustar\0":
            raise TarReadError(f"entry {index}: not a USTAR header")
        name, prefix = _field(block, 0, 100), _field(block, 345, 500)
        raw_path = prefix + b"/" + name if prefix else name
        if len(raw_path) > MAX_PATH_BYTES:
            raise TarReadError(f"entry {index}: path longer than {MAX_PATH_BYTES} bytes")
        raw_link = _field(block, 157, 257)
        if len(raw_link) > MAX_LINK_BYTES:
            raise TarReadError(f"entry {index}: link target longer than {MAX_LINK_BYTES} bytes")
        flag = block[156:157]
        if flag not in _TYPES:
            raise TarReadError(f"entry {index}: unsupported entry type {flag!r}")
        entry_type = _TYPES[flag]
        mode = _octal(block, 100, 108, "mode", index)
        size = _octal(block, 124, 136, "size", index)
        offset += BLOCK
        content: bytes | None = None
        if entry_type is EntryType.REGULAR:
            if offset + size > len(data):
                raise TarReadError(f"entry {index}: content runs past the end of the TAR")
            content = data[offset : offset + size]
            offset += -(-size // BLOCK) * BLOCK
        elif size:
            raise TarReadError(f"entry {index}: a non-regular entry carries {size} content bytes")
        try:
            entries.append(
                ArchiveEntry(
                    _text(raw_path, "path", index),
                    entry_type,
                    content,
                    _text(raw_link, "link target", index) if raw_link else None,
                    mode,
                )
            )
        except ValueError as error:
            if isinstance(error, TarReadError):
                raise
            raise TarReadError(f"entry {index}: {error}") from error
    case = ArchiveCase(tuple(entries))
    try:
        rebuilt = build_tar(case)
    except ValueError as error:
        raise TarReadError(f"the builder cannot re-encode this input: {error}") from error
    if rebuilt != data:
        raise TarReadError(
            "re-encoding does not give the same bytes (this TAR was not written by this builder "
            f"or is damaged): sha256 {sha256(data).hexdigest()} != {sha256(rebuilt).hexdigest()}"
        )
    if expected_case_id is not None and case.case_id != expected_case_id:
        raise TarReadError(f"case_id {case.case_id} differs from the expected {expected_case_id}")
    return case
