import copy
from typing import Any

import pytest
from scripts.analyze_node_internal_completion import analyze_evidence
from scripts.qualify_node_internal_completion import qualification_cases, summarize


def _stock_run() -> dict[str, object]:
    return {
        "profile": "stock",
        "status": "completed",
        "duration_ns": 2,
        "observation": {
            "target_duration_ns": 1,
            "events": [],
            "final_semantic_snapshot": [],
        },
    }


def _evidence() -> dict[str, Any]:
    cases = qualification_cases()
    runs = {
        name: {
            "stock": [_stock_run()],
            "marker": [{**_stock_run(), "profile": "marker"}],
            "snapshot": [{**_stock_run(), "profile": "snapshot"}],
        }
        for name in cases
    }
    return {
        "schema_version": 1,
        "experiment_id": "node-internal-completion-qualification-v3",
        "config": {"cases": {name: {"case_id": case.case_id} for name, case in cases.items()}},
        "runs": runs,
        "mechanical_summary": summarize(cases, runs),
    }


def test_analyzer_recomputes_stored_summary() -> None:
    evidence = _evidence()

    assert analyze_evidence(evidence) == evidence["mechanical_summary"]


def test_analyzer_rejects_changed_case_identity() -> None:
    evidence = copy.deepcopy(_evidence())
    evidence["config"]["cases"]["mixed"]["case_id"] = "0" * 64

    with pytest.raises(ValueError, match="case identity mismatch"):
        analyze_evidence(evidence)
