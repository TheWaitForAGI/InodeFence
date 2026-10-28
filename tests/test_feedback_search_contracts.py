"""Cross-policy execution-status and deterministic composition contracts."""

import random
from dataclasses import replace

import pytest

from inodefence.feedback import FeedbackProjection, SearchPolicy, SearchState, state_signature
from inodefence.model import ExecutionStatus
from inodefence.mutator import MutationPolicy, mutate_with_policy
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts
from test_feedback_corpus import _case, _object, _result


def _status(result, status):
    exit_code = (
        None
        if status == ExecutionStatus.TIMED_OUT
        else (0 if status == ExecutionStatus.SUCCESS else 1)
    )
    return replace(result, execution=replace(result.execution, status=status, exit_code=exit_code))


@pytest.mark.parametrize("policy", tuple(SearchPolicy))
@pytest.mark.parametrize("status", tuple(ExecutionStatus))
def test_status_changes_do_not_admit_cases_but_semantic_state_changes_do(policy, status):
    seed = _case("seed")
    state = SearchState((seed,), policy)
    state.consider(_result(seed))
    same = state.consider(_status(_result(_case("same")), status))
    assert not same.interesting and not same.admission_eligible and not same.retained
    changed = state.consider(_status(_result(_case("changed"), b"new semantic output"), status))
    assert changed.state_novel and changed.feedback_key_novel
    # D keys on extraction structure, not content: a content-only state change
    # adds no new coverage feature, so D (unlike B1/B3) does not admit it.
    assert changed.retained == (policy in (SearchPolicy.B1, SearchPolicy.B3))
    assert state.stats.observations == 3 and state.stats.unique_states == 2


@pytest.mark.parametrize("policy", tuple(SearchPolicy))
@pytest.mark.parametrize("mutation", (MutationPolicy.M1, MutationPolicy.M1_NO_REORDER))
@pytest.mark.parametrize("projection", tuple(FeedbackProjection))
def test_core_search_mutation_composition_repeats_lineage_with_volatile_evidence_differences(
    policy, mutation, projection
):
    def exercise(shift):
        seeds = (_case("a"), _case("b"))
        state = SearchState(seeds, policy, projection=projection)
        rng = random.Random(131)
        lineage = []

        def observe(case, index):
            # Synthetic semantic output and evidence channels, independent of raw IDs/status.
            result = _result(
                case, str(sum(len(entry.content or b"") for entry in case.entries) % 3).encode()
            )
            result = _status(result, tuple(ExecutionStatus)[index % len(ExecutionStatus)])
            if index % 4 == 0:
                added = _object("archive/" + str(index % 8), inode=30)
                result = replace(
                    result,
                    after=replace(
                        result.after,
                        objects=tuple(
                            sorted((*result.after.objects, added), key=lambda obj: obj.path)
                        ),
                    ),
                )

            def relabel(snapshot):
                return replace(
                    snapshot,
                    objects=tuple(
                        replace(
                            obj,
                            st_dev=obj.st_dev + shift,
                            st_ino=obj.st_ino + shift,
                            mtime_ns=obj.mtime_ns + shift,
                            ctime_ns=obj.ctime_ns + shift,
                        )
                        for obj in snapshot.objects
                    ),
                )

            # Preserve semantic relations/change labels while varying the raw allocation.
            before, after = relabel(result.before), relabel(result.after)
            result = replace(
                result,
                before=before,
                after=after,
                changes=compare_states(before, after),
                signature=state_signature(before, after),
                violations=evaluate_contracts(before, after),
            )
            decision = state.consider(result)
            return decision

        for index, seed in enumerate(seeds):
            observe(seed, index)
        for index in range(2, 24):
            parent = state.select_case(rng)
            child = mutate_with_policy(parent, rng, mutation)
            decision = observe(child, index)
            lineage.append((parent.case_id, child.case_id, decision))
        return lineage, state.entries, state.stats, state.unique_feedback_keys, rng.getstate()

    assert exercise(0) == exercise(9000)
