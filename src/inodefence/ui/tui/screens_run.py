"""The TUI's run screens: pick a command, fill its form, confirm, and read what it printed.

Nothing here starts a process; :mod:`inodefence.ui.tui.launch` does, when the app calls it after a
confirmation. The forms come from the CLI's parser (:mod:`inodefence.ui.tui.forms`); this module
only lays them out. A command that starts Docker (verify, explore, replay) is shown in full in
:class:`ConfirmScreen` -- the focus is on *Cancel*, a ``--dry-run`` plan can be read first, and a
budget above :data:`BUDGET_RECONFIRM` needs *Start* twice (decided 2026-11-20). The CLI checks
every value; its refusal is shown as it printed it.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    DataTable,
    Input,
    Label,
    OptionList,
    Select,
    Static,
)
from textual.widgets.option_list import Option

from inodefence.target_result import LABEL
from inodefence.ui.tui import launch as launch_records
from inodefence.ui.tui.forms import CommandForm, Field, FieldKind, command_line, missing_required
from inodefence.ui.tui.palette import PALETTE, TITLE

#: Above this budget the confirmation asks once more (a warning; the cap itself is the CLI's).
BUDGET_RECONFIRM = 2000
#: One line on every confirmation of a run: what kind of record it makes, in the result's own words.
PRODUCT_RUN = (
    f'product run: its result is labelled "{LABEL}" (not a qualification or experiment result)'
)


def _within(path: Path, roots: Iterable[Path]) -> bool:
    resolved = path.expanduser().resolve()
    return any(resolved.is_relative_to(Path(root).expanduser().resolve()) for root in roots)


def out_folder(values: Mapping[str, Any], cwd: Path) -> Path | None:
    """The ``--out`` the command will use, resolved as the CLI does (against the working folder)."""
    out = values.get("out")
    if out in (None, ""):
        return None
    path = Path(str(out)).expanduser()
    return path if path.is_absolute() else cwd / path


def confirm_notes(
    form: CommandForm,
    values: Mapping[str, Any],
    *,
    cwd: Path,
    roots: Sequence[Path],
    running_targets: Iterable[str | None] = (),
) -> list[str]:
    """What the confirmation says besides the command line. Warnings only: nothing is refused here
    (the CLI refuses what it refuses, and the screen shows it)."""
    notes = [PRODUCT_RUN]
    budget = values.get("budget")
    if budget not in (None, "") and str(budget).isdigit() and int(str(budget)) > BUDGET_RECONFIRM:
        notes.append(f"! budget {budget} is above {BUDGET_RECONFIRM}: Start asks once more")
    if values.get("verbose"):
        notes.append(
            "! --verbose shows the launcher's raw output and writes no launcher log: this run is "
            "not on the screen until it ends"
        )
    if values.get("auto_prepare"):
        notes.append("--auto-prepare may build the target's Docker image first")
    out = out_folder(values, cwd)
    if out is not None and not _within(out, roots):
        notes.append(
            f"! --out {out} is outside this screen's folders: added for this session only "
            f"(later: inodefence tui {out})"
        )
    target = values.get("target") or "node-tar"
    if form.name == "explore" and target in set(running_targets):
        notes.append(f"! a {target} exploration is already running here (the CLI allows a second)")
    return notes


# -- the command line, wrapped where a person would wrap it --------------------------------------


def command_units(argv: Sequence[str]) -> list[str]:
    """``argv`` as shell-quoted units: an option with its value is one unit, never split."""
    units: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if (
            token.startswith("-")
            and index + 1 < len(argv)
            and not argv[index + 1].startswith("-")
            and index >= 2  # "inodefence <command>" stay apart
        ):
            units.append(f"{shlex.quote(token)} {shlex.quote(argv[index + 1])}")
            index += 2
        else:
            units.append(shlex.quote(token))
            index += 1
    return units


def wrapped_command(argv: Sequence[str], width: int) -> str:
    """The command line in lines of at most ``width``, broken only between options, each continued
    line ending in `` \\`` and the next indented -- still pastes into a shell as it is."""
    lines: list[str] = []
    current = ""
    for unit in command_units(argv):
        candidate = f"{current} {unit}" if current else unit
        if current and len(candidate) + 2 > width:
            lines.append(current + " \\")
            current = "  " + unit
        else:
            current = candidate
    lines.append(current)
    return "\n".join(lines)


# -- pick a command ------------------------------------------------------------------------------


class CommandPicker(ModalScreen[str | None]):
    """The CLI's sub-commands with their own help line: the three that start Docker first."""

    BINDINGS = [Binding("escape", "dismiss(None)", "cancel")]

    def __init__(self, forms: Mapping[str, CommandForm]) -> None:
        super().__init__()
        self._forms = forms

    def _option(self, name: str, form: CommandForm) -> Option:
        line = Text(f"{name:<9}", style=f"bold {TITLE}")
        # the kind in a fixed column right after the name, so the two groups read at a glance
        if form.starts_docker:
            line.append(f"{'starts Docker':<15}", style=PALETTE["warn"])
        else:
            line.append(f"{'reads only':<15}", style=PALETTE["muted"])
        line.append(form.help)  # Text: a help line is never read as markup
        return Option(line, id=name)

    def compose(self) -> ComposeResult:
        docker = [n for n, f in self._forms.items() if f.starts_docker]
        reading = [n for n, f in self._forms.items() if not f.starts_docker]
        options: list[Option | None] = [self._option(n, self._forms[n]) for n in docker]
        options.append(None)  # a separator between the two groups
        options += [self._option(n, self._forms[n]) for n in reading]
        with Vertical(id="picker", classes="run-box") as box:
            box.border_title = "run a command"
            box.border_subtitle = "enter: choose · esc: cancel"
            yield OptionList(*options, id="picker-list")

    def on_option_list_option_selected(self, message: OptionList.OptionSelected) -> None:
        self.dismiss(message.option.id)


