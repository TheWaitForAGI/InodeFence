"""Host qualification judgement (qualify_host) and the sealed Stage A key extraction."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0
from scripts import extract_stage_a_abort_keys, qualify_host

from test_host_qualification_assignment import _replicate_setup
from test_run_exp0 import TARGET_IMAGES, VICTIM, _cell, _fake_runner
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine
from test_run_exp0_host_guards import CONTROLLER_ID, DIGEST, HELPER_ID, FakeDocker
from test_run_exp0_host_guards import real_guards as real_guards
from test_two_host_split import _host_args

ORACLE_WORDS = ("contract_violated", "c1_", "c2_", "violated_contracts", "t_first")


def _criteria(tmp_path: Path, cells: int, **over: Any) -> tuple[Path, str]:
    criteria = {
        "schema": qualify_host.CRITERIA_SCHEMA,
        "max_first_attempt_abort_ratio": "0.30",
        "max_unstable_steps_per_1000": "1",
        "max_cell_seconds": 7200,
        "expected_cells": cells,
        "expected_image_ids": {
            "inodefence-node-tar-effect:7.5.2": DIGEST,
            "inodefence-controller:local": CONTROLLER_ID,
            "inodefence-helper:local": HELPER_ID,
        },
        **over,
    }
    path = tmp_path / "criteria.json"
    path.write_text(json.dumps(criteria, sort_keys=True), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _environment(prereg: Path) -> dict[str, Any]:
    """The Stage A environment record a key file would carry for this registration's cells."""
    registration = run_exp0.load_preregistration(prereg)
    plan = run_exp0.Exp0Plan(registration, prereg, "x", "7.5.2", False)
    return {
        "search_policies": sorted({str(arm.search) for arm in plan.arms()}),
        "mutation_policy": plan.arms()[0].mutation,
        "vocabulary": registration.vocabulary_mode.value,
        "sentinel_generator_id": registration.sentinel_generator_id,
        "sentinel_generator_seed": registration.sentinel_generator_seed,
        "sentinel_count": registration.sentinel_count,
        "budget": registration.budget,
        "seeds": sorted(registration.seeds),
    }


def _keys(
    tmp_path: Path, aborts: list[dict[str, Any]], prereg: Path, **environment: Any
) -> tuple[Path, str]:
    document = {
        "schema": extract_stage_a_abort_keys.SCHEMA,
        "budget": 6,
        "image_digest": DIGEST,
        "environment": {**_environment(prereg), **environment},
        "aborts": aborts,
    }
    path = tmp_path / "keys.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _run_host1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: Any
) -> tuple[list[str], Path, Path, Path, int]:
    out, args, assignment = _replicate_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(run_exp0, "docker_engine_version", lambda context: "29.8.0")
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main(_host_args(args, out, "HOST1", assignment, "2"))
    prereg = Path(args[args.index("--preregistration") + 1])
    host1 = out.parent / f"{out.name}-HOST1"
    cells = len(json.loads((host1 / "summaries" / "index.json").read_text())["cells"])
    return args, prereg, assignment, host1, cells


