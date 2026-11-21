"""What the TUI shows, as plain labelled cells (no Textual here; unit-tested on its own).

Every value comes from :mod:`inodefence.app` (runs, events, doctor, targets). This module only
formats: an unknown value is ``?`` (a count) or ``—`` (a field), never ``0``; every coloured cell
also carries a text label, so the screen reads the same without colour; nothing says "confirmed"
or "vulnerability" -- a violation is a *candidate* and a replay says how many judged rounds
reproduced it.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from inodefence.app.events import EventKind, TimeSource, UiEvent
from inodefence.app.runs import (
    LIVE_PULL_INTERVAL_SECONDS,
    CaseRow,
    FindingClass,
    Judgment,
    LaunchActivity,
    ReadState,
    ReplayRecord,
    RunKind,
    RunListing,
    RunRef,
    RunSnapshot,
    Source,
    Verdict,
    launcher_activity,
)

#: A ``running`` snapshot older than this is shown as stalled, not active.
ACTIVE_MAX_AGE_SECONDS = 4 * LIVE_PULL_INTERVAL_SECONDS
UNKNOWN = "?"
NONE = "—"

# Cell styles (the app maps them to colours; the text never depends on them).
OK, WARN, BAD, DIM, ACCENT, PLAIN = "ok", "warn", "bad", "dim", "accent", ""


@dataclass(frozen=True, slots=True)
class Cell:
    text: str
    style: str = PLAIN


@dataclass(frozen=True, slots=True)
class Row:
    key: str
    cells: tuple[Cell, ...]


@dataclass
class DashboardState:
    """Everything one screen refresh draws, read by the app from :mod:`inodefence.app`."""

    snapshots: Mapping[str, RunSnapshot] = field(default_factory=dict)
    listings: Sequence[RunListing] = ()
    events: Sequence[UiEvent] = ()
    #: ``(status, summary)`` of the doctor report; ``None`` while checking or unavailable
    engine: tuple[str, str] | None = None
    engine_error: str | None = None
    #: ``{target: {feature: value}}`` from the registry, or ``None`` when it could not be read
    targets: Mapping[str, Mapping[str, Any]] | None = None
    targets_error: str | None = None
    #: ``{target: prepared image count}`` from doctor's image groups, when doctor gave it
    images: Mapping[str, int] | None = None
    #: the folders this screen scans (shown as is, so a synthetic demo folder is visible as such)
    roots: Sequence[Path] = ()
    now: float = field(default_factory=time.time)


def count(value: int | None) -> str:
    return UNKNOWN if value is None else str(value)


def text(value: object) -> str:
    return NONE if value is None or value == "" else str(value)


def ago(seconds: float | None) -> str:
    if seconds is None:
        return UNKNOWN
    seconds = max(seconds, 0.0)
    if seconds < 120:
        return f"{seconds:.0f}s ago"
    if seconds < 7200:
        return f"{seconds / 60:.0f}m ago"
    return f"{seconds / 3600:.1f}h ago"


def short_sha(value: str | None, keep: int = 12) -> str:
    if not value:
        return NONE
    head, _, tail = value.partition(":")
    return f"{head}:{tail[:keep]}" if tail else value[:keep]


def contract_cell(value: bool | None) -> Cell:
    """``V`` violated, ``-`` judged not violated, ``?`` not judged or not observed."""
    if value is True:
        return Cell("V", BAD)
    if value is False:
        return Cell("-", PLAIN)
    return Cell("?", DIM)


def verdict_cell(verdict: Verdict | None, validated: bool = True) -> Cell:
    if verdict is None:
        return Cell("no result", DIM)
    suffix = "" if validated else " (as stored)"
    style = {Verdict.PASS: OK, Verdict.FAIL: BAD, Verdict.ERROR: WARN}[verdict]
    return Cell(verdict.value + suffix, style)


def finding_class_cell(finding: FindingClass | None) -> Cell:
    if finding is FindingClass.CANDIDATE:
        return Cell("candidate", BAD)
    if finding is FindingClass.CANDIDATE_NEEDS_REPRO_CHECK:
        return Cell("needs repro check", WARN)
    return Cell(NONE, DIM)


def judgment_cell(judgment: Judgment) -> Cell:
    if judgment is Judgment.RUN_ERROR:
        return Cell("run error", BAD)
    if judgment is Judgment.UNJUDGED:
        return Cell("unjudged", WARN)
    return Cell("judged", PLAIN)


def replay_cell(records: Sequence[ReplayRecord]) -> Cell:
    """The newest readable replay: conclusion, same contracts n/judged, rounds done."""
    readable = [r for r in records if r.read_state is ReadState.OK]
    if not readable:
        return Cell("no replay", DIM)
    record = readable[-1]
    conclusion = record.conclusion.value if record.conclusion else UNKNOWN
    if record.judged == 0:
        detail = f"0 judged of {count(record.rounds_done)}"
    else:
        detail = (
            f"{count(record.same_contracts)}/{count(record.judged)} judged, "
            f"{count(record.rounds_done)} rounds"
        )
    style = {
        "reproduced_violation": OK,
        "partially_reproduced": WARN,
        "not_reproduced": WARN,
        "unjudged": WARN,
        "infrastructure_failure": BAD,
    }.get(conclusion, PLAIN)
    return Cell(f"{conclusion} · {detail}", style)


_SHORT_CONCLUSION = {
    "reproduced_violation": "reproduced",
    "partially_reproduced": "partial",
    "not_reproduced": "not reproduced",
    "no_violation": "no violation",
    "new_violation": "new violation",
    "unjudged": "unjudged",
    "infrastructure_failure": "infra failure",
    "no_rounds": "no rounds",
}
CONTRACT_LEGEND = "C0 C1 C2:  V violated  ·  - judged, not violated  ·  ? not judged / not observed"


def replay_columns(records: Sequence[ReplayRecord]) -> tuple[Cell, Cell]:
    """Findings' two replay columns: a short conclusion and ``n/judged · rounds`` (same
    contracts in n of the judged rounds, then how many rounds ran)."""
    readable = [r for r in records if r.read_state is ReadState.OK]
    if not readable:
        return Cell("no replay", DIM), Cell(NONE, DIM)
    full = replay_cell(readable)
    record = readable[-1]
    name = record.conclusion.value if record.conclusion else UNKNOWN
    label = Cell(_SHORT_CONCLUSION.get(name, name), full.style)
    if record.judged == 0:
        return label, Cell(f"0/0 · {count(record.rounds_done)} rounds", WARN)
    numbers = f"{count(record.same_contracts)}/{count(record.judged)}"
    return label, Cell(f"{numbers} · {count(record.rounds_done)} rounds")


def run_state(snapshot: RunSnapshot, now: float) -> Cell:
    """The run's state as the files say it; a running snapshot gone quiet is "stalled"."""
    progress = snapshot.progress
    summary = snapshot.summary
    if progress is not None and progress.source is Source.LIVE and progress.state is not None:
        if progress.state == "running":
            age = snapshot.progress_age(now)
            if age is None:
                return Cell("running (age ?)", WARN)
            if age > ACTIVE_MAX_AGE_SECONDS:
                return Cell(f"stalled ({ago(age)})", WARN)
            return Cell("running", ACCENT)
        style = {"finished": OK, "stopped": WARN, "failed": BAD}.get(progress.state, PLAIN)
        return Cell(progress.state, style)
    if summary is not None:
        if summary.read_state is ReadState.OK:
            return Cell("finished", OK)
        if summary.read_state is ReadState.UNVALIDATED:
            return Cell("finished (as stored, not validated)", WARN)
        if summary.read_state is ReadState.NOT_READY:
            return Cell("result not ready", WARN)
        return Cell(f"result {summary.read_state.value}", WARN)
    launcher = snapshot.launcher_state
    if launcher is not None:
        # seen only through its launcher log: an estimate from the log's last write, never "running"
        age = ago(max(now - launcher.last_write, 0.0))
        if launcher_activity(launcher.last_write, now) is LaunchActivity.ACTIVE:
            return Cell(f"launching/running (from launcher log, last write {age})", ACCENT)
        return Cell(f"no activity (launcher log last written {age})", WARN)
    # No live folder and no result: only node-tar writes running numbers, so this is not "stalled".
    return Cell("no live data", DIM)


