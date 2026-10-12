"""Generic checkpoint capture and comparison, independent of target adapters."""

from pathlib import Path
from time import monotonic_ns

from inodefence.model import (
    EntryCheckpoint,
    FilesystemTransition,
    ObservationCompleteness,
    ObservationPoint,
    derive_transition,
)

from .snapshot import _capture_objects


def capture_checkpoint(
    sandbox_root: Path,
    checkpoint_index: int,
    point: ObservationPoint,
    protected_paths: tuple[str, ...],
) -> EntryCheckpoint:
    """Capture one full checkpoint or raise; partial snapshots are never returned."""
    started = monotonic_ns()
    objects = _capture_objects(sandbox_root)
    finished = monotonic_ns()
    return EntryCheckpoint(
        checkpoint_index,
        point,
        str(sandbox_root),
        objects,
        protected_paths,
        started,
        finished,
        ObservationCompleteness.COMPLETE,
    )


def compare_observations(
    previous: EntryCheckpoint,
    current: EntryCheckpoint,
    *,
    transition_index: int,
) -> FilesystemTransition:
    """Compare consecutive dynamic observations without weakening compare_states()."""
    return derive_transition(previous, current, transition_index)
