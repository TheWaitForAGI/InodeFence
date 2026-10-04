"""Bounded caller orchestration contracts without filesystem execution."""

import random
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

import inodefence.campaign as campaign
from inodefence.campaign import CampaignConfig, CampaignOrigin, run_campaign
from inodefence.feedback import Corpus, state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
)
from inodefence.model.provenance import SourceProvenance, TargetProvenance
from inodefence.mutator import mutate
from inodefence.provenance import freeze_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets import TargetAdapter


def _case(name: str) -> ArchiveCase:
    return ArchiveCase((ArchiveEntry(name, EntryType.REGULAR, content=b"seed"),))


def _result(case: ArchiveCase, status: ExecutionStatus = ExecutionStatus.SUCCESS) -> RunResult:
    before = StateSnapshot("/var/lib/inodefence/synthetic", SnapshotPhase.BEFORE, (), ())
    after = replace(before, phase=SnapshotPhase.AFTER)
    exit_code = {
        ExecutionStatus.SUCCESS: 0,
        ExecutionStatus.REJECTED: 2,
        ExecutionStatus.FAILED: 1,
        ExecutionStatus.TIMED_OUT: None,
    }[status]
    return RunResult(
        case,
        case.case_id,
        "synthetic-test",
        ExecutionResult("controlled", "test", (), status, exit_code, "", "", 0.0),
        before,
        after,
        (),
        state_signature(before, after),
        (),
    )


class UnusedTarget:
    @property
    def provenance(self) -> TargetProvenance:
        return TargetProvenance("controlled", "test", None)

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        raise AssertionError("unit tests must not execute a target")


@pytest.fixture
def executions(monkeypatch: pytest.MonkeyPatch) -> list[ArchiveCase]:
    calls: list[ArchiveCase] = []

    def execute(
        case: ArchiveCase, target: TargetAdapter, *, sentinels: tuple[SentinelSpec, ...]
    ) -> RunResult:
        calls.append(case)
        return _result(case)

    monkeypatch.setattr(campaign, "run_case", execute)
    return calls


@pytest.mark.parametrize("budget", (2, 3, 12))
def test_exact_budget_seed_order_and_lineage(budget: int, executions: list[ArchiveCase]) -> None:
    initial = (_case("b"), _case("a"))
    result = run_campaign(initial, UnusedTarget(), CampaignConfig(17, budget))
    assert len(executions) == len(result.steps) == budget
    assert executions[:2] == list(initial)
    assert result.initial_case_ids == tuple(case.case_id for case in initial)
    assert tuple(step.index for step in result.steps) == tuple(range(budget))
    for step in result.steps[:2]:
        assert step.origin == CampaignOrigin.SEED
        assert step.parent_case_id is None
    for step in result.steps[2:]:
        assert step.origin == CampaignOrigin.MUTATION
        assert step.parent_case_id == initial[0].case_id  # same synthetic state retains only first


@pytest.mark.parametrize("budget", (0, -1))
def test_nonpositive_budget_rejected(budget: int) -> None:
    with pytest.raises(ValueError, match="execution_budget"):
        CampaignConfig(1, budget)


@pytest.mark.parametrize("seed,budget", ((True, 1), (1.5, 1), (1, True), (1, 2.5)))
def test_config_requires_integer_seed_and_budget(seed: int, budget: int) -> None:
    with pytest.raises(ValueError):
        CampaignConfig(seed, budget)


@pytest.mark.parametrize(
    "initial,budget,message",
    (
        ((), 1, "non-empty"),
        ((_case("a"), _case("b")), 1, "initial cases"),
        ((_case("a"), _case("a")), 2, "duplicate"),
    ),
)
def test_invalid_initial_cases_rejected_before_execution(
    initial: tuple[ArchiveCase, ...], budget: int, message: str, executions: list[ArchiveCase]
) -> None:
    with pytest.raises(ValueError, match=message):
        run_campaign(initial, UnusedTarget(), CampaignConfig(1, budget))
    assert executions == []