def run_state_short(snapshot: RunSnapshot, now: float) -> Cell:
    """:func:`run_state` for table columns: a launcher-only run's estimate as a short label (the
    campaign panel and the header keep the long wording with the log's age)."""
    launcher = snapshot.launcher_state
    if launcher is None:
        return run_state(snapshot, now)
    if launcher_activity(launcher.last_write, now) is LaunchActivity.ACTIVE:
        return Cell(EST_ACTIVE, ACCENT)
    return Cell(EST_QUIET, WARN)


def is_active(snapshot: RunSnapshot, now: float) -> bool:
    launcher = snapshot.launcher_state
    if launcher is not None:
        return launcher_activity(launcher.last_write, now) is LaunchActivity.ACTIVE
    return run_state(snapshot, now).text == "running"


def is_stalled(snapshot: RunSnapshot, now: float) -> bool:
    launcher = snapshot.launcher_state
    if launcher is not None:  # quiet past any phase a live launcher allows
        return launcher_activity(launcher.last_write, now) is LaunchActivity.NO_ACTIVITY
    return run_state(snapshot, now).text.startswith("stalled")


def source_cell(snapshot: RunSnapshot) -> Cell:
    progress = snapshot.progress
    if progress is None:
        return Cell("none", DIM)
    if progress.source is Source.LAUNCHER_LOG:
        return Cell(f"launcher-log est. ({text(progress.launcher_step)})", DIM)
    return Cell(progress.source.value, DIM if progress.source is Source.NONE else PLAIN)


def _explore(state: DashboardState) -> list[RunSnapshot]:
    return [s for s in state.snapshots.values() if s.ref.kind is RunKind.EXPLORE]


def _verify(state: DashboardState) -> list[RunSnapshot]:
    return [s for s in state.snapshots.values() if s.ref.kind is RunKind.VERIFY]


