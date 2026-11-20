"""Command forms derived from the CLI's own argparse definitions (nothing is re-stated here).

:func:`command_forms` reads ``inodefence.cli.build_parser()`` and turns each sub-command into a
:class:`CommandForm`: its options with their kind, choices, defaults, ``required`` and help, as the
parser holds them. When the CLI gains an option it appears in the form; ``tests/test_tui_forms.py``
fails if the two ever differ. Target-specific options (e.g. python-tarfile's
``--extraction-filter`` for ``explore``) come from the target registry (``app.targets``) and are
added only where the sub-command's parser does not already have them; the CLI forwards them to the
driver as it does for a typed command.

Values are not validated here beyond "a required field is empty": the CLI checks them and its
refusal (exit 3 and the reason on stderr) is what the screen shows. :func:`command_line` builds the
exact argument list a person would type; it never adds an option the person did not set.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

#: Sub-commands the TUI does not offer: ``tui`` is this screen, ``dashboard`` starts a server.
NOT_OFFERED = frozenset({"tui", "dashboard"})
#: Sub-commands that start Docker (an extractor run or an image build): confirmed before starting.
STARTS_DOCKER = frozenset({"verify", "explore", "replay"})


class FieldKind(StrEnum):
    POSITIONAL = "positional"
    FLAG = "flag"  # store_true: on or off
    VALUE = "value"  # one value
    REPEAT = "repeat"  # action="append": zero or more values


@dataclass(frozen=True, slots=True)
class Field:
    """One option or positional argument of a sub-command, as the parser (or registry) holds it."""

    dest: str
    #: the option strings (``--budget``); empty for a positional argument
    flags: tuple[str, ...]
    kind: FieldKind
    help: str
    choices: tuple[str, ...] | None = None
    default: Any = None
    required: bool = False
    #: fields in the same mutually exclusive group share this id (``--quiet`` / ``--verbose``)
    exclusive_group: int | None = None
    #: from the target registry, shown only for that target
    target: str | None = None

    @property
    def flag(self) -> str | None:
        """The long option string used on the command line, or ``None`` for a positional."""
        if not self.flags:
            return None
        return next((f for f in self.flags if f.startswith("--")), self.flags[0])


@dataclass(frozen=True, slots=True)
class CommandForm:
    name: str
    help: str
    fields: tuple[Field, ...]

    @property
    def starts_docker(self) -> bool:
        return self.name in STARTS_DOCKER

    @property
    def has_dry_run(self) -> bool:
        return any(f.dest == "dry_run" for f in self.fields)

    def visible_fields(self, target: str | None) -> tuple[Field, ...]:
        """The fields to show for ``target`` (registry options only for their own target)."""
        return tuple(f for f in self.fields if f.target is None or f.target == target)


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:  # argparse has no public way to list sub-parsers
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _help_of(parser: argparse.ArgumentParser, name: str) -> str:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for choice in action._choices_actions:
                if choice.dest == name:
                    return choice.help or ""
    return ""


def _field(action: argparse.Action, groups: Mapping[int, int]) -> Field | None:
    if isinstance(action, argparse._HelpAction | argparse._VersionAction):
        return None
    if not action.option_strings:
        kind = FieldKind.POSITIONAL
    elif isinstance(action, argparse._StoreTrueAction):
        kind = FieldKind.FLAG
    elif isinstance(action, argparse._AppendAction):
        kind = FieldKind.REPEAT
    else:
        kind = FieldKind.VALUE
    choices = tuple(str(c) for c in action.choices) if action.choices else None
    required = (
        bool(action.required) or kind is FieldKind.POSITIONAL and action.nargs not in ("*", "?")
    )
    return Field(
        dest=action.dest,
        flags=tuple(action.option_strings),
        kind=kind,
        help=action.help or "",
        choices=choices,
        default=action.default,
        required=required,
        exclusive_group=groups.get(id(action)),
    )


def _registry_fields(name: str, parser: argparse.ArgumentParser, registry: Mapping[str, Any]):
    have = {flag for action in parser._actions for flag in action.option_strings}
    out = []
    for target, feats in registry.items():
        for option in feats.get("options") or ():
            flag = f"--{option['name']}"
            if flag in have:  # the parser has it already (verify's --extraction-filter)
                continue
            choices = option.get("choices")
            out.append(
                Field(
                    dest=option["name"].replace("-", "_"),
                    flags=(flag,),
                    kind=FieldKind.VALUE if option.get("single") else FieldKind.REPEAT,
                    help=option.get("description") or "",
                    choices=tuple(choices) if choices else None,
                    required=bool(option.get("required")),
                    target=target,
                )
            )
    return out


def command_forms(
    parser: argparse.ArgumentParser | None = None, registry: Mapping[str, Any] | None = None
) -> dict[str, CommandForm]:
    """Every offered sub-command's form, in the parser's order.

    ``registry`` (``app.targets.load``) adds target-specific options to ``verify`` and ``explore``;
    without it the forms hold the parser's options only.
    """
    if parser is None:
        from inodefence.cli import build_parser

        parser = build_parser()
    forms = {}
    for name, sub in _subparsers(parser).items():
        if name in NOT_OFFERED:
            continue
        groups = {
            id(action): index
            for index, group in enumerate(sub._mutually_exclusive_groups)
            for action in group._group_actions
        }
        fields = [f for action in sub._actions if (f := _field(action, groups)) is not None]
        if registry is not None and name in ("verify", "explore"):
            fields += _registry_fields(name, sub, registry)
        forms[name] = CommandForm(name=name, help=_help_of(parser, name), fields=tuple(fields))
    return forms


def missing_required(form: CommandForm, values: Mapping[str, Any], target: str | None) -> list[str]:
    """The required fields left empty (the only check made here; the CLI checks the rest)."""
    return [
        f.flag or f.dest
        for f in form.visible_fields(target)
        if f.required and values.get(f.dest) in (None, "", [], ())
    ]


def command_line(
    form: CommandForm, values: Mapping[str, Any], target: str | None = None
) -> list[str]:
    """``["inodefence", <command>, ...]`` exactly as a person would type it.

    Only fields set to something other than their default are written (positionals and required
    fields always), in the parser's order; a flag field is written when on; a repeat field once per
    value. Nothing is added that the person did not set.
    """
    argv = ["inodefence", form.name]
    positionals: list[str] = []
    for f in form.visible_fields(target):
        value = values.get(f.dest, f.default)
        if f.kind is FieldKind.POSITIONAL:
            if value not in (None, ""):
                positionals.append(str(value))
            continue
        flag = f.flag
        assert flag is not None
        if f.kind is FieldKind.FLAG:
            if value:
                argv.append(flag)
        elif f.kind is FieldKind.REPEAT:
            items: Sequence[Any] = value if isinstance(value, list | tuple) else [value]
            for item in items:
                if item not in (None, ""):
                    argv += [flag, str(item)]
        # a form's text box gives "20" for the default 20: unchanged is unchanged, typed or not
        elif value not in (None, "") and (f.required or str(value) != str(f.default)):
            argv += [flag, str(value)]
    return argv[:2] + positionals + argv[2:]  # positionals first, as the CLI's help shows them
