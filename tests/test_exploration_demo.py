"""exploration_demo_report: same loop as historical, minus the version allowlist, labelled
an exploratory non-qualification run. Locks that historical_demo_report keeps its version gate
and that the two reports differ only by the exploration labelling (no docker; the heavy pieces
are stubbed so only the entry wrapper is exercised)."""

from __future__ import annotations

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


def _stub_campaign(monkeypatch: pytest.MonkeyPatch, tar_version: str) -> None:
    """Make bind/campaign/report cheap so only the report-assembly wrapper runs."""
    monkeypatch.setattr(
        rd.NodeTarEffectTarget, "bind", classmethod(lambda cls, b, i, **k: _FakeTarget(tar_version))
    )
    monkeypatch.setattr(rd, "run_effect_campaign", lambda cases, produce, config, on_step: object())
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

    def fake_campaign(cases: Any, produce: Any, config: Any, on_step: Any) -> Any:
        captured["config"] = config
        return object()

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
    expl = exploration_demo_report(BACKEND, IMAGE, "7.5.2", seed=1, budget=5)
    only_in_explore = {
        "qualification",
        "requested_spec",
        "case_records",
        "violation_inputs",
        "vocabulary_mode",  # exploration records its vocabulary mode; historical does not
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


def _violation_capture_report(monkeypatch: pytest.MonkeyPatch, *, violating: bool) -> dict:
    """Drive exploration_demo_report with a fake run whose oracle verdict we control."""

    class _Verdict:
        def __init__(self, cid: str, hit: bool) -> None:
            self.contract_id = type("C", (), {"value": cid})()
            self.violated = hit

    verdicts = [_Verdict("C0", False), _Verdict("C1", violating), _Verdict("C2", False)]
    execution = type("E", (), {"status": rd.ExecutionStatus.SUCCESS})()
    base = type("B", (), {"violations": verdicts, "execution": execution})()
    fake_run = type("R", (), {"base_result": base})()
    monkeypatch.setattr(rd, "_native_effect_producer", lambda *a, **k: lambda case: fake_run)

    def fake_campaign(cases: Any, produce: Any, config: object, on_step: object = None) -> object:
        produce(list(cases)[0])  # one real seed case, so build_tar produces real bytes
        return object()

    monkeypatch.setattr(rd, "run_effect_campaign", fake_campaign)
    monkeypatch.setattr(rd, "effect_campaign_report", lambda r, p: {"demo_report_schema": 4})
    monkeypatch.setattr(rd, "_historical_oracle_events", lambda r: [])
    monkeypatch.setattr(
        rd.NodeTarEffectTarget, "bind", classmethod(lambda cls, b, i, **k: _FakeTarget("7.5.23"))
    )
    return exploration_demo_report(BACKEND, IMAGE, "7.5.23", seed=1, budget=5)


def test_exploration_records_all_cases_but_saves_only_violating_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _violation_capture_report(monkeypatch, violating=True)
    (case,) = report["case_records"]  # every run is recorded with its verdict
    assert case["outcome"] == "extracted" and case["c1"] is True and case["c0"] is False
    (saved,) = report["violation_inputs"]  # only the violating run's TAR is kept
    assert saved["run_index"] == case["run_index"]
    assert len(saved["tar_sha256"]) == 64 and saved["tar_b64"]


def test_exploration_saves_no_input_when_no_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _violation_capture_report(monkeypatch, violating=False)
    assert len(report["case_records"]) == 1 and report["violation_inputs"] == []