def _replays(state: DashboardState) -> list[ReplayRecord]:
    found: dict[str, ReplayRecord] = {}
    for snapshot in state.snapshots.values():
        for record in snapshot.replays:
            found[str(record.path)] = record
    return list(found.values())


def findings(state: DashboardState) -> list[tuple[RunSnapshot, CaseRow]]:
    out = []
    for snapshot in state.snapshots.values():
        if snapshot.ref.kind is RunKind.REPLAY:
            continue
        out += [(snapshot, row) for row in snapshot.findings]
    return out


def _replays_for(snapshot: RunSnapshot, row: CaseRow, every: Sequence[ReplayRecord]):
    own = [r for r in snapshot.replays if r.original_case_id == row.case_id]
    if own:
        return own
    if row.input_path is not None:
        folder = row.input_path.parent
        return [r for r in every if r.path.parent.name.startswith(f"{folder.name}.replay-")]
    return []


# -- header, overview ------------------------------------------------------------------------------


def engine_cell(state: DashboardState) -> Cell:
    if state.engine is None:
        return Cell("unavailable" if state.engine_error else "checking…", DIM)
    status, _ = state.engine
    return Cell(status, {"OK": OK, "FAIL": BAD}.get(status, WARN))


def header(state: DashboardState, selected: RunSnapshot | None) -> list[tuple[str, Cell]]:
    """``(label, value)`` pairs; the first is the name (empty label). Nothing selected: ``—``."""
    active = sum(is_active(s, state.now) for s in _explore(state))
    stalled = sum(is_stalled(s, state.now) for s in _explore(state))
    run, status = Cell(NONE, DIM), Cell(NONE, DIM)
    if selected is not None:
        ref = selected.ref
        run = Cell(target_label(ref))
        status = run_state(selected, state.now)
    return [
        ("", Cell("InodeFence", ACCENT)),
        ("engine", engine_cell(state)),
        ("active runs", Cell(str(active), ACCENT if active else PLAIN)),
        ("stalled runs", Cell(str(stalled), WARN if stalled else DIM)),
        ("selected", run),
        ("state", status),
    ]


def key_figures(state: DashboardState) -> list[tuple[str, Cell, str]]:
    """The Overview's headline numbers: ``(label, value, detail)``; unknown is ``—``."""
    explore = _explore(state)
    every = findings(state)
    needs = sum(r.finding is FindingClass.CANDIDATE_NEEDS_REPRO_CHECK for _, r in every)
    stalled = sum(is_stalled(s, state.now) for s in explore)
    engine = engine_cell(state)
    targets = Cell(str(len(state.targets))) if state.targets is not None else Cell(NONE, DIM)
    return [
        ("system", engine, "doctor"),
        ("targets", targets, "registered"),
        ("active", Cell(str(sum(is_active(s, state.now) for s in explore)), ACCENT),
         f"stalled {stalled}"),
        ("candidates", Cell(str(len(every)), BAD if every else PLAIN), f"needs repro {needs}"),
        ("replays", Cell(str(len(_replays(state)))), "replay.json"),
    ]  # fmt: skip


#: Width of the Campaigns progress bar (characters).
BAR_WIDTH = 10


def progress_bar(runs: int | None, budget: int | None, width: int = BAR_WIDTH) -> str | None:
    """``███░░░░░░░`` from the real runs and budget only; ``None`` when either is unknown."""
    if runs is None or budget is None or budget <= 0:
        return None
    filled = round(width * min(max(runs / budget, 0.0), 1.0))
    return "█" * filled + "░" * (width - filled)


EMPTY_TITLE = "no run folders found"
EMPTY_HINT = (
    "make a run: press n, or inodefence explore --target node-tar --version latest --auto-prepare"
)


def is_empty(state: DashboardState) -> bool:
    return not state.snapshots and not any(item.ref for item in state.listings)


def empty_lines(state: DashboardState) -> list[Cell]:
    return [
        Cell(EMPTY_TITLE, ACCENT),
        *(Cell(f"scanned {root}", DIM) for root in state.roots),
        Cell(EMPTY_HINT),
        Cell("(or pass the folders to read: inodefence tui <folder> ...)", DIM),
    ]


