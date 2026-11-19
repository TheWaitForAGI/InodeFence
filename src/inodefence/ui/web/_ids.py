"""Opaque run ids, so a URL never carries a filesystem path.

The public id of a run is ``sha256(RunRef.key)[:16]``: short, stable across scans, and meaningless
to a path walk. :class:`RunRegistry` keeps, only in memory, the map from id to :class:`RunRef`
built by the last scan; the run folders are always the source. Resolving an id looks it up in that
map -- the client never hands the server a path -- and an id the last scan did not hold triggers
exactly one rescan before a miss becomes a 404.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from inodefence.app import runs as runs_app


def run_id(ref: runs_app.RunRef) -> str:
    """The opaque public id of a run: ``sha256(ref.key)[:16]``."""
    return sha256(ref.key.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Scan:
    listings: tuple[runs_app.RunListing, ...]


class RunRegistry:
    """The id -> :class:`RunRef` map of the last scan (memory only; never written to disk)."""

    def __init__(self, roots: tuple[Path, ...], *, extra: tuple[Path, ...] = ()) -> None:
        self._roots = roots
        self._extra = extra
        self._lock = threading.Lock()
        self._ids: dict[str, runs_app.RunRef] = {}

    def scan(self) -> Scan:
        """Re-discover runs under the configured roots and rebuild the id map."""
        listings = tuple(runs_app.discover_runs(self._roots, extra=self._extra))
        ids = {run_id(item.ref): item.ref for item in listings if item.ref is not None}
        with self._lock:
            self._ids = ids
        return Scan(listings)

    def resolve(self, ident: str) -> runs_app.RunRef | None:
        """The run for an opaque id, or ``None`` after one rescan still does not hold it."""
        with self._lock:
            ref = self._ids.get(ident)
        if ref is not None:
            return ref
        self.scan()
        with self._lock:
            return self._ids.get(ident)


__all__ = ["RunRegistry", "Scan", "run_id"]
