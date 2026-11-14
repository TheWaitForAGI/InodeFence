"""Mid-run observability for a running exploration: progress snapshot + immediate violation cases.

A long exploration (HOST3) must be checkable while it runs, without waiting for ``result.json``:

- **Progress snapshot** -- ``<live>/progress.json``, rewritten every ``every_runs`` steps, every
  ``every_seconds`` (checked at step boundaries), right after each violation, and at the end. It is
  written to a temporary file and moved into place with :func:`os.replace`, so a reader at any
  moment sees one complete point-in-time snapshot. It only reports what the loop already knows per
  step (counts, rates, run identity); nothing is re-observed or inferred.
- **Violation cases** -- each violating step is written the moment it happens, under
  ``<live>/violations/run-NNNNNN/`` (``input.tar`` + ``case.json``). The directory is assembled as
  a dot-prefixed temporary directory and published with one :func:`os.rename`, so a half-written
  case is never visible; readers ignore dot-names. Repeats of the same violation fingerprint are
  counted, but files are written only for the first ``per_fingerprint_cap`` steps per fingerprint.
  If the run dies, everything written so far stays.
- **Host pull** -- the exploration runs inside the controller container, so :class:`LivePuller`
  copies the live folder to the host with ``docker cp`` on a timer (no mount, no isolation or
  controller change). A failed pull never stops the exploration; it is recorded in a separate
  host-only ``<live>/fetch.json`` (``progress.json`` is overwritten by every successful pull).
- **Reading** -- :func:`render_live_status` (``inodefence status``) shows both files and the case
  list.

The recorder is target-agnostic: a loop turns its own step object into a neutral :class:`LiveStep`
with a small adapter (node-tar: :func:`inodefence.live_effect.live_step_from_effect`). A
violation here is a *candidate* the oracle flagged, not a confirmed vulnerability.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

PROGRESS_SCHEMA = "inodefence-live-progress-v1"
CASE_SCHEMA = "inodefence-live-violation-v1"
FETCH_SCHEMA = "inodefence-live-fetch-v1"
PROGRESS_FILE = "progress.json"
FETCH_FILE = "fetch.json"
VIOLATIONS_DIR = "violations"
CASE_FILE = "case.json"
CASE_TAR = "input.tar"
#: Run states written to ``progress.json``. ``failed`` means the loop raised; files so far remain.
STATES = ("running", "finished", "stopped", "failed")
#: Execution statuses a step may report (mirrors ``model.results.ExecutionStatus`` values).
STATUSES = ("success", "rejected", "failed", "timed_out")
CONTRACT_KEYS = ("c0", "c1", "c2")
REPLAY_NOTE = (
    "no single-TAR replay entry exists yet; the input and its run identity are recorded here"
)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat(timespec="seconds")


def _parse_iso(text: object) -> float | None:
    if not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to a sibling temporary file, then move it over ``path`` in one step."""
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _dump(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True, slots=True)
class LiveStep:
    """One completed exploration step, in a form every target's loop can produce.

    ``index`` is the loop's 0-based step index (run number = ``index + 1``). ``c0``..``c2`` are the
    oracle's verdicts for the contracts it judged (``None`` = not judged on this step). ``unjudged``
    means the observation was unusable, so the oracle could not rule at all (a silent negative, not
    a clean run). ``fingerprints`` are the ids of every violation class this step showed;
    ``new_fingerprints`` the ones first seen on this step. ``tar_bytes`` is the exact input and is
    required when the step violated. ``observation`` holds short oracle explanations and
    ``observation_complete`` whether the observation behind the verdicts was complete.
    ``status`` (termination) and the verdicts are independent axes: a rejected, crashed or timed-out
    run the oracle judged keeps its verdicts; ``unjudged`` means the oracle was not evaluated.
    """

    index: int
    case_id: str
    status: str
    c0: bool | None = None
    c1: bool | None = None
    c2: bool | None = None
    unjudged: bool = False
    parent_case_id: str | None = None
    origin: str = "seed"
    mutation: str | None = None
    mutation_applied: bool | None = None
    fingerprints: tuple[str, ...] = ()
    new_fingerprints: tuple[str, ...] = ()
    tar_bytes: bytes | None = None
    observation: tuple[str, ...] = ()
    observation_complete: bool | None = None

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("LiveStep.index must be a non-negative integer")
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("LiveStep.case_id must be a non-empty string")
        if self.status not in STATUSES:
            raise ValueError(f"LiveStep.status must be one of {STATUSES}, got {self.status!r}")
        if self.violated and self.tar_bytes is None:
            raise ValueError("a violating LiveStep must carry its input tar_bytes")

    @property
    def violated(self) -> bool:
        return self.c0 is True or self.c1 is True or self.c2 is True

    @property
    def needs_repro_check(self) -> bool:
        """A violation seen when the target did not succeed or the observation was incomplete
        (same rule as ``CaseVerdict.needs_repro_check``): still a violation, check it first."""
        return self.violated and (self.status != "success" or self.observation_complete is not True)

    @property
    def contracts(self) -> dict[str, bool | None]:
        return {"c0": self.c0, "c1": self.c1, "c2": self.c2}


