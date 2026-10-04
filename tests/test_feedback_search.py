"""Search comparators preserve full diagnostics while changing parent admission."""

import json
import random
from dataclasses import replace

import pytest

from inodefence.feedback import Corpus, SearchDecision, SearchPolicy, SearchState
from inodefence.model import ExecutionStatus, canonical_json
from test_feedback_corpus import _case, _creation, _result


@pytest.mark.parametrize("policy", tuple(SearchPolicy))
def test_same_signature_new_c0_distinguishes_admission_from_analysis(policy) -> None:
    seed, child = _case("seed"), _case("child")
    state = SearchState((seed,), policy)
    first = state.consider(_result(seed))
    assert first.retained == (policy != SearchPolicy.B0)
    outcome = replace(_result(child), violations=(_creation(),))
    raw = canonical_json(outcome)
    decision = state.consider(outcome)
    assert not decision.state_novel and decision.new_violation_fingerprints
    assert decision.interesting
    assert decision.retained == (policy == SearchPolicy.B3)
    assert decision.admission_eligible == (policy == SearchPolicy.B3)
    assert canonical_json(outcome) == raw
    repeated = state.consider(replace(outcome, case=_case("another")))
    assert not repeated.interesting and not repeated.retained
    assert state.stats.observations == 3
    assert state.stats.interesting_observations == 2
    assert state.stats.unique_states == state.stats.unique_violation_fingerprints == 1
    assert (
        state.stats.retained_cases
        == {SearchPolicy.B0: 0, SearchPolicy.B1: 1, SearchPolicy.B3: 2}[policy]
    )


@pytest.mark.parametrize("policy", tuple(SearchPolicy))
def test_duplicate_case_new_outcome_advances_indexes_without_duplicate_parent(policy) -> None:
    case = _case("seed")
    state = SearchState((case,), policy)
    state.consider(_result(case))
    admission = state.entries
    new = replace(_result(case, b"changed"), violations=(_creation(),))
    decision = state.consider(new)
    assert decision.interesting and not decision.retained
    assert decision.already_retained == (policy != SearchPolicy.B0)
    assert state.entries == admission
    assert state.stats.unique_states == 2
    assert not state.consider(replace(new, case=_case("other"))).interesting


@pytest.mark.parametrize("status", tuple(ExecutionStatus))
def test_b0_advances_previous_child_for_every_status_without_selection_draws(status) -> None:
    seeds = (_case("a"), _case("b"))
    state = SearchState(seeds, SearchPolicy.B0)
    for seed in seeds:
        state.consider(_result(seed))
    rng, expected = random.Random(91), random.Random(91)
    assert state.select_case(rng) == expected.choice(seeds)
    assert rng.getstate() == expected.getstate()
    for index in range(6):
        child = _case(str(index))
        result = _result(child)
        exit_code = (
            None
            if status == ExecutionStatus.TIMED_OUT
            else 1
            if status != ExecutionStatus.SUCCESS
            else 0
        )
        result = replace(
            result, execution=replace(result.execution, status=status, exit_code=exit_code)
        )
        state.consider(result)
        assert state.select_case(rng) == child == state.active_case
        assert rng.getstate() == expected.getstate()
    assert state.entries == () and state.stats.retained_cases == 0


def test_b0_noop_advances_with_identical_case_and_diagnostic_novelty_is_irrelevant() -> None:
    seed = _case("a")
    first, second = SearchState((seed,), SearchPolicy.B0), SearchState((seed,), SearchPolicy.B0)
    rngs = (random.Random(2), random.Random(2))
    for state, rng in zip((first, second), rngs, strict=True):
        state.consider(_result(seed))
        assert state.select_case(rng) == seed
    for index in range(8):
        child = seed if index % 2 else _case(str(index))
        plain = _result(child)
        novel = replace(_result(child, str(index).encode()), violations=(_creation(str(index)),))
        first.consider(plain)
        second.consider(novel)
        assert first.select_case(rngs[0]) == second.select_case(rngs[1]) == child
        assert rngs[0].getstate() == rngs[1].getstate()
    assert first.stats.unique_states != second.stats.unique_states
    assert first.entries == second.entries == ()


def test_b3_core_matches_legacy_corpus_decisions_stats_and_rng_sequence() -> None:
    seeds = (_case("a"), _case("b"))
    state, legacy = SearchState(seeds, SearchPolicy.B3), Corpus()
    outcomes = [_result(seed) for seed in seeds]
    outcomes += [
        replace(_result(_case("c")), violations=(_creation(),)),
        _result(_case("d"), b"new"),
    ]
    outcomes += [outcomes[0], replace(outcomes[0], violations=(_creation("archive/second"),))]
    for outcome in outcomes:
        actual, old = state.consider(outcome), legacy.consider(outcome)
        assert (
            actual.case_id,
            actual.state_novel,
            actual.new_violation_fingerprints,
            actual.already_retained,
            actual.interesting,
            actual.retained,
        ) == (
            old.case_id,
            old.state_novel,
            old.new_violation_fingerprints,
            old.already_retained,
            old.interesting,
            old.retained,
        )
        assert state.entries == legacy.entries and state.stats == legacy.stats
    rng, old_rng = random.Random(19), random.Random(19)
    assert [state.select_case(rng) for _ in range(50)] == [
        legacy.select_case(old_rng) for _ in range(50)
    ]
    assert rng.getstate() == old_rng.getstate()


@pytest.mark.parametrize("policy", (SearchPolicy.B1, SearchPolicy.B3))
def test_seed_admission_follows_novelty_and_uniform_parents(policy) -> None:
    seeds = (_case("a"), _case("b"), _case("c"))
    state = SearchState(seeds, policy)
    assert state.consider(_result(seeds[0])).retained
    assert not state.consider(_result(seeds[1])).retained
    assert state.consider(_result(seeds[2], b"other")).retained
    rng, expected = random.Random(44), random.Random(44)
    pool = (seeds[0], seeds[2])
    assert [state.select_case(rng) for _ in range(100)] == [
        expected.choice(pool) for _ in range(100)
    ]
    assert rng.getstate() == expected.getstate()


def test_invalid_policy_and_seed_phase_fail_without_rng_or_index_changes() -> None:
    seed, rng = _case("a"), random.Random(1)
    for cases, policy in (
        ((), SearchPolicy.B0),
        ((seed, seed), SearchPolicy.B1),
        ((seed,), "unknown"),
    ):
        with pytest.raises(ValueError):
            SearchState(cases, policy)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SearchPolicy("unknown")
    state = SearchState((seed,), SearchPolicy.B1)
    before = rng.getstate()
    with pytest.raises(ValueError, match="seed phase"):
        state.select_case(rng)
    with pytest.raises(ValueError, match="cases/order"):
        state.consider(_result(_case("wrong")))
    assert rng.getstate() == before and state.stats.observations == 0


def test_explicit_admission_is_serialized_and_validated() -> None:
    decision = SearchDecision("case", True, (), False, False, True)
    assert decision.interesting and not decision.retained
    assert json.loads(canonical_json(decision))["value"]["admission_eligible"] is False
    with pytest.raises(ValueError, match="bool"):
        replace(decision, admission_eligible=1)