def _judge(
    prereg: Path,
    assignment: Path,
    host1: Path,
    criteria: tuple[Path, str],
    keys: tuple[Path, str],
    out: Path,
) -> tuple[int, dict[str, Any], str]:
    code = qualify_host.main(
        [
            "--preregistration",
            str(prereg),
            "--seed-assignment",
            str(assignment),
            "--host-id",
            "HOST1",
            "--output",
            str(host1),
            "--criteria",
            str(criteria[0]),
            "--criteria-sha256",
            criteria[1],
            "--stage-a-keys",
            str(keys[0]),
            "--stage-a-keys-sha256",
            keys[1],
            "--out",
            str(out),
        ]
    )
    text = out.read_text(encoding="utf-8") if out.is_file() else ""
    return code, (json.loads(text) if text else {}), text


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_a_clean_host_passes_and_no_oracle_value_leaves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    _, prereg, assignment, host1, cells = _run_host1(
        tmp_path, monkeypatch, _fake_runner(TARGET_IMAGES)
    )
    keys = _keys(tmp_path, [], prereg)
    code, report, text = _judge(
        prereg, assignment, host1, _criteria(tmp_path, cells), keys, tmp_path / "q.json"
    )
    assert code == 0 and report["verdict"] == "PASS", report["criteria"]
    assert set(report["criteria"]) >= {
        "cleanup_unknown",
        "image_ids_expected_start_and_end",
        "engine_images_path_unchanged",
        "record_completeness",
        "watchdog",
        "first_attempt_abort_ratio",
        "unconfirmed_aborts",
        "unstable_steps_per_1000_by_arm",
        "longest_attempt_seconds",
        "start_denied",
        "infrastructure_stops",
        "stage_a_recurrence",
    }
    for word in ORACLE_WORDS:
        assert word not in text
    step = json.loads(next(host1.rglob("*.steps.jsonl")).read_text().splitlines()[0])
    assert json.dumps(step.get("oracle"), sort_keys=True) not in text
    assert report["files_read"]


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_criteria_fixed_before_measurement_cannot_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    _, prereg, assignment, host1, cells = _run_host1(
        tmp_path, monkeypatch, _fake_runner(TARGET_IMAGES)
    )
    criteria = _criteria(tmp_path, cells)
    moved = _criteria(tmp_path, cells, max_first_attempt_abort_ratio="0.50")[0]
    code, _, _ = _judge(
        prereg,
        assignment,
        host1,
        (moved, criteria[1]),
        _keys(tmp_path, [], prereg),
        tmp_path / "q.json",
    )
    assert code == 2


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_a_retried_first_attempt_still_counts_as_an_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    inner = _fake_runner(TARGET_IMAGES)
    seen: set[str] = set()
    captured: dict[str, Any] = {}

    def runner(cell: Any, output: Path, env: Any, bash: str, **limits: Any) -> Any:
        result = inner(cell, output, env, bash, **limits)
        if cell.run_id == VICTIM and VICTIM not in seen:
            seen.add(VICTIM)
            paths = _cell(captured["args"], VICTIM, output)
            paths["report"].unlink()
            paths["steps_jsonl"].unlink()
        return result

    out, args, assignment = _replicate_setup(tmp_path, monkeypatch)
    captured["args"] = args
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main(_host_args(args, out, "HOST1", assignment, "2"))
    host1 = out.parent / f"{out.name}-HOST1"
    prereg = Path(args[args.index("--preregistration") + 1])
    cells = len(json.loads((host1 / "summaries" / "index.json").read_text())["cells"])
    code, report, _ = _judge(
        prereg,
        assignment,
        host1,
        _criteria(tmp_path, cells),
        _keys(tmp_path, [], prereg),
        tmp_path / "q.json",
    )
    ratio = report["criteria"]["first_attempt_abort_ratio"]["value"]
    assert ratio["failed_first_attempts"] == 1 and ratio["retries"] == 1
    assert report["criteria"]["record_completeness"]["result"] == "PASS"


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_a_stage_a_abort_recurrence_fails_the_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    behaviour: dict[str, Any] = {**TARGET_IMAGES, "abort": {VICTIM}}
    _, prereg, assignment, host1, cells = _run_host1(tmp_path, monkeypatch, _fake_runner(behaviour))
    steps = next(p for p in host1.rglob("*.steps.jsonl") if VICTIM in p.name)
    case_ids = [json.loads(line)["case_id"] for line in steps.read_text().splitlines()]
    policy = next(
        arm.search
        for arm in run_exp0.Exp0Plan(
            run_exp0.load_preregistration(prereg), prereg, "x", "7.5.2", False
        ).arms()
        if arm.label == "D"
    )
    key = {
        "search_policy": policy,
        "seed": 9001,
        "step_index": 2,
        "case_id": "c",
        "path_prefix_sha256": extract_stage_a_abort_keys.path_sha256(case_ids[:2]),
    }
    code, report, _ = _judge(
        prereg,
        assignment,
        host1,
        _criteria(tmp_path, cells),
        _keys(tmp_path, [key], prereg),
        tmp_path / "q.json",
    )
    recurrence = report["criteria"]["stage_a_recurrence"]
    assert recurrence["result"] == "FAIL"
    assert recurrence["value"]["recurrences"] == [{"seed": 9001, "step_index": 2}]
    assert recurrence["value"]["same_path_to_abort"] == 1
    assert code == 1


