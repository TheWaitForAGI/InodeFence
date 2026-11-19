"""The default install has no Rich: every command and screen still works, on its plain path.

Two guards:

* AST rule: no module under ``inodefence/ui`` imports ``rich``/``textual``/``fastapi`` at module
  level, except the Rich renderable builders listed in ``RICH_ONLY``; those are imported only
  by ``ui/console.py`` *after* it has chosen Rich (never at its module level).
* Behaviour with Rich blocked (``sys.modules['rich'] = None``, and the Rich-only modules dropped
  from the import cache so a stray import really fails): each command below exits as usual and
  prints its plain screen, even when stdout claims to be an interactive terminal.

Add a line here for every new command or screen.
"""

from __future__ import annotations

import ast
import io
import json
import sys
from pathlib import Path

import pytest
from tests import app_synthetic as syn

from inodefence import cli
from inodefence.app import doctor as doctor_app
from inodefence.app import targets as targets_app
from inodefence.ui import console

UI = Path(__file__).resolve().parents[1] / "src" / "inodefence" / "ui"
OPTIONAL = ("rich", "textual", "fastapi", "uvicorn")
#: Modules that build Rich renderables and so import Rich at module level. Only
#: ``ui/console.py`` imports them, inside a method, once Rich is in use.
RICH_ONLY = {"components.py", "results.py"}
FIXTURE = Path(__file__).parent / "fixtures" / "result-contract-v1" / "fixture-regression.json"


def _module_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:  # module level only: function bodies are lazy
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
            if node.module == "inodefence.ui":
                names |= {f"inodefence.ui.{alias.name}" for alias in node.names}
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("inodefence.ui.")
        ):
            names.add(node.module)
    return names


def test_no_ui_module_imports_an_optional_package_at_module_level() -> None:
    offenders = {}
    for path in sorted(UI.rglob("*.py")):
        rel = path.relative_to(UI).as_posix()
        if rel in RICH_ONLY:
            continue
        found = _module_level_imports(path) & set(OPTIONAL)
        if found:
            offenders[rel] = sorted(found)
    assert offenders == {}, "import these lazily, or add the module to RICH_ONLY with a reason"


def test_rich_only_modules_are_imported_only_lazily() -> None:
    for path in sorted(UI.rglob("*.py")):
        rel = path.relative_to(UI).as_posix()
        reached = {
            name.rsplit(".", 1)[-1] + ".py"
            for name in _module_level_imports(path)
            if name.startswith("inodefence.ui.")
        }
        if rel not in RICH_ONLY:
            assert not reached & RICH_ONLY, f"{rel} imports a Rich-only module at module level"
    cli_imports = _module_level_imports(UI.parent / "cli.py")
    assert not {n for n in cli_imports if n.startswith("inodefence.ui.")} - {"inodefence.ui"}


@pytest.fixture
def no_rich(monkeypatch):
    """Rich cannot be imported; stdout says it is an interactive terminal (the hardest case)."""
    for name in list(sys.modules):
        if name in OPTIONAL or name.split(".")[0] in OPTIONAL:
            monkeypatch.setitem(sys.modules, name, None)
    for name in OPTIONAL:
        monkeypatch.setitem(sys.modules, name, None)
    for name in ("inodefence.ui.components", "inodefence.ui.results"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(console, "interactive", lambda stream, environ=None: True)
    assert console.rich_module() is None


def _cell(root: Path, name: str, data: dict) -> Path:
    cell = root / name
    (cell / "inputs").mkdir(parents=True)
    for item in data["repro_inputs"]:
        (cell / item["tar_path"]).write_bytes(b"x")
    (cell / "result.json").write_text(json.dumps(data), encoding="utf-8")
    return cell / "result.json"


def test_doctor_screen(no_rich, capsys) -> None:
    report = doctor_app.Report((doctor_app.Item("Python 3.12", "OK", "3.12.3"),))
    console.Console(version="0.2.0").doctor(report)
    out = capsys.readouterr().out
    assert "Python 3.12" in out and "no check failed" in out  # plain renderer (colour on a tty)


def test_targets_screen(no_rich, capsys) -> None:
    root = Path(__file__).resolve().parents[1]
    rows = targets_app.table_rows(targets_app.load(root))
    console.Console(version="0.2.0").targets(rows, targets_app.TABLE_HEADER, targets_app.TABLE_NOTE)
    out = capsys.readouterr().out
    assert "node-tar" in out and "\x1b" not in out


def test_compare(no_rich, capsys, tmp_path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    a = _cell(tmp_path, "a", data)
    assert cli.main(["compare", str(a), str(a)]) == 0
    out = capsys.readouterr().out
    assert "verdict: A FAIL  B FAIL" in out and "no recorded SHA-256 on either side" in out


def test_verify_after_screen(no_rich, monkeypatch, capsys, tmp_path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def driver(driver: str, argv: list[str], command: str) -> int:
        print("TARGET-RUN FAIL")
        _cell(tmp_path, "node-tar-7.5.2", data)
        return 1

    monkeypatch.setattr(cli, "_forward", driver)
    monkeypatch.setattr(cli, "_resolve_out", lambda args, name: tmp_path)
    assert cli.main(["verify", "--version", "7.5.2"]) == 1
    assert capsys.readouterr().out == "TARGET-RUN FAIL\n"


def test_replay_after_screen(no_rich, monkeypatch, capsys, tmp_path) -> None:
    case_dir = tmp_path / "violations" / "run-000002"
    case_dir.mkdir(parents=True)

    def driver(driver: str, argv: list[str], command: str) -> int:
        print("REPLAY done")
        syn.replay(case_dir, {"c0": False, "c1": True, "c2": False, "fingerprints": []},
                   [syn.judged_round(True)])  # fmt: skip
        return 0

    monkeypatch.setattr(cli, "_forward", driver)
    assert cli.main(["replay", str(case_dir)]) == 0
    assert capsys.readouterr().out == "REPLAY done\n"


def test_summary(no_rich, capsys) -> None:
    assert cli.main(["summary", str(FIXTURE), "--no-verify-inputs"]) == 0
    assert capsys.readouterr().out.startswith("#")


def test_status(no_rich, capsys, tmp_path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _cell(tmp_path, "node-tar-7.5.2", data)
    assert cli.main(["status", str(tmp_path)]) == 0
    assert "\x1b" not in capsys.readouterr().out


def test_explore_progress_display(no_rich) -> None:
    from inodefence.drivers import progress

    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    display = progress.select_display(Tty(), {"TERM": "xterm"})
    assert isinstance(display, progress.Display)
