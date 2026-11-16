"""Where the repository checkout is: the ONE module for both views of it (leaf module).

The drivers need the clone for three things that are not packaged: the per-target build assets
(``tools/``), the controller shell launchers (``scripts/local_*.sh``) and the docker build context
(the repository root). Two questions, two functions, the same meaning as before the move:

* **Which clone the CLI runs** -- :func:`repo_root`, used only by ``locate``: ``INODEFENCE_HOME``
  (environment, then the user config file), else the checkout this installed code belongs to;
  never the working directory. ``locate`` then runs the drivers with that clone's ``src`` first on
  ``PYTHONPATH``, so in the subprocess the driver code *is* that clone's.
* **The driver's own repository** -- :func:`require_repository`: always the checkout of the
  running code (:func:`code_checkout`), exactly like the old ``scripts/*.py`` drivers'
  ``Path(__file__).parents[1]``. ``INODEFENCE_HOME`` and the working directory are not
  consulted, so the code that runs, the assets and launchers it uses and the engine revision it
  records (``engine_provenance``) are one tree by definition. Driver code that is not inside a
  clone (an installed wheel run directly) is refused at run time.

Nothing here runs at import: module constants derive from :func:`code_checkout` (pure path
arithmetic), so importing any driver works in any install (e.g. ``inodefence targets`` reading an
adapter's options).

This module imports only the standard library and :mod:`inodefence.user_config` (itself
stdlib-only), so ``locate`` can import it without a cycle.
"""

from __future__ import annotations

import os
from pathlib import Path

#: What marks a directory as the repository (a driver entry point and the build assets).
MARKER_DRIVER = Path("scripts/run_target.py")
MARKER_ASSETS = Path("tools")

#: ``src/inodefence/drivers/repo.py`` -> the checkout root, in a source / editable layout.
_CHECKOUT = Path(__file__).resolve().parents[3]

#: The refusal for driver code run directly (``python -m inodefence.drivers.…``) from outside a
#: clone, e.g. from an installed wheel. ``{code}`` is the running driver code's folder. A driver
#: run directly uses only its own clone, so the advice must not be "set INODEFENCE_HOME" or "run
#: from the clone": neither is consulted here.
REPO_NOT_FOUND_HINT = (
    "InodeFence repository not found for this driver: its code at {code} is not inside a clone, "
    "and a driver run directly uses only its own clone's tools/ and scripts/ (INODEFENCE_HOME "
    "and the working directory are not consulted here; the build assets and controller "
    "launchers are not packaged). Run it as `inodefence verify / explore / replay`, which runs "
    "the drivers of the clone chosen by INODEFENCE_HOME or by an editable install "
    "(`pip install -e .` in the clone)."
)

#: Where a clone keeps the packaged drivers (absent in a clone from before they moved there).
DRIVERS_PACKAGE = Path("src/inodefence/drivers")

#: The refusal for a chosen clone with no packaged drivers to run -- damaged, or a clone older than
#: this ``inodefence`` (it still has the drivers under ``scripts/`` only). One wording, used by
#: ``locate`` before it starts a driver; ``{root}`` is the chosen clone.
OLD_LAYOUT_REFUSAL = (
    "the selected repository has no InodeFence code to run: {root} has no "
    f"{DRIVERS_PACKAGE.as_posix()}/ (damaged, or a clone older than this version of inodefence). "
    "Update that clone (`git pull`), or set INODEFENCE_HOME to a current clone."
)

#: The guidance when the driver code runs from a clone but that clone's ``experiments/`` (the
#: committed repro programs the fixture paths use) is not importable: the clone root is not on
#: ``sys.path``, e.g. an editable install run directly from another working directory.
REPOSITORY_CODE_NOT_ON_PATH = (
    "InodeFence repository code `{module}` is not importable: the driver runs from the clone at "
    "{root}, but that clone's root is not on the Python path. Run it as "
    "`inodefence verify / explore / replay`, or from the clone's root directory."
)

#: Exit status for :data:`REPOSITORY_CODE_NOT_ON_PATH` (a setup error, as for a missing clone).
REPOSITORY_CODE_EXIT = 3


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


def home_setting() -> tuple[str, str] | None:
    """``(value, where it was set)`` of ``INODEFENCE_HOME``, or ``None`` when it is not set.

    The same precedence as :func:`repo_root`: the environment first, then the user config file.
    """
    if os.environ.get("INODEFENCE_HOME"):
        return os.environ["INODEFENCE_HOME"], "environment"
    value = configured_home()
    return (value, "user config file") if value else None


def home_path(value: str) -> Path:
    """The clone an ``INODEFENCE_HOME`` value names, as an absolute path.

    Absolute because the CLI runs the driver with the clone as its working directory and the
    clone's ``src`` on ``PYTHONPATH``: a relative path would be re-read from inside the clone,
    miss its ``src`` and silently run whichever ``inodefence`` is installed instead. A relative
    value is taken against the working directory the command was started in.
    """
    return Path(value).expanduser().absolute()


def repo_root() -> Path | None:
    """Which clone the CLI runs (``locate`` only), or ``None``; never a guess.

    ``INODEFENCE_HOME`` wins when set (environment first, then the user config file); it is made
    absolute (:func:`home_path`). Otherwise, in an editable install this file is
    ``<repo>/src/inodefence/drivers/repo.py``, so its ``parents[3]`` is the repository root; a
    wheel install has no such layout and returns ``None``. The working directory is not consulted
    as a fallback (as in ``locate`` before the move).
    """
    setting = home_setting()
    if setting is not None:
        root = home_path(setting[0])
        return root if is_repo(root) else None
    return _CHECKOUT if is_repo(_CHECKOUT) else None


def code_checkout() -> Path:
    """The tree that holds the running ``inodefence`` code (``<tree>/src/inodefence``); no I/O.

    Pure path arithmetic, so module constants derived from it (``REPO_ROOT``, launcher and
    ``tools/`` paths) cost nothing at import and never raise. It is the same value as the old
    ``scripts/`` drivers' ``Path(__file__).parents[1]``.
    """
    return _CHECKOUT


def require_repository() -> Path:
    """The driver's own repository: :func:`code_checkout`, which must be a clone.

    ``RuntimeError`` when the running code is not inside a clone (an installed copy run
    directly), even if a clone exists elsewhere (``INODEFENCE_HOME``, the working directory):
    the drivers never read the assets, launchers or git revision of a tree other than their own.
    """
    if is_repo(_CHECKOUT):
        return _CHECKOUT
    raise RuntimeError(REPO_NOT_FOUND_HINT.format(code=Path(__file__).resolve().parent))


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
