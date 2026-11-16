"""The CLI's view of the repository and the product drivers: thin glue, no resolution logic.

Where the checkout is comes from :mod:`inodefence.drivers.repo` (the one resolver, a leaf module);
the drivers themselves are the packaged modules under :mod:`inodefence.drivers`. This module only
names which driver module each command runs, runs it, and reads the target registry for
``inodefence targets``. Dependency direction: ``cli -> locate -> drivers -> engine``; nothing below
imports ``locate``.

Running a target still needs a repository clone: the per-target build assets (``tools/``) and the
controller shell launchers (``scripts/local_*.sh``) are not packaged.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from inodefence.drivers import repo as _repo

#: Driver modules the CLI forwards to, run as ``python -m <module>``.
VERIFY_DRIVER = "inodefence.drivers.run_target"
EXPLORE_DRIVER = "inodefence.drivers.run_target_explore"
REPLAY_DRIVER = "inodefence.drivers.run_target_replay"

#: What marks a directory as the repository (unchanged: ``scripts/run_target.py`` -- now a
#: compatibility alias of the packaged verify driver -- and ``tools/``).
_MARKER_DRIVER = _repo.MARKER_DRIVER
_MARKER_ASSETS = _repo.MARKER_ASSETS

REPO_NOT_FOUND = (
    "InodeFence repository not found. targets / verify / explore / replay need a clone of the "
    "repository (the image recipes under tools/ and the controller launchers under scripts/ are "
    "not in the installed package): install from the clone with `pip install -e .`, or set "
    "INODEFENCE_HOME (environment or the user config file) to the clone's root (it must contain "
    "scripts/run_target.py and tools/). --version, doctor, status and summary work without it."
)


def _is_repo(root: Path) -> bool:
    return _repo.is_repo(root)


def repo_root() -> Path | None:
    """Locate the repository explicitly, or ``None``; never a guess.

    ``INODEFENCE_HOME`` wins when set (environment first, then the user config file); otherwise an
    editable install finds its own checkout. See :func:`inodefence.drivers.repo.repo_root`.
    """
    return _repo.repo_root()


def _driver_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root), env.get("PYTHONPATH", "")])
    return env


#: Environment variable naming the user-facing command (``inodefence verify``) for the driver's
#: usage and error messages; unset when a driver is run directly.
PROG_ENV = "INODEFENCE_PROG"


def run_driver(root: Path, driver: str, argv: list[str], *, prog: str | None = None) -> int:
    """Run a driver module (``python -m <driver>``) with the given argv and return its exit code.

    ``prog`` is the command the user typed (e.g. ``inodefence verify``); the driver shows it in its
    usage and error messages instead of its own module name.

    The driver runs in a subprocess with the clone's ``src`` first on ``PYTHONPATH`` and the clone
    as the working directory, so the driver and the engine it composes are the clone's code (also
    when ``inodefence`` itself is installed from a wheel) and its relative asset paths resolve. No
    shell: argv is passed as a list, so user values are never re-parsed as shell syntax.
    """
    env = _driver_env(root)
    if prog:
        env[PROG_ENV] = prog
    completed = subprocess.run(
        [sys.executable, "-m", driver, *argv], cwd=root, env=env, check=False
    )
    return completed.returncode


def target_support(root: Path) -> dict[str, dict[str, Any]]:
    """What each registered target supports, read from the drivers (the single source of truth).

    Reads the packaged registry in-process (no ``sys.path`` change): the adapters are the installed
    package's own. ``root`` is the checkout the CLI found; the adapters resolve their asset paths
    from it through :mod:`inodefence.drivers.repo`. Exploration support is read from the adapter's
    ``explore`` hook, so it updates on its own as a target's owner fills the hook in; a target with
    no hook reports why.
    """
    del root  # the registry is packaged; the checkout matters only to the drivers' asset paths
    from inodefence.drivers import run_target

    support: dict[str, dict[str, Any]] = {}
    for name in sorted(run_target.TARGETS):
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