@dataclass(frozen=True, slots=True)
class LiveRunMeta:
    """Identity of the run, copied into every snapshot and case record.

    ``replay_template`` is an optional one-line command with ``{tar}`` (path of the case's
    ``input.tar`` relative to the live folder), ``{image_id}`` and ``{version}`` placeholders. It is
    ``None`` until a target provides a single-TAR replay entry; case records then say so plainly
    instead of inventing a command.
    """

    target: str
    version: str
    seed: int
    budget: int | None
    image_id: str | None = None
    search_policy: str | None = None
    vocab_mode: str | None = None
    engine_commit: str | None = None
    replay_template: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "version": self.version,
            "seed": self.seed,
            "budget": self.budget,
            "image_id": self.image_id,
            "search_policy": self.search_policy,
            "vocab_mode": self.vocab_mode,
            "engine_commit": self.engine_commit,
        }


def fingerprint_id(contract: str, canonical: str) -> str:
    """A short stable id for one violation class: ``<contract>-<16 hex of sha256>``."""
    return f"{contract}-{sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


@dataclass
class _Counters:
    runs: int = 0
    violation_steps: int = 0
    unjudged: int = 0
    terminations: dict[str, int] = field(default_factory=lambda: {status: 0 for status in STATUSES})
    first_violation_run: int | None = None
    last_violation_run: int | None = None
    case_dirs_written: int = 0
    by_fingerprint: dict[str, int] = field(default_factory=dict)
    write_errors: int = 0
    last_write_error: str | None = None


