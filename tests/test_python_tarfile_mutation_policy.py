"""python-tarfile ``explore --mutation-policy``: the same rules as node-tar, on a per-case report.

- The option reaches the launcher only as given; the caller's environment never does.
- The result records the policy only after the loop report shows it ran it (else exit 2, no result).
- The build-invalid count is ``executed - len(case_records)``; it is written only when > 0 and is
  left out of the un-judged ratio's denominator.
- Case numbers, the first-violation rank and the replay lookup agree with the loop's steps.
- Without the option nothing is checked or recorded (the default output fixture is pinned in
  ``tests/test_explore_mutation_policy.py``).

The loop runs on the in-process ``_LocalBackend`` (no Docker). Build-invalid steps are synthetic:
the loop's builder probe refuses every third mutation child.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.test_python_tarfile_contained import IMAGE, RUNTIME, _LocalBackend
from tests.test_python_tarfile_step_numbering import BUDGET, SEED, _run

import inodefence.drivers.explore_result as er
import inodefence.drivers.python_tarfile.explore as pte
import inodefence.drivers.run_target as rt
import inodefence.drivers.run_target_explore as rte
from inodefence.case_replay import load_result_replay_request
from inodefence.drivers.python_tarfile.producer import ProducerImage
from inodefence.mutator.policy import MutationPolicy
from inodefence.python_tarfile_explore import python_tarfile_exploration_report
from inodefence.target_result import load_target_result

V2 = MutationPolicy.V2_FREEZE3_FIXED_BASELINE
FILTER = "fully_trusted"  # the in-process fixture reaches a violation only without a filter


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        er, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )


def _prepared() -> rt.PreparedTargetImage:
    return rt.PreparedTargetImage(
        "python-tarfile", RUNTIME, RUNTIME, "python:x", "sha256:" + "c" * 64, False
    )


def _made() -> ProducerImage:
    return ProducerImage(IMAGE, "sha256:" + "d" * 64, RUNTIME, "e" * 64, "f" * 64, "reused")


def _write(tmp: Path, report: dict[str, Any], policy: str | None) -> Path:
    result, tars = pte.build_campaign_result(
        report, _prepared(), _made(), FILTER, seed=SEED, budget=BUDGET, mutation_policy=policy
    )
    return er.write_result(tmp / "result", result, tars)


def test_v2_result_counts_build_invalid_steps_and_numbers_by_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report, lines = _run(monkeypatch, policy=V2)
    invalid = sum(1 for line in lines if line["outcome"] == "build-invalid")
    first = min(item["run_index"] for item in report["violation_inputs"])
    path = _write(tmp_path, report, V2.value)
    raw = json.loads(path.read_text(encoding="utf-8"))
    campaign = raw["campaign"]
    assert campaign["mutation_policy"] == V2.value
    assert campaign["build_invalid"] == invalid > 0
    assert campaign["runs_executed"] == BUDGET
    # the first-violation rank is the step's (1-based), build-invalid steps before it included
    assert campaign["runs_to_first_violation"] == first + 1
    result = load_target_result(path)
    assert result.extraction_runs == BUDGET - invalid == len(result.cases)
    assert result.unjudged_ratio == round(result.unjudged_steps / (BUDGET - invalid), 6)
    # case step-N is step N; replay finds that step's input under the same name
    assert {case.case_id for case in result.cases} == {
        f"step-{i}" for i, line in enumerate(lines) if line["outcome"] == "executed"
    }
    request = load_result_replay_request(path.parent, f"step-{first}")
    assert request.case.case_id == lines[first]["case_id"]
    assert request.original["run"] == f"step-{first}"


def test_v2_without_build_invalid_steps_writes_no_count(tmp_path: Path) -> None:
    report, _ = _run(None, policy=V2)
    campaign = json.loads(_write(tmp_path, report, V2.value).read_text(encoding="utf-8"))[
        "campaign"
    ]
    assert campaign["mutation_policy"] == V2.value
    assert "build_invalid" not in campaign


def test_a_per_case_report_without_its_step_count_is_an_error(tmp_path: Path) -> None:
    report, _ = _run(None, policy=V2)
    del report["executed"]
    with pytest.raises(er.BuildInvalidUnknownError, match="build-invalid count unknown"):
        _write(tmp_path, report, V2.value)
    report["executed"] = len(report["case_records"]) - 1
    with pytest.raises(er.BuildInvalidUnknownError, match="exceed"):
        _write(tmp_path, report, V2.value)


# -- the driver hook -----------------------------------------------------------------------------


def _fake_controller(report: dict[str, Any], seen: list[str | None]):
    def fake(*_: Any, out: Path, run_id: str, mutation_policy=None, **__: Any) -> Path:
        seen.append(mutation_policy)
        path = pte.report_path(out, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    return fake


def _engine_report(policy: MutationPolicy | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {} if policy is None else {"mutation_policy": policy}
    return python_tarfile_exploration_report(
        _LocalBackend(), IMAGE, "data", RUNTIME, seed=SEED, budget=12, **kwargs
    )


def _explore(monkeypatch: pytest.MonkeyPatch, tmp: Path, report: dict, option: str | None):
    seen: list[str | None] = []
    monkeypatch.setattr(pte, "run_controller", _fake_controller(report, seen))
    options = rt.ExploreOptions(
        budget=12, seed=SEED, out=tmp, mutation_policy=option,
        target_options={"extraction-filter": "data"},
    )  # fmt: skip
    outcome = pte.explore(_prepared(), options, ensure=lambda *a, **k: _made())
    return outcome, seen


def test_the_hook_passes_the_option_and_records_the_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outcome, seen = _explore(monkeypatch, tmp_path, _engine_report(V2), V2.value)
    assert seen == [V2.value]
    campaign = json.loads(outcome.result_path.read_text(encoding="utf-8"))["campaign"]
    assert campaign["mutation_policy"] == V2.value


def test_a_run_that_did_not_run_the_requested_policy_is_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(RuntimeError, match="requested"):
        _explore(monkeypatch, tmp_path, _engine_report(None), V2.value)
    assert not list(tmp_path.rglob("result.json"))


def test_without_the_option_nothing_is_checked_or_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outcome, seen = _explore(monkeypatch, tmp_path, _engine_report(V2), None)
    assert seen == [None]
    campaign = json.loads(outcome.result_path.read_text(encoding="utf-8"))["campaign"]
    assert "mutation_policy" not in campaign and "build_invalid" not in campaign


def test_the_driver_accepts_the_option_for_python_tarfile(capsys, tmp_path: Path) -> None:
    argv = ["--target", "python-tarfile", "--version", "3.12.7", "--extraction-filter", "data"]
    argv += ["--out", str(tmp_path), "--dry-run"]
    assert rte.main(argv) == 0
    plan = json.loads(capsys.readouterr().out)
    assert rte.main([*argv, "--mutation-policy", V2.value]) == 0
    with_option = json.loads(capsys.readouterr().out)
    assert with_option.pop("mutation_policy") == V2.value
    assert with_option == plan


def test_v21_stays_refused_by_the_loop() -> None:
    with pytest.raises(ValueError, match="no exploration plan is approved"):
        python_tarfile_exploration_report(
            _LocalBackend(), IMAGE, "data", RUNTIME, seed=SEED, budget=12,
            mutation_policy=MutationPolicy.V2_FREEZE3_FIXED_BASELINE_MINIMAL_EMPTY_REG,
        )  # fmt: skip
