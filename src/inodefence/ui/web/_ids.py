"""Opaque run ids, so a URL never carries a filesystem path.

The public id of a run is ``sha256(RunRef.key)[:16]``: short, stable across scans, and meaningless
to a path walk. :class:`RunRegistry` keeps, only in memory, the map from id to :class:`RunRef`
built by the last scan; the run folders are always the source. Resolving an id looks it up in that
map -- the client never hands the server a path -- and an id the last scan did not hold triggers
exactly one rescan before a miss becomes a 404.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from inodefence.app import runs as runs_app

#: An unknown id triggers at most one rescan per this many seconds, so a flood of unknown ids
#: cannot make the server rescan the disk on every request.
RESCAN_MIN_INTERVAL_SECONDS = 2.0


def run_id(ref: runs_app.RunRef) -> str:
    """The opaque public id of a run: ``sha256(ref.key)[:16]``."""
    return sha256(ref.key.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Scan:
    listings: tuple[runs_app.RunListing, ...]


class RunRegistry:
    """The id -> :class:`RunRef` map of the last scan (memory only; never written to disk)."""

    def __init__(
        self,
        roots: tuple[Path, ...],
        *,
        extra: tuple[Path, ...] = (),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._roots = roots
        self._extra = extra
        self._clock = clock
        self._lock = threading.Lock()
        self._ids: dict[str, runs_app.RunRef] = {}
        self._last_scan: float | None = None

    def scan(self) -> Scan:
        """Re-discover runs under the configured roots and rebuild the id map."""
        listings = tuple(runs_app.discover_runs(self._roots, extra=self._extra))
        ids = {run_id(item.ref): item.ref for item in listings if item.ref is not None}
        with self._lock:
            self._ids = ids
            self._last_scan = self._clock()
        return Scan(listings)

    def resolve(self, ident: str) -> runs_app.RunRef | None:
        """The run for an opaque id, or ``None``.

        A miss rescans at most once per :data:`RESCAN_MIN_INTERVAL_SECONDS`, so a flood of unknown
        ids cannot make every request walk the disk.
        """
        with self._lock:
            ref = self._ids.get(ident)
            last = self._last_scan
        if ref is not None:
            return ref
        if last is not None and (self._clock() - last) < RESCAN_MIN_INTERVAL_SECONDS:
            return None
        self.scan()
        with self._lock:
            return self._ids.get(ident)


__all__ = ["RunRegistry", "Scan", "run_id"]
