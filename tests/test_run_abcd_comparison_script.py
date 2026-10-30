"""The A/B/C/D reference-run serializers round-trip harness output to plain JSON.

These stay subprocess-free: they build a real ArmComparison through the synthetic
monkeypatched campaign path (no extractor runs) and check the script's dict
builders produce JSON-serializable records with every arm and stringified enums.
"""

import json

from scripts.run_abcd_comparison import _comparison_dict, _metrics_dict, _spec_dict

import inodefence.campaign as campaign
from inodefence.evaluation.arm_comparison import Arm, run_abcd_comparison
from test_campaign import UnusedTarget
from test_feedback_corpus import _case, _result


def _seeds():
    return (_case("first"), _case("second"))


def _benign(calls):
    def execute(case, target, *, sentinels):
        calls.append(case)
        return _result(case, str(len(calls)).encode())

    return execute


def test_comparison_dict_is_json_serializable_with_all_arms(monkeypatch):
    monkeypatch.setattr(campaign, "run_case", _benign([]))
    comparison = run_abcd_comparison(_seeds(), UnusedTarget(), random_seed=5, execution_budget=7)
    data = _comparison_dict(comparison)
    text = json.dumps(data, sort_keys=True)  # must not raise
    assert isinstance(text, str)
    assert set(data["metrics"]) == {arm.value for arm in Arm}
    assert set(data["arm_specs"]) == {arm.value for arm in Arm}
    assert data["execution_budget"] == 7
    random_arm = data["metrics"][Arm.A.value]
    assert random_arm["search_policy"] == "unretained-walk-v1"
    assert random_arm["right_censored_at"] == 7
    assert random_arm["first_violation_censored"] is True
    assert "no effectiveness ranking" in data["comparison_status"]


def test_spec_and_metrics_dicts_stringify_enums(monkeypatch):
    monkeypatch.setattr(campaign, "run_case", _benign([]))
    comparison = run_abcd_comparison(
        _seeds(), UnusedTarget(), random_seed=1, execution_budget=6, arms=(Arm.C,)
    )
    spec = _spec_dict(comparison.arm_specs[Arm.C])
    assert spec["search_policy"] == "state-v2-or-violation-v1-uniform-parent-v1"
    assert spec["mutation_policy"] == "uniform-generic-m1-v1"
    metrics = _metrics_dict(comparison.metrics[Arm.C])
    assert metrics["feedback_projection"] == "state-v3-full-key-v1"
    assert json.dumps(metrics, sort_keys=True)  # serializable
