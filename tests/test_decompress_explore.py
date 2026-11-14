"""decompress exploration driver: conversion, the not-a-PASS gate, wiring (no docker)."""

from __future__ import annotations

import base64
import json
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest
import scripts.decompress_explore as dx
import scripts.run_decompress_target as dt

from inodefence.target_result import RUN_ERROR, Provenance, Verdict, load_target_result

SPEC = "@xhmikosr/decompress@11.1.4"
ENGINE = Provenance(None, True)


def _step(index: int, *, termination: str = "success", violated: bool = False, frame_error=None):
    return {
        "index": index,
        "termination": termination,
        "oracle": {"C0": False, "C1": violated, "C2": violated},
        "frame_error": frame_error,
        "contract_violated": violated,
    }


def _report(steps: list[dict], inputs: list[dict] | None = None) -> dict[str, Any]:
    return {
        "label": "demo run",
        "config": {
            "mutation_policy": "m1-x",
            "search_policy": "p3-y",
            "random_seed": 1,
            "execution_budget": len(steps),
        },
        "steps": steps,
        "violation_inputs": inputs or [],
    }


def _convert(report: dict, ratio: float = 0.1):
    return dx.build_campaign_result(
        report,
        spec=SPEC,
        image_ref="img:1",
        image_id="sha256:" + "a" * 64,
        preparation=None,
        max_unjudged_ratio=ratio,
        seed=1,
        budget=len(report["steps"]),
        engine=ENGINE,
    )


def test_clean_campaign_is_pass_with_counts() -> None:
    result, tars, summary = _convert(_report([_step(i) for i in range(5)]))
    assert result.verdict is Verdict.PASS and tars == {}
    assert summary["unjudged_steps"] == 0 and summary["not_readable_as_pass"] is None
    assert summary["label"] == "exploratory demo run" and summary["qualification"] is False
    assert summary["mutation_policy"] == "m1-x"


def test_every_step_without_a_frame_is_error_not_pass() -> None:
    # The stale-worker shape: every frame call failed (exit 3 -> failed) with no stdout frame.
    steps = [_step(i, termination="failed", frame_error="no stdout frame") for i in range(5)]
    result, _, summary = _convert(_report(steps))
    assert result.verdict is Verdict.ERROR
    assert {c.outcome for c in result.cases} == {RUN_ERROR}
    assert "no step produced a worker frame" in summary["not_readable_as_pass"]


def test_unjudged_ratio_over_the_limit_is_error() -> None:
    steps = [_step(i) for i in range(8)] + [_step(8 + i, termination="timed_out") for i in range(2)]
    result, _, summary = _convert(_report(steps), ratio=0.1)
    assert result.verdict is Verdict.ERROR
    assert summary["unjudged_steps"] == 2 and summary["unjudged_ratio"] == 0.2


def test_unjudged_under_the_limit_is_counted_and_not_observed() -> None:
    steps = [_step(i) for i in range(9)] + [_step(9, termination="failed")]
    result, _, summary = _convert(_report(steps), ratio=0.2)
    assert result.verdict is Verdict.PASS
    failed = result.cases[-1]
    assert failed.outcome == "failed" and (failed.c1, failed.c2) == (None, None)
    assert summary["unjudged_steps"] == 1 and summary["not_readable_as_pass"] is None


def test_partial_frame_errors_with_judged_steps_are_not_a_gate() -> None:
    steps = [_step(i, frame_error="x" if i % 2 else None) for i in range(4)]
    result, _, summary = _convert(_report(steps))
    assert result.verdict is Verdict.PASS and summary["frame_error_steps"] == 2


def test_violation_keeps_its_input_and_writes_result(tmp_path: Path) -> None:
    archive = b"tar-bytes"
    item = {
        "index": 3,
        "case_id": "c",
        "tar_b64": base64.b64encode(archive).decode(),
        "tar_sha256": sha256(archive).hexdigest(),
    }
    steps = [_step(i, violated=(i == 3)) for i in range(5)]
    result, tars, summary = _convert(_report(steps, [item]))
    assert result.verdict is Verdict.FAIL and result.violating_cases == ("step-3",)
    path = dx.write_outputs(tmp_path, result, tars, summary)
    loaded = load_target_result(path)
    assert loaded.repro_inputs[0].tar_path == "inputs/step-3.tar"
    assert (tmp_path / "inputs" / "step-3.tar").read_bytes() == archive
    assert json.loads((tmp_path / "exploration.json").read_text())["violation_inputs"] == 1
    with pytest.raises(FileExistsError):
        dx.write_outputs(tmp_path, result, tars, summary)


