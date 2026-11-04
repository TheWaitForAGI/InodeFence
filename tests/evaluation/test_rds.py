"""R/D/S-u equal-vocabulary runner: vocabulary equality, uniform operator selection,
retention semantics and the T_first/U_viol per-cell summary (synthetic producer)."""

import dataclasses
import json
import random
from collections.abc import Callable
from hashlib import sha256

import pytest

from inodefence.campaign import CampaignOrigin
from inodefence.effect_synthetic import _object, _trace_for_case
from inodefence.evaluation.rds import (
    RdsArm,
    RdsCellAborted,
    RdsCellConfig,
    RVariant,
    VocabularyMode,
    arm_for_policy,
    arm_search_policy,
    is_hit,
    run_rds_cell,
    summarize_rds_steps,
    summary_record,
    vocabulary_pools,
)
from inodefence.feedback import EffectSearchPolicy, EffectSearchState, state_signature
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ContractId,
    EffectRunResult,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    ObjectSnapshot,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
)
from inodefence.mutator import MutationPolicy, m1
from inodefence.mutator.m1_addressing import COMPONENTS as PROTECTED_COMPONENTS
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts

MAIN_ARMS = (RdsArm.R, RdsArm.D, RdsArm.S_U)
# Sentinel names that no vocabulary hardcodes; the pool must read them from the
# BEFORE snapshot's EXTERNAL objects.
RANDOM_SENTINELS = ("k3v9.dat", "zq1.bin", "m77")


def _sentinels(content: bytes = b"sentinel") -> tuple[ObjectSnapshot, ...]:
    return tuple(
        _object(f"outside/{name}", dev=9, ino=90 + index, content=content)
        for index, name in enumerate(RANDOM_SENTINELS)
    )


def _snapshot(phase: SnapshotPhase, objects: tuple[ObjectSnapshot, ...]) -> StateSnapshot:
    return StateSnapshot(
        "/var/lib/inodefence/rds-test",
        phase,
        tuple(sorted(objects, key=lambda obj: obj.path)),
        tuple(sorted(f"outside/{name}" for name in RANDOM_SENTINELS)),
    )


def _custom_result(
    case: ArchiveCase,
    before_objects: tuple[ObjectSnapshot, ...],
    after_objects: tuple[ObjectSnapshot, ...],
) -> EffectRunResult:
    """Synthetic result with caller-chosen snapshots; the oracle runs for real on them."""
    before = _snapshot(SnapshotPhase.BEFORE, before_objects)
    after = _snapshot(SnapshotPhase.AFTER, after_objects)
    trace = dataclasses.replace(_trace_for_case(case), before=before, after=after)
    base = RunResult(
        case,
        sha256(case.case_id.encode()).hexdigest(),
        "ustar",
        ExecutionResult("synthetic", "1", ("synthetic",), ExecutionStatus.SUCCESS, 0, "", "", 0.01),
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )
    return EffectRunResult(base, trace)


def _extracted(case: ArchiveCase) -> tuple[ObjectSnapshot, ...]:
    return tuple(
        _object(f"extract/object-{index}", ino=100 + index) for index in range(len(case.entries))
    )


def _benign(case: ArchiveCase) -> EffectRunResult:
    return _custom_result(case, _sentinels(), _sentinels() + _extracted(case))


def _c2_hit(case: ArchiveCase) -> EffectRunResult:
    # The first sentinel's content changes: C2 (external effect) violated.
    sentinels = list(_sentinels())
    sentinels[0] = _object(f"outside/{RANDOM_SENTINELS[0]}", dev=9, ino=90, content=b"tampered")
    return _custom_result(case, _sentinels(), tuple(sentinels) + _extracted(case))


def _c1_hit(case: ArchiveCase) -> EffectRunResult:
    # An extraction object shares (st_dev, st_ino) with a sentinel: C1 violated.
    alias = _object("extract/object-0", dev=9, ino=90)
    return _custom_result(case, _sentinels(), _sentinels() + (alias,) + _extracted(case)[1:])


_Producer = Callable[[ArchiveCase], EffectRunResult]


class _Script:
    """Call-indexed producer: ``special[k]`` replaces the benign result at call k."""

    def __init__(self, special: dict[int, _Producer | Exception]) -> None:
        self.calls = 0
        self.special = special

    def __call__(self, case: ArchiveCase) -> EffectRunResult:
        index = self.calls
        self.calls += 1
        action = self.special.get(index)
        if action is None:
            return _benign(case)
        if isinstance(action, Exception):
            raise action
        return action(case)


def _cell(arm: RdsArm, producer, *, seed: int = 9001, budget: int = 24, **kwargs):
    return run_rds_cell(minimal_seed_corpus(), producer, RdsCellConfig(arm, seed, budget, **kwargs))


