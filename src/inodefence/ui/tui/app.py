"""The Textual dashboard: a tiled, read-only monitor over :mod:`inodefence.app` (see ``model.py``).

Overview is a tiled screen: the selected campaign (an observed-throughput graph and its numbers),
outcomes and oracle panels, targets, the run list, and the event stream -- all drawn from real
values (a graph with no observed samples is not drawn). Targets, Campaigns, Findings and Artifacts
use the same panel grammar (titled borders, bars, badges). Nothing here parses a run file or
decides a verdict, and keys only move around: nothing is started, stopped, deleted or written.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, RichLog, Static, TabbedContent, TabPane

from inodefence.app.events import RunFollower, UiEvent
from inodefence.app.runs import RunSnapshot, default_roots, discover_runs
from inodefence.ui.tui import model
from inodefence.ui.tui.model import Cell, DashboardState, Row, Sample
from inodefence.ui.tui.palette import BAR_HIGH, BAR_LOW, BAR_MID, DEEP, PALETTE, PANEL
from inodefence.ui.tui.palette import TITLE as TITLE_COLOUR

COLOURS = {
    model.OK: PALETTE["ok"],
    model.WARN: PALETTE["warn"],
    model.BAD: PALETTE["bad"],
    model.DIM: PALETTE["muted"],
    model.ACCENT: PALETTE["accent"],
    model.PLAIN: "",
}
EVENT_LINES = 200
#: Below either of these the Overview keeps only campaign, runs and events.
WIDE_MIN_COLUMNS, WIDE_MIN_ROWS = 110, 30

COLUMNS = {
    "runs": ("run", "state", "progress", "cand."),
    "targets": ("target", "explore", "replay", "prepared images", "last verify"),
    "campaigns": ("run", "target", "version", "state", "runs/budget", "rate", "violations",
                  "unjudged", "updated", "source"),
    "verify": ("cell", "verdict", "executed", "run errors", "unjudged", "warning"),
    "findings": ("case", "target", "C0", "C1", "C2", "class", "termination", "replay",
                 "judged rounds", "location"),
}  # fmt: skip
#: Tables whose highlighted row selects the run the panels follow.
SELECTING = ("runs", "campaigns", "verify", "findings")


def styled(cell: Cell) -> Text:
    colour = COLOURS.get(cell.style, "")
    return Text(cell.text, style=colour) if colour else Text(cell.text)


def badge(cell: Cell) -> Text:
    """A state as a badge: a symbol and the word (never colour alone)."""
    symbol = {model.OK: "✓", model.WARN: "!", model.BAD: "✗", model.ACCENT: "●"}.get(
        cell.style, "·"
    )
    return styled(Cell(f"{symbol} {cell.text}", cell.style))


def lines_text(lines: Sequence[tuple[str, Cell]], width: int | None = None) -> Text:
    out = Text()
    label_width = width or max((len(label) for label, _ in lines), default=0)
    for label, cell in lines:
        out.append(f"{label:<{label_width}}  ", style=PALETTE["muted"])
        out.append_text(styled(cell))
        out.append("\n")
    out.rstrip()
    return out


def bar_text(value: int | None, total: int | None, width: int) -> Text:
    """A coloured bar from real numbers only; unknown gives no bar."""
    drawn = model.bar(value, total, width)
    if drawn is None:
        return Text("?", style=PALETTE["muted"])
    filled = drawn.count("█")
    ratio = filled / width if width else 0
    colour = BAR_LOW if ratio < 0.5 else BAR_MID if ratio < 0.85 else BAR_HIGH
    out = Text("█" * filled, style=colour)
    out.append("░" * (width - filled), style=PALETTE["border"])
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


def default_images() -> Mapping[str, int] | None:
    from inodefence.app import doctor

    return doctor.image_groups()


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
        with VerticalScroll(id="detail") as box:
            box.border_title = self._title
            yield Static(self._body, id="detail-body")


def _panel(widget_id: str, title: str) -> Static:
    panel = Static(id=widget_id, classes="panel")
    panel.border_title = title
    return panel


class InodeFenceTui(App[None]):
    TITLE = "InodeFence"
    #: read-only screen: no command palette (its built-in commands are not needed here)
    ENABLE_COMMAND_PALETTE = False
    CSS = f"""
    Screen {{ background: {DEEP}; color: {PALETTE["text"]}; }}
    * {{ scrollbar-background: {PANEL}; scrollbar-background-hover: {PANEL};
         scrollbar-color: {PALETTE["border"]}; scrollbar-size-horizontal: 0;
         scrollbar-size-vertical: 1; }}
    #header {{ height: 1; background: {PALETTE["surface_alt"]}; padding: 0 1; }}
    TabbedContent {{ height: 1fr; }}
    Tabs {{ background: {DEEP}; }}
    Tab {{ color: {PALETTE["muted"]}; }}
    Tab.-active {{ color: {PALETTE["accent"]}; }}
    TabPane {{ padding: 0; }}
    .panel, .box {{
        border: round {PALETTE["border"]}; border-title-color: {TITLE_COLOUR};
        border-subtitle-color: {PALETTE["muted"]}; background: {PANEL}; padding: 0 1;
    }}
    .box:focus-within {{ border: round {PALETTE["accent"]}; }}
    DataTable {{ background: {PANEL}; height: auto; max-height: 100%; }}
    DataTable > .datatable--header {{ background: {PANEL}; color: {PALETTE["muted"]}; }}
    DataTable > .datatable--cursor {{ background: #164e63; }}
    #ov-left {{ width: 2fr; }}
    #p-runs {{ width: 1fr; min-width: 58; }}
    #p-campaign {{ height: 9; }}
    #ov-mid {{ height: auto; }}
    #p-outcomes, #p-oracle {{ width: 1fr; height: auto; min-height: 9; }}
    #p-targets {{ height: auto; }}
    #p-scan {{ height: auto; color: {PALETTE["muted"]}; padding: 0 1; }}
    #p-events {{ height: 8; }}
    #events {{ background: {PANEL}; }}
    #empty {{ height: auto; }}
    #cmp-split, #find-split {{ height: 1fr; }}
    #p-campaign-list {{ width: 3fr; }}
    #p-run-detail {{ width: 2fr; min-width: 30; height: 1fr; }}
    #p-finding-list {{ width: 3fr; }}
    #p-finding-detail {{ width: 2fr; min-width: 32; height: 1fr; }}
    #ov-body.narrow {{ layout: vertical; }}
    #ov-body.narrow #p-campaign {{ height: 6; }}
    Screen.narrow #p-events {{ height: 5; }}
    #ov-body.narrow #ov-left {{ width: 1fr; height: auto; }}
    #ov-body.narrow #p-runs {{ width: 1fr; min-width: 0; height: 1fr; }}
    #find-split.narrow {{ layout: vertical; }}
    #find-split.narrow #p-finding-list, #find-split.narrow #p-finding-detail {{ width: 1fr; }}
    #findings-legend, #verify-title {{ height: 1; color: {PALETTE["muted"]}; }}
    DetailScreen {{ align: center middle; }}
    #detail {{ width: 90%; height: 80%; background: {PALETTE["surface_alt"]};
               border: round {PALETTE["accent"]}; border-title-color: {TITLE_COLOUR};
               padding: 0 1; }}
    Footer {{ background: {PALETTE["surface_alt"]}; }}
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
        images: Callable[[], Mapping[str, int] | None] | None = default_images,
        background: bool = True,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__()
        self.roots = [*(default_roots() if roots is None else roots), *extra]
        self.refresh_seconds = refresh
        self.follower = follower or RunFollower(roots=self.roots, interval=refresh, clock=clock)
        self._doctor, self._targets, self._images = doctor, targets, images
        self._background = background
        self._clock = clock
        self.state = DashboardState(roots=tuple(self.roots))
        self.events: deque[UiEvent] = deque(maxlen=EVENT_LINES)
        #: progress samples this screen observed, per run (the campaign graph; nothing earlier)
        self.history: dict[str, list[Sample]] = {}
        self.selected_key: str | None = None
        self._subscription = self.follower.subscribe()
        self._row_keys: dict[str, list[str]] = {}
        self._columns_ready = False

    # -- layout -------------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        with TabbedContent(id="tabs", initial="overview"):
            with TabPane("1 Overview", id="overview"):
                yield _panel("empty", "no runs")
                with Horizontal(id="ov-body"):
                    with Vertical(id="ov-left"):
                        yield _panel("p-campaign", "campaign")
                        with Horizontal(id="ov-mid"):
                            yield _panel("p-outcomes", "outcomes")
                            yield _panel("p-oracle", "oracle")
                        yield _panel("p-targets", "targets")
                        yield Static(id="p-scan")
                    with Vertical(id="p-runs", classes="box") as runs:
                        runs.border_title = "runs"
                        yield DataTable(id="runs-table", cursor_type="row")
            with TabPane("2 Targets", id="targets"):
                with Vertical(classes="box") as box:
                    box.border_title = "targets"
                    box.border_subtitle = "registry · doctor · scanned verify results"
                    yield DataTable(id="targets-table", cursor_type="row")
            with TabPane("3 Campaigns", id="campaigns"):
                with Horizontal(id="cmp-split"):
                    with Vertical(id="p-campaign-list", classes="box") as box:
                        box.border_title = "explore runs"
                        yield DataTable(id="campaigns-table", cursor_type="row")
                        yield Static("verify cells", id="verify-title")
                        yield DataTable(id="verify-table", cursor_type="row")
                    yield _panel("p-run-detail", "selected run")
            with TabPane("4 Findings", id="findings"):
                with Horizontal(id="find-split"):
                    with Vertical(id="p-finding-list", classes="box") as box:
                        box.border_title = "violation candidates"
                        box.border_subtitle = "oracle flags · not confirmed"
                        yield DataTable(id="findings-table", cursor_type="row")
                        yield Static(model.CONTRACT_LEGEND, id="findings-legend")
                    yield _panel("p-finding-detail", "candidate")
            with TabPane("5 Artifacts", id="artifacts"):
                with VerticalScroll(classes="box") as box:
                    box.border_title = "artifacts"
                    box.border_subtitle = "metadata and hashes only"
                    yield Static(id="artifacts-body")
        with Vertical(id="p-events", classes="box") as events:
            events.border_title = "events"
            events.border_subtitle = "u updated_at · r recorded_at · m mtime · o observed"
            yield RichLog(id="events", max_lines=EVENT_LINES, wrap=False, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        for name, columns in COLUMNS.items():
            self.query_one(f"#{name}-table", DataTable).add_columns(*columns)
        self._columns_ready = True
        self.query_one("#events", RichLog).write(Text(model.READ_ONLY_NOTE, style=PALETTE["muted"]))
        if self._background:
            self.follower.start()
            for loader in (self._load_engine, self._load_targets, self._load_images):
                self.run_worker(loader, thread=True, exclusive=False)
            self.set_interval(self.refresh_seconds, self.tick)
        self.tick()

    def on_unmount(self) -> None:
        self._subscription.close()
        self.follower.stop(timeout=2)

    # -- background reads (doctor, registry, images) ------------------------------------------

    def _load_engine(self) -> None:
        if self._doctor is not None:
            try:
                self.state.engine = self._doctor()
            except Exception as error:  # noqa: BLE001 -- shown as "unavailable", never raised
                self.state.engine_error = f"{type(error).__name__}: {error}"
        self.call_from_thread(self.redraw)

    def _load_targets(self) -> None:
        if self._targets is not None:
            try:
                self.state.targets = self._targets()
            except Exception as error:  # noqa: BLE001
                self.state.targets_error = f"{type(error).__name__}: {error}"
        self.call_from_thread(self.redraw)

    def _load_images(self) -> None:
        if self._images is not None:
            try:
                self.state.images = self._images()
            except Exception:  # noqa: BLE001 -- the column stays "—"
                self.state.images = None
        self.call_from_thread(self.redraw)

    def load_now(self) -> None:
        """Doctor, registry and images in this thread (tests, or when no background is wanted)."""
        for loader, attr in ((self._doctor, "engine"), (self._targets, "targets"),
                             (self._images, "images")):  # fmt: skip
            if loader is None:
                continue
            try:
                setattr(self.state, attr, loader())
            except Exception as error:  # noqa: BLE001
                if attr == "engine":
                    self.state.engine_error = str(error)
                elif attr == "targets":
                    self.state.targets_error = str(error)

    # -- refresh ------------------------------------------------------------------------------

    def tick(self) -> None:
        log = self.query_one("#events", RichLog)
        while (event := self._subscription.get(timeout=0)) is not None:
            self.events.append(event)
            log.write(event_text(event))
        self.state.events = list(self.events)
        self.state.snapshots = self.follower.snapshots()
        for key, snapshot in self.state.snapshots.items():
            model.observe(self.history.setdefault(key, []), snapshot)
        self.state.listings = discover_runs(self.roots, max_entries=2000)
        self.state.now = self._clock()
        self.redraw()

    def _wide(self) -> bool:
        return self.size.width >= WIDE_MIN_COLUMNS and self.size.height >= WIDE_MIN_ROWS

    def redraw(self) -> None:
        if not self._columns_ready:
            return
        state = self.state
        wide = self._wide()
        self.draw_selection()
        empty = model.is_empty(state)
        panel = self.query_one("#empty", Static)
        panel.display = empty
        if empty:
            panel.update(Text("\n").join(styled(cell) for cell in model.empty_lines(state)))
        self.query_one("#ov-body").display = not empty
        self.query_one("#ov-mid").display = wide
        self.query_one("#p-targets").display = wide
        self.query_one("#p-scan").display = wide
        self.query_one("#find-split").set_class(not wide, "narrow")
        self.query_one("#ov-body").set_class(not wide, "narrow")
        self.screen.set_class(not wide, "narrow")
        self._fill("runs", model.runs_list(state) or [_empty_row(4, "no explore runs")])
        targets = model.target_rows(state)
        if state.targets is None:
            reason = state.targets_error or "reading the registry…"
            targets = [_empty_row(5, f"targets unavailable: {reason}")]
        self._fill("targets", targets)
        self.query_one("#p-targets", Static).update(targets_text(state))
        scan = Text(model.READ_ONLY_NOTE, style=PALETTE["muted"])
        for root in state.roots:
            scan.append(f"\nscanning {root}", style=PALETTE["muted"])
        self.query_one("#p-scan", Static).update(scan)
        campaigns = model.campaign_rows(state)
        self._fill("campaigns", campaigns or [_empty_row(10, "no explore runs found")])
        verify = model.verify_rows(state)
        self._fill("verify", verify or [_empty_row(6, "no verify cells found")])
        findings = model.finding_rows(state)
        self._fill("findings", findings or [_empty_row(10, "no violation candidates")])

    def draw_selection(self) -> None:
        """Everything that follows the selected run: header, campaign/outcomes/oracle panels,
        the Campaigns detail, the Findings detail, Artifacts."""
        state = self.state
        selected = self._selected_snapshot()
        followed = selected or model.default_selection(state)
        self.query_one("#header", Static).update(header_text(state, selected, self._clock()))
        campaign = self.query_one("#p-campaign", Static)
        campaign.border_subtitle = (
            "following the newest run" if selected is None and followed else "selected run"
        )
        width = max(campaign.size.width - 42, 10)
        history = self.history.get(followed.ref.key, []) if followed else []
        campaign.update(
            campaign_view(followed, history, state.now, width, compact=not self._wide())
        )
        self.query_one("#p-outcomes", Static).update(outcomes_text(followed))
        oracle = self.query_one("#p-oracle", Static)
        oracle.border_subtitle = "case folders: lower bound" if followed else ""
        oracle.update(lines_text(model.oracle_lines(state, followed)))
        self.query_one("#p-run-detail", Static).update(run_detail_view(selected, state.now))
        self.query_one("#p-finding-detail", Static).update(self._finding_detail())
        self.query_one("#artifacts-body", Static).update(
            artifacts_text(model.artifact_lines(selected))
        )

    def _finding_detail(self) -> Text:
        key = self.selected_key
        if key is None or "#" not in key:
            return Text("select a candidate (↑ ↓)", style=PALETTE["muted"])
        return lines_text(model.finding_detail(self.state, key))

    def on_resize(self) -> None:
        self.redraw()

    def _fill(self, name: str, rows: Sequence[Row]) -> None:
        """Redraw a table in place, keeping the cursor on the same row KEY (the same run or
        finding) when it is still there, else on the same position (clamped)."""
        table = self.query_one(f"#{name}-table", DataTable)
        cursor = table.cursor_row
        old_keys = self._row_keys.get(name, [])
        kept = old_keys[cursor] if 0 <= cursor < len(old_keys) else None
        table.clear()
        badged = BADGE_COLUMNS.get(name)
        for row in rows:
            cells = [
                badge(cell) if index == badged and row.key != "-" else styled(cell)
                for index, cell in enumerate(row.cells)
            ]
            if name in PROGRESS_COLUMNS and row.key != "-":
                cells[PROGRESS_COLUMNS[name]] = progress_cell(self.state.snapshots.get(row.key))
            table.add_row(*cells)
        keys = [row.key for row in rows]
        self._row_keys[name] = keys
        if rows:
            target = keys.index(kept) if kept is not None and kept in keys else cursor
            table.move_cursor(row=min(max(target, 0), len(rows) - 1))

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
            table = tables.first()
            table.focus()  # keys move rows right away
            name = (table.id or "").removesuffix("-table")
            keys = self._row_keys.get(name, [])
            row = table.cursor_row
            if name in SELECTING and 0 <= row < len(keys) and keys[row] != "-":
                self.selected_key = keys[row]  # the panels follow the row the cursor is on
                self.draw_selection()

    def action_refresh_now(self) -> None:
        self.follower.poll_once()
        self.tick()

    def action_help(self) -> None:
        body = Text()
        for key, what in (
            ("1-5", "Overview · Targets · Campaigns · Findings · Artifacts"),
            ("↑ ↓ / j k", "move in a list; the panels follow the highlighted run"),
            ("enter", "candidate detail, or the artifacts of a run"),
            ("esc", "close a detail"),
            ("r", "re-read now"),
            ("q", "quit"),
        ):
            body.append(f"{key:<10} {what}\n")
        body.append("\n" + model.CONTRACT_LEGEND + "\n")
        body.append("? as a number: the files do not hold it (only node-tar writes live numbers)\n")
        body.append("the campaign graph shows only what this screen observed since it opened\n")
        body.append(
            "a violation is a candidate; a replay says how many judged rounds repeated it\n"
        )
        body.append(model.TIME_LEGEND + "\n\n")
        for line in model.scanned_lines(self.state):
            body.append(line + "\n", style=PALETTE["muted"])
        self.push_screen(DetailScreen("help", body))

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        name = (message.data_table.id or "").removesuffix("-table")
        keys = self._row_keys.get(name, [])
        # Only the table the user is in selects (a redraw highlights rows in every table).
        if not message.data_table.has_focus:
            return
        if name in SELECTING and 0 <= message.cursor_row < len(keys):
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
            self.push_screen(DetailScreen(f"candidate {key.split('#', 1)[-1]}", lines_text(lines)))
        elif name in ("runs", "campaigns", "verify"):
            self.action_show("artifacts")


#: Which column of a table is a state shown as a badge (symbol + word).
BADGE_COLUMNS = {"runs": 1, "campaigns": 3, "verify": 1}
#: Which column is runs/budget, drawn as a coloured bar from the run's real numbers.
PROGRESS_COLUMNS = {"runs": 2, "campaigns": 4}


# -- panel renderers (Rich renderables from model values) ------------------------------------------


def header_text(state: DashboardState, selected: RunSnapshot | None, now: float) -> Text:
    out = Text()
    for index, (label, cell) in enumerate(model.header(state, selected)):
        if index:
            out.append(" │ ", style=PALETTE["border"])
        if label:
            out.append(f"{label} ", style=PALETTE["muted"])
        shown = label in ("engine", "state") and cell.text != model.NONE
        out.append_text(badge(cell) if shown else styled(cell))
    out.append(" │ ", style=PALETTE["border"])
    out.append(datetime.fromtimestamp(now).strftime("%H:%M:%S"), style=PALETTE["muted"])
    return out


def campaign_view(
    snapshot: RunSnapshot | None,
    history: Sequence[Sample],
    now: float,
    width: int,
    *,
    compact: bool = False,
) -> Table:
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(ratio=1)
    grid.add_column(width=38)
    graph = Text()
    values = model.increments(history)
    line = model.sparkline(values, width)
    if snapshot is None:
        graph.append("no explore run found", style=PALETTE["muted"])
    elif not line:
        live = snapshot.progress is not None and snapshot.progress.source.value == "live"
        graph.append(
            "waiting for a second progress snapshot" if live else "no live data for this run",
            style=PALETTE["muted"],
        )
        if not live:
            graph.append("\n(only node-tar writes running numbers)", style=PALETTE["muted"])
    else:
        top = max(v for v in values if v is not None)
        rows = 3
        if not compact:
            graph.append(f"runs between snapshots · max {top:.0f}\n", style=PALETTE["muted"])
        for row in range(rows, 0, -1):  # a 3-line graph from the same samples
            graph.append(_graph_row(values[-width:], row) + "\n", style=PALETTE["accent"])
        observed = f"{len(history)} snapshots observed by this screen"
        graph.append(observed if not compact else f"max {top:.0f}/snapshot · {len(history)} seen",
                     style=PALETTE["muted"])  # fmt: skip
    side = Text()
    details = model.run_detail(snapshot, now)[1:]
    if compact:
        details = [d for d in details if d[0] in ("state", "runs", "rate")]
    for label, cell in details:
        side.append(f"{label:<9}", style=PALETTE["muted"])
        side.append_text(badge(cell) if label == "state" else styled(cell))
        side.append("\n")
    p = snapshot.progress if snapshot else None
    side.append(f"{'progress':<9}", style=PALETTE["muted"])
    side.append_text(bar_text(p.runs if p else None, p.budget if p else None, 20))
    grid.add_row(graph, side)
    return grid


def _graph_row(values: Sequence[float | None], level: int) -> str:
    known = [v for v in values if v is not None]
    if not known:
        return ""
    top = max(known) or 1.0
    out = []
    for v in values:
        if v is None:
            out.append(" ")
            continue
        fill = v / top * 3 - (level - 1)  # this row's share of a 3-row column
        if fill >= 1:
            out.append("█")
        elif fill <= 0:
            out.append("▁" if level == 1 else " ")
        else:
            out.append(model.SPARK[min(7, max(0, round(fill * 7)))])
    return "".join(out)


def progress_cell(snapshot: RunSnapshot | None) -> Text:
    """``███░░░ 91/200`` from real numbers; ``?/?`` and no bar when unknown."""
    p = snapshot.progress if snapshot else None
    runs, budget = (p.runs, p.budget) if p else (None, None)
    numbers = f"{model.count(runs)}/{model.count(budget)}"
    if model.bar(runs, budget, 10) is None:
        return Text(numbers, style=PALETTE["muted"])
    out = bar_text(runs, budget, 10)
    out.append(f" {numbers}")
    return out


def outcomes_text(snapshot: RunSnapshot | None) -> Text:
    if snapshot is None:
        return Text("no run selected", style=PALETTE["muted"])
    out = Text()
    for label, value, total, style in model.outcome_rows(snapshot):
        out.append(f"{label:<14}", style=PALETTE["muted"])
        tone = (COLOURS.get(style) or PALETTE["text"]) if value else PALETTE["muted"]
        out.append(f"{model.count(value):>6} ", style=tone)
        drawn = model.bar(value, total, 14) if value is not None else None
        if drawn is not None:
            out.append(drawn.replace("░", " "), style=COLOURS.get(style) or PALETTE["accent"])
        out.append("\n")
    out.rstrip()
    return out


def targets_text(state: DashboardState) -> Text:
    lines = model.target_lines(state)
    if not lines:
        reason = state.targets_error or "reading the registry…"
        return Text(f"targets unavailable: {reason}", style=PALETTE["muted"])
    out = Text()
    for name, caps, images, verified in lines:
        out.append(f"{name:<16}", style=PALETTE["accent"])
        out.append(f"{caps.text:<16}", style=PALETTE["muted"])
        out.append("images ", style=PALETTE["muted"])
        out.append_text(styled(images))
        out.append("   last verify ", style=PALETTE["muted"])
        out.append_text(styled(verified))
        out.append("\n")
    out.rstrip()
    return out


def run_detail_view(snapshot: RunSnapshot | None, now: float) -> Text:
    if snapshot is None:
        return Text("select a run (↑ ↓)", style=PALETTE["muted"])
    out = lines_text(model.run_detail(snapshot, now), width=8)
    p = snapshot.progress
    out.append("\n\n")
    out.append(f"{'progress':<10}", style=PALETTE["muted"])
    out.append_text(bar_text(p.runs if p else None, p.budget if p else None, 18))
    out.append("\n\n")
    out.append_text(outcomes_text(snapshot))
    return out


def artifacts_text(lines: Sequence[tuple[str, Cell]]) -> Text:
    """The artifacts as a tree-like list: sections, then indented entries."""
    out = Text()
    for label, cell in lines:
        branch = "  └ " if label.startswith("  ") else "▸ "
        out.append(branch, style=PALETTE["border"])
        out.append(f"{label.strip():<18}", style=PALETTE["muted"])
        out.append_text(styled(cell))
        out.append("\n")
    out.rstrip()
    return out


def event_text(event: UiEvent) -> Text:
    when, kind, run, content = model.event_cells(event)
    out = Text()
    widths = model.EVENT_WIDTHS
    out.append(f"{when.text:<{widths[0]}} ", style=PALETTE["muted"])
    out.append_text(styled(Cell(f"{kind.text:<{widths[1]}} ", kind.style)))
    out.append(f"{run.text:<{widths[2]}} ")
    out.append_text(styled(content))
    return out


def _empty_row(width: int, message: str) -> Row:
    return Row("-", (Cell(message, model.DIM), *(Cell("") for _ in range(width - 1))))
