"""The FastAPI app: GET-only JSON over :mod:`inodefence.app`, an SSE event stream, static files.

Imported only through :func:`inodefence.ui.web.create_app`, which has already checked that FastAPI
is installed. Nothing here starts, stops, deletes or replays a run, runs an extractor, or serves a
stored input's bytes; every value comes from the shared read model and is serialised unchanged
(:func:`._serialize.to_jsonable`). Run identity in URLs is an opaque id (:mod:`._ids`): the server
resolves it against its own last scan, so no path is ever accepted from the client.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from inodefence.app import doctor as doctor_app
from inodefence.app import events as events_app
from inodefence.app import runs as runs_app
from inodefence.app import targets as targets_app
from inodefence.ui import theme

from . import API_SCHEMA
from ._ids import RunRegistry, run_id
from ._serialize import to_jsonable

STATIC_DIR = Path(__file__).parent / "static"
HEALTH_TTL_SECONDS = 30.0
FINDINGS_DEFAULT_LIMIT = 200
FINDINGS_MAX_LIMIT = 500
FOLLOW_INTERVAL_SECONDS = 1.0
SSE_POLL_TIMEOUT_SECONDS = 1.0


def _default_health_check(repo_root: Path | None) -> doctor_app.Report:
    """The real doctor report (read-only checks). ``repo_root`` is accepted for a uniform seam."""
    from inodefence.user_config import UserConfigError, load_user_config

    try:
        config = load_user_config()
        config_error = None
    except (UserConfigError, OSError) as exc:
        config, config_error = None, str(exc)
    return doctor_app.run(config, config_error, details=False)


class HealthCache:
    """A memory-only, TTL cache of the doctor report; refreshed off-thread, never on disk.

    The first read returns nothing (the route shows "checking") and starts the first check in the
    background; later reads return the last report with its age, and start a refresh when it is
    older than ``ttl``. A check that raises leaves the previous report in place.
    """

    def __init__(
        self,
        check: Callable[[], doctor_app.Report],
        *,
        ttl: float = HEALTH_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._check = check
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._report: doctor_app.Report | None = None
        self._checked_at: float | None = None
        self._refreshing = False

    def snapshot(self) -> tuple[doctor_app.Report | None, float | None]:
        now = self._clock()
        start = False
        with self._lock:
            fresh = self._checked_at is not None and (now - self._checked_at) < self._ttl
            if not fresh and not self._refreshing:
                self._refreshing = True
                start = True
            report, checked_at = self._report, self._checked_at
        if start:
            threading.Thread(target=self._refresh, name="inodefence-ui-health", daemon=True).start()
        return report, checked_at

    def _refresh(self) -> None:
        report: doctor_app.Report | None = None
        try:
            report = self._check()
        except Exception:  # noqa: BLE001 - a doctor failure must not kill the refresh thread
            report = None
        with self._lock:
            if report is not None:
                self._report = report
                self._checked_at = self._clock()
            self._refreshing = False


def _health_payload(cache: HealthCache) -> dict[str, Any]:
    report, checked_at = cache.snapshot()
    if report is None:
        return {
            "schema": API_SCHEMA,
            "state": "checking",
            "report": None,
            "summary": None,
            "exit_code": None,
            "failed": None,
            "unknown": None,
            "checked_at": None,
            "age_seconds": None,
        }
    age = None if checked_at is None else max(time.time() - checked_at, 0.0)
    return {
        "schema": API_SCHEMA,
        "state": "ok",
        "report": to_jsonable(report),
        "summary": report.summary,
        "exit_code": report.exit_code,
        "failed": report.failed,
        "unknown": report.unknown,
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


def _artifacts_for(snapshot: runs_app.RunSnapshot) -> list[dict[str, Any]]:
    """Artifact paths already named in the snapshot (no new filesystem access, no size/mtime yet).

    A richer list (kinds, size, mtime, shared with the TUI) belongs in the app layer; this derives
    only what the read model already exposes. Contents are never read or served.
    """
    out: list[dict[str, Any]] = []
    summary = snapshot.summary
    if summary is not None and summary.result_path is not None:
        out.append(
            {
                "kind": "result",
                "path": str(summary.result_path),
                "read_state": summary.read_state.value,
            }
        )
    if snapshot.launcher_log is not None:
        out.append({"kind": "launcher_log", "path": str(snapshot.launcher_log), "read_state": None})
    for record in snapshot.replays:
        out.append(
            {"kind": "replay", "path": str(record.path), "read_state": record.read_state.value}
        )
    return out


def _count_findings(snapshot: runs_app.RunSnapshot, finding: runs_app.FindingClass) -> int:
    return sum(1 for row in snapshot.findings if row.finding is finding)


def _run_status(snapshot: runs_app.RunSnapshot) -> dict[str, Any]:
    """A compact per-run status for the runs table and the Overview aggregates (no recompute).

    Separate axes stay separate (termination counts, verdict, candidate counts); every missing
    value is ``None`` (shown as "-"/"?"), never ``0``. The full record is at ``/api/runs/{id}``.
    """
    progress = snapshot.progress
    summary = snapshot.summary
    return {
        "state": progress.state if progress else None,
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
        "terminations": to_jsonable(summary.terminations) if summary else {},
        "candidates": _count_findings(snapshot, runs_app.FindingClass.CANDIDATE),
        "candidates_needs_repro": _count_findings(
            snapshot, runs_app.FindingClass.CANDIDATE_NEEDS_REPRO_CHECK
        ),
        "replays": len(snapshot.replays),
        "progress_age_seconds": snapshot.progress_age(),
    }


def _inputs_for(snapshot: runs_app.RunSnapshot) -> list[dict[str, Any]]:
    summary = snapshot.summary
    if summary is None or summary.integrity is None:
        return []
    return [
        {"case_id": case_id, "tar_sha256": sha, "path": str(path), "rechecked": False}
        for case_id, sha, path in summary.integrity.inputs
    ]


def build_app(
    *,
    roots: Iterable[Path] | None,
    extra: tuple[Path, ...],
    repo_root: Path | None,
) -> FastAPI:
    resolved_roots: tuple[Path, ...] = (
        tuple(runs_app.default_roots()) if roots is None else tuple(Path(r) for r in roots)
    )
    scan_roots = (*resolved_roots, *extra)
    registry = RunRegistry(resolved_roots, extra=extra)
    health = HealthCache(check=lambda: _default_health_check(repo_root))
    follower = events_app.RunFollower(roots=scan_roots, interval=FOLLOW_INTERVAL_SECONDS)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        follower.start()
        try:
            yield
        finally:
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
        return _health_payload(health)

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
            for row in snapshot.findings:
                findings.append(
                    {
                        "run_id": ident,
                        "run_kind": ref.kind.value,
                        "target": snapshot.ref.target,
                        "version": snapshot.ref.version,
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
            "artifacts": _artifacts_for(snapshot),
            "inputs": _inputs_for(snapshot),
            "note": "inputs not re-checked; file contents are never served",
        }

    @app.get("/api/events")
    async def api_events(request: Request) -> StreamingResponse:
        subscription = follower.subscribe()

        async def stream():
            try:
                yield ": connected\n\n"
                while True:
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