# ---- arm ↔ policy realization -------------------------------------------------------


def test_arm_policy_ids_are_explicit_and_invertible() -> None:
    assert arm_search_policy(RdsArm.R) == EffectSearchPolicy.R_UNRETAINED_WALK
    assert (
        arm_search_policy(RdsArm.R, RVariant.SEED_RESTART)
        == EffectSearchPolicy.R_UNRETAINED_SEED_RESTART
    )
    assert arm_search_policy(RdsArm.D) == EffectSearchPolicy.D_STRUCTURE_COVERAGE
    assert arm_search_policy(RdsArm.S_U) == EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM
    assert arm_search_policy(RdsArm.S_A) == EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT
    assert arm_for_policy(EffectSearchPolicy.R_UNRETAINED_SEED_RESTART) == (
        RdsArm.R,
        RVariant.SEED_RESTART,
    )
    assert arm_for_policy(EffectSearchPolicy.D_STRUCTURE_COVERAGE) == (RdsArm.D, None)
    with pytest.raises(ValueError):
        arm_for_policy(EffectSearchPolicy.P1_EFFECT_RETENTION)
    # Historical arm IDs are untouched.
    assert EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT.value == (
        "effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1"
    )
    assert (
        MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK.value == "uniform-generic-m1-escape-hardlink-v1"
    )


@pytest.mark.parametrize("mode", tuple(VocabularyMode))
def test_vocabulary_mode_fixes_one_mutation_policy_for_every_arm(mode: VocabularyMode) -> None:
    policies = {RdsCellConfig(arm, 1, 8, mode).mutation_policy for arm in RdsArm}
    assert len(policies) == 1


# ---- vocabulary equality ------------------------------------------------------------


def test_fixed_observed_pool_is_identical_across_arms_and_read_from_before_snapshot() -> None:
    pools = {}
    for arm in MAIN_ARMS:
        cell = _cell(arm, _Script({}), vocabulary_mode=VocabularyMode.OBSERVED_NAMES)
        summary = cell.summary
        assert (
            summary.mutation_policy == MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE
        )
        pools[arm] = (set(summary.vocabulary_pool_after_seed), set(summary.vocabulary_pool_final))
        # Fixed once: never grows after the seed baseline.
        assert summary.vocabulary_pool_after_seed == summary.vocabulary_pool_final
        # Sentinel names come from the observed BEFORE tree, not from any hardcoded token.
        assert set(RANDOM_SENTINELS) | {"outside"} <= set(summary.vocabulary_pool_final)
        assert "sentinel.txt" not in summary.vocabulary_pool_final
        assert summary.observed_protected_paths == tuple(
            sorted(f"outside/{n}" for n in RANDOM_SENTINELS)
        )
    assert len({frozenset(after) for after, _ in pools.values()}) == 1
    assert len({frozenset(final) for _, final in pools.values()}) == 1


def test_fixed_pool_ignores_names_the_runs_produce_while_accumulated_pool_grows() -> None:
    def noisy(case: ArchiveCase) -> EffectRunResult:
        # Every run creates an extraction object with a fresh name.
        extra = _object(f"extract/fresh-{case.case_id[:6]}", ino=7)
        return _custom_result(case, _sentinels(), _sentinels() + _extracted(case) + (extra,))

    fixed = _cell(RdsArm.S_U, noisy, vocabulary_mode=VocabularyMode.OBSERVED_NAMES).summary
    grown = _cell(
        RdsArm.S_U, noisy, vocabulary_mode=VocabularyMode.OBSERVED_NAMES_ACCUMULATED
    ).summary
    assert not any(token.startswith("fresh-") for token in fixed.vocabulary_pool_final)
    assert any(token.startswith("fresh-") for token in grown.vocabulary_pool_final)
    assert set(fixed.vocabulary_pool_final) < set(grown.vocabulary_pool_final)


def test_static_vocabulary_modes_report_their_constant_pools() -> None:
    generic = _cell(RdsArm.D, _Script({}), vocabulary_mode=VocabularyMode.GENERIC).summary
    protected = _cell(
        RdsArm.D, _Script({}), vocabulary_mode=VocabularyMode.PROTECTED_COMPONENTS
    ).summary
    assert generic.vocabulary_pool_final == m1.COMPONENTS
    assert protected.vocabulary_pool_final == PROTECTED_COMPONENTS
    assert vocabulary_pools(VocabularyMode.OBSERVED_NAMES, (), 0) == (m1.COMPONENTS, m1.COMPONENTS)


# ---- uniform operator selection -----------------------------------------------------


