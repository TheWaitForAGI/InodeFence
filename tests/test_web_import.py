"""The web package imports without the optional web dependencies; it asks to install them.

These tests do NOT import fastapi, so they run even where the ``web`` extra is absent.
"""

from __future__ import annotations

import sys

import pytest

import inodefence.ui.web as web


def test_public_api_without_optional_deps():
    assert hasattr(web, "create_app")
    assert hasattr(web, "run")
    assert issubclass(web.WebUnavailable, ImportError)
    assert web.DEFAULT_HOST == "127.0.0.1"


def test_importing_package_does_not_import_fastapi():
    # fastapi may be installed, but importing inodefence.ui.web must not pull in the heavy app
    # module; it is loaded only when create_app() is called.
    assert "inodefence.ui.web._app" not in sys.modules


def test_create_app_without_fastapi_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastapi", None)  # make `import fastapi` fail
    with pytest.raises(web.WebUnavailable):
        web.create_app()


def test_run_without_fastapi_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastapi", None)
    with pytest.raises(web.WebUnavailable):
        web.run()
