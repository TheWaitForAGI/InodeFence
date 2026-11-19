"""The static files ship offline: no external URL, and no forbidden result label."""

from __future__ import annotations

import re
from pathlib import Path

import inodefence.ui.web as web

STATIC = Path(web.__file__).parent / "static"
FILES = ("index.html", "app.css", "app.js")

# http(s) URLs or protocol-relative (//host) references in a src/href/url(...)
_EXTERNAL = re.compile(
    r"https?://|src\s*=\s*[\"']//|href\s*=\s*[\"']//|url\(\s*[\"']?//", re.IGNORECASE
)


def _texts() -> dict[str, str]:
    return {name: (STATIC / name).read_text(encoding="utf-8") for name in FILES}


def test_static_files_present():
    for name in FILES:
        assert (STATIC / name).is_file(), name


def test_no_external_references():
    for name, text in _texts().items():
        match = _EXTERNAL.search(text)
        assert match is None, f"{name} has an external reference: {match.group(0) if match else ''}"


def test_no_forbidden_labels():
    for name, text in _texts().items():
        low = text.lower()
        assert "confirmed" not in low, name
        assert "vulnerability" not in low, name
        assert "취약점" not in text, name  # 취약점


def test_as_stored_label_is_present():
    # an UNVALIDATED result must be shown with a visible "as stored" mark, not just a tooltip
    assert "as stored" in (STATIC / "app.js").read_text(encoding="utf-8")


def test_no_unicode_escape_literals_in_html():
    # the HTML must use real characters / entities, not JS-style \\uXXXX escapes
    assert "\\u" not in (STATIC / "index.html").read_text(encoding="utf-8")
