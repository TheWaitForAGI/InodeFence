"""No screen says more than the evidence: every string the TUI, the console output, the web server
and the read model can show is checked for a positive "confirmed" and for "vulnerability" (QA:
the check existed for the web's static files only, so a TUI help line could say it unnoticed).

"not confirmed" is the qualifier every oracle flag carries (W4) and stays allowed. Docstrings and
comments are not screen text and are not checked; the web's static files have their own check
(``tests/test_web_static.py``).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import inodefence

SRC = Path(inodefence.__file__).resolve().parent
#: Every module whose strings can reach a screen: the three interfaces, their read model and the
#: command line itself.
SCREENS = sorted([*(SRC / "ui").rglob("*.py"), *(SRC / "app").glob("*.py"), SRC / "cli.py"])
POSITIVE_CONFIRMED = re.compile(r"(?<!not[ _])confirmed", re.IGNORECASE)
FORBIDDEN = (POSITIVE_CONFIRMED, re.compile(r"vulnerab", re.IGNORECASE), re.compile("취약점"))


def screen_strings(path: Path) -> list[tuple[int, str]]:
    """``(line, text)`` of every string literal in ``path`` except docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docstrings
    ]  # fmt: skip


@pytest.mark.parametrize("path", SCREENS, ids=lambda p: str(p.relative_to(SRC)))
def test_no_screen_string_overclaims(path: Path) -> None:
    bad = [
        f"{path.relative_to(SRC)}:{line}: {text!r}"
        for line, text in screen_strings(path)
        if any(pattern.search(text) for pattern in FORBIDDEN)
    ]
    assert bad == []


def test_the_check_catches_what_it_should(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(
        '"""a docstring may say confirmed vulnerability"""\n'
        'HELP = ("x", "confirmed vulnerability")\n'
        'LATER = "not yet confirmed, then confirmed"\n'
        'OK = "oracle flags · not confirmed"\n'
        'NAME = "NOT_CONFIRMED"\n',
        encoding="utf-8",
    )
    flagged = [text for _, text in screen_strings(probe) if any(p.search(text) for p in FORBIDDEN)]
    assert sorted(flagged) == ["confirmed vulnerability", "not yet confirmed, then confirmed"]
    assert len(SCREENS) > 20  # the scan reaches the TUI, console, web and app modules
    assert {p.parent.name for p in SCREENS} >= {"tui", "web", "app", "ui", "inodefence"}
