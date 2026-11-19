"""D065 widened: FAST keeps the rebuild skip only on more targets than decompress/oras-go.

``EXPECTED`` is the branch's table (the one line that differs between the local result branches):
which targets probe per case under FAST and the ``fast_acceptance`` state each result records.
For every target in it beyond the 2b pair, W4's three conditions hold as for 2b:

1. probes: the driver requests no interval, so the loop probes at bind and before every case
   (1 + budget, as STRICT) and its report carries no ``identity_checks`` record;
2. an inherited ``DEMO_IDENTITY_CHECK_EVERY`` never reaches the launch;
3. the result carries the per-case marker with that target's state (never omitted: without it a
   STRICT-shaped folder would pass the comparison tool's STRICT side), the relaxed check stays
   limited to the marker, and the comparison tool refuses the folder on both sides.

Plus the 0.2.0 equivalence: the target's FAST launch equals what main ``fccdf35`` launched
(``tests/fixtures/fast-2b-v1/launches-0.2.0.json``, recorded with fccdf35's own drivers).
Synthetic only; no target runs.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
from scripts import compare_fast_strict as cfs
from tests.test_python_tarfile_contained import IMAGE, RUNTIME, _LocalBackend

import inodefence.drivers.explore_result as er
import inodefence.drivers.node_tar.explore as nte
import inodefence.drivers.python_tarfile.explore as pte
import inodefence.drivers.run_target as rt
import inodefence.drivers.run_target_explore as rte
from inodefence.drivers.python_tarfile.producer import ProducerImage
from inodefence.drivers.runtime import policy as pol
from inodefence.drivers.runtime import shared_images
from inodefence.drivers.runtime.session import RuntimeSession
from inodefence.python_tarfile_explore import python_tarfile_exploration_report
from inodefence.target_result import (
    FAST_ACCEPTANCE_CRITERION_MET_NO_VIOLATION_PATHS,
    FAST_ACCEPTANCE_NOT_MEASURED,
    TargetResultError,
    _check_identity_checks,
    from_json_dict,
    per_case_identity_marker,
)
from inodefence.target_result_summary import PER_CASE_SUMMARY, render_summary

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fast-2b-v1" / "launches-0.2.0.json"
#: This branch's table (P: node-tar keeps the D064 interval).
EXPECTED = {
    "decompress": FAST_ACCEPTANCE_NOT_MEASURED,
    "oras-go": FAST_ACCEPTANCE_NOT_MEASURED,
    "python-tarfile": FAST_ACCEPTANCE_CRITERION_MET_NO_VIOLATION_PATHS,
}
WIDENED = tuple(t for t in EXPECTED if t not in ("decompress", "oras-go"))
FAST_2B = dataclasses.replace(pol.FAST, identity_check_every=None)


@pytest.fixture(autouse=True)
def _fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        er, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )
    monkeypatch.delenv("DEMO_IDENTITY_CHECK_EVERY", raising=False)
    monkeypatch.setattr(
        shared_images, "check", lambda *a, **k: shared_images.SharedImages(True, "t")
    )
    monkeypatch.setattr(nte, "LivePuller", _NoPuller)


class _NoPuller:
    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    def start(self) -> _NoPuller:
        return self

    def stop(self, **k: Any) -> None:
        pass


def test_the_table_is_this_branchs() -> None:
    assert rt.FAST_PER_CASE_IDENTITY == EXPECTED
    for state in set(EXPECTED.values()):
        assert state in PER_CASE_SUMMARY  # every state has its summary words


# -- the driver's policy change and its stderr line ----------------------------------------------


def _dry_run(target: str, capsys) -> tuple[dict[str, Any], str]:
    argv = ["--target", target, "--dry-run", "--profile", "fast", "--out", tempfile.gettempdir()]
    if target == "python-tarfile":
        argv += ["--version", "3.12.7", "--extraction-filter", "data"]
    else:
        argv += ["--version", "7.5.23"]
    assert rte.main(argv) == 0
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.err


@pytest.mark.parametrize("target", WIDENED)
def test_fast_keeps_the_rebuild_skip_only(target: str, capsys) -> None:
    plan, err = _dry_run(target, capsys)
    assert plan["runtime_profile"] == {"profile": "fast", "policy": {"reuse_shared_images": True}}
    assert err.count("TARGET-EXPLORE:") == 1
    assert (
        f"--profile fast on {target} skips the shared-image rebuild only; the D064 "
        "identity-probe interval is not applied, so the image identity is probed before every "
        "case." in err
    )
    assert "no FAST acceptance" not in err  # that reason belongs to not_measured only


# -- condition 2 and the 0.2.0 launch ------------------------------------------------------------


def _launch(target: str, session: RuntimeSession, runner: Any, tmp: Path) -> None:
    try:
        if target == "python-tarfile":
            pte.run_controller("img", "3.12.7", "data", out=tmp, run_id="rid", budget=4, seed=1,
                               runner=runner, session=session)  # fmt: skip
        else:
            node = rt.PreparedTargetImage("node-tar", "7.5.23", "7.5.23", "img",
                                          "sha256:" + "a" * 64, True)  # fmt: skip
            nte.run_controller(node, out=tmp, run_id="rid", budget=4, seed=1, python="x",
                               runner=runner, session=session)  # fmt: skip
    except RuntimeError:
        pass  # the fake runner exits 1: only the launch is under test


@pytest.mark.parametrize("target", WIDENED)
def test_an_inherited_interval_never_reaches_the_launch(
    target: str, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEMO_IDENTITY_CHECK_EVERY", "7")
    seen: dict[str, Any] = {}

    def explore(prepared: Any, options: rt.ExploreOptions) -> rt.ExploreOutcome:
        seen["requested"] = rt.requested_identity_check_every(options)
        session = options.runtime
        assert isinstance(session, RuntimeSession)
        seen["policy"] = session.policy
        envs: list[dict[str, str]] = []

        def runner(argv: Any, env: Any = None, **_: Any) -> Any:
            envs.append(dict(env))
            return subprocess.CompletedProcess(argv, 1)

        _launch(target, session, runner, tmp_path / "launch")
        seen["envs"] = envs
        seen["applied"] = [record.policy_applied for record in session.launches]
        return rt.ExploreOutcome(tmp_path / "absent" / "result.json", "PASS", 4, 0)

    adapter = dataclasses.replace(
        rt.load_adapter(target), explore=explore, cells=lambda versions, filters: []
    )
    monkeypatch.setattr(rte, "load_adapter", lambda name: adapter)
    prepared = rt.PreparedTargetImage(target, "x", "x", "img", "sha256:" + "a" * 64, True)
    monkeypatch.setattr(rte, "prepare_target_image", lambda *a, **k: prepared)
    monkeypatch.setattr(rte, "docker_problem", lambda: None)
    argv = ["--target", target, "--version", "x", "--out", str(tmp_path / "out")]
    argv += ["--auto-prepare", "--output", "quiet", "--profile", "fast"]
    if target == "python-tarfile":
        argv += ["--extraction-filter", "data"]
    assert rte.main(argv) == 0
    assert seen["requested"] is None and seen["policy"] == FAST_2B
    assert seen["envs"] and all("DEMO_IDENTITY_CHECK_EVERY" not in env for env in seen["envs"])
    assert all("identity_check_every" not in applied for applied in seen["applied"])


@pytest.mark.parametrize("target", WIDENED)
def test_the_launch_equals_0_2_0(target: str) -> None:
    seen: list[dict[str, Any]] = []

    def runner(argv: Any, env: Any = None, **_: Any) -> Any:
        changed = {k: v for k, v in env.items() if os.environ.get(k) != v}
        removed = sorted(k for k in os.environ if k not in env)
        seen.append({"argv": [Path(a).name if "/" in a else a for a in argv],
                     "changed": changed, "removed": removed})  # fmt: skip
        return subprocess.CompletedProcess(argv, 1)

    with tempfile.TemporaryDirectory() as tmp:
        _launch(target, RuntimeSession(target=target, policy=FAST_2B), runner, Path(tmp))
        for item in seen:
            item["changed"] = {k: v.replace(tmp, "<tmp>") for k, v in item["changed"].items()}
            if "DEMO_ENGINE_COMMIT" in item["changed"]:
                item["changed"]["DEMO_ENGINE_COMMIT"] = "<engine>"
    assert seen == json.loads(FIXTURE.read_text(encoding="utf-8"))[target]


# -- condition 1: probes and the loop report -----------------------------------------------------


def _python_report(every: int | None, budget: int = 6) -> tuple[dict[str, Any], int]:
    backend = _LocalBackend()
    report = python_tarfile_exploration_report(
        backend, IMAGE, "data", RUNTIME, seed=7, budget=budget, identity_check_every=every
    )
    probes = sum(1 for command in backend.commands if command[3] == "--identify")
    report.pop("timing")  # wall-clock seconds: the only field that differs between two runs
    return report, probes


@pytest.mark.skipif("python-tarfile" not in EXPECTED, reason="python-tarfile keeps its interval")
def test_python_tarfile_probes_before_every_case_like_strict(tmp_path: Path) -> None:
    requested = rt.requested_identity_check_every(
        rt.ExploreOptions(budget=6, seed=7, out=tmp_path,
                          runtime=RuntimeSession(target="python-tarfile", policy=FAST_2B))
    )  # fmt: skip
    assert requested is None
    fast, fast_probes = _python_report(requested)
    strict, strict_probes = _python_report(None)
    assert fast_probes == strict_probes == 1 + 6  # bind + one per case
    assert fast == strict and "identity_checks" not in fast
    _, interval_probes = _python_report(3)  # contrast: the D064 schedule probes less
    assert interval_probes < fast_probes


# -- condition 3: the marker through each driver, its scope, the comparison tool -----------------


def _python_result(tmp: Path, session: RuntimeSession) -> dict[str, Any]:
    report = python_tarfile_exploration_report(_LocalBackend(), IMAGE, "data", RUNTIME, seed=7,
                                               budget=6)  # fmt: skip
    prepared = rt.PreparedTargetImage(
        "python-tarfile", RUNTIME, RUNTIME, "python:x", "sha256:" + "c" * 64, False
    )
    made = ProducerImage(IMAGE, "sha256:" + "d" * 64, RUNTIME, "e" * 64, "f" * 64, "reused")

    def fake(*_: Any, out: Path, run_id: str, **__: Any) -> Path:
        path = pte.report_path(out, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    pte.run_controller = fake  # type: ignore[assignment]  # restored by the caller's monkeypatch
    options = rt.ExploreOptions(budget=6, seed=7, out=tmp, runtime=session,
                                target_options={"extraction-filter": "data"})  # fmt: skip
    outcome = pte.explore(prepared, options, ensure=lambda *a, **k: made)
    return json.loads(outcome.result_path.read_text(encoding="utf-8"))


def _node_result(tmp: Path, session: RuntimeSession) -> dict[str, Any]:
    report = {
        "demo_report_schema": 5,
        "streaming": True,
        "aggregate": {"runs_executed": 6, "terminations": {"success": 6}, "unjudged_steps": 0,
                      "errors": 0},
        "violation_cases": [],
        "violation_inputs": [],
    }  # fmt: skip

    def fake(prepared: Any, *, out: Path, run_id: str, **_: Any) -> Path:
        path = nte.controller_report_path(out, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    nte.run_controller = fake  # type: ignore[assignment]
    prepared = rt.PreparedTargetImage("node-tar", "7.5.23", "7.5.23",
                                      "inodefence-node-tar-registry:7.5.23",
                                      "sha256:" + "a" * 64, True)  # fmt: skip
    outcome = nte.explore(prepared, rt.ExploreOptions(budget=6, seed=1, out=tmp, runtime=session))
    return json.loads(outcome.result_path.read_text(encoding="utf-8"))


RESULTS = {"python-tarfile": _python_result, "node-tar": _node_result}


@pytest.mark.parametrize("target", WIDENED)
def test_the_driver_never_omits_the_marker(target: str, monkeypatch, tmp_path: Path) -> None:
    # Without the marker a STRICT-shaped folder would pass the comparison tool's STRICT side.
    monkeypatch.setattr(pte, "run_controller", pte.run_controller)
    monkeypatch.setattr(nte, "run_controller", nte.run_controller)
    fast = RESULTS[target](tmp_path / "f", RuntimeSession(target=target, policy=FAST_2B))
    marker = fast["campaign"]["identity_checks"]
    assert marker == per_case_identity_marker(target, EXPECTED[target])
    assert "total_checks" not in marker
    strict = RESULTS[target](tmp_path / "s", RuntimeSession(target=target, policy=pol.STRICT))
    assert "identity_checks" not in strict["campaign"]
    fast["campaign"].pop("identity_checks")
    assert fast == strict  # a STRICT and a per-case FAST result differ only by the marker


@pytest.mark.parametrize("target", WIDENED)
def test_the_summary_names_the_targets_state(target: str, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pte, "run_controller", pte.run_controller)
    monkeypatch.setattr(nte, "run_controller", nte.run_controller)
    data = RESULTS[target](tmp_path / "f", RuntimeSession(target=target, policy=FAST_2B))
    text = render_summary(from_json_dict(data), source_name="result.json", inputs_verified=True)
    words = PER_CASE_SUMMARY[EXPECTED[target]]
    assert f"| 이미지 신원 확인 | 케이스마다 (FAST 간격 미적용, {words}) |" in text


def _folder(tmp: Path, target: str) -> Path:
    """A per-case FAST result folder of ``target``'s shape: STRICT-shaped loop report and runtime
    record, a result.json with the marker."""
    tmp.mkdir()
    report: dict[str, Any] = {"demo_report_schema": 5}
    if target == "python-tarfile":
        report["case_records"] = []
    else:
        report["aggregate"] = {"runs_executed": 6, "terminations": {"success": 6}}
    (tmp / "report.json").write_text(json.dumps(report))
    result = {
        "schema": cfs.RESULT_SCHEMA,
        "campaign": {"identity_checks": per_case_identity_marker(target, EXPECTED[target])},
    }
    (tmp / "result.json").write_text(json.dumps(result))  # fmt: skip
    runtime = {
        "schema": cfs.RUNTIME_SCHEMA,
        "kind": "explore",
        "launches": [{"policy_applied": {"reuse_shared_images": {"applied": True}}}],
    }
    (tmp / "runtime.json").write_text(json.dumps(runtime))
    return tmp


@pytest.mark.parametrize("side", ["fast", "strict"])
@pytest.mark.parametrize("target", WIDENED)
def test_the_comparison_tool_refuses_the_folder_on_either_side(
    target: str, side: str, tmp_path: Path
) -> None:
    with pytest.raises(cfs.InputError):
        cfs.check_fast_layers(_folder(tmp_path / "f", target), side)


@pytest.mark.parametrize("target", WIDENED)
def test_the_relaxed_check_stays_limited_to_the_marker(target: str) -> None:
    marker = per_case_identity_marker(target, EXPECTED[target])
    with pytest.raises(TargetResultError, match="interval 1"):
        _check_identity_checks({**marker, "interval": 200})
    with pytest.raises(TargetResultError, match="total_checks"):
        _check_identity_checks({"interval": 1})  # no marker: total_checks is required
    _check_identity_checks(marker)  # the marker itself is accepted
