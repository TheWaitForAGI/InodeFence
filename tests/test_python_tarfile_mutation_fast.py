"""python-tarfile with ``--mutation-policy`` and ``--profile fast`` together (#535 closing base).

Two features meet on one target: the v2 mutation policy (#511) and FAST (#536). Both tests run the
product command (``run_target_explore.main``), which builds the runtime session and, for a target
in the D065 table, drops the D064 interval; only the adapter's ``explore`` is a stand-in, and it
calls the real python-tarfile driver code with the options and session ``main`` gave it. The
launch carries the option and FAST's own flags and nothing inherited; each dropped inherited value
keeps its own warning line; result.json keeps both ``campaign.mutation_policy`` and the FAST record.

``EXPECT_INTERVAL`` follows the D065 table: true on this base, false once python-tarfile joins the
table (result branches P/F); the launch then carries no ``DEMO_IDENTITY_CHECK_EVERY`` and the result
records the per-case marker.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from tests.test_python_tarfile_contained import IMAGE, RUNTIME, _LocalBackend

import inodefence.drivers.explore_result as er
import inodefence.drivers.python_tarfile.explore as pte
import inodefence.drivers.run_target as rt
import inodefence.drivers.run_target_explore as rte
from inodefence.drivers.python_tarfile.producer import ProducerImage
from inodefence.drivers.runtime import policy as pol
from inodefence.drivers.runtime import shared_images
from inodefence.drivers.runtime.session import RuntimeSession
from inodefence.mutator import MutationPolicy
from inodefence.python_tarfile_explore import python_tarfile_exploration_report

V2 = MutationPolicy.V2_FREEZE3_FIXED_BASELINE.value
#: True on this base: python-tarfile FAST keeps the D064 interval (false on P/F).
EXPECT_INTERVAL = "python-tarfile" not in rt.FAST_PER_CASE_IDENTITY
PREPARED = rt.PreparedTargetImage(
    "python-tarfile", RUNTIME, RUNTIME, "python:x", "sha256:" + "c" * 64, False
)


@pytest.fixture(autouse=True)
def _fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        er, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )
    monkeypatch.setattr(
        shared_images, "check", lambda *a, **k: shared_images.SharedImages(True, "t")
    )
    monkeypatch.delenv("DEMO_IDENTITY_CHECK_EVERY", raising=False)


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp: Path,
    body: Callable[[rt.ExploreOptions], rt.ExploreOutcome],
) -> rt.ExploreOptions:
    """Run the product command with both options; ``body`` gets the options ``main`` built."""
    seen: dict[str, rt.ExploreOptions] = {}

    def explore(prepared: Any, options: rt.ExploreOptions) -> rt.ExploreOutcome:
        seen["options"] = options
        return body(options)

    adapter = dataclasses.replace(
        rt.load_adapter("python-tarfile"), explore=explore, cells=lambda versions, filters: []
    )
    monkeypatch.setattr(rte, "load_adapter", lambda name: adapter)
    monkeypatch.setattr(rte, "prepare_target_image", lambda *a, **k: PREPARED)
    monkeypatch.setattr(rte, "docker_problem", lambda: None)
    argv = ["--target", "python-tarfile", "--version", RUNTIME, "--out", str(tmp / "out")]
    argv += ["--auto-prepare", "--output", "quiet", "--profile", "fast"]
    argv += ["--extraction-filter", "data", "--mutation-policy", V2]
    rte.main(argv)
    return seen["options"]


def test_the_launch_carries_the_option_and_fast_and_nothing_inherited(
    monkeypatch, tmp_path: Path, capfd
) -> None:
    monkeypatch.setenv("DEMO_MUTATION_POLICY", "inherited-mutation")
    monkeypatch.setenv("DEMO_POLICY", "inherited-search")
    monkeypatch.setenv("DEMO_IDENTITY_CHECK_EVERY", "7")
    envs: list[dict[str, str]] = []

    def runner(argv: Any, env: Any = None, **_: Any) -> Any:
        envs.append(dict(env))
        return subprocess.CompletedProcess(argv, 1)

    def body(options: rt.ExploreOptions) -> rt.ExploreOutcome:
        session = options.runtime
        assert isinstance(session, RuntimeSession)
        with pytest.raises(RuntimeError):  # the fake runner exits 1: only the launch is tested
            pte.run_controller("img", RUNTIME, "data", out=tmp_path / "launch", run_id="rid",
                               budget=4, seed=1, mutation_policy=options.mutation_policy,
                               runner=runner, session=session)  # fmt: skip
        return rt.ExploreOutcome(tmp_path / "absent" / "result.json", "PASS", 4, 0)

    options = _run_main(monkeypatch, tmp_path, body)
    assert options.mutation_policy == V2
    (env,) = envs
    assert env["DEMO_MUTATION_POLICY"] == V2
    assert "DEMO_POLICY" not in env
    assert env["SKIP_BUILD"] == "1"
    if EXPECT_INTERVAL:
        assert env["DEMO_IDENTITY_CHECK_EVERY"] == str(pol.FAST_IDENTITY_CHECK_EVERY)
    else:
        assert "DEMO_IDENTITY_CHECK_EVERY" not in env
    # fd level: during explore the driver prints to the saved stderr descriptor (LauncherLog)
    err = capfd.readouterr().err
    # each dropped inherited value gets its own line; neither hides the other
    assert "use --mutation-policy (node-tar, python-tarfile exploration)" in err
    assert "exploration runs the target's fixed search policy" in err
    assert "DEMO_IDENTITY_CHECK_EVERY=7 is ignored" in err


def test_result_keeps_both_the_policy_and_the_fast_record(monkeypatch, tmp_path: Path) -> None:
    made = ProducerImage(IMAGE, "sha256:" + "d" * 64, RUNTIME, "e" * 64, "f" * 64, "reused")
    written: dict[str, Path] = {}

    def body(options: rt.ExploreOptions) -> rt.ExploreOutcome:
        # the loop report a run with what main asked for would write
        every = rt.requested_identity_check_every(options)
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
        outcome = pte.explore(PREPARED, options, ensure=lambda *a, **k: made)
        written["result"] = outcome.result_path
        return outcome

    _run_main(monkeypatch, tmp_path, body)
    campaign = json.loads(written["result"].read_text(encoding="utf-8"))["campaign"]
    assert campaign["mutation_policy"] == V2
    checks = campaign["identity_checks"]
    if EXPECT_INTERVAL:
        assert checks["interval"] == pol.FAST_IDENTITY_CHECK_EVERY and checks["total_checks"] >= 1
    else:
        assert checks["interval"] == 1 and checks["acceptance_evidence"] is False
