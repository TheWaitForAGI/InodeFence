"""Pre-violation signals: region-level observations of a run, before any boundary verdict (#511).

Exploratory feedback channel of :mod:`inodefence.feedback.exploration_search` (W4 2026-11-18).
A signal is computed from the observed effect events of one trace and nothing else:

* the observed operation, its outcome, the archive entry kind that triggered it, and the
  **region** of the affected paths (extraction root / harness / external,
  :func:`~inodefence.model.filesystem.path_region`, the fixed harness-layout rule that is also the
  C0 boundary);
* for a hardlink whose observed target lies outside the extraction root, the bucketed escape shape
  of its raw link text (the same buckets as the boundary-attempt key).

Never read here (W4 line): the oracle verdict or violation fingerprints, the protected-path list
(``trace.before.protected_paths``), sentinel names or ids, whether an external path is protected,
which external object it is, or any distance to it. Inside the external region nothing finer
than "external" is used. ``tests/test_exploration_pre_violation.py`` checks the import graph and
that renaming or reordering the protected list and sentinel names changes no signal.

Signal kinds (memo #511, section 1; S1/S2 input-structure signals are excluded by W4 ruling 3):

* ``link-escape-attempt`` (S3): a LINK operation of a hardlink entry whose affected paths leave the
  extraction root and whose raw target is absolute or leads with ``..``; any outcome.
* ``link-external-resolve`` (S4): a LINK operation with an affected path in the external region.
* ``symlink-external-resolve`` (S5): a SYMLINK operation with an affected path in the external
  region.
* ``in-root-identity-relation`` (S6): a hardlink identity relation created with **every** affected
  path inside the extraction root. Once one path is external it is not a pre-violation signal and
  is not emitted (W4 ruling 2).
* ``refused-operation`` (S7): an operation whose outcome is not ``succeeded`` (the outcome enum
  only; target error text is never read).
* ``same-path-replacement`` (S8): a namespace replacement or identity-relation removal with every
  affected path inside the extraction root.

Eligibility is the boundary-attempt gate: an integrity-valid, complete trace that the target
finished with ``success`` or ``rejected``. Any other trace yields no signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from inodefence.feedback.effect import _escape_shape
from inodefence.model import (
    EffectClass,
    EffectEventTrace,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EntryType,
    FilesystemEffectEvent,
    ObservedOperationType,
    OperationOutcome,
    Region,
)
from inodefence.model.filesystem import path_region


class PreViolationSignalKind(StrEnum):
    LINK_ESCAPE_ATTEMPT = "link-escape-attempt"
    LINK_EXTERNAL_RESOLVE = "link-external-resolve"
    SYMLINK_EXTERNAL_RESOLVE = "symlink-external-resolve"
    IN_ROOT_IDENTITY_RELATION = "in-root-identity-relation"
    REFUSED_OPERATION = "refused-operation"
    SAME_PATH_REPLACEMENT = "same-path-replacement"


#: The region value of an event with no affected path.
NO_REGION = "none"
_REPLACEMENT_CLASSES = (EffectClass.NAMESPACE_REPLACEMENT, EffectClass.IDENTITY_RELATION_REMOVAL)


@dataclass(frozen=True, slots=True, order=True)
class PreViolationSignal:
    """One region-level signal. ``shape`` is ``""`` except for ``link-escape-attempt``."""

    kind: str
    entry_type: str
    operation: str
    region: str
    outcome: str
    shape: str = ""

    def __post_init__(self) -> None:
        PreViolationSignalKind(self.kind)
        if self.region not in (NO_REGION, *(region.value for region in Region)):
            raise ValueError("signal region must be a Region value or 'none'")


def signals_eligible(trace: EffectEventTrace) -> bool:
    """The boundary-attempt gate: valid, complete, and finished with success or rejected."""
    return (
        trace.integrity_valid
        and trace.completeness == EffectStreamCompleteness.COMPLETE
        and trace.termination in (EffectTargetTermination.SUCCESS, EffectTargetTermination.REJECTED)
    )


def _regions(event: FilesystemEffectEvent) -> tuple[Region, ...]:
    return tuple(path_region(path) for path in event.affected_paths)


def _outer_region(regions: tuple[Region, ...]) -> str:
    """The outermost region among the affected paths (external > harness > extraction)."""
    for region in (Region.EXTERNAL, Region.HARNESS, Region.EXTRACTION):
        if region in regions:
            return region.value
    return NO_REGION


def _event_signals(event: FilesystemEffectEvent) -> set[PreViolationSignal]:
    regions = _regions(event)
    entry_type = event.entry.entry_type
    common = (entry_type.value, event.operation.value, _outer_region(regions), event.outcome.value)
    found: set[PreViolationSignal] = set()
    if event.operation == ObservedOperationType.LINK:
        target = event.entry.link_target
        if (
            entry_type == EntryType.HARDLINK
            and target is not None
            and any(region != Region.EXTRACTION for region in regions)
        ):
            shape = _escape_shape(target)
            if shape is not None:
                found.add(
                    PreViolationSignal(
                        PreViolationSignalKind.LINK_ESCAPE_ATTEMPT.value, *common, shape.value
                    )
                )
        if Region.EXTERNAL in regions:
            found.add(
                PreViolationSignal(PreViolationSignalKind.LINK_EXTERNAL_RESOLVE.value, *common)
            )
    if event.operation == ObservedOperationType.SYMLINK and Region.EXTERNAL in regions:
        found.add(
            PreViolationSignal(PreViolationSignalKind.SYMLINK_EXTERNAL_RESOLVE.value, *common)
        )
    in_root = bool(regions) and all(region == Region.EXTRACTION for region in regions)
    if event.effect_class == EffectClass.HARDLINK_IDENTITY_RELATION_CREATION and in_root:
        found.add(
            PreViolationSignal(PreViolationSignalKind.IN_ROOT_IDENTITY_RELATION.value, *common)
        )
    if event.effect_class in _REPLACEMENT_CLASSES and in_root:
        found.add(PreViolationSignal(PreViolationSignalKind.SAME_PATH_REPLACEMENT.value, *common))
    if event.outcome != OperationOutcome.SUCCEEDED:
        found.add(PreViolationSignal(PreViolationSignalKind.REFUSED_OPERATION.value, *common))
    return found


def pre_violation_signals(trace: EffectEventTrace) -> tuple[PreViolationSignal, ...]:
    """The sorted, unique signals of one trace; empty when the trace is not eligible."""
    if not isinstance(trace, EffectEventTrace):
        raise ValueError("pre-violation signals require an EffectEventTrace")
    if not signals_eligible(trace):
        return ()
    found: set[PreViolationSignal] = set()
    for event in trace.effect_events:
        found |= _event_signals(event)
    return tuple(sorted(found))
