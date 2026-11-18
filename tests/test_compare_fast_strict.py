"""#536 FAST vs STRICT comparison tool on synthetic evidence (no target run, no Docker).

Fixtures follow design §7.1: F1 identical (exit 0), F2 a trajectory divergence at step 3
(exit 1, first divergence reported), F3 a deterministic replay mismatch (exit 1), and broken
FAST controls (skipped reset, stale image, injected false positives) that must exit 1.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from scripts import compare_fast_strict as cfs

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_demo import effect_campaign_report
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.execution_parity import (
    ResetVerification,
    extract_parity_subject,
    parity_subject_to_dict,
)
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance, ResourcePolicy
from inodefence.mutator import MutationPolicy

BUDGET = 8
#: The record the FAST end check adds (research/b-engine-fast-w5 identity_schedule.record()).
_FAST_RECORD = {
    "identity_checks": "campaign",
    "interval": 4,
    "cases_prepared": BUDGET,
    "start_checks": 1,
    "periodic_checks": 2,
    "end_checks": 1,
    "total_checks": 4,
    "per_case_checks_skipped": 6,
}


def _isolation(image: str = "a") -> IsolationProvenance:
    return IsolationProvenance(
        IsolationPolicy("sha256:" + image * 64, 1000, 1000, ResourcePolicy()),
        "docker-compatible",
        "27.0.0",
        "1.47",
        "linux",
        "amd64",
        "amd64",
    )


def _report(
    seed: int = 11, *, parity: bool = False, image: str = "a", reset_residual_at: int | None = None
) -> dict:
    config = EffectCampaignConfig(
        seed, BUDGET, EffectSearchPolicy.P1_EFFECT_RETENTION, MutationPolicy.LEGACY
    )
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    report = effect_campaign_report(result, "synthetic")
    report["timing"] = {"total_seconds": 12.0, "per_case": []}
    if parity:
        resets = tuple(
            ResetVerification(i, i == reset_residual_at, False) for i in range(len(result.steps))
        )
        subject = extract_parity_subject(
            result, label="x", isolation=_isolation(image), resets=resets
        )
        report["parity_subject"] = parity_subject_to_dict(subject)
    return report


def _product_records(folder: Path, *, fast: bool, name: str = "run", interval: int = 4) -> None:
    """What the product exploration writes beside the loop report: ``result.json`` (FAST adds
    ``campaign.identity_checks``) and the runtime record under ``runtime/`` (FAST: profile fast and
    ``policy_applied.identity_check_every`` on the explore launch)."""
    result = folder / "target-explore" / f"{name}-result"
    result.mkdir(parents=True, exist_ok=True)
    campaign: dict[str, object] = {"runs_executed": BUDGET}
    if fast:
        campaign[cfs.FAST_RECORD] = {**_FAST_RECORD, "interval": interval}
    (result / "result.json").write_text(
        json.dumps({"schema": cfs.RESULT_SCHEMA, "verdict": "PASS", "campaign": campaign}),
        encoding="utf-8",
    )
    launch: dict[str, object] = {"classification": "completed"}
    if fast:
        launch["policy_applied"] = {
            "identity_check_every": {
                "applied": True,
                "detail": f"INODEFENCE_IDENTITY_CHECK_EVERY={interval}",
            }
        }
    runtime = {
        "schema": cfs.RUNTIME_SCHEMA,
        "kind": "explore",
        "profile": "fast" if fast else "strict",
        "policy": {"identity_check_every": interval} if fast else {},
        "launches": [launch],
    }
    (folder / "runtime").mkdir(parents=True, exist_ok=True)
    (folder / "runtime" / f"{name}-20261118T000000Z.json").write_text(json.dumps(runtime))


def _write(folder: Path, report: dict, *, streaming: bool = True, name: str = "run") -> Path:
    """Write a campaign the way exploration does or run_exp0 does.

    streaming=True is the product exploration layout (``inodefence explore --out <folder>``):
    ``runtime/``, ``target-explore/<run>/`` with the engine report and its ``.steps.jsonl``, and
    ``target-explore/<run>-result/result.json`` (verdict PASS). streaming=False is a run_exp0
    cell: the report with its steps array, no result.json.
    """
    folder.mkdir(parents=True, exist_ok=True)
    report = copy.deepcopy(report)
    if folder.name == "f":  # test convention: folder "f" is the FAST run, "s" the STRICT run
        report[cfs.FAST_RECORD] = _FAST_RECORD
    base = f"inodefence-effect-explore-{name}"
    if not streaming:
        (folder / f"{base}.json").write_text(json.dumps(report), encoding="utf-8")
        return folder
    (folder / "runtime").mkdir(exist_ok=True)
    (folder / "runtime" / "explore-launcher-x.log").write_text("launcher output\n")
    run = folder / "target-explore" / name
    run.mkdir(parents=True)
    steps = report.pop("steps")
    (run / f"{base}.steps.jsonl").write_text(
        "".join(json.dumps(step, sort_keys=True) + "\n" for step in steps), encoding="utf-8"
    )
    (run / f"{base}.json").write_text(json.dumps(report), encoding="utf-8")
    _product_records(folder, fast=cfs.FAST_RECORD in report, name=name)
    return folder


def _run(capsys, *argv: str) -> tuple[int, dict]:
    code = cfs.main(list(argv))
    out = capsys.readouterr().out
    return code, json.loads(out)


def _trajectory(capsys, strict: Path, fast: Path, *extra: str, kind: str = "isolated"):
    return _run(
        capsys,
        "--mode",
        "trajectory",
        "--fast-kind",
        kind,
        "--strict",
        str(strict),
        "--fast",
        str(fast),
        *extra,
    )


# -- F1: identical except fields allowed to differ ---------------------------------------------


@pytest.mark.parametrize("streaming", [True, False])
def test_f1_identical_campaigns_are_equivalent(tmp_path: Path, capsys, streaming: bool) -> None:
    strict = _report()
    fast = copy.deepcopy(strict)
    fast["timing"] = {"total_seconds": 3.0, "per_case": [{"container_id": "other"}]}
    code, out = _trajectory(
        capsys,
        _write(tmp_path / "s", strict, streaming=streaming),  # STRICT: explore or run_exp0 layout
        _write(tmp_path / "f", fast),  # FAST exists only as a product exploration (three layers)
    )
    assert code == 0
    assert out["verdict"] == "equivalent"
    assert "first_divergence" not in out
    assert out["dimensions_judged"] == [
        "case_sequence",
        "step_input_hash",
        "oracle_and_feedback",
        "outcome_class",
        "corpus",
    ]
    assert "sufficient for an isolated FAST only" in out["scope"]


def test_f1_with_parity_subjects_judges_all_dimensions(tmp_path: Path, capsys) -> None:
    report = _report(parity=True)
    code, out = _trajectory(
        capsys,
        _write(tmp_path / "s", report),
        _write(tmp_path / "f", report),
        kind="shared",
    )
    assert code == 0 and out["verdict"] == "equivalent"
    assert "snapshots" in out["dimensions_judged"]
    assert "isolation_and_reset" in out["dimensions_judged"]
    assert "scope" not in out


# -- F2: trajectory divergence at step 3 --------------------------------------------------------


def test_f2_oracle_divergence_at_step_3(tmp_path: Path, capsys) -> None:
    strict = _report()
    fast = copy.deepcopy(strict)
    assert not any(fast["steps"][3]["oracle"].values())  # the fixture's step 3 has no violation
    fast["steps"][3]["oracle"]["C1"] = True
    code, out = _trajectory(
        capsys, _write(tmp_path / "s", strict), _write(tmp_path / "f", fast), "--stop-first"
    )
    assert code == 1 and out["verdict"] == "divergent"
    first = out["first_divergence"]
    assert first["dimension"] == "oracle_and_feedback"
    assert first["step_index"] == 3
    assert first["case_id"] == strict["steps"][3]["case_id"]
    assert (first["field"], first["strict"], first["fast"]) == ("oracle", "none", "C1")
    assert "campaigns" not in out  # --stop-first prints the first divergence only


def test_f2_case_sequence_divergence_at_step_3(tmp_path: Path, capsys) -> None:
    strict = _report()
    fast = copy.deepcopy(strict)
    fast["steps"][3]["case_id"] = "0" * 64
    code, out = _trajectory(capsys, _write(tmp_path / "s", strict), _write(tmp_path / "f", fast))
    assert code == 1
    first = out["first_divergence"]
    assert (first["dimension"], first["step_index"], first["field"]) == (
        "case_sequence",
        3,
        "case_id",
    )
    counts = out["campaigns"][0]["divergences_per_dimension"]
    assert counts["case_sequence"] == 1 and counts["step_input_hash"] == 1


@pytest.mark.parametrize(
    ("mutate", "dimension"),
    [
        (lambda s: s.__setitem__("archive_format", "other-format"), "step_input_hash"),
        (lambda s: s["feedback"].__setitem__("new_effect_keys", [{"k": 1}]), "oracle_and_feedback"),
        (lambda s: s.__setitem__("outcome", "run_error"), "outcome_class"),
        (lambda s: s["feedback"].__setitem__("retained", not s["feedback"]["retained"]), "corpus"),
    ],
)
def test_each_report_dimension_catches_its_difference(
    tmp_path: Path, capsys, mutate, dimension: str
) -> None:
    strict = _report()
    fast = copy.deepcopy(strict)
    mutate(fast["steps"][5])
    code, out = _trajectory(capsys, _write(tmp_path / "s", strict), _write(tmp_path / "f", fast))
    assert code == 1
    assert (out["first_divergence"]["dimension"], out["first_divergence"]["step_index"]) == (
        dimension,
        5,
    )


def test_incomplete_fast_side_diverges_where_it_stops(tmp_path: Path, capsys) -> None:
    strict = _report()
    fast = copy.deepcopy(strict)
    fast["steps"] = fast["steps"][:5]
    code, out = _trajectory(capsys, _write(tmp_path / "s", strict), _write(tmp_path / "f", fast))
    assert code == 1
    first = out["first_divergence"]
    assert (first["dimension"], first["step_index"]) == ("case_sequence", 5)
    assert (first["strict"], first["fast"]) == (BUDGET, 5)


# -- option-1 negative control (design §8.1): target image swapped mid-campaign ----------------


def _image_swap_pair() -> tuple[dict, dict]:
    """STRICT on a violating release throughout; FAST swapped to a fixed release from step 4,
    so the violating inputs after the swap are judged differently (7.5.2 -> 7.5.11 shape)."""
    strict = _report()
    for step in strict["steps"][4:]:
        step["oracle"]["C1"] = True  # the violating release judges these inputs as C1
    fast = copy.deepcopy(strict)
    for step in fast["steps"][4:]:
        step["oracle"]["C1"] = False  # after the swap the fixed release does not violate
    return strict, fast


def test_image_swap_without_end_check_is_divergent(tmp_path: Path, capsys) -> None:
    """§8.1 (a): end check disabled -> the trajectory comparison itself must catch the swap."""
    strict, fast = _image_swap_pair()
    code, out = _trajectory(capsys, _write(tmp_path / "s", strict), _write(tmp_path / "f", fast))
    assert code == 1
    first = out["first_divergence"]
    assert (first["dimension"], first["step_index"], first["strict"], first["fast"]) == (
        "oracle_and_feedback",
        4,
        "C1",
        "none",
    )


def _failed_end_check(folder: Path, shape: str) -> None:
    """What a failed FAST end check leaves (research/b-engine-fast-w5 ba57db8), per target:
    the product driver raises RuntimeError -> ERROR, exit 2, no result.json in every case."""
    for result in folder.glob("target-explore/*-result"):
        for item in result.iterdir():
            item.unlink()
        result.rmdir()
    run = folder / "target-explore" / "run"
    if shape == "node-tar":  # raises inside the loop: live state failed, no engine report
        for report in run.glob("*.json"):
            report.unlink()
        (run / "live").mkdir()
        (run / "live" / "progress.json").write_text(json.dumps({"state": "failed"}))
    elif shape == "python-tarfile":  # raises before the report is written
        for report in run.glob("*.json"):
            report.unlink()
    elif shape == "decompress/oras-go":  # the controller writes an aborted report
        (run / "inodefence-decompress-campaign-run.json").write_text(
            json.dumps({"decompress_campaign_schema": 1, "aborted": {"reason": "identity changed"}})
        )
    else:
        raise AssertionError(shape)


@pytest.mark.parametrize("shape", ["node-tar", "python-tarfile", "decompress/oras-go"])
def test_image_swap_with_end_check_is_an_invalid_run(tmp_path: Path, capsys, shape: str) -> None:
    """§8.1 (b): end check enabled -> the run fails closed and is never compared (exit 2)."""
    strict, fast = _image_swap_pair()
    fast_dir = _write(tmp_path / "f", fast)
    _failed_end_check(fast_dir, shape)
    code, out = _trajectory(capsys, _write(tmp_path / "s", strict), fast_dir)
    assert code == 2 and out["verdict"] == "invalid"
    assert "no result.json" in out["error"]
    if shape == "node-tar":
        assert "live state failed" in out["error"]
    if shape == "decompress/oras-go":
        assert "report aborted" in out["error"]


def test_a_result_with_verdict_error_is_an_invalid_run(tmp_path: Path, capsys) -> None:
    report = _report()
    fast_dir = _write(tmp_path / "f", report)
    (fast_dir / "target-explore" / "run-result" / "result.json").write_text(
        json.dumps({"schema": cfs.RESULT_SCHEMA, "verdict": "ERROR"})
    )
    code, out = _trajectory(capsys, _write(tmp_path / "s", report), fast_dir)
    assert code == 2 and out["verdict"] == "invalid" and "verdict ERROR" in out["error"]


# -- state-sharing FAST controls (must exit 1; need parity_subject) ------------------------------


def test_broken_fast_skipped_reset_is_divergent(tmp_path: Path, capsys) -> None:
    code, out = _trajectory(
        capsys,
        _write(tmp_path / "s", _report(parity=True)),
        _write(tmp_path / "f", _report(parity=True, reset_residual_at=2)),
        kind="shared",
    )
    assert code == 1
    first = out["first_divergence"]
    assert (first["dimension"], first["step_index"]) == ("isolation_and_reset", 2)


def test_broken_fast_stale_image_is_divergent(tmp_path: Path, capsys) -> None:
    code, out = _trajectory(
        capsys,
        _write(tmp_path / "s", _report(parity=True, image="a")),
        _write(tmp_path / "f", _report(parity=True, image="b")),
        kind="shared",
    )
    assert code == 1
    first = out["first_divergence"]
    assert first["dimension"] == "isolation_and_reset" and first["step_index"] is None
    assert "image_id" in first["field"]


def test_broken_fast_snapshot_difference_is_divergent(tmp_path: Path, capsys) -> None:
    strict = _report(parity=True)
    fast = copy.deepcopy(strict)
    groups = fast["parity_subject"]["steps"][4]["after"]["identity_groups"]
    groups.append(["leaked/a", "leaked/b"])
    code, out = _trajectory(
        capsys, _write(tmp_path / "s", strict), _write(tmp_path / "f", fast), kind="shared"
    )
    assert code == 1
    assert (out["first_divergence"]["dimension"], out["first_divergence"]["step_index"]) == (
        "snapshots",
        4,
    )


# -- input errors (exit 2) ----------------------------------------------------------------------


def test_shared_fast_without_parity_subject_is_input_insufficient(tmp_path: Path, capsys) -> None:
    report = _report()
    code, out = _trajectory(
        capsys, _write(tmp_path / "s", report), _write(tmp_path / "f", report), kind="shared"
    )
    assert code == 2 and out["verdict"] == "input_error"
    assert "parity_subject" in out["error"]


def test_missing_fast_kind_is_an_input_error(tmp_path: Path, capsys) -> None:
    report = _report()
    code, out = _run(
        capsys,
        "--mode",
        "trajectory",
        "--strict",
        str(_write(tmp_path / "s", report)),
        "--fast",
        str(_write(tmp_path / "f", report)),
    )
    assert code == 2 and "--fast-kind" in out["error"]


def test_folder_without_reports_is_an_input_error(tmp_path: Path, capsys) -> None:
    (tmp_path / "empty").mkdir()
    code, out = _trajectory(capsys, _write(tmp_path / "s", _report()), tmp_path / "empty")
    assert code == 2 and "no campaign report" in out["error"]


def test_unpaired_reports_are_an_input_error(tmp_path: Path, capsys) -> None:
    report = _report()
    strict = _write(tmp_path / "s", report, name="a")
    _write(strict, report, name="b")
    fast = _write(tmp_path / "f", report, name="a")
    _write(fast, report, name="c")
    code, out = _trajectory(capsys, strict, fast)
    assert code == 2 and "without a partner" in out["error"]


def test_unknown_option_exits_2() -> None:
    assert cfs.main(["--mode", "trajectory", "--bogus"]) == 2


# -- one STRICT and one FAST run of the same campaign (design §8.3, QA) -------------------------


def test_two_strict_runs_are_refused_not_equivalent(tmp_path: Path, capsys) -> None:
    report = _report()
    code, out = _trajectory(capsys, _write(tmp_path / "s", report), _write(tmp_path / "s2", report))
    assert code == 2 and out["verdict"] == "input_error"
    assert "not a FAST run" in out["error"]


def test_a_strict_side_carrying_the_fast_record_is_refused(tmp_path: Path, capsys) -> None:
    report = _report()
    code, out = _trajectory(capsys, _write(tmp_path / "f", report), _write(tmp_path / "f2", report))
    # the strict folder ("f") carries identity_checks
    assert code == 2 and "it is a FAST run" in out["error"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("config", {"random_seed": 99}),
        ("image_id", "sha256:" + "f" * 64),
        ("node_tar_version", "7.5.11"),
        ("vocabulary_mode", "other"),
        ("engine_commit", "0" * 40),
        ("initial_case_ids", ["x"]),
    ],
)
def test_runs_of_different_campaigns_are_refused(
    tmp_path: Path, capsys, field: str, value: object
) -> None:
    strict = _report()
    fast = copy.deepcopy(strict)
    fast[field] = value
    code, out = _trajectory(capsys, _write(tmp_path / "s", strict), _write(tmp_path / "f", fast))
    assert code == 2 and "not the same campaign" in out["error"] and field in out["error"]


def _remove(folder: Path, pattern: str) -> None:
    for path in folder.rglob(pattern):
        path.unlink()


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        (lambda f: _remove(f, "result.json"), "no result.json"),
        (lambda f: _remove(f, "*T000000Z.json"), "no runtime record"),
        (lambda f: _product_records(f, fast=True, interval=7), "disagree on the probe interval"),
        (lambda f: _product_records(f, fast=False), "STRICT shape"),
    ],
)
def test_fast_needs_three_layers_agreeing_on_the_interval(
    tmp_path: Path, capsys, damage, message: str
) -> None:
    """Design §8.4: FAST is read from the loop report, result.json and the runtime record, which
    must all record it with the same interval; any missing layer, STRICT-shaped layer or
    disagreement is an input error, never a comparison."""
    report = _report()
    fast_dir = _write(tmp_path / "f", report)
    damage(fast_dir)
    if message == "no result.json":  # a product folder without result.json is an invalid run
        code, out = _trajectory(capsys, _write(tmp_path / "s", report), fast_dir)
        assert code == 2 and out["verdict"] == "invalid"
        return
    code, out = _trajectory(capsys, _write(tmp_path / "s", report), fast_dir)
    assert code == 2 and out["verdict"] == "input_error" and message in out["error"]


def test_strict_side_with_a_fast_runtime_record_is_refused(tmp_path: Path, capsys) -> None:
    report = _report()
    strict_dir = _write(tmp_path / "s", report)
    _product_records(strict_dir, fast=True)  # the run claimed STRICT but ran FAST
    code, out = _trajectory(capsys, strict_dir, _write(tmp_path / "f", report))
    assert code == 2 and "strict:" in out["error"] and "record a FAST run" in out["error"]


def test_the_agreed_interval_is_reported(tmp_path: Path, capsys) -> None:
    report = _report()
    code, out = _trajectory(capsys, _write(tmp_path / "s", report), _write(tmp_path / "f", report))
    assert code == 0 and out["fast_interval"] == 4


@pytest.mark.parametrize("state", ["stopped", "running", None])
def test_a_progress_state_other_than_finished_is_invalid(
    tmp_path: Path, capsys, state: str | None
) -> None:
    report = _report()
    fast_dir = _write(tmp_path / "f", report)
    live = fast_dir / "target-explore" / "run" / "live"
    live.mkdir()
    body = "{not json" if state is None else json.dumps({"state": state})
    (live / "progress.json").write_text(body)
    code, out = _trajectory(capsys, _write(tmp_path / "s", report), fast_dir)
    assert code == 2 and out["verdict"] == "invalid"
    assert f"live state {state or 'unreadable'}" in out["error"]


def test_a_finished_progress_state_is_fine(tmp_path: Path, capsys) -> None:
    report = _report()
    fast_dir = _write(tmp_path / "f", report)
    (fast_dir / "target-explore" / "run" / "live").mkdir()
    (fast_dir / "target-explore" / "run" / "live" / "progress.json").write_text(
        json.dumps({"state": "finished"})
    )
    code, _ = _trajectory(capsys, _write(tmp_path / "s", report), fast_dir)
    assert code == 0


# -- descriptive identity partition -------------------------------------------------------------


def test_identity_partition_groups_paths_sharing_an_inode() -> None:
    def path(name: str, ino: int) -> dict:
        return {"path": name, "after": {"status": "present", "st_dev": 1, "st_ino": ino}}

    step = {
        "trace": {
            "effect_events": [
                {"paths": [path("x/a", 7), path("outside/s", 7)]},
                {"paths": [path("x/b", 9), {"path": "x/c", "after": None}]},
            ]
        }
    }
    assert cfs._identity_partition(step) == [["outside/s", "x/a"]]


# -- replay mode (F3 and the TOST rule) ---------------------------------------------------------


def _replays(folder: Path, counts: dict[str, int], n: int) -> Path:
    """STRICT ("s"): ``inodefence replay`` records. FAST ("f"): verdict lines from FAST campaigns
    on the pinned case set, marked ``"profile": "fast"`` (replay always runs STRICT)."""
    folder.mkdir(parents=True, exist_ok=True)
    if folder.name == "f":
        lines = [
            {"input_id": case, "run_index": i, "violated": i < k, "profile": "fast"}
            for case, k in counts.items()
            for i in range(n)
        ]
        (folder / "fast.verdicts.jsonl").write_text(
            "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
        )
        return folder
    for case, k in counts.items():
        rounds = [{"round": i + 1, "c0": i < k, "c1": False, "c2": False} for i in range(n)]
        record = {
            "schema": cfs.REPLAY_SCHEMA,
            "original": {"case_id": case, "tar_sha256": "t" + case},
            "rounds": rounds,
        }
        sub = folder / f"{case}.replay"
        sub.mkdir()
        (sub / "replay.json").write_text(json.dumps(record), encoding="utf-8")
    return folder


def _inputs(path: Path, cases: list[str]) -> Path:
    path.write_text(json.dumps([{"input_id": f"in-{c}", "case": c} for c in cases]))
    return path


def _replay(capsys, tmp_path: Path, strict: dict[str, int], fast: dict[str, int], n: int = 10):
    return _run(
        capsys,
        "--mode",
        "replay",
        "--strict",
        str(_replays(tmp_path / "s", strict, n)),
        "--fast",
        str(_replays(tmp_path / "f", fast, n)),
        "--inputs",
        str(_inputs(tmp_path / "inputs.json", sorted(strict))),
        "--n",
        str(n),
    )


def test_f3_deterministic_input_mismatch_is_non_equivalent(tmp_path: Path, capsys) -> None:
    code, out = _replay(capsys, tmp_path, {"a": 0, "b": 10}, {"a": 3, "b": 10})
    assert code == 1 and out["verdict"] == "non_equivalent"
    row = next(r for r in out["per_input"] if r["case"] == "a")
    assert (row["k_strict"], row["k_fast"], row["rule"], row["pass"]) == (
        0,
        3,
        "(i)deterministic",
        False,
    )
    assert out["tost"] is None


def test_deterministic_inputs_with_equal_counts_are_equivalent(tmp_path: Path, capsys) -> None:
    code, out = _replay(capsys, tmp_path, {"a": 0, "b": 10}, {"a": 0, "b": 10})
    assert code == 0 and out["verdict"] == "equivalent"


def test_stochastic_inputs_pass_tost_when_rates_match(tmp_path: Path, capsys) -> None:
    strict = {c: k for c, k in zip("abcdef", (3, 5, 7, 4, 6, 2), strict=True)}
    fast = {c: k for c, k in zip("abcdef", (4, 5, 6, 4, 6, 2), strict=True)}
    code, out = _replay(capsys, tmp_path, strict, fast)
    assert code == 0
    assert out["tost"]["pass"] is True and out["tost"]["inputs"] == 6
    assert all(r["rule"] == "(ii)stochastic-pooled" for r in out["per_input"])


def test_broken_fast_raising_stochastic_rates_fails_tost(tmp_path: Path, capsys) -> None:
    strict = {c: k for c, k in zip("abcdef", (3, 5, 7, 4, 6, 2), strict=True)}
    fast = {c: min(10, k + 4) for c, k in strict.items()}
    code, out = _replay(capsys, tmp_path, strict, fast)
    assert code == 1 and out["tost"]["pass"] is False


def test_fewer_than_five_stochastic_inputs_need_twenty_rounds(tmp_path: Path, capsys) -> None:
    code, out = _replay(capsys, tmp_path, {"a": 3, "b": 0}, {"a": 3, "b": 0})
    assert code == 2 and "20 needed" in out["error"]
    code, out = _replay(capsys, tmp_path / "n20", {"a": 6, "b": 0}, {"a": 6, "b": 0}, n=20)
    assert code == 0 and out["tost"]["n"] == 20


def test_rounds_without_a_verdict_make_the_count_short(tmp_path: Path, capsys) -> None:
    strict = _replays(tmp_path / "s", {"a": 0}, 10)
    record_path = strict / "a.replay" / "replay.json"
    record = json.loads(record_path.read_text())
    record["rounds"][0].update(c0=None, c1=None, c2=None)
    record_path.write_text(json.dumps(record))
    code, out = _run(
        capsys,
        "--mode",
        "replay",
        "--strict",
        str(strict),
        "--fast",
        str(_replays(tmp_path / "f", {"a": 0}, 10)),
        "--inputs",
        str(_inputs(tmp_path / "inputs.json", ["a"])),
    )
    assert code == 2 and "9 judged rounds" in out["error"]


def _verdict_lines(folder: Path, profile: str | None) -> Path:
    folder.mkdir()
    mark = {} if profile is None else {"profile": profile}
    lines = [{"input_id": "x", "run_index": i, "violated": False, **mark} for i in range(10)]
    (folder / "set.verdicts.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))
    return folder


def _replay_dirs(capsys, tmp_path: Path, strict: Path, fast: Path):  # type: ignore[no-untyped-def]
    return _run(
        capsys,
        "--mode",
        "replay",
        "--strict",
        str(strict),
        "--fast",
        str(fast),
        "--inputs",
        str(_inputs(tmp_path / "inputs.json", ["x"])),
    )


@pytest.mark.parametrize("strict_profile", [None, "strict"])
def test_verdict_lines_are_read_by_input_id(tmp_path: Path, capsys, strict_profile) -> None:
    code, out = _replay_dirs(
        capsys,
        tmp_path,
        _verdict_lines(tmp_path / "s", strict_profile),
        _verdict_lines(tmp_path / "f", "fast"),
    )
    assert code == 0 and out["per_input"][0]["k_fast"] == 0


@pytest.mark.parametrize("fast_profile", [None, "strict"])
def test_fast_side_needs_lines_marked_fast(tmp_path: Path, capsys, fast_profile) -> None:
    code, out = _replay_dirs(
        capsys,
        tmp_path,
        _verdict_lines(tmp_path / "s", None),
        _verdict_lines(tmp_path / "f", fast_profile),
    )
    assert code == 2 and 'not marked "profile": "fast"' in out["error"]


def test_strict_side_refuses_lines_marked_fast(tmp_path: Path, capsys) -> None:
    code, out = _replay_dirs(
        capsys,
        tmp_path,
        _verdict_lines(tmp_path / "s", "fast"),
        _verdict_lines(tmp_path / "f", "fast"),
    )
    assert code == 2 and "STRICT side line marked profile 'fast'" in out["error"]


def test_a_replay_record_on_the_fast_side_is_refused(tmp_path: Path, capsys) -> None:
    """`inodefence replay` always runs STRICT: two replay folders would compare STRICT with
    STRICT and pass trivially (QA)."""
    strict = _replays(tmp_path / "s", {"x": 0}, 10)
    fast = _replays(tmp_path / "s2", {"x": 0}, 10)  # replay.json records, used as the FAST side
    code, out = _replay_dirs(capsys, tmp_path, strict, fast)
    assert code == 2 and "always runs STRICT" in out["error"]


# -- statistics helpers -------------------------------------------------------------------------


def test_fisher_exact_matches_a_known_value() -> None:
    # [[3, 1], [1, 3]]: two-sided p = 34/70 (the classic tea-tasting table).
    assert cfs.fisher_exact(3, 1, 1, 3) == pytest.approx(34 / 70)
    assert cfs.fisher_exact(5, 5, 5, 5) == pytest.approx(1.0)


def test_holm_adjustment() -> None:
    assert cfs.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_tost_zero_difference_passes_and_large_difference_fails() -> None:
    assert cfs.tost([3, 5, 7, 4, 6], [3, 5, 7, 4, 6], 10, 0.10, 0.05)["pass"] is True
    assert cfs.tost([1, 1, 1, 1, 1], [5, 5, 5, 5, 5], 10, 0.10, 0.05)["pass"] is False


# -- decompress / oras-go reduced reader (design §8.3) -----------------------------------------


def _reduced_reports(folder: Path, schema: str, runs: list[dict[str, int]], *, fast: bool) -> Path:
    """Campaign reports of the pinned case set: one report per campaign, each step one run of a
    case; ``runs`` maps case -> 1 (violated) / 0 (not) / -1 (extractor did not finish)."""
    folder.mkdir(parents=True, exist_ok=True)
    for number, campaign in enumerate(runs):
        steps = [
            {
                "index": index,
                "case_id": case,
                "termination": "failed" if value < 0 else "success",
                "oracle": {"C0": value > 0, "C1": False, "C2": False},
                "new_attempt_keys": 1,
            }
            for index, (case, value) in enumerate(campaign.items())
        ]
        report: dict[str, object] = {schema: 1, "steps": steps, "config": {"random_seed": number}}
        if fast:
            report[cfs.FAST_RECORD] = _FAST_RECORD
        (folder / f"campaign-{number}.json").write_text(json.dumps(report))
    if fast:
        for number in range(len(runs)):
            _product_records(folder, fast=True, name=f"c{number}")
    return folder


def _reduced_replay(capsys, tmp_path: Path, strict: Path, fast: Path, cases: list[str]):  # type: ignore[no-untyped-def]
    (tmp_path / "inputs.json").write_text(
        json.dumps([{"input_id": f"in-{c}", "case": c} for c in cases])
    )
    return _run(
        capsys,
        "--mode",
        "replay",
        "--strict",
        str(strict),
        "--fast",
        str(fast),
        "--inputs",
        str(tmp_path / "inputs.json"),
    )


@pytest.mark.parametrize("schema", list(cfs.REDUCED_REPORT_SCHEMAS))
def test_reduced_reports_feed_replay_counts(tmp_path: Path, capsys, schema: str) -> None:
    strict = _reduced_reports(tmp_path / "s", schema, [{"x": 0, "y": 1}] * 10, fast=False)
    fast_runs = [{"x": 1 if i < 3 else 0, "y": 1} for i in range(10)]
    fast = _reduced_reports(tmp_path / "f", schema, fast_runs, fast=True)
    code, out = _reduced_replay(capsys, tmp_path, strict, fast, ["x", "y"])
    assert code == 1  # x: STRICT k=0, FAST k=3 -> rule (i) mismatch
    rows = {row["input_id"]: row for row in out["per_input"]}
    assert (rows["in-x"]["k_strict"], rows["in-x"]["k_fast"], rows["in-x"]["pass"]) == (0, 3, False)
    assert (rows["in-y"]["k_strict"], rows["in-y"]["k_fast"], rows["in-y"]["pass"]) == (
        10,
        10,
        True,
    )


def test_reduced_reports_need_one_strict_and_one_fast_side(tmp_path: Path, capsys) -> None:
    schema = "decompress_campaign_schema"
    strict = _reduced_reports(tmp_path / "s", schema, [{"x": 0}] * 10, fast=False)
    not_fast = _reduced_reports(tmp_path / "f", schema, [{"x": 0}] * 10, fast=False)
    code, out = _reduced_replay(capsys, tmp_path, strict, not_fast, ["x"])
    assert code == 2 and "FAST run" in out["error"]


def test_unfinished_reduced_steps_have_no_verdict(tmp_path: Path, capsys) -> None:
    schema = "oras_go_campaign_schema"
    runs = [{"x": 0}] * 10
    strict = _reduced_reports(tmp_path / "s", schema, runs, fast=False)
    fast = _reduced_reports(tmp_path / "f", schema, [{"x": -1}] + runs[1:], fast=True)
    code, out = _reduced_replay(capsys, tmp_path, strict, fast, ["x"])
    assert code == 2 and "9 judged rounds" in out["error"]


def test_an_aborted_reduced_report_makes_the_replay_side_invalid(tmp_path: Path, capsys) -> None:
    schema = "decompress_campaign_schema"
    strict = _reduced_reports(tmp_path / "s", schema, [{"x": 0}] * 10, fast=False)
    fast = _reduced_reports(tmp_path / "f", schema, [{"x": 0}] * 10, fast=True)
    (fast / "campaign-aborted.json").write_text(
        json.dumps({schema: 1, "aborted": {"reason": "identity changed"}})
    )
    code, out = _reduced_replay(capsys, tmp_path, strict, fast, ["x"])
    assert code == 2 and out["verdict"] == "invalid" and "report aborted" in out["error"]
