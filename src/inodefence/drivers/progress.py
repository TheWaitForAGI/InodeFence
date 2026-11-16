"""Live terminal progress for ``inodefence explore``, read from the existing live layer.

The numbers come from the files a run already writes -- ``live/progress.json`` and the violation
case folders (:mod:`inodefence.live_exploration`, the same readers ``inodefence status`` uses), and
``result.json`` once it exists -- so this display and ``status`` agree by construction. Nothing is
added inside the container, no file format changes, and nothing here feeds back into the run: it
is a host-side thread that stats one small file on a timer.

**Output modes** (``--output`` of the explore driver; ``inodefence explore`` maps its flags):

- ``stream`` (``--verbose``; the driver's own default): the launcher's output goes straight to the
  terminal and no progress line is printed -- exactly the behaviour before this module.
- ``progress`` (the ``inodefence explore`` default): progress lines on **stderr**, the launcher's
  raw output (image build, controller steps) in a log file under ``<out>/runtime/`` whose path is
  printed. The driver's own lines (``TARGET-EXPLORE ...``, ``result: ...``, errors, diagnoses) are
  printed as before, on the same streams.
- ``quiet`` (``--quiet``): as ``progress`` but without progress lines. The final result lines and
  errors still print, and a failure names the log and shows its last lines.

**Display.** One line. On a terminal (stderr is a TTY and ``TERM`` is not ``dumb``) it is redrawn
in place with a plain ``\\r`` at most once per :data:`TTY_INTERVAL` seconds and cut to the terminal
width. Otherwise (pipe, file, CI) a full line is printed when the phase changes, when the counts
changed and :data:`LINE_INTERVAL` seconds have passed since the last line, and as a heartbeat every
:data:`HEARTBEAT_INTERVAL` seconds. No colour or escape sequence is ever written, so ``NO_COLOR``
is honoured trivially.

**Unknown is not zero.** A value the files do not hold is shown as ``?``, never as ``0``:

- Only node-tar writes a live folder today. For the other three targets every count is ``?``
  while the loop runs, and the final line is read from ``result.json``.
- ``progress.json`` has no per-contract counts. ``C0``/``C1``/``C2`` are counted from the violation
  case folders on the host: exact when every violating run has its folder there, a lower bound
  (``C1>=2``) when the per-fingerprint cap or a pending pull holds some back.
- The throughput is the snapshot's own ``runs_per_second`` (what ``status`` shows).

**ETA rule.** An ETA is shown only while the loop runs, from live data, when the budget is known,
at least :data:`ETA_MIN_RUNS` runs are done, and this display has seen at least two distinct
snapshots whose rates differ by at most :data:`ETA_RATE_TOLERANCE` of the newer one. It is
``(budget - runs) / runs_per_second``, the formula of ``status``'s "about T at this rate".
Otherwise no ETA is printed.

**Phases.** ``prepare`` (image lookup / build, worker checks: no launch yet), ``running`` (the
launcher is running and the loop has not ended; this includes the launcher's own controller
set-up before the loop, so ``step=`` shows the launcher's current ``==> [step]`` label),
``cleanup`` (the loop's last snapshot or report is on the host, or the launcher returned and the
result is being written), then ``completed`` or ``aborted``. An ``aborted`` line carries a
one-line cause: the driver's error plus the stage and category of the runtime session's stop
diagnosis (:mod:`inodefence.drivers.runtime.diagnostics`).
"""

from __future__ import annotations

import io
import os
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from inodefence.live_exploration import (
    CONTRACT_KEYS,
    PROGRESS_FILE,
    STATUSES,
    list_violation_cases,
    read_progress,
)

#: The explore driver's ``--output`` values (see the module docstring).
STREAM, PROGRESS, QUIET = "stream", "progress", "quiet"
MODES = (STREAM, PROGRESS, QUIET)

UNKNOWN = "?"
PREFIX = "[explore]"
PREPARE, RUNNING, CLEANUP, COMPLETED, ABORTED = (
    "prepare",
    "running",
    "cleanup",
    "completed",
    "aborted",
)
#: ``progress.json`` states after which the loop no longer runs.
ENDED_STATES = ("finished", "stopped", "failed")