def test_stage_a_keys_keep_input_identifiers_only(tmp_path: Path) -> None:
    design = Path("experiments/configs/concurrency-scaling-v2.md")
    block = tmp_path / "block-1-j2"
    (block / "raw").mkdir(parents=True)
    steps = [
        {"index": i, "case_id": f"case-{i}", "oracle": {"contract_violated": True}}
        for i in range(3)
    ]
    (block / "raw" / "s.steps.jsonl").write_text("".join(json.dumps(s) + "\n" for s in steps))
    (block / "raw" / "r.json").write_text(
        json.dumps(
            {
                "aborted": {
                    "step_index": 2,
                    "case_id": "case-2",
                    "reason": "broker: secret detail",
                },
                "oracle_summary": {"c1_identity": True},
            }
        )
    )
    (block / "block.json").write_text(
        json.dumps(
            {
                "design_sha256": hashlib.sha256(design.read_bytes()).hexdigest(),
                "stage": "A",
                "jobs": 2,
                "cells": [
                    {
                        "arm": "R-restart",
                        "seed": 8110,
                        "returncode": 1,
                        "report": "r.json",
                        "steps": "s.steps.jsonl",
                    },
                    {
                        "arm": "D",
                        "seed": 8110,
                        "returncode": 0,
                        "report": "x.json",
                        "steps": "x.steps.jsonl",
                    },
                ],
            }
        )
    )
    out = tmp_path / "evidence" / "keys.json"
    assert (
        extract_stage_a_abort_keys.main(
            ["--block", str(block), "--design", str(design), "--out", str(out)]
        )
        == 0
    )
    text = out.read_text()
    document = json.loads(text)
    [key] = document["aborts"]
    assert key["search_policy"] == "unretained-seed-restart-v1-uniform-mutation-v1"
    assert (key["seed"], key["step_index"], key["case_id"]) == (8110, 2, "case-2")
    assert key["path_prefix_sha256"] == extract_stage_a_abort_keys.path_sha256(["case-0", "case-1"])
    for word in ("secret detail", "contract_violated", "c1_identity", "oracle_summary"):
        assert word not in text
    assert (
        extract_stage_a_abort_keys.main(
            ["--block", str(block), "--design", str(design), "--out", "scripts/keys.json"]
        )
        == 2
    )  # never inside the repository


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_an_abort_without_a_whole_error_chain_is_unconfirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_guards: FakeDocker
) -> None:
    behaviour: dict[str, Any] = {**TARGET_IMAGES, "abort": {VICTIM}}
    _, prereg, assignment, host1, cells = _run_host1(tmp_path, monkeypatch, _fake_runner(behaviour))
    _, report, _ = _judge(
        prereg,
        assignment,
        host1,
        _criteria(tmp_path, cells),
        _keys(tmp_path, [], prereg),
        tmp_path / "q.json",
    )
    assert report["criteria"]["unconfirmed_aborts"] == {
        "result": "FAIL",
        "value": 1,
        "threshold": 0,
    }


@pytest.mark.parametrize(
    ("stub", "unconfirmed"),
    [
        (None, True),
        ({"reason": "x"}, True),
        ({"reason": "x", "error_chain": []}, True),
        ({"reason": "x", "error_chain": [{"type": "A"}, {"truncated": True}]}, True),
        (
            {"reason": "container cleanup inspect failed", "error_chain": [{"type": "Cleanup"}]},
            False,
        ),
        ({"reason": "broker", "error_chain": [{"type": "A"}, {"type": "B"}]}, False),
    ],
)
def test_q8_unconfirmed_abort_definition(stub: Any, unconfirmed: bool) -> None:
    assert qualify_host.unconfirmed_abort(stub) is unconfirmed