def test_tampered_violation_input_is_refused() -> None:
    item = {"index": 0, "case_id": "c", "tar_b64": "eA==", "tar_sha256": "0" * 64}
    with pytest.raises(ValueError, match="SHA-256"):
        _convert(_report([_step(0, violated=True)], [item]))


def test_controller_gets_the_prepared_image_and_options(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs["env"])
        dx.controller_report_path(tmp_path, "rid").write_text("{}")
        return subprocess.CompletedProcess(cmd, 0)

    path = dx.run_controller(
        "sha256:img", tmp_path, "rid", seed=7, budget=9, mutation_policy=None,
        search_policy="p", runner=runner,
    )  # fmt: skip
    assert path.is_file()
    assert seen["EXPLORE_IMAGE"] == "sha256:img" and seen["DEMO_BUDGET"] == "9"
    assert seen["DEMO_POLICY"] == "p" and "DEMO_MUTATION_POLICY" not in seen


def test_dry_run_prepares_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dt, "ensure_image", lambda *a, **k: pytest.fail("no preparation"))
    assert dx.main(["--version", "decompress@latest", "--out", str(tmp_path), "--dry-run"]) == 0
    assert not list(tmp_path.iterdir())


def test_setup_refusal_is_exit_3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def refuse(*a: Any, **k: Any) -> dt.PreparedDecompress:
        raise ValueError("worker incompatible (decompress worker) in x: usage; rebuild it")

    monkeypatch.setattr(dt, "ensure_image", refuse)
    assert dx.main(["--version", SPEC, "--out", str(tmp_path)]) == 3


def test_ensure_image_refuses_a_stale_worker_even_for_an_existing_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.run_target as rt

    monkeypatch.setattr(rt, "image_id", lambda ref: "sha256:existing")  # reused, not rebuilt
    monkeypatch.setattr(
        dt.registry,
        "worker_check",
        lambda *a: {
            "ok": False,
            "reason": "worker frame failed (exit 3): usage",
            "worker_sha256": None,
        },
    )
    with pytest.raises(ValueError, match="worker incompatible.*rebuild it"):
        dt.ensure_image(SPEC)
    (cell,) = dt.ADAPTER.cells([SPEC], [])
    assert "rebuild it" in (dt.verify_existing(cell, "img") or "")


def test_selfdiscover_script_explore_branch_skips_target_build() -> None:
    text = dx.SCRIPT.read_text(encoding="utf-8")
    subprocess.run(["bash", "-n", str(dx.SCRIPT)], check=True)
    assert 'DECOMPRESS_IMAGE="${EXPLORE_IMAGE:-inodefence-decompress-selfdiscover:' in text
    assert 'if [ -z "$EXPLORE_IMAGE" ]; then' in text  # the role image is built only without it
    assert "$HOME/inodefence-explore/decompress" in text
    assert "decompress-effect-campaign" in text  # the unchanged controller mode


# ---- the TargetAdapter.explore hook ----


def _prepared(tmp_path: Path) -> Any:
    from scripts.run_target import PreparedTargetImage

    return PreparedTargetImage(
        target="decompress",
        requested="@xhmikosr/decompress@latest",
        version=SPEC,
        image_ref="inodefence-decompress:11.1.4-x",
        image_id="sha256:" + "b" * 64,
        exploratory=False,
    )


def _ok_check(*a: Any) -> dict[str, Any]:
    return {"ok": True, "reason": "decompress worker identify+frame ok", "worker_sha256": "d" * 64}


def test_hook_is_registered_on_the_adapter() -> None:
    assert dt.ADAPTER.explore is not None


