"""D065 ("2b"): decompress/oras-go ``--profile fast`` keeps the shared-image rebuild skip only.

The D064 identity-probe interval is not applied to these two targets (no FAST acceptance was
measured for them): their image identity is probed before every case, as STRICT does. W4's three
conditions, pinned here:

1. probe count: the controller receives no interval, so it probes at bind and before every case,
   the same count as a STRICT run (the loop has no separate end probe without an interval);
2. an inherited or forwarded interval is ignored: with ``DEMO_IDENTITY_CHECK_EVERY=7`` in the
   caller's environment the requested interval is None, the launch env carries no such variable;
3. the record: ``campaign.identity_checks`` is the per-case marker (``interval`` 1,
   ``fast_acceptance: not_measured``, ``acceptance_evidence: false``, no ``total_checks``); the
   relaxed check applies to the marker only; one stderr line; summary.md says "케이스마다".

Plus the 0.2.0 equivalence: the two targets' FAST launches equal what main ``fccdf35`` (0.2.0)
launched (``tests/fixtures/fast-2b-v1/launches-0.2.0.json``, recorded by running fccdf35's own
drivers with the same fake runner), and a STRICT and a 2b result of the same run differ only by
the marker. node-tar/python-tarfile FAST and every STRICT path are unchanged (their existing
tests). Synthetic only; no target runs.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
from scripts import compare_fast_strict as cfs
from scripts.container_controller import run_native_decompress_campaign, run_native_oras_go_campaign
from tests import test_decompress_effect_campaign as dtest
from tests import test_oras_go_effect_campaign as otest

import inodefence.drivers.decompress.explore as dce
import inodefence.drivers.explore_result as er
import inodefence.drivers.oras_go.explore as oge
import inodefence.drivers.run_target as rt
import inodefence.drivers.run_target_explore as rte
from inodefence.drivers.runtime import policy as pol
from inodefence.drivers.runtime import shared_images
from inodefence.drivers.runtime.session import RuntimeSession
from inodefence.target_result import (
    PER_CASE_IDENTITY_MARKER,
    TargetResultError,
    from_json_dict,
)
from inodefence.target_result_summary import render_summary

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fast-2b-v1" / "launches-0.2.0.json"
TWO = ("decompress", "oras-go")
VERSIONS = {"decompress": "decompress@4.2.1", "oras-go": "2.6.2"}
FAST_2B = dataclasses.replace(pol.FAST, identity_check_every=None)
NEEDS_SANDBOX = pytest.mark.skipif(
    not Path("/var/lib/inodefence").is_dir(),
    reason="disposable sandbox requires the Linux runtime root (Dev Container)",
)


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        er, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )


def test_the_two_targets_are_the_d065_list() -> None:
    assert rt.FAST_PER_CASE_IDENTITY_TARGETS == TWO


# -- the driver's one policy change --------------------------------------------------------------


def _dry_run(target: str, capsys) -> tuple[dict[str, Any], str]:
    argv = ["--target", target, "--version", VERSIONS.get(target, "7.5.23"), "--dry-run"]
    argv += ["--profile", "fast", "--out", tempfile.gettempdir()]
    if target == "python-tarfile":
        argv[3] = "3.12.7"
        argv += ["--extraction-filter", "data"]
    assert rte.main(argv) == 0
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.err


@pytest.mark.parametrize("target", TWO)
def test_fast_on_the_two_targets_keeps_the_rebuild_skip_only(target: str, capsys) -> None:
    plan, err = _dry_run(target, capsys)
    assert plan["runtime_profile"] == {"profile": "fast", "policy": {"reuse_shared_images": True}}
    assert err.count("TARGET-EXPLORE:") == 1
    assert (
        f"--profile fast on {target} skips the shared-image rebuild only; the D064 "
        "identity-probe interval is not applied" in err
    )


@pytest.mark.parametrize("target", ["node-tar", "python-tarfile"])
def test_fast_on_node_tar_and_python_tarfile_is_unchanged(target: str, capsys) -> None:
    plan, err = _dry_run(target, capsys)
    assert plan["runtime_profile"]["policy"] == {
        "reuse_shared_images": True,
        "identity_check_every": pol.FAST_IDENTITY_CHECK_EVERY,
    }
    assert "D064 identity-probe interval is not applied" not in err


# -- condition 2: an inherited value is ignored; the launch carries no interval ------------------


def _launch(target: str, session: RuntimeSession, runner: Any, tmp: Path) -> None:
    try:
        if target == "decompress":
            dce.run_controller("img", tmp, "rid", seed=1, budget=4, mutation_policy=None,
                               search_policy=None, runner=runner, session=session)  # fmt: skip
        else:
            prepared = rt.PreparedTargetImage("oras-go", "2.6.1", "2.6.1", "img",
                                              "sha256:" + "a" * 64, True)  # fmt: skip
            oge.run_controller(prepared, out=tmp, run_id="rid", budget=4, seed=1, python="x",
                               runner=runner, session=session)  # fmt: skip
    except RuntimeError:
        pass  # the fake runner exits 1: only the launch is under test


@pytest.mark.parametrize("target", TWO)
def test_an_inherited_interval_is_ignored_on_the_two_targets(
    target: str, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEMO_IDENTITY_CHECK_EVERY", "7")
    monkeypatch.setattr(
        shared_images, "check", lambda *a, **k: shared_images.SharedImages(True, "t")
    )
    seen: dict[str, Any] = {}

    def explore(prepared: Any, options: rt.ExploreOptions) -> rt.ExploreOutcome:
        seen["requested"] = rt.requested_identity_check_every(options)
        seen["policy"] = options.runtime.policy
        envs: list[dict[str, str]] = []

        def runner(argv: Any, env: Any = None, **_: Any) -> Any:
            envs.append(dict(env))
            seen["argv"] = list(argv)
            return subprocess.CompletedProcess(argv, 1)

        _launch(target, options.runtime, runner, tmp_path / "launch")
        seen["envs"] = envs
        seen["applied"] = [record.policy_applied for record in options.runtime.launches]
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
    assert rte.main(argv) == 0
    assert seen["requested"] is None
    assert seen["policy"] == FAST_2B
    assert seen["envs"] and all("DEMO_IDENTITY_CHECK_EVERY" not in env for env in seen["envs"])
    assert not any("--identity-check-every" in arg for arg in seen["argv"])
    assert all("identity_check_every" not in applied for applied in seen["applied"])


# -- 0.2.0 equivalence (1): the launches equal fccdf35's FAST launches ----------------------------


def test_the_launches_equal_0_2_0(monkeypatch) -> None:
    monkeypatch.delenv("DEMO_IDENTITY_CHECK_EVERY", raising=False)
    monkeypatch.setattr(
        shared_images, "check", lambda *a, **k: shared_images.SharedImages(True, "t")
    )
    records: dict[str, list[dict[str, Any]]] = {}
    for target in TWO:
        seen: list[dict[str, Any]] = []

        def runner(argv: Any, env: Any = None, _seen: list = seen, **_: Any) -> Any:
            changed = {k: v for k, v in env.items() if os.environ.get(k) != v}
            removed = sorted(k for k in os.environ if k not in env)
            _seen.append({"argv": [Path(a).name if "/" in a else a for a in argv],
                          "changed": changed, "removed": removed})  # fmt: skip
            return subprocess.CompletedProcess(argv, 1)

        with tempfile.TemporaryDirectory() as tmp:
            _launch(target, RuntimeSession(target=target, policy=FAST_2B), runner, Path(tmp))
            for item in seen:
                item["changed"] = {k: v.replace(tmp, "<tmp>") for k, v in item["changed"].items()}
        records[target] = seen
    assert records == json.loads(FIXTURE.read_text(encoding="utf-8"))


# -- condition 1 and 0.2.0 equivalence (2): probes and the loop report ---------------------------


CONTROLLERS = {
    "decompress": (dtest._ExtractingBackend, dtest._identity_bytes, dtest._IMAGE,
                   run_native_decompress_campaign),
    "oras-go": (otest._ExtractingBackend, otest._identity_bytes, otest._IMAGE,
                run_native_oras_go_campaign),
}  # fmt: skip


def _counting(base: type, identity: bytes):
    class Counting(base):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__(identity)
            self.probes = 0
            self.archive_runs = 0

        def prepare(self, request):  # type: ignore[no-untyped-def]
            if "identify" in request.command:
                self.probes += 1
            else:
                self.archive_runs += 1
            return super().prepare(request)

    return Counting()


def _controller_run(target: str, tmp: Path, every: int | None, budget: int = 6):
    base, identity, image, run = CONTROLLERS[target]
    backend = _counting(base, identity())
    tmp.mkdir(parents=True, exist_ok=True)
    evidence = tmp / f"{target}-{every}.json"
    args = argparse.Namespace(
        seed=7, budget=budget, mutation_policy=None, policy=None, identity_check_every=every
    )
    assert run(backend, image, evidence, args) == 0
    return evidence.read_bytes(), backend


@NEEDS_SANDBOX
@pytest.mark.parametrize("target", TWO)
def test_2b_probes_before_every_case_like_strict(target: str, tmp_path: Path) -> None:
    # 2b passes no interval (condition 2), so the controller gets None: the STRICT path.
    requested = rt.requested_identity_check_every(
        rt.ExploreOptions(budget=6, seed=7, out=tmp_path,
                          runtime=RuntimeSession(target=target, policy=FAST_2B))
    )  # fmt: skip
    assert requested is None
    report_2b, backend_2b = _controller_run(target, tmp_path / "a", requested)
    report_strict, backend_strict = _controller_run(target, tmp_path / "b", None)
    assert backend_2b.archive_runs == 6
    assert backend_2b.probes == backend_strict.probes == 1 + 6  # bind + one per case
    assert report_2b == report_strict  # the loop report is STRICT's, byte for byte
    assert "identity_checks" not in json.loads(report_2b)
    # for contrast: an interval-2 FAST run probes less (bind, every 2nd case, end)
    _, backend_fast = _controller_run(target, tmp_path / "c", 2)
    assert backend_fast.probes < backend_2b.probes


# -- condition 3: the marker, its validation, the summary, the comparison tool -------------------


def _session(policy: pol.RuntimePolicy, target: str = "decompress") -> RuntimeSession:
    return RuntimeSession(target=target, policy=policy)


def _result() -> Any:
    from inodefence.target_result import CampaignInfo, ResultMode, TargetAxes, TargetResult

    return TargetResult(
        target="decompress",
        axes=TargetAxes(target_version="decompress@4.2.1"),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cases=(),
        repro_inputs=(),
        provenance=rt.Provenance("b" * 40, False, "img", "sha256:" + "a" * 64),
        campaign=CampaignInfo(seed=1, budget=4, runs_to_first_violation=None, runs_executed=4),
    )


def test_the_marker_is_written_only_for_fast_without_an_interval() -> None:
    result = _result()
    marked = er.with_per_case_identity_marker(result, _session(FAST_2B))
    assert marked.campaign.identity_checks == PER_CASE_IDENTITY_MARKER
    assert "total_checks" not in marked.campaign.identity_checks
    assert er.with_per_case_identity_marker(result, _session(pol.STRICT)) is result
    assert er.with_per_case_identity_marker(result, _session(pol.FAST, "node-tar")) is result
    assert er.with_per_case_identity_marker(result, None) is result


def test_a_strict_and_a_2b_result_differ_only_by_the_marker() -> None:
    result = _result()
    strict = result.to_json_dict()
    fast = er.with_per_case_identity_marker(result, _session(FAST_2B)).to_json_dict()
    marker = fast["campaign"].pop("identity_checks")
    assert marker == PER_CASE_IDENTITY_MARKER and fast == strict


def _with_checks(checks: dict[str, Any]) -> dict[str, Any]:
    data = _result().to_json_dict()
    data["campaign"]["identity_checks"] = checks
    return data


def test_the_relaxed_check_covers_the_marker_only() -> None:
    from_json_dict(_with_checks(dict(PER_CASE_IDENTITY_MARKER)))  # accepted
    with pytest.raises(TargetResultError, match="interval 1"):
        from_json_dict(_with_checks({**PER_CASE_IDENTITY_MARKER, "interval": 200}))
    with pytest.raises(TargetResultError, match="total_checks"):
        from_json_dict(_with_checks({"interval": 1}))  # no marker: total_checks is required
    with pytest.raises(TargetResultError, match="total_checks"):
        from_json_dict(_with_checks({"interval": 200}))  # a real FAST record, unchanged rule
    from_json_dict(_with_checks({"interval": 200, "total_checks": 3}))  # still accepted


def test_the_summary_says_per_case_for_the_marker_only() -> None:
    marked = er.with_per_case_identity_marker(_result(), _session(FAST_2B))
    text = render_summary(marked, source_name="result.json", inputs_verified=True)
    assert "| 이미지 신원 확인 | 케이스마다 (FAST 간격 미적용, FAST 수용 측정 없음) |" in text
    assert "총 " not in text.split("이미지 신원 확인", 1)[1].split("\n", 1)[0]
    fast = dataclasses.replace(
        _result(),
        campaign=dataclasses.replace(
            _result().campaign, identity_checks={"interval": 200, "total_checks": 3}
        ),
    )
    text = render_summary(fast, source_name="result.json", inputs_verified=True)
    assert "캠페인 단위(시작·200건마다·끝), 총 3회" in text


def test_both_drivers_write_the_marker_after_the_identity_record() -> None:
    for module in (dce, oge):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        calls = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("with_identity_checks", "with_per_case_identity_marker")
        ]
        assert calls == ["with_identity_checks", "with_per_case_identity_marker"], module


def _folder(tmp: Path) -> Path:
    """The three layers of a 2b result folder: STRICT-shaped loop report and runtime record,
    a result.json with the marker (interval 1)."""
    tmp.mkdir()
    (tmp / "report.json").write_text(json.dumps({"decompress_campaign_schema": 1, "steps": []}))
    data = _with_checks(dict(PER_CASE_IDENTITY_MARKER))
    (tmp / "result.json").write_text(json.dumps(data))
    runtime = {
        "schema": cfs.RUNTIME_SCHEMA,
        "kind": "explore",
        "launches": [{"policy_applied": {"reuse_shared_images": {"applied": True}}}],
    }
    (tmp / "runtime.json").write_text(json.dumps(runtime))
    return tmp


@pytest.mark.parametrize("side", ["fast", "strict"])
def test_the_comparison_tool_refuses_a_2b_folder_on_either_side(side: str, tmp_path: Path) -> None:
    # Neither FAST acceptance evidence nor a STRICT baseline: exit 2 (InputError) both ways.
    with pytest.raises(cfs.InputError):
        cfs.check_fast_layers(_folder(tmp_path / "f"), side)
