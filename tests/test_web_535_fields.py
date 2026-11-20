"""The web tolerates #535's new result.json fields without breaking.

#535 added ``fast_acceptance`` and a nested ``acceptance_scope`` (with a ``counted_seeds`` list)
to result.json. The read model keeps campaign keys it does not know in ``extras``; the web only has
to serialize them (nested dict + list) and keep every endpoint 200 -- it never renders arbitrary
extras into the fixed detail fields, so there is nothing to crash on.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests import app_synthetic as syn  # noqa: E402

from inodefence.ui import web  # noqa: E402


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

    # a valid replay beside the run, then #535's extra detector column appended to a round AFTER
    # the writer ran. The web reads replays with inodefence.app.runs.read_replay, which reads only
    # the fields it knows (round/classification/termination/c0..c2) and ignores the rest -- so the
    # extra column must not break it. (Appending after the write keeps the writer-side validator,
    # case_replay.normalize_round, out of this read-side tolerance test.)
    replay_path = syn.replay(
        folder, {"c0": False, "c1": True, "c2": False}, [syn.judged_round(True), syn.failed_round()]
    )
    record = json.loads(replay_path.read_text(encoding="utf-8"))
    record["rounds"][0]["additive_detectors"] = {
        "schema": "inodefence-additive-detectors-v1",
        "note": "a #535 detector column the read side has never parsed; it must be ignored",
    }
    replay_path.write_text(json.dumps(record), encoding="utf-8")

    client = TestClient(web.create_app(roots=[out]))
    runs = client.get("/api/runs")
    assert runs.status_code == 200
    run = next(r for r in runs.json()["runs"] if r["kind"] == "explore")
    # the nested dict + list must not cause a 500 on any endpoint that reads this run
    assert client.get(f"/api/runs/{run['id']}").status_code == 200
    replays = client.get("/api/replays")
    assert replays.status_code == 200
    assert len(replays.json()["replays"]) >= 1  # the replay is read despite the extra columns
    for path in ("/api/findings", f"/api/artifacts/{run['id']}"):
        assert client.get(path).status_code == 200
    # the unknown campaign keys survive as extras (list of ints intact), not silently dropped
    detail = client.get(f"/api/runs/{run['id']}").json()
    blob = json.dumps(detail)
    assert "acceptance_scope" in blob
    assert "58001" in blob