class LiveRecorder:
    """Consume :class:`LiveStep` records and keep ``progress.json`` and violation cases current.

    Call :meth:`on_step` once per completed step (from the loop's ``on_step`` hook) and
    :meth:`close` once at the end -- in a ``finally`` with ``state="failed"`` when the loop raised,
    so the last snapshot says how the run ended. A write error (full disk, permissions) does not
    stop the exploration; it is counted and shown in the snapshot (``write_errors``), never
    swallowed silently.
    """

    def __init__(
        self,
        live_dir: Path,
        meta: LiveRunMeta,
        *,
        every_runs: int = 25,
        every_seconds: float = 30.0,
        per_fingerprint_cap: int = 3,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if type(every_runs) is not int or every_runs < 1:
            raise ValueError("every_runs must be an integer >= 1")
        if every_seconds <= 0:
            raise ValueError("every_seconds must be > 0")
        if type(per_fingerprint_cap) is not int or per_fingerprint_cap < 0:
            raise ValueError("per_fingerprint_cap must be an integer >= 0")
        self.live_dir = live_dir
        self.meta = meta
        self.every_runs = every_runs
        self.every_seconds = every_seconds
        self.per_fingerprint_cap = per_fingerprint_cap
        self._clock = clock
        self._started = clock()
        self._counters = _Counters()
        self._state = "running"
        self._stop_reason: str | None = None
        self._last_written_runs = 0
        self._last_written_at = self._started
        self._closed = False
        (live_dir / VIOLATIONS_DIR).mkdir(parents=True, exist_ok=True)
        self._write_progress()  # a fresh run is visible (state=running, 0 runs) before step 1

    # -- feeding ---------------------------------------------------------------------------------
    def on_step(self, step: LiveStep) -> None:
        if self._closed:
            raise RuntimeError("LiveRecorder is closed")
        c = self._counters
        c.runs = max(c.runs, step.index + 1)
        if step.unjudged:
            c.unjudged += 1
        c.terminations[step.status] += 1
        wrote_case = False
        if step.violated:
            run = step.index + 1
            c.violation_steps += 1
            c.first_violation_run = c.first_violation_run or run
            c.last_violation_run = run
            keep = not step.fingerprints  # a violation with no fingerprint is always kept
            for fp in step.fingerprints:
                c.by_fingerprint[fp] = c.by_fingerprint.get(fp, 0) + 1
                if c.by_fingerprint[fp] <= self.per_fingerprint_cap:
                    keep = True
            if keep and self.per_fingerprint_cap > 0:
                wrote_case = self._write_case(step)
        now = self._clock()
        due = (
            wrote_case
            or step.violated
            or c.runs - self._last_written_runs >= self.every_runs
            or now - self._last_written_at >= self.every_seconds
        )
        if due:
            self._write_progress(now)

    def close(self, *, state: str = "finished", stop_reason: str | None = None) -> None:
        """Write the final snapshot. ``state`` is ``finished``, ``stopped`` or ``failed``."""
        if state not in STATES or state == "running":
            raise ValueError(f"close state must be one of {STATES[1:]}")
        if self._closed:
            return
        self._state = state
        self._stop_reason = stop_reason
        self._write_progress()
        self._closed = True

    # -- views -----------------------------------------------------------------------------------
    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        now = self._clock() if now is None else now
        c = self._counters
        elapsed = max(now - self._started, 0.0)
        return {
            "schema": PROGRESS_SCHEMA,
            "state": self._state,
            "stop_reason": self._stop_reason,
            "started_at": _iso(self._started),
            "updated_at": _iso(now),
            "elapsed_seconds": round(elapsed, 3),
            "runs_executed": c.runs,
            "runs_per_second": round(c.runs / elapsed, 3) if elapsed > 0 else None,
            "violations": {
                "steps": c.violation_steps,
                "unique_fingerprints": len(c.by_fingerprint),
                "case_dirs_written": c.case_dirs_written,
                "first_at_run": c.first_violation_run,
                "last_at_run": c.last_violation_run,
                "by_fingerprint": dict(sorted(c.by_fingerprint.items())),
                "per_fingerprint_cap": self.per_fingerprint_cap,
            },
            "unjudged": {
                "steps": c.unjudged,
                "ratio": round(c.unjudged / c.runs, 6) if c.runs else 0.0,
            },
            # The termination axis, apart from judgment: "almost everything is rejected" and
            # "nothing could be judged" must read differently at a glance.
            "terminations": dict(c.terminations),
            "write_errors": c.write_errors,
            "last_write_error": c.last_write_error,
            "snapshot_every": {"runs": self.every_runs, "seconds": self.every_seconds},
            **self.meta.as_dict(),
        }

    # -- writing ---------------------------------------------------------------------------------
    def _note_write_error(self, what: str, error: OSError) -> None:
        self._counters.write_errors += 1
        self._counters.last_write_error = f"{what}: {error}"

    def _write_progress(self, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        try:
            _atomic_write_text(self.live_dir / PROGRESS_FILE, _dump(self.snapshot(now)))
        except OSError as error:
            self._note_write_error("progress", error)
            return
        self._last_written_runs = self._counters.runs
        self._last_written_at = now

    def _write_case(self, step: LiveStep) -> bool:
        assert step.tar_bytes is not None  # guaranteed by LiveStep for a violating step
        run = step.index + 1
        name = f"run-{run:06d}"
        violations = self.live_dir / VIOLATIONS_DIR
        final = violations / name
        if final.exists():
            return False
        tmp = violations / f".tmp-{name}-{os.getpid()}"
        rel_tar = f"{VIOLATIONS_DIR}/{name}/{CASE_TAR}"
        replay = None
        if self.meta.replay_template is not None:
            replay = self.meta.replay_template.format(
                tar=rel_tar, image_id=self.meta.image_id or "", version=self.meta.version
            )
        record = {
            "schema": CASE_SCHEMA,
            "run": run,
            "index": step.index,
            "case_id": step.case_id,
            "parent_case_id": step.parent_case_id,
            "origin": step.origin,
            "mutation": step.mutation,
            "mutation_applied": step.mutation_applied,
            "status": step.status,
            **step.contracts,
            "unjudged": step.unjudged,
            "fingerprints": list(step.fingerprints),
            "new_fingerprints": list(step.new_fingerprints),
            "observation": list(step.observation),
            "observation_complete": step.observation_complete,
            "needs_repro_check": step.needs_repro_check,
            "tar": CASE_TAR,
            "tar_sha256": sha256(step.tar_bytes).hexdigest(),
            "tar_bytes": len(step.tar_bytes),
            "replay": replay,
            "replay_note": None if replay is not None else REPLAY_NOTE,
            "recorded_at": _iso(self._clock()),
            **self.meta.as_dict(),
        }
        try:
            if tmp.exists():
                shutil.rmtree(tmp)
            tmp.mkdir()
            (tmp / CASE_TAR).write_bytes(step.tar_bytes)
            (tmp / CASE_FILE).write_text(_dump(record), encoding="utf-8")
            os.rename(tmp, final)
        except OSError as error:
            self._note_write_error(f"violation {name}", error)
            shutil.rmtree(tmp, ignore_errors=True)
            return False
        self._counters.case_dirs_written += 1
        return True


# -- host side ---------------------------------------------------------------------------------


Runner = Callable[..., subprocess.CompletedProcess[Any]]


class LivePuller:
    """Copy a container's live folder to the host on a timer with ``docker cp``.

    ``pull_once`` copies ``<container>:<container_live_dir>/.`` into a staging folder next to
    ``host_live_dir``, then promotes it: ``progress.json`` is moved over the host copy in one step,
    and each complete violation case (a non-dot ``run-*`` folder holding ``case.json``) not yet on
    the host is moved in. Staging sits beside the live folder so promotion is a same-filesystem
    rename. Any failure is recorded in ``<host_live_dir>/fetch.json`` and returned as ``False``;
    nothing here raises into the exploration.
    """

    def __init__(
        self,
        container: str,
        container_live_dir: str,
        host_live_dir: Path,
        *,
        interval: float = 15.0,
        timeout: float = 60.0,
        runner: Runner = subprocess.run,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if interval <= 0:
            raise ValueError("interval must be > 0")
        self.container = container
        self.container_live_dir = container_live_dir.rstrip("/") or "/"
        self.host_live_dir = host_live_dir
        self.interval = interval
        self.timeout = timeout
        self._runner = runner
        self._clock = clock
        self._ok = 0
        self._failed = 0
        self._last_ok: float | None = None
        self._last_error_at: float | None = None
        self._last_error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _staging(self) -> Path:
        return self.host_live_dir.parent / f".{self.host_live_dir.name}.pull-tmp"

    def pull_once(self) -> bool:
        staging = self._staging()
        try:
            self.host_live_dir.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True)
            done = self._runner(
                ["docker", "cp", f"{self.container}:{self.container_live_dir}/.", str(staging)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            if done.returncode != 0:
                detail = (done.stderr or done.stdout or "").strip().splitlines()
                raise RuntimeError(
                    f"docker cp exit {done.returncode}" + (f": {detail[-1]}" if detail else "")
                )
            self._promote(staging)
        except Exception as error:  # noqa: BLE001 -- a pull must never stop the exploration
            self._failed += 1
            self._last_error_at = self._clock()
            self._last_error = f"{type(error).__name__}: {error}"
            self._write_fetch()
            return False
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        self._ok += 1
        self._last_ok = self._clock()
        self._write_fetch()
        return True

    def _promote(self, staging: Path) -> None:
        progress = staging / PROGRESS_FILE
        if progress.is_file():
            os.replace(progress, self.host_live_dir / PROGRESS_FILE)
        source = staging / VIOLATIONS_DIR
        if not source.is_dir():
            return
        dest = self.host_live_dir / VIOLATIONS_DIR
        dest.mkdir(parents=True, exist_ok=True)
        for case in sorted(source.iterdir()):
            if case.name.startswith(".") or not (case / CASE_FILE).is_file():
                continue  # in-progress (dot) or incomplete: wait for the next pull
            target = dest / case.name
            if not target.exists():
                os.rename(case, target)

    def _write_fetch(self) -> None:
        data = {
            "schema": FETCH_SCHEMA,
            "container": self.container,
            "container_live_dir": self.container_live_dir,
            "interval_seconds": self.interval,
            "pulls_ok": self._ok,
            "pulls_failed": self._failed,
            "last_ok_at": _iso(self._last_ok) if self._last_ok is not None else None,
            "last_error_at": _iso(self._last_error_at) if self._last_error_at is not None else None,
            "last_error": self._last_error,
            "updated_at": _iso(self._clock()),
        }
        try:
            _atomic_write_text(self.host_live_dir / FETCH_FILE, _dump(data))
        except OSError:
            pass  # the host folder itself is unwritable; status will show no fetch.json

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self.pull_once()

    def start(self) -> LivePuller:
        if self._thread is not None:
            raise RuntimeError("LivePuller already started")
        self._thread = threading.Thread(target=self._loop, name="inodefence-live-pull", daemon=True)
        self._thread.start()
        return self

    def stop(self, *, final_pull: bool = True) -> None:
        """Stop the timer; by default pull once more so the final snapshot reaches the host."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.timeout + self.interval)
            self._thread = None
        if final_pull:
            self.pull_once()


# -- reading -----------------------------------------------------------------------------------


def _read_json(path: Path, schema: str) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != schema:
        return None
    return data


def read_progress(live_dir: Path) -> dict[str, Any] | None:
    return _read_json(live_dir / PROGRESS_FILE, PROGRESS_SCHEMA)


def read_fetch(live_dir: Path) -> dict[str, Any] | None:
    return _read_json(live_dir / FETCH_FILE, FETCH_SCHEMA)


def list_violation_cases(live_dir: Path) -> list[dict[str, Any]]:
    """Complete violation case records, oldest run first (in-progress dot folders are skipped)."""
    folder = live_dir / VIOLATIONS_DIR
    if not folder.is_dir():
        return []
    cases = []
    for case in sorted(folder.iterdir()):
        if case.name.startswith(".") or not case.is_dir():
            continue
        record = _read_json(case / CASE_FILE, CASE_SCHEMA)
        if record is not None:
            record["dir"] = f"{VIOLATIONS_DIR}/{case.name}"
            cases.append(record)
    return sorted(cases, key=lambda record: record.get("run", 0))


def find_live_dirs(folder: Path) -> list[Path]:
    """Live folders under an exploration output folder: itself, ``live/``, or ``*/live/``."""
    if (folder / PROGRESS_FILE).is_file() or (folder / FETCH_FILE).is_file():
        return [folder]
    found = [folder / "live"] if (folder / "live").is_dir() else []
    found += sorted(p for p in folder.glob("*/live") if p.is_dir())
    return found


def _ago(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    seconds = max(seconds, 0.0)
    if seconds < 120:
        return f"{seconds:.0f}s ago"
    if seconds < 7200:
        return f"{seconds / 60:.0f}m ago"
    return f"{seconds / 3600:.1f}h ago"


def _contracts_hit(record: Mapping[str, Any]) -> str:
    hit = [key.upper() for key in CONTRACT_KEYS if record.get(key) is True]
    return "+".join(hit) or "-"


def render_live_status(
    live_dir: Path, *, now: float | None = None, max_cases: int = 20, display: str | None = None
) -> str:
    """A short human view of a running (or finished) exploration's live folder."""
    now = time.time() if now is None else now
    shown = display or str(live_dir)
    progress = read_progress(live_dir)
    fetch = read_fetch(live_dir)
    lines: list[str] = []
    if progress is None:
        lines.append(f"{shown}: no progress snapshot yet (or unreadable)")
    else:
        updated = _parse_iso(progress.get("updated_at"))
        age = None if updated is None else now - updated
        every = progress.get("snapshot_every") or {}
        stale_after = max(3 * float(every.get("seconds") or 30.0), 120.0)
        state = progress.get("state")
        head = f"{shown}: {state}"
        if progress.get("stop_reason"):
            head += f" ({progress['stop_reason']})"
        head += f", snapshot {_ago(age)}"
        if state == "running" and age is not None and age > stale_after:
            head += "  ** STALE: no new step written for a while -- is the run stuck? **"
        lines.append(head)
        ident = (
            f"  target={progress.get('target')} version={progress.get('version')} "
            f"seed={progress.get('seed')} budget="
            f"{progress.get('budget') if progress.get('budget') is not None else 'until stopped'}"
        )
        for key in ("image_id", "search_policy", "vocab_mode", "engine_commit"):
            if progress.get(key):
                ident += f" {key}={progress[key]}"
        lines.append(ident)
        v = progress.get("violations") or {}
        u = progress.get("unjudged") or {}
        rate = progress.get("runs_per_second")
        lines.append(
            f"  runs={progress.get('runs_executed')}"
            + (f" ({rate}/s)" if rate is not None else "")
            + f" violations={v.get('steps', 0)} steps / {v.get('unique_fingerprints', 0)} unique"
            + f" un-judged={u.get('steps', 0)} (ratio {u.get('ratio', 0.0)})"
        )
        t = progress.get("terminations") or {}
        lines.append(
            "  ended: "
            + " ".join(f"{name}={t.get(name, 0)}" for name in STATUSES)
            + "  (termination is separate from judgment; un-judged = oracle not evaluated)"
        )
        if v.get("first_at_run") is not None:
            lines.append(
                f"  first violation at run {v['first_at_run']}, last at run {v.get('last_at_run')}"
            )
        if progress.get("write_errors"):
            lines.append(
                f"  ** {progress['write_errors']} write error(s) in the controller; last: "
                f"{progress.get('last_write_error')} **"
            )
    if fetch is not None:
        last_ok = _parse_iso(fetch.get("last_ok_at"))
        text = (
            f"  host pull: {fetch.get('pulls_ok', 0)} ok / {fetch.get('pulls_failed', 0)} failed, "
            f"last ok {_ago(None if last_ok is None else now - last_ok)}"
        )
        if fetch.get("last_error"):
            text += f"; last error: {fetch['last_error']}"
        lines.append(text)
    cases = list_violation_cases(live_dir)
    if cases:
        lines.append(
            f"  violation cases on disk: {len(cases)} (each folder: input.tar + case.json)"
        )
        for record in cases[-max_cases:]:
            fps = record.get("fingerprints") or []
            lines.append(
                f"    run {record.get('run')}: {_contracts_hit(record)}"
                f" ended={record.get('status')}"
                + (" REPRO-CHECK" if record.get("needs_repro_check") else "")
                + f" fp={','.join(fps) if fps else '-'}"
                f" sha256={str(record.get('tar_sha256', ''))[:16]}..."
                f" {record['dir']}/"
            )
        if len(cases) > max_cases:
            lines.append(f"    ... {len(cases) - max_cases} earlier case(s) not listed")
    elif progress is not None:
        lines.append("  violation cases on disk: none yet")
    return "\n".join(lines)


def live_dirs_status(folder: Path, *, now: float | None = None) -> list[str]:
    """Render every live folder found under ``folder`` (empty when there is none)."""
    out = []
    for live in find_live_dirs(folder):
        try:
            display = str(live.relative_to(folder)) if live != folder else str(folder)
        except ValueError:
            display = str(live)
        out.append(render_live_status(live, now=now, display=display))
    return out


__all__: Sequence[str] = (
    "CASE_SCHEMA",
    "FETCH_SCHEMA",
    "PROGRESS_SCHEMA",
    "LivePuller",
    "LiveRecorder",
    "LiveRunMeta",
    "LiveStep",
    "find_live_dirs",
    "fingerprint_id",
    "list_violation_cases",
    "live_dirs_status",
    "read_fetch",
    "read_progress",
    "render_live_status",
)
