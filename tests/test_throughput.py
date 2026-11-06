"""Unit tests for the throughput + parity comparison analysis (no Docker)."""

import pytest

from inodefence.evaluation.execution_parity import (
    CanonicalSnapshot,
    ParityStep,
    ParitySubject,
    ResetVerification,
)
from inodefence.evaluation.throughput import (
    CampaignTiming,
    CellParity,
    MethodMeasurement,
    ThroughputComparison,
    build_comparison,
    render_report,
)


def _d(obj: object) -> dict:
    assert isinstance(obj, dict)
    return obj


def _l(obj: object) -> list:
    assert isinstance(obj, list)
    return obj


def _timing(
    run_id: str, *, wall: float, cases: int, aborts: int = 0, retries: int = 0
) -> CampaignTiming:
    return CampaignTiming(run_id, 7, "default", None, wall, cases, aborts, retries)


def _step(index: int, case_id: str, *, retry: int = 0, digest_tag: bytes = b"x") -> ParityStep:
    from hashlib import sha256

    obj = (
        f"extract/{case_id}",
        "regular",
        1,
        0o644,
        1,
        1000,
        1000,
        None,
        sha256(digest_tag).hexdigest(),
    )
    snap = CanonicalSnapshot("after", ("outside/sentinel",), (obj,), ())
    return ParityStep(index, case_id, (("C0", False),), (), snap, snap, retry)


def _subject(
    label: str,
    case_ids: tuple[str, ...],
    *,
    retry_at: tuple[int, ...] = (),
    digest_tag: bytes = b"x",
) -> ParitySubject:
    steps = tuple(
        _step(i, cid, retry=(1 if i in retry_at else 0), digest_tag=digest_tag)
        for i, cid in enumerate(case_ids)
    )
    resets = tuple(ResetVerification(i, False, False) for i in range(len(case_ids)))
    iso = (("image_id", "sha256:" + "a" * 64),)
    return ParitySubject(label, steps, iso, resets)


def _measurement(
    method: str, *, startup: float, total: float, timings: tuple[CampaignTiming, ...]
) -> MethodMeasurement:
    return MethodMeasurement(method, startup, total, timings)


# ---- MethodMeasurement derived metrics ---------------------------------------


def test_method_measurement_aggregates() -> None:
    m = _measurement(
        "worker-pool",
        startup=5.0,
        total=20.0,
        timings=(
            _timing("a", wall=12.0, cases=10, aborts=1, retries=2),
            _timing("b", wall=15.0, cases=10),
        ),
    )
    assert m.total_cases == 20
    assert m.total_aborts == 1
    assert m.total_retries == 2
    assert m.campaign_wall_sum == 27.0
    assert m.cases_per_second == pytest.approx(1.0)  # 20 cases / 20s


def test_cases_per_second_zero_when_no_wall() -> None:
    m = _measurement("x", startup=0.0, total=0.0, timings=(_timing("a", wall=0.0, cases=0),))
    assert m.cases_per_second == 0.0


# ---- comparison + speedup ----------------------------------------------------


def test_speedup_and_parity_passed() -> None:
    per_case = _measurement(
        "per-case", startup=4.0, total=40.0, timings=(_timing("c0", wall=38.0, cases=6),)
    )
    pool = _measurement(
        "worker-pool", startup=6.0, total=20.0, timings=(_timing("c0", wall=14.0, cases=6),)
    )
    subjects_a = {"c0": _subject("per-case", ("x", "y"))}
    subjects_b = {"c0": _subject("worker-pool", ("x", "y"))}
    comparison = build_comparison(per_case, pool, subjects_a, subjects_b)
    assert comparison.speedup == pytest.approx(2.0)
    assert comparison.parity_passed is True
    assert len(comparison.cells) == 1
    assert comparison.cells[0].run_id == "c0"


def test_build_comparison_pairs_only_shared_run_ids() -> None:
    per_case = _measurement("per-case", startup=0.0, total=10.0, timings=())
    pool = _measurement("worker-pool", startup=0.0, total=10.0, timings=())
    subjects_a = {"c0": _subject("per-case", ("x",)), "c1": _subject("per-case", ("z",))}
    subjects_b = {"c0": _subject("worker-pool", ("x",)), "c2": _subject("worker-pool", ("w",))}
    comparison = build_comparison(per_case, pool, subjects_a, subjects_b)
    assert [cell.run_id for cell in comparison.cells] == ["c0"]


def test_parity_failure_surfaces_in_comparison() -> None:
    per_case = _measurement("per-case", startup=0.0, total=10.0, timings=())
    pool = _measurement("worker-pool", startup=0.0, total=5.0, timings=())
    # Same case ids, but the worker-pool run observed a different content digest.
    subjects_a = {"c0": _subject("per-case", ("x",), digest_tag=b"baseline")}
    subjects_b = {"c0": _subject("worker-pool", ("x",), digest_tag=b"different")}
    comparison = build_comparison(per_case, pool, subjects_a, subjects_b)
    assert comparison.parity_passed is False
    assert comparison.cells[0].report.core_parity is False


# ---- report rendering --------------------------------------------------------


def test_render_report_shape() -> None:
    per_case = _measurement(
        "per-case", startup=4.0, total=40.0, timings=(_timing("c0", wall=38.0, cases=6),)
    )
    pool = _measurement(
        "worker-pool",
        startup=6.0,
        total=20.0,
        timings=(_timing("c0", wall=14.0, cases=6, retries=3),),
    )
    subjects_a = {"c0": _subject("per-case", ("x", "y"))}
    subjects_b = {"c0": _subject("worker-pool", ("x", "y"), retry_at=(1,))}
    report = render_report(build_comparison(per_case, pool, subjects_a, subjects_b))
    assert report["schema"] == "worker-pool-throughput-parity-v1"
    assert _d(report["summary"])["speedup"] == pytest.approx(2.0)
    assert _d(report["summary"])["cells_compared"] == 1
    assert _d(report["per_case"])["cases_per_second"] == pytest.approx(0.15)
    assert _d(report["worker_pool"])["total_retries"] == 3  # from the campaign timing
    cell = _d(_l(report["parity"])[0])
    assert cell["run_id"] == "c0"
    assert cell["both_retry_free"] is False
    assert _d(_l(cell["retried_steps"])[0])["index"] == 1
    assert _d(_l(cell["retried_steps"])[0])["matches_retry_free"] is True


# ---- validation --------------------------------------------------------------


def test_campaign_timing_rejects_negative_wall() -> None:
    with pytest.raises(ValueError):
        CampaignTiming("a", 7, "default", None, -1.0, 1, 0, 0)


def test_method_measurement_rejects_non_timing() -> None:
    with pytest.raises(ValueError):
        MethodMeasurement("x", 0.0, 1.0, ("not a timing",))  # type: ignore[arg-type]


def test_cell_parity_requires_report() -> None:
    with pytest.raises(ValueError):
        CellParity("c0", object())  # type: ignore[arg-type]


def test_comparison_requires_measurements() -> None:
    with pytest.raises(ValueError):
        ThroughputComparison(object(), object(), ())  # type: ignore[arg-type]
