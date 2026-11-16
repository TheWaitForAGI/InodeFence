"""One exploration's runtime session: the policy it runs under and the record of its launches.

The common explore driver creates a :class:`RuntimeSession` and hands it to the target hook in
``ExploreOptions.runtime``; the hook passes it to :func:`inodefence.drivers.launcher.run_launcher`,
which runs each controller launch through :meth:`RuntimeSession.launch`. Under STRICT the launch is
exactly the call the hook made before (same argv, environment and keyword arguments); the session
only times it and records the result.

After the run -- also when the launcher failed or the run was interrupted, when the record matters
most -- the driver writes the record with :meth:`RuntimeSession.write` to
``<out>/runtime/<run_id>-<UTC time>.json`` (schema :data:`SCHEMA`). It is an additional file: no
existing result file changes, and an existing record is never overwritten. It holds no absolute
path and no environment beyond the whitelisted run parameters (``hooks.RECORDED_ENV``).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inodefence.drivers.runtime.hooks import Finding, LaunchRequest, recorded_env
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

    def to_json(self) -> dict[str, Any]:
        return {
            **asdict(self.request),
            "args": list(self.request.args),
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "classification": self.classification,
            "findings": [asdict(f) for f in self.findings],
            "diagnostic_failures": list(self.diagnostic_failures),
        }


@dataclass(slots=True)
class RuntimeSession:
    """The policy one exploration runs under and the launches it made."""

    target: str
    policy: RuntimePolicy = STRICT
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
        **kwargs: Any,
    ) -> Any:
        """Run ``bash <script> <args...>`` through ``runner`` exactly as given, and record it."""
        request = LaunchRequest(
            target=self.target,
            profile=self.policy.profile.value,
            script=script.name,
            args=tuple(args),
            run_id=env.get("RUN_ID"),
            env=recorded_env(env),
        )
        record = LaunchRecord(request)
        self.launches.append(record)
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
