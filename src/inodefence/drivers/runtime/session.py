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

Under FAST (``policy.FAST``, chosen by the user; never for a replay) the session applies the
policy's one flag before the launch, in :meth:`RuntimeSession._reuse_shared_images`: the launch
gets ``SKIP_BUILD=1`` only when ``runtime.shared_images`` verifies the two shared images. If they
are not verified it first runs the launcher's own build-only run (recorded as a launch of its own)
and verifies what that built; a launcher without a build-only run is launched as STRICT launches
it, and that fallback is printed and recorded. A failed build stops the run before any controller
exists (:class:`hooks.LaunchBlocked`, exit 3). The argv, every other environment key and the
keyword arguments are STRICT's, and so is everything after the launcher returns.
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
from inodefence.drivers.runtime import diagnostics, shared_images
from inodefence.drivers.runtime.hooks import (
    Finding,
    LaunchArtifacts,
    LaunchBlocked,
    LaunchKind,
    LaunchOutcome,
    LaunchRequest,
    recorded_env,
)
from inodefence.drivers.runtime.policy import STRICT, RuntimePolicy, RuntimeProfile

SCHEMA = "inodefence-runtime-v1"
#: Each kind's driver output prefix (the default of :attr:`RuntimeSession.prefix`).
PREFIXES: dict[str, str] = {"explore": "TARGET-EXPLORE", "replay": "REPLAY"}
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
    #: What the policy's flags did to this launch, by flag name (empty under STRICT: not recorded).
    policy_applied: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        recorded = self._to_json()
        if self.policy_applied:  # a key STRICT's record does not have
            recorded["policy_applied"] = dict(self.policy_applied)
        return recorded

    def _to_json(self) -> dict[str, Any]:
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
            "kind": request.kind,
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
    #: what the session's launches are for (``replay``: ``inodefence replay``)
    kind: LaunchKind = "explore"
    #: the driver's output prefix, for any line a diagnostic prints (default: the kind's)
    prefix: str = ""
    started_at: str = field(
        default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    launches: list[LaunchRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.prefix:
            self.prefix = PREFIXES[self.kind]
        if self.kind == "replay" and self.policy.profile is not RuntimeProfile.STRICT:
            # a replay is an independent verification: it never runs under another profile
            raise ValueError(
                f"a replay always runs under the strict profile (got {self.policy.profile.value})"
            )

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
        applied: dict[str, Any] = {}
        if self.policy.reuse_shared_images:
            env, applied = self._reuse_shared_images(script, args, runner, env, kwargs)
        record = self._record(script, args, env, artifacts)
        record.policy_applied = applied
        done = self._run(record, script, args, runner, env, kwargs)
        if applied.get("reuse_shared_images", {}).get("applied"):
            self._shared_images_unchanged(record, applied["reuse_shared_images"])
        return done

    def _record(
        self,
        script: Path,
        args: Sequence[str],
        env: dict[str, str],
        artifacts: LaunchArtifacts | None,
    ) -> LaunchRecord:
        """A new launch record for ``bash <script> <args...>`` with ``env``; runs the ``before``
        checks, and a ``block`` finding stops the launch here (:class:`LaunchBlocked`)."""
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
            kind=self.kind,
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
        return record

    @staticmethod
    def _run(
        record: LaunchRecord,
        script: Path,
        args: Sequence[str],
        runner: Callable[..., Any],
        env: dict[str, str],
        kwargs: dict[str, Any],
    ) -> Any:
        """Call ``runner`` exactly as given and note how it ended (an exception is re-raised)."""
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

    # ---- FAST: the reuse_shared_images flag ----

    def _say(self, text: str) -> None:
        print(f"{self.prefix} RUNTIME: profile={self.policy.profile.value} {text}", file=sys.stderr)

    def _reuse_shared_images(
        self,
        script: Path,
        args: Sequence[str],
        runner: Callable[..., Any],
        env: dict[str, str],
        kwargs: dict[str, Any],
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """The environment to launch with, and what was decided (for the record and the user).

        ``SKIP_BUILD=1`` is added only for verified images. Not verified: build them with the
        launcher's build-only run and verify that; no such run: launch as STRICT does, said and
        recorded. A build that fails raises :class:`LaunchBlocked` -- nothing else is launched.
        """
        flag = "reuse_shared_images"

        def decided(
            applied: bool, reason: str, images: shared_images.SharedImages | None
        ) -> dict[str, Any]:
            detail: dict[str, Any] = {"applied": applied, "reason": reason}
            if images is not None:
                detail["shared_images"] = images.as_record()
            self._say(f"{flag}={'applied' if applied else 'not-applied'} ({reason})")
            return {flag: detail}

        if env.get("SKIP_BUILD") or env.get("BUILD_ONLY"):
            reason = (
                "SKIP_BUILD / BUILD_ONLY is already set in the environment; launched as given, "
                "the shared images were not verified by this profile"
            )
            return env, decided(False, reason, None)
        if script.name not in shared_images.SKIP_BUILD_LAUNCHERS:
            reason = f"{script.name} has no SKIP_BUILD switch; launched as strict launches it"
            return env, decided(False, reason, None)
        repo_root = script.resolve().parent.parent
        images = shared_images.check(repo_root, env)
        if not images.verified:
            if script.name not in shared_images.BUILD_ONLY_LAUNCHERS:
                reason = (
                    f"{images.reason}, and {script.name} has no build-only run to verify them "
                    "with; launched as strict launches it (the launcher builds them). An explore "
                    "of another target under this profile verifies them"
                )
                return env, decided(False, reason, images)
            self._say(f"{flag}: {images.reason}; building them first (launcher build-only run)")
            images = self._build_shared_images(script, args, runner, env, kwargs, repo_root)
        return {**env, "SKIP_BUILD": "1"}, decided(True, f"SKIP_BUILD=1: {images.reason}", images)

    def _build_shared_images(
        self,
        script: Path,
        args: Sequence[str],
        runner: Callable[..., Any],
        env: dict[str, str],
        kwargs: dict[str, Any],
        repo_root: Path,
    ) -> shared_images.SharedImages:
        """The launcher's build-only run, recorded as a launch of its own, then the verification.

        Anything but a successful build of both images raises :class:`LaunchBlocked`.
        """
        flag, profile = "reuse_shared_images", self.policy.profile.value
        build_env = {**env, "BUILD_ONLY": "1"}
        build = self._record(script, args, build_env, None)
        build.finished = True  # not a run: no outcome diagnosis, no leftovers to look for
        build.classification = "shared-image-build-error"
        # Listed only once it is over: a reader of the session's last launch (the progress
        # display) then never takes a finished build for a finished run.
        self.launches.remove(build)
        try:
            self._run(build, script, args, runner, build_env, kwargs)
            if build.returncode != 0:
                build.classification = "shared-image-build-failed"
                raise LaunchBlocked(
                    f"profile {profile}: the shared-image build failed (launcher exit "
                    f"{build.returncode}); no controller was created and nothing was run. See "
                    "the launcher output, or run with --profile strict"
                )
            build.classification = "shared-image-build"
            images = shared_images.record(repo_root, env)
            build.policy_applied = {flag: {"shared_images": images.as_record()}}
            if not images.verified:
                raise LaunchBlocked(
                    f"profile {profile}: {images.reason}; nothing was run. "
                    "Run with --profile strict"
                )
            return images
        finally:
            self.launches.append(build)

    def _shared_images_unchanged(self, record: LaunchRecord, detail: dict[str, Any]) -> None:
        """After a launch that reused the images: are the two tags still the verified ids?

        The tags are host-global, so another checkout's build can move them while this run is
        going. Recorded (and one stderr line) when they moved or Docker cannot say; never changes
        the exit code or a verdict.
        """
        verified = detail.get("shared_images", {})
        context = verified.get("docker_context")
        try:
            now = shared_images.image_ids(context) if context else None
        except Exception as error:  # noqa: BLE001 - recorded as a diagnostic failure, not hidden
            self._failed(record, "shared_images.image_ids", error)
            return
        detail["unchanged_after_launch"] = now == verified.get("image_ids")
        if not detail["unchanged_after_launch"]:
            finding = Finding(
                "warn",
                "shared-images-changed",
                "a shared image tag no longer resolves to the verified id (rebuilt from another "
                "checkout while this run was going, or Docker did not answer): this run's "
                "controller / helper image may not be the verified one -- repeat the run",
            )
            record.findings.append(finding)
            print(f"RUNTIME DIAGNOSTIC WARN {finding.code}: {finding.message}", file=sys.stderr)

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
            "kind": self.kind,
            "profile": self.policy.profile.value,
            "policy": self.policy.flags(),
            "started_at": self.started_at,
            "launches": [launch.to_json() for launch in self.launches],
        }

    def render(self) -> str:
        """The record as JSON text (what :meth:`write` writes; the replay driver publishes it)."""
        return json.dumps(self.to_json(), indent=2, sort_keys=True) + "\n"

    def write(self, out: Path) -> Path | None:
        """Write the record under ``<out>/runtime/`` (never overwriting); ``None`` if no launch."""
        if not self.launches:
            return None
        run_id = next((r.request.run_id for r in self.launches if r.request.run_id), None)
        stamp = self.started_at.replace("-", "").replace(":", "")
        stem = f"{run_id}-{stamp}" if run_id else stamp
        folder = out / RECORD_DIR
        folder.mkdir(parents=True, exist_ok=True)
        data = self.render()
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
