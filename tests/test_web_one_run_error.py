"""One run's error stays with that run: every /api route answers 200, keeps the other runs, and
marks the failing one ``read_state: unreadable`` with the reason (QA N1: a result.json with a
wrongly shaped section made /api/runs and /api/findings answer 500 and every run disappeared).

The app layer no longer raises for such files; this pins the web's own guard, which also covers
the serialisation step. Requires the ``web`` extra.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests import app_synthetic as syn  # noqa: E402

from inodefence.app import runs as runs_app  # noqa: E402
from inodefence.ui import web  # noqa: E402
from inodefence.ui.web import _app  # noqa: E402

BROKEN = "synthetic-broken-cell"


@pytest.fixture
def two_runs(tmp_path: Path) -> Path:
    root = tmp_path / "out"
    good = syn.explore_out(root / "good")
    rid = syn.run_id()
    res = syn.result(cases=[syn.case("step-1", False), syn.case("step-2", True)], saved=["step-2"])
    syn.write_result(good / "target-explore" / f"{rid}-result", res)
    cases = [syn.case("toplevel_hardlink", True, termination=None)]
    fixture = syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION, cases=cases)
    syn.write_result(root / "verify" / BROKEN, fixture)
    return root


def _break(monkeypatch: pytest.MonkeyPatch, where: str) -> None:
    """Make reading (or serialising) the BROKEN run alone raise."""
    if where == "read":
        real = runs_app.read_run

        def read_run(ref, *args, **kwargs):  # type: ignore[no-untyped-def]
            if ref.run_id == BROKEN:
                raise RuntimeError("synthetic read failure")
            return real(ref, *args, **kwargs)

        monkeypatch.setattr(runs_app, "read_run", read_run)
    else:
        real_jsonable = _app.to_jsonable

        def to_jsonable(value):  # type: ignore[no-untyped-def]
            ref = getattr(value, "ref", None)
            if (
                getattr(ref, "run_id", None) == BROKEN
                or getattr(value, "case_id", None) == "toplevel_hardlink"
                or BROKEN in str(getattr(value, "path", ""))  # an artifact entry of that run
            ):
                raise ValueError("synthetic serialisation failure")
            return real_jsonable(value)

        monkeypatch.setattr(_app, "to_jsonable", to_jsonable)


@pytest.mark.parametrize("where", ["read", "serialise"])
def test_one_failing_run_never_takes_the_lists_down(
    two_runs: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    _break(monkeypatch, where)
    client = TestClient(web.create_app(roots=[two_runs]))

    runs = client.get("/api/runs")
    assert runs.status_code == 200
    by_id = {r["run_id"]: r for r in runs.json()["runs"]}
    good = next(r for name, r in by_id.items() if name != BROKEN)
    assert good["status"] is not None and good["status"]["candidates"] == 1
    if where == "read":  # the status itself could not be built
        assert by_id[BROKEN]["read_state"] == "unreadable"
        assert "synthetic read failure" in by_id[BROKEN]["error"]
        assert by_id[BROKEN]["status"] is None

    findings = client.get("/api/findings")
    assert findings.status_code == 200
    body = findings.json()
    assert [f["case"]["case_id"] for f in body["findings"]] == ["step-2"]  # the good run's
    assert body["fixture_violations"] == []  # the broken run adds nothing half-way
    (bad,) = body["unreadable"]
    assert bad["read_state"] == "unreadable" and "synthetic" in bad["error"]

    assert client.get("/api/replays").status_code == 200

    broken_id = by_id[BROKEN]["id"]
    detail = client.get(f"/api/runs/{broken_id}")
    assert detail.status_code == 200 and detail.json()["read_state"] == "unreadable"
    assert detail.json()["snapshot"] is None
    artifacts = client.get(f"/api/artifacts/{broken_id}")
    assert artifacts.status_code == 200 and artifacts.json()["read_state"] == "unreadable"
    assert client.get(f"/api/runs/{good['id']}").json()["read_state"] == "ok"


def test_without_failures_every_route_says_ok(two_runs: Path) -> None:
    client = TestClient(web.create_app(roots=[two_runs]))
    runs = client.get("/api/runs").json()["runs"]
    assert all(r["status"] is not None for r in runs)
    assert client.get("/api/findings").json()["unreadable"] == []
    assert client.get("/api/replays").json()["unreadable"] == []
    for run in runs:
        detail = client.get(f"/api/runs/{run['id']}").json()
        assert detail["read_state"] == "ok" and detail["status"] is not None
        assert client.get(f"/api/artifacts/{run['id']}").json()["read_state"] == "ok"
