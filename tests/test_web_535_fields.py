"""The web is robust to #535's additions to the stored records.

#535 added ``fast_acceptance`` and a nested ``acceptance_scope`` (with a ``counted_seeds`` list)
to result.json, and an ``additive_detectors`` column to replay.json rounds. The read model keeps
unknown campaign keys in ``extras`` and :func:`inodefence.app.runs.read_replay` reads only the
round fields it knows, so the web has to serialize them and stay 200 -- it never renders arbitrary
extras into the fixed detail fields.

Two replay tests on purpose:
- :func:`test_web_reads_real_535_additive_detector_columns` writes a replay the real #535 writer
  accepts (its ``check_fields`` validates the column) and checks the web reads it;
- :func:`test_web_tolerates_unknown_replay_column` appends an unknown column after the writer and
  checks the web still stays 200 -- read-side tolerance of a shape the writer would reject.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests import app_synthetic as syn  # noqa: E402

from inodefence.ui import web  # noqa: E402


def _explore_with_result(tmp_path):
    out = syn.explore_out(tmp_path)
    rid = syn.run_id()
    res = syn.result(cases=[syn.case("step-1", True)], saved=["step-1"])
    folder = out / "target-explore" / f"{rid}-result"
    syn.write_result(folder, res)
    return out, folder


def test_web_tolerates_new_535_result_fields(tmp_path):
    out = syn.explore_out(tmp_path)
    rid = syn.run_id()
    res = syn.result(cases=[syn.case("step-1", False), syn.case("step-2", True)], saved=["step-2"])
    data = json.loads(res.dumps())
    scope = {
        "version": "7.5.2",
        "policy": "default",
        "budget": 2000,
        "counted_seeds": [58001, 58002, 58003],
        "rule": "v3",
        "rule_sha": "37651dbe",
    }
    data.setdefault("campaign", {})["fast_acceptance"] = {"accepted": True, "counted": 3}
    data["campaign"]["acceptance_scope"] = scope
    data["acceptance_scope"] = scope  # also top-level, to stress both reader paths

    folder = out / "target-explore" / f"{rid}-result"
    folder.mkdir(parents=True)
    (folder / "inputs").mkdir()
    for item in res.repro_inputs:
        (folder / item.tar_path).write_bytes(syn.TAR)
    (folder / "result.json").write_text(json.dumps(data), encoding="utf-8")

    client = TestClient(web.create_app(roots=[out]))
    runs = client.get("/api/runs")
    assert runs.status_code == 200
    run = next(r for r in runs.json()["runs"] if r["kind"] == "explore")
    assert client.get(f"/api/runs/{run['id']}").status_code == 200
    for path in ("/api/findings", "/api/replays", f"/api/artifacts/{run['id']}"):
        assert client.get(path).status_code == 200
    blob = json.dumps(client.get(f"/api/runs/{run['id']}").json())
    assert "acceptance_scope" in blob  # the unknown campaign keys survive as extras
    assert "58001" in blob  # the nested int list is intact, not dropped


def test_web_reads_real_535_additive_detector_columns(tmp_path):
    # the real #535 shape, validated by the writer's own check_fields; skipped before #535 lands
    adv = pytest.importorskip("inodefence.additive_detectors")
    detectors = {
        "schema": adv.SCHEMA,
        "generalized_identity": {
            "count": 0,
            adv.REGIONS_KEY["generalized_identity"]: [],
            "basis": adv.BASIS["generalized_identity"],
        },
        "symlink_referent": {
            "count": 0,
            adv.REGIONS_KEY["symlink_referent"]: [],
            "basis": adv.BASIS["symlink_referent"],
        },
        "evidence_sha256": "0" * 64,
    }
    adv.check_fields(detectors)  # the real #535 validator accepts this shape

    out, folder = _explore_with_result(tmp_path)
    rounds = [syn.judged_round(True), syn.failed_round()]
    rounds[0]["additive_detectors"] = detectors
    syn.replay(
        folder, {"c0": False, "c1": True, "c2": False}, rounds
    )  # the normal #535 writer path

    client = TestClient(web.create_app(roots=[out]))
    replays = client.get("/api/replays")
    assert replays.status_code == 200
    assert len(replays.json()["replays"]) >= 1  # a real #535 replay.json is read


def test_web_tolerates_unknown_replay_column(tmp_path):
    out, folder = _explore_with_result(tmp_path)
    # a valid replay, then a column the read side has never parsed, appended AFTER the writer ran
    path = syn.replay(folder, {"c0": False, "c1": True, "c2": False}, [syn.judged_round(True)])
    record = json.loads(path.read_text(encoding="utf-8"))
    record["rounds"][0]["some_future_detector"] = {"schema": "x", "values": [1, 2, 3]}
    path.write_text(json.dumps(record), encoding="utf-8")

    client = TestClient(web.create_app(roots=[out]))
    replays = client.get("/api/replays")
    assert replays.status_code == 200
    assert len(replays.json()["replays"]) >= 1  # read_replay ignores the unknown column, no crash
