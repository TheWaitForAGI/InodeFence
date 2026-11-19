"""InodeFence local web dashboard (read-only).

A GET-only `FastAPI <https://fastapi.tiangolo.com/>`_ app over the shared read model
(:mod:`inodefence.app`). It shows only what the run folders already hold: it never starts, stops,
deletes or replays anything, never runs an extractor, and never serves a stored input's bytes
(paths and recorded SHA-256 only). Binding is ``127.0.0.1`` by default.

FastAPI and uvicorn are an **optional** dependency (``pip install 'inodefence[web]'``). Importing
this package never imports them; :func:`create_app` and :func:`run` raise :class:`WebUnavailable`
when they are missing, with the install hint.

Response JSON mirrors the :mod:`inodefence.app` dataclasses one for one -- an enum becomes its
value, a :class:`~pathlib.Path` a string, a tuple a list, ``None`` ``null`` -- and no value is
recomputed on the web side. The envelope carries ``schema = "inodefence-web-api-v1"``; that name
is a convenience for this dashboard, **not** a compatibility promise.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, never imports fastapi at runtime
    from fastapi import FastAPI

#: Envelope schema of every JSON response (a convenience, not a compatibility promise).
API_SCHEMA = "inodefence-web-api-v1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_INSTALL_HINT = (
    "the InodeFence web dashboard needs its optional dependencies; "
    "install them with: pip install 'inodefence[web]'"
)


class WebUnavailable(ImportError):
    """The optional web dependencies (``fastapi``, ``uvicorn``) are not installed."""


def _require_web() -> None:
    try:
        import fastapi  # noqa: F401  (presence check only)
    except ImportError as exc:  # pragma: no cover - exercised by the fastapi-missing test
        raise WebUnavailable(_INSTALL_HINT) from exc


def create_app(
    roots: Iterable[Path] | None = None,
    *,
    extra: Iterable[Path] = (),
    repo_root: Path | None = None,
) -> FastAPI:
    """Build the read-only dashboard app over ``roots`` (default :func:`app.runs.default_roots`).

    ``extra`` adds further output folders to scan; ``repo_root`` is the clone whose driver registry
    feeds ``/api/targets`` (``None`` when unknown -- that endpoint then reports it, and never
    guesses the working directory). Raises :class:`WebUnavailable` without the web dependencies.
    """
    _require_web()
    from ._app import build_app

    return build_app(roots=roots, extra=tuple(extra), repo_root=repo_root)


def run(
    roots: Iterable[Path] | None = None,
    *,
    extra: Iterable[Path] = (),
    repo_root: Path | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> int:
    """Serve the dashboard on ``host:port`` (``127.0.0.1`` by default); returns an exit code.

    A ``host`` other than ``127.0.0.1`` is honoured only because it was passed explicitly, and a
    one-line warning is printed to stderr: the dashboard is read-only, but anyone who can reach the
    address can view the run metadata. Raises :class:`WebUnavailable` without the web dependencies.
    """
    _require_web()
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - the web extra installs uvicorn with fastapi
        raise WebUnavailable(_INSTALL_HINT) from exc

    if host != DEFAULT_HOST:
        print(
            f"inodefence dashboard: binding to {host} instead of {DEFAULT_HOST}; "
            "the dashboard is read-only, but anyone who can reach this address can view it",
            file=sys.stderr,
        )
    app = create_app(roots, extra=extra, repo_root=repo_root)
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


__all__ = [
    "API_SCHEMA",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "WebUnavailable",
    "create_app",
    "run",
]
