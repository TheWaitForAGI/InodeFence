"""python-tarfile with ``--mutation-policy`` and ``--profile fast`` together (#535 closing base).

Two features meet on one target here: the v2 mutation policy (#511) and FAST (D064 interval on
this base; python-tarfile is not in the D065 table yet). The launch carries the option and the
FAST flags and nothing inherited; the warnings for dropped inherited values are each printed;
result.json keeps both ``campaign.mutation_policy`` and the FAST probe record.

Note for result branches P/F (python-tarfile joins the D065 table there): the launch then carries
no ``DEMO_IDENTITY_CHECK_EVERY`` and the result's ``identity_checks`` is the per-case marker
instead of the interval record; ``EXPECT_INTERVAL`` below flips with that.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests.test_python_tarfile_contained import IMAGE, RUNTIME, _LocalBackend

import inodefence.drivers.explore_result as er
import inodefence.drivers.python_tarfile.explore as pte
import inodefence.drivers.run_target as rt
from inodefence.drivers.python_tarfile.producer import ProducerImage
from inodefence.drivers.runtime import policy as pol
from inodefence.drivers.runtime import shared_images
from inodefence.drivers.runtime.session import RuntimeSession
from inodefence.mutator import MutationPolicy
from inodefence.python_tarfile_explore import python_tarfile_exploration_report

V2 = MutationPolicy.V2_FREEZE3_FIXED_BASELINE.value
#: True on this base: python-tarfile FAST keeps the D064 interval (flips on P/F).
EXPECT_INTERVAL = "python-tarfile" not in rt.FAST_PER_CASE_IDENTITY


@pytest.fixture(autouse=True)
def _fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        er, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )
    monkeypatch.setattr(
        shared_images, "check", lambda *a, **k: shared_images.SharedImages(True, "t")
    )


def test_the_launch_carries_the_option_and_fast_and_nothing_inherited(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("DEMO_MUTATION_POLICY", "inherited-mutation")
    monkeypatch.setenv("DEMO_POLICY", "inherited-search")
    monkeypatch.setenv("DEMO_IDENTITY_CHECK_EVERY", "7")
    envs: list[dict[str, str]] = []

    def runner(argv: Any, env: Any = None, **_: Any) -> Any:
        envs.append(dict(env))
        return subprocess.CompletedProcess(argv, 1)

    session = RuntimeSession(target="python-tarfile", policy=pol.FAST)
    with pytest.raises(RuntimeError):  # the fake runner exits 1: only the launch is under test
        pte.run_controller("img", "3.12.7", "data", out=tmp_path, run_id="rid", budget=4,
                           seed=1, mutation_policy=V2, runner=runner, session=session)  # fmt: skip
    (env,) = envs
    assert env["DEMO_MUTATION_POLICY"] == V2
    assert "DEMO_POLICY" not in env
    assert env["SKIP_BUILD"] == "1"
    if EXPECT_INTERVAL:
        assert env["DEMO_IDENTITY_CHECK_EVERY"] == str(pol.FAST_IDENTITY_CHECK_EVERY)
    else:
        assert "DEMO_IDENTITY_CHECK_EVERY" not in env
    err = capsys.readouterr().err
    # each dropped inherited value gets its own line; neither hides the other
    assert "use --mutation-policy (node-tar, python-tarfile exploration)" in err
    assert "exploration runs the target's fixed search policy" in err


def test_result_keeps_both_the_policy_and_the_fast_record(monkeypatch, tmp_path: Path) -> None:
    every = pol.FAST_IDENTITY_CHECK_EVERY if EXPECT_INTERVAL else None
    report = python_tarfile_exploration_report(
        _LocalBackend(), IMAGE, "data", RUNTIME, seed=7, budget=6,
        mutation_policy=MutationPolicy(V2), identity_check_every=every,
    )  # fmt: skip

    def fake(*_: Any, out: Path, run_id: str, **__: Any) -> Path:
        path = pte.report_path(out, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    monkeypatch.setattr(pte, "run_controller", fake)
    prepared = rt.PreparedTargetImage(
        "python-tarfile", RUNTIME, RUNTIME, "python:x", "sha256:" + "c" * 64, False
    )
    made = ProducerImage(IMAGE, "sha256:" + "d" * 64, RUNTIME, "e" * 64, "f" * 64, "reused")
    options = rt.ExploreOptions(
        budget=6, seed=7, out=tmp_path, mutation_policy=V2,
        runtime=RuntimeSession(target="python-tarfile", policy=pol.FAST),
        target_options={"extraction-filter": "data"},
    )  # fmt: skip
    outcome = pte.explore(prepared, options, ensure=lambda *a, **k: made)
    campaign = json.loads(outcome.result_path.read_text(encoding="utf-8"))["campaign"]
    assert campaign["mutation_policy"] == V2
    checks = campaign["identity_checks"]
    if EXPECT_INTERVAL:
        assert checks["interval"] == pol.FAST_IDENTITY_CHECK_EVERY and checks["total_checks"] >= 1
    else:
        assert checks["interval"] == 1 and checks["acceptance_evidence"] is False
