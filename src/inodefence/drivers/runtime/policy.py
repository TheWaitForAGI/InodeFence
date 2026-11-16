"""The runtime profile a run executes under: what may change in HOW it executes.

A profile never changes what is judged: the oracle, mutation, feedback, the target containers'
isolation, the result format, verdicts and exit codes are the same under every profile. It may
only select host-side execution choices, each one a named flag of :class:`RuntimePolicy`.

There is one profile, :data:`STRICT`: the verified execution, unchanged, with no flags. It is what
every run uses and the baseline any later profile is compared against; ``replay`` (an independent
verification) always runs STRICT. A later profile is added here as a ``RuntimeProfile`` value plus
the flags it sets -- only once each flag's effect has been measured, never in name only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RuntimeProfile(StrEnum):
    STRICT = "strict"


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """The host-side execution choices of one profile; host-side flags are added as fields."""

    profile: RuntimeProfile

    def flags(self) -> dict[str, bool]:
        """The policy's flags by name, for the runtime record (STRICT has none)."""
        return {}


STRICT = RuntimePolicy(RuntimeProfile.STRICT)
