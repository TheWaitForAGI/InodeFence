"""exploration_demo_report: same loop as historical, minus the version allowlist, labelled
an exploratory non-qualification run. Locks that historical_demo_report keeps its version gate
and that the two reports differ only by the exploration labelling (no docker; the heavy pieces
are stubbed so only the entry wrapper is exercised)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import scripts.run_effect_demo as rd
from scripts.run_effect_demo import exploration_demo_report, historical_demo_report

from inodefence.feedback import EffectSearchPolicy
from inodefence.mutator import MutationPolicy

IMAGE = "sha256:" + "0" * 64
# Stand-in backend: only bind/campaign are exercised and they are stubbed.
BACKEND: Any = object()


class _FakeTarget:
    def __init__(self, tar_version: str) -> None:
        self.tar_version = tar_version
        self.node_version = "22.22.0"


class _FakeResult:
    """Enough of a campaign result for the report assembly (streaming reads executed/retained)."""

    def __init__(self, executed: int = 0) -> None:
        self.executed = executed
        self.retained_case_ids: tuple[str, ...] = ()
        self.steps: list[Any] = []


def _stub_campaign(monkeypatch: pytest.MonkeyPatch, tar_version: str) -> None:
    """Make bind/campaign/report cheap so only the report-assembly wrapper runs."""
    monkeypatch.setattr(
        rd.NodeTarEffectTarget, "bind", classmethod(lambda cls, b, i, **k: _FakeTarget(tar_version))
    )
    monkeypatch.setattr(
        rd,
        "run_effect_campaign",
        lambda cases, produce, config, on_step=None, hooks=None: _FakeResult(),
    )
    base = {"demo_report_schema": 4, "steps": [], "retained_case_ids": [], "final_search_stats": {}}
    monkeypatch.setattr(rd, "effect_campaign_report", lambda result, producer: dict(base))
    monkeypatch.setattr(rd, "_historical_oracle_events", lambda result: [])


def test_exploration_defaults_to_the_registered_su_arm(monkeypatch: pytest.MonkeyPatch) -> None:
    # The explore default is the registered experiment's S-u arm, referenced from evaluation.rds:
    # S_U_STATE_RETENTION_UNIFORM retention + observed-names vocabulary (FIXED_BASELINE mutation).
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        rd.NodeTarEffectTarget, "bind", classmethod(lambda cls, b, i, **k: _FakeTarget("7.5.23"))
    )

    def fake_campaign(
        cases: Any, produce: Any, config: Any, on_step: Any = None, hooks: Any = None
    ) -> Any:
        captured["config"] = config
        return _FakeResult()

    monkeypatch.setattr(rd, "run_effect_campaign", fake_campaign)
    monkeypatch.setattr(
        rd,
        "effect_campaign_report",
        lambda result, producer: {
            "demo_report_schema": 4,
            "steps": [],
            "retained_case_ids": [],
            "final_search_stats": {},
        },
    )
    monkeypatch.setattr(rd, "_historical_oracle_events", lambda result: [])
    report = exploration_demo_report(BACKEND, IMAGE, "7.5.23", seed=1, budget=5)
    assert captured["config"].search_policy is EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM
    assert (
        captured["config"].mutation_policy
        is MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE
    )
    assert report["vocabulary_mode"] == "observed-names"


def test_exploration_report_is_labelled_non_qualification(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_campaign(monkeypatch, "7.5.23")
    report = exploration_demo_report(
        BACKEND, IMAGE, "7.5.23", seed=1, budget=5, requested_spec="latest"
    )
    assert report["label"] == "exploratory demo run"
    assert report["mode"] == "exploration"
    assert report["qualification"] is False
    assert report["requested_spec"] == "latest"
    assert report["node_tar_version"] == "7.5.23"
    assert report["requested_tar_version"] == "7.5.23"
    assert report["image_id"] == IMAGE


def test_exploration_matches_historical_except_the_labelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 7.5.2 is a historical catalog member, so historical passes its gate and both run the
    # same stubbed loop; the reports must then differ only by the exploration labelling.
    _stub_campaign(monkeypatch, "7.5.2")
    hist = historical_demo_report(BACKEND, IMAGE, "7.5.2", seed=1, budget=5)
    # Compare the per-case (streaming off) explore report against historical; streaming's aggregate
    # shape is a deliberate difference covered by its own tests.
    expl = exploration_demo_report(BACKEND, IMAGE, "7.5.2", seed=1, budget=5, stream=False)
    only_in_explore = {
        "qualification",
        "requested_spec",
        "case_records",
        "violation_inputs",
        "vocabulary_mode",  # exploration records its vocabulary mode; historical does not
        "observer_integrity_policy",  # and its observer policy
        "streaming",  # and whether the result streamed (aggregate) or listed every case
    }
    assert set(expl) - set(hist) == only_in_explore
    # timing is wall-clock and differs run-to-run by design; everything else is deterministic.
    differ = {k for k in hist if hist[k] != expl.get(k)}
    assert differ - {"timing"} == {"label", "mode"}
    assert hist["label"] == "demo run" and hist["mode"] == "historical"
    # Everything the loop produced (steps, search stats, retained corpus, checks) is identical.
    for shared in (
        "steps",
        "final_search_stats",
        "retained_case_ids",
        "native_checks",
        "node_version",
    ):
        assert hist[shared] == expl[shared]


def test_historical_still_rejects_an_unregistered_version_but_exploration_binds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Historical keeps its allowlist: 7.5.23 is refused before binding.
    with pytest.raises(ValueError):
        historical_demo_report(BACKEND, IMAGE, "7.5.23", budget=5)

    # Exploration has no version gate: it reaches bind for the same version.
    reached: list[str] = []

    def bind(cls: Any, backend: Any, image_id: str, **kw: Any) -> _FakeTarget:
        reached.append(image_id)
        raise RuntimeError("bind reached")  # stop before the real campaign

    monkeypatch.setattr(rd.NodeTarEffectTarget, "bind", classmethod(bind))
    with pytest.raises(RuntimeError, match="bind reached"):
        exploration_demo_report(BACKEND, IMAGE, "7.5.23", budget=5)
    assert reached == [IMAGE]  # no allowlist rejection before binding


def _violation_capture_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    violating: bool,
    status: Any = None,
    integrity_valid: bool = True,
    stream: bool = False,
) -> dict:
    """Drive exploration_demo_report with a fake run whose oracle verdict we control."""

    class _Verdict:
        def __init__(self, cid: str, hit: bool) -> None:
            self.contract_id = type("C", (), {"value": cid})()
            self.violated = hit

    verdicts = [_Verdict("C0", False), _Verdict("C1", violating), _Verdict("C2", False)]
    execution = type(
        "E", (), {"status": status if status is not None else rd.ExecutionStatus.SUCCESS}
    )()
    base = type("B", (), {"violations": verdicts, "execution": execution})()
    trace = type("T", (), {"integrity_valid": integrity_valid, "observation_failures": ()})()
    fake_run = type("R", (), {"base_result": base, "trace": trace})()
    monkeypatch.setattr(rd, "_native_effect_producer", lambda *a, **k: lambda case: fake_run)

    def fake_campaign(
        cases: Any, produce: Any, config: object, on_step: object = None, hooks: object = None
    ) -> object:
        produce(list(cases)[0])  # one real seed case, so build_tar produces real bytes
        return _FakeResult(executed=1)

    monkeypatch.setattr(rd, "run_effect_campaign", fake_campaign)
    monkeypatch.setattr(rd, "effect_campaign_report", lambda r, p: {"demo_report_schema": 4})
    monkeypatch.setattr(rd, "_historical_oracle_events", lambda r: [])
    monkeypatch.setattr(
        rd.NodeTarEffectTarget, "bind", classmethod(lambda cls, b, i, **k: _FakeTarget("7.5.23"))
    )
    return exploration_demo_report(BACKEND, IMAGE, "7.5.23", seed=1, budget=5, stream=stream)


def test_exploration_records_all_cases_but_saves_only_violating_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _violation_capture_report(monkeypatch, violating=True)
    (case,) = report["case_records"]  # every run is recorded with its verdict
    assert case["outcome"] == "judged" and case["termination"] == "success"
    assert case["c1"] is True and case["c0"] is False
    (saved,) = report["violation_inputs"]  # only the violating run's TAR is kept
    assert saved["run_index"] == case["run_index"]
    assert len(saved["tar_sha256"]) == 64 and saved["tar_b64"]


@pytest.mark.parametrize(
    ("status", "termination"),
    [
        (lambda: rd.ExecutionStatus.REJECTED, "rejected"),
        (lambda: rd.ExecutionStatus.FAILED, "failed"),
        (lambda: rd.ExecutionStatus.TIMED_OUT, "timed_out"),
    ],
)
def test_non_success_run_keeps_its_judgment_and_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch, status: Any, termination: str
) -> None:
    # A rejected / crashed / timed-out extraction is still a judged outcome (the oracle ran on the
    # snapshots): outcome stays "judged" and C0/C1/C2 are kept; the exit lands in termination, and a
    # violation left behind by a non-clean run is still captured.
    report = _violation_capture_report(monkeypatch, violating=True, status=status())
    (case,) = report["case_records"]
    assert case["outcome"] == "judged" and case["termination"] == termination
    assert case["c1"] is True and case["c0"] is False  # judgment kept despite the non-SUCCESS exit
    assert len(report["violation_inputs"]) == 1  # the violating input is still captured


def test_incomplete_observation_is_recorded_on_the_case(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _violation_capture_report(monkeypatch, violating=True, integrity_valid=False)
    (case,) = report["case_records"]
    # SUCCESS but the trace was not integrity-valid: judged, but observation_complete=False, so the
    # converter's CaseVerdict.needs_repro_check flags it (past audits mis-read hits from
    # invalid-trace runs as clean findings).
    assert case["outcome"] == "judged" and case["observation_complete"] is False


def test_exploration_saves_no_input_when_no_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _violation_capture_report(monkeypatch, violating=False)
    assert len(report["case_records"]) == 1 and report["violation_inputs"] == []


def test_live_dir_records_run_settings_from_actual_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json as _json

    from inodefence.sentinel_set import generate_sentinel_set

    sset = generate_sentinel_set(20261104, 5)
    monkeypatch.setattr(
        rd.NodeTarEffectTarget, "bind", classmethod(lambda cls, b, i, **k: _FakeTarget("7.5.23"))
    )
    monkeypatch.setattr(
        rd,
        "run_effect_campaign",
        lambda cases, produce, config, on_step=None, hooks=None: _FakeResult(),
    )
    monkeypatch.setattr(
        rd,
        "effect_campaign_report",
        lambda r, p: {
            "demo_report_schema": 4,
            "steps": [],
            "retained_case_ids": [],
            "final_search_stats": {},
        },
    )
    monkeypatch.setattr(rd, "_historical_oracle_events", lambda r: [])
    live = tmp_path / "live"
    rd.exploration_demo_report(
        BACKEND,
        IMAGE,
        "7.5.23",
        seed=1,
        budget=5,
        sentinel_set=sset,
        observer_integrity_continue=True,
        live_dir=live,
    )
    prog = _json.loads((live / "progress.json").read_text())
    rs = prog["run_settings"]
    assert rs["sentinel_count"] == 5 and rs["sentinel_seed"] == 20261104
    assert rs["observer_integrity_policy"] == "invalid-continue" and rs["profile"] == "full"
    assert prog["state"] == "finished"  # the try/else path closed it cleanly


def test_streaming_report_is_aggregate_plus_only_violating_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _violation_capture_report(monkeypatch, violating=True, stream=True)
    assert report["streaming"] is True
    assert "case_records" not in report  # streaming keeps aggregate counts, not every case
    agg = report["aggregate"]
    assert agg["runs_executed"] == 1 and agg["terminations"].get("success") == 1
    assert agg["unjudged_steps"] == 0 and agg["errors"] == 0
    (case,) = report["violation_cases"]  # only the violating case is listed
    assert case["c1"] is True and case["outcome"] == "judged"
    (saved,) = report["violation_inputs"]
    assert saved["run_index"] == case["run_index"]


def test_streaming_off_keeps_the_full_per_case_report(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _violation_capture_report(monkeypatch, violating=True, stream=False)
    assert report["streaming"] is False
    assert len(report["case_records"]) == 1 and "aggregate" not in report


# ---- untrusted trace with no violation is unjudged, not a clean negative (W1, 2026-11-16) ----


def _many_runs_report(
    monkeypatch: pytest.MonkeyPatch, runs: list[tuple[Any, bool, bool]], *, stream: bool
) -> dict:
    """``runs`` = (status, integrity_valid, violating) per run; drives the real record code."""

    class _Verdict:
        def __init__(self, cid: str, hit: bool) -> None:
            self.contract_id = type("C", (), {"value": cid})()
            self.violated = hit

    fakes = []
    for status, intact, hit in runs:
        verdicts = [_Verdict("C0", False), _Verdict("C1", hit), _Verdict("C2", False)]
        execution = type("E", (), {"status": status})()
        base = type("B", (), {"violations": verdicts, "execution": execution})()
        trace = type("T", (), {"integrity_valid": intact, "observation_failures": ()})()
        fakes.append(type("R", (), {"base_result": base, "trace": trace})())
    queue = iter(fakes)

    def producer(*a: Any, **k: Any) -> Any:
        # Like the real producer: one native check per run, and the streaming run counter.
        def produce(case: Any) -> Any:
            k["checks"].append({})
            if k.get("run_counter") is not None:
                k["run_counter"][0] += 1
            return next(queue)

        return produce

    monkeypatch.setattr(rd, "_native_effect_producer", producer)

    def fake_campaign(
        cases: Any, produce: Any, config: object, on_step: object = None, hooks: object = None
    ) -> object:
        seed = list(cases)[0]
        for _ in runs:
            produce(seed)
        return _FakeResult(executed=len(runs))

    monkeypatch.setattr(rd, "run_effect_campaign", fake_campaign)
    monkeypatch.setattr(rd, "effect_campaign_report", lambda r, p: {"demo_report_schema": 4})
    monkeypatch.setattr(rd, "_historical_oracle_events", lambda r: [])
    monkeypatch.setattr(
        rd.NodeTarEffectTarget, "bind", classmethod(lambda cls, b, i, **k: _FakeTarget("7.5.23"))
    )
    budget = len(runs)
    return exploration_demo_report(BACKEND, IMAGE, "7.5.23", seed=1, budget=budget, stream=stream)


def _verdict(report: dict, budget: int) -> str:
    from inodefence.drivers.explore_result import build_campaign_result
    from inodefence.drivers.run_target import PreparedTargetImage

    prepared = PreparedTargetImage(
        "node-tar", "7.5.23", "7.5.23", "img", "sha256:" + "a" * 64, True
    )
    result, _ = build_campaign_result(report, prepared, seed=1, budget=budget)
    return result.verdict.value


@pytest.mark.parametrize("stream", [True, False])
def test_twenty_successes_without_an_intact_trace_are_error_not_pass(
    monkeypatch: pytest.MonkeyPatch, stream: bool
) -> None:
    # W3 probe5 shape: 20 runs, every observation_complete False, no violation. Before: all
    # "judged" with C values -> PASS. Now each is run_error, so the result is ERROR.
    runs = [(rd.ExecutionStatus.SUCCESS, False, False)] * 20
    report = _many_runs_report(monkeypatch, runs, stream=stream)
    if stream:
        assert report["aggregate"]["unjudged_steps"] == 20
        assert report["aggregate"]["errors"] == 20
    else:
        assert {c["outcome"] for c in report["case_records"]} == {"run_error"}
    assert _verdict(report, 20) == "ERROR"


def test_untrusted_trace_keeps_a_violation_and_rejection_keeps_its_judgment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ok, rej, tmo = (
        rd.ExecutionStatus.SUCCESS,
        rd.ExecutionStatus.REJECTED,
        rd.ExecutionStatus.TIMED_OUT,
    )
    runs = [(ok, False, True), (rej, False, False), (tmo, False, False)] + [(ok, True, False)] * 7
    report = _many_runs_report(monkeypatch, runs, stream=False)
    outcomes = [(c["outcome"], c["c1"]) for c in report["case_records"]][:4]
    # D1: the clean timed-out run is unjudged; the rejection stays judged; the violation is kept.
    assert outcomes == [("judged", True), ("judged", False), ("run_error", None), ("judged", False)]
    assert _verdict(report, 10) == "FAIL"  # 1/10 unjudged is under the 0.2 ceiling


# ---- D1 regression matrix (user decision 2026-11-16): node-tar exploration record ----

_S, _R, _F, _T = (
    rd.ExecutionStatus.SUCCESS,
    rd.ExecutionStatus.REJECTED,
    rd.ExecutionStatus.FAILED,
    rd.ExecutionStatus.TIMED_OUT,
)
_CLEAN = (_S, True, False)  # success, intact trace, no violation

D1_CASES = [
    # (name, runs as (status, integrity_valid, violating), expected verdict)
    ("only normal rejections", [(_R, True, False)] * 10, "PASS"),
    ("all failed", [(_F, True, False)] * 10, "ERROR"),
    ("all timed out", [(_T, False, False)] * 10, "ERROR"),
    ("failed with an observed violation", [(_F, False, True)] + [_CLEAN] * 9, "FAIL"),
    ("success, broken trace, violation", [(_S, False, True)] + [_CLEAN] * 9, "FAIL"),
    ("unjudged exactly at the ceiling", [(_F, True, False)] * 2 + [_CLEAN] * 8, "PASS"),
    ("unjudged over the ceiling", [(_T, True, False)] * 3 + [_CLEAN] * 7, "ERROR"),
    ("nothing judgeable", [(_F, True, False)] * 5 + [(_S, False, False)] * 5, "ERROR"),
]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(("name", "runs", "expected"), D1_CASES, ids=[c[0] for c in D1_CASES])
def test_d1_matrix_record_aggregate_and_verdict_agree(
    monkeypatch: pytest.MonkeyPatch, stream: bool, name: str, runs: list, expected: str
) -> None:
    report = _many_runs_report(monkeypatch, runs, stream=stream)
    unjudged = sum(
        1
        for status, intact, hit in runs
        if not hit and (status in (_F, _T) or (status is _S and not intact))
    )
    if stream:
        agg = report["aggregate"]
        assert agg["unjudged_steps"] == unjudged == agg["errors"]
    else:
        records = report["case_records"]
        assert sum(r["outcome"] == "run_error" for r in records) == unjudged
    assert _verdict(report, len(runs)) == expected
    violating = [i for i, (_, _, hit) in enumerate(runs) if hit]
    # An observed violation is never lost: its input is saved whatever the exit or trace.
    assert [v["run_index"] for v in report["violation_inputs"]] == violating