# -- fill the form -------------------------------------------------------------------------------

#: Shown above "more options", in this order when the command has them (the rest go below).
COMMON = ("target", "version", "budget", "seed", "auto_prepare", "case_dir", "case", "rounds",
          "folder", "result", "a", "b")  # fmt: skip


def _widget_id(field: Field) -> str:
    return f"field-{field.dest}"


def ordered_fields(form: CommandForm) -> tuple[list[Field], list[Field]]:
    """``(main, more)``: required fields, then :data:`COMMON` ones, then target-only ones in the
    main group; every other field under "more options"."""
    rank = {dest: index for index, dest in enumerate(COMMON)}
    main = [f for f in form.fields if f.required or f.dest in rank or f.target is not None]
    main.sort(key=lambda f: (0 if f.required and f.target is None else 1, rank.get(f.dest, 99)))
    more = [f for f in form.fields if f not in main]
    return main, more


class CommandFormScreen(ModalScreen[tuple[list[str], dict[str, Any]] | None]):
    """One command's options as the parser defines them; returns ``(argv, values)`` or ``None``."""

    BINDINGS = [Binding("escape", "dismiss(None)", "cancel")]

    def __init__(
        self,
        form: CommandForm,
        *,
        targets: Sequence[str] = (),
        preset: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.form = form
        self._targets = list(targets)
        self._preset = dict(preset or {})
        self._help = {_widget_id(f): f.help for f in form.fields}

    def _target(self) -> str | None:
        try:
            widget = self.query_one("#field-target", Select)
        except Exception:  # noqa: BLE001 -- commands without --target
            return None
        value = widget.value
        return value if isinstance(value, str) else None

    def _row(self, field: Field) -> Horizontal:
        value = self._preset.get(field.dest, field.default)
        label = (field.flag or field.dest) + (" *" if field.required else "")
        scope = f" ({field.target})" if field.target else ""
        widget: Any
        choices = field.choices
        if field.dest == "target" and not choices and self._targets:
            choices = tuple(self._targets)
        if field.kind is FieldKind.FLAG:
            widget = Checkbox("", value=bool(value), id=_widget_id(field))
        elif choices:
            current = value if value in choices else Select.NULL
            widget = Select([(c, c) for c in choices], value=current,
                            allow_blank=not field.required or current is Select.NULL,
                            id=_widget_id(field), compact=True)  # fmt: skip
        else:
            shown = ", ".join(map(str, value)) if isinstance(value, list | tuple) else value
            hint = "comma-separated" if field.kind is FieldKind.REPEAT else field.help
            widget = Input(value="" if shown in (None, "") else str(shown), placeholder=hint,
                           id=_widget_id(field), compact=True)  # fmt: skip
        return Horizontal(Label(label + scope, classes="field-label"), widget, classes="field")

    def compose(self) -> ComposeResult:
        main, more = ordered_fields(self.form)
        with Vertical(id="form", classes="run-box") as box:
            box.border_title = f"inodefence {self.form.name}"
            box.border_subtitle = (
                "starts Docker after a confirmation" if self.form.starts_docker else "reads only"
            )
            with VerticalScroll(id="form-fields"):
                for field in main:
                    yield self._row(field)
                if more:
                    yield Collapsible(*(self._row(f) for f in more), title="more options",
                                      id="form-more")  # fmt: skip
            yield Static("", id="form-help")
            yield Static("", id="form-error")
            with Horizontal(id="form-buttons"):
                yield Static("* required · the CLI checks every value", id="form-note")
                yield Button("Cancel", id="form-cancel", compact=True)
                yield Button("Continue", id="form-continue", compact=True)

    def on_mount(self) -> None:
        self._show_target_fields()

    def on_descendant_focus(self, event: Any) -> None:
        widget_id = getattr(event.widget, "id", None) or ""
        self.query_one("#form-help", Static).update(Text(self._help.get(widget_id, "")))

    def _show_target_fields(self) -> None:
        target = self._target()
        for field in self.form.fields:
            if field.target is None:
                continue
            row = self.query_one(f"#{_widget_id(field)}").parent
            if row is not None and isinstance(row, Horizontal):
                row.display = field.target == target

    def on_select_changed(self, message: Select.Changed) -> None:
        if message.select.id == "field-target":
            self._show_target_fields()

    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field in self.form.fields:
            widget = self.query_one(f"#{_widget_id(field)}")
            if isinstance(widget, Checkbox):
                out[field.dest] = widget.value
            elif isinstance(widget, Select):
                out[field.dest] = None if widget.value is Select.NULL else widget.value
            elif isinstance(widget, Input):
                text = widget.value.strip()
                if field.kind is FieldKind.REPEAT:
                    out[field.dest] = [part.strip() for part in text.split(",") if part.strip()]
                else:
                    out[field.dest] = text or None
        return out

    def on_button_pressed(self, message: Button.Pressed) -> None:
        if message.button.id == "form-cancel":
            self.dismiss(None)
            return
        values = self.values()
        target = self._target()
        missing = missing_required(self.form, values, target)
        if missing:
            self.query_one("#form-error", Static).update("required: " + ", ".join(missing))
            return
        self.dismiss((command_line(self.form, values, target), values))


# -- confirm -------------------------------------------------------------------------------------


def notes_text(notes: Sequence[str]) -> Text:
    """The confirmation's notes: a line starting with ``!`` is a warning (amber), the rest plain."""
    out = Text()
    for index, note in enumerate(notes):
        if index:
            out.append("\n")
        out.append(note, style=PALETTE["warn"] if note.startswith("!") else PALETTE["text"])
    return out


class ConfirmScreen(ModalScreen[bool]):
    """The whole command line before anything starts; the focus is on Cancel."""

    BINDINGS = [Binding("escape", "dismiss(False)", "cancel")]

    def __init__(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        program: str,
        notes: Sequence[str],
        plan: Callable[[], tuple[int | None, str]] | None = None,
        reconfirm: bool = False,
        width: int = 92,
    ) -> None:
        super().__init__()
        self.argv = list(argv)
        self._cwd, self._program, self._notes = cwd, program, list(notes)
        self._plan = plan
        self._reconfirm = reconfirm
        self._asked_once = False
        self._width = width

    def compose(self) -> ComposeResult:
        command = self.argv[1] if len(self.argv) > 1 else ""
        with Vertical(id="confirm", classes="run-box") as box:
            box.border_title = f"start {command}? · starts Docker"
            box.border_subtitle = "nothing runs until Start · esc: cancel"
            yield Static(Text(wrapped_command(self.argv, self._width)), id="confirm-command")
            yield Static(Text(f"in {self._cwd}\nprogram {self._program}"), id="confirm-where")
            yield Static(notes_text(self._notes), id="confirm-notes")
            yield VerticalScroll(
                Static("", id="confirm-plan-body", markup=False), id="confirm-plan"
            )
            with Horizontal(id="confirm-buttons"):
                if self._plan is not None:
                    yield Button("Plan (--dry-run)", id="confirm-plan-button", compact=True)
                yield Button("Cancel", id="confirm-cancel", compact=True)
                yield Button("Start", id="confirm-start", compact=True)

    def on_mount(self) -> None:
        self.query_one("#confirm-cancel", Button).focus()  # one Enter never starts a run

    def on_button_pressed(self, message: Button.Pressed) -> None:
        button = message.button.id
        if button == "confirm-cancel":
            self.dismiss(False)
        elif button == "confirm-plan-button" and self._plan is not None:
            self.query_one("#confirm-plan-body", Static).update(
                "planning (the CLI with --dry-run; nothing runs)…"
            )
            self.run_worker(self._show_plan, thread=True, exclusive=True)
        elif button == "confirm-start":
            if self._reconfirm and not self._asked_once:
                self._asked_once = True
                notes = [*self._notes, "! press Start once more to start this budget"]
                self.query_one("#confirm-notes", Static).update(notes_text(notes))
                self.query_one("#confirm-cancel", Button).focus()
                return
            self.dismiss(True)

    def _show_plan(self) -> None:
        assert self._plan is not None
        code, output = self._plan()
        head = "plan (exit ?)" if code is None else f"plan (exit {code})"
        self.app.call_from_thread(
            self.query_one("#confirm-plan-body", Static).update, f"{head}\n{output.rstrip()}"
        )


# -- what a command printed ----------------------------------------------------------------------


class OutputScreen(ModalScreen[None]):
    """A command that runs nothing (doctor, targets, status, summary, compare): its output as
    printed, and its exit code."""

    BINDINGS = [Binding("escape,q", "dismiss", "close")]

    def __init__(self, argv: Sequence[str], body: str) -> None:
        super().__init__()
        self._argv, self._body = list(argv), body

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="output", classes="run-box") as box:
            box.border_title = shlex.join(self._argv)
            box.border_subtitle = "esc: close"
            yield Static(self._body, id="output-body", markup=False)


