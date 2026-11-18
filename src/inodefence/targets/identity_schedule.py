"""Reduced image-identity checking for FAST exploration (#536 option 1).

STRICT (the default, ``identity_schedule=None`` on a target) runs the image identity probe -- a
separate disposable container that re-hashes the worker and target sources inside the image --
before every archive execution, as the frozen runtime audit (#45) introduced it.

A target given an :class:`IdentitySchedule` probes instead:

* at the start: ``bind()`` already probed once to pin the identity (unchanged);
* every ``interval``-th prepared case;
* at the end: the campaign calls the target's ``verify_identity_at_end()``. A mismatch there
  raises, and the caller marks the whole campaign invalid (fail-closed).

Why this keeps the guarantee within the existing trust model: every archive-run container is
created from the immutable ``sha256:`` image ID, the backend re-inspects that ID on every
prepare and rejects a different one, and containers run ``--read-only``, so the image files the
probe hashes cannot differ between cases without the ID changing. The per-case probe therefore
adds evidence of the same fact, not a different check; what FAST gives up is detecting a change
at the case where it happened (it is detected at the next periodic or the end probe instead).
Image contents and the probe implementation stay trusted, as before.

Isolation is unchanged: archive-run containers, their policy check and their removal are the
backend's and run per case exactly as in STRICT. Replay always runs STRICT.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

DEFAULT_INTERVAL = 200


@dataclass(eq=False, slots=True)
class IdentitySchedule:
    """Mutable per-campaign counter; one instance per bound target."""

    interval: int = DEFAULT_INTERVAL
    prepared: int = 0
    periodic_checks: int = 0
    end_checked: bool = False

    def __post_init__(self) -> None:
        if type(self.interval) is not int or self.interval < 1:
            raise ValueError("identity check interval must be a positive integer")

    def due(self) -> bool:
        """Count one prepared case; True when this case must probe the image identity."""
        self.prepared += 1
        if self.prepared % self.interval == 0:
            self.periodic_checks += 1
            return True
        return False

    def record(self) -> dict[str, object]:
        """What ran, for the campaign report and the runtime record."""
        return {
            "identity_checks": "campaign",
            "interval": self.interval,
            "cases_prepared": self.prepared,
            "start_checks": 1,
            "periodic_checks": self.periodic_checks,
            "end_checks": 1 if self.end_checked else 0,
            "total_checks": 1 + self.periodic_checks + (1 if self.end_checked else 0),
            # STRICT would have probed before each of these cases as well.
            "per_case_checks_skipped": self.prepared - self.periodic_checks,
        }


class _Scheduled(Protocol):
    def verify_identity_at_end(self) -> None: ...


def apply_identity_schedule[T](target: T, every: int | None) -> tuple[T, IdentitySchedule | None]:
    """Give a freshly bound target the FAST schedule; ``every=None`` returns it unchanged."""
    if every is None:
        return target, None
    schedule = IdentitySchedule(every)
    return replace(target, identity_schedule=schedule), schedule  # type: ignore[type-var]


def finish_identity_schedule(target: _Scheduled, schedule: IdentitySchedule | None) -> dict:
    """End-of-campaign probe for FAST; returns the report entry. STRICT: ``{}``, no probe.

    A mismatch raises from the target, so the caller's existing failure path ends the whole
    campaign without a result (fail-closed).
    """
    if schedule is None:
        return {}
    target.verify_identity_at_end()
    return {"identity_checks": schedule.record()}
