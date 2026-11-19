"""The dashboard opens the repository's REAL stored result fixtures (not the synthetic helpers).

One fixture is a valid ``inodefence-target-result-v1`` result; the other is a foreign/old-schema
JSON the strict reader must refuse. Every endpoint has to stay 200 and the foreign one has to
degrade to a read-state, never crash -- the same way a real, missing-field result would.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from inodefence.ui import web  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def real_out(tmp_path):
    out = tmp_path / "verify-out"
    cell = out / "node-tar-7.5.2"
    cell.mkdir(parents=True)
    shutil.copy(FIXTURES / "result-contract-v1" / "campaign.json", cell / "result.json")
    foreign = out / "foreign-cell"
    foreign.mkdir()
    shutil.copy(FIXTURES / "g1-20261104" / "7.5.2-R-s9001.reduced.json", foreign / "result.json")
    return out


def test_dashboard_opens_real_result_fixtures(real_out):
    with TestClient(web.create_app(roots=[real_out])) as client:
        runs = client.get("/api/runs")
        assert runs.status_code == 200
        data = runs.json()
        assert data["runs_total"] >= 2
        for run in data["runs"]:
            assert client.get(f"/api/runs/{run['id']}").status_code == 200
            assert client.get(f"/api/artifacts/{run['id']}").status_code == 200
        for path in ("/", "/theme.css", "/api/findings", "/api/replays", "/api/targets"):
            assert client.get(path).status_code == 200
        # one real result read OK (with a verdict), one foreign result degraded -- neither crashed
        ok = [r for r in data["runs"] if r["status"] and r["status"]["read_state"] == "ok"]
        refused = [
            r for r in data["runs"] if r["status"] and r["status"]["read_state"] == "unreadable"
        ]
        assert ok, "the real inodefence-target-result-v1 fixture should read OK"
        assert refused, "the foreign-schema fixture should degrade to unreadable, not crash"
        assert ok[0]["status"]["verdict"] is not None
        # missing values on the degraded run are None (shown as "-"), never fabricated
        assert refused[0]["status"]["verdict"] is None