#: Seconds between in-place redraws on a terminal (also the poll period there).
TTY_INTERVAL = 1.0
#: Seconds between polls when not on a terminal.
LINE_POLL_INTERVAL = 2.0
#: Minimum seconds between two non-terminal lines that only report changed counts.
LINE_INTERVAL = 30.0
#: A non-terminal line is printed after this many seconds even when nothing changed.
HEARTBEAT_INTERVAL = 300.0
#: ETA rule (module docstring): runs done, and how far two consecutive snapshot rates may differ.
ETA_MIN_RUNS = 10
ETA_RATE_TOLERANCE = 0.25
#: A live snapshot written this long before this run started belongs to an earlier run: ignored.
STALE_SNAPSHOT_SLACK = 5.0
#: How many of the launcher log's last lines a failure shows.
LOG_TAIL_LINES = 15
LOG_DIR = "runtime"  # beside the runtime record (``drivers.runtime.session.RECORD_DIR``)


def _count(value: object) -> int | None:
    """``value`` as a count, or ``None`` when the file does not really hold one."""
    return value if type(value) is int and value >= 0 else None


def _epoch(text: object) -> float | None:
    if not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def duration(seconds: float) -> str:
    """``45s`` / ``12m`` / ``3.4h`` (the wording of ``inodefence status``)."""
    seconds = max(seconds, 0.0)
    if seconds < 120:
        return f"{seconds:.0f}s"
    if seconds < 7200:
        return f"{seconds / 60:.0f}m"
    return f"{seconds / 3600:.1f}h"


@dataclass(frozen=True, slots=True)
class Counts:
    """What the files say about a run right now; ``None`` means unknown (rendered ``?``)."""

    #: where the numbers were read: ``live`` (progress.json), ``result`` (result.json) or ``none``
    source: str = "none"
    runs: int | None = None
    terminations: Mapping[str, int | None] = field(
        default_factory=lambda: dict.fromkeys(STATUSES, None)
    )
    unjudged: int | None = None
    #: violating runs (``violations.steps``; a candidate the oracle flagged, not a confirmed bug)
    violations: int | None = None
    #: violating runs per contract key (``c0``/``c1``/``c2``)
    contracts: Mapping[str, int | None] = field(
        default_factory=lambda: dict.fromkeys(CONTRACT_KEYS, None)
    )
    #: the per-contract counts are a lower bound (not every violating run's record was readable)
    contracts_lower_bound: bool = False
    runs_per_second: float | None = None
    budget: int | None = None
    #: ``progress.json`` state (``running`` / ``finished`` / ``stopped`` / ``failed``)
    state: str | None = None
    updated_at: float | None = None


def counts_from_progress(
    progress: Mapping[str, Any], cases: Sequence[Mapping[str, Any]] | None
) -> Counts:
    """The counts of one ``progress.json`` snapshot plus the violation cases read beside it.

    ``cases`` is :func:`inodefence.live_exploration.list_violation_cases` of the same folder (or
    ``None`` when it could not be listed). A field the snapshot lacks, or holds with another type,
    stays unknown.
    """
    violations = progress.get("violations")
    unjudged = progress.get("unjudged")
    terminations = progress.get("terminations")
    steps = _count(violations.get("steps")) if isinstance(violations, Mapping) else None
    contracts: dict[str, int | None] = dict.fromkeys(CONTRACT_KEYS, None)
    lower_bound = False
    if steps == 0:
        contracts = dict.fromkeys(CONTRACT_KEYS, 0)
    elif steps is not None and cases is not None:
        contracts = {key: sum(case.get(key) is True for case in cases) for key in CONTRACT_KEYS}
        lower_bound = len(cases) < steps
    rate = progress.get("runs_per_second")
    state = progress.get("state")
    return Counts(
        source="live",
        runs=_count(progress.get("runs_executed")),
        terminations={
            name: _count(terminations.get(name)) if isinstance(terminations, Mapping) else None
            for name in STATUSES
        },
        unjudged=_count(unjudged.get("steps")) if isinstance(unjudged, Mapping) else None,
        violations=steps,
        contracts=contracts,
        contracts_lower_bound=lower_bound,
        runs_per_second=float(rate)
        if isinstance(rate, int | float) and not isinstance(rate, bool)
        else None,
        budget=_count(progress.get("budget")),
        state=state if isinstance(state, str) else None,
        updated_at=_epoch(progress.get("updated_at")),
    )


