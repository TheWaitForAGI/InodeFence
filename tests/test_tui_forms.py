"""The TUI's command forms are the CLI's argparse definitions, read, never re-stated."""

from __future__ import annotations

import argparse

import pytest

from inodefence.cli import build_parser
from inodefence.ui.tui import forms
from inodefence.ui.tui.forms import FieldKind

REGISTRY = {
    "node-tar": {"options": []},
    "python-tarfile": {
        "options": [
            {
                "name": "extraction-filter",
                "description": "tarfile extraction filter",
                "required": True,
                "choices": ["fully_trusted", "data"],
                "single": True,
            }
        ]
    },
}


def _sub(name: str) -> argparse.ArgumentParser:
    return forms._subparsers(build_parser())[name]


def test_every_cli_command_but_the_screens_themselves_has_a_form() -> None:
    commands = set(forms._subparsers(build_parser()))
    assert set(forms.command_forms()) == commands - forms.NOT_OFFERED
    assert forms.NOT_OFFERED <= commands  # the two left out still exist in the CLI


@pytest.mark.parametrize("name", sorted(set(forms.command_forms())))
def test_a_form_has_exactly_the_parsers_options(name: str) -> None:
    form = forms.command_forms()[name]
    parser_options = {
        (a.dest, tuple(a.option_strings))
        for a in _sub(name)._actions
        if not isinstance(a, argparse._HelpAction)
    }
    assert {(f.dest, f.flags) for f in form.fields} == parser_options


def test_an_option_added_to_the_cli_appears_in_the_form() -> None:
    parser = build_parser()
    forms._subparsers(parser)["explore"].add_argument("--brand-new", choices=["a", "b"])
    (field,) = [f for f in forms.command_forms(parser)["explore"].fields if f.dest == "brand_new"]
    assert field.flags == ("--brand-new",) and field.choices == ("a", "b")


def test_kinds_defaults_choices_and_groups_come_from_the_parser() -> None:
    fields = {f.dest: f for f in forms.command_forms()["explore"].fields}
    assert fields["version"].required and fields["version"].kind is FieldKind.VALUE
    assert fields["budget"].default == 20 and fields["seed"].default == 123
    assert fields["auto_prepare"].kind is FieldKind.FLAG
    assert fields["profile"].choices is not None and "strict" in fields["profile"].choices
    assert fields["quiet"].exclusive_group is not None
    assert fields["quiet"].exclusive_group == fields["verbose"].exclusive_group
    verify = {f.dest: f for f in forms.command_forms()["verify"].fields}
    assert verify["version"].kind is FieldKind.REPEAT
    replay = {f.dest: f for f in forms.command_forms()["replay"].fields}
    assert replay["case_dir"].kind is FieldKind.POSITIONAL and replay["case_dir"].required


def test_docker_commands_are_the_three_that_run_an_extractor() -> None:
    every = forms.command_forms()
    assert {n for n, f in every.items() if f.starts_docker} == {"verify", "explore", "replay"}
    assert {n for n, f in every.items() if f.has_dry_run} == {"verify", "explore", "replay"}


def test_registry_options_are_added_only_where_the_parser_lacks_them() -> None:
    every = forms.command_forms(registry=REGISTRY)
    explore = every["explore"]
    (extra,) = [f for f in explore.fields if f.target == "python-tarfile"]
    assert extra.flag == "--extraction-filter" and extra.kind is FieldKind.VALUE and extra.required
    assert extra not in explore.visible_fields("node-tar")
    assert extra in explore.visible_fields("python-tarfile")
    # verify's parser has --extraction-filter already: no second field from the registry
    assert [f.flag for f in every["verify"].fields].count("--extraction-filter") == 1


def test_the_command_line_is_what_a_person_would_type_and_parses_back() -> None:
    form = forms.command_forms(registry=REGISTRY)["explore"]
    values = {"target": "python-tarfile", "version": "3.12.16", "budget": 20, "seed": 7,
              "auto_prepare": True, "extraction_filter": "data", "dry_run": False}  # fmt: skip
    argv = forms.command_line(form, values, "python-tarfile")
    assert argv == ["inodefence", "explore", "--target", "python-tarfile", "--version", "3.12.16",
                    "--seed", "7", "--auto-prepare", "--extraction-filter", "data"]  # fmt: skip
    args, extra = build_parser().parse_known_args(argv[1:])
    assert (args.target, args.version, args.seed, args.auto_prepare) == (
        "python-tarfile", "3.12.16", 7, True,
    )  # fmt: skip
    assert args.budget == 20 and extra == ["--extraction-filter", "data"]  # forwarded as typed


def test_positionals_and_repeats() -> None:
    every = forms.command_forms()
    assert forms.command_line(every["replay"], {"case_dir": "/x/run-000001", "rounds": 5}) == [
        "inodefence", "replay", "/x/run-000001", "--rounds", "5",
    ]  # fmt: skip
    verify = forms.command_line(every["verify"], {"version": ["7.5.2", "7.5.3"]})
    assert verify == ["inodefence", "verify", "--version", "7.5.2", "--version", "7.5.3"]
    assert forms.command_line(every["compare"], {"a": "A.json", "b": "B.json"})[2:] == [
        "A.json", "B.json",
    ]  # fmt: skip


def test_only_an_empty_required_field_is_checked_here() -> None:
    form = forms.command_forms(registry=REGISTRY)["explore"]
    assert forms.missing_required(form, {}, "node-tar") == ["--version"]
    missing = forms.missing_required(form, {"version": "3.12.16"}, "python-tarfile")
    assert missing == ["--extraction-filter"]
    assert forms.missing_required(form, {"version": "latest", "budget": -5}, "node-tar") == []


def test_a_default_typed_as_text_is_not_written() -> None:
    form = forms.command_forms()["explore"]
    argv = forms.command_line(form, {"version": "latest", "budget": "20", "seed": "123"})
    assert argv == ["inodefence", "explore", "--version", "latest"]