def test_the_category_comes_from_the_original_reason() -> None:
    from inodefence.execution.call_diagnostics import annotate_reason
    from inodefence.execution.stall_recovery import CallObservation

    call = CallObservation("container inspect", "c", -9, True, False, 0.0, 0.0, 10.0)
    # Includes a reason that ends with a signature prefix (W4 Low 1 on #343).
    for original in ("broker: lost", "x container runtime", "container runtime inspect failed: "):
        suffixed = {"reason": annotate_reason(original, [call])}
        assert suffixed["reason"] != original
        assert qualify_host.abort_category(suffixed) == qualify_host.abort_category(
            {"reason": original}
        )
    assert qualify_host.abort_category({"reason": "anything", "category": "broker"}) == "broker"


@pytest.mark.usefixtures("admit_fixture_holdout")
def test_a_different_cell_environment_invalidates_the_recurrence_test_before_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, args, assignment = _replicate_setup(tmp_path, monkeypatch)
    prereg = Path(args[args.index("--preregistration") + 1])
    base = [
        "--preregistration",
        str(prereg),
        "--seed-assignment",
        str(assignment),
        "--host-id",
        "HOST1",
        "--check-environment",
    ]
    keys = _keys(tmp_path, [], prereg)
    good = tmp_path / "env.json"
    assert (
        qualify_host.main(
            [
                *base,
                "--stage-a-keys",
                str(keys[0]),
                "--stage-a-keys-sha256",
                keys[1],
                "--out",
                str(good),
            ]
        )
        == 0
    )
    assert json.loads(good.read_text())["input_dependence_test_valid"] is True
    other = _keys(tmp_path, [], prereg, mutation_policy="uniform-generic-m1-escape-hardlink-v1")
    bad = tmp_path / "env-bad.json"
    assert (
        qualify_host.main(
            [
                *base,
                "--stage-a-keys",
                str(other[0]),
                "--stage-a-keys-sha256",
                other[1],
                "--out",
                str(bad),
            ]
        )
        == 1
    )
    result = json.loads(bad.read_text())
    assert result["input_dependence_test_valid"] is False
    assert any(problem.startswith("mutation_policy") for problem in result["problems"])


def test_cell_path_pairs_count_m_x_and_flag_reexecutions(tmp_path: Path) -> None:
    from scripts import compare_cell_paths

    def write(name: str, ids: list[str], reexecutions: int | None = None) -> Path:
        steps = tmp_path / f"{name}.steps.jsonl"
        steps.write_text(
            "".join(
                json.dumps({"index": i, "case_id": c, "oracle": {"hit": 1}}) + "\n"
                for i, c in enumerate(ids)
            )
        )
        if reexecutions is not None:
            (tmp_path / f"{name}.json").write_text(
                json.dumps({"infra_reexecutions": [{}] * reexecutions, "oracle_summary": {"c1": 1}})
            )
        return steps

    pairs = {
        "same": (write("a1", ["x", "y"]), write("a2", ["x", "y"])),
        "diff": (write("b1", ["x", "y"], 1), write("b2", ["x", "z"], 0)),
        "gone": (write("c1", ["x"]), tmp_path / "missing.steps.jsonl"),
    }
    out = tmp_path / "pairs.json"
    argv = ["--budget", "2", "--out", str(out)]
    for label, (left, right) in pairs.items():
        argv += ["--pair", f"{label}={left},{right}"]
    assert compare_cell_paths.main(argv) == 0
    text = out.read_text()
    summary = json.loads(text)["summary"]
    assert summary == {
        "pairs": 3,
        "identical": 1,
        "m_x": 1,
        "incomparable": 1,
        "with_reexecutions": ["diff"],
    }
    for word in ('"x"', "oracle", "c1"):
        assert word not in text
