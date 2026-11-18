"""Ground truth for oracle-accuracy fixtures, independent of the InodeFence oracle (#514).

This module decides from two raw snapshots of the disposable sandbox whether C0, C1 and C2 (as
written in ``docs/research/design/security-contracts.md``) actually happened. It imports nothing
from InodeFence: no observer, oracle or feedback code, only ``os``, ``stat`` and ``hashlib``.
Agreement with the oracle is then a measurement, not a tautology.

* C0: outside ``extract/``, a path was created or deleted, or its identity ``(st_dev, st_ino)``
  or file type changed. A content change of an existing outside file is not C0.
* C1: after the run, an object inside ``extract/`` (``lstat``, links not followed) has the same
  ``(st_dev, st_ino)`` as a sentinel.
* C2: a sentinel's existence, type, identity, content digest, size, mode, nlink, uid/gid,
  mtime or ctime changed (atime is excluded).
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Entry:
    kind: str
    dev: int
    ino: int
    digest: str | None
    size: int
    mode: int
    nlink: int
    uid: int
    gid: int
    mtime_ns: int
    ctime_ns: int


def _kind(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISREG(mode):
        return "file"
    return "other"


def snapshot(root: Path) -> dict[str, Entry]:
    """Every path under ``root`` (relative, POSIX), by ``lstat``; regular files also hashed."""
    entries: dict[str, Entry] = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(directory) / name
            info = path.lstat()
            kind = _kind(info.st_mode)
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if kind == "file" else None
            entries[path.relative_to(root).as_posix()] = Entry(
                kind,
                info.st_dev,
                info.st_ino,
                digest,
                info.st_size,
                stat.S_IMODE(info.st_mode),
                info.st_nlink,
                info.st_uid,
                info.st_gid,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )
    return entries


def truth(
    before: dict[str, Entry],
    after: dict[str, Entry],
    sentinels: tuple[str, ...] = ("outside/sentinel.txt",),
    extract: str = "extract",
) -> tuple[bool, bool, bool]:
    """(C0, C1, C2) from two snapshots of the same sandbox root."""

    def inside(path: str) -> bool:
        return path == extract or path.startswith(extract + "/")

    c0 = False
    for path in set(before) | set(after):
        if inside(path):
            continue
        old, new = before.get(path), after.get(path)
        if old is None or new is None:
            c0 = True
        elif (old.dev, old.ino, old.kind) != (new.dev, new.ino, new.kind):
            c0 = True

    sentinel_ids = {(after[s].dev, after[s].ino) for s in sentinels if s in after}
    c1 = any(
        (entry.dev, entry.ino) in sentinel_ids
        for path, entry in after.items()
        if inside(path) and path != extract
    )

    def watched(entry: Entry | None) -> tuple | None:
        if entry is None:
            return None
        return (
            entry.kind,
            entry.dev,
            entry.ino,
            entry.digest,
            entry.size,
            entry.mode,
            entry.nlink,
            entry.uid,
            entry.gid,
            entry.mtime_ns,
            entry.ctime_ns,
        )

    c2 = any(watched(before.get(s)) != watched(after.get(s)) for s in sentinels)
    return c0, c1, c2
