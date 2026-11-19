"""The Textual dashboard: five read-only screens over :mod:`inodefence.app` (see ``model.py``).

Nothing here parses a run file or decides a verdict: rows come from :mod:`.model`, which formats
what :mod:`inodefence.app.runs` / :mod:`inodefence.app.events` read. Keys only move around (screens,
rows, detail, refresh, help, quit); nothing is started, stopped, deleted or written.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, RichLog, Static, TabbedContent, TabPane

from inodefence.app.events import RunFollower, UiEvent
from inodefence.app.runs import RunSnapshot, default_roots, discover_runs
from inodefence.ui.tui import model
from inodefence.ui.tui.model import Cell, DashboardState, Row

COLOURS = {
    model.OK: "#4ade80",
    model.WARN: "#fbbf24",
    model.BAD: "#f87171",
    model.DIM: "#94a3b8",
    model.ACCENT: "#22d3ee",
    model.PLAIN: "",
}
EVENT_LINES = 200
RECENT_ACTIVITY = 8

TABS = ("overview", "targets", "campaigns", "findings", "artifacts")
COLUMNS = {
    "overview": ("item", "value", "source"),
    "targets": ("target", "explore", "replay", "prepared images", "last verify"),
    "campaigns": ("run", "target", "version", "state", "runs/budget", "rate", "violations",
                  "unjudged", "updated", "source"),
    "verify": ("cell", "verdict", "executed", "run errors", "unjudged", "warning"),
    "findings": ("case", "target", "C0", "C1", "C2", "class", "termination", "replay",
                 "location"),
}  # fmt: skip


def styled(cell: Cell) -> Text:
    colour = COLOURS.get(cell.style, "")
    return Text(cell.text, style=colour) if colour else Text(cell.text)


def lines_text(lines: Sequence[tuple[str, Cell]]) -> Text:
    out = Text()
    width = max((len(label) for label, _ in lines), default=0)
    for label, cell in lines:
        out.append(f"{label:<{width}}  ", style=COLOURS[model.DIM])
        out.append_text(styled(cell))
        out.append("\n")
    return out


def default_doctor() -> tuple[str, str]:
    """The doctor report as ``(status, summary)`` (Docker calls inside have their own timeouts)."""
    from inodefence.app import doctor
    from inodefence.user_config import UserConfigError, load_user_config

    try:
        config, error = load_user_config(), None
    except UserConfigError as problem:
        config, error = None, str(problem)
    report = doctor.run(config, error)
    status = "FAIL" if report.failed else ("UNKNOWN" if report.unknown else "OK")
    return status, report.summary


def default_targets() -> Mapping[str, Mapping[str, Any]]:
    from inodefence.app import targets
    from inodefence.locate import repo_root

    root = repo_root()
    if root is None:
        raise RuntimeError("repository not found (targets come from its registry)")
    return targets.load(root)


class DetailScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape,q,enter", "dismiss", "close")]

    def __init__(self, title: str, body: Text) -> None:
        super().__init__()
        self._title, self._body = title, body

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="detail"):
            yield Static(Text(self._title, style=COLOURS[model.ACCENT]), id="detail-title")
            yield Static(self._body, id="detail-body")


class InodeFenceTui(App[None]):
    TITLE = "InodeFence"
    #: read-only screen: no command palette (its built-in commands are not needed here)
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: #0f172a; color: #e2e8f0; }
    #header { height: 1; background: #1e293b; padding: 0 1; }
    TabbedContent { height: 1fr; }
    DataTable { background: #0f172a; height: 1fr; }
    DataTable > .datatable--header { background: #1e293b; color: #94a3b8; }
    DataTable > .datatable--cursor { background: #164e63; }
    #overview-table { height: auto; max-height: 14; }
    #recent { height: 1fr; padding: 0 1; }
    #artifacts-body { padding: 0 1; }
    #events { height: 6; border-top: solid #334155; background: #0b1220; }
    #verify-title { height: 1; color: #94a3b8; padding: 0 1; }
    DetailScreen { align: center middle; }
    #detail { width: 90%; height: 80%; background: #1e293b; border: solid #22d3ee; padding: 0 1; }
    Footer { background: #1e293b; }
    """
    BINDINGS = [
        Binding("1", "show('overview')", "Overview"),
        Binding("2", "show('targets')", "Targets"),
        Binding("3", "show('campaigns')", "Campaigns"),
        Binding("4", "show('findings')", "Findings"),
        Binding("5", "show('artifacts')", "Artifacts"),
        Binding("r", "refresh_now", "Refresh"),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        roots: Sequence[Path] | None = None,
        *,
        extra: Sequence[Path] = (),
        refresh: float = 1.0,
        follower: RunFollower | None = None,
        doctor: Callable[[], tuple[str, str]] | None = default_doctor,
        targets: Callable[[], Mapping[str, Mapping[str, Any]]] | None = default_targets,
        background: bool = True,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__()
        self.roots = [*(default_roots() if roots is None else roots), *extra]
        self.refresh_seconds = refresh
        self.follower = follower or RunFollower(roots=self.roots, interval=refresh, clock=clock)
        self._doctor = doctor
        self._targets = targets
        self._background = background
        self._clock = clock
        self.state = DashboardState(roots=tuple(self.roots))
        self.events: deque[UiEvent] = deque(maxlen=EVENT_LINES)
        self.selected_key: str | None = None
        self._subscription = self.follower.subscribe()
        self._row_keys: dict[str, list[str]] = {}

    # -- layout -------------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        with TabbedContent(id="tabs", initial="overview"):
            with TabPane("1 Overview", id="overview"):
                yield DataTable(id="overview-table", cursor_type="row", zebra_stripes=False)
                yield Static(id="recent")
            with TabPane("2 Targets", id="targets"):
                yield DataTable(id="targets-table", cursor_type="row")
            with TabPane("3 Campaigns", id="campaigns"):
                yield DataTable(id="campaigns-table", cursor_type="row")
                yield Static("verify cells", id="verify-title")
                yield DataTable(id="verify-table", cursor_type="row")
            with TabPane("4 Findings", id="findings"):
                yield DataTable(id="findings-table", cursor_type="row")
            with TabPane("5 Artifacts", id="artifacts"):
                with VerticalScroll():
                    yield Static(id="artifacts-body")
        yield RichLog(id="events", max_lines=EVENT_LINES, wrap=False, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        for name, columns in COLUMNS.items():
            self.query_one(f"#{name}-table", DataTable).add_columns(*columns)
        self.query_one("#events", RichLog).write(Text(model.READ_ONLY_NOTE, style=COLOURS["dim"]))
        if self._background:
            self.follower.start()
            if self._doctor is not None:
                self.run_worker(self._load_engine, thread=True, exclusive=False)
            if self._targets is not None:
                self.run_worker(self._load_targets, thread=True, exclusive=False)
            self.set_interval(self.refresh_seconds, self.tick)
        self.tick()

    def on_unmount(self) -> None:
        self._subscription.close()
        self.follower.stop(timeout=2)

    # -- background reads (doctor, registry) --------------------------------------------------

    def _load_engine(self) -> None:
        assert self._doctor is not None
        try:
            self.state.engine = self._doctor()
        except Exception as error:  # noqa: BLE001 -- shown as "unavailable", never raised
            self.state.engine_error = f"{type(error).__name__}: {error}"
        self.call_from_thread(self.redraw)

    def _load_targets(self) -> None:
        assert self._targets is not None
        try:
            self.state.targets = self._targets()
        except Exception as error:  # noqa: BLE001
            self.state.targets_error = f"{type(error).__name__}: {error}"
        self.call_from_thread(self.redraw)

    def load_now(self) -> None:
        """Doctor and registry in this thread (tests, or when no background is wanted)."""
        if self._doctor is not None:
            try:
                self.state.engine = self._doctor()
            except Exception as error:  # noqa: BLE001
                self.state.engine_error = str(error)
        if self._targets is not None:
            try:
                self.state.targets = self._targets()
            except Exception as error:  # noqa: BLE001
                self.state.targets_error = str(error)

    # -- refresh ------------------------------------------------------------------------------

    def tick(self) -> None:
        log = self.query_one("#events", RichLog)
        while (event := self._subscription.get(timeout=0)) is not None:
            self.events.append(event)
            log.write(styled(model.event_line(event)))
        self.state.events = list(self.events)
        self.state.snapshots = self.follower.snapshots()
        self.state.listings = discover_runs(self.roots, max_entries=2000)
        self.state.now = self._clock()
        self.redraw()

    def draw_selection(self) -> None:
        """The header and the Artifacts screen, which follow the selected run."""
        selected = self._selected_snapshot()
        header = Text()
        for index, cell in enumerate(model.header(self.state, selected)):
            if index == 1 or index > 2:  # "engine" and its status stay together
                header.append(" │ ", style=COLOURS["dim"])
            header.append_text(styled(cell))
        self.query_one("#header", Static).update(header)
        self.query_one("#artifacts-body", Static).update(lines_text(model.artifact_lines(selected)))

    def redraw(self) -> None:
        state = self.state
        self.draw_selection()
        self._fill("overview", model.overview_rows(state))
        recent = Text("recent activity\n", style=COLOURS["dim"])
        for event in model.recent(state.events, RECENT_ACTIVITY):
            recent.append_text(styled(model.event_line(event)))
            recent.append("\n")
        if not state.events:
            recent.append("no events yet", style=COLOURS["dim"])
        for line in model.scanned_lines(state):
            recent.append("\n" + line, style=COLOURS["dim"])
        self.query_one("#recent", Static).update(recent)
        targets = model.target_rows(state)
        if state.targets is None:
            reason = state.targets_error or "reading the registry…"
            targets = [Row("-", (Cell(f"targets unavailable: {reason}", model.DIM),
                                 Cell(""), Cell(""), Cell(""), Cell("")))]  # fmt: skip
        self._fill("targets", targets)
        campaigns = model.campaign_rows(state)
        self._fill("campaigns", campaigns or [_empty_row(10, "no explore runs found")])
        verify = model.verify_rows(state)
        self._fill("verify", verify or [_empty_row(6, "no verify cells found")])
        findings = model.finding_rows(state)
        self._fill("findings", findings or [_empty_row(9, "no violation candidates")])

    def _fill(self, name: str, rows: Sequence[Row]) -> None:
        table = self.query_one(f"#{name}-table", DataTable)
        cursor = table.cursor_row
        table.clear()
        for row in rows:
            table.add_row(*(styled(cell) for cell in row.cells))
        self._row_keys[name] = [row.key for row in rows]
        if rows:
            table.move_cursor(row=min(cursor, len(rows) - 1))

    def _selected_snapshot(self) -> RunSnapshot | None:
        if self.selected_key is None:
            return None
        run_key = self.selected_key.split("#", 1)[0]
        return self.state.snapshots.get(run_key)

    # -- keys ---------------------------------------------------------------------------------

    def action_show(self, tab: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab
        tables = self.query_one(f"#{tab}", TabPane).query(DataTable)
        if tables:
            tables.first().focus()  # keys move rows right away

    def action_refresh_now(self) -> None:
        self.follower.poll_once()
        self.tick()

    def action_help(self) -> None:
        body = Text()
        for key, what in (
            ("1-5 / tab", "switch screens"),
            ("↑ ↓ / j k", "move in a table"),
            ("enter", "open the detail of a finding, or the artifacts of a run"),
            ("esc", "close the detail"),
            ("r", "re-read now"),
            ("q", "quit"),
        ):
            body.append(f"{key:<10} {what}\n")
        body.append("\n")
        body.append("V violated · - judged, not violated · ? not judged or not observed\n")
        body.append("? as a number: the files do not hold it (only node-tar writes live numbers)\n")
        body.append(
            "a violation is a candidate; a replay says in how many judged rounds it repeated\n"
        )
        body.append("\n")
        for line in model.scanned_lines(self.state):
            body.append(line + "\n", style=COLOURS["dim"])
        self.push_screen(DetailScreen("help", body))

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        name = (message.data_table.id or "").removesuffix("-table")
        keys = self._row_keys.get(name, [])
        if name in ("campaigns", "verify", "findings") and 0 <= message.cursor_row < len(keys):
            if keys[message.cursor_row] not in ("-", self.selected_key):
                self.selected_key = keys[message.cursor_row]
                self.draw_selection()

    def on_data_table_row_selected(self, message: DataTable.RowSelected) -> None:
        name = (message.data_table.id or "").removesuffix("-table")
        keys = self._row_keys.get(name, [])
        if not 0 <= message.cursor_row < len(keys) or keys[message.cursor_row] == "-":
            return
        key = keys[message.cursor_row]
        self.selected_key = key
        self.draw_selection()
        if name == "findings":
            lines = model.finding_detail(self.state, key)
            self.push_screen(DetailScreen(f"finding {key.split('#', 1)[-1]}", lines_text(lines)))
        elif name in ("campaigns", "verify"):
            self.action_show("artifacts")


def _empty_row(width: int, message: str) -> Row:
    return Row("-", (Cell(message, model.DIM), *(Cell("") for _ in range(width - 1))))
