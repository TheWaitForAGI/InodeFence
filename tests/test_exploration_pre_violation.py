"""Exploration policy #511: pre-violation signals, separation, scheduler, campaign (W4 2026-11-18).

All on the synthetic producer (no target run). ``_producer`` turns the synthetic trace of an
escaping hardlink / absolute symlink into a refused external link / external symlink operation, so
the signal kinds that the plain synthetic producer never shows are exercised.
"""

from __future__ import annotations

import ast
import random
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import inodefence.effect_synthetic as synthetic
from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_demo import effect_campaign_report
from inodefence.effect_scheduler import (
    WEIGHT_UNIT,
    PreViolationNoveltyScheduler,
    PreViolationSchedulerEvidence,
    applied_operators,
)
from inodefence.feedback import EffectSearchPolicy
from inodefence.feedback.exploration_search import ExplorationPolicyId, ExplorationSearchState
from inodefence.feedback.pre_violation import (
    PreViolationSignal,
    PreViolationSignalKind,
    pre_violation_signals,
)
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EffectClass,
    EffectEvidenceStrength,
    EffectPathEvidence,
    EffectRunResult,
    EffectTargetTermination,
    EntryType,
    ObservedOperationType,
    OperationOutcome,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
)
from inodefence.mutator import MutationAttempt, MutationOperatorId, MutationPolicy, operator_ids
from inodefence.mutator.chain import ChainedMutationAttempt, ChainLink

SRC = Path(__file__).resolve().parents[1] / "src" / "inodefence"
EXPLORE = ExplorationPolicyId.PRE_VIOLATION_SIGNAL_NOVELTY
S_U = EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM
V2 = MutationPolicy.V2_FREEZE3_FIXED_BASELINE
REG, HARD, SYM = EntryType.REGULAR, EntryType.HARDLINK, EntryType.SYMLINK
#: The external path the modified events touch. In the default layout it IS the protected
#: sentinel; the separation test renames the sentinels so that it no longer is.
ESCAPE_PATH = "outside/sentinel"


def _absent(path: str) -> EffectPathEvidence:
    return EffectPathEvidence(path, synthetic._observation(None), synthetic._observation(None))


def _snapshots(
    sentinels: tuple[str, ...], protected: tuple[str, ...] | None = None
) -> tuple[StateSnapshot, StateSnapshot]:
    root = "/var/lib/inodefence/effect-feedback"
    # Snapshots keep objects sorted by path; the given order still decides the inode numbers, so
    # a reordered list is a different layout of the same names.
    inode = {name: 9 + i for i, name in enumerate(sentinels)}
    objects = tuple(
        synthetic._object(name, dev=9, ino=inode[name], content=b"sentinel")
        for name in sorted(sentinels)
    )
    protected = tuple(sorted(sentinels if protected is None else protected))
    return (
        StateSnapshot(root, SnapshotPhase.BEFORE, objects, protected),
        StateSnapshot(root, SnapshotPhase.AFTER, objects, protected),
    )


