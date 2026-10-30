"""The M4 decompress A/C/D roll-up reduces campaign reports to the identity-vs-coverage verdict.

These pin the reduction logic (arm labelling, per-rung rate/first, the frame-observed decoupling
count, and the C-vs-D contrast) against synthetic reports, so the scientific verdict cannot drift
from a careless edit. They do not run decompress; the native run produces the real reports.
"""

from scripts.analyze_m4_decompress_abcd import arm_label, cd_contrast, cell_metrics

from inodefence.feedback import EffectSearchPolicy


def _step(
    case_id: str,
    *,
    boundary: bool,
    external: bool,
    new_attempt_keys: int = 0,
    retained: bool = False,
    c1: bool = False,
) -> dict:
    return {
        "case_id": case_id,
        "boundary_attempt_present": boundary,
        "external_resolve_present": external,
        "new_attempt_keys": new_attempt_keys,
        "retained": retained,
        "oracle": {"C0": False, "C1": c1, "C2": False},
    }


def _report(search_policy: EffectSearchPolicy, seed: int, steps: list[dict]) -> dict:
    return {
        "decompress_campaign_schema": 1,
        "config": {
            "random_seed": seed,
            "execution_budget": len(steps),
            "mutation_policy": "uniform-generic-m1-escape-hardlink-v1",
            "search_policy": search_policy.value,
            "adaptive_scheduler": True,
        },
        "discovered_violation": any(s["oracle"]["C1"] for s in steps),
        "steps": steps,
    }


def test_arm_label_maps_search_policy_to_a_c_d() -> None:
    assert arm_label(EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT.value) == "C"
    assert arm_label(EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT.value) == "D"
    # The floor is anything that admits neither gradient rung.
    assert arm_label(EffectSearchPolicy.P1_EFFECT_RETENTION.value) == "A"


def test_cell_metrics_reads_per_rung_rate_and_first_execution() -> None:
    report = _report(
        EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT,
        600,
        [
            _step("s", boundary=False, external=False),
            _step("x", boundary=False, external=True, new_attempt_keys=1, retained=True),
            _step("y", boundary=True, external=True, new_attempt_keys=1, retained=True),
        ],
    )
    metrics = cell_metrics(report)
    assert metrics["arm"] == "C"
    assert metrics["seed"] == 600
    assert metrics["boundary_attempt"]["rate"] == 1 / 3
    assert metrics["boundary_attempt"]["executions_to_first"] == 3
    assert metrics["external_resolve"]["rate"] == 2 / 3
    assert metrics["external_resolve"]["executions_to_first"] == 2


def test_cell_metrics_counts_shapeless_decoupled_and_c_exclusive_admissions() -> None:
    # Step "x": external present, boundary absent -> the decompress shapeless escape (decoupled).
    # It carries a new attempt key, so on the C arm it is a novelty D (coverage) could never earn.
    report = _report(
        EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT,
        601,
        [
            _step("s", boundary=False, external=False),
            _step("x", boundary=False, external=True, new_attempt_keys=1, retained=True),
            _step("z", boundary=True, external=True, new_attempt_keys=1, retained=True),
        ],
    )
    metrics = cell_metrics(report)
    assert metrics["decoupled_external_steps"] == 1  # frame-observed: external & not boundary
    assert metrics["external_only_novel_keys"] == 1  # admitted a key only the C rung could


def test_cd_contrast_flags_operationally_identical_vs_separated() -> None:
    steps_same = [
        _step("s", boundary=False, external=False),
        _step("e", boundary=True, external=True, new_attempt_keys=1, retained=True),
    ]
    c = cell_metrics(_report(EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT, 602, steps_same))
    d = cell_metrics(_report(EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT, 602, steps_same))
    same = cd_contrast(c, d)
    assert same["operationally_identical_case_sequence"] is True
    assert same["identical_on_both_rungs"] is True

    # A diverged case sequence (C admitted a shapeless escape D was blind to) -> separated.
    c_div = cell_metrics(
        _report(
            EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT,
            603,
            [
                _step("s", boundary=False, external=False),
                _step("x", boundary=False, external=True, new_attempt_keys=1, retained=True),
            ],
        )
    )
    d_div = cell_metrics(
        _report(
            EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT,
            603,
            [
                _step("s", boundary=False, external=False),
                _step("w", boundary=False, external=False),
            ],
        )
    )
    separated = cd_contrast(c_div, d_div)
    assert separated["operationally_identical_case_sequence"] is False
