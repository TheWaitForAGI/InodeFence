"""G1 smoke driver: planning, dry-run and summarize-only (no Docker)."""

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.run_effect_demo import synthetic_demo_report
from scripts.run_g1_smoke import (
    LABELS,
    SENTINEL_WIRING,
    G1Plan,
    cell_paths,
    g1_verdict,
    main,
    summarize_output,
    vocabulary_equality,
)

from inodefence.evaluation.rds import RdsArm, RVariant, VocabularyMode, arm_search_policy
from inodefence.mutator import MutationPolicy


def _plan(plan: str = "completion", seeds=(9001,), budget: int = 6) -> G1Plan:
    return G1Plan(
        plan,
        "7.5.2",
        tuple(seeds),
        budget,
        VocabularyMode.OBSERVED_NAMES,
        RVariant.WALK,
        None,
        None,
    )


def test_completion_plan_is_three_equal_vocabulary_cells() -> None:
    cells = _plan().cells()
    assert [cell.arm.label for cell in cells] == ["R", "D", "S-u"]
    assert {cell.arm.mutation for cell in cells} == {
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE.value
    }
    assert [cell.arm.search for cell in cells] == [
        arm_search_policy(arm).value for arm in (RdsArm.R, RdsArm.D, RdsArm.S_U)
    ]
    assert [cell.run_id for cell in cells] == ["7.5.2-R-s9001", "7.5.2-D-s9001", "7.5.2-S-u-s9001"]
    assert all(cell.budget == 6 and cell.mode == "demo-historical" for cell in cells)


def test_smoke_plan_default_seeds_give_at_least_ten_cells() -> None:
    assert len(_plan("smoke", (9001, 9002, 9003, 9004)).cells()) == 12


def test_vocabulary_equality_groups_the_same_seed_by_target() -> None:
    cells = [
        {
            "target_id": target,
            "seed": 42,
            "arm": arm,
            "vocabulary_pool_final": [pool],
        }
        for target, pool in (("target-a", "a"), ("target-b", "b"))
        for arm in ("R", "S-u")
    ]
    expected = {"target-a": frozenset({"R", "S-u"}), "target-b": frozenset({"R", "S-u"})}
    result = vocabulary_equality(cells, expected_arms_by_target=expected)
    assert result["equal"] is True
    assert set(result["per_seed"]) == {"target-a/42", "target-b/42"}
    assert result["per_seed"]["target-a/42"]["pool_sizes"] == {"R": 1, "S-u": 1}


def test_vocabulary_equality_requires_every_declared_arm_and_nonempty_pools() -> None:
    cells = [
        {"target_id": "one", "seed": 1, "arm": "R", "vocabulary_pool_final": ["a"]},
        {"target_id": "one", "seed": 1, "arm": "S-u", "vocabulary_pool_final": ["a"]},
    ]
    expected = {"one": frozenset({"R", "S-u"})}
    assert vocabulary_equality(cells, expected_arms_by_target=expected)["equal"] is True
    assert vocabulary_equality(cells[:1], expected_arms_by_target=expected)["equal"] is False
    assert (
        vocabulary_equality(cells, expected_arms_by_target={"one": frozenset({"R", "D", "S-u"})})[
            "equal"
        ]
        is False
    )
    duplicate = [*cells, dict(cells[1])]
    assert vocabulary_equality(duplicate, expected_arms_by_target=expected)["equal"] is False
    empty = [dict(cell, vocabulary_pool_final=[]) for cell in cells]
    assert vocabulary_equality(empty, expected_arms_by_target=expected)["equal"] is False


def test_legacy_single_target_vocabulary_result_shape_and_three_arm_gate() -> None:
    cells = [
        {"seed": 5, "arm": arm, "vocabulary_pool_final": ["outside"]} for arm in ("R", "D", "S-u")
    ]
    result = vocabulary_equality(cells)
    assert set(result) == {"equal", "per_seed", "basis"}
    assert set(result["per_seed"]) == {"5"}
    assert result["equal"] is True
    assert vocabulary_equality(cells[:2])["equal"] is False


def test_dry_run_prints_commands_env_and_paths_without_docker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "g1"
    assert main(["--plan", "completion", "--output", str(out), "--budget", "50", "--dry-run"]) == 0
    text = capsys.readouterr().out
    assert "local_node_tar_smoke.sh demo-historical" in text
    assert '"RUN_ID": "7.5.2-S-u-s9001"' in text and '"DEMO_BUDGET": "50"' in text
    assert f'"DEMO_POLICY": "{arm_search_policy(RdsArm.D).value}"' in text
    assert "fixed-baseline-v1" in text and '"SKIP_BUILD": "1"' in text
    assert str(out / "summaries" / "7.5.2-R-s9001.summary.json") in text
    assert "inodefence-effect-demo-historical-7.5.2-D-s9001.steps.jsonl" in text
    assert not out.exists()  # nothing was created