def _producer(
    sentinels: tuple[str, ...] = ("outside/sentinel",),
    protected: tuple[str, ...] | None = None,
    *,
    realized: bool = False,
):
    """Synthetic results; an escaping hardlink is a refused external LINK, an absolute symlink an
    external SYMLINK; the protected list and sentinel names are ``sentinels``.

    ``realized``: the escaping hardlink instead **succeeds** as a verified identity relation
    between ``ESCAPE_PATH`` and the in-root path. That is a realized external effect, so the
    recorded S-u channel's effect key carries the protected-external mark, which follows the
    protected list; the exploration signals must not.
    """

    def produce(case: ArchiveCase) -> EffectRunResult:
        trace = synthetic._trace_for_case(case)
        events = []
        for event in trace.effect_events:
            entry = case.entries[event.entry.entry_index]
            target = entry.link_target or ""
            if entry.entry_type == HARD and target.startswith("..") and realized:
                inner = event.affected_paths[1]
                ino = 100 + event.entry.entry_index
                outside = synthetic._object(ESCAPE_PATH, dev=7, ino=ino)
                linked = synthetic._object(inner, dev=7, ino=ino)
                event = replace(
                    event,
                    affected_paths=(ESCAPE_PATH, inner),
                    object_evidence=(
                        EffectPathEvidence(
                            ESCAPE_PATH,
                            synthetic._observation(outside),
                            synthetic._observation(outside),
                        ),
                        EffectPathEvidence(
                            inner, synthetic._observation(None), synthetic._observation(linked)
                        ),
                    ),
                )
            elif entry.entry_type == HARD and target.startswith(".."):
                inner = event.affected_paths[1]
                event = replace(
                    event,
                    effect_class=EffectClass.OPERATION_OBSERVED,
                    evidence_strength=EffectEvidenceStrength.OPERATION_RESULT,
                    affected_paths=(ESCAPE_PATH, inner),
                    outcome=OperationOutcome.ACCESS_DENIED,
                    object_evidence=(_absent(ESCAPE_PATH), _absent(inner)),
                )
            elif entry.entry_type == SYM and target.startswith("/"):
                event = replace(
                    event,
                    effect_class=EffectClass.OPERATION_OBSERVED,
                    evidence_strength=EffectEvidenceStrength.OPERATION_RESULT,
                    affected_paths=(ESCAPE_PATH,),
                    object_evidence=(_absent(ESCAPE_PATH),),
                )
            events.append(event)
        before, after = _snapshots(sentinels, protected)
        trace = replace(trace, effect_events=tuple(events), before=before, after=after)
        base = RunResult(
            case,
            synthetic._digest(case.case_id.encode()),
            "ustar",
            synthetic._result(case).base_result.execution,
            before,
            after,
            synthetic.compare_states(before, after),
            synthetic.state_signature(before, after),
            synthetic.evaluate_contracts(before, after),
        )
        return EffectRunResult(base, trace)

    return produce


def _case(*items: tuple[EntryType, str, str | None]) -> ArchiveCase:
    return ArchiveCase(
        tuple(
            ArchiveEntry(path, kind, content=b"x" if kind == REG else None, link_target=target)
            for kind, path, target in items
        )
    )


def _kinds(case: ArchiveCase) -> set[str]:
    return {signal.kind for signal in pre_violation_signals(_producer()(case).trace)}


# --- signals -------------------------------------------------------------------------------


def test_signal_kinds_from_observed_events() -> None:
    in_root = _case((REG, "a", None), (HARD, "b", "a"))
    assert _kinds(in_root) == {PreViolationSignalKind.IN_ROOT_IDENTITY_RELATION}
    escape = _case((REG, "a", None), (HARD, "b", "../outside/t"))
    assert _kinds(escape) == {
        PreViolationSignalKind.LINK_ESCAPE_ATTEMPT,
        PreViolationSignalKind.LINK_EXTERNAL_RESOLVE,
        PreViolationSignalKind.REFUSED_OPERATION,
    }
    attempt = next(
        s
        for s in pre_violation_signals(_producer()(escape).trace)
        if s.kind == PreViolationSignalKind.LINK_ESCAPE_ATTEMPT
    )
    assert (attempt.region, attempt.outcome, attempt.shape) == (
        "external",
        "access_denied",
        "parent_1",
    )
    symlink = _case((REG, "a", None), (SYM, "s", "/outside/t"))
    assert _kinds(symlink) == {PreViolationSignalKind.SYMLINK_EXTERNAL_RESOLVE}
    assert _kinds(_case((REG, "a", None))) == set()


