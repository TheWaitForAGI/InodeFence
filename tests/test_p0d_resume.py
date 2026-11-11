"""Synthetic resume under a changed jobs value while the preregistration is unchanged."""

import json

import pytest
import scripts.run_exp0 as launcher

from test_run_exp0 import BEFORE, TARGET_IMAGES, _deadline_setup, _fake_runner, _result_lines
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine

pytestmark = pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")


def test_resume_accepts_different_jobs_below_the_cap(tmp_path, monkeypatch):
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="2")
    out.mkdir()
    (out / "cell-results.jsonl").write_text(
        json.dumps({"event": "start", "run_id": "earlier", "attempt": 1, "jobs": 2})
        + "\n"
        + json.dumps({"event": "infrastructure-stop", "reason": "synthetic"})
        + "\n"
    )
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(launcher, "run_cell_with_watchdog", runner)
    assert launcher.main(args) == 1 and not runner.calls
    changed = list(args)
    changed[changed.index("--jobs") + 1] = "1"
    assert launcher.main([*changed, "--resume-after-stop", "synthetic-ref"]) == 0
    rows = _result_lines(out)
    assert any(r.get("event") == "infrastructure-resume" for r in rows)
    assert {r["jobs"] for r in rows if r.get("event") == "start"} == {1, 2}
    assert runner.calls
