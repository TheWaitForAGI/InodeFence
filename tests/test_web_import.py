"""The web package imports without the optional web dependencies; it asks to install them.

These tests do NOT import fastapi, so they run even where the ``web`` extra is absent. The
"does not import fastapi" check runs in a fresh interpreter so it never depends on what another
test in the same session already imported.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import inodefence.ui.web as web


def test_public_api_without_optional_deps():
    assert hasattr(web, "create_app")
    assert hasattr(web, "run")
    assert issubclass(web.WebUnavailable, ImportError)
    assert web.DEFAULT_HOST == "127.0.0.1"


def test_importing_package_does_not_import_fastapi():
    src = str(Path(__file__).resolve().parents[1] / "src")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([src, os.environ.get("PYTHONPATH", "")])}
    code = (
        "import sys\n"
        "import inodefence.ui.web as web\n"
        "assert 'fastapi' not in sys.modules, 'fastapi was imported by the package'\n"
        "assert 'inodefence.ui.web._app' not in sys.modules, '_app was imported by the package'\n"
        "assert hasattr(web, 'create_app') and hasattr(web, 'run')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr


def test_create_app_without_fastapi_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastapi", None)  # make `import fastapi` fail
    with pytest.raises(web.WebUnavailable):
        web.create_app()


def test_run_without_fastapi_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastapi", None)
    with pytest.raises(web.WebUnavailable):
        web.run()
