import copy
import hashlib
from typing import Any

import pytest
from scripts.analyze_node_causal_effects import analyze_evidence
from scripts.qualify_node_causal_effects import (
    EXPERIMENT_ID,
    REJECTION_CASE,
    archive_bytes,
    assess_run,
    qualification_cases,
    summarize,
)


def _identity(
    ordinal: int,
    path: str,
    entry_type: str = "File",
    link_target: str | None = None,
) -> dict[str, object]:
    return {
        "ordinal": ordinal,
        "path": path,
        "type": entry_type,
        "link_target": link_target,
    }


def _run(
    profile: str,
    events: list[dict[str, object]],
    *,
    outcome: str = "success",
    returncode: int = 0,
) -> dict[str, object]:
    return {
        "profile": profile,
        "status": "process_returned",
        "returncode": returncode,
        "duration_ns": 2,
        "observation": {
            "target_duration_ns": 1,
            "target_outcome": outcome,
            "events": events,
            "observation_failures": [],
            "final_semantic_snapshot": [],
        },
    }


def _read(identity: dict[str, object]) -> dict[str, object]:
    return {"phase": "archive_entry_read", "identity": identity}


def _effect(operation_id: int, identity: dict[str, object]) -> dict[str, object]:
    return {
        "phase": "filesystem_operation_complete",
        "operation_id": operation_id,
        "operation": "open",
        "identity": identity,
        "paths": [identity["path"]],
        "success": True,
    }


def _complete(identity: dict[str, object], *, target_error: str | None = None) -> dict[str, object]:
    return {
        "phase": "entry_effect_complete",
        "identity": identity,
        "association_failure": None,
        "target_error": target_error,
    }


def test_causal_effect_run_passes_predeclared_feasibility_gate() -> None:
    case = qualification_cases()["regular-file"]
    identity = _identity(0, "regular")
    run = _run("effects", [_read(identity), _effect(0, identity), _complete(identity)])

    assessment = assess_run("regular-file", case, run)

    assert assessment["feasible"] is True
    assert assessment["operation_associations_exact"] is True
    assert assessment["later_effects_before_completion"] == []


def test_later_ordinal_effect_before_earlier_completion_fails_gate() -> None:
    case = qualification_cases()["directory-child"]
    parent = _identity(0, "parent", "Directory")
    child = _identity(1, "parent/child")
    run = _run(
        "effects",
        [
            _read(parent),
            _read(child),
            _effect(0, parent),
            _effect(1, child),
            _complete(parent),
            _complete(child),
        ],
    )

    assessment = assess_run("directory-child", case, run)

    assert assessment["feasible"] is False
    assert assessment["later_effects_before_completion"] == [
        {
            "at_ordinal": 0,
            "later_ordinal": 1,
            "operation": "open",
            "paths": ["parent/child"],
        }
    ]


def test_partial_rejection_preserves_completed_prefix_and_explicit_outcome() -> None:
    case = qualification_cases()[REJECTION_CASE]
    archive = archive_bytes(REJECTION_CASE, case)
    first = _identity(0, "completed-before-error")
    second = _identity(1, "completed-before-error", "Link", "missing-target")
    run = _run(
        "effects",
        [
            _read(first),
            _read(second),
            _effect(0, first),
            _complete(first),
            _complete(second, target_error="Error: missing-target"),
        ],
        outcome="rejected",
        returncode=2,
    )

    assessment = assess_run(REJECTION_CASE, case, run)

    assert archive.endswith(b"\0" * 1024)
    assert case.entries[1].entry_type.value == "hardlink"
    assert assessment["rejection_handled"] is True
    assert assessment["feasible"] is False


def _stock_run(outcome: str = "success", returncode: int = 0) -> dict[str, object]:
    return _run("stock", [], outcome=outcome, returncode=returncode)


def _evidence() -> dict[str, Any]:
    cases = qualification_cases()
    runs: dict[str, dict[str, list[dict[str, object]]]] = {}
    for name, case in cases.items():
        outcome = "rejected" if name == REJECTION_CASE else "success"
        returncode = 2 if name == REJECTION_CASE else 0
        identities = [
            _identity(
                index,
                entry.path,
                {
                    "directory": "Directory",
                    "hardlink": "Link",
                    "symlink": "SymbolicLink",
                }.get(entry.entry_type.value, "File"),
                entry.link_target,
            )
            for index, entry in enumerate(case.entries)
        ]
        events = [_read(identity) for identity in identities]
        for index, identity in enumerate(identities):
            target_error = (
                "Error: missing-target"
                if name == REJECTION_CASE and index == len(identities) - 1
                else None
            )
            events.extend(
                (_effect(index, identity), _complete(identity, target_error=target_error))
            )
        context_events = [
            event for event in events if event["phase"] != "filesystem_operation_complete"
        ]
        runs[name] = {
            "stock": [_stock_run(outcome, returncode)],
            "context": [_run("context", context_events, outcome=outcome, returncode=returncode)],
            "effects": [_run("effects", events, outcome=outcome, returncode=returncode)],
        }
    configured = {
        name: {
            "case_id": case.case_id,
            "archive_sha256": hashlib.sha256(archive_bytes(name, case)).hexdigest(),
        }
        for name, case in cases.items()
    }
    return {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "config": {"cases": configured},
        "runs": runs,
        "mechanical_summary": summarize(cases, runs),
    }


def test_analyzer_recomputes_stored_summary() -> None:
    evidence = _evidence()

    assert analyze_evidence(evidence) == evidence["mechanical_summary"]


def test_analyzer_rejects_changed_archive_identity() -> None:
    evidence = copy.deepcopy(_evidence())
    evidence["config"]["cases"]["regular-file"]["archive_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="archive identity mismatch"):
        analyze_evidence(evidence)
