"""Where the repository checkout is: the ONE resolver for the drivers (and, through it, ``locate``).

The drivers need the clone for three things that are not packaged: the per-target build assets
(``tools/``), the controller shell launchers (``scripts/local_*.sh``) and the docker build context
(the repository root).

One resolution order, the CLI's (``INODEFENCE_HOME`` -> the checkout of this code -> for the
drivers, the working directory): :func:`repo_root` (what ``locate`` uses) and
:func:`repository_root` (the drivers).

One invariant, as before the move (the drivers were ``scripts/*.py`` inside the repository): the
code that runs, the assets and launchers it uses and the engine revision it records
(``engine_provenance``) come from **one tree**. A driver's ``main`` checks it at run time with
:func:`require_repository` and refuses otherwise (exit 3). The CLI satisfies it by construction:
it runs drivers with the resolved clone's ``src`` first on ``PYTHONPATH``.

Nothing here runs at import: module constants derive from :func:`code_checkout` (pure path
arithmetic), so importing any driver works in any install (e.g. ``inodefence targets`` reading an
adapter's options); in a run that passes the check, that value is the resolved repository.

This module is a leaf: it imports only the standard library and :mod:`inodefence.user_config`
(itself stdlib-only), so ``locate`` can import it without a cycle.
"""

from __future__ import annotations

import os
from pathlib import Path

#: What marks a directory as the repository (a driver entry point and the build assets).
MARKER_DRIVER = Path("scripts/run_target.py")
MARKER_ASSETS = Path("tools")

#: ``src/inodefence/drivers/repo.py`` -> the checkout root, in a source / editable layout.
_CHECKOUT = Path(__file__).resolve().parents[3]

REPO_NOT_FOUND_HINT = (
    "InodeFence repository not found: the target drivers need a clone (tools/ and the controller "
    "launchers under scripts/ are not packaged). Run from the clone, install it with "
    "`pip install -e .`, or set INODEFENCE_HOME to the clone's root."
)


def is_repo(root: Path) -> bool:
    """``root`` holds the driver entry point and the build assets."""
    return (root / MARKER_DRIVER).is_file() and (root / MARKER_ASSETS).is_dir()


def configured_home() -> str | None:
    """``INODEFENCE_HOME`` from the user config file, or ``None`` (also for a broken file)."""
    from inodefence.user_config import UserConfigError, load_user_config

    try:
        setting = load_user_config().get("INODEFENCE_HOME")
    except UserConfigError:
        return None  # the CLI reports a broken config file up front; here: not configured
    return setting.value if setting is not None else None


def repo_root() -> Path | None:
    """Locate the repository explicitly, or ``None``; never a guess (the CLI's view).

    ``INODEFENCE_HOME`` wins when set (environment first, then the user config file). Otherwise,
    in an editable install this file is ``<repo>/src/inodefence/drivers/repo.py``, so its
    ``parents[3]`` is the repository root; a wheel install has no such layout and returns
    ``None``.
    """
    env = os.environ.get("INODEFENCE_HOME") or configured_home()
    if env:
        root = Path(env).expanduser()
        return root if is_repo(root) else None
    return _CHECKOUT if is_repo(_CHECKOUT) else None


def code_checkout() -> Path:
    """The tree that holds the running ``inodefence`` code (``<tree>/src/inodefence``); no I/O.

    Pure path arithmetic, so module constants derived from it (``REPO_ROOT``, launcher and
    ``tools/`` paths) cost nothing at import and never raise. It is the same value as the old
    ``scripts/`` drivers' ``Path(__file__).parents[1]``; :func:`require_repository` guarantees it
    equals the resolved repository whenever a driver actually runs.
    """
    return _CHECKOUT


def repository_root() -> Path:
    """The repository the drivers use: :func:`repo_root` (the CLI's order), then the cwd.

    Raises ``RuntimeError`` when none is a repository. On its own this may name a tree other than
    the running code's; drivers go through :func:`require_repository`, which refuses that.
    """
    found = repo_root()
    if found is not None:
        return found
    cwd = Path.cwd()
    if is_repo(cwd):
        return cwd
    raise RuntimeError(REPO_NOT_FOUND_HINT)


def require_repository() -> Path:
    """The resolved repository, checked to be the tree of the running code (fail-closed).

    The invariant of the drivers (as before the move, when they were ``scripts/*.py`` inside the
    repository): the code that runs, the assets and launchers it uses and the engine revision it
    records all come from one tree. ``RuntimeError`` when the repository is not found, or when the
    running ``inodefence`` package is not ``<repository>/src/inodefence``. The CLI path satisfies
    it by construction (it runs drivers with ``<root>/src`` first on ``PYTHONPATH``).
    """
    root = repository_root()
    running = Path(__file__).resolve().parents[1]
    if (root / "src" / "inodefence").resolve() != running:
        raise RuntimeError(
            f"the running code and the repository are different trees (code: {running}; "
            f"repository: {root}). Run it as `inodefence verify / explore / replay`, which runs "
            f"the drivers with that clone's own code, or with `PYTHONPATH={root / 'src'}`."
        )
    return root


def require_repository_or_exit(parser: object, status: int) -> Path:
    """:func:`require_repository` for a driver ``main``: on failure, ``parser.exit(status, ...)``.

    ``parser`` is the driver's ``argparse.ArgumentParser`` (duck-typed to keep this a leaf);
    called after argument parsing, so ``--help`` and usage errors behave as before.
    """
    try:
        return require_repository()
    except RuntimeError as error:
        prog = getattr(parser, "prog", "inodefence")
        parser.exit(status, f"{prog}: error: {error}\n")  # type: ignore[attr-defined]
        raise  # unreachable: ArgumentParser.exit raises SystemExit
