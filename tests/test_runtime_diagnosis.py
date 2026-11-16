"""Run diagnosis: stage x category x evidence from the launcher's exit code and files only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inodefence.drivers.runtime import diagnosis
from inodefence.drivers.runtime.diagnosis import UNKNOWN, Stage
from inodefence.drivers.runtime.health import DaemonState, DaemonStatus, ImageLookup, ImageState


def _write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_python_tarfile_smoke_shape_is_a_loop_stop_with_its_category(tmp_path: Path) -> None:
    # Same shape as the HOST4 PR 1 smoke stub (synthetic; reason empty after "failed: ").
    report = _write(
        tmp_path / "inodefence-python-tarfile-explore-r.json",
        {
            "aborted": {
                "category": "cleanup_inspect",
                "reason": "container runtime cleanup inspect failed: ",
            },
            "label": "x",
            "mode": "exploration",
            "producer": "python-tarfile",
            "qualification": False,
        },
    )
    steps = tmp_path / "inodefence-python-tarfile-explore-r.steps.jsonl"
    steps.write_text("{}\n" * 18, encoding="utf-8")
    found = diagnosis.run_diagnosis(1, report, evidence=[steps, tmp_path / "absent.jsonl"])
    assert found is not None
    assert (found.stage, found.category, found.result_written) == (
        Stage.LOOP,
        "cleanup_inspect",
        False,
    )
    assert found.evidence == (report, steps)
    line = found.line("TARGET-EXPLORE")
    assert line.startswith("TARGET-EXPLORE DIAGNOSIS: stage=loop category=cleanup_inspect ")
    assert "result=not-written" in line and str(steps) in line
    assert "not a target verdict" in line
    record = found.as_record()
    assert record["evidence"] == [report.name, steps.name]  # names only, no host paths


def test_category_falls_back_to_the_shared_classifier(tmp_path: Path) -> None:
    report = _write(
        tmp_path / "r.json",
        {"aborted": {"reason": "container runtime cleanup inspect failed: boom"}},
    )
    found = diagnosis.run_diagnosis(1, report)
    assert found is not None and found.category == "cleanup_inspect"

    bogus = _write(tmp_path / "b.json", {"aborted": {"category": "made-up", "reason": ""}})
    found = diagnosis.run_diagnosis(1, bogus)
    assert found is not None and (found.stage, found.category) == (Stage.LOOP, UNKNOWN)


def test_complete_report_with_a_failed_launcher_is_cleanup_unknown_not_success(
    tmp_path: Path,
) -> None:
    report = _write(tmp_path / "r.json", {"aggregate": {"runs_executed": 20}})
    found = diagnosis.run_diagnosis(125, report)
    assert found is not None
    assert (found.stage, found.category, found.result_written) == (Stage.CLEANUP, UNKNOWN, False)
    assert "cleanup state unknown" in found.detail and "not treated as success" in found.detail


def test_no_report_is_controller_setup(tmp_path: Path) -> None:
    found = diagnosis.run_diagnosis(1, tmp_path / "missing.json")
    assert found is not None and (found.stage, found.category) == (Stage.CONTROLLER_SETUP, UNKNOWN)
    assert found.evidence == ()
    timed_out = DaemonStatus(DaemonState.TIMEOUT, "x")
    found = diagnosis.run_diagnosis(1, tmp_path / "missing.json", daemon_after=timed_out)
    assert found is not None and found.category == "daemon-timeout"


def test_clean_run_has_no_diagnosis(tmp_path: Path) -> None:
    report = _write(tmp_path / "r.json", {"aggregate": {}})
    assert diagnosis.run_diagnosis(0, report, result_written=True) is None


def test_exit_0_without_a_report_is_diagnosed_without_guessing_the_stage(tmp_path: Path) -> None:
    found = diagnosis.run_diagnosis(0, tmp_path / "missing.json")
    assert found is not None
    assert (found.stage.value, found.category, found.result_written) == ("UNKNOWN", UNKNOWN, False)
    assert "the launcher exited 0 but left no loop report" in found.detail
    line = found.line("TARGET-EXPLORE")
    assert "stage=UNKNOWN category=UNKNOWN result=not-written evidence=none" in line


def test_unreadable_report(tmp_path: Path) -> None:
    report = tmp_path / "r.json"
    report.write_text("{not json", encoding="utf-8")
    for rc in (0, 1):
        found = diagnosis.run_diagnosis(rc, report)
        assert found is not None and (found.stage, found.category) == (Stage.LOOP, UNKNOWN)


@pytest.mark.parametrize(
    ("state", "category"),
    [(DaemonState.UNREACHABLE, "daemon-unreachable"), (DaemonState.TIMEOUT, "daemon-timeout")],
)
def test_daemon_and_image_stages(state: DaemonState, category: str) -> None:
    assert diagnosis.daemon_diagnosis(DaemonStatus(DaemonState.OK, "ok")) is None
    found = diagnosis.daemon_diagnosis(DaemonStatus(state, "why"))
    assert found is not None and (found.stage, found.category) == (Stage.PREFLIGHT, category)

    unknown = ImageLookup(ImageState.UNKNOWN, detail="no answer")
    found = diagnosis.image_diagnosis(unknown, DaemonStatus(state, "why"))
    assert found is not None and (found.stage, found.category) == (Stage.IMAGE, category)
    assert diagnosis.image_diagnosis(ImageLookup(ImageState.ABSENT)) is None
    found = diagnosis.image_diagnosis(unknown)
    assert found is not None and found.category == UNKNOWN