# -- the commands this screen started ------------------------------------------------------------


def _short_time(stamp: str | None) -> str:
    """``2026-11-20T02:17:43Z`` -> ``11-20 02:17:43Z`` (UTC, as recorded)."""
    return stamp[5:].replace("T", " ") if stamp else "?"


def _state_style(text: str) -> str:
    if text == "running":
        return PALETTE["accent"]
    if text.startswith(("exit 0", "record not", "ended")):
        return PALETTE["muted"] if not text.startswith("exit 0") else PALETTE["ok"]
    if "FAIL" in text:  # a judged violation: the run's verdict, not an error of the screen
        return PALETTE["warn"]
    return PALETTE["text"]


class LaunchesScreen(ModalScreen[str | None]):
    """Commands started from this TUI (their launch records), newest first: the command, its state
    (running, or the exit code with the CLI's meaning) and the tail of what it printed. Read every
    second; Enter on one dismisses with its ``--out`` folder (or ``None``) so the app can go there.
    """

    BINDINGS = [Binding("escape,q", "dismiss(None)", "close")]

    def __init__(self, records: Callable[[], Sequence[launch_records.Launch]]) -> None:
        super().__init__()
        self._records = records
        self._shown: list[launch_records.Launch] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="launches", classes="run-box") as box:
            box.border_title = "my commands"
            box.border_subtitle = "started from this screen · enter: go to its folder · esc: close"
            yield DataTable(id="launches-table", cursor_type="row")
            yield VerticalScroll(Static("", id="launch-detail", markup=False), id="launch-box")

    def on_mount(self) -> None:
        table = self.query_one("#launches-table", DataTable)
        table.add_columns("started (UTC)", "command", "state")
        self.reload()
        self.set_interval(1.0, self.reload)

    def reload(self) -> None:
        table = self.query_one("#launches-table", DataTable)
        cursor = table.cursor_row
        self._shown = list(self._records())
        table.clear()
        if not self._shown:
            table.add_row("—", "nothing started from this screen yet (n: run a command)", "")
        for record in self._shown:
            state = launch_records.state_text(record)
            command = " ".join(record.argv[1:]) or "?"
            table.add_row(_short_time(record.started_at), command[:70],
                          Text(state, style=_state_style(state)))  # fmt: skip
        if self._shown:
            table.move_cursor(row=min(max(cursor, 0), len(self._shown) - 1))
        self._show_detail()

    def _selected(self) -> launch_records.Launch | None:
        cursor = self.query_one("#launches-table", DataTable).cursor_row
        return self._shown[cursor] if 0 <= cursor < len(self._shown) else None

    def _show_detail(self) -> None:
        record = self._selected()
        body = self.query_one("#launch-detail", Static)
        if record is None:
            body.update("")
            return
        lines = [
            shlex.join(record.argv),  # the raw command, on one line, to copy
            f"in {record.cwd}",
            f"started {record.started_at or '?'} · ended {record.ended_at or '—'}",
            f"state {launch_records.state_text(record)}",
            f"record {record.folder}",
            "",
            *launch_records.output_tail(record, 20),
        ]
        body.update("\n".join(lines))

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        self._show_detail()

    def on_data_table_row_selected(self, message: DataTable.RowSelected) -> None:
        record = self._selected()
        if record is None:
            return
        argv = list(record.argv)
        out = argv[argv.index("--out") + 1] if "--out" in argv[:-1] else None
        self.dismiss(str(Path(record.cwd) / out) if out else None)


