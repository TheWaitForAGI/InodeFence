"""What a diagnostic sees of one controller launch, and what it may report back.

The diagnostics (``inodefence.drivers.runtime.diagnostics``) plug in here without touching the
launcher: each observer gets a :class:`LaunchRequest` right before the launcher runs and the
:class:`LaunchOutcome` once the run is over (after the hook wrote its result, or failed to), and
returns :class:`Finding` s; ``classify`` names how a launch ended. The rules that keep STRICT
unchanged:

* findings are recorded (runtime record); a ``warn`` is also one stderr line, a ``block`` is
  printed once, by the driver, as its setup refusal;
* only a ``block`` finding *before* the launch stops it -- :class:`LaunchBlocked`, a setup error
  (exit 3) -- and a block is added only for a condition that already fails today, moved earlier
  (agreed with the integrator first);
* an observer or ``classify`` that raises is recorded as a diagnostic failure (runtime record and
  one stderr line), never swallowed, and never changes the launcher's exit code, the exception
  path or the verdict.

A request carries only the whitelisted environment keys (:data:`RECORDED_ENV`): run parameters, no
paths, no credentials, not the user's environment. Its :class:`LaunchArtifacts` (absolute paths on
this host, for the diagnostics to look at) are never written to the runtime record.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

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
class LaunchArtifacts:
    """Where this launch leaves its evidence on the host (the hook knows; the record omits it)."""

    #: the loop report the launcher copies back (``HOST_EVIDENCE``), also when it was not written
    report: Path | None = None
    #: the host live folder the loop's snapshots are copied to (node-tar explore), if any
    live: Path | None = None

    def evidence(self) -> tuple[Path, ...]:
        """Candidate evidence files: the report and the launcher's ``.steps`` / ``.calls`` logs
        beside it (``<report stem>.steps.jsonl`` / ``.calls.jsonl``), then the live folder."""
        found: list[Path] = []
        if self.report is not None:
            stem = self.report.with_suffix("")
            found += [self.report, Path(f"{stem}.steps.jsonl"), Path(f"{stem}.calls.jsonl")]
        if self.live is not None:
            found.append(self.live)
        return tuple(found)


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    """One controller launch about to run.

    ``controller`` / ``volume`` are the names the launcher gives this run's disposable controller
    and runtime volume (``inodefence.drivers.launcher.run_resources``).
    """

    target: str
    profile: str
    script: str  # the launcher's file name under scripts/ (not its absolute path)
    args: tuple[str, ...]
    run_id: str | None
    env: dict[str, str] = field(default_factory=dict)  # :func:`recorded_env` only
    controller: str | None = None
    volume: str | None = None
    artifacts: LaunchArtifacts = field(default_factory=LaunchArtifacts)


@dataclass(frozen=True, slots=True)
class LaunchOutcome:
    """How a launch ended: ``returncode`` is ``None`` if the runner raised (``error``: what).

    ``result_written`` says whether the hook wrote its common result after this launch; ``prefix``
    is the driver's output prefix (``TARGET-EXPLORE``) for any line a diagnostic prints.
    """

    request: LaunchRequest
    returncode: int | None
    duration_seconds: float
    error: str | None = None
    result_written: bool = False
    prefix: str = "TARGET-EXPLORE"


class LaunchObserver(Protocol):
    """A diagnostic: checks before a launch, and after it with the outcome."""

    def before(self, request: LaunchRequest) -> list[Finding]: ...

    def after(self, outcome: LaunchOutcome) -> list[Finding]: ...


class LaunchBlocked(ValueError):
    """A ``block`` finding stopped a launch before it ran (a setup error: exit 3)."""
