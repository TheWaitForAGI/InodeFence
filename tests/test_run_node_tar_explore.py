"""Explore engine pure core: version exclusion gate, run->case mapping, campaign result mapping."""

import json
from types import SimpleNamespace
from typing import cast

import pytest
from scripts.run_node_tar_explore import (
    EXPLORE_MUTATION_POLICY,
    EXPLORE_OBSERVED_CONTRACTS,
    ExploreCase,
    build_explore_result,
    excluded_explore_version,
    explore_case_from_run,
)

from inodefence.effect_pipeline import NativeEffectRun
from inodefence.model import ExecutionStatus
from inodefence.target_result import RUN_ERROR, ResultMode, Verdict, from_json_dict

CONFIRMATORY = ("7.4.4", "7.5.2", "7.5.3")


def test_mutation_policy_is_the_token_clean_arm() -> None:
    # Research integrity: the vocabulary must not contain the victim's name.
    assert EXPLORE_MUTATION_POLICY.value == "uniform-generic-m1-escape-hardlink-v1"


@pytest.mark.parametrize("version", CONFIRMATORY)
def test_confirmatory_versions_are_refused(version: str) -> None:
    reason = excluded_explore_version(version, confirmatory=CONFIRMATORY)
    assert reason is not None and "confirmatory" in reason


@pytest.mark.parametrize("version", ["7.0.1", "7.4.3", "7.4.4"])
def test_pre_7_5_or_confirmatory_old_versions_refused(version: str) -> None:
    assert excluded_explore_version(version, confirmatory=CONFIRMATORY) is not None


@pytest.mark.parametrize("version", ["7.5.1", "7.5.8", "7.5.23", "7.6.0"])
def test_in_scope_versions_are_allowed(version: str) -> None:
    assert excluded_explore_version(version, confirmatory=CONFIRMATORY) is None


def test_unrecognized_version_refused() -> None:
    reason = excluded_explore_version("latest", confirmatory=CONFIRMATORY)
    assert reason is not None and "unrecognized" in reason


def test_default_confirmatory_set_reads_from_historical_targets() -> None:
    # No injected set: the real frozen catalog pair / holdout must still be refused.
    assert excluded_explore_version("7.5.2") is not None
    assert excluded_explore_version("7.0.1") is not None  # floor, independent of the set


def _fake_run(status: ExecutionStatus, c0: bool, c1: bool, c2: bool) -> NativeEffectRun:
    # A duck-typed stand-in: explore_case_from_run reads only status and the contract verdicts.
    violations = [
        SimpleNamespace(contract_id=SimpleNamespace(value=name), violated=flag)
        for name, flag in (("C0", c0), ("C1", c1), ("C2", c2))
    ]
    base = SimpleNamespace(execution=SimpleNamespace(status=status), violations=violations)
    return cast(NativeEffectRun, SimpleNamespace(result=SimpleNamespace(base_result=base)))


def test_explore_case_from_run_success_maps_the_oracle_tristate() -> None:
    case = explore_case_from_run(_fake_run(ExecutionStatus.SUCCESS, False, True, True), b"tar")
    assert (case.outcome, case.c0, case.c1, case.c2) == ("extracted", False, True, True)
    assert case.violated is True


def test_explore_case_from_run_failure_is_a_run_error_with_no_observation() -> None:
    case = explore_case_from_run(_fake_run(ExecutionStatus.FAILED, False, False, False), b"tar")
    assert case == ExploreCase(RUN_ERROR, None, None, None, b"tar")
    assert case.violated is False


def _result(*cases: ExploreCase, seed: int = 7, budget: int = 20):
    return build_explore_result(
        target_version="7.5.1",
        image_ref="inodefence-node-tar-effect:7.5.1-explore",
        image_id=None,
        engine_sha="a" * 40,
        engine_dirty=False,
        seed=seed,
        budget=budget,
        cases=cases,
    )


def test_build_result_is_campaign_mode_with_block_and_first_violation() -> None:
    result = _result(
        ExploreCase("extracted", False, False, False, b"a"),
        ExploreCase("extracted", True, False, False, b"b"),  # first violation at run 2
        ExploreCase("extracted", False, True, True, b"c"),
    )
    assert result.mode is ResultMode.CAMPAIGN
    assert result.observed_contracts == EXPLORE_OBSERVED_CONTRACTS
    assert result.verdict is Verdict.FAIL
    assert result.campaign is not None
    assert result.campaign.runs_to_first_violation == 2
    assert result.campaign.seed == 7 and result.campaign.budget == 20
    assert [c.case_id for c in result.cases] == ["step-0", "step-1", "step-2"]
    assert result.repro_inputs[0].tar_path == "inputs/step-0.tar"
    # Round-trips through the strict reader (campaign block and all).
    assert from_json_dict(json.loads(result.dumps())) == result


def test_build_result_all_clean_is_pass_with_no_first_violation() -> None:
    result = _result(
        ExploreCase("extracted", False, False, False, b"a"),
        ExploreCase("extracted", False, False, False, b"b"),
    )
    assert result.verdict is Verdict.PASS
    assert result.campaign is not None and result.campaign.runs_to_first_violation is None


def test_build_result_run_error_gives_error_verdict_and_null_contracts() -> None:
    result = _result(
        ExploreCase("extracted", False, False, False, b"a"),
        ExploreCase(RUN_ERROR, None, None, None, b"b"),
    )
    assert result.verdict is Verdict.ERROR
    step1 = result.cases[1]
    assert (step1.outcome, step1.c0, step1.c1, step1.c2) == (RUN_ERROR, None, None, None)
    assert result.campaign is not None and result.campaign.runs_to_first_violation is None