_SURFACE, _PANEL, _RAISED = PALETTE["surface"], PALETTE["surface_alt"], PALETTE["surface_raised"]
RUN_CSS = f"""
CommandPicker, CommandFormScreen, ConfirmScreen, OutputScreen, LaunchesScreen {{
    align: center middle; background: {_SURFACE} 60%;
}}
.run-box {{
    border: round {PALETTE["border"]}; border-title-color: {TITLE};
    border-subtitle-color: {PALETTE["muted"]}; background: {_PANEL}; padding: 0 1;
}}
#picker {{ width: 96; max-width: 100%; height: auto; max-height: 90%; }}
#picker-list {{ background: {_PANEL}; border: none; }}
#picker-list > .option-list--option-highlighted {{ background: #164e63; }}
#form {{ width: 96; max-width: 100%; height: auto; max-height: 100%; }}
#form-fields {{ height: auto; max-height: 1fr; }}
.field {{ height: 1; }}
.field-label {{ width: 26; color: {PALETTE["muted"]}; }}
.field Input, .field Select {{ width: 1fr; background: {_RAISED}; }}
.field Input:focus, .field Select:focus-within {{ background: #164e63; }}
.field Checkbox {{ border: none; padding: 0; height: 1; width: auto; background: {_PANEL}; }}
.field Select > SelectCurrent {{ background: {_RAISED}; border: none; }}
.field Select:focus-within > SelectCurrent {{ background: #164e63; }}
#form-more {{ background: {_PANEL}; border: none; padding: 0; margin: 0; height: auto; }}
#form-more > Contents {{ padding: 0; }}
#form-more CollapsibleTitle {{ color: {TITLE}; padding: 0; }}
#form-help {{ color: {PALETTE["muted"]}; height: auto; }}
#form-error {{ color: {PALETTE["warn"]}; height: auto; }}
#form-buttons, #confirm-buttons {{ height: 1; margin-top: 1; align: right middle; }}
#form-note {{ width: 1fr; color: {PALETTE["muted"]}; }}
.run-box Button {{
    background: {_RAISED}; color: {PALETTE["text"]}; margin-left: 2; min-width: 10;
}}
.run-box Button:focus {{ background: {PALETTE["accent"]}; color: {_SURFACE}; text-style: bold; }}
#confirm {{ width: 100; max-width: 100%; height: auto; max-height: 100%; }}
#confirm-command {{ color: {PALETTE["accent"]}; height: auto; }}
#confirm-where {{ color: {PALETTE["muted"]}; height: auto; }}
#confirm-notes {{ height: auto; margin: 1 0 0 0; }}
#confirm-plan {{ height: auto; max-height: 12; }}
#output {{ width: 100; max-width: 100%; height: 90%; }}
#launches {{ width: 110; max-width: 100%; height: 90%; }}
#launches-table {{ height: auto; max-height: 12; background: {_PANEL}; }}
#launches-table > .datatable--header {{ background: {_PANEL}; color: {PALETTE["muted"]}; }}
#launches-table > .datatable--cursor {{ background: #164e63; }}
#launch-box {{ height: 1fr; margin-top: 1; }}
#launch-detail {{ color: {PALETTE["text"]}; }}
"""