def test_hook_refuses_a_stale_worker_before_any_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.run_target import ExploreOptions

    monkeypatch.setattr(
        dt.registry,
        "worker_check",
        lambda *a: {"ok": False, "reason": "frame failed (exit 3): usage", "worker_sha256": None},
    )
    monkeypatch.setattr(dx, "run_controller", lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(ValueError, match="worker incompatible.*rebuild it"):
        dx.explore(_prepared(tmp_path), ExploreOptions(5, 1, tmp_path))


def test_hook_runs_the_controller_and_writes_the_common_campaign_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.run_target import ExploreOptions

    archive = b"bytes"
    report = _report(
        [_step(i, violated=(i == 2)) for i in range(5)],
        [
            {
                "index": 2,
                "case_id": "c",
                "tar_b64": base64.b64encode(archive).decode(),
                "tar_sha256": sha256(archive).hexdigest(),
            }
        ],
    )
    seen: dict[str, Any] = {}

    def controller(image_id: str, evidence: Path, run_id: str, **kwargs: Any) -> Path:
        seen.update(image_id=image_id, run_id=run_id, **kwargs)
        path = evidence / "r.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report))
        return path

    monkeypatch.setattr(dt.registry, "worker_check", _ok_check)
    monkeypatch.setattr(dx, "run_controller", controller)
    monkeypatch.setattr(dx, "engine_provenance", lambda image: ENGINE)
    outcome = dt.ADAPTER.explore(_prepared(tmp_path), ExploreOptions(5, 7, tmp_path))  # type: ignore[misc]
    assert (outcome.verdict, outcome.runs, outcome.violations) == ("FAIL", 5, 1)
    assert seen["image_id"] == "sha256:" + "b" * 64 and seen["seed"] == 7 and seen["budget"] == 5
    result = load_target_result(outcome.result_path)
    assert result.campaign is not None and result.campaign.runs_to_first_violation == 3
    assert result.campaign.seed == 7 and result.campaign.budget == 5
    summary = json.loads((outcome.result_path.parent / "exploration.json").read_text())
    assert summary["requested"] == "@xhmikosr/decompress@latest"
    assert summary["worker_check"].startswith("decompress worker identify+frame ok")
    assert (outcome.result_path.parent / "summary.md").is_file()


def test_report_steps_carry_the_judged_flag() -> None:
    from tests.test_decompress_effect_campaign import _benign_run, _seeds

    from inodefence.decompress_effect_campaign import (
        DecompressEffectCampaignConfig,
        decompress_effect_campaign_report,
        run_decompress_effect_campaign,
    )

    config = DecompressEffectCampaignConfig(random_seed=3, execution_budget=5)
    result = run_decompress_effect_campaign(_seeds(), _benign_run, config)
    steps = decompress_effect_campaign_report(result, producer="t")["steps"]
    assert isinstance(steps, list) and all(s["judged"] is True for s in steps)


# ---- policies: only what the decompress loop implements, never silently another way ----


@pytest.mark.parametrize(
    ("search", "mutation", "why"),
    [
        (
            "effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1",  # S-u
            None,
            "boundary-attempt keys only for the P3 policies",
        ),
        ("effect-feedback-v2-or-violation-v1-uniform-mutation-v1", None, "adaptive"),  # P1
        (
            None,
            "uniform-generic-m1-state-aware-escape-hardlink-fixed-baseline-v1",
            "fixed-baseline",
        ),
        ("unretained-walk-v1-uniform-mutation-v1", None, "not implemented"),  # R arm
    ],
)
def test_unsupported_policy_is_refused_before_anything_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, search: Any, mutation: Any, why: str
) -> None:
    import types

    monkeypatch.setattr(dt.registry, "worker_check", lambda *a: pytest.fail("no worker check"))
    monkeypatch.setattr(dx, "run_controller", lambda *a, **k: pytest.fail("no controller run"))
    options = types.SimpleNamespace(
        budget=5,
        seed=1,
        out=tmp_path,
        image_tag_suffix="",
        search_policy=search,
        mutation_policy=mutation,
    )
    with pytest.raises(ValueError, match=f"does not implement.*{why}.*Supported:"):
        # ExploreOptions has no policy fields yet (the common declaration is pending); the hook
        # reads them by name, so a stand-in object carries them here.
        dx.explore(_prepared(tmp_path), cast(Any, options))
    assert not list(tmp_path.iterdir())


def test_defaults_and_supported_values_reach_the_controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert dx.check_policies(None, None) == (dx.DEFAULT_SEARCH_POLICY, dx.DEFAULT_MUTATION_POLICY)
    for search in dx.SUPPORTED_SEARCH_POLICIES:
        for mutation in dx.SUPPORTED_MUTATION_POLICIES:
            assert dx.check_policies(search, mutation) == (search, mutation)
    seen: dict[str, Any] = {}

    def controller(image_id: str, evidence: Path, run_id: str, **kwargs: Any) -> Path:
        seen.update(kwargs)
        raise RuntimeError("stop after recording")

    monkeypatch.setattr(dt.registry, "worker_check", _ok_check)
    monkeypatch.setattr(dx, "run_controller", controller)
    from scripts.run_target import ExploreOptions

    with pytest.raises(RuntimeError, match="stop after recording"):
        dx.explore(_prepared(tmp_path), ExploreOptions(5, 1, tmp_path))
    assert seen["search_policy"] == dx.DEFAULT_SEARCH_POLICY
    assert seen["mutation_policy"] == dx.DEFAULT_MUTATION_POLICY
