"""The runtime profile a run executes under: what may change in HOW it executes.

A profile never changes what is judged: the oracle, mutation, feedback, the target containers'
isolation, the result format, verdicts and exit codes are the same under every profile. It may
only select host-side execution choices, each one a named flag of :class:`RuntimePolicy`.

:data:`STRICT` is the verified execution, unchanged, with no flags. It is the default, the
baseline any other profile is compared against, and what ``replay`` (an independent verification)
always runs. A profile is added here as a ``RuntimeProfile`` value plus the flags it sets -- only
once each flag's effect has been measured, never in name only.

:data:`FAST` sets one flag, ``reuse_shared_images``: the launcher is told to leave out its rebuild
of the two shared images (controller, helper) when ``runtime.shared_images`` proves they are the
ones this checkout builds. Measured on the reference host (node-tar 7.5.23, budget 20): the
rebuild is a fixed cost per run of about 2.4 s; nothing per case changes. The per-case cost (Docker
calls of the isolation layer) and the controller's per-run ``pip install`` are outside what a
host-side profile may touch and are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum


class RuntimeProfile(StrEnum):
    STRICT = "strict"
    FAST = "fast"


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """The host-side execution choices of one profile; host-side flags are added as fields."""

    profile: RuntimeProfile
    #: Launch with ``SKIP_BUILD=1`` when the shared controller / helper images are verified to be
    #: this checkout's (``runtime.shared_images``); otherwise build them first, or say why not.
    reuse_shared_images: bool = False

    def flags(self) -> dict[str, bool]:
        """The flags this policy sets, by name, for the runtime record (STRICT sets none)."""
        return {
            item.name: True
            for item in fields(self)
            if item.name != "profile" and getattr(self, item.name) is True
        }


STRICT = RuntimePolicy(RuntimeProfile.STRICT)
FAST = RuntimePolicy(RuntimeProfile.FAST, reuse_shared_images=True)

#: The profiles a user may select (``inodefence explore --profile``), by name.
PROFILES: dict[str, RuntimePolicy] = {
    RuntimeProfile.STRICT.value: STRICT,
    RuntimeProfile.FAST.value: FAST,
}
