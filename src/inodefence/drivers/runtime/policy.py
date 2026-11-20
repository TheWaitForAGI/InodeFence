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
rebuild is a fixed cost per run of about 1.5 s (2.78 s -> 1.33 s before the controller is prepared,
5 interleaved runs each); nothing per case changes. The per-case cost (Docker
calls of the isolation layer) and the controller's per-run ``pip install`` are outside what a
host-side profile may touch and are unchanged.

FAST also sets ``identity_check_every`` (#536 option 1, approved by Jiwoong 2026-11-18, see the
decision in docs/DECISIONS.md): the launch gets ``DEMO_IDENTITY_CHECK_EVERY=<N>`` and the targets
re-run their image identity probe at bind, every N-th case and at the end of the campaign instead
of before every case (``inodefence.targets.identity_schedule``). The target containers, their
isolation and the verdicts are unchanged; an end probe that fails voids the campaign. Its measured
effect is recorded once measured (#536); until then nothing claims a speed-up from it.
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
    #: Probe the target image identity every N-th case (plus bind and end) instead of before every
    #: case; ``None``: before every case (STRICT). Passed as ``DEMO_IDENTITY_CHECK_EVERY``.
    identity_check_every: int | None = None

    def flags(self) -> dict[str, bool | int]:
        """The flags this policy sets, by name, for the runtime record (STRICT sets none)."""
        return {
            item.name: value
            for item in fields(self)
            if item.name != "profile"
            and (value := getattr(self, item.name)) is not None
            and value is not False
        }


STRICT = RuntimePolicy(RuntimeProfile.STRICT)
#: FAST's identity probe interval: the targets' ``identity_schedule.DEFAULT_INTERVAL`` (W5's
#: draft, before W1's measurement); a test keeps the two in step once both are on the branch.
FAST_IDENTITY_CHECK_EVERY = 200
FAST = RuntimePolicy(
    RuntimeProfile.FAST,
    reuse_shared_images=True,
    identity_check_every=FAST_IDENTITY_CHECK_EVERY,
)

#: The profiles a user may select (``inodefence explore --profile``), by name.
PROFILES: dict[str, RuntimePolicy] = {
    RuntimeProfile.STRICT.value: STRICT,
    RuntimeProfile.FAST.value: FAST,
}