def test_in_root_identity_relation_is_not_emitted_once_a_path_is_external() -> None:
    trace = _producer()(_case((REG, "a", None), (HARD, "b", "a"))).trace
    event = trace.effect_events[1]
    external = replace(
        event,
        affected_paths=(ESCAPE_PATH, event.affected_paths[1]),
        object_evidence=(_absent(ESCAPE_PATH), event.object_evidence[1]),
    )
    moved = replace(trace, effect_events=(trace.effect_events[0], external))
    kinds = {signal.kind for signal in pre_violation_signals(moved)}
    assert PreViolationSignalKind.IN_ROOT_IDENTITY_RELATION not in kinds


def test_same_path_replacement_in_root() -> None:
    trace = _producer()(_case((REG, "a", None))).trace
    event = replace(
        trace.effect_events[0],
        effect_class=EffectClass.NAMESPACE_REPLACEMENT,
        operation=ObservedOperationType.RENAME,
    )
    kinds = {
        signal.kind for signal in pre_violation_signals(replace(trace, effect_events=(event,)))
    }
    assert kinds == {PreViolationSignalKind.SAME_PATH_REPLACEMENT}


def test_ineligible_traces_give_no_signal() -> None:
    trace = _producer()(_case((REG, "a", None), (HARD, "b", "../x"))).trace
    assert pre_violation_signals(trace)
    for termination in (EffectTargetTermination.FAILED, EffectTargetTermination.TIMED_OUT):
        assert pre_violation_signals(replace(trace, termination=termination)) == ()
    rejected = replace(trace, termination=EffectTargetTermination.REJECTED)
    assert pre_violation_signals(rejected) == pre_violation_signals(trace)


# --- separation (W4 ruling 1) ----------------------------------------------------------------

