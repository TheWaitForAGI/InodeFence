"""The FastAPI app: GET-only JSON over :mod:`inodefence.app`, an SSE event stream, static files.

Imported only through :func:`inodefence.ui.web.create_app`, which has already checked that FastAPI
is installed. Nothing here starts, stops, deletes or replays a run, runs an extractor, or serves a
stored input's bytes; every value comes from the shared read model and is serialised unchanged
(:func:`._serialize.to_jsonable`). Run identity in URLs is an opaque id (:mod:`._ids`): the server
resolves it against its own last scan, so no path is ever accepted from the client.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

# starlette is not an optional package here (fastapi depends on it); only fastapi/uvicorn are
# imported lazily. fastapi.Request / fastapi.responses.* ARE these starlette types, so importing
# them at module level keeps FastAPI's annotation resolution working for the route handlers.
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, Response, StreamingResponse
from starlette.staticfiles import StaticFiles

from inodefence.app import doctor as doctor_app
from inodefence.app import events as events_app
from inodefence.app import runs as runs_app
from inodefence.app import targets as targets_app
from inodefence.ui import theme

from . import API_SCHEMA
from ._ids import RunRegistry, run_id
from ._serialize import to_jsonable

if TYPE_CHECKING:  # the FastAPI type for annotations; the class itself is imported in build_app
    from fastapi import FastAPI

STATIC_DIR = Path(__file__).parent / "static"
HEALTH_TTL_SECONDS = 30.0
FINDINGS_DEFAULT_LIMIT = 200
FINDINGS_MAX_LIMIT = 500
FOLLOW_INTERVAL_SECONDS = 1.0
SSE_POLL_TIMEOUT_SECONDS = 1.0


#: One health check's result: the doctor report and the per-target prepared-image counts.
HealthResult = tuple["doctor_app.Report", "dict[str, int] | None"]


def _default_health_check(repo_root: Path | None) -> HealthResult:
    """The real doctor report + image groups (read-only). ``repo_root`` keeps a uniform seam.

    ``image_groups()`` is its own ``docker images`` lookup, not a slice of the report; it runs once
    per health refresh (the same TTL/background cadence as the report), never per request.
    """
    from inodefence.user_config import UserConfigError, load_user_config

    try:
        config = load_user_config()
        config_error = None
    except (UserConfigError, OSError) as exc:
        config, config_error = None, str(exc)
    report = doctor_app.run(config, config_error, details=False)
    return report, doctor_app.image_groups()


class HealthCache:
    """A memory-only, TTL cache of the doctor report (and image groups); off-thread, never on disk.

    The first read returns nothing (the route shows "checking") and starts the first check in the
    background; later reads return the last result with its age, and start a refresh when it is
    older than ``ttl``. A check that raises leaves the previous result in place.
    """

    def __init__(
        self,
        check: Callable[[], HealthResult],
        *,
        ttl: float = HEALTH_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._check = check
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._report: doctor_app.Report | None = None
        self._groups: dict[str, int] | None = None
        self._checked_at: float | None = None
        self._refreshing = False

    def snapshot(self) -> tuple[doctor_app.Report | None, dict[str, int] | None, float | None]:
        now = self._clock()
        start = False
        with self._lock:
            fresh = self._checked_at is not None and (now - self._checked_at) < self._ttl
            if not fresh and not self._refreshing:
                self._refreshing = True
                start = True
            report, groups, checked_at = self._report, self._groups, self._checked_at
        if start:
            threading.Thread(target=self._refresh, name="inodefence-ui-health", daemon=True).start()
        return report, groups, checked_at

    def _refresh(self) -> None:
        result: HealthResult | None = None
        try:
            result = self._check()
        except Exception:  # noqa: BLE001 - a doctor failure must not kill the refresh thread
            result = None
        with self._lock:
            if result is not None:
                self._report, self._groups = result
                self._checked_at = self._clock()
            self._refreshing = False


def _package_version() -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("inodefence")
    except PackageNotFoundError:  # pragma: no cover - installed in every supported environment
        return None


def _health_payload(cache: HealthCache) -> dict[str, Any]:
    report, groups, checked_at = cache.snapshot()
    if report is None:
        return {
            "schema": API_SCHEMA,
            "state": "checking",
            "package_version": _package_version(),
            "report": None,
            "summary": None,
            "exit_code": None,
            "failed": None,
            "unknown": None,
            "image_groups": None,
            "checked_at": None,
            "age_seconds": None,
        }
    age = None if checked_at is None else max(time.time() - checked_at, 0.0)
    return {
        "schema": API_SCHEMA,
        "state": "ok",
        "package_version": _package_version(),
        "report": to_jsonable(report),
        "summary": report.summary,
        "exit_code": report.exit_code,
        "failed": report.failed,
        "unknown": report.unknown,
        "image_groups": groups,
        "checked_at": checked_at,
        "age_seconds": age,
    }


def _listing_payload(listing: runs_app.RunListing) -> dict[str, Any]:
    ref = listing.ref
    return {
        "id": None if ref is None else run_id(ref),
        "path": str(listing.path),
        "read_state": listing.read_state.value,
        "error": listing.error,
        "kind": None if ref is None else ref.kind.value,
        "root": None if ref is None else str(ref.root),
        "run_id": None if ref is None else ref.run_id,
        "run_id_derived": None if ref is None else ref.run_id_derived,
        "target": None if ref is None else ref.target,
        "version": None if ref is None else ref.version,
    }


def _count_findings(snapshot: runs_app.RunSnapshot, finding: runs_app.FindingClass) -> int:
    return sum(1 for row in snapshot.findings if row.finding is finding)


def _stalled(snapshot: runs_app.RunSnapshot) -> bool | None:
    """A live run gone quiet: live + running + age > 4 x the live-pull interval (the TUI's
    ACTIVE_MAX_AGE; the threshold is read from the app layer, never re-stated here). ``None`` when
    the question does not apply (not a live run) or the age is unknown. RES1 will lift this to a
    shared app.runs function; swap to it when it lands."""
    progress = snapshot.progress
    if (
        progress is None
        or progress.source is not runs_app.Source.LIVE
        or progress.state != "running"
    ):
        return None
    age = snapshot.progress_age()
    return None if age is None else age > 4 * runs_app.LIVE_PULL_INTERVAL_SECONDS


def _run_status(snapshot: runs_app.RunSnapshot) -> dict[str, Any]:
    """A compact per-run status for the runs table and the Overview aggregates (no recompute).

    Separate axes stay separate (termination counts, verdict, candidate counts); every missing
    value is ``None`` (shown as "-"/"?"), never ``0``. The full record is at ``/api/runs/{id}``.
    """
    progress = snapshot.progress
    summary = snapshot.summary
    return {
        "state": progress.state if progress else None,
        "stalled": _stalled(snapshot),
        "source": progress.source.value if progress else None,
        "runs": progress.runs if progress else None,
        "budget": progress.budget if progress else None,
        "runs_per_second": progress.runs_per_second if progress else None,
        "violations": progress.violations if progress else None,
        "unjudged": progress.unjudged if progress else None,
        "updated_at": progress.updated_at if progress else None,
        "launcher_step": progress.launcher_step if progress else None,
        "verdict": summary.verdict.value if summary and summary.verdict else None,
        "validated": summary.validated if summary else None,
        "read_state": summary.read_state.value if summary else None,
        "label": summary.label if summary else None,
        "executed": summary.executed if summary else None,
        # result file's mtime (RES1 RunSummary.result_mtime); getattr degrades to None until the
        # field reaches this base, then auto-populates. UI label: "result written", not "verified".
        "result_mtime": getattr(summary, "result_mtime", None) if summary else None,
        "terminations": to_jsonable(summary.terminations) if summary else {},
        "candidates": _count_findings(snapshot, runs_app.FindingClass.CANDIDATE),
        "candidates_needs_repro": _count_findings(
            snapshot, runs_app.FindingClass.CANDIDATE_NEEDS_REPRO_CHECK
        ),
        "replays": len(snapshot.replays),
        "progress_age_seconds": snapshot.progress_age(),
    }


def build_app(
    *,
    roots: Iterable[Path] | None,
    extra: tuple[Path, ...],
    repo_root: Path | None,
) -> FastAPI:
    # fastapi itself is imported here, never at module level: no module under inodefence/ui imports
    # fastapi/uvicorn at module level (tests/test_ui_without_rich.py), and this submodule is loaded
    # only by the lazy create_app()/run() entry. Request and the responses come from starlette at
    # module level so FastAPI can resolve the route handlers' annotations.
    from fastapi import FastAPI, HTTPException

    resolved_roots: tuple[Path, ...] = (
        tuple(runs_app.default_roots()) if roots is None else tuple(Path(r) for r in roots)
    )
    scan_roots = (*resolved_roots, *extra)
    registry = RunRegistry(resolved_roots, extra=extra)
    health = HealthCache(check=lambda: _default_health_check(repo_root))
    follower = events_app.RunFollower(roots=scan_roots, interval=FOLLOW_INTERVAL_SECONDS)
    # Set on lifespan shutdown so the SSE generator leaves its ``while`` loop instead of polling the
    # follower forever: without it an open ``/api/events`` stream keeps the server alive on Ctrl-C.
    shutting_down = asyncio.Event()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        shutting_down.clear()
        follower.start()
        try:
            yield
        finally:
            shutting_down.set()
            follower.stop()

    app = FastAPI(
        title="InodeFence dashboard",
        version=API_SCHEMA,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.registry = registry
    app.state.health = health
    app.state.follower = follower
    app.state.shutting_down = shutting_down
    app.state.repo_root = repo_root

    def read_snapshot(ref: runs_app.RunRef) -> runs_app.RunSnapshot:
        # No cache yet (correctness first; the scan cap bounds cost). An mtime-keyed memory cache is
        # a follow-up -- allowed by the spec, never written to disk.
        return runs_app.read_run(ref)

    def bounded_runs(limit: int) -> tuple[list[runs_app.RunListing], int, int]:
        limit = max(1, min(limit, FINDINGS_MAX_LIMIT))
        listings = [item for item in registry.scan().listings if item.ref is not None]
        total = len(listings)
        chosen = listings[:limit]
        return chosen, total, limit

    @app.get("/api/health")
    def api_health() -> dict[str, Any]:
        payload = _health_payload(health)
        payload["roots"] = [str(root) for root in scan_roots]
        return payload

    @app.get("/api/targets")
    def api_targets() -> dict[str, Any]:
        if repo_root is None:
            return {
                "schema": API_SCHEMA,
                "state": "unavailable",
                "reason": "no repository root configured",
                "targets": {},
            }
        try:
            registry_data = targets_app.load(repo_root)
        except Exception as exc:  # noqa: BLE001 - a bad clone must make the page empty, not 500
            return {
                "schema": API_SCHEMA,
                "state": "unavailable",
                "reason": f"target registry not readable: {exc}",
                "targets": {},
            }
        return {"schema": API_SCHEMA, "state": "ok", "targets": to_jsonable(registry_data)}

    @app.get("/api/runs")
    def api_runs(limit: int = FINDINGS_DEFAULT_LIMIT) -> dict[str, Any]:
        limit = max(1, min(limit, FINDINGS_MAX_LIMIT))
        listings = registry.scan().listings
        with_ref = [item for item in listings if item.ref is not None]
        unreadable = [_listing_payload(item) for item in listings if item.ref is None]
        total = len(with_ref)
        runs: list[dict[str, Any]] = []
        for index, item in enumerate(with_ref):
            payload = _listing_payload(item)
            if index < limit:
                snapshot = read_snapshot(item.ref)  # type: ignore[arg-type]  (ref is not None)
                payload["target"] = snapshot.ref.target or payload["target"]
                payload["version"] = snapshot.ref.version or payload["version"]
                payload["status"] = _run_status(snapshot)
            else:
                payload["status"] = None
            runs.append(payload)
        return {
            "schema": API_SCHEMA,
            "roots": [str(root) for root in scan_roots],
            "runs": runs,
            "unreadable": unreadable,
            "runs_total": total,
            "runs_scanned": min(limit, total),
            "truncated": total > limit,
            "limit": limit,
        }

    @app.get("/api/runs/{ident}")
    def api_run(ident: str) -> dict[str, Any]:
        ref = registry.resolve(ident)
        if ref is None:
            raise HTTPException(status_code=404, detail="unknown run id")
        snapshot = read_snapshot(ref)
        return {
            "schema": API_SCHEMA,
            "id": ident,
            "progress_age_seconds": snapshot.progress_age(),
            "stalled": _stalled(snapshot),
            "snapshot": to_jsonable(snapshot),
        }

    @app.get("/api/findings")
    def api_findings(limit: int = FINDINGS_DEFAULT_LIMIT) -> dict[str, Any]:
        chosen, total, limit = bounded_runs(limit)
        findings: list[dict[str, Any]] = []
        for listing in chosen:
            ref = listing.ref
            assert ref is not None  # bounded_runs keeps only listings with a ref
            snapshot = read_snapshot(ref)
            ident = run_id(ref)
            summary = snapshot.summary
            for row in snapshot.findings:
                findings.append(
                    {
                        "run_id": ident,
                        "run_kind": ref.kind.value,
                        "target": snapshot.ref.target,
                        "version": snapshot.ref.version,
                        "validated": summary.validated if summary else None,
                        "read_state": summary.read_state.value if summary else None,
                        "case": to_jsonable(row),
                    }
                )
        return {
            "schema": API_SCHEMA,
            "findings": findings,
            "runs_total": total,
            "runs_scanned": len(chosen),
            "truncated": total > len(chosen),
            "limit": limit,
        }

    @app.get("/api/replays")
    def api_replays(limit: int = FINDINGS_DEFAULT_LIMIT) -> dict[str, Any]:
        chosen, total, limit = bounded_runs(limit)
        replays: list[dict[str, Any]] = []
        seen: set[str] = set()
        for listing in chosen:
            ref = listing.ref
            assert ref is not None
            snapshot = read_snapshot(ref)
            ident = run_id(ref)
            for record in snapshot.replays:
                key = str(record.path)
                if key in seen:
                    continue
                seen.add(key)
                replays.append(
                    {
                        "run_id": ident,
                        "run_kind": ref.kind.value,
                        "target": snapshot.ref.target,
                        "version": snapshot.ref.version,
                        "replay": to_jsonable(record),
                    }
                )
        return {
            "schema": API_SCHEMA,
            "replays": replays,
            "runs_total": total,
            "runs_scanned": len(chosen),
            "truncated": total > len(chosen),
            "limit": limit,
        }

    @app.get("/api/artifacts/{ident}")
    def api_artifacts(ident: str) -> dict[str, Any]:
        ref = registry.resolve(ident)
        if ref is None:
            raise HTTPException(status_code=404, detail="unknown run id")
        snapshot = read_snapshot(ref)
        return {
            "schema": API_SCHEMA,
            "id": ident,
            "kind": ref.kind.value,
            "artifacts": [to_jsonable(entry) for entry in runs_app.list_artifacts(snapshot)],
            "note": "metadata only; inputs are not re-checked and file contents are never served",
        }

    @app.get("/api/events")
    async def api_events(request: Request) -> StreamingResponse:
        subscription = follower.subscribe()

        async def stream():
            try:
                yield ": connected\n\n"
                # Leave the loop on client disconnect OR server shutdown; the short poll timeout
                # bounds how long either takes to be noticed (one SSE_POLL_TIMEOUT_SECONDS at most).
                while not shutting_down.is_set():
                    if await request.is_disconnected():
                        break
                    event = await run_in_threadpool(subscription.get, SSE_POLL_TIMEOUT_SECONDS)
                    if event is None:
                        yield ": keepalive\n\n"
                        continue
                    yield f"data: {event.to_json_line()}\n\n"
            finally:
                subscription.close()

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/theme.css")
    def theme_css() -> Response:
        # One palette for every screen: the web never re-writes a colour value, it serves the
        # shared theme module's CSS custom properties (``--if-*``).
        return Response(content=theme.css_variables(), media_type="text/css")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


__all__ = ["HealthCache", "build_app"]
