"""R/D/S-u equal-vocabulary arm runner on the effect-campaign path (H-A; EXP-0).

Realizes the three main arms of ``docs/research/design/research-questions.md`` v2
H-A (and the optional S-a ablation) as concrete ``EffectCampaignConfig`` values so
every arm runs through the one ``run_effect_campaign`` loop with:

* the SAME vocabulary — one ``VocabularyMode`` maps to one ``MutationPolicy`` that
  is applied to every arm (the token pool is a property of the cell, not the arm);
* the SAME random seed, execution budget, 8-slot operator table and UNIFORM
  operator scheduler (every slot weight 1 at every step);
* the SAME diagnostic channel (the boundary-attempt key set under the P3 clean-
  trace gate), so dense signals are measured identically;
* ONLY the retention (admission) policy differing: R none, D target-agnostic
  structure coverage, S-u identity/effect/boundary-attempt state keys.

The per-cell summary (``RdsCellSummary``) is the record the statistics lane
consumes: ``t_first`` (first C1 ∨ C2, right-censored at the budget for a complete
no-hit campaign and at the abort point for an aborted one) and ``u_viol`` (unique
normalized C1/C2 violation fingerprints). A hit is a post-state oracle C1 or C2
contract violation; C0 alone is not a hit and is counted separately. Nothing here
ranks arms or claims effectiveness; this is the measurement harness.

Unique-violation identification (U_viol) — the oracle-evidence design:

1. **Signature.** One ``ViolationFingerprint`` per violated contract per step
   (``feedback/fingerprint.py``): ``contract_id`` plus the sorted, duplicate-free
   evidence tuple — C1: ``(internal_path, sentinel_path)`` identity relations;
   C0/C2: ``(path, changed-field labels)``. Excluded from the signature: device and
   inode numbers, timestamps and other before/after values, explanation and
   limitations text, the step index, the case id and the mutation that produced
   the step. The canonical order is ``(contract_id, evidence keys)``.
2. **Deduplication scope.** Within one cell, across all its steps: a signature
   reached at several steps counts once. Pooling across cells (per arm, per seed)
   is the analysis tools' job and is not done here.
3. **Lineage.** Lineage is not a signature component. "Same lineage, same
   fingerprint counts once" is absorbed by fingerprint equality: two steps of the
   same lineage with the same signature are one class, and so are two steps of
   different lineages with the same signature.
4. **Eligibility.** A step is feedback-eligible when its trace is integrity-valid,
   complete and terminated SUCCESS (or REJECTED under the boundary-attempt
   channel); ineligible otherwise (``feedback/effect.py``, ``effect_novelty.py``).
   Eligibility gates what the loop *feeds back*, not what the oracle *found*:
   ``u_viol`` counts the oracle's classes of every step regardless of eligibility,
   while ``u_viol_feedback`` separately counts the classes the loop recorded as new
   feedback on eligible steps (raw search-behaviour diversity, not the metric).
5. **One event definition.** ``hit``, ``t_first`` and ``u_viol`` all read the same
   event — a step whose post-state oracle reports C1 ∨ C2 violated
   (``contract_violated``) — for every arm, and the in-memory summary
   (``summarize_rds_steps``) and the report summary (``rds_report``) realize it
   identically; the parity tests in ``tests/evaluation`` hold them to that.

The producer is caller-owned: the synthetic producer yields "synthetic" labelled
results, and a native node-tar producer is bound by the runtime lane inside the
controller. This module never executes a target itself.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar

from inodefence.campaign import CampaignOrigin
from inodefence.effect_campaign import (
    EffectCampaignConfig,
    EffectCampaignResult,
    EffectCampaignStep,
    _observed_name_segments,
    run_effect_campaign,
)
from inodefence.feedback import EffectSearchPolicy, violation_fingerprints
from inodefence.model import (
    ArchiveCase,
    ContractId,
    EffectFeedbackKeyKind,
    EffectRunResult,
    EffectTargetTermination,
)
from inodefence.mutator import MutationPolicy, m1
from inodefence.mutator.m1_addressing import COMPONENTS as PROTECTED_COMPONENTS

HIT_CONTRACTS: frozenset[ContractId] = frozenset((ContractId.C1, ContractId.C2))
HIT_DEFINITION = (
    "post-state oracle C1 or C2 contract violation (contract_violated); C0 alone is not a hit"
)
CENSORING_NOTE = (
    "t_first is the 1-based execution count of the first hit; a complete no-hit campaign "
    "is right-censored at the execution budget N and an aborted campaign at the number "
    "of executions completed before the abort; no hit index is imputed"
)
U_VIOL_DEFINITION = (
    "number of unique normalized C1/C2 ViolationFingerprint classes (contract_id + sorted "
    "evidence: C1 internal/sentinel path pairs, C2 path + changed-field labels; no "
    "device/inode numbers, timestamps, values, text, step or case identity) over all "
    "executions of the cell, read from the post-state oracle of every step regardless of "
    "feedback eligibility; the same fingerprint reached again (same lineage or not) counts "
    "once; pooling across cells is left to the analysis tools"
)
U_VIOL_SOURCE_ORACLE = "oracle"
U_VIOL_SOURCE_FEEDBACK_FALLBACK = "feedback-fallback"
U_VIOL_FEEDBACK_DEFINITION = (
    "number of unique C1/C2 fingerprints the search loop recorded as new feedback "
    "(feedback-eligible steps only); a search-behaviour descriptor, not the U_viol metric"
)


class RdsArm(StrEnum):
    """H-A arms. R/D/S-u are the main comparison; S-a is the optional scheduler ablation."""

    R = "R"
    D = "D"
    S_U = "S-u"
    S_A = "S-a"


class RVariant(StrEnum):
    """Which random floor R realizes; the policy ID fixes it (see ``EffectSearchPolicy``)."""

    WALK = "walk"
    SEED_RESTART = "seed-restart"


class VocabularyMode(StrEnum):
    """One token pool per cell, applied to every arm through one ``MutationPolicy``.

    generic: the 7 generic M1 tokens only (cannot spell a sentinel name; H-C floor).
    protected-components: generic plus the static ``outside``/``sentinel.txt`` tokens
        (cannot spell a seed-randomized sentinel name).
    observed-names: generic plus the segment names of the objects in the seed baseline
        run's (step 0) BEFORE snapshot, fixed once per campaign and never grown. The
        EXP-0 default: the pool is the harness layout every arm sees, read from the
        observed tree (EXTERNAL region included), never from the protected list.
    observed-names-accumulated: the historical A3full mechanism (names accumulate from
        every run's before/after snapshots). Ablation only: a retention difference then
        changes the observed objects and hence the pool, confounding vocabulary.
    """

    GENERIC = "generic"
    PROTECTED_COMPONENTS = "protected-components"
    OBSERVED_NAMES = "observed-names"
    OBSERVED_NAMES_ACCUMULATED = "observed-names-accumulated"


VOCABULARY_MUTATION_POLICY: Mapping[VocabularyMode, MutationPolicy] = MappingProxyType(
    {
        VocabularyMode.GENERIC: MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK,
        VocabularyMode.PROTECTED_COMPONENTS: MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK,
        VocabularyMode.OBSERVED_NAMES: MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE,
        VocabularyMode.OBSERVED_NAMES_ACCUMULATED: MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK,
    }
)

_R_VARIANT_POLICY: Mapping[RVariant, EffectSearchPolicy] = MappingProxyType(
    {
        RVariant.WALK: EffectSearchPolicy.R_UNRETAINED_WALK,
        RVariant.SEED_RESTART: EffectSearchPolicy.R_UNRETAINED_SEED_RESTART,
    }
)
_ARM_POLICY: Mapping[RdsArm, EffectSearchPolicy] = MappingProxyType(
    {
        RdsArm.D: EffectSearchPolicy.D_STRUCTURE_COVERAGE,
        RdsArm.S_U: EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM,
        RdsArm.S_A: EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT,
    }
)


def arm_search_policy(arm: RdsArm, r_variant: RVariant = RVariant.WALK) -> EffectSearchPolicy:
    """The one retention policy ID an arm realizes (R additionally by its variant)."""
    if not isinstance(arm, RdsArm) or not isinstance(r_variant, RVariant):
        raise ValueError("arm must be an RdsArm and r_variant an RVariant")
    if arm == RdsArm.R:
        return _R_VARIANT_POLICY[r_variant]
    return _ARM_POLICY[arm]


def arm_for_policy(policy: EffectSearchPolicy) -> tuple[RdsArm, RVariant | None]:
    """Inverse of ``arm_search_policy``; raises for a policy that realizes no arm."""
    for variant, candidate in _R_VARIANT_POLICY.items():
        if candidate == policy:
            return RdsArm.R, variant
    for arm, candidate in _ARM_POLICY.items():
        if candidate == policy:
            return arm, None
    raise ValueError(f"{policy.value} realizes no R/D/S arm")


@dataclass(frozen=True, slots=True)
class RdsCellConfig:
    """One cell = arm × seed × budget under one shared vocabulary mode."""

    arm: RdsArm
    random_seed: int
    execution_budget: int
    vocabulary_mode: VocabularyMode = VocabularyMode.OBSERVED_NAMES
    r_variant: RVariant = RVariant.WALK

    def __post_init__(self) -> None:
        if not isinstance(self.arm, RdsArm):
            raise ValueError("arm must be an RdsArm")
        if not isinstance(self.vocabulary_mode, VocabularyMode):
            raise ValueError("vocabulary_mode must be a VocabularyMode")
        if not isinstance(self.r_variant, RVariant):
            raise ValueError("r_variant must be an RVariant")
        # Seed/budget typing is enforced by EffectCampaignConfig.
        self.campaign_config()

    @property
    def search_policy(self) -> EffectSearchPolicy:
        return arm_search_policy(self.arm, self.r_variant)

    @property
    def mutation_policy(self) -> MutationPolicy:
        return VOCABULARY_MUTATION_POLICY[self.vocabulary_mode]

    def campaign_config(self) -> EffectCampaignConfig:
        return EffectCampaignConfig(
            random_seed=self.random_seed,
            execution_budget=self.execution_budget,
            search_policy=self.search_policy,
            mutation_policy=self.mutation_policy,
        )


def _pool(observed: set[str]) -> tuple[str, ...]:
    # Exactly how the campaign hands observed names to the mutator
    # (``extra_components=tuple(sorted(observed_names))`` appended to m1.COMPONENTS).
    return m1.COMPONENTS + tuple(sorted(observed))


def vocabulary_pools(
    mode: VocabularyMode, steps: Sequence[EffectCampaignStep], initial_count: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(pool after the seed phase, pool at the end) as the mutator saw them.

    Reconstructed with the same function and inputs the campaign used
    (``_observed_name_segments`` over the recorded step results), so it is the pool
    itself, not an estimate. Static modes return their constant tuple twice; the
    fixed-baseline mode returns the step-0 BEFORE pool twice (it never grows).
    """
    if mode == VocabularyMode.GENERIC:
        return m1.COMPONENTS, m1.COMPONENTS
    if mode == VocabularyMode.PROTECTED_COMPONENTS:
        return PROTECTED_COMPONENTS, PROTECTED_COMPONENTS
    if mode == VocabularyMode.OBSERVED_NAMES:
        if not steps:
            return m1.COMPONENTS, m1.COMPONENTS
        fixed = _pool(_observed_name_segments(steps[0].result, before_only=True))
        return fixed, fixed
    after_seed: set[str] = set()
    for step in steps[:initial_count]:
        after_seed |= _observed_name_segments(step.result)
    final = set(after_seed)
    for step in steps[initial_count:]:
        final |= _observed_name_segments(step.result)
    return _pool(after_seed), _pool(final)


def violated_contracts(result: EffectRunResult) -> frozenset[ContractId]:
    """Contracts the post-state oracle reports as violated for this run."""
    return frozenset(item.contract_id for item in result.base_result.violations if item.violated)


def is_hit(result: EffectRunResult) -> bool:
    """H-A hit: a C1 or C2 post-state violation (C0 alone is not a hit)."""
    return bool(violated_contracts(result) & HIT_CONTRACTS)


@dataclass(frozen=True, slots=True)
class RdsCellSummary:
    """Per-cell record for the statistics lane; every field is read from the steps.

    ``t_first``/``t_first_event`` are the survival pair (time, event indicator):
    event 1 at the 1-based execution count of the first hit, else event 0 with the
    censoring time (``execution_budget`` when complete, ``executions_completed`` when
    aborted). ``first_c0/c1/c2`` are 1-based first-observation counts per contract
    (None if never observed). Counts of keys/states are search-behaviour
    descriptors, not effectiveness (EN-008).
    """

    serialization_schema: ClassVar[int] = 1

    arm: RdsArm
    r_variant: RVariant | None
    search_policy: EffectSearchPolicy
    mutation_policy: MutationPolicy
    vocabulary_mode: VocabularyMode
    random_seed: int
    execution_budget: int
    initial_cases: int
    executions_completed: int
    complete: bool
    aborted: bool
    abort_step_index: int | None
    abort_reason: str | None
    hit: bool
    t_first: int
    t_first_event: int
    t_first_censored: bool
    first_hit_step_index: int | None
    hit_steps: int
    u_viol: int
    u_viol_c0: int
    # Where u_viol/u_viol_c0 were read from: "oracle" (the post-state verdicts of every
    # step, eligibility-independent) or "feedback-fallback" (records that predate
    # oracle_fingerprints; counts only what the loop fed back).
    u_viol_source: str
    u_viol_feedback: int
    first_c0: int | None
    first_c1: int | None
    first_c2: int | None
    c0_steps: int
    rejected_executions: int
    observation_failures: int
    boundary_attempt_keys: int
    unique_effect_keys: int
    retained_cases: int
    vocabulary_pool_after_seed: tuple[str, ...]
    vocabulary_pool_final: tuple[str, ...]
    observed_protected_paths: tuple[str, ...]
    sentinel_set: Mapping[str, object] | None
    hit_definition: str = HIT_DEFINITION
    censoring: str = CENSORING_NOTE
    u_viol_definition: str = U_VIOL_DEFINITION
    u_viol_feedback_definition: str = U_VIOL_FEEDBACK_DEFINITION


def _first_execution(indexes: Sequence[int]) -> int | None:
    return indexes[0] + 1 if indexes else None


def summarize_rds_steps(
    steps: Sequence[EffectCampaignStep],
    config: RdsCellConfig,
    *,
    aborted_at_step: int | None = None,
    abort_reason: str | None = None,
    sentinel_set: Mapping[str, object] | None = None,
) -> RdsCellSummary:
    """Summarize a complete or aborted cell from its recorded steps.

    ``aborted_at_step`` is the index of the step that did not complete (equal to the
    number of completed steps); ``sentinel_set`` is the runtime's sentinel generator
    description passed through verbatim for cross-checking, never used as feedback.
    """
    if not isinstance(config, RdsCellConfig):
        raise ValueError("summary requires an RdsCellConfig")
    recorded = tuple(steps)
    if not all(isinstance(step, EffectCampaignStep) for step in recorded):
        raise ValueError("summary requires EffectCampaignStep records")
    if tuple(step.index for step in recorded) != tuple(range(len(recorded))):
        raise ValueError("summary requires contiguous step indexes from zero")
    if len(recorded) > config.execution_budget:
        raise ValueError("recorded steps exceed the execution budget")
    if (aborted_at_step is None) != (abort_reason is None):
        raise ValueError("abort step and reason must appear together")
    if aborted_at_step is not None and aborted_at_step != len(recorded):
        raise ValueError("abort step index must equal the number of completed steps")
    if sentinel_set is not None and not isinstance(sentinel_set, Mapping):
        raise ValueError("sentinel_set must be a mapping when given")
    completed = len(recorded)
    aborted = aborted_at_step is not None
    complete = not aborted and completed == config.execution_budget
    if not complete and not aborted:
        raise ValueError("an incomplete cell must declare its abort step and reason")

    hit_indexes = [step.index for step in recorded if is_hit(step.result)]
    per_contract = {
        contract: [step.index for step in recorded if contract in violated_contracts(step.result)]
        for contract in ContractId
    }
    hit_fingerprints = set()
    c0_fingerprints = set()
    feedback_fingerprints = set()
    for step in recorded:
        # U_viol reads the oracle verdicts of every step; feedback eligibility (which
        # gates what the loop fed back) does not enter the metric.
        for fingerprint in violation_fingerprints(step.result.base_result.violations):
            if fingerprint.contract_id in HIT_CONTRACTS:
                hit_fingerprints.add(fingerprint)
            else:
                c0_fingerprints.add(fingerprint)
        for fingerprint in step.feedback.new_violation_fingerprints:
            if fingerprint.contract_id in HIT_CONTRACTS:
                feedback_fingerprints.add(fingerprint)
    first_hit = _first_execution(hit_indexes)
    boundary_keys = sum(
        1
        for step in recorded
        for key in step.feedback.new_effect_keys
        if key.kind == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT
    )
    initial_count = sum(1 for step in recorded if step.origin == CampaignOrigin.SEED)
    after_seed, final = vocabulary_pools(config.vocabulary_mode, recorded, initial_count)
    return RdsCellSummary(
        arm=config.arm,
        r_variant=config.r_variant if config.arm == RdsArm.R else None,
        search_policy=config.search_policy,
        mutation_policy=config.mutation_policy,
        vocabulary_mode=config.vocabulary_mode,
        random_seed=config.random_seed,
        execution_budget=config.execution_budget,
        initial_cases=initial_count,
        executions_completed=completed,
        complete=complete,
        aborted=aborted,
        abort_step_index=aborted_at_step,
        abort_reason=abort_reason,
        hit=first_hit is not None,
        t_first=first_hit if first_hit is not None else completed,
        t_first_event=1 if first_hit is not None else 0,
        t_first_censored=first_hit is None,
        first_hit_step_index=hit_indexes[0] if hit_indexes else None,
        hit_steps=len(hit_indexes),
        u_viol=len(hit_fingerprints),
        u_viol_c0=len(c0_fingerprints),
        u_viol_source=U_VIOL_SOURCE_ORACLE,
        u_viol_feedback=len(feedback_fingerprints),
        first_c0=_first_execution(per_contract[ContractId.C0]),
        first_c1=_first_execution(per_contract[ContractId.C1]),
        first_c2=_first_execution(per_contract[ContractId.C2]),
        c0_steps=len(per_contract[ContractId.C0]),
        rejected_executions=sum(
            1
            for step in recorded
            if step.result.trace.termination == EffectTargetTermination.REJECTED
        ),
        observation_failures=sum(1 for step in recorded if step.feedback.observation_failure),
        boundary_attempt_keys=boundary_keys,
        unique_effect_keys=sum(len(step.feedback.new_effect_keys) for step in recorded),
        retained_cases=sum(1 for step in recorded if step.feedback.retained),
        vocabulary_pool_after_seed=after_seed,
        vocabulary_pool_final=final,
        observed_protected_paths=(
            recorded[0].result.trace.before.protected_paths if recorded else ()
        ),
        sentinel_set=sentinel_set,
    )


def _plain(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def summary_record(summary: RdsCellSummary) -> dict[str, object]:
    """JSON-ready mapping of the summary (enum values, lists, plain scalars)."""
    record: dict[str, object] = {"schema_version": RdsCellSummary.serialization_schema}
    for field in fields(summary):
        record[field.name] = _plain(getattr(summary, field.name))
    return record


@dataclass(frozen=True, slots=True)
class RdsCellResult:
    config: RdsCellConfig
    campaign: EffectCampaignResult
    summary: RdsCellSummary


class RdsCellAborted(RuntimeError):
    """The producer failed mid-cell; every completed step and a censored summary survive."""

    def __init__(
        self,
        config: RdsCellConfig,
        steps: tuple[EffectCampaignStep, ...],
        reason: str,
        sentinel_set: Mapping[str, object] | None = None,
    ) -> None:
        self.config = config
        self.steps = steps
        self.reason = reason
        self.summary = summarize_rds_steps(
            steps,
            config,
            aborted_at_step=len(steps),
            abort_reason=reason,
            sentinel_set=sentinel_set,
        )
        super().__init__(f"cell aborted at step {len(steps)}: {reason}")


EffectResultProducer = Callable[[ArchiveCase], EffectRunResult]
StepObserver = Callable[[EffectCampaignStep], None]


def run_rds_cell(
    initial_cases: Sequence[ArchiveCase],
    produce_result: EffectResultProducer,
    config: RdsCellConfig,
    *,
    on_step: StepObserver | None = None,
    sentinel_set: Mapping[str, object] | None = None,
) -> RdsCellResult:
    """Run one cell through ``run_effect_campaign`` and summarize it.

    A producer exception becomes ``RdsCellAborted`` carrying the completed steps and
    an abort-censored summary (the exception is chained as the cause). ``on_step``
    sees each completed step first, so a caller can persist incrementally.
    """
    if not isinstance(config, RdsCellConfig):
        raise ValueError("run_rds_cell requires an RdsCellConfig")
    steps: list[EffectCampaignStep] = []

    def collect(step: EffectCampaignStep) -> None:
        steps.append(step)
        if on_step is not None:
            on_step(step)

    try:
        campaign = run_effect_campaign(
            initial_cases, produce_result, config.campaign_config(), collect
        )
    except Exception as error:
        raise RdsCellAborted(
            config, tuple(steps), f"{type(error).__name__}: {error}", sentinel_set
        ) from error
    return RdsCellResult(
        config, campaign, summarize_rds_steps(campaign.steps, config, sentinel_set=sentinel_set)
    )
