"""W4 Q2 (ii): node-tar FAST keeps the D064 interval and its result says which scope was measured.

``fast_acceptance`` is ``passed`` only for a run inside the measured scope (exact version, exact
policy, exact budget -- the narrowest reading, pending W4), and ``interval_on_unmeasured_scope``
for every other node-tar FAST run; both carry the measured ``acceptance_scope``. The interval is
not switched off outside the scope (no version gating). Older records without the label are still
read and shown as unlabeled. ``test_the_scope_is_filled`` FAILS until the follow-up result fills
``counted_seeds`` and ``rule_sha`` in the one constant, so this branch cannot ship unfilled.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from tests.test_fast_identity_driver import RECORD, _prepared, _report, _result, _session

import inodefence.drivers.explore_result as er
import inodefence.drivers.node_tar.explore as nte
import inodefence.drivers.run_target as rt
from inodefence.drivers.runtime import policy
from inodefence.target_result import (
    FAST_ACCEPTANCE_INTERVAL_ON_UNMEASURED_SCOPE,
    FAST_ACCEPTANCE_PASSED,
    NODE_TAR_ACCEPTED_FAST_SCOPE,
    SCOPE_KEYS,
    TargetResultError,
    from_json_dict,
    in_accepted_scope,
    load_target_result,
)
from inodefence.target_result_summary import render_summary

SCOPE = NODE_TAR_ACCEPTED_FAST_SCOPE


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        er, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )


def test_the_scope_is_filled() -> None:
    # Fails on purpose until the follow-up measurement's values are written into the constant.
    assert type(SCOPE["counted_seeds"]) is int and SCOPE["counted_seeds"] >= 1
    assert isinstance(SCOPE["rule_sha"], str) and SCOPE["rule_sha"].startswith("37651dbe")


def test_the_measured_scope() -> None:
    assert tuple(SCOPE) == SCOPE_KEYS
    assert (SCOPE["version"], SCOPE["policy"], SCOPE["budget"]) == ("7.5.2", "default", 2000)


@pytest.mark.parametrize(
    ("version", "policy_name", "budget", "inside"),
    [
        ("7.5.2", "default", 2000, True),
        ("7.5.23", "default", 2000, False),
        ("7.5.2", "default", 1999, False),
        ("7.5.2", "default", 2001, False),
        ("7.5.2", "uniform-b-grammar-v2-freeze-3-fixed-baseline-v1", 2000, False),
    ],
)
def test_inside_the_scope_means_an_exact_match(
    version: str, policy_name: str, budget: int, inside: bool
) -> None:
    assert in_accepted_scope(SCOPE, version, policy_name, budget) is inside


def _explore(monkeypatch, tmp: Path, version: str, budget: int, session: Any) -> dict[str, Any]:
    def fake(prepared: Any, *, out: Path, run_id: str, **_: Any) -> Path:
        path = nte.controller_report_path(out, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        report = _report(identity_checks=RECORD)
        report["aggregate"] = {**report["aggregate"], "runs_executed": budget,
                               "terminations": {"success": budget}}  # fmt: skip
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    monkeypatch.setattr(nte, "run_controller", fake)
    prepared = dataclasses.replace(_prepared(), version=version, requested=version)
    options = rt.ExploreOptions(budget=budget, seed=1, out=tmp, runtime=session)
    outcome = nte.explore(prepared, options)
    campaign = load_target_result(outcome.result_path).campaign
    assert campaign is not None
    return campaign.identity_checks or {}


def test_a_run_inside_the_scope_is_labeled_passed(monkeypatch, tmp_path: Path) -> None:
    checks = _explore(monkeypatch, tmp_path, "7.5.2", 2000, _session(policy.FAST))
    assert checks["fast_acceptance"] == FAST_ACCEPTANCE_PASSED
    assert checks["acceptance_scope"] == SCOPE and checks["interval"] == RECORD["interval"]


def test_a_run_outside_the_scope_keeps_the_interval_and_says_so(monkeypatch, tmp_path) -> None:
    checks = _explore(monkeypatch, tmp_path, "7.5.23", 20, _session(policy.FAST))
    assert checks["fast_acceptance"] == FAST_ACCEPTANCE_INTERVAL_ON_UNMEASURED_SCOPE
    assert checks["acceptance_scope"] == SCOPE
    assert checks["interval"] == policy.FAST_IDENTITY_CHECK_EVERY  # no version gating


def test_strict_carries_no_label(monkeypatch, tmp_path: Path) -> None:
    def fake(prepared: Any, *, out: Path, run_id: str, **_: Any) -> Path:
        path = nte.controller_report_path(out, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_report()), encoding="utf-8")
        return path

    monkeypatch.setattr(nte, "run_controller", fake)
    outcome = nte.explore(_prepared(), rt.ExploreOptions(budget=20, seed=1, out=tmp_path))
    raw = json.loads(outcome.result_path.read_text(encoding="utf-8"))
    assert "identity_checks" not in raw["campaign"]


def _with(checks: dict[str, Any]) -> dict[str, Any]:
    data = _result(_report(identity_checks=RECORD)).to_json_dict()
    data["campaign"]["identity_checks"] = checks
    return data


@pytest.mark.parametrize(
    ("checks", "match"),
    [
        ({**RECORD, "fast_acceptance": "passed"}, "acceptance_scope"),
        ({**RECORD, "acceptance_scope": SCOPE}, "fast_acceptance"),
        ({**RECORD, "fast_acceptance": "accepted", "acceptance_scope": SCOPE}, "fast_acceptance"),
        ({**RECORD, "fast_acceptance": "passed", "acceptance_scope": {"version": "7.5.2"}},
         "acceptance_scope"),
    ],
)  # fmt: skip
def test_a_malformed_label_is_refused(checks: dict[str, Any], match: str) -> None:
    with pytest.raises(TargetResultError, match=match):
        from_json_dict(_with(checks))


def test_an_older_record_without_the_label_is_read_and_shown_unlabeled() -> None:
    result = from_json_dict(_with(dict(RECORD)))  # no fast_acceptance, no scope: still accepted
    text = render_summary(result, source_name="result.json", inputs_verified=True)
    assert "| FAST 수용 표시 | 표시 없음(옛 기록) |" in text


def test_a_labeled_record_shows_its_label_verbatim() -> None:
    checks = {**RECORD, "fast_acceptance": FAST_ACCEPTANCE_PASSED, "acceptance_scope": SCOPE}
    text = render_summary(from_json_dict(_with(checks)), source_name="r.json", inputs_verified=True)
    assert "| FAST 수용 표시 | passed (측정 범위: 버전 7.5.2, 정책 default, 예산 2000) |" in text
