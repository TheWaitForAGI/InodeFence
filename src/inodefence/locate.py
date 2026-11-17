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

import json
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


def repo_not_found_message() -> str:
    """Why :func:`repo_root` found no clone, for the user: :data:`REPO_NOT_FOUND`, or more exact.

    When ``INODEFENCE_HOME`` is set (environment or user config file) the generic advice "set
    INODEFENCE_HOME" is wrong -- it is set, to something that is not a clone -- so this says
    which value, where it came from and what that folder lacks.
    """
    setting = _repo.home_setting()
    if setting is None:
        return REPO_NOT_FOUND
    value, source = setting
    root = _repo.home_path(value)
    if not root.is_dir():
        lacks = "that folder does not exist"
    else:
        missing = [
            f"{marker.as_posix()}{'/' if marker == _MARKER_ASSETS else ''}"
            for marker, present in (
                (_MARKER_DRIVER, (root / _MARKER_DRIVER).is_file()),
                (_MARKER_ASSETS, (root / _MARKER_ASSETS).is_dir()),
            )
            if not present
        ]
        if not missing:  # it is a clone (called although repo_root() found it)
            return REPO_NOT_FOUND
        lacks = f"it has no {' and no '.join(missing)}"
    return (
        f"INODEFENCE_HOME ({source}) is {value!r} -> {root}, which is not an InodeFence clone: "
        f"{lacks}. targets / verify / explore / replay need one: set INODEFENCE_HOME to the "
        "clone's root (the folder with scripts/run_target.py and tools/), or unset it to use an "
        "editable install's own clone. --version, doctor, status and summary work without it."
    )


def _is_repo(root: Path) -> bool:
    return _repo.is_repo(root)


def repo_root() -> Path | None:
    """Locate the repository explicitly, or ``None``; never a guess.

    ``INODEFENCE_HOME`` wins when set (environment first, then the user config file); otherwise an
    editable install finds its own checkout. See :func:`inodefence.drivers.repo.repo_root`.
    """
    return _repo.repo_root()


class RepositoryCodeMissing(RuntimeError):
    """The chosen repository has no InodeFence code to run (damaged, or older than this CLI)."""


def check_repository_code(root: Path) -> None:
    """Refuse before a subprocess when ``root`` has no package to run (fail closed).

    A tree with the markers but without ``src/inodefence/__init__.py`` and
    ``src/inodefence/drivers`` would make ``python -m inodefence.drivers.…`` resolve to whatever
    ``inodefence`` is installed, i.e. silently run another tree than the one the user chose. Raises
    :class:`RepositoryCodeMissing`.
    """
    package = root / "src" / "inodefence"
    if not ((package / "__init__.py").is_file() and (package / "drivers").is_dir()):
        raise RepositoryCodeMissing(_repo.OLD_LAYOUT_REFUSAL.format(root=root))


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
    check_repository_code(root)
    env = _driver_env(root)
    if prog:
        env[PROG_ENV] = prog
    completed = subprocess.run(
        [sys.executable, "-m", driver, *argv], cwd=root, env=env, check=False
    )
    return completed.returncode


#: Flag of this module's own entry point that prints :func:`_read_registry` as JSON. Internal: only
#: :func:`target_support` runs it; it is not a user command and ``inodefence --help`` does not list
#: it.
_SUPPORT_FLAG = "--target-support-json"


def target_support(root: Path) -> dict[str, dict[str, Any]]:
    """What each registered target supports, read from the drivers (the single source of truth).

    The registry is read in a subprocess run exactly like a driver (``cwd`` = the clone, the
    clone's ``src`` and root first on ``PYTHONPATH``), not in this process: the adapters import the
    clone's fixture modules (``experiments/repro``), which are not packaged, and reading them here
    would mix this install's engine with the clone's files. So ``targets`` reports the same code
    ``verify`` / ``explore`` run. Raises :class:`RepositoryCodeMissing` when ``root`` has no code to
    run and ``RuntimeError`` when the registry cannot be read.
    """
    check_repository_code(root)
    completed = subprocess.run(
        [sys.executable, "-m", "inodefence.locate", _SUPPORT_FLAG],
        cwd=root,
        env=_driver_env(root),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        lines = [line for line in completed.stderr.splitlines() if line.strip()]
        raise RuntimeError(lines[-1] if lines else f"exit {completed.returncode}")
    return json.loads(completed.stdout)


def _read_registry() -> dict[str, dict[str, Any]]:
    """The registry as plain data (run inside the clone's environment by :func:`target_support`).

    Every field is read from the adapter, so it updates on its own as a target's owner fills a
    hook in: ``regression`` is always true (``run`` is a required hook), ``auto_prepare`` is true
    unless ``prepare`` is still the ``prepare_unsupported`` default, and ``explore`` / ``replay``
    are true when the hook is set. A target with no exploration hook reports why.
    """
    from inodefence.drivers import run_target

    support: dict[str, dict[str, Any]] = {}
    for name in sorted(run_target.TARGETS):
        adapter = run_target.load_adapter(name)
        explores = getattr(adapter, "explore", None) is not None
        prepares = getattr(adapter, "prepare", None) is not run_target.prepare_unsupported
        replays = getattr(adapter, "replay", None) is not None
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
            "auto_prepare": prepares,
            "explore": explores,
            "explore_reason": None if explores else "no exploration hook for this target yet",
            "replay": replays,
            "options": options,
        }
    return support


def _support_main(argv: list[str]) -> int:
    """Internal entry point (run by :func:`target_support` only): registry JSON on stdout.

    Refuses (exit 3) unless the running code belongs to the resolved repository tree -- the same
    invariant the drivers enforce -- so ``targets`` never reports another checkout's registry.
    """
    if argv != [_SUPPORT_FLAG]:
        print(f"internal: python -m inodefence.locate {_SUPPORT_FLAG}", file=sys.stderr)
        return 3
    try:
        _repo.require_repository()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 3
    json.dump(_read_registry(), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(_support_main(sys.argv[1:]))