FORBIDDEN_MODULES = (
    "inodefence.oracle",
    "inodefence.feedback.fingerprint",
    "inodefence.sentinel_set",
    "inodefence.observer",
    "inodefence.feedback.signature",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_a_signal_code_imports_no_oracle_protected_list_or_sentinel_module() -> None:
    signal_module = SRC / "feedback" / "pre_violation.py"
    assert _imports(signal_module) <= {
        "__future__",
        "dataclasses",
        "enum",
        "inodefence.feedback.effect",
        "inodefence.model",
        "inodefence.model.filesystem",
    }
    for path in (signal_module, SRC / "feedback" / "exploration_search.py"):
        imported = _imports(path)
        assert not any(name.startswith(FORBIDDEN_MODULES) for name in imported), path
        # No code path reads the protected list or violations (docstrings may name them).
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        names |= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert not names & {
            "protected_paths",
            "violations",
            "violation_fingerprints",
            "new_violation_fingerprints",
            "evaluate_contracts",
        }, path


#: A mutation policy whose vocabulary does not read observed names. The v2 policies read the
#: harness's BEFORE names, which include the sentinel names by the threat model (every arm's
#: vocabulary), so renaming sentinels changes the generated children there: that is input
#: generation, not feedback. The campaign-level check uses this policy; the v2 check is per case.
NON_OBSERVING = MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK


def _exploration_trajectory(
    sentinels: tuple[str, ...],
    seed: int,
    mutation_policy: MutationPolicy = NON_OBSERVING,
    protected: tuple[str, ...] | None = None,
    *,
    realized: bool = False,
) -> tuple[list[Any], list[ArchiveCase], list[Any]]:
    """(exploration decisions, executed cases, recorded S-u channel per step)."""
    config = EffectCampaignConfig(seed, 60, S_U, mutation_policy, exploration_policy=EXPLORE)
    produce = _producer(sentinels, protected, realized=realized)
    result = run_effect_campaign(_escape_corpus(), produce, config)
    report: dict[str, Any] = effect_campaign_report(result, "synthetic")
    trajectory: list[Any] = [result.retained_case_ids]
    for step in report["steps"]:
        selection = step["selection"]
        trajectory.append(
            (
                step["case_id"],
                step["parent_case_id"],
                step.get("exploration"),
                None if selection is None else selection["corpus_admission"],
                None if selection is None else selection["operator_weights"],
            )
        )
    cases = [step.result.base_result.case for step in result.steps]
    recorded = [step["feedback"] for step in report["steps"]]
    return trajectory, cases, recorded


def _escape_corpus() -> tuple[ArchiveCase, ...]:
    return (
        *minimal_seed_corpus(),
        _case((REG, "a", None), (HARD, "b", "../outside/t")),
    )


VARIANTS = (
    ("outside/zz-renamed",),
    ("outside/b-second", "outside/a-first"),
    ("outside/a-first", "outside/b-second"),
    ("outside/sentinel", "outside/another"),
)


@pytest.mark.parametrize("seed", [5, 777])
def test_b_renaming_or_reordering_protected_list_and_sentinels_changes_no_decision(
    seed: int,
) -> None:
    # Whole campaign: signals, admissions, parent draws, rewards and weights are byte-identical.
    reference, _, _ = _exploration_trajectory(("outside/sentinel",), seed)
    assert any(item[2] and item[2]["new_signals"] for item in reference[1:])  # signals exercised
    for sentinels in VARIANTS:
        assert _exploration_trajectory(sentinels, seed)[0] == reference, sentinels
    # Not vacuous: the variants do change what the run records as protected (the escape path is
    # protected in the default layout only).
    escape = _escape_corpus()[-1]
    protected = {
        _producer(sentinels)(escape).trace.before.protected_paths
        for sentinels in (("outside/sentinel",), *VARIANTS)
    }
    assert len(protected) == 4 and (ESCAPE_PATH,) in protected


#: A fixed name pool (the objects the harness lays out, i.e. the v2 vocabulary source) and
#: permutations of the protected list over it: which names are marked protected, and the order
#: (inode numbers) the harness created them in. The vocabulary is the same in every variant.
NAME_POOL = ("outside/another", "outside/sentinel", "outside/third")
PROTECTED_VARIANTS = (
    (NAME_POOL, ("outside/sentinel",)),
    (NAME_POOL, ("outside/another",)),
    (NAME_POOL, ("outside/another", "outside/third")),
    (NAME_POOL, NAME_POOL),
    (tuple(reversed(NAME_POOL)), ("outside/sentinel",)),
    (tuple(reversed(NAME_POOL)), ("outside/third",)),
)


@pytest.mark.parametrize("seed", [5, 777])
def test_b_v2_policy_whole_campaign_with_a_fixed_name_pool_and_permuted_protected_list(
    seed: int,
) -> None:
    # W4 2026-11-18: with the name pool fixed, permuting the protected list (membership and
    # order) changes no feedback decision of the whole v2 campaign: signals, admissions, parent
    # draws, rewards and weights. This isolates exactly what feedback must not see.
    pool, protected = PROTECTED_VARIANTS[0]
    reference, _, _ = _exploration_trajectory(pool, seed, V2, protected)
    assert any(item[2] and item[2]["new_signals"] for item in reference[1:])
    for pool, protected in PROTECTED_VARIANTS[1:]:
        assert _exploration_trajectory(pool, seed, V2, protected)[0] == reference, protected
    # Not vacuous: the recorded protected lists differ across the variants.
    escape = _escape_corpus()[-1]
    recorded = {
        _producer(pool, protected)(escape).trace.before.protected_paths
        for pool, protected in PROTECTED_VARIANTS
    }
    assert len(recorded) == 5  # five memberships; two variants share one and differ in order


@pytest.mark.parametrize("seed", [5, 777])
def test_b_v2_realized_external_effect_moves_the_s_u_record_but_no_exploration_decision(
    seed: int,
) -> None:
    # QA check 37: with a realized external effect on a path whose protection changes, the
    # channel that reads the protected list (the recorded S-u effect keys) does move across the
    # variants, while every exploration decision stays byte-identical.
    pool, protected = PROTECTED_VARIANTS[0]
    reference, _, reference_record = _exploration_trajectory(
        pool, seed, V2, protected, realized=True
    )
    assert any(item[2] and item[2]["new_signals"] for item in reference[1:])
    records = [reference_record]
    for pool, protected in PROTECTED_VARIANTS[1:]:
        trajectory, _, record = _exploration_trajectory(pool, seed, V2, protected, realized=True)
        assert trajectory == reference, protected
        records.append(record)
    assert any(record != reference_record for record in records[1:])


def test_b_v2_policy_signals_per_case_do_not_depend_on_protected_list_or_sentinels() -> None:
    _, cases, _ = _exploration_trajectory(("outside/sentinel",), 5, V2)
    for case in cases:
        reference = pre_violation_signals(_producer()(case).trace)
        for sentinels in VARIANTS:
            assert pre_violation_signals(_producer(sentinels)(case).trace) == reference


# --- scheduler (W4 rulings 4, 5) ------------------------------------------------------------

TABLE = operator_ids(V2)
ADD, REMOVE = MutationOperatorId.ADD_ENTRY, MutationOperatorId.REMOVE_ENTRY
SIGNAL = PreViolationSignal("refused-operation", "hardlink", "link", "external", "access_denied")


def _attempt(operator: MutationOperatorId, applied: bool = True) -> MutationAttempt:
    parent = minimal_seed_corpus()[0]
    child = parent if not applied else _case((REG, "a", None), (REG, "z", None))
    return MutationAttempt(operator, V2, parent.case_id, child, applied)


def _observe(scheduler, operator, applied_ops, signals) -> PreViolationSchedulerEvidence:
    rng = random.Random(1)
    while True:
        selection = scheduler.choose_operator(TABLE, rng)
        if selection.operator_id == operator:
            break
    return scheduler.observe_signals(
        selection, _attempt(operator), applied_ops, signals, bool(signals)
    )


def test_binary_reward_split_evenly_over_applied_operators() -> None:
    scheduler = PreViolationNoveltyScheduler(operators=TABLE)
    evidence = _observe(scheduler, ADD, (ADD, REMOVE), (SIGNAL,))
    assert evidence.reward == 1 and evidence.credited_operators == (ADD, REMOVE)
    weights = dict(evidence.weights_after)
    assert weights[ADD] == weights[REMOVE] == WEIGHT_UNIT + WEIGHT_UNIT // 2
    assert all(weights[op] == WEIGHT_UNIT for op in TABLE if op not in (ADD, REMOVE))
    # No new signal: no reward, nobody credited, weights unchanged.
    quiet = _observe(scheduler, ADD, (ADD,), ())
    assert quiet.reward == 0 and quiet.credited_operators == ()
    assert quiet.weights_after == evidence.weights_after
    # A reward with no applied operator (all attempts were no-ops) credits nobody.
    none_applied = _observe(scheduler, ADD, (), (SIGNAL,))
    assert none_applied.reward == 1 and none_applied.credited_operators == ()
    assert none_applied.weights_after == evidence.weights_after


def test_weights_are_capped_and_more_than_six_applied_operators_are_refused() -> None:
    scheduler = PreViolationNoveltyScheduler(operators=TABLE, maximum_weight=2)
    for _ in range(5):
        evidence = _observe(scheduler, ADD, (ADD,), (SIGNAL,))
    assert dict(evidence.weights_after)[ADD] == 2 * WEIGHT_UNIT
    with pytest.raises(ValueError, match="at most 6"):
        _observe(scheduler, ADD, (ADD,) * 7, (SIGNAL,))


def test_observe_signals_reward_and_weights_ignore_effect_keys_and_fingerprints() -> None:
    # QA check 37 note a: effect_scheduler.py is outside the import-graph check, so pin it here:
    # in observe_signals the recorded-channel arguments only pass through to the evidence.
    source = (SRC / "effect_scheduler.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "observe_signals"
    )
    passthrough = {"new_effect_keys", "new_violation_fingerprints"}
    evidence_call = next(
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "PreViolationSchedulerEvidence"
    )
    allowed = {id(arg) for arg in evidence_call.args}
    uses = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Name) and node.id in passthrough and isinstance(node.ctx, ast.Load)
    ]
    assert uses and all(id(node) in allowed for node in uses)