def read_live_counts(live_dir: Path) -> Counts | None:
    """The live folder's counts, or ``None`` when it has no readable snapshot (yet)."""
    progress = read_progress(live_dir)
    if progress is None:
        return None
    try:
        cases: list[dict[str, Any]] | None = list_violation_cases(live_dir)
    except OSError:
        cases = None
    return counts_from_progress(progress, cases)


def counts_from_result(result_path: Path) -> Counts | None:
    """The counts of a finished run's ``result.json`` (``None`` when it cannot be read).

    ``result.json`` lists every case for a small run and only the saved violating cases for a
    streaming one; the per-contract counts are a lower bound when its ``violation_capture`` says
    some violating runs were held back at the per-fingerprint cap.
    """
    from inodefence.target_result import TargetResultError, load_target_result

    try:
        result = load_target_result(result_path, verify_inputs=False)
    except (TargetResultError, OSError, ValueError):
        return None
    campaign = result.campaign
    capture = campaign.violation_capture if campaign is not None else None
    violating = [case for case in result.cases if case.violated]
    total = _count(capture.get("total")) if isinstance(capture, Mapping) else None
    violations = total if total is not None else len(violating)
    return Counts(
        source="result",
        runs=result.executed,
        terminations=dict(result.termination_counts),
        unjudged=result.unjudged_steps,
        violations=violations,
        contracts={
            key: sum(getattr(case, key) is True for case in violating) for key in CONTRACT_KEYS
        },
        contracts_lower_bound=len(violating) < violations,
        budget=campaign.budget if campaign is not None else None,
    )


class EtaEstimator:
    """Decides whether the evidence supports an ETA (the rule in the module docstring)."""

    def __init__(self) -> None:
        self._seen: list[tuple[float | None, int, float]] = []  # (updated_at, runs, rate)

    def observe(self, counts: Counts) -> None:
        if counts.source != "live" or not counts.runs or not counts.runs_per_second:
            return
        if counts.runs_per_second <= 0:
            return
        sample = (counts.updated_at, counts.runs, counts.runs_per_second)
        if self._seen and self._seen[-1][:2] == sample[:2]:
            return  # the same snapshot read again
        self._seen = [*self._seen[-1:], sample]

    def eta_seconds(self, counts: Counts, phase: str) -> float | None:
        if phase != RUNNING or counts.source != "live" or len(self._seen) < 2:
            return None
        runs, budget, rate = counts.runs, counts.budget, counts.runs_per_second
        if runs is None or budget is None or not rate or rate <= 0:
            return None
        if runs < ETA_MIN_RUNS or runs >= budget:
            return None
        previous, latest = self._seen[-2][2], self._seen[-1][2]
        if abs(latest - previous) > ETA_RATE_TOLERANCE * latest:
            return None
        return (budget - runs) / rate


@dataclass(frozen=True, slots=True)
class View:
    """Everything one progress line shows."""

    phase: str
    target: str
    #: the exact version once the image is prepared; before that the requested spec
    version: str
    version_exact: bool
    profile: str
    seed: int
    budget: int
    out: Path
    counts: Counts = field(default_factory=Counts)
    eta_seconds: float | None = None
    elapsed_seconds: float | None = None
    #: seconds since the live snapshot was written (the numbers are as of then)
    snapshot_age: float | None = None
    verdict: str | None = None
    cause: str | None = None
    #: the launcher's own current step label (its last ``==> [step]`` line in the log), if any
    step: str | None = None
    #: whether the line names the output folder (the header and the last line do)
    show_out: bool = True


def _show(value: int | None) -> str:
    return UNKNOWN if value is None else str(value)


