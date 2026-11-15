"""'No run extracted successfully' is surfaced the same way everywhere, and never changes a verdict.

An exploration in which every run was rejected (e.g. oras-go with the common seeds, which lack its
``d/`` directory-artifact prefix) reads PASS by the result contract, but its "no violation" rests
on runs that never wrote the archive out. The one wording (``no_extraction_warning``) appears in
the summary page, the explore driver's output line and ``inodefence status``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from inodefence.target_result import (
    JUDGED,
    CampaignInfo,
    CaseVerdict,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    Verdict,
    no_extraction_warning,
)
from inodefence.target_result_summary import render_summary


def test_warning_only_when_runs_were_recorded_and_none_succeeded() -> None:
    assert no_extraction_warning({}) is None  # nothing recorded (e.g. an old fixture result)
    assert no_extraction_warning({"success": 1, "rejected": 19}) is None
    warning = no_extraction_warning({"rejected": 18, "failed": 2})
    assert warning is not None
    assert warning.startswith("추출 성공 0건(전부 rejected 18 · failed 2)")
    assert "verdict unchanged" in warning


def _campaign(terminations: dict[str, int]) -> TargetResult:
    runs = sum(terminations.values())
    cases = tuple(
        CaseVerdict(f"step-{i}", JUDGED, False, False, False, "rejected", True) for i in range(runs)
    )
    return TargetResult(
        target="oras-go",
        axes=TargetAxes(target_version="2.6.2"),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cases=cases,
        repro_inputs=(),
        provenance=Provenance("a" * 40, False, "img", None),
        campaign=CampaignInfo(seed=123, budget=runs, runs_to_first_violation=None),
    )


def test_summary_shows_success_count_and_the_warning_without_changing_the_verdict() -> None:
    result = _campaign({"rejected": 20})
    assert result.verdict is Verdict.PASS and result.success_runs == 0
    text = render_summary(result, source_name="result.json", inputs_verified=True)
    assert "| 추출 성공 | 0건 |" in text
    assert "> **주의** — 추출 성공 0건(전부 rejected 20)" in text
    assert "**PASS**" in text  # verdict line unchanged


def test_live_status_shows_the_same_warning(tmp_path: Path) -> None:
    from tests.test_live_exploration import _recorder, _step

    from inodefence.live_exploration import render_live_status

    rec, clock, live = _recorder(tmp_path)
    for i in range(4):
        rec.on_step(_step(i, status="rejected", c0=False, c1=False, c2=False))
    rec._write_progress()  # flush (test only)
    text = render_live_status(live, now=clock.now + 1, display="live")
    assert "추출 성공 0건(전부 rejected 4)" in text
    rec.on_step(_step(4, c0=False, c1=False, c2=False))  # one success: no warning
    rec._write_progress()
    assert "추출 성공 0건" not in render_live_status(live, now=clock.now + 1, display="live")


def test_explore_driver_prints_the_warning_and_keeps_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import scripts.run_target_explore as rte
    from scripts.explore_result import write_result
    from scripts.run_target import ExploreOutcome

    result = _campaign({"rejected": 5})
    result_path = write_result(tmp_path / "res", result, {})

    def prepare(adapter, target, spec, *, image_tag_suffix, filters=()):  # type: ignore[no-untyped-def]
        from scripts.run_target import PreparedTargetImage

        return PreparedTargetImage(target, spec, spec, "img", "sha256:" + "b" * 64, True)

    def hook(prepared, options):  # type: ignore[no-untyped-def]
        return ExploreOutcome(result_path, "PASS", 5, 0)

    import dataclasses

    adapter = dataclasses.replace(
        rte.load_adapter("oras-go"), explore=hook, explore_min_budget=None
    )
    monkeypatch.setattr(rte, "prepare_target_image", prepare)
    monkeypatch.setattr(rte, "load_adapter", lambda name: adapter)
    argv = ["--target", "oras-go", "--version", "2.6.2", "--auto-prepare", "--budget", "5"]
    assert rte.main([*argv, "--out", str(tmp_path / "out")]) == 0  # PASS exit unchanged
    assert "TARGET-EXPLORE WARNING: 추출 성공 0건(전부 rejected 5)" in capsys.readouterr().out