@pytest.mark.parametrize("arm", MAIN_ARMS)
def test_main_arms_select_operators_uniformly_at_every_step(arm: RdsArm) -> None:
    cell = _cell(arm, _Script({}), budget=40)
    mutations = [step for step in cell.campaign.steps if step.origin == CampaignOrigin.MUTATION]
    assert mutations
    for step in mutations:
        evidence = step.scheduler_evidence
        assert evidence is not None
        assert all(weight == 1 for _, weight in evidence.weights_before)
        assert all(weight == 1 for _, weight in evidence.weights_after)
        assert evidence.selected_weight == 1 and evidence.reward == 0


def test_operator_selection_is_the_same_uniform_draw_in_every_main_arm() -> None:
    # Given the same RNG state, the scheduler of each main arm picks the same slot:
    # the draw does not depend on the arm.
    from inodefence.effect_scheduler import EffectUniformMutationScheduler
    from inodefence.mutator import operator_ids

    picks = []
    for arm in MAIN_ARMS:
        config = RdsCellConfig(arm, 5, 8)
        scheduler = EffectUniformMutationScheduler()
        rng = random.Random(777)
        picks.append(
            tuple(
                scheduler.choose_operator(operator_ids(config.mutation_policy), rng).operator_id
                for _ in range(64)
            )
        )
    assert len(set(picks)) == 1


# ---- retention semantics -----------------------------------------------------------


def test_r_walk_retains_nothing_and_walks_through_children() -> None:
    cell = _cell(RdsArm.R, _Script({}), budget=16)
    steps = cell.campaign.steps
    initial = set(cell.campaign.initial_case_ids)
    assert cell.campaign.retained_case_ids == ()
    assert cell.summary.retained_cases == 0 and cell.summary.r_variant == RVariant.WALK
    mutations = [step for step in steps if step.origin == CampaignOrigin.MUTATION]
    assert mutations[0].parent_case_id in initial
    for previous, step in zip(mutations, mutations[1:], strict=False):
        assert step.parent_case_id == previous.result.base_result.case.case_id


def test_r_seed_restart_draws_every_parent_from_the_seeds() -> None:
    cell = _cell(RdsArm.R, _Script({}), budget=16, r_variant=RVariant.SEED_RESTART)
    initial = set(cell.campaign.initial_case_ids)
    mutations = [s for s in cell.campaign.steps if s.origin == CampaignOrigin.MUTATION]
    assert mutations and all(step.parent_case_id in initial for step in mutations)
    assert cell.summary.r_variant == RVariant.SEED_RESTART
    assert cell.summary.search_policy == EffectSearchPolicy.R_UNRETAINED_SEED_RESTART


def test_d_admits_seeds_and_only_structure_coverage_novelty() -> None:
    seeds = minimal_seed_corpus()
    state = EffectSearchState(seeds, EffectSearchPolicy.D_STRUCTURE_COVERAGE)
    for seed in seeds:
        assert state.consider(_benign(seed)).retained
    same_shape = ArchiveCase((ArchiveEntry("x.txt", EntryType.REGULAR, content=b"y"),))
    assert not state.consider(_benign(same_shape)).admission_eligible
    deeper = ArchiveCase((ArchiveEntry("p/q.txt", EntryType.REGULAR, content=b"y"),))
    nested = _custom_result(deeper, _sentinels(), _sentinels() + (_object("extract/p/q", ino=200),))
    decision = state.consider(nested)
    assert decision.admission_eligible and decision.retained
    # A second observation of the same new feature is no longer novel for D.
    again = ArchiveCase((ArchiveEntry("p/r.txt", EntryType.REGULAR, content=b"z"),))
    assert not state.consider(
        _custom_result(again, _sentinels(), _sentinels() + (_object("extract/p/r", ino=201),))
    ).admission_eligible


def test_s_u_admission_equals_p3_and_main_arms_share_the_diagnostic_channel() -> None:
    seeds = minimal_seed_corpus()
    policies = (
        EffectSearchPolicy.R_UNRETAINED_WALK,
        EffectSearchPolicy.D_STRUCTURE_COVERAGE,
        EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM,
        EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT,
    )
    states = {policy: EffectSearchState(seeds, policy) for policy in policies}
    rng = random.Random(3)
    cases = list(seeds)
    for _ in range(12):
        cases.append(m1.add_escaping_hardlink(cases[-1], rng))
    for case in cases:
        result = _benign(case)
        decisions = {policy: states[policy].consider(result) for policy in policies}
        eligible = {d.feedback_eligible for d in decisions.values()}
        keys = {d.new_effect_keys for d in decisions.values()}
        assert len(eligible) == 1 and len(keys) == 1
        s_u = decisions[EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM]
        s_a = decisions[EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT]
        assert s_u.admission_eligible == s_a.admission_eligible
        assert not decisions[EffectSearchPolicy.R_UNRETAINED_WALK].admission_eligible
    assert len(states[EffectSearchPolicy.R_UNRETAINED_WALK].entries) == 0