def test_same_inputs_generate_same_cases_and_parent_lineage(executions: list[ArchiveCase]) -> None:
    config = CampaignConfig(1234, 25)
    initial = (_case("a"), _case("b"))
    first = run_campaign(initial, UnusedTarget(), config)
    second = run_campaign(initial, UnusedTarget(), config)
    assert first == second
    assert len({step.result.case.case_id for step in first.steps}) > 2


def test_seeds_do_not_consume_rng_and_selection_precedes_mutation(
    monkeypatch: pytest.MonkeyPatch, executions: list[ArchiveCase]
) -> None:
    initial = (_case("a"), _case("b"))
    expected_rng = random.Random(234)
    expected_corpus = Corpus()
    for case in initial:
        expected_corpus.consider(_result(case))
    parent = expected_corpus.select_case(expected_rng)
    expected_child = mutate(parent, expected_rng)
    expected_state = expected_rng.getstate()
    observed_states: list[object] = []

    def mutation(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
        assert executions == list(initial)
        child = mutate(case, rng)
        observed_states.append(rng.getstate())
        return child

    monkeypatch.setattr(campaign, "mutate", mutation)
    result = run_campaign(initial, UnusedTarget(), CampaignConfig(234, 3))
    assert result.steps[2].result.case == expected_child
    assert result.steps[2].parent_case_id == parent.case_id
    assert observed_states == [expected_state]


def test_global_random_state_untouched(executions: list[ArchiveCase]) -> None:
    before = random.getstate()
    run_campaign((_case("a"),), UnusedTarget(), CampaignConfig(9, 12))
    assert random.getstate() == before


def test_noop_is_executed_without_retry(
    monkeypatch: pytest.MonkeyPatch, executions: list[ArchiveCase]
) -> None:
    mutations: list[ArchiveCase] = []

    def noop(case: ArchiveCase, rng: random.Random) -> ArchiveCase:
        mutations.append(case)
        return case

    monkeypatch.setattr(campaign, "mutate", noop)
    initial = _case("a")
    result = run_campaign((initial,), UnusedTarget(), CampaignConfig(8, 6))
    assert executions == [initial] * 6
    assert mutations == [initial] * 5
    assert len(result.steps) == 6
    assert result.final_corpus_stats.observations == 6
    assert result.retained_case_ids == (initial.case_id,)


@pytest.mark.parametrize("status", tuple(ExecutionStatus))
def test_all_target_statuses_count_and_reach_feedback(
    monkeypatch: pytest.MonkeyPatch, status: ExecutionStatus
) -> None:
    def execute(
        case: ArchiveCase, target: TargetAdapter, *, sentinels: tuple[SentinelSpec, ...]
    ) -> RunResult:
        return _result(case, status)

    monkeypatch.setattr(campaign, "run_case", execute)
    result = run_campaign((_case("a"),), UnusedTarget(), CampaignConfig(7, 5))
    assert len(result.steps) == result.final_corpus_stats.observations == 5
    assert all(step.result.execution.status == status for step in result.steps)


@pytest.mark.parametrize("failure_at", (0, 2))
def test_unexpected_run_error_propagates_and_stops(
    monkeypatch: pytest.MonkeyPatch, failure_at: int
) -> None:
    error = RuntimeError("harness unavailable")
    calls = 0

    def execute(
        case: ArchiveCase, target: TargetAdapter, *, sentinels: tuple[SentinelSpec, ...]
    ) -> RunResult:
        nonlocal calls
        calls += 1
        if calls == failure_at + 1:
            raise error
        return _result(case)

    monkeypatch.setattr(campaign, "run_case", execute)
    with pytest.raises(RuntimeError) as caught:
        run_campaign((_case("a"),), UnusedTarget(), CampaignConfig(7, 5))
    assert caught.value is error
    assert calls == failure_at + 1


def test_final_stats_and_admission_order_match_feedback_replay(
    executions: list[ArchiveCase],
) -> None:
    result = run_campaign((_case("b"), _case("a")), UnusedTarget(), CampaignConfig(3, 15))
    replay = Corpus()
    for step in result.steps:
        assert replay.consider(step.result) == step.feedback
    assert result.final_corpus_stats == replay.stats
    assert result.retained_case_ids == tuple(entry.case.case_id for entry in replay.entries)


def test_records_and_input_cases_remain_immutable(executions: list[ArchiveCase]) -> None:
    initial = [_case("a"), _case("b")]
    before = tuple(initial)
    result = run_campaign(initial, UnusedTarget(), CampaignConfig(31, 10))
    assert tuple(initial) == before
    initial.clear()
    assert result.initial_case_ids == tuple(case.case_id for case in before)
    for record in (result.config, result, result.steps[0]):
        with pytest.raises(FrozenInstanceError):
            setattr(record, fields(record)[0].name, "change")
        assert not hasattr(record, "__dict__")
    assert isinstance(result.steps, tuple) and isinstance(result.retained_case_ids, tuple)


def test_sentinel_configuration_is_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    specs = (SentinelSpec("custom", b"protected"),)

    def execute(
        case: ArchiveCase, target: TargetAdapter, *, sentinels: tuple[SentinelSpec, ...]
    ) -> RunResult:
        assert sentinels is specs
        return _result(case)

    monkeypatch.setattr(campaign, "run_case", execute)
    run_campaign((_case("a"),), UnusedTarget(), CampaignConfig(3, 3), sentinels=specs)


def test_provenance_frozen_before_first_execution_and_same_value_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = UnusedTarget()
    specs = (SentinelSpec(),)
    frozen = freeze_provenance(target.provenance, specs, source=SourceProvenance("a" * 40, False))
    events: list[str] = []

    def freeze(*args, **kwargs):
        events.append("freeze")
        return frozen

    def execute(case, target, *, sentinels):
        assert events[0] == "freeze"
        events.append("execute")
        return _result(case)

    monkeypatch.setattr(campaign, "freeze_provenance", freeze)
    monkeypatch.setattr(campaign, "run_case", execute)
    result = run_campaign((_case("a"),), target, CampaignConfig(1, 2), sentinels=specs)
    assert events == ["freeze", "execute", "execute"]
    assert result.provenance is frozen
    supplied = run_campaign((_case("a"),), target, CampaignConfig(1, 1), provenance=frozen)
    assert supplied.provenance is frozen
    assert events.count("freeze") == 1


@pytest.mark.parametrize(
    "changes",
    ({"target_version": "different"}, {"timeout_seconds": 1.0}, {"target_id": "different"}),
)
def test_result_cannot_rewrite_frozen_provenance(monkeypatch: pytest.MonkeyPatch, changes) -> None:
    calls = []

    def execute(case, target, *, sentinels):
        calls.append(case)
        raw = _result(case)
        return replace(raw, execution=replace(raw.execution, **changes))

    monkeypatch.setattr(campaign, "run_case", execute)
    with pytest.raises(ValueError, match="differs from frozen"):
        run_campaign((_case("a"),), UnusedTarget(), CampaignConfig(1, 3))
    assert len(calls) == 1


def test_mismatched_supplied_provenance_rejected_before_execution(
    executions: list[ArchiveCase],
) -> None:
    target = UnusedTarget()
    frozen = freeze_provenance(target.provenance, (SentinelSpec("other"),))
    with pytest.raises(ValueError, match="must match"):
        run_campaign((_case("a"),), target, CampaignConfig(1, 1), provenance=frozen)
    assert executions == []


def test_mutable_adapter_configuration_change_stops_before_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ChangingTarget(UnusedTarget):
        version = "test"

        @property
        def provenance(self) -> TargetProvenance:
            return TargetProvenance("controlled", self.version, None)

    target = ChangingTarget()
    calls = []

    def execute(case, adapter, *, sentinels):
        calls.append(case)
        target.version = "changed"
        return _result(case)

    monkeypatch.setattr(campaign, "run_case", execute)
    with pytest.raises(ValueError, match="configuration changed"):
        run_campaign((_case("a"),), target, CampaignConfig(1, 3))
    assert len(calls) == 1
