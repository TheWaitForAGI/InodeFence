"""Where the repository checkout is: the ONE resolver for the drivers (and, through it, ``locate``).

The drivers need the clone for three things that are not packaged: the per-target build assets
(``tools/``), the controller shell launchers (``scripts/local_*.sh``) and the docker build context
(the repository root). Every such path is computed from :func:`repository_root`.

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
    ``scripts/`` drivers' ``Path(__file__).parents[1]``.
    """
    return _CHECKOUT


def repository_root() -> Path:
    """The checkout a driver reads its assets from (the drivers' view).

    The checkout that holds this code comes first: that is what the drivers used before they
    moved into the package (``Path(__file__).parents[1]`` under ``scripts/``), so the engine
    revision (``engine_provenance``) and the assets stay those of the running code. Then the
    explicit repository (:func:`repo_root`), then the working directory (the CLI runs drivers
    with ``cwd`` = root). Raises ``RuntimeError`` when none is a repository.
    """
    if is_repo(_CHECKOUT):
        return _CHECKOUT
    explicit = repo_root()
    if explicit is not None:
        return explicit
    cwd = Path.cwd()
    if is_repo(cwd):
        return cwd
    raise RuntimeError(REPO_NOT_FOUND_HINT)