def _segments(view: View) -> list[tuple[int, str]]:
    """The line's parts in display order, each with a keep-priority (0 is dropped last)."""
    counts = view.counts
    version = view.version if view.version_exact else f"{view.version}(requested)"
    head = f"{PREFIX} {view.phase}"
    if view.verdict:
        head += f" verdict={view.verdict}"
    if view.step and view.phase in (RUNNING, CLEANUP):
        head += f" step={view.step}"
    parts = [
        (0, f"{head} runs={_show(counts.runs)}/{view.budget}"),
        (5, f"{view.target} {version} profile={view.profile} seed={view.seed}"),
        (
            1,
            " ".join(f"{name}={_show(counts.terminations.get(name))}" for name in STATUSES)
            + f" un-judged={_show(counts.unjudged)}",
        ),
    ]
    bound = ">=" if counts.contracts_lower_bound else "="
    contract_text = " ".join(
        f"{key.upper()}{'=' if counts.contracts.get(key) is None else bound}"
        f"{_show(counts.contracts.get(key))}"
        for key in CONTRACT_KEYS
    )
    parts.append((2, f"violations={_show(counts.violations)} {contract_text}"))
    rate = counts.runs_per_second
    speed = f"{rate} runs/s" if rate is not None else f"{UNKNOWN} runs/s"
    if view.eta_seconds is not None:
        speed += f" eta~{duration(view.eta_seconds)}"
    parts.append((3, speed))
    if view.elapsed_seconds is not None:
        parts.append((4, f"elapsed={duration(view.elapsed_seconds)}"))
    if view.snapshot_age is not None and view.phase == RUNNING:
        parts.append((6, f"snapshot={duration(view.snapshot_age)} ago"))
    if view.show_out:
        parts.append((7, f"out={view.out}"))
    if view.cause:
        parts.append((0, f"cause: {view.cause}"))
    return parts


def format_line(view: View, width: int | None = None) -> str:
    """One progress line. With ``width`` the least important parts are dropped until it fits
    (identity and output folder first -- the header line already printed them), then it is cut."""
    parts = _segments(view)
    line = " | ".join(text for _, text in parts)
    if width is None:
        return line
    for drop in sorted({priority for priority, _ in parts}, reverse=True):
        if len(line) <= width or drop == 0:
            break
        parts = [part for part in parts if part[0] != drop]
        line = " | ".join(text for _, text in parts)
    return line if len(line) <= width else line[: max(width - 1, 0)] + ">"


def header_line(view: View, log: Path | None) -> str:
    """The one line printed when a run starts: identity, where results go, where the log is."""
    version = view.version if view.version_exact else f"{view.version}(requested)"
    text = (
        f"{PREFIX} {view.target} {version} profile={view.profile} seed={view.seed} "
        f"budget={view.budget}; results: {view.out}"
    )
    if log is not None:
        text += f"; launcher output: {log} (--verbose shows it here)"
    return text


def last_launcher_step(log: Path, tail_bytes: int = 8192) -> str | None:
    """The label of the last ``==> [label]`` line near the end of the launcher log, or ``None``.

    Every launcher announces its steps this way (``step()`` in ``scripts/local_*.sh``). It is shown
    as-is, as a hint of what the launcher is doing; nothing is classified or decided from it.
    """
    try:
        with log.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(stream.tell() - tail_bytes, 0))
            text = stream.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("==> [") and line.endswith("]"):
            return line[5:-1].strip().replace(" ", "-") or None
    return None


def is_terminal(stream: TextIO, environ: Mapping[str, str] | None = None) -> bool:
    """Whether ``stream`` gets the in-place line (a TTY whose ``TERM`` is not ``dumb``)."""
    environ = os.environ if environ is None else environ
    try:
        tty = stream.isatty()
    except (AttributeError, ValueError):
        return False
    return bool(tty) and environ.get("TERM", "") != "dumb"