def test_evidence_reward_must_match_new_signals() -> None:
    evidence = _observe(PreViolationNoveltyScheduler(operators=TABLE), ADD, (ADD,), (SIGNAL,))
    with pytest.raises(ValueError, match="exactly on a new signal"):
        replace(evidence, new_signals=())


def test_applied_operators_of_single_attempts_and_chains() -> None:
    assert applied_operators(_attempt(ADD)) == (ADD,)
    assert applied_operators(_attempt(ADD, applied=False)) == ()
    parent = minimal_seed_corpus()[0]
    child = _case((REG, "z", None))
    chained = ChainedMutationAttempt(
        REMOVE,
        V2,
        parent.case_id,
        child,
        True,
        links=(ChainLink(ADD, True, 1), ChainLink(ADD, False, 1), ChainLink(REMOVE, True, 1)),
    )
    assert applied_operators(chained) == (ADD, REMOVE)


# --- campaign and report ---------------------------------------------------------------------


def test_config_requires_the_declared_base_search_policy() -> None:
    with pytest.raises(ValueError, match="requires search_policy"):
        EffectCampaignConfig(5, 20, EffectSearchPolicy.D_STRUCTURE_COVERAGE, V2, None, EXPLORE)
    with pytest.raises(ValueError, match="ExplorationPolicyId"):
        EffectCampaignConfig(5, 20, S_U, V2, None, EXPLORE.value)  # type: ignore[arg-type]