# ---- per-cell summary: T_first / U_viol ---------------------------------------------


def test_hit_definition_is_c1_or_c2_not_c0() -> None:
    case = minimal_seed_corpus()[0]
    assert not is_hit(_benign(case))
    assert is_hit(_c2_hit(case)) and is_hit(_c1_hit(case))
    c0_only = _custom_result(
        case, _sentinels(), _sentinels() + _extracted(case) + (_object("outside/new", ino=5),)
    )
    assert {v.contract_id for v in c0_only.base_result.violations if v.violated} == {ContractId.C0}
    assert not is_hit(c0_only)


def test_summary_complete_no_hit_is_right_censored_at_budget() -> None:
    summary = _cell(RdsArm.S_U, _Script({}), budget=20).summary
    assert summary.complete and not summary.aborted and not summary.hit
    assert (summary.t_first, summary.t_first_event, summary.t_first_censored) == (20, 0, True)
    assert summary.u_viol == 0 and summary.first_c1 is None and summary.first_c2 is None
    assert summary.executions_completed == 20 and summary.initial_cases == 4


def test_summary_first_hit_is_one_based_execution_count_and_u_viol_dedups() -> None:
    # Hit at call 7 (step index 7) with C2, the same C2 class again at 10, C1 at 12.
    producer = _Script({7: _c2_hit, 10: _c2_hit, 12: _c1_hit})
    summary = _cell(RdsArm.D, producer, budget=20).summary
    assert summary.hit and summary.first_hit_step_index == 7
    assert (summary.t_first, summary.t_first_event, summary.t_first_censored) == (8, 1, False)
    assert summary.hit_steps == 3
    assert summary.u_viol == 2  # one C2 class (seen twice) + one C1 class
    assert summary.first_c2 == 8 and summary.first_c1 == 13 and summary.first_c0 is None
    assert summary.complete


def test_summary_abort_is_censored_at_completed_executions() -> None:
    producer = _Script({9: RuntimeError("observer evidence integrity")})
    with pytest.raises(RdsCellAborted) as info:
        _cell(RdsArm.R, producer, budget=20)
    summary = info.value.summary
    assert summary.aborted and not summary.complete
    assert summary.abort_step_index == 9 and summary.executions_completed == 9
    assert "RuntimeError" in str(summary.abort_reason)
    assert (summary.t_first, summary.t_first_event, summary.t_first_censored) == (9, 0, True)
    assert len(info.value.steps) == 9 and isinstance(info.value.__cause__, RuntimeError)


def test_summary_rejects_inconsistent_abort_declarations() -> None:
    cell = _cell(RdsArm.R, _Script({}), budget=8)
    with pytest.raises(ValueError):
        summarize_rds_steps(cell.campaign.steps[:5], cell.config)
    with pytest.raises(ValueError):
        summarize_rds_steps(
            cell.campaign.steps[:5], cell.config, aborted_at_step=4, abort_reason="x"
        )


def test_summary_record_is_json_ready_and_passes_sentinel_set_through() -> None:
    sentinel_set = {
        "generator_id": "sentinel-names/seed-random-v1",
        "generator_seed": 9001,
        "count": 3,
        "names": list(RANDOM_SENTINELS),
    }
    cell = run_rds_cell(
        minimal_seed_corpus(),
        _Script({}),
        RdsCellConfig(RdsArm.S_U, 9001, 8),
        sentinel_set=sentinel_set,
    )
    record = summary_record(cell.summary)
    text = json.dumps(record, sort_keys=True)
    assert json.loads(text)["sentinel_set"] == sentinel_set
    assert record["arm"] == "S-u" and record["r_variant"] is None
    assert record["search_policy"] == EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM.value
    assert record["vocabulary_mode"] == "observed-names" and record["schema_version"] == 1
    assert isinstance(record["vocabulary_pool_final"], list)


def test_cell_is_deterministic_for_a_seed() -> None:
    first = _cell(RdsArm.S_U, _Script({}), budget=16)
    second = _cell(RdsArm.S_U, _Script({}), budget=16)
    assert first.campaign == second.campaign and first.summary == second.summary


def test_observed_names_mode_dispatches_fixed_baseline_policy_in_campaign_loop() -> None:
    # The loop reads extra components only through the state-aware policies; the
    # fixed-baseline ID is one of them and must not raise in apply_operator.
    from inodefence.mutator import MutationOperatorId, apply_operator

    case = minimal_seed_corpus()[0]
    attempt = apply_operator(
        case,
        random.Random(1),
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE,
        MutationOperatorId.ADD_HARDLINK,
        extra_components=("outside", "k3v9.dat"),
    )
    assert attempt.mutation_policy == MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE
