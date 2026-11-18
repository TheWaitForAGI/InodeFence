"""python-tarfile numbers each case by the loop step it runs in, build-invalid steps included.

D060: a child the TAR builder cannot represent is a recorded step that spends one budget unit and
is never extracted. node-tar numbers by step; so does python-tarfile, so case ``step-N``, its
``violation_inputs`` entry and line N of the controller's ``.steps.jsonl`` all name the same step,
and the first-violation rank counts steps. The difference only shows under the v2 policy (the only
one that records build-invalid steps); a run without one numbers exactly as before.

The build-invalid steps here are synthetic: the loop's builder probe is replaced so every third
mutation child is refused (the real v2 grammar produced none in short runs on this backend). The
extraction backend is the in-process ``_LocalBackend`` of the contained-target tests (no Docker).
"""

from __future__ import annotations

import base64
from typing import Any

import pytest
from tests.test_python_tarfile_contained import IMAGE, RUNTIME, _LocalBackend

import inodefence.effect_campaign as ec
from inodefence.builder import build_tar
from inodefence.generator import minimal_seed_corpus
from inodefence.mutator.policy import MutationPolicy
from inodefence.python_tarfile_explore import python_tarfile_exploration_report
from inodefence.tar_reader import read_builder_tar

V2 = MutationPolicy.V2_FREEZE3_FIXED_BASELINE
SEEDS = len(minimal_seed_corpus())
BUDGET = 40
SEED = 1  # with the synthetic refusals below, its first violation lands after build-invalid steps


def _run(
    monkeypatch: pytest.MonkeyPatch | None, *, policy: MutationPolicy | None, stream: bool = True
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if monkeypatch is not None:
        calls = [0]

        def every_third_refused(case):  # type: ignore[no-untyped-def]
            calls[0] += 1
            if calls[0] % 3 == 1:
                raise ValueError("synthetic: the builder cannot represent this child")
            return build_tar(case)

        monkeypatch.setattr(ec, "build_tar", every_third_refused)
    lines: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {} if policy is None else {"mutation_policy": policy}
    report = python_tarfile_exploration_report(
        _LocalBackend(), IMAGE, "fully_trusted", RUNTIME, seed=SEED, budget=BUDGET,
        allow_fully_trusted=True, stream=stream, step_sink=lines.append, **kwargs,
    )  # fmt: skip
    return report, lines


@pytest.mark.parametrize("stream", [True, False])
def test_case_numbers_are_step_numbers_when_build_invalid_steps_occur(
    monkeypatch: pytest.MonkeyPatch, stream: bool
) -> None:
    report, lines = _run(monkeypatch, policy=V2, stream=stream)
    assert len(lines) == BUDGET
    if stream:  # the retaining report lists its steps instead of an ``executed`` count
        assert report["executed"] == BUDGET
    else:
        assert [step["index"] for step in report["steps"]] == list(range(BUDGET))
    assert [line["index"] for line in lines] == list(range(BUDGET))  # line N is step N
    invalid = [i for i, line in enumerate(lines) if line["outcome"] == "build-invalid"]
    executed = [i for i, line in enumerate(lines) if line["outcome"] == "executed"]
    assert invalid and invalid[0] >= SEEDS  # some, and only among mutation steps
    # every case record carries its step's index; build-invalid steps have none
    assert [record["run_index"] for record in report["case_records"]] == executed
    assert len(report["case_records"]) == BUDGET - len(invalid)


def test_a_violation_input_is_the_input_of_its_step(monkeypatch: pytest.MonkeyPatch) -> None:
    report, lines = _run(monkeypatch, policy=V2)
    assert report["violation_inputs"], "fixture must reach a violation"
    for item in report["violation_inputs"]:
        index = item["run_index"]
        case = read_builder_tar(base64.b64decode(item["tar_b64"]))
        assert case.case_id == lines[index]["case_id"]
        assert lines[index]["outcome"] == "executed"
    first = min(item["run_index"] for item in report["violation_inputs"])
    # the extraction count before it is smaller: the step rank is what node-tar would report
    assert sum(1 for line in lines[:first] if line["outcome"] == "build-invalid") > 0


@pytest.mark.parametrize("policy", [None, V2])
def test_without_build_invalid_steps_numbering_is_unchanged(policy: MutationPolicy | None) -> None:
    report, lines = _run(None, policy=policy)
    assert all(line["outcome"] == "executed" for line in lines)
    assert [record["run_index"] for record in report["case_records"]] == list(range(BUDGET))
