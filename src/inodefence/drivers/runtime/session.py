"""One exploration's runtime session: the policy it runs under and the record of its launches.

The common explore driver creates a :class:`RuntimeSession` and hands it to the target hook in
``ExploreOptions.runtime``; the hook passes it to :func:`inodefence.drivers.launcher.run_launcher`,
which runs each controller launch through :meth:`RuntimeSession.launch`. Under STRICT the launch is
exactly the call the hook made before (same argv, environment and keyword arguments); the session
times it, runs the diagnostics' ``before`` checks (``runtime.diagnostics``) and records it.

When the run is over -- the hook wrote its result, failed, or the run was interrupted -- the driver
calls :meth:`RuntimeSession.finish`, which classifies each launch and runs the diagnostics'
``after`` checks, then :meth:`RuntimeSession.write`, which writes the record to
``<out>/runtime/<run_id>-<UTC time>.json`` (schema :data:`SCHEMA`). It is an additional file: no
existing result file changes, and an existing record is never overwritten. It holds no absolute
path and no environment beyond the whitelisted run parameters (``hooks.RECORDED_ENV``).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inodefence.drivers.launcher import run_resources
from inodefence.drivers.runtime import diagnostics
from inodefence.drivers.runtime.hooks import (
    Finding,
    LaunchArtifacts,
    LaunchBlocked,
    LaunchOutcome,
    LaunchRequest,
    recorded_env,
)
from inodefence.drivers.runtime.policy import STRICT, RuntimePolicy

SCHEMA = "inodefence-runtime-v1"
#: The folder under the run's output folder that holds the runtime records.
RECORD_DIR = "runtime"


@dataclass(slots=True)
class LaunchRecord:
    """One launch as recorded: request, outcome, classification and what the diagnostics said."""

    request: LaunchRequest
    returncode: int | None = None
    duration_seconds: float | None = None
    error: str | None = None
    classification: str | None = None
    findings: list[Finding] = field(default_factory=list)
    diagnostic_failures: list[str] = field(default_factory=list)
    finished: bool = False

    def to_json(self) -> dict[str, Any]:
        request = self.request
        return {  # no artifacts: they are absolute host paths
            "target": request.target,
            "profile": request.profile,
            "script": request.script,
            "args": list(request.args),
            "run_id": request.run_id,
            "env": dict(request.env),
            "controller": request.controller,
            "volume": request.volume,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "classification": self.classification,
            "findings": [
                {"severity": f.severity, "code": f.code, "message": f.message}
                for f in self.findings
            ],
            "diagnostic_failures": list(self.diagnostic_failures),
        }


@dataclass(slots=True)
class RuntimeSession:
    """The policy one exploration runs under and the launches it made."""

    target: str
    policy: RuntimePolicy = STRICT
    #: the driver's output prefix, for any line a diagnostic prints
    prefix: str = "TARGET-EXPLORE"
    started_at: str = field(
        default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    launches: list[LaunchRecord] = field(default_factory=list)

    # ---- one launch ----

    def launch(
        self,
        script: Path,
        args: Sequence[str],
        *,
        runner: Callable[..., Any],
        env: dict[str, str],
        artifacts: LaunchArtifacts | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run ``bash <script> <args...>`` through ``runner`` exactly as given, and record it.

        A ``block`` finding of a ``before`` check stops the launch first (:class:`LaunchBlocked`).
        """
        run_id = env.get("RUN_ID")
        controller, volume = run_resources(self.target, run_id)
        request = LaunchRequest(
            target=self.target,
            profile=self.policy.profile.value,
            script=script.name,
            args=tuple(args),
            run_id=run_id,
            env=recorded_env(env),
            controller=controller,
            volume=volume,
            artifacts=artifacts or LaunchArtifacts(),
        )
        record = LaunchRecord(request)
        self.launches.append(record)
        for observer in diagnostics.OBSERVERS:
            self._observe(record, observer, "before", request)
        blocks = [f for f in record.findings if f.severity == "block"]
        if blocks:
            record.classification = "blocked"
            record.finished = True
            raise LaunchBlocked("; ".join(f"{f.code}: {f.message}" for f in blocks))
        started = time.monotonic()
        try:
            done = runner(["bash", str(script), *args], env=env, **kwargs)
        except BaseException as error:  # recorded, then re-raised unchanged
            record.duration_seconds = round(time.monotonic() - started, 3)
            record.error = type(error).__name__
            raise
        record.duration_seconds = round(time.monotonic() - started, 3)
        returncode = getattr(done, "returncode", None)
        record.returncode = returncode if isinstance(returncode, int) else None
        return done

    # ---- after the run ----

    def finish(self, *, result_written: bool) -> None:
        """Classify every launch not yet finished and run the ``after`` checks on it (once).

        Called by the driver once the run is over, whatever its end; it never raises (a failing
        diagnostic is recorded) and never changes the exit code, the exception path or a verdict.
        """
        for record in self.launches:
            if record.finished:
                continue
            record.finished = True
            outcome = LaunchOutcome(
                request=record.request,
                returncode=record.returncode,
                duration_seconds=record.duration_seconds or 0.0,
                error=record.error,
                result_written=result_written,
                prefix=self.prefix,
            )
            try:
                record.classification = diagnostics.classify(outcome)
            except Exception as error:  # noqa: BLE001 - recorded as a diagnostic failure
                self._failed(record, "classify", error)
            for observer in diagnostics.OBSERVERS:
                self._observe(record, observer, "after", outcome)

    def _observe(self, record: LaunchRecord, observer: object, phase: str, subject: object) -> None:
        name = f"{type(observer).__name__}.{phase}"
        try:
            findings = list(getattr(observer, phase)(subject))
        except Exception as error:  # noqa: BLE001 - recorded as a diagnostic failure, not hidden
            self._failed(record, name, error)
            return
        for finding in findings:
            record.findings.append(finding)
            # warn: one stderr line here. block: the driver prints it once as its SETUP refusal
            # (LaunchBlocked); info: recorded only.
            if finding.severity == "warn":
                print(
                    f"RUNTIME DIAGNOSTIC {finding.severity.upper()} {finding.code}: "
                    f"{finding.message}",
                    file=sys.stderr,
                )

    @staticmethod
    def _failed(record: LaunchRecord, name: str, error: Exception) -> None:
        detail = f"{name}: {type(error).__name__}: {error}"
        record.diagnostic_failures.append(detail)
        print(f"RUNTIME DIAGNOSTIC FAILED (not a check result) {detail}", file=sys.stderr)

    # ---- the record ----

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "target": self.target,
            "profile": self.policy.profile.value,
            "policy": self.policy.flags(),
            "started_at": self.started_at,
            "launches": [launch.to_json() for launch in self.launches],
        }

    def write(self, out: Path) -> Path | None:
        """Write the record under ``<out>/runtime/`` (never overwriting); ``None`` if no launch."""
        if not self.launches:
            return None
        run_id = next((r.request.run_id for r in self.launches if r.request.run_id), None)
        stamp = self.started_at.replace("-", "").replace(":", "")
        stem = f"{run_id}-{stamp}" if run_id else stamp
        folder = out / RECORD_DIR
        folder.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.to_json(), indent=2, sort_keys=True) + "\n"
        handle, temporary = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(data)
            for attempt in range(100):
                target = folder / (f"{stem}.json" if attempt == 0 else f"{stem}.{attempt}.json")
                try:
                    os.link(temporary, target)  # atomic, and fails instead of overwriting
                except FileExistsError:
                    continue
                return target
            raise FileExistsError(f"no free runtime record name for {stem} under {folder}")
        finally:
            os.unlink(temporary)