def test_dry_run_with_sentinel_shows_intended_env_and_live_run_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "g1"
    args = ["--plan", "completion", "--output", str(out), "--sentinel-seed", "9001"]
    assert main([*args, "--dry-run"]) == 0
    assert '"DEMO_SENTINEL_SEED": "9001"' in capsys.readouterr().out
    assert main(args) == 2
    text = capsys.readouterr().out
    assert "not wired" in text and SENTINEL_WIRING[0].split(":")[0] in text
    assert not out.exists()


def test_smoke_plan_needs_ten_cells() -> None:
    with pytest.raises(SystemExit):
        main(["--plan", "smoke", "--output", "/tmp/x", "--seeds", "1", "--dry-run"])


def _write_cells(plan: G1Plan, output: Path, *, abort: dict[str, int] | None = None) -> None:
    """Synthetic demo reports in the layout the smoke script produces."""
    output.mkdir(parents=True)
    abort = abort or {}
    for cell in plan.cells():
        paths = cell_paths(cell, output)
        config = plan.cell_config(cell)
        report: dict[str, Any] = synthetic_demo_report(
            cell.seed, cell.budget, config.search_policy, config.mutation_policy
        )
        steps: list[Any] = report["steps"]
        if cell.run_id in abort:
            keep = abort[cell.run_id]
            report = {
                "label": "demo run",
                "producer": "native",
                "aborted": {
                    "step_index": keep,
                    "reason": "broker",
                    "case_id": "c",
                    "observed": None,
                },
            }
            steps = steps[:keep]
        paths["report"].write_text(json.dumps(report), encoding="utf-8")
        paths["steps_jsonl"].write_text(
            "".join(json.dumps(s) + "\n" for s in steps), encoding="utf-8"
        )


def test_summarize_only_builds_index_and_verdict(tmp_path: Path, capsys) -> None:
    plan = _plan("smoke", (1, 2, 3, 4), budget=6)
    out = tmp_path / "g1"
    _write_cells(plan, out, abort={"7.5.2-D-s2": 3})
    document = summarize_output(plan, out)
    index = json.loads((out / "summaries" / "index.json").read_text())
    assert index == document
    assert index["label"] == list(LABELS) and "unregistered" in index["gate"]
    assert index["abort_count"] == 1 and index["g1_verdict"]["pass"] is True
    assert index["vocabulary_equal_across_arms"] is True
    aborted = next(c for c in index["cells"] if c["run_id"] == "7.5.2-D-s2")
    assert aborted["aborted"] and aborted["t_first"] == 3 and aborted["t_first_event"] == 0
    record = json.loads((out / "summaries" / "7.5.2-S-u-s1.summary.json").read_text())
    assert record["summary"]["arm"] == "S-u" and record["summary"]["complete"] is True
    assert record["source"]["steps_from"] == "report" and record["label"] == list(LABELS)
    assert record["sentinel_set_requested"] is None
    assert record["config_nonconformant"] is False and record["invalid_reason"] is None
    assert record["timing"]["execution_mode"] == "per-case-container"
    assert record["timing"]["wall_seconds"] is None  # synthetic reports carry no timing
    assert record["environment"]["image_id"] is None and index["invalid_count"] == 0
    code = main(
        [
            "--plan",
            "smoke",
            "--output",
            str(out),
            "--seeds",
            "1,2,3,4",
            "--budget",
            "6",
            "--summarize-only",
        ]
    )
    assert code == 0 and '"pass": true' in capsys.readouterr().out


def test_completion_verdict_fails_on_any_abort(tmp_path: Path) -> None:
    plan = _plan("completion", (7,), budget=5)
    out = tmp_path / "g1"
    _write_cells(plan, out, abort={"7.5.2-R-s7": 2})
    document = summarize_output(plan, out)
    verdict = document["g1_verdict"]
    assert (verdict["aborts"], verdict["vocabulary_equal_across_arms"], verdict["pass"]) == (
        1,
        True,
        False,
    )
    small = g1_verdict("smoke", [{"complete": True}] * 9, True)
    assert (small["cells"], small["pass"]) == (9, False)
    assert g1_verdict("completion", [{"complete": True}] * 3, False)["pass"] is False