def overview_rows(state: DashboardState) -> list[Row]:
    explore, verify = _explore(state), _verify(state)
    all_findings = findings(state)
    needs = sum(r.finding is FindingClass.CANDIDATE_NEEDS_REPRO_CHECK for _, r in all_findings)
    fixtures = sum(len(s.fixture_violations) for s in verify)
    unclassified = sum(len(s.unclassified_violations) for s in state.snapshots.values())
    unread = sum(item.read_state is not ReadState.OK for item in state.listings)
    engine = engine_cell(state)
    engine_text = engine.text if state.engine is None else f"{engine.text} · {state.engine[1]}"
    targets = (
        Cell(str(len(state.targets)))
        if state.targets is not None
        else Cell(f"unknown ({state.targets_error or 'registry not read'})", DIM)
    )
    finished = sum(run_state(s, state.now).text.startswith("finished") for s in explore)
    as_stored = sum(
        s.summary is not None and s.summary.read_state is ReadState.UNVALIDATED
        for s in state.snapshots.values()
    )
    rows = [
        ("system", Cell(engine_text, engine.style), "doctor"),
        ("targets registered", targets, "registry"),
        ("active campaigns", Cell(str(sum(is_active(s, state.now) for s in explore))), "live"),
        ("stalled", Cell(str(sum(is_stalled(s, state.now) for s in explore))), "live"),
        ("finished explore runs", Cell(str(finished)), "result"),
        ("verify cells", Cell(str(len(verify))), "result"),
        ("results as stored (not validated)", Cell(str(as_stored), WARN if as_stored else PLAIN),
         "result"),
        ("violation candidates", Cell(str(len(all_findings)), BAD if all_findings else PLAIN),
         "live / result"),
        ("  needing a repro check", Cell(str(needs), WARN if needs else PLAIN), "live / result"),
        ("  by replay", Cell(replay_breakdown(state)), "replay.json"),
        ("replays", Cell(str(len(_replays(state)))), "replay.json"),
        ("known fixtures violated (verify)", Cell(str(fixtures)), "result"),
        *(
            [("unclassified (result not validated)", Cell(str(unclassified), WARN), "result")]
            if unclassified  # neither candidates nor fixtures: mode and run kind both unknown
            else []
        ),
        ("folders not read", Cell(str(unread), WARN if unread else PLAIN), "scan"),
    ]  # fmt: skip
    return [Row(label, (Cell(label), value, Cell(src, DIM))) for label, value, src in rows]


#: What this screen does, said where it is always visible (the events panel, the scan lines).
SCREEN_NOTE = (
    "reads existing run folders · runs a command only when you choose on"
    "e (one that starts Docker only after Start) · stops and deletes nothing"
)


def replay_breakdown(state: DashboardState) -> str:
    """Candidates by their newest replay's conclusion, so a candidate count never reads as
    "all reproduced": ``reproduced n · partially n · not reproduced n · other n · no replay n``."""
    every = _replays(state)
    counts = {"reproduced": 0, "partially": 0, "not reproduced": 0, "other": 0, "no replay": 0}
    for snapshot, row in findings(state):
        readable = [r for r in _replays_for(snapshot, row, every) if r.read_state is ReadState.OK]
        if not readable or readable[-1].conclusion is None:
            counts["no replay"] += 1
            continue
        name = readable[-1].conclusion.value
        key = {
            "reproduced_violation": "reproduced",
            "partially_reproduced": "partially",
            "not_reproduced": "not reproduced",
        }.get(name, "other")
        counts[key] += 1
    return " · ".join(f"{name} {value}" for name, value in counts.items())


def scanned_lines(state: DashboardState) -> list[str]:
    return [SCREEN_NOTE, *(f"scanning {root}" for root in state.roots)]


# -- targets ---------------------------------------------------------------------------------------


def target_rows(state: DashboardState) -> list[Row]:
    if state.targets is None:
        return []
    last: dict[str, RunSnapshot] = {}
    for snapshot in _verify(state):
        target = snapshot.ref.target
        if target is None or snapshot.summary is None or snapshot.summary.result_path is None:
            continue
        if target not in last or _mtime(snapshot.summary.result_path) > _mtime(
            last[target].summary.result_path  # type: ignore[union-attr]
        ):
            last[target] = snapshot
    rows = []
    for name, feats in state.targets.items():
        explore = "yes" if feats.get("explore") else "no"
        replay = "yes" if feats.get("replay") else "no"
        images = (
            Cell(str(state.images[name]))
            if state.images is not None and name in state.images
            else Cell(NONE, DIM)
        )
        if name in last:
            snap = last[name]
            summary = snap.summary
            assert summary is not None
            verdict = verdict_cell(summary.verdict, summary.validated)
            when = _clock(_mtime(summary.result_path))
            verified = Cell(f"{text(snap.ref.version)} · {verdict.text} · {when}", verdict.style)
        else:
            verified = Cell(NONE, DIM)
        rows.append(Row(name, (Cell(name, ACCENT), Cell(explore), Cell(replay), images, verified)))
    return rows


