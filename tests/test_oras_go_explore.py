"""oras_go_explore: the oras-go explore hook and its driver wiring (no docker)."""

from __future__ import annotations

import base64
import json
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import scripts.node_tar_explore as nte
import scripts.oras_go_explore as oge
import scripts.run_oras_go_target as rog
import scripts.run_target as rt
import scripts.run_target_explore as rte
from scripts.run_target import ExploreOptions, PreparedTargetImage

from inodefence.target_result import Verdict, load_target_result

TAR = b"bytes of a violating oras-go case"
IMAGE_ID = "sha256:" + "c" * 64


def _prepared(version: str = "2.7.0") -> PreparedTargetImage:
    return PreparedTargetImage(
        "oras-go", "latest", version, f"inodefence-oras-go-registry:{version}", IMAGE_ID, True
    )


def _report(*, runs: int, violating: int | None, image_id: str = IMAGE_ID) -> dict[str, Any]:
    records = [
        {"run_index": i, "outcome": "success", "c0": False, "c1": False, "c2": False}
        for i in range(runs)
    ]
    inputs: list[dict[str, Any]] = []
    if violating is not None:
        records[violating] = {
            "run_index": violating,
            "outcome": "rejected",
            "c0": False,
            "c1": True,
            "c2": True,
        }
        inputs.append(
            {
                "run_index": violating,
                "tar_sha256": sha256(TAR).hexdigest(),
                "tar_b64": base64.b64encode(TAR).decode(),
            }
        )
    return {
        "oras_go_campaign_schema": 1,
        "label": "demo run",
        "config": {"mutation_policy": "uniform-generic-m1-state-aware-escape-hardlink-v1"},
        "image_id": image_id,
        "case_records": records,
        "violation_inputs": inputs,
    }


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nte, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )


class FakeScript:
    """Stands in for ``bash local_oras_go_selfdiscover.sh``: records env, writes a report."""

    def __init__(self, report: dict[str, Any] | None, returncode: int = 0) -> None:
        self.report = report
        self.returncode = returncode
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(self, cmd: list[str], *, env: dict[str, str], cwd: str) -> Any:
        self.calls.append((cmd, env))
        if self.report is not None:
            path = Path(env["INODEFENCE_EVIDENCE_DIR"])
            path.mkdir(parents=True, exist_ok=True)
            report_file = path / f"inodefence-oras-go-selfdiscover-{env['RUN_ID']}.json"
            report_file.write_text(json.dumps(self.report), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, self.returncode)


def _explore(tmp_path: Path, script: FakeScript, monkeypatch: pytest.MonkeyPatch, budget: int = 5):
    real = oge.run_controller
    monkeypatch.setattr(
        oge, "run_controller", lambda prepared, **kw: real(prepared, **kw, runner=script)
    )
    return oge.explore(_prepared(), ExploreOptions(budget=budget, seed=7, out=tmp_path))


def test_hook_is_registered_on_the_oras_go_adapter() -> None:
    assert rog.ADAPTER.explore is not None
    assert rt.load_adapter("oras-go").explore is rog.ADAPTER.explore


def test_violating_run_writes_oras_go_campaign_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = FakeScript(_report(runs=5, violating=3))
    outcome = _explore(tmp_path, script, monkeypatch)
    assert (outcome.verdict, outcome.runs, outcome.violations) == ("FAIL", 5, 1)
    result = load_target_result(outcome.result_path)
    assert result.target == "oras-go" and result.verdict is Verdict.FAIL
    assert result.axes.target_version == "2.7.0"
    assert result.violating_cases == ("step-3",)
    assert result.campaign is not None and result.campaign.runs_to_first_violation == 4
    assert (result.campaign.seed, result.campaign.budget) == (7, 5)
    assert result.provenance.image_id == IMAGE_ID
    assert (outcome.result_path.parent / "inputs" / "step-3.tar").read_bytes() == TAR
    assert (outcome.result_path.parent / "summary.md").is_file()
    ((cmd, env),) = script.calls
    assert cmd[-1].endswith("local_oras_go_selfdiscover.sh")
    assert env["EXPLORE_IMAGE"] == "inodefence-oras-go-registry:2.7.0"
    assert (env["DEMO_BUDGET"], env["DEMO_SEED"]) == ("5", "7")
    assert env["RUN_ID"] == "oras-go-2.7.0-7-5"


def test_clean_run_passes_with_no_saved_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome = _explore(tmp_path, FakeScript(_report(runs=4, violating=None)), monkeypatch, 4)
    assert (outcome.verdict, outcome.runs, outcome.violations) == ("PASS", 4, 0)
    assert not any((outcome.result_path.parent / "inputs").iterdir())


@pytest.mark.parametrize(
    ("report", "message"),
    [
        ({"aborted": {"reason": "docker stalled"}}, "campaign aborted: docker stalled"),
        (_report(runs=5, violating=None, image_id="sha256:" + "d" * 64), "campaign ran image"),
        ({"image_id": IMAGE_ID, "steps": []}, "no case_records"),
    ],
)
def test_unusable_report_writes_no_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, report: dict[str, Any], message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        _explore(tmp_path, FakeScript(report), monkeypatch)
    assert not list(tmp_path.rglob("result.json"))


def test_failed_controller_run_writes_no_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RuntimeError, match="controller run failed"):
        _explore(tmp_path, FakeScript(_report(runs=5, violating=1), returncode=1), monkeypatch)
    assert not list(tmp_path.rglob("result.json"))


def test_tampered_violation_input_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(runs=5, violating=2)
    report["violation_inputs"][0]["tar_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        _explore(tmp_path, FakeScript(report), monkeypatch)


def test_budget_below_seed_count_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="budget must be"):
        oge.explore(_prepared(), ExploreOptions(budget=oge.MIN_BUDGET - 1, seed=1, out=tmp_path))


def test_driver_prepares_then_calls_the_oras_go_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, Any] = {}

    def prepare(adapter, target, spec, *, image_tag_suffix):  # type: ignore[no-untyped-def]
        seen["prepare"] = (target, spec, image_tag_suffix)
        return _prepared()

    def hook(prepared, options):  # type: ignore[no-untyped-def]
        seen["hook"] = (prepared.target, options.budget, options.seed)
        return rt.ExploreOutcome(tmp_path / "result.json", "PASS", options.budget, 0)

    monkeypatch.setattr(rte, "prepare_target_image", prepare)
    monkeypatch.setattr(oge, "explore", hook)
    argv = ["--target", "oras-go", "--version", "latest", "--auto-prepare", "--budget", "6"]
    rte.main([*argv, "--seed", "9", "--out", str(tmp_path)])
    assert seen == {"prepare": ("oras-go", "latest", ""), "hook": ("oras-go", 6, 9)}
