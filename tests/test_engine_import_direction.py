"""Architecture direction (AGENTS.md "아키텍처 경계"): the engine never imports the command layer.

The command layer is ``inodefence.cli``, ``inodefence.locate``, the product drivers
(``inodefence.drivers``) and the interfaces' shared layers (``inodefence.app``, ``inodefence.ui``).
It sits above the engine (seed generator, mutator, builder, target adapters, observer, oracle,
feedback, the campaign loops and everything else under ``src/inodefence``) and may import it;
the engine importing the command layer would let a display, a CLI default or a driver choice reach
into a run. Checked on the source (AST), absolute and relative imports alike.

Command-layer modules (not checked here): ``cli.py``, ``locate.py``, ``user_config.py`` (the user's
settings file, read by the command only), ``__main__.py`` and the ``app``, ``ui`` and ``drivers``
packages. At the time this test was added no engine module broke the rule (no known exception).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "inodefence"
COMMAND_MODULES = {"cli.py", "locate.py", "user_config.py", "__main__.py"}
COMMAND_PACKAGES = ("app", "ui", "drivers")
FORBIDDEN = (
    "inodefence.app",
    "inodefence.ui",
    "inodefence.cli",
    "inodefence.locate",
    "inodefence.drivers",
)


def _module_name(rel: Path) -> str:
    parts = ["inodefence", *rel.with_suffix("").parts]
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imported(source: str, module: str, is_package: bool) -> list[tuple[int, str]]:
    """Every module name ``source`` imports, relative imports resolved against ``module``."""
    package = module if is_package else module.rsplit(".", 1)[0]
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                stem = ".".join(base + ([node.module] if node.module else []))
            else:
                stem = node.module or ""
            found.append((node.lineno, stem))
            found += [(node.lineno, f"{stem}.{alias.name}") for alias in node.names]
    return found


def _violations(source: str, module: str, is_package: bool = False) -> list[str]:
    return [
        f"{module}:{line}: {name}"
        for line, name in _imported(source, module, is_package)
        if any(name == f or name.startswith(f + ".") for f in FORBIDDEN)
    ]


def _engine_files() -> list[Path]:
    files = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC)
        if rel.parts[0] in COMMAND_PACKAGES or (
            len(rel.parts) == 1 and rel.name in COMMAND_MODULES
        ):
            continue
        files.append(path)
    return files


def test_the_engine_never_imports_the_command_layer() -> None:
    offenders = []
    for path in _engine_files():
        rel = path.relative_to(SRC)
        offenders += _violations(
            path.read_text(encoding="utf-8"), _module_name(rel), rel.name == "__init__.py"
        )
    assert offenders == []


def test_the_engine_set_covers_the_engine() -> None:
    names = {path.relative_to(SRC).as_posix() for path in _engine_files()}
    for expected in (
        "effect_campaign.py",
        "live_effect.py",
        "oracle/__init__.py",
        "mutator/__init__.py",
        "feedback/__init__.py",
        "execution/container.py",
        "targets/node_tar_effect.py",
    ):
        assert expected in names, expected
    assert not any(name.startswith(("app/", "ui/", "drivers/")) for name in names)


@pytest.mark.parametrize(
    "line",
    [
        "import inodefence.app.runs",
        "from inodefence.ui import console",
        "from inodefence import cli",
        "from inodefence.locate import repo_root",
        "import inodefence.drivers.run_target",
        "from ..drivers import progress",
        "from .. import locate",
    ],
)
def test_each_forbidden_form_is_caught(line: str) -> None:
    # The control: the check flags an engine module importing the command layer in any form.
    assert _violations(line + "\n", "inodefence.targets.node_tar_effect")


def test_an_engine_import_is_not_flagged() -> None:
    source = "from inodefence.oracle import judge\nfrom .identity_schedule import x\n"
    assert _violations(source, "inodefence.targets.node_tar_effect") == []