def _mtime(path: Path | None) -> float:
    if path is None:
        return 0.0
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _clock(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M") if epoch else NONE


# -- campaigns -------------------------------------------------------------------------------------


def campaign_rows(state: DashboardState) -> list[Row]:
    rows = []
    ordered = sorted(_explore(state), key=lambda s: s.read_at - (s.progress_age() or 0))
    for snapshot in reversed(ordered):
        p, ref = snapshot.progress, snapshot.ref
        runs = f"{count(p.runs if p else None)}/{count(p.budget if p else None)}"
        bar = progress_bar(p.runs if p else None, p.budget if p else None)
        if bar is not None:
            runs = f"{runs} {bar}"
        rate = (
            f"{p.runs_per_second * 60:.1f}/min"
            if p is not None and p.runs_per_second is not None
            else UNKNOWN
        )
        violations = p.violations if p else None
        rows.append(
            Row(
                ref.key,
                (
                    Cell(run_name(snapshot), ACCENT),
                    run_state_short(snapshot, state.now),
                    Cell(runs),
                    Cell(rate),
                    Cell(count(violations), BAD if violations else PLAIN),
                    Cell(count(p.unjudged if p else None)),
                    Cell(ago(snapshot.progress_age(state.now)), DIM),
                    source_cell(snapshot),
                ),
            )
        )
    return rows


def verify_rows(state: DashboardState) -> list[Row]:
    rows = []
    for snapshot in sorted(_verify(state), key=lambda s: str(s.ref.root)):
        summary = snapshot.summary
        if summary is None or not summary.has_values:
            state_text = summary.read_state.value if summary else "missing"
            cells = (Cell(text(snapshot.ref.run_id), ACCENT), Cell(state_text, WARN),
                     Cell(UNKNOWN), Cell(UNKNOWN), Cell(UNKNOWN), Cell(UNKNOWN),
                     Cell(NONE, DIM))  # fmt: skip
            rows.append(Row(snapshot.ref.key, cells))
            continue
        warning = Cell("no extraction", WARN) if summary.no_extraction_warning else Cell(NONE, DIM)
        rows.append(
            Row(
                snapshot.ref.key,
                (
                    Cell(text(snapshot.ref.run_id), ACCENT),
                    verdict_cell(summary.verdict, summary.validated),
                    Cell(count(summary.executed)),
                    Cell(count(summary.errored), BAD if summary.errored else PLAIN),
                    Cell(count(summary.unjudged_steps), WARN if summary.unjudged_steps else PLAIN),
                    Cell(str(len(summary.fixture_violations))),
                    warning,
                ),
            )
        )
    return rows


# -- findings --------------------------------------------------------------------------------------


def finding_key(snapshot: RunSnapshot, row: CaseRow) -> str:
    return f"{snapshot.ref.key}#{row.case_id}"


def finding_rows(state: DashboardState) -> list[Row]:
    every = _replays(state)
    rows = []
    for snapshot, row in findings(state):
        rows.append(
            Row(
                finding_key(snapshot, row),
                (
                    Cell(row.case_id, ACCENT),
                    contract_cell(row.c0),
                    contract_cell(row.c1),
                    contract_cell(row.c2),
                    finding_class_cell(row.finding),
                    *replay_columns(_replays_for(snapshot, row, every)),
                ),
            )
        )
    return rows


#: Detail lines whose value is long and gets its own full-width block (label above, value below).
BLOCK_LABELS = ("input SHA-256", "input file", "replay folder")


def yes_no(value: bool | None) -> Cell:
    if value is None:
        return Cell(NONE, DIM)
    return Cell("yes" if value else "no", PLAIN if value else WARN)


def finding_detail(state: DashboardState, key: str) -> list[tuple[str, Cell]]:
    every = _replays(state)
    for snapshot, row in findings(state):
        if finding_key(snapshot, row) != key:
            continue
        lines: list[tuple[str, Cell]] = [
            ("case", Cell(row.case_id, ACCENT)),
            ("run", Cell(text(snapshot.ref.run_id))),
            ("target", Cell(target_label(snapshot.ref))),
            ("class", finding_class_cell(row.finding)),
            ("C0 / C1 / C2", Cell(" ".join(contract_cell(v).text for v in row.contracts.values()))),
            ("termination", Cell(row.termination.value)),
            ("judgment", judgment_cell(row.judgment)),
            ("observation complete", yes_no(row.observation_complete)),
            (
                "fingerprints",
                Cell(
                    str(len(row.fingerprints)) if row.fingerprints else NONE,
                    PLAIN if row.fingerprints else DIM,
                ),
            ),
            ("recorded", Cell(text(row.recorded_at), PLAIN if row.recorded_at else DIM)),
            ("input SHA-256", Cell(text(row.tar_sha256))),
            ("input file", Cell(text(row.input_path), DIM)),
        ]
        for record in _replays_for(snapshot, row, every):
            lines.append(("replay", replay_cell([record])))
            lines.append(("replay folder", Cell(str(record.path.parent), DIM)))
            for entry in record.rounds:
                verdicts = " ".join(contract_cell(v).text for v in (entry.c0, entry.c1, entry.c2))
                lines.append(
                    (f"  round {count(entry.round)}",
                     Cell(f"{text(entry.classification)} · {text(entry.termination)} · {verdicts}"))
                )  # fmt: skip
        return lines
    return []


# -- artifacts -------------------------------------------------------------------------------------


def artifact_lines(snapshot: RunSnapshot | None) -> list[tuple[str, Cell]]:
    if snapshot is None:
        return [("run", Cell("select a run in Campaigns or Flagged cases", DIM))]
    ref = snapshot.ref
    lines: list[tuple[str, Cell]] = [
        ("run", Cell(f"{ref.kind.value} {text(ref.run_id)}", ACCENT)),
        ("folder", Cell(str(ref.root), DIM)),
        ("target", Cell(target_label(ref))),
    ]
    summary = snapshot.summary
    if summary is None:
        lines.append(("result.json", Cell("not written yet", DIM)))
    else:
        state = summary.read_state.value + ("" if summary.validated else ", as stored")
        lines.append(("result.json", Cell(f"{text(summary.result_path)} ({state})")))
        lines.append(("verdict", verdict_cell(summary.verdict, summary.validated)))
        integrity = summary.integrity
        if integrity is not None:
            dirty = " (dirty)" if integrity.engine_dirty else ""
            lines += [
                ("engine", Cell(f"{short_sha(integrity.engine_sha)}{dirty}")),
                ("image", Cell(text(integrity.image_ref))),
                ("image id", Cell(short_sha(integrity.image_id, 20))),
                ("lock / worker", Cell(f"{short_sha(integrity.lock_sha256)} / "
                                       f"{short_sha(integrity.worker_sha256)}")),
                ("inputs", Cell(f"{len(integrity.inputs)} saved, "
                                + ("re-checked" if integrity.rechecked else "not re-checked"))),
            ]  # fmt: skip
            for case_id, sha, path in integrity.inputs[:20]:
                lines.append((f"  {case_id}", Cell(f"{short_sha(sha)} {path}", DIM)))
        if summary.extras:
            lines.append(("newer keys", Cell(", ".join(sorted(summary.extras)), DIM)))
        if summary.error:
            lines.append(("note", Cell(summary.error, WARN)))
    if ref.kind is RunKind.EXPLORE:
        lines.append(("runtime folder", Cell(str(ref.root / "runtime"), DIM)))
        live = ref.root / "target-explore" / (ref.run_id or "") / "live"
        lines.append(("live folder", Cell(str(live) if live.is_dir() else NONE, DIM)))
        step = snapshot.progress.launcher_step if snapshot.progress else None
        log = f"{text(snapshot.launcher_log)} (last step est.: {text(step)})"
        lines.append(("launcher log", Cell(log, DIM)))
    for record in snapshot.replays:
        lines.append(("replay", replay_cell([record])))
        lines.append(("  replay.json", Cell(str(record.path), DIM)))
    for error in snapshot.read_errors:
        lines.append(("read problem", Cell(error, WARN)))
    return lines


# -- events ----------------------------------------------------------------------------------------

_TIME_ABBREV = {
    TimeSource.UPDATED_AT: "u",
    TimeSource.RECORDED_AT: "r",
    TimeSource.MTIME: "m",
    TimeSource.OBSERVED: "o",
}


TIME_LEGEND = "time source: u updated_at · r recorded_at · m file mtime · o observed by this screen"


def event_cells(event: UiEvent) -> tuple[Cell, Cell, Cell, Cell]:
    """``time source``, ``kind``, ``run``, ``content``: aligned columns for the event strip."""
    clock = event.timestamp[11:19] if len(event.timestamp) >= 19 else event.timestamp
    when = Cell(f"{clock} {_TIME_ABBREV.get(event.time_source, '?')}", DIM)
    parts = []
    if event.progress_current is not None or event.progress_total is not None:
        parts.append(f"{count(event.progress_current)}/{count(event.progress_total)}")
    for value in (event.status, event.verdict, event.case_id, event.message):
        if value:
            parts.append(str(value))
    if event.estimated:
        parts.append("(est.)")
    kind = event.kind.value
    style = PLAIN
    if event.kind is EventKind.READ_ERROR:
        kind, style = "READ", WARN
    elif event.kind is EventKind.VIOLATION_CASE:
        style = BAD
    elif event.kind is EventKind.RESULT_READY:
        style = {"PASS": OK, "FAIL": BAD, "ERROR": WARN}.get(event.verdict or "", PLAIN)
    elif event.estimated:
        style = DIM
    return when, Cell(kind, style), Cell(event.run_id or NONE), Cell(" ".join(parts), style)


EVENT_WIDTHS = (10, 14, 26)


def event_line(event: UiEvent) -> Cell:
    """One event as a single aligned line (the content keeps the kind's style)."""
    when, kind, run, content = event_cells(event)
    head = f"{when.text:<{EVENT_WIDTHS[0]}} {kind.text:<{EVENT_WIDTHS[1]}} "
    return Cell(head + f"{run.text:<{EVENT_WIDTHS[2]}} {content.text}".rstrip(), kind.style)


def recent(events: Iterable[UiEvent], limit: int) -> list[UiEvent]:
    return list(events)[-limit:]


# -- tiled dashboard panels ------------------------------------------------------------------------

SPARK = "▁▂▃▄▅▆▇█"
#: How many observed progress samples a run keeps for its graph (this screen's own observation).
HISTORY = 240


@dataclass(frozen=True, slots=True)
class Sample:
    """One progress snapshot this screen saw: its own ``updated_at``, runs, runs per second."""

    at: float
    runs: int | None
    rate: float | None


def observe(history: list[Sample], snapshot: RunSnapshot) -> None:
    """Append the snapshot's live progress when it is new (same ``updated_at``: nothing)."""
    p = snapshot.progress
    if p is None or p.source is not Source.LIVE or p.updated_at is None:
        return
    if history and history[-1].at == p.updated_at:
        return
    history.append(Sample(p.updated_at, p.runs, p.runs_per_second))
    del history[:-HISTORY]


def sparkline(values: Sequence[float | None], width: int) -> str:
    """The last ``width`` values as block characters scaled to their maximum; unknown values are
    gaps. Empty when nothing is known (nothing is drawn without data)."""
    if width <= 0:
        return ""
    tail = list(values)[-width:]
    known = [v for v in tail if v is not None]
    if not known:
        return ""
    top = max(known)
    if top <= 0:
        return "".join(" " if v is None else SPARK[0] for v in tail)
    steps = len(SPARK) - 1
    return "".join(
        " " if v is None else SPARK[min(steps, max(0, round(v / top * steps)))] for v in tail
    )


def increments(history: Sequence[Sample]) -> list[float | None]:
    """Runs done between consecutive observed snapshots (the graph's values)."""
    out: list[float | None] = []
    for before, after in zip(history, history[1:], strict=False):
        if before.runs is None or after.runs is None:
            out.append(None)
        else:
            out.append(float(max(after.runs - before.runs, 0)))
    return out


def bar(value: int | None, total: int | None, width: int) -> str | None:
    return progress_bar(value, total, width)


def default_selection(state: DashboardState) -> RunSnapshot | None:
    """The run the Overview follows when none is chosen: an active one, else the newest."""
    explore = _explore(state)
    active = [s for s in explore if is_active(s, state.now)]
    pool = active or explore
    if not pool:
        return None
    return max(pool, key=lambda s: (s.progress.updated_at if s.progress else None) or 0.0)


def outcome_rows(snapshot: RunSnapshot | None) -> list[tuple[str, int | None, int | None, str]]:
    """``(label, count, total, style)`` for the outcomes panel: each termination, unjudged,
    build-invalid. Unknown counts are ``None`` (drawn as ``?`` with no bar)."""
    p = snapshot.progress if snapshot else None
    total = p.runs if p else None
    terms = p.terminations if p else {}
    rows = [
        ("success", terms.get("success"), total, OK),
        ("rejected", terms.get("rejected"), total, WARN),
        ("failed", terms.get("failed"), total, BAD),
        ("timed out", terms.get("timed_out"), total, BAD),
        ("unjudged", p.unjudged if p else None, total, WARN),
        ("build-invalid", p.build_invalid if p else None, total, DIM),
    ]
    return rows


def oracle_lines(state: DashboardState, snapshot: RunSnapshot | None) -> list[tuple[str, Cell]]:
    """The selected run's candidates: count, per-contract counts from its case folders (a lower
    bound while some are held back), needs-repro-check, replay conclusions."""
    if snapshot is None:
        return [("run", Cell("no run selected", DIM))]
    p = snapshot.progress
    rows = snapshot.findings
    lower = p.contracts_lower_bound if p else False
    lines: list[tuple[str, Cell]] = [
        ("candidates", Cell(count(p.violations if p else len(rows)), BAD if rows else PLAIN)),
    ]
    contracts = p.contracts if p else {}
    marks = []
    for key in ("c0", "c1", "c2"):
        value = contracts.get(key) if contracts else None
        prefix = "≥" if lower and value is not None else ""
        marks.append(f"{key.upper()} {prefix}{count(value)}")
    lines.append(
        ("by contract", Cell("  ".join(marks) + ("  (from case folders)" if lower else "")))
    )
    needs = sum(r.finding is FindingClass.CANDIDATE_NEEDS_REPRO_CHECK for r in rows)
    total = p.violations if p else len(rows)
    if total is None and not rows:  # the candidates are not known, so neither is this (QA)
        lines.append(("needs repro check", Cell(UNKNOWN, DIM)))
    else:
        shown = f"≥{needs}" if lower else str(needs)  # only the case folders read so far
        lines.append(("needs repro check", Cell(shown, WARN if needs else PLAIN)))
    return lines


def replay_bars(
    state: DashboardState, snapshot: RunSnapshot | None
) -> list[tuple[str, int, int, str]]:
    """``(label, count, candidates, style)``: the selected run's candidates by their newest
    replay's conclusion (``n/judged`` stays in Findings)."""
    if snapshot is None:
        return []
    every = _replays(state)
    order = ("reproduced", "partial", "not reproduced", "other", "no replay")
    counts = dict.fromkeys(order, 0)
    for row in snapshot.findings:
        label, _ = replay_columns(_replays_for(snapshot, row, every))
        counts[label.text if label.text in counts else "other"] += 1
    total = len(snapshot.findings)
    styles = {"reproduced": OK, "partial": WARN, "not reproduced": WARN, "other": DIM,
              "no replay": DIM}  # fmt: skip
    return [(name, counts[name], total, styles[name]) for name in order]


def runs_list(state: DashboardState) -> list[Row]:
    """The compact run list of the Overview: target@version, state, mini bar, candidates, age."""
    rows = []
    ordered = sorted(_explore(state), key=lambda s: (s.progress.updated_at if s.progress else None)
                     or 0.0, reverse=True)  # fmt: skip
    for snapshot in ordered:
        p, ref = snapshot.progress, snapshot.ref
        mini = bar(p.runs if p else None, p.budget if p else None, 6)
        runs = f"{count(p.runs if p else None)}/{count(p.budget if p else None)}"
        violations = p.violations if p else None
        rows.append(
            Row(
                ref.key,
                (
                    Cell(run_name(snapshot, OVERVIEW_NAME_LIMIT), ACCENT),
                    run_state_short(snapshot, state.now),
                    Cell(f"{mini} {runs}" if mini else runs),
                    Cell(count(violations), BAD if violations else PLAIN),
                ),
            )
        )
    return rows


def target_label(ref: RunRef) -> str:
    """``target@version``; ``target`` alone without a version; ``—`` when neither is known."""
    if ref.target is None and ref.version is None:
        return NONE
    if ref.version is None:
        return text(ref.target)
    return f"{text(ref.target)}@{ref.version}"


#: A launcher-only run's name in the run lists: its id is written only when it ends.
NO_ID_YET = "(no id yet)"
#: A launcher-only run's state in the tables, from its log's last write (estimated). Short on
#: purpose: the Overview's runs table is 56 columns at 140x40 and the state column has 14 with
#: its badge (the campaign panel and the header carry the long wording with the log's age).
EST_ACTIVE = "est. live"
EST_QUIET = "est. quiet"
#: The Overview's run names (``node-tar@7.5.2 #1-20`` fits exactly; longer ones are cut).
OVERVIEW_NAME_LIMIT = 20


def run_name(snapshot: RunSnapshot, limit: int = 22) -> str:
    """``target@version``, or the run id when the files do not name the target yet."""
    ref = snapshot.ref
    if ref.kind is RunKind.EXPLORE and ref.run_id is None:
        room = limit - len(NO_ID_YET) - 1  # the end of the folder name identifies it
        folder = ref.root.name
        tail = folder if len(folder) <= room else "…" + folder[len(folder) - room + 1 :]
        return f"{NO_ID_YET} {tail}" if room > 1 else NO_ID_YET
    if ref.target is None:
        return shorten_middle(text(ref.run_id), limit)
    name = f"{ref.target}@{text(ref.version)}"
    tail = run_tail(ref.run_id, ref.version)
    return shorten_middle(f"{name} #{tail}" if tail else name, limit)


def run_tail(run_id: str | None, version: str | None) -> str | None:
    """What follows the version in a run id (``…-7.5.2-1-20`` -> ``1-20``: seed and budget)."""
    if not run_id:
        return None
    if version and f"{version}-" in run_id:
        return run_id.split(f"{version}-", 1)[1] or None
    return run_id if len(run_id) <= 8 else "…" + run_id[-8:]  # cut: say so


def shorten_middle(value: str, width: int) -> str:
    """``value`` cut in the middle with ``…`` to fit ``width`` (the ends are what identify it)."""
    if width <= 1 or len(value) <= width:
        return value
    keep = width - 1
    head = keep // 2
    return value[:head] + "…" + value[len(value) - (keep - head) :]


def run_detail(snapshot: RunSnapshot | None, now: float) -> list[tuple[str, Cell]]:
    """The campaign box: state, runs/budget, rate, age, source, run id."""
    if snapshot is None:
        return [("run", Cell("no explore run found", DIM))]
    p, ref = snapshot.progress, snapshot.ref
    runs, budget = (p.runs, p.budget) if p else (None, None)
    rate = f"{p.runs_per_second * 60:.1f} runs/min" if p and p.runs_per_second else UNKNOWN
    return [
        ("run", Cell(text(ref.run_id) if ref.run_id else NO_ID_YET, ACCENT)),
        ("target", Cell(target_label(ref))),
        ("state", run_state(snapshot, now)),
        ("runs", Cell(f"{count(runs)} / {count(budget)}")),
        ("rate", Cell(rate)),
        ("updated", Cell(ago(snapshot.progress_age(now)), DIM)),
        ("source", source_cell(snapshot)),
    ]


def target_lines(state: DashboardState) -> list[tuple[str, Cell, Cell, Cell]]:
    """One line per registered target: capabilities, prepared images, last verify."""
    out = []
    for row in target_rows(state):
        name, explore, replay, images, verified = row.cells
        caps = " ".join(
            label
            for label, cell in (("explore", explore), ("replay", replay))
            if cell.text == "yes"
        )
        out.append((name.text, Cell(caps or NONE, DIM), images, verified))
    return out


def collapse_events(events: Sequence[UiEvent]) -> list[tuple[UiEvent, int]]:
    """Consecutive ``progress`` events of the same run folded into the last one with a count,
    so they do not push the other kinds out of a short panel."""
    out: list[tuple[UiEvent, int]] = []
    for event in events:
        if (
            out
            and event.kind is EventKind.PROGRESS
            and out[-1][0].kind is EventKind.PROGRESS
            and out[-1][0].run_id == event.run_id
            and out[-1][0].run_root == event.run_root
        ):
            out[-1] = (event, out[-1][1] + 1)
        else:
            out.append((event, 1))
    return out


def percent(runs: int | None, budget: int | None) -> str | None:
    if runs is None or budget is None or budget <= 0:
        return None
    return f"{runs / budget * 100:.1f}%"