def test_retention_is_seeds_plus_new_signals_and_parents_come_from_it() -> None:
    config = EffectCampaignConfig(5, 60, S_U, V2, exploration_policy=EXPLORE)
    result = run_effect_campaign(_escape_corpus(), _producer(), config)
    report: dict[str, Any] = effect_campaign_report(result, "synthetic")
    assert report["config"]["exploration_policy"] == EXPLORE.value
    seeds = list(result.initial_case_ids)
    admitted = [
        step["case_id"]
        for step in report["steps"]
        if step.get("exploration") and step["exploration"]["signal_retained"]
    ]
    assert list(result.retained_case_ids) == seeds + admitted
    pool = list(seeds)
    for step in report["steps"][len(seeds) :]:
        assert step["parent_case_id"] in pool
        assert step["selection"]["corpus_admission"]["corpus_size_before"] == len(pool)
        if step["exploration"]["signal_retained"]:
            assert step["exploration"]["new_signals"]
            pool.append(step["case_id"])
        reward = step["scheduler_evidence"]["reward"]
        assert reward == int(bool(step["exploration"]["new_signals"]))


def test_without_exploration_policy_nothing_changes_in_the_report() -> None:
    config = EffectCampaignConfig(5, 20, S_U, V2)
    report: dict[str, Any] = effect_campaign_report(
        run_effect_campaign(minimal_seed_corpus(), synthetic.synthetic_effect_result, config),
        "synthetic",
    )
    assert "exploration_policy" not in report["config"]
    assert not any("exploration" in step for step in report["steps"])


def test_exploration_state_records_the_s_u_channel_but_decides_by_signals() -> None:
    cases = _escape_corpus()
    state = ExplorationSearchState(cases, EXPLORE)
    produce = _producer()
    for case in cases:
        state.consider(produce(case))
    assert state.retained_case_ids == tuple(case.case_id for case in cases)
    assert state.last.signal_retained is False  # seeds are the base corpus, not signal admissions
    assert state.unique_signals >= 3