class Display:
    """Writes progress to one stream: an in-place line on a terminal, rate-limited lines elsewhere.

    ``message`` prints a line that stays (and, on a terminal, first clears the in-place line), so
    the driver's own output never lands in the middle of a status line. All writes take one lock.
    """

    def __init__(
        self,
        stream: TextIO,
        *,
        terminal: bool,
        clock: Callable[[], float] = time.monotonic,
        width: Callable[[], int] | None = None,
    ) -> None:
        self.stream = stream
        self.terminal = terminal
        self._clock = clock
        self._width = width or self._terminal_width
        self._lock = threading.RLock()
        self._drawn = 0  # length of the in-place line currently on the terminal
        self._last_key: object = None
        self._last_phase: str | None = None
        self._last_line_at: float | None = None

    def _terminal_width(self) -> int:
        # COLUMNS first (as the standard library does), then the stream's own terminal. Not
        # shutil.get_terminal_size: it asks file descriptor 1, which is the launcher log here.
        try:
            columns = int(os.environ.get("COLUMNS", ""))
        except ValueError:
            columns = 0
        if columns <= 0:
            try:
                columns = os.get_terminal_size(self.stream.fileno()).columns
            except (OSError, ValueError, AttributeError):
                columns = 0
        return columns if columns > 0 else 80

    def _write(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            pass  # a closed terminal must never stop the run

    def _clear(self) -> None:
        if self._drawn:
            self._write("\r" + " " * self._drawn + "\r")
            self._drawn = 0

    def update(self, view: View) -> bool:
        """Show ``view`` if the mode's rate limit allows it; returns whether anything was written.

        Terminal: redraw in place (the caller polls once per :data:`TTY_INTERVAL`). Elsewhere: a
        line on a phase change, on changed counts once :data:`LINE_INTERVAL` has passed since the
        last line, and as a heartbeat after :data:`HEARTBEAT_INTERVAL`.
        """
        with self._lock:
            if self.terminal:
                line = format_line(view, max(self._width() - 1, 20))
                pad = " " * max(self._drawn - len(line), 0)
                self._write("\r" + line + pad + ("\r" + line if pad else ""))
                self._drawn = len(line)
                return True
            now = self._clock()
            key = (view.phase, view.counts)
            since = None if self._last_line_at is None else now - self._last_line_at
            due = (
                since is None
                or view.phase != self._last_phase
                or (key != self._last_key and since >= LINE_INTERVAL)
                or since >= HEARTBEAT_INTERVAL
            )
            if not due:
                return False
            self._write(format_line(view) + "\n")
            self._last_key, self._last_phase, self._last_line_at = key, view.phase, now
            return True

    def message(self, text: str) -> None:
        """Print ``text`` as lines that stay (clearing the in-place line first)."""
        with self._lock:
            self._clear()
            self._write(text if text.endswith("\n") else text + "\n")

    def passthrough(self, stream: TextIO, text: str) -> None:
        """Write the driver's own output to ``stream`` without tearing the in-place line."""
        with self._lock:
            self._clear()
            try:
                stream.write(text)
                stream.flush()
            except (OSError, ValueError):
                pass

    def final(self, view: View) -> None:
        """The last progress line, always printed and left on the screen."""
        self.message(format_line(view))


class _Passthrough(io.TextIOBase):
    """Stands in for ``sys.stdout`` / ``sys.stderr`` while the file descriptors point at the log.

    The driver's own ``print`` lines still reach the real terminal (through the saved descriptor),
    after the in-place status line is cleared; only inherited child output goes to the log.
    """

    def __init__(self, target: TextIO, display: Display | None) -> None:
        super().__init__()
        self._target = target
        self._display = display

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if self._display is not None:
            self._display.passthrough(self._target, text)
        else:
            self._target.write(text)
            self._target.flush()
        return len(text)

    def flush(self) -> None:
        try:
            self._target.flush()
        except (OSError, ValueError):
            pass

    def isatty(self) -> bool:
        return self._target.isatty()

    def fileno(self) -> int:
        return self._target.fileno()

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return self._target.encoding


class LauncherLog:
    """Send this process's inherited stdout / stderr (file descriptors 1 and 2) to a log file.

    The target hooks start their launcher with the driver's own descriptors, so pointing 1 and 2
    at the log captures the launcher's (and image preparation's) raw output without touching a
    hook or a launcher. ``sys.stdout`` / ``sys.stderr`` are replaced by pass-throughs to the saved
    descriptors, so everything the driver itself prints is unchanged. ``stop`` restores all of it;
    an empty log is removed.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.out: TextIO | None = None  # the real stdout / stderr while redirected
        self.err: TextIO | None = None
        self._saved: tuple[TextIO, TextIO] | None = None
        self._fds: tuple[int, int] | None = None
        self._created_dir = False

    def start(self) -> None:
        self._created_dir = not self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        log_fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            out_fd, err_fd = os.dup(1), os.dup(2)
            os.dup2(log_fd, 1)
            os.dup2(log_fd, 2)
        finally:
            os.close(log_fd)
        self._fds = (out_fd, err_fd)
        self._saved = (sys.stdout, sys.stderr)
        self.out = os.fdopen(out_fd, "w", encoding="utf-8", errors="replace", closefd=False)
        self.err = os.fdopen(err_fd, "w", encoding="utf-8", errors="replace", closefd=False)

    def attach(self, display: Display | None) -> None:
        """Route the driver's own prints to the real streams (through ``display`` if given)."""
        assert self.out is not None and self.err is not None
        sys.stdout = _Passthrough(self.out, display)
        sys.stderr = _Passthrough(self.err, display)

    def stop(self) -> None:
        if self._fds is None or self._saved is None:
            return
        for stream in (sys.stdout, sys.stderr, self.out, self.err):
            try:
                if stream is not None:
                    stream.flush()
            except (OSError, ValueError):
                pass
        out_fd, err_fd = self._fds
        os.dup2(out_fd, 1)
        os.dup2(err_fd, 2)
        os.close(out_fd)
        os.close(err_fd)
        sys.stdout, sys.stderr = self._saved
        self._fds = self._saved = self.out = self.err = None
        try:
            if self.path.stat().st_size == 0:
                self.path.unlink()
                if self._created_dir:
                    self.path.parent.rmdir()
        except OSError:
            pass

    def tail(self, lines: int = LOG_TAIL_LINES) -> list[str]:
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        return text.splitlines()[-lines:]


def stop_cause(session: Any, error: BaseException | None) -> str:
    """One line saying why a run stopped: the error, plus the session's stop diagnosis if any.

    The diagnosis is the ``stop-diagnosis`` finding the runtime session recorded for the launch
    (stage and category, :mod:`inodefence.drivers.runtime.diagnostics`); nothing is re-classified.
    """
    if isinstance(error, KeyboardInterrupt):
        text = "interrupted (Ctrl-C)"
    elif error is None:
        text = "stopped without a result"
    else:
        first = str(error).strip().splitlines()
        text = first[0] if first else type(error).__name__
    for record in reversed(getattr(session, "launches", [])):
        for finding in getattr(record, "findings", []):
            if finding.code == "stop-diagnosis":
                where = " ".join(finding.message.split()[:2])  # "stage=... category=..."
                return f"{text} [{where}]"
    return text


class ExploreProgress:
    """The explore driver's progress display for one run (a no-op in ``stream`` mode).

    The driver calls :meth:`start` before preparing the image, :meth:`prepared` once the exact
    version is known, :meth:`completed` / :meth:`failed` when the hook returned or raised, and
    :meth:`finish` last (after the runtime session was finished, so its diagnosis can be quoted).
    The live folder and the loop report are found through the session's launch record
    (``LaunchArtifacts``), so no target hook is involved.
    """

    def __init__(
        self,
        mode: str,
        *,
        session: Any,
        target: str,
        requested: str,
        seed: int,
        budget: int,
        out: Path,
        stream: TextIO | None = None,
        environ: Mapping[str, str] | None = None,
        wall: Callable[[], float] = time.time,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"output mode must be one of {MODES}, got {mode!r}")
        self.mode = mode
        self.session = session
        self.target = target
        self.version = requested
        self.version_exact = False
        self.seed = seed
        self.budget = budget
        self.out = out
        self._stream = stream
        self._environ = environ
        self._wall = wall
        self._started_wall = wall()
        self._eta = EtaEstimator()
        self._counts = Counts()
        self._stat: tuple[int, int] | None = None
        self._final_phase: str | None = None
        self._frozen = False
        self._result_path: Path | None = None
        self._verdict: str | None = None
        self._error: BaseException | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.display: Display | None = None
        self.log: LauncherLog | None = None

    # ---- what the files say ----

    def _artifacts(self) -> Any:
        launches = getattr(self.session, "launches", [])
        return launches[-1].request.artifacts if launches else None

    def _live_counts(self) -> Counts | None:
        """This run's live counts; re-read only when ``progress.json`` changed on disk."""
        artifacts = self._artifacts()
        live = getattr(artifacts, "live", None)
        if live is None:
            return None
        try:
            stat = (live / PROGRESS_FILE).stat()
        except OSError:
            return None
        key = (stat.st_mtime_ns, stat.st_size)
        if key == self._stat and self._counts.source == "live":
            return self._counts
        counts = read_live_counts(live)
        if counts is None:
            return None
        if (
            counts.updated_at is not None
            and counts.updated_at < self._started_wall - STALE_SNAPSHOT_SLACK
        ):
            return None  # left by an earlier run in the same folder
        self._stat = key
        return counts

    def phase(self) -> str:
        if self._final_phase is not None:
            return self._final_phase
        launches = getattr(self.session, "launches", [])
        if not launches:
            return PREPARE
        record = launches[-1]
        if record.duration_seconds is not None or record.error is not None:
            return CLEANUP  # the launcher returned; the hook is writing the result
        if self._counts.source == "live" and self._counts.state in ENDED_STATES:
            return CLEANUP
        report = getattr(record.request.artifacts, "report", None)
        if report is not None and report.exists():
            return CLEANUP
        return RUNNING

    def view(self) -> View:
        live = None if self._frozen else self._live_counts()
        if live is not None:
            self._counts = live
            self._eta.observe(live)
        phase = self.phase()
        now = self._wall()
        counts = self._counts
        age = None
        if counts.source == "live" and counts.updated_at is not None:
            age = max(now - counts.updated_at, 0.0)
        return View(
            phase=phase,
            target=self.target,
            version=self.version,
            version_exact=self.version_exact,
            profile=str(getattr(self.session.policy.profile, "value", self.session.policy.profile)),
            seed=self.seed,
            budget=self.budget,
            out=self.out,
            counts=counts,
            eta_seconds=self._eta.eta_seconds(counts, phase),
            elapsed_seconds=now - self._started_wall,
            snapshot_age=age,
            verdict=self._verdict if phase == COMPLETED else None,
            cause=stop_cause(self.session, self._error) if phase == ABORTED else None,
            step=last_launcher_step(self.log.path) if self.log is not None else None,
            # the header line and the last line name the folder; the lines between stay short
            show_out=phase in (COMPLETED, ABORTED),
        )

    # ---- the driver's calls ----

    def start(self) -> None:
        if self.mode == STREAM:
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        log = LauncherLog(self.out / LOG_DIR / f"explore-launcher-{stamp}-{os.getpid()}.log")
        try:
            log.start()
        except OSError as error:
            # No log, no redirect: the run goes on with today's streamed output.
            print(
                f"TARGET-EXPLORE PROGRESS: launcher log not created ({error}); "
                "showing the launcher output instead",
                file=sys.stderr,
            )
            self.mode = STREAM
            return
        self.log = log
        if self.mode == PROGRESS:
            stream = self._stream or log.err
            assert stream is not None
            self.display = Display(stream, terminal=is_terminal(stream, self._environ))
        log.attach(self.display)
        if self.display is not None:
            self.display.message(header_line(self.view(), log.path))
            self.display.update(self.view())
            self._thread = threading.Thread(
                target=self._loop, name="inodefence-explore-progress", daemon=True
            )
            self._thread.start()

    def _loop(self) -> None:
        assert self.display is not None
        interval = TTY_INTERVAL if self.display.terminal else LINE_POLL_INTERVAL
        while not self._stop.wait(interval):
            try:
                self.display.update(self.view())
            except Exception:  # noqa: BLE001 - a display fault must never stop the run
                continue

    def prepared(self, version: str) -> None:
        """The image is ready: ``version`` is the exact version this run executes."""
        resolved = version != self.version
        self.version, self.version_exact = version, True
        if self.display is not None and resolved:
            self.display.message(f"{PREFIX} version resolved: {version}")

    def completed(self, result_path: Path, verdict: str) -> None:
        self._result_path, self._verdict = result_path, verdict

    def failed(self, error: BaseException) -> None:
        self._error = error

    def finish(self) -> None:
        """Stop the display, print the last line (and a failure's cause and log tail), restore."""
        if self.mode == STREAM:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        ok = self._result_path is not None
        if not ok and self._error is None:
            active = sys.exc_info()[1]
            self._error = active
        live = self._live_counts()
        if live is not None:
            self._counts = live
        if ok and not (self._counts.source == "live" and self._counts.state in ENDED_STATES):
            # No live folder (three of the four targets), or its last snapshot did not reach the
            # host: the finished run's own result is the source.
            assert self._result_path is not None
            self._counts = counts_from_result(self._result_path) or self._counts
        self._frozen = True  # the last line shows exactly the counts chosen above
        self._final_phase = COMPLETED if ok else ABORTED
        view = self.view()
        err = self.log.err if self.log is not None else None
        if self.display is not None:
            self.display.final(view)
        elif not ok and err is not None:
            err.write(f"{PREFIX} {ABORTED} | cause: {view.cause}\n")
        if not ok and self.log is not None and err is not None:
            tail = self.log.tail()
            if tail:
                text = (
                    f"{PREFIX} launcher output: {self.log.path} (last {len(tail)} line(s) below)\n"
                    + "".join(f"  {line}\n" for line in tail)
                )
                if self.display is not None:
                    self.display.message(text)
                else:
                    err.write(text)
        if self.log is not None:
            self.log.stop()
            self.log = None
