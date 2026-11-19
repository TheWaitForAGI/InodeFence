"""The GET-only API over synthetic run folders: responses, read-only guarantees, host, health.

Everything is built from ``tests.app_synthetic`` (the word ``synthetic`` is in every folder); no
extractor runs. Requires the ``web`` extra.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests import app_synthetic as syn  # noqa: E402

from inodefence.app import doctor as doctor_app  # noqa: E402
from inodefence.ui import web  # noqa: E402
from inodefence.ui.web import _app  # noqa: E402


@pytest.fixture
def run_out(tmp_path):
    out = syn.explore_out(tmp_path)
    rid = syn.run_id()
    res = syn.result(
        cases=[syn.case("step-1", False), syn.case("step-2", True)],
        saved=["step-2"],
    )
    syn.write_result(out / "target-explore" / f"{rid}-result", res)
    return out


@pytest.fixture
def client(run_out):
    return TestClient(web.create_app(roots=[run_out]))


def test_runs_lists_synthetic_run(client):
    data = client.get("/api/runs").json()
    assert data["schema"] == web.API_SCHEMA
    assert data["runs_total"] == 1
    run = data["runs"][0]
    assert run["id"]
    assert run["kind"] == "explore"
    assert run["target"] == "node-tar"
    # step-2 violated and was judged -> one candidate; unknown stays distinct from zero
    assert run["status"]["candidates"] == 1
    assert run["status"]["verdict"] in ("PASS", "FAIL")


def test_run_detail_and_unknown_id_is_404(client):
    ident = client.get("/api/runs").json()["runs"][0]["id"]
    detail = client.get(f"/api/runs/{ident}")
    assert detail.status_code == 200
    assert detail.json()["snapshot"]["ref"]["kind"] == "explore"
    assert client.get("/api/runs/deadbeefdeadbeef").status_code == 404
    assert client.get("/api/runs/not-a-real-id").status_code == 404


def test_write_methods_are_405(client):
    assert client.post("/api/runs").status_code == 405
    assert client.put("/api/health").status_code == 405
    assert client.delete("/api/findings").status_code == 405


def test_findings_are_candidates(client):
    data = client.get("/api/findings").json()
    assert data["runs_total"] == 1
    assert any(f["case"]["case_id"] == "step-2" for f in data["findings"])
    for finding in data["findings"]:
        assert finding["case"]["finding"] in ("candidate", "candidate_needs_repro_check")
        assert finding["run_id"]


def test_replays_empty_for_run_without_replay(client):
    data = client.get("/api/replays").json()
    assert data["replays"] == []
    assert data["runs_total"] == 1


def test_artifacts_are_metadata_only(client):
    ident = client.get("/api/runs").json()["runs"][0]["id"]
    data = client.get(f"/api/artifacts/{ident}").json()
    assert data["kind"] == "explore"
    assert any(item["case_id"] == "step-2" for item in data["inputs"])
    assert "contents are never served" in data["note"]
    for item in data["inputs"]:
        assert set(item) == {"case_id", "tar_sha256", "path", "rechecked"}
        assert item["rechecked"] is False
    assert client.get("/api/artifacts/deadbeefdeadbeef").status_code == 404


def test_targets_unavailable_without_repo_root(client):
    data = client.get("/api/targets").json()
    assert data["state"] == "unavailable"
    assert data["targets"] == {}


def test_theme_css_served_from_shared_palette(client):
    res = client.get("/theme.css")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/css")
    assert "--if-accent" in res.text


def test_index_page_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "InodeFence dashboard" in res.text


def test_no_forbidden_labels_in_responses(client):
    for path in ("/api/runs", "/api/findings", "/api/replays"):
        low = client.get(path).text.lower()
        assert "confirmed" not in low
        assert "vulnerability" not in low


def test_health_starts_checking_then_reports(run_out, monkeypatch):
    report = doctor_app.Report(
        items=(doctor_app.Item(label="docker", status="OK", value="server 1.2"),)
    )
    monkeypatch.setattr(_app, "_default_health_check", lambda repo_root: report)
    client = TestClient(web.create_app(roots=[run_out]))
    data = client.get("/api/health").json()
    assert data["state"] in ("checking", "ok")
    deadline = time.time() + 5.0
    while data["state"] == "checking" and time.time() < deadline:
        time.sleep(0.05)
        data = client.get("/api/health").json()
    assert data["state"] == "ok"
    assert data["failed"] is False
    assert data["exit_code"] == 0
    assert data["age_seconds"] is not None


def test_run_defaults_to_loopback_and_warns_on_other_host(run_out, monkeypatch, capsys):
    pytest.importorskip("uvicorn")
    import uvicorn

    calls: dict[str, object] = {}

    def fake_run(app, host, port, log_level):  # noqa: ANN001 - test stub
        calls["host"] = host
        calls["port"] = port

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert web.run(roots=[run_out]) == 0
    assert calls["host"] == "127.0.0.1"
    assert web.run(roots=[run_out], host="0.0.0.0") == 0
    assert "127.0.0.1" in capsys.readouterr().err  # the non-default-host warning


def test_events_stream_is_event_stream(run_out):
    with TestClient(web.create_app(roots=[run_out])) as client:  # lifespan starts the follower
        with client.stream("GET", "/api/events") as res:
            assert res.status_code == 200
            assert res.headers["content-type"].startswith("text/event-stream")
