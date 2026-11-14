"""Find the InodeFence repository and its out-of-package drivers, from one place.

Today only ``src/inodefence/`` is packaged; the drivers (``scripts/``) and the per-target build
assets (``tools/``) live in the repository, so the installed command must locate the repository to
run anything. Everything that needs a repository path or a driver goes through this module, so
moving the drivers into the package later (install-anywhere) is a change in one place, not a sweep
of hardcoded ``scripts/`` references across the CLI and option definitions.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

#: Drivers the CLI forwards to. The ONE place that knows the out-of-package ``scripts/`` layout.
VERIFY_DRIVER = "scripts/run_target.py"
EXPLORE_DRIVER = "scripts/run_target_explore.py"
REPLAY_DRIVER = "scripts/run_target_replay.py"

#: What marks a directory as the repository (a driver and the build assets must both be there).
_MARKER_DRIVER = Path(VERIFY_DRIVER)
_MARKER_ASSETS = Path("tools")

REPO_NOT_FOUND = (
    "InodeFence repository not found. Install from a clone with `pip install -e .`, or set "
    "INODEFENCE_HOME to the repository root (it must contain scripts/run_target.py and tools/)."
)


def _is_repo(root: Path) -> bool:
    return (root / _MARKER_DRIVER).is_file() and (root / _MARKER_ASSETS).is_dir()


def repo_root() -> Path | None:
    """Locate the repository explicitly, or ``None``; never a guess.

    ``INODEFENCE_HOME`` wins when set. Otherwise, in an editable install this file is
    ``<repo>/src/inodefence/locate.py``, so its grandparent's parent is the repository root; a
    wheel install has no such layout and returns ``None`` (the drivers are not bundled there).
    """
    env = os.environ.get("INODEFENCE_HOME")
    if env:
        root = Path(env).expanduser()
        return root if _is_repo(root) else None
    candidate = Path(__file__).resolve().parents[2]
    return candidate if _is_repo(candidate) else None


def _driver_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root), env.get("PYTHONPATH", "")])
    return env


def run_driver(root: Path, driver: str, argv: list[str]) -> int:
    """Run a repository driver (``scripts/…``) with the given argv and return its exit code.

    The driver runs in a subprocess with the repository on ``PYTHONPATH`` and as the working
    directory, so the driver's own ``REPO_ROOT`` and relative asset paths resolve. No shell: argv
    is passed as a list, so user values are never re-parsed as shell syntax.
    """
    completed = subprocess.run(
        [sys.executable, str(root / driver), *argv], cwd=root, env=_driver_env(root), check=False
    )
    return completed.returncode


def _registry_and_adapters(root: Path) -> tuple[dict[str, str], Any]:
    for path in (str(root), str(root / "src")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from scripts import run_target

    return dict(run_target.TARGETS), run_target


def target_support(root: Path) -> dict[str, dict[str, Any]]:
    """What each registered target supports, read from the drivers (the single source of truth).

    Exploration support is read from the adapter's ``explore`` hook, so it updates on its own as a
    target's owner fills the hook in; a target with no hook reports why.
    """
    targets, run_target = _registry_and_adapters(root)
    support: dict[str, dict[str, Any]] = {}
    for name in sorted(targets):
        adapter = run_target.load_adapter(name)
        explores = getattr(adapter, "explore", None) is not None
        options = [
            {
                "name": opt.name,
                "description": opt.description,
                "required": opt.required,
                "choices": list(opt.choices) if opt.choices else None,
                "single": opt.single,
            }
            for opt in getattr(adapter, "options", ())
        ]
        support[name] = {
            "regression": True,
            "auto_prepare": True,
            "explore": explores,
            "explore_reason": None if explores else "no exploration hook for this target yet",
            "options": options,
        }
    return support
