"""Streaming exploration's violation capture, end to end through the REAL effect loop.

These tests deliberately do NOT stub ``run_effect_campaign`` (an earlier stub-based test hid a
streaming-summary defect that only surfaced in a real Docker run). The loop runs for real; only the
per-case producer is replaced, returning a genuine ``EffectRunResult`` built from the synthetic
result with a controlled violation injected. That exercises the whole streaming path:
``exploration_demo_report`` -> ``LiveRecorder`` immediate disk write -> ``build_campaign_result``
reading the violations back from the live folder.

The real Docker + streaming + real-violation end to end (a violating input the extractor actually
produces) needs a node-tar release below the sealed floor and is deferred to after seal release;
here the capture is proven with injected violations instead.
"""

from __future__ import annotations

import dataclasses as dc
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import scripts.run_effect_demo as rd
from scripts.explore_result import build_campaign_result, write_result
from scripts.run_target import PreparedTargetImage

from inodefence.effect_synthetic import _result as synthetic_result
from inodefence.live_exploration import list_violation_cases, read_progress
from inodefence.model import (
    ArchiveCase,
    ChangeField,
    ContractId,
    EffectTargetTermination,
    ExecutionStatus,
    ObjectSnapshot,
    ObjectType,
    StateChange,
)
from inodefence.target_result import Verdict, from_json_dict, load_target_result

IMAGE = "sha256:" + "0" * 64
# Stand-in backend: bind and the per-case producer are replaced, so it is never called.
BACKEND: Any = object()
# The model couples a run's execution status, exit code and effect-trace termination; keep them
# consistent when injecting a non-success outcome.
_TERMINATION = {
    ExecutionStatus.REJECTED: EffectTargetTermination.REJECTED,
    ExecutionStatus.FAILED: EffectTargetTermination.FAILED,
}


class _FakeTarget:
    tar_version = "7.5.23"
    node_version = "22.22.0"


def _external_change(path: str) -> StateChange:
    """A fixed external change usable as C2 evidence; identical bytes -> stable fingerprint."""
    obj = ObjectSnapshot(
        path, ObjectType.REGULAR, 1, 10, 1, 0o600, 5, 1000, 1000, 10, 10,
        content_digest=sha256(b"state").hexdigest(),
    )  # fmt: skip
    return StateChange(path, None, obj, (ChangeField.EXISTENCE,))


# One fixed change -> every injected violation shares a single C2 fingerprint, so a budget above the
# per-fingerprint cap (3) exercises the dropped-at-cap path.
SENTINEL_CHANGE = _external_change("outside/sentinel.txt")
OTHER_CHANGE = _external_change("outside/other.txt")


def _inject_c2(
    base: Any, *, changes: tuple[StateChange, ...], status: ExecutionStatus | None
) -> Any:
    violated = tuple(
        dc.replace(
            verdict,
            violated=True,
            evidence=changes,
            explanation="injected external effect",
            limitations=("injected for test",),
        )
        if verdict.contract_id == ContractId.C2
        else verdict
        for verdict in base.violations
    )
    if status is None or status is ExecutionStatus.SUCCESS:
        execution = base.execution
    else:
        # The model couples exit code to status: a non-success run cannot keep exit code 0.
        execution = dc.replace(base.execution, status=status, exit_code=1)
    return dc.replace(base, violations=violated, execution=execution)


def _producer(
    *,
    violate: bool = True,
    status: ExecutionStatus | None = None,
    changes: tuple[StateChange, ...] = (SENTINEL_CHANGE,),
    raise_after: int | None = None,
) -> Callable[[ArchiveCase], Any]:
    """A real-result producer: synthetic result for the case, with a controlled C2 violation."""
    calls = [0]

    def produce(case: ArchiveCase) -> Any:
        calls[0] += 1
        if raise_after is not None and calls[0] > raise_after:
            raise RuntimeError("injected mid-loop failure")
        result = synthetic_result(case)
        if not violate:
            return result
        base = _inject_c2(result.base_result, changes=changes, status=status)
        if status is None or status is ExecutionStatus.SUCCESS:
            return dc.replace(result, base_result=base)
        trace = dc.replace(result.trace, termination=_TERMINATION[status])
        return dc.replace(result, base_result=base, trace=trace)

    return produce


def _run(
    monkeypatch: pytest.MonkeyPatch,
    live: Path,
    *,
    budget: int = 20,
    producer: Callable[[ArchiveCase], Any] | None = None,
    sentinel_set: Any = None,
    observer_integrity_continue: bool = False,
) -> dict:
    monkeypatch.setattr(
        rd.NodeTarEffectTarget, "bind", classmethod(lambda cls, b, i, **k: _FakeTarget())
    )
    monkeypatch.setattr(rd, "_native_effect_producer", lambda *a, **k: producer or _producer())
    return rd.exploration_demo_report(
        BACKEND,
        IMAGE,
        "7.5.23",
        seed=1,
        budget=budget,
        live_dir=live,
        stream=True,
        sentinel_set=sentinel_set,
        observer_integrity_continue=observer_integrity_continue,
    )


def _prepared() -> PreparedTargetImage:
    return PreparedTargetImage(
        "node-tar", "latest", "7.5.23", "inodefence-node-tar-registry:7.5.23",
        "sha256:" + "a" * 64, True,
    )  # fmt: skip


