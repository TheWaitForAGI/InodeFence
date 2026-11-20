"""Verify fixture-violations, verify-cell terminations, and launcher-only runs (QA F2/D2/D3).

All synthetic (``tests.app_synthetic``); the read model's new fields come from product/ui-app:
- a ``fixture-regression`` result's violations are known fixtures, not exploration candidates;
- a verify cell records no termination counts (every key None);
- a run seen only through its launcher log has no numbers and an estimated activity.
"""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests import app_synthetic as syn  # noqa: E402

from inodefence.app import runs as runs_app  # noqa: E402
from inodefence.target_result import ResultMode  # noqa: E402
from inodefence.ui import web  # noqa: E402


def _launcher_log(out, stamp="20261120T021743Z"):
    log = out / runs_app.RUNTIME_DIR / f"explore-launcher-{stamp}-4242.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("==> [preflight]\n==> [python-tarfile-effect-campaign]\n", encoding="utf-8")
    return log


def test_fixture_violations_are_counted_and_listed_apart_from_candidates(tmp_path):
    out = syn.explore_out(tmp_path)
    rid = syn.run_id()
    # a fixture-regression result: its violations are known fixtures, not candidates (by its mode)
    res = syn.result(
        mode=ResultMode.FIXTURE_REGRESSION,
        cases=[syn.case("toplevel_hardlink", True), syn.case("nested_hardlink", True)],
    )
    syn.write_result(out / "target-explore" / f"{rid}-result", res)

    client = TestClient(web.create_app(roots=[out]))
    run = next(r for r in client.get("/api/runs").json()["runs"] if r["status"])
    st = run["status"]
    assert st["fixture_violations"] == 2  # counted
    assert st["candidates"] == 0 and st["candidates_needs_repro"] == 0  # NOT candidates

    data = client.get("/api/findings").json()
    assert data["findings"] == []  # a fixture violation is never a candidate finding
    assert len(data["fixture_violations"]) == 2
    assert {x["case"]["case_id"] for x in data["fixture_violations"]} == {
        "toplevel_hardlink",
        "nested_hardlink",
    }
    # the rows carry the fixture marks, and still no file bytes
    for x in data["fixture_violations"]:
        assert x["case"]["known_fixture"] is True
        assert "content" not in x["case"] and "bytes" not in x["case"]


def test_verify_cell_terminations_are_unknown_not_zero(tmp_path):
    out = syn.explore_out(tmp_path)
    rid = syn.run_id()
    res = syn.result(
        # a verify cell records no termination counts (termination=None per case) -> all keys None
        mode=ResultMode.FIXTURE_REGRESSION,
        cases=[syn.case("toplevel_hardlink", True, termination=None)],
    )
    syn.write_result(out / "target-explore" / f"{rid}-result", res)
    client = TestClient(web.create_app(roots=[out]))
    st = next(r for r in client.get("/api/runs").json()["runs"] if r["status"])["status"]
    # D2: all four keys present, each None (the UI shows "?" per value, never 0 / dropped)
    assert set(st["terminations"]) == {"success", "rejected", "failed", "timed_out"}
    assert all(v is None for v in st["terminations"].values())


def test_launcher_only_run_is_active_without_numbers(tmp_path):
    out = tmp_path / "pt-out"
    _launcher_log(out)  # just written -> within the quiet limit
    client = TestClient(web.create_app(roots=[out]))
    run = next(
        r for r in client.get("/api/runs").json()["runs"] if r["status"] and r["status"]["launcher"]
    )
    st = run["status"]
    assert st["launcher"]["activity"] == "active"
    assert st["launcher"]["estimated"] is True
    assert st["runs"] is None and st["budget"] is None  # no fabricated progress
    assert st["candidates"] == 0 and st["fixture_violations"] == 0
    # the opaque id derives from RunRef.key ("explore:<root>:"), so the detail resolves
    assert client.get(f"/api/runs/{run['id']}").status_code == 200


def test_launcher_only_run_gone_quiet_is_no_activity(tmp_path):
    out = tmp_path / "pt-out"
    log = _launcher_log(out)
    old = time.time() - (runs_app.LAUNCHER_QUIET_MAX_SECONDS + 600)
    os.utime(log, (old, old))  # quiet longer than any live launcher phase
    client = TestClient(web.create_app(roots=[out]))
    run = next(
        r for r in client.get("/api/runs").json()["runs"] if r["status"] and r["status"]["launcher"]
    )
    assert run["status"]["launcher"]["activity"] == "no_activity"