def test_vocabulary_equality_is_asserted_per_seed_from_recorded_pools(tmp_path: Path) -> None:
    plan = _plan("completion", (5,), budget=5)
    out = tmp_path / "g1"
    _write_cells(plan, out)
    document = summarize_output(plan, out)
    assert document["vocabulary_equal_across_arms"] is True
    detail = document["vocabulary_equality"]["per_seed"]["5"]
    assert detail["equal"] and detail["arms"] == ["D", "R", "S-u"]
    pools = {cell["arm"]: set(cell["vocabulary_pool_final"]) for cell in document["cells"]}
    assert len(set(map(frozenset, pools.values()))) == 1 and "outside" in pools["R"]
    # Tamper one arm's step-0 BEFORE names: the equality must fail and so must G1.
    report_path = cell_paths(plan.cells()[1], out)["report"]
    report = json.loads(report_path.read_text())
    report["steps"][0]["name_segments"]["before"].append("elsewhere")
    report_path.write_text(json.dumps(report))
    document = summarize_output(plan, out)
    assert document["vocabulary_equal_across_arms"] is False
    assert document["g1_verdict"]["pass"] is False
    sizes = document["vocabulary_equality"]["per_seed"]["5"]["pool_sizes"]
    assert sizes["D"] == sizes["R"] + 1


def test_config_nonconformant_cell_is_the_invalid_bucket(tmp_path: Path) -> None:
    plan = _plan("completion", (3,), budget=5)
    out = tmp_path / "g1"
    _write_cells(plan, out)
    paths = cell_paths(plan.cells()[2], out)
    report = json.loads(paths["report"].read_text())
    report["config"]["random_seed"] = 99  # a different cell than planned
    paths["report"].write_text(json.dumps(report))
    document = summarize_output(plan, out)
    entry = next(c for c in document["cells"] if c["run_id"] == "7.5.2-S-u-s3")
    assert entry["invalid"] and not entry["complete"] and not entry["aborted"]
    assert document["invalid_count"] == 1 and document["abort_count"] == 0
    assert document["g1_verdict"]["pass"] is False
    record = json.loads(paths["summary"].read_text())
    assert record["config_nonconformant"] is True and "differs" in record["invalid_reason"]
    assert record["summary"] is None


def test_timing_and_environment_are_read_from_report_and_log(tmp_path: Path) -> None:
    from inodefence.evaluation.rds_report import environment_record, timing_record

    report = {
        "timing": {
            "total_seconds": 120.0,
            "per_case": [
                {"case_id": "a", "wall_seconds": w, "target_seconds": w / 2}
                for w in (1.0, 2.0, 3.0, 10.0)
            ],
        },
        "image_id": "sha256:" + "ab" * 32,
        "node_tar_version": "7.5.2",
    }
    timing = timing_record(report, "per-case-container")
    assert timing["wall_seconds"] == 120.0 and timing["exec_per_hour"] == 120.0
    assert (timing["full_step_seconds_p50"], timing["full_step_seconds_p95"]) == (2.0, 10.0)
    assert timing["full_step_seconds_max"] == 10.0 and timing["step_target_seconds"] == [
        0.5,
        1.0,
        1.5,
        5.0,
    ]
    assert timing_record(None, None) == {
        "wall_seconds": None,
        "step_wall_seconds": None,
        "step_target_seconds": None,
        "full_step_seconds_p50": None,
        "full_step_seconds_p95": None,
        "full_step_seconds_max": None,
        "exec_per_hour": None,
        "execution_mode": None,
    }
    env = environment_record(report, {"machine": "x86_64", "docker_server_version": "29.8.1"})
    assert env["image_id"] == report["image_id"] and env["recipe_sha256"] is None
    assert env["host_machine"] == "x86_64" and env["docker_server_version"] == "29.8.1"
    # The driver reads the docker engine version from the smoke script's log line.
    plan = _plan("completion", (1,), budget=4)
    out = tmp_path / "g1"
    _write_cells(plan, out)
    cell_paths(plan.cells()[0], out)["log"].write_text(
        "==> [preflight]\ncontext=default engine=29.8.1 mode=demo-historical\n"
    )
    summarize_output(plan, out)
    record = json.loads(cell_paths(plan.cells()[0], out)["summary"].read_text())
    assert record["environment"]["docker_server_version"] == "29.8.1"
    assert record["environment"]["host_machine"] is None  # no matrix.json in this fixture