def test_streaming_captures_violations_to_disk_with_cap_and_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live"
    report = _run(monkeypatch, live, budget=20)
    # Every run violates the same C2 fingerprint; only per_fingerprint_cap (3) inputs are kept.
    capture = report["violation_capture"]
    assert capture["total"] == 20
    assert capture["retained"] == 3 and capture["dropped"] == 17
    assert capture["per_fingerprint_cap"] == 3 and capture["unique_fingerprints"] == 1
    ((fp, counts),) = capture["by_fingerprint"].items()
    assert fp.startswith("C2-") and counts == {"total": 20, "retained": 3}
    assert "by_fingerprint_truncated" not in capture and "multi_fingerprint_steps" not in capture
    # The report carries NO in-memory violation TARs (the recorder wrote them to disk instead).
    assert report.get("violation_inputs") == [] and report.get("violation_cases") == []
    # The inputs are already on disk -- not accumulated in memory until the end.
    disk = list_violation_cases(live)
    assert len(disk) == 3
    assert all(case["c2"] is True and case["tar_bytes"] > 0 for case in disk)


def test_result_json_points_to_the_disk_cases_and_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live"
    report = _run(monkeypatch, live, budget=20)
    result, tar_files = build_campaign_result(report, _prepared(), seed=1, budget=20, live_dir=live)
    assert result.verdict is Verdict.FAIL
    assert len(result.repro_inputs) == 3  # == retained, the cap-kept inputs
    # Every result pointer matches a disk case's id and SHA-256.
    disk = {f"step-{case['index']}": case for case in list_violation_cases(live)}
    for repro in result.repro_inputs:
        assert repro.case_id in disk
        assert repro.tar_sha256 == disk[repro.case_id]["tar_sha256"]
        assert sha256(tar_files[repro.tar_path]).hexdigest() == repro.tar_sha256
    # Written and re-read through the strict reader (re-hashes every saved input, checks the
    # violation_capture consistency: total == retained + dropped == len(repro_inputs)).
    out = write_result(tmp_path / "result", result, tar_files)
    loaded = load_target_result(out)
    assert loaded.verdict is Verdict.FAIL
    assert loaded.campaign is not None and loaded.campaign.violation_capture is not None
    assert loaded.campaign.violation_capture["dropped"] == 17


def test_forced_termination_leaves_the_violation_and_snapshot_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live"
    # Violate on the first case, then raise on the second: proves the first violation was written
    # AS IT HAPPENED, not buffered to a clean end that never comes.
    producer = _producer(raise_after=1)
    with pytest.raises(RuntimeError, match="injected mid-loop failure"):
        _run(monkeypatch, live, budget=20, producer=producer)
    disk = list_violation_cases(live)
    assert len(disk) == 1 and disk[0]["c2"] is True  # the pre-crash violation survived
    progress = read_progress(live)
    assert (
        progress is not None and progress["state"] == "failed"
    )  # final snapshot says how it ended
    assert progress["violations"]["steps"] == 1 and progress["violations"]["case_dirs_written"] == 1


def test_case_json_records_the_actual_run_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from inodefence.sentinel_set import generate_sentinel_set

    live = tmp_path / "live"
    sset = generate_sentinel_set(20261104, 5)
    _run(monkeypatch, live, budget=12, sentinel_set=sset, observer_integrity_continue=True)
    (case, *_) = list_violation_cases(live)
    settings = case["run_settings"]
    assert settings["sentinel_count"] == 5 and settings["sentinel_seed"] == 20261104
    assert (
        settings["observer_integrity_policy"] == "invalid-continue"
        and settings["profile"] == "full"
    )


def test_non_success_violation_is_flagged_needs_repro_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live"
    producer = _producer(status=ExecutionStatus.REJECTED)
    report = _run(monkeypatch, live, budget=12, producer=producer)
    disk = list_violation_cases(live)
    assert disk and all(case["status"] == "rejected" for case in disk)
    assert all(case["needs_repro_check"] is True for case in disk)  # violation on a non-clean exit
    # The converted result carries the same flag on its CaseVerdict.
    result, _ = build_campaign_result(report, _prepared(), seed=1, budget=12, live_dir=live)
    assert result.cases and all(case.needs_repro_check for case in result.cases)


def test_capture_separates_fingerprinted_and_unfingerprinted_buckets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two distinct C2 fingerprints across the run -> two real buckets; unique_fingerprints counts
    # only real fingerprints. (All runs violate, so there is no unfingerprinted bucket here; the
    # point is that unique_fingerprints == len(by_fingerprint) when no (unfingerprinted) key.)
    changes_by_call = [(SENTINEL_CHANGE,), (OTHER_CHANGE,)]

    calls = [0]

    def produce(case: ArchiveCase) -> Any:
        result = synthetic_result(case)
        changes = changes_by_call[calls[0] % 2]
        calls[0] += 1
        return dc.replace(
            result, base_result=_inject_c2(result.base_result, changes=changes, status=None)
        )

    live = tmp_path / "live"
    report = _run(monkeypatch, live, budget=20, producer=produce)
    capture = report["violation_capture"]
    assert capture["unique_fingerprints"] == 2
    assert len(capture["by_fingerprint"]) == 2
    assert all(key.startswith("C2-") for key in capture["by_fingerprint"])
    assert capture["total"] == 20
    # from_json_dict's consistency checks pass for the two-fingerprint shape.
    result, tar_files = build_campaign_result(report, _prepared(), seed=1, budget=20, live_dir=live)
    out = write_result(tmp_path / "result", result, tar_files)
    assert from_json_dict(__import__("json").loads(out.read_text())).verdict is Verdict.FAIL
