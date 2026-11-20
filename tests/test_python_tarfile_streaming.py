"""#542: python-tarfile exploration streams its steps; the common result is unchanged.

The loop keeps no step in memory (``CampaignHooks(retain_steps=False)``); every step still
reaches ``step_sink`` (the controller's ``<report>.steps.jsonl``). The per-case verdict records
stay, so the product driver builds a byte-identical ``result.json``. What remains per case is
that small record (a few hundred bytes), not the step's snapshots and trace.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from tests.test_python_tarfile_contained import IMAGE, RUNTIME, _LocalBackend

import inodefence.drivers.explore_result as er
import inodefence.drivers.run_target as rt
from inodefence.drivers.python_tarfile import explore as pte
from inodefence.drivers.python_tarfile.producer import ProducerImage
from inodefence.effect_demo import render_effect_campaign_summary
from inodefence.generator import minimal_seed_corpus
from inodefence.python_tarfile_explore import python_tarfile_exploration_report

ROOT = Path(__file__).resolve().parents[1]
SEEDS = len(minimal_seed_corpus())


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        er, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )


def _run(budget: int, *, stream: bool, seed: int = 7) -> tuple[dict[str, Any], list[Any]]:
    lines: list[Any] = []
    report = python_tarfile_exploration_report(
        _LocalBackend(), IMAGE, "data", RUNTIME, seed=seed, budget=budget, stream=stream,
        step_sink=lines.append,
    )  # fmt: skip
    return report, lines


def _result_json(report: dict[str, Any], tmp: Path) -> str:
    prepared = rt.PreparedTargetImage(
        "python-tarfile", RUNTIME, RUNTIME, "python:x", "sha256:" + "c" * 64, False
    )
    made = ProducerImage(IMAGE, "sha256:" + "d" * 64, RUNTIME, "e" * 64, "f" * 64, "reused")
    budget = report["config"]["execution_budget"]
    result, tars = pte.build_campaign_result(report, prepared, made, "data", seed=7, budget=budget)
    return er.write_result(tmp, result, tars).read_text(encoding="utf-8")


@pytest.mark.parametrize("seed", [7, 31])
def test_streaming_and_retaining_runs_give_the_same_records_and_result(
    seed: int, tmp_path: Path
) -> None:
    budget = SEEDS + 6
    streamed, streamed_lines = _run(budget, stream=True, seed=seed)
    retained, retained_lines = _run(budget, stream=False, seed=seed)
    for key in ("case_records", "violation_inputs", "retained_case_ids", "initial_case_ids"):
        assert streamed[key] == retained[key], key
    assert streamed["config"] == retained["config"]
    # every step still reaches the sink, in order, with the same case ids
    assert len(streamed_lines) == len(retained_lines) == budget
    assert [line["case_id"] for line in streamed_lines] == [
        line["case_id"] for line in retained_lines
    ]
    assert [line["case_id"] for line in retained["steps"]] == [
        line["case_id"] for line in streamed_lines
    ]
    # the product result is byte-identical
    assert _result_json(streamed, tmp_path / "s") == _result_json(retained, tmp_path / "r")


def test_the_streaming_report_keeps_what_readers_match_on_and_drops_the_steps() -> None:
    report, _ = _run(SEEDS + 2, stream=True)
    assert report["streaming"] is True and report["demo_report_schema"] == 5
    for key in ("steps", "observer_integrity_summary", "final_search_stats", "aggregate"):
        assert key not in report, key
    for key in ("config", "initial_case_ids", "retained_case_ids", "image_id", "vocabulary_mode"):
        assert key in report, key
    # the controller prints this summary at the end of every run
    summary = render_effect_campaign_summary(report)
    assert f"runs={SEEDS + 2} (streaming)" in summary


def test_the_report_no_longer_grows_with_per_step_detail() -> None:
    # Serialized size per extra step: the retaining report carries every step's trace and
    # snapshots; the streaming one only each case's small verdict record.
    small, large = SEEDS + 2, SEEDS + 12

    def per_step(stream: bool) -> float:
        a = len(json.dumps(_run(small, stream=stream)[0]))
        b = len(json.dumps(_run(large, stream=stream)[0]))
        return (b - a) / (large - small)

    streamed, retained = per_step(True), per_step(False)
    assert streamed < 1024, streamed  # a case_records entry is a few hundred bytes
    assert streamed * 4 < retained, (streamed, retained)


def test_the_controller_always_journals_python_tarfile_steps() -> None:
    # The steps' only record is the journal: the controller's python-tarfile mode always opens
    # <report>.steps.jsonl and passes its writer as step_sink, whatever else is configured.
    source = (ROOT / "scripts" / "container_controller.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "python_tarfile_exploration_report"
    ]
    assert len(calls) == 1
    sinks = [kw for kw in calls[0].keywords if kw.arg == "step_sink"]
    assert len(sinks) == 1 and isinstance(sinks[0].value, ast.Name)
    assert sinks[0].value.id == "persist_step"
    assert "steps_stream.write(render_effect_step_line(record))" in source
    assert "steps_path = demo_steps_path(evidence)" in source
