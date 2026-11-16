"""What a diagnostic sees of one controller launch, and what it may report back.

The diagnostics (``inodefence.drivers.runtime.diagnostics``) plug in here without touching the
launcher: each observer gets a :class:`LaunchRequest` before the launcher runs and the
:class:`LaunchOutcome` after, and returns :class:`Finding` s; ``classify`` names how a launch
ended. The rules that keep STRICT unchanged:

* findings are recorded (runtime record; ``warn`` / ``block`` also one stderr line each);
* only a ``block`` finding *before* the launch stops it -- :class:`LaunchBlocked`, a setup error
  (exit 3) -- and a block is added only for a condition that already fails today, moved earlier
  (agreed with the integrator first);
* an observer or ``classify`` that raises is recorded as a diagnostic failure (runtime record and
  one stderr line), never swallowed, and never changes the launcher's exit code, the exception
  path or the verdict.

A request carries only the whitelisted environment keys (:data:`RECORDED_ENV`): run parameters, no
paths, no credentials, not the user's environment.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["info", "warn", "block"]

#: The launcher environment keys a request (and the runtime record) carries: run parameters only.
#: Path-valued keys (``INODEFENCE_EVIDENCE_DIR``, ``DEMO_HOST_LIVE_DIR``, ...) are left out.
RECORDED_ENV = (
    "RUN_ID",
    "TAR_VERSION",
    "EXPLORE_IMAGE",
    "DEMO_BUDGET",
    "DEMO_SEED",
    "DEMO_POLICY",
    "DEMO_MUTATION_POLICY",
    "DEMO_SENTINEL_SEED",
    "DEMO_SENTINEL_COUNT",
    "DEMO_OBSERVER_INTEGRITY_POLICY",
    "DEMO_ENGINE_COMMIT",
    "SKIP_BUILD",
    "BUILD_ONLY",
)


def recorded_env(env: Mapping[str, str]) -> dict[str, str]:
    """The whitelisted subset of a launcher environment (:data:`RECORDED_ENV`)."""
    return {key: env[key] for key in RECORDED_ENV if key in env}


@dataclass(frozen=True, slots=True)
class Finding:
    """One diagnostic result: ``code`` is a stable slug, ``message`` the one-line explanation."""

    severity: Severity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    """One controller launch about to run."""

    target: str
    profile: str
    script: str  # the launcher's file name under scripts/ (not its absolute path)
    args: tuple[str, ...]
    run_id: str | None
    env: dict[str, str] = field(default_factory=dict)  # :func:`recorded_env` only


@dataclass(frozen=True, slots=True)
class LaunchOutcome:
    """How a launch ended: ``returncode`` is ``None`` if the runner raised (``error``: what)."""

    request: LaunchRequest
    returncode: int | None
    duration_seconds: float
    error: str | None = None
