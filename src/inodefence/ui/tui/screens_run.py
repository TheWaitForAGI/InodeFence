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
from textual.widgets import Button, Checkbox, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

from inodefence.target_result import LABEL
from inodefence.ui.tui.forms import CommandForm, Field, FieldKind, command_line, missing_required

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


# -- pick a command ------------------------------------------------------------------------------


class CommandPicker(ModalScreen[str | None]):
    """The CLI's sub-commands with their own help line."""

    BINDINGS = [Binding("escape", "dismiss(None)", "cancel")]

    def __init__(self, forms: Mapping[str, CommandForm]) -> None:
        super().__init__()
        self._forms = forms

    def compose(self) -> ComposeResult:
        with Vertical(id="picker", classes="run-box") as box:
            box.border_title = "run a command"
            box.border_subtitle = "enter: choose · esc: cancel"
            yield OptionList(
                *(
                    Option(Text(f"{name:<9} {form.help}"  # Text: a help line is never markup
                                + ("  · starts Docker" if form.starts_docker else "")), id=name)
                    for name, form in self._forms.items()
                ),
                id="picker-list",
            )  # fmt: skip

    def on_option_list_option_selected(self, message: OptionList.OptionSelected) -> None:
        self.dismiss(message.option.id)


# -- fill the form -------------------------------------------------------------------------------


def _widget_id(field: Field) -> str:
    return f"field-{field.dest}"


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

    def _target(self) -> str | None:
        try:
            widget = self.query_one("#field-target", Select)
        except Exception:  # noqa: BLE001 -- commands without --target
            return None
        value = widget.value
        return value if isinstance(value, str) else None

    def _input(self, field: Field) -> Any:
        value = self._preset.get(field.dest, field.default)
        label = field.flag or field.dest
        mark = " *" if field.required else ""
        scope = f"  ({field.target} only)" if field.target else ""
        if field.kind is FieldKind.FLAG:
            return Checkbox(f"{label}{scope}", value=bool(value), id=_widget_id(field),
                            tooltip=field.help)  # fmt: skip
        choices = field.choices
        if field.dest == "target" and not choices and self._targets:
            choices = tuple(self._targets)
        if choices:
            options = [(c, c) for c in choices]
            current = value if value in choices else Select.NULL
            blank = not field.required or current is Select.NULL
            return Vertical(
                Label(f"{label}{mark}{scope}", classes="field-label"),
                Select(options, value=current, allow_blank=blank, id=_widget_id(field),
                       tooltip=field.help),
                classes="field",
            )  # fmt: skip
        shown = ", ".join(map(str, value)) if isinstance(value, list | tuple) else value
        hint = "comma-separated" if field.kind is FieldKind.REPEAT else field.help
        return Vertical(
            Label(f"{label}{mark}{scope}", classes="field-label"),
            Input(value="" if shown in (None, "") else str(shown), placeholder=hint[:80],
                  id=_widget_id(field), tooltip=field.help),
            classes="field",
        )  # fmt: skip

    def compose(self) -> ComposeResult:
        with Vertical(id="form", classes="run-box") as box:
            box.border_title = f"inodefence {self.form.name}"
            box.border_subtitle = "* required · the CLI checks every value · esc: cancel"
            with VerticalScroll(id="form-fields"):
                for field in self.form.fields:
                    yield self._input(field)
            yield Static("", id="form-error")
            with Horizontal(id="form-buttons"):
                yield Button("Cancel", id="form-cancel")
                yield Button("Continue", id="form-continue", variant="primary")

    def on_mount(self) -> None:
        self._show_target_fields()

    def _show_target_fields(self) -> None:
        target = self._target()
        for field in self.form.fields:
            if field.target is None:
                continue
            widget = self.query_one(f"#{_widget_id(field)}")
            holder = (
                widget.parent
                if widget.parent is not None and widget.parent.has_class("field")
                else widget
            )
            holder.display = field.target == target  # fmt: skip

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
    ) -> None:
        super().__init__()
        self.argv = list(argv)
        self._cwd, self._program, self._notes = cwd, program, list(notes)
        self._plan = plan
        self._reconfirm = reconfirm
        self._asked_once = False

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm", classes="run-box") as box:
            box.border_title = f"start {self.argv[1] if len(self.argv) > 1 else ''}?"
            box.border_subtitle = "nothing runs until Start · esc: cancel"
            yield Static(shlex.join(self.argv), id="confirm-command")
            yield Static(f"in {self._cwd}\nprogram {self._program}", id="confirm-where")
            yield Static("\n".join(self._notes), id="confirm-notes")
            yield VerticalScroll(Static("", id="confirm-plan-body"), id="confirm-plan")
            with Horizontal(id="confirm-buttons"):
                if self._plan is not None:
                    yield Button("Plan (--dry-run)", id="confirm-plan-button")
                yield Button("Cancel", id="confirm-cancel")
                yield Button("Start", id="confirm-start", variant="warning")

    def on_mount(self) -> None:
        self.query_one("#confirm-cancel", Button).focus()  # one Enter never starts a run

    def on_button_pressed(self, message: Button.Pressed) -> None:
        button = message.button.id
        if button == "confirm-cancel":
            self.dismiss(False)
        elif button == "confirm-plan-button" and self._plan is not None:
            body = self.query_one("#confirm-plan-body", Static)
            body.update("planning (the CLI with --dry-run; nothing runs)…")
            self.run_worker(self._show_plan, thread=True, exclusive=True)
        elif button == "confirm-start":
            if self._reconfirm and not self._asked_once:
                self._asked_once = True
                self.query_one("#confirm-notes", Static).update(
                    "\n".join([*self._notes, "! press Start once more to start this budget"])
                )
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
    printed, and its exit code with the CLI's meaning."""

    BINDINGS = [Binding("escape,q", "dismiss", "close")]

    def __init__(self, argv: Sequence[str], body: str) -> None:
        super().__init__()
        self._argv, self._body = list(argv), body

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="output", classes="run-box") as box:
            box.border_title = shlex.join(self._argv)
            box.border_subtitle = "esc: close"
            yield Static(self._body, id="output-body", markup=False)


RUN_CSS = """
.run-box { border: round $accent; background: $surface; padding: 0 1; }
#picker { width: 90; height: auto; max-height: 20; }
#form { width: 96; height: 90%; }
#form-fields { height: 1fr; }
.field { height: auto; }
.field-label { color: $text-muted; }
#form-error { color: $warning; height: auto; }
#form-buttons, #confirm-buttons { height: 3; align: right middle; }
#confirm { width: 100; height: auto; max-height: 90%; }
#confirm-command { color: $accent; text-style: bold; height: auto; }
#confirm-where { color: $text-muted; height: auto; }
#confirm-notes { height: auto; margin: 1 0; }
#confirm-plan { height: auto; max-height: 14; }
#output { width: 100; height: 90%; }
CommandPicker, CommandFormScreen, ConfirmScreen, OutputScreen { align: center middle; }
"""
