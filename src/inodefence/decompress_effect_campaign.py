"""decompress self-discovery loop (M4): the generic fuzz loop over a real-decompress producer.

This is the decompress twin of ``effect_campaign.run_effect_campaign``. node-tar self-discovery
drives the generic loop over a rich, ordered ``EffectEventTrace``; decompress cannot expose that
ordered, entry-correlated stream within the safety boundary (observed in
``experiments/repro/decompress_entry_effect_feasibility.py``). So this loop drives the SAME generic
pieces -- the generic mutator (``apply_operator``), the generic adaptive/uniform scheduler
(``effect_scheduler``), the generic oracle verdict (via ``run_decompress_frame_case``), and the
SANCTIONED boundary-attempt normalizer (``feedback.boundary_attempt_frame``) -- over the FEASIBLE
set-based signal: the ``inodefence-boundary-attempt-v1`` frame the decompress ``frame`` worker
emits.

Two independent novelty channels steer the search, both over real observations:
  * boundary-attempt keys -- ``frame_boundary_attempt_keys(run.frame)``: the set-based gradient
    (a link/symlink op whose observed resolved target is external), rewarded even when the op was
    refused, exactly the M3.1 ``EffectNoveltyIndex`` boundary-attempt arm does for node-tar.
  * violation fingerprints -- ``violation_fingerprints(run.base_result.violations)``: the generic
    C0/C1/C2 oracle verdict on the real before/after snapshots. A new C1/C2 fingerprint is the
    "hit": the loop self-discovered an archive boundary violation in decompress.

A full-state-signature channel additionally retains cases that reach a new post-extraction state,
so the corpus grows without an effect-novelty stream. Reward (scheduler weight) follows the generic
rule: a new boundary-attempt key OR a new violation fingerprint.

Honesty / research invariants: generic mutator / observer / oracle / feedback are UNCHANGED (only
called). The hit is the production oracle, target-agnostic, no decompress/CVE condition. No
sentinel name or CVE enters the mutation vocabulary or a verdict (D005/D006); the state-aware
escape policy composes link targets only from object names the run OBSERVES in the general tree
(not the protected list), exactly as the node-tar loop does, and its blind control drops external
names. This is a self-discovery ATTEMPT on a second extractor, not an effectiveness claim versus
node-tar, and the feasible channel here is narrower than node-tar's ordered effect channel.
"""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar

from inodefence.campaign import CampaignOrigin
from inodefence.effect_pipeline_decompress import DecompressFrameRun
from inodefence.effect_scheduler import (
    EffectAdaptiveMutationScheduler,
    EffectMutationSchedulerEvidence,
    EffectUniformMutationScheduler,
)
from inodefence.feedback import EffectSearchPolicy, ViolationFingerprint, violation_fingerprints
from inodefence.feedback.boundary_attempt_frame import frame_boundary_attempt_keys
from inodefence.model import (
    ArchiveCase,
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    ExecutionStatus,
    StateSignature,
)
from inodefence.model.filesystem import Region, path_region
from inodefence.mutation_scheduler import MutationSelection
from inodefence.mutator import MutationAttempt, MutationPolicy, apply_operator, operator_ids

# Only a cleanly started run (decompress ran to a success or an explicit refusal) is an eligible
# observation. A harness/IO failure or timeout leaves the frame and post-state only partially
# observed, so it contributes no key, violation or corpus admission (fail-closed, mirroring the
# node-tar effect search's eligibility gate).
_ELIGIBLE_TERMINATIONS = (ExecutionStatus.SUCCESS, ExecutionStatus.REJECTED)


@dataclass(frozen=True, slots=True)
class DecompressEffectCampaignConfig:
    random_seed: int
    execution_budget: int
    mutation_policy: MutationPolicy = MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK
    # Which boundary-gradient rungs steer the search, mirroring the node-tar effect campaign's
    # EffectSearchPolicy ladder (see DecompressEffectSearchState). The default admits both rungs
    # (= the C arm), which is the single-channel behaviour this campaign had before the arm split.
    search_policy: EffectSearchPolicy = EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT
    adaptive_scheduler: bool = True

    def __post_init__(self) -> None:
        if type(self.random_seed) is not int:
            raise ValueError("random_seed must be an integer")
        if type(self.execution_budget) is not int or self.execution_budget <= 0:
            raise ValueError("execution_budget must be a positive integer")
        if not isinstance(self.mutation_policy, MutationPolicy):
            raise ValueError("mutation_policy must be a supported MutationPolicy")
        if not isinstance(self.search_policy, EffectSearchPolicy):
            raise ValueError("search_policy must be a supported EffectSearchPolicy")
        if type(self.adaptive_scheduler) is not bool:
            raise ValueError("adaptive_scheduler must be a bool")


@dataclass(frozen=True, slots=True)
class DecompressEffectDecision:
    """Per-observation feedback over the two real channels plus full-state novelty."""

    case_id: str
    new_attempt_keys: tuple[EffectFeedbackKey, ...]
    new_violation_fingerprints: tuple[ViolationFingerprint, ...]
    full_state_novel: bool
    contract_violated: bool
    frame_observed: bool
    # Arm-INDEPENDENT observation of which boundary-gradient rungs the frame exhibited this step
    # (whatever the active search policy admits). The decompress escape -- a shapeless relative
    # hardlink resolved against the sandbox-root CWD -- is external-resolve-present but NOT
    # boundary-attempt-present, so these two booleans are how the A/C/D analysis reads each rung's
    # rate off any arm's evidence. Both False on an ineligible run or a missing/absent frame.
    frame_boundary_attempt_present: bool
    frame_external_resolve_present: bool
    eligible: bool
    already_retained: bool
    admission_eligible: bool

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("decision requires a case ID")
        if not isinstance(self.new_attempt_keys, tuple) or not all(
            isinstance(key, EffectFeedbackKey) for key in self.new_attempt_keys
        ):
            raise ValueError("decision requires boundary-attempt feedback keys")
        if not isinstance(self.new_violation_fingerprints, tuple) or not all(
            isinstance(item, ViolationFingerprint) for item in self.new_violation_fingerprints
        ):
            raise ValueError("decision requires violation fingerprints")
        for value in (
            self.full_state_novel,
            self.contract_violated,
            self.frame_observed,
            self.frame_boundary_attempt_present,
            self.frame_external_resolve_present,
            self.eligible,
            self.already_retained,
            self.admission_eligible,
        ):
            if type(value) is not bool:
                raise ValueError("decision flags must be bool")
        if not self.eligible and (
            self.new_attempt_keys
            or self.new_violation_fingerprints
            or self.full_state_novel
            or self.admission_eligible
        ):
            raise ValueError("ineligible observations must fail closed")

    @property
    def reward(self) -> int:
        """Generic scheduler reward: a new boundary-attempt key OR a new violation fingerprint."""
        return int(bool(self.new_attempt_keys) or bool(self.new_violation_fingerprints))

    @property
    def retained(self) -> bool:
        return self.admission_eligible and not self.already_retained


@dataclass(frozen=True, slots=True)
class DecompressEffectStats:
    observations: int
    eligible_observations: int
    retained_cases: int
    unique_attempt_keys: int
    unique_violation_fingerprints: int
    unique_full_states: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (
                self.observations,
                self.eligible_observations,
                self.retained_cases,
                self.unique_attempt_keys,
                self.unique_violation_fingerprints,
                self.unique_full_states,
            )
        ):
            raise ValueError("decompress effect stats must be nonnegative integers")


class DecompressEffectSearchState:
    """Boundary-attempt / violation / full-state novelty channels, fail-closed on eligibility."""

    def __init__(
        self,
        initial_cases: Sequence[ArchiveCase],
        search_policy: EffectSearchPolicy = EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT,
    ) -> None:
        if not isinstance(search_policy, EffectSearchPolicy):
            raise ValueError("search_policy must be a supported EffectSearchPolicy")
        cases = tuple(initial_cases)
        if not cases or not all(isinstance(case, ArchiveCase) for case in cases):
            raise ValueError("initial cases must be nonempty ArchiveCase records")
        if len({case.case_id for case in cases}) != len(cases):
            raise ValueError("initial cases contain duplicate case IDs")
        self._initial_cases = cases
        self._policy = search_policy
        # Same rung ladder as the node-tar EffectNoveltyIndex: the lexical boundary-attempt rung
        # is on for both P3 arms, and the region-based external-resolve rung is the refinement
        # that only P3_EXTERNAL_RESOLVE adds. Any non-P3 policy (the P1 random floor) admits
        # neither gradient rung and steers by full-state novelty + violations alone -- the floor.
        self._include_boundary_attempt = search_policy in (
            EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT,
            EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT,
        )
        self._include_external_resolve = (
            search_policy == EffectSearchPolicy.P3_EXTERNAL_RESOLVE_GRADIENT
        )
        self._keys: set[EffectFeedbackKey] = set()
        self._violations: set[ViolationFingerprint] = set()
        self._states: set[StateSignature] = set()
        self._entries: list[ArchiveCase] = []
        self._retained_ids: set[str] = set()
        self._observations = 0
        self._eligible_observations = 0

    @property
    def policy(self) -> EffectSearchPolicy:
        return self._policy

    def _admits(self, kind: EffectFeedbackKeyKind) -> bool:
        """Whether this arm steers on a frame key of the given rung kind."""
        if kind == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT:
            return self._include_boundary_attempt
        if kind == EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE:
            return self._include_external_resolve
        return False

    def consider(self, run: DecompressFrameRun) -> DecompressEffectDecision:
        if not isinstance(run, DecompressFrameRun):
            raise ValueError("decompress search requires a DecompressFrameRun")
        index = self._observations
        if index < len(self._initial_cases) and run.base_result.case != self._initial_cases[index]:
            raise ValueError("seed observations must match declared cases/order")
        self._observations += 1
        case_id = run.base_result.case.case_id
        eligible = run.base_result.execution.status in _ELIGIBLE_TERMINATIONS
        frame_observed = run.frame is not None
        if eligible:
            self._eligible_observations += 1
            # Derive every rung the frame exhibits from the UNCHANGED generic normalizer, record
            # each rung's arm-independent presence, then admit only the kinds this arm steers on.
            frame_keys = frame_boundary_attempt_keys(run.frame) if frame_observed else ()
            boundary_present = any(
                key.kind == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT for key in frame_keys
            )
            external_present = any(
                key.kind == EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE for key in frame_keys
            )
            attempt_keys = tuple(key for key in frame_keys if self._admits(key.kind))
            all_violations = violation_fingerprints(run.base_result.violations)
            new_keys = tuple(key for key in attempt_keys if key not in self._keys)
            new_violations = tuple(v for v in all_violations if v not in self._violations)
            state_novel = run.base_result.signature not in self._states
            self._keys.update(attempt_keys)
            self._violations.update(all_violations)
            self._states.add(run.base_result.signature)
            contract_violated = bool(all_violations)
        else:
            new_keys = ()
            new_violations = ()
            state_novel = False
            boundary_present = False
            external_present = False
            contract_violated = bool(violation_fingerprints(run.base_result.violations))
        already_retained = case_id in self._retained_ids
        admission_eligible = eligible and (bool(new_keys) or bool(new_violations) or state_novel)
        decision = DecompressEffectDecision(
            case_id,
            new_keys,
            new_violations,
            state_novel,
            contract_violated if eligible else False,
            frame_observed,
            boundary_present,
            external_present,
            eligible,
            already_retained,
            admission_eligible,
        )
        if decision.retained:
            self._entries.append(run.base_result.case)
            self._retained_ids.add(case_id)
        return decision

    def select_case(self, rng: random.Random) -> ArchiveCase:
        if self._observations < len(self._initial_cases):
            raise ValueError("parent selection requires a completed seed phase")
        if not self._entries:
            raise ValueError("cannot select a case from an empty decompress corpus")
        return rng.choice(self._entries)

    @property
    def entries(self) -> tuple[ArchiveCase, ...]:
        return tuple(self._entries)

    @property
    def stats(self) -> DecompressEffectStats:
        return DecompressEffectStats(
            self._observations,
            self._eligible_observations,
            len(self._entries),
            len(self._keys),
            len(self._violations),
            len(self._states),
        )


@dataclass(frozen=True, slots=True)
class DecompressEffectStep:
    serialization_schema: ClassVar[int] = 1

    index: int
    origin: CampaignOrigin
    parent_case_id: str | None
    run: DecompressFrameRun
    decision: DecompressEffectDecision
    mutation_attempt: MutationAttempt | None
    scheduler_evidence: EffectMutationSchedulerEvidence | None

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("step index must be nonnegative")
        if not isinstance(self.origin, CampaignOrigin) or not isinstance(
            self.run, DecompressFrameRun
        ):
            raise ValueError("step requires typed origin and run")
        if not isinstance(self.decision, DecompressEffectDecision):
            raise ValueError("step requires a typed decision")
        if self.decision.case_id != self.run.base_result.case.case_id:
            raise ValueError("step decision differs from its run")
        if (self.origin == CampaignOrigin.SEED) != (self.parent_case_id is None):
            raise ValueError("only mutation steps carry a parent case ID")
        if (self.origin == CampaignOrigin.SEED) != (self.mutation_attempt is None):
            raise ValueError("only mutation steps carry a mutation attempt")
        if (self.origin == CampaignOrigin.SEED) != (self.scheduler_evidence is None):
            raise ValueError("only mutation steps carry scheduler evidence")
        if self.mutation_attempt is not None and (
            self.mutation_attempt.child_case != self.run.base_result.case
            or self.mutation_attempt.parent_case_id != self.parent_case_id
        ):
            raise ValueError("mutation attempt differs from step lineage/run")


@dataclass(frozen=True, slots=True)
class DecompressEffectCampaignResult:
    serialization_schema: ClassVar[int] = 1

    config: DecompressEffectCampaignConfig
    initial_case_ids: tuple[str, ...]
    steps: tuple[DecompressEffectStep, ...]
    final_stats: DecompressEffectStats
    retained_case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.config, DecompressEffectCampaignConfig):
            raise ValueError("result requires a typed config")
        if (
            not isinstance(self.initial_case_ids, tuple)
            or not self.initial_case_ids
            or len(set(self.initial_case_ids)) != len(self.initial_case_ids)
        ):
            raise ValueError("result requires unique initial IDs")
        if not isinstance(self.steps, tuple) or not all(
            isinstance(step, DecompressEffectStep) for step in self.steps
        ):
            raise ValueError("result requires typed steps")
        if len(self.steps) != self.config.execution_budget or len(self.initial_case_ids) > len(
            self.steps
        ):
            raise ValueError("steps must fill the execution budget")
        if tuple(step.index for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("step indexes must be contiguous")
        if not isinstance(self.final_stats, DecompressEffectStats):
            raise ValueError("result requires final stats")
        if not isinstance(self.retained_case_ids, tuple) or not all(
            isinstance(case_id, str) and case_id for case_id in self.retained_case_ids
        ):
            raise ValueError("result requires retained case IDs")

    @property
    def discovered_violation(self) -> bool:
        """True iff any step's generic oracle verdict was a C0/C1/C2 violation (self-discovery)."""
        return any(step.decision.contract_violated for step in self.steps)


DecompressResultProducer = Callable[[ArchiveCase], DecompressFrameRun]
DecompressStepObserver = Callable[[DecompressEffectStep], None]

_STATE_AWARE_POLICIES = (
    MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK,
    MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND,
)


def _observed_name_segments(run: DecompressFrameRun, *, exclude_external: bool) -> set[str]:
    """Segment names of objects observed in the general filesystem tree (never protected_paths).

    Identical mechanism to ``effect_campaign._observed_name_segments``: the only names the
    state-aware escape policy learns come from ``ObjectSnapshot`` paths the run observed, not from
    the protected list (reading the protected list would be reading the answer). The blind control
    drops any object whose path is in the EXTERNAL region, so it never learns an external object's
    name. Target-agnostic (filters by Region, never by a specific name).
    """
    names: set[str] = set()
    for snapshot in (run.base_result.before, run.base_result.after):
        for obj in snapshot.objects:
            if exclude_external and path_region(obj.path) == Region.EXTERNAL:
                continue
            for segment in obj.path.split("/"):
                if segment and segment not in (".", ".."):
                    names.add(segment)
    return names


def run_decompress_effect_campaign(
    initial_cases: Sequence[ArchiveCase],
    produce_result: DecompressResultProducer,
    config: DecompressEffectCampaignConfig,
    on_step: DecompressStepObserver | None = None,
) -> DecompressEffectCampaignResult:
    """Drive the generic fuzz loop over a real-decompress producer; self-discover C0/C1/C2 hits.

    ``on_step`` receives each completed step right after feedback and scheduler bookkeeping, so a
    caller can persist the loop record incrementally; an aborting producer then leaves every
    finished step behind.
    """
    if not callable(produce_result) or not isinstance(config, DecompressEffectCampaignConfig):
        raise ValueError("campaign requires a producer and typed config")
    if on_step is not None and not callable(on_step):
        raise ValueError("on_step must be callable when given")
    cases = tuple(initial_cases)
    if not cases or not all(isinstance(case, ArchiveCase) for case in cases):
        raise ValueError("initial cases must be nonempty ArchiveCase records")
    if config.execution_budget < len(cases):
        raise ValueError("execution_budget must cover all initial cases")
    initial_ids = tuple(case.case_id for case in cases)
    if len(set(initial_ids)) != len(initial_ids):
        raise ValueError("initial cases contain duplicate case IDs")

    state = DecompressEffectSearchState(cases, config.search_policy)
    steps: list[DecompressEffectStep] = []
    state_aware = config.mutation_policy in _STATE_AWARE_POLICIES
    blind_observation = (
        config.mutation_policy == MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND
    )
    observed_names: set[str] = set()
    scheduler = (
        EffectAdaptiveMutationScheduler()
        if config.adaptive_scheduler
        else EffectUniformMutationScheduler()
    )

    def observe(
        case: ArchiveCase,
        origin: CampaignOrigin,
        parent: str | None,
        attempt: MutationAttempt | None = None,
        selection: MutationSelection | None = None,
    ) -> None:
        run = produce_result(case)
        if not isinstance(run, DecompressFrameRun) or run.base_result.case != case:
            raise ValueError("producer must return a DecompressFrameRun for the requested case")
        if state_aware:
            observed_names.update(_observed_name_segments(run, exclude_external=blind_observation))
        decision = state.consider(run)
        if (attempt is None) != (selection is None):
            raise ValueError("mutation attempt and scheduler selection must appear together")
        scheduler_evidence = None
        if attempt is not None and selection is not None:
            scheduler_evidence = scheduler.observe_outcome(
                selection,
                attempt,
                decision.new_attempt_keys,
                decision.new_violation_fingerprints,
            )
        step = DecompressEffectStep(
            len(steps), origin, parent, run, decision, attempt, scheduler_evidence
        )
        steps.append(step)
        if on_step is not None:
            on_step(step)

    for case in cases:
        observe(case, CampaignOrigin.SEED, None)

    rng = random.Random(config.random_seed)
    while len(steps) < config.execution_budget:
        parent = state.select_case(rng)
        selection = scheduler.choose_operator(operator_ids(config.mutation_policy), rng)
        attempt = apply_operator(
            parent,
            rng,
            config.mutation_policy,
            selection.operator_id,
            extra_components=tuple(sorted(observed_names)) if state_aware else (),
        )
        observe(attempt.child_case, CampaignOrigin.MUTATION, parent.case_id, attempt, selection)

    return DecompressEffectCampaignResult(
        config,
        initial_ids,
        tuple(steps),
        state.stats,
        tuple(entry.case_id for entry in state.entries),
    )


def decompress_effect_campaign_report(
    result: DecompressEffectCampaignResult, *, producer: str, label: str | None = None
) -> dict[str, object]:
    """Serialize a campaign to a JSON-ready report: config, per-step feedback, and the hit.

    ``producer`` labels where the runs came from (e.g. a native decompress image id), so a
    reader never mistakes a test/synthetic producer for a native run. ``discovered_violation``
    is the honest self-discovery outcome (a generic C0/C1/C2 verdict on some step); a false value
    is a true negative, not a failure. Reads only the typed result; invents nothing.
    """
    if not isinstance(result, DecompressEffectCampaignResult):
        raise ValueError("report requires a DecompressEffectCampaignResult")
    if not isinstance(producer, str) or not producer:
        raise ValueError("report requires a producer label")
    steps: list[dict[str, object]] = []
    for step in result.steps:
        base = step.run.base_result
        decision = step.decision
        steps.append(
            {
                "index": step.index,
                "origin": step.origin.value,
                "case_id": base.case.case_id,
                "parent_case_id": step.parent_case_id,
                "termination": base.execution.status.value,
                "oracle": {v.contract_id.value: v.violated for v in base.violations},
                "frame_observed": decision.frame_observed,
                "frame_attempts": len(step.run.frame["attempts"]) if step.run.frame else 0,
                "frame_error": step.run.frame_error,
                # Arm-independent frame observation of each boundary-gradient rung, so an A/C/D
                # roll-up reads boundary-attempt vs external-resolve rate off any arm's evidence.
                "boundary_attempt_present": decision.frame_boundary_attempt_present,
                "external_resolve_present": decision.frame_external_resolve_present,
                "new_attempt_keys": len(decision.new_attempt_keys),
                "new_violation_fingerprints": len(decision.new_violation_fingerprints),
                "full_state_novel": decision.full_state_novel,
                "contract_violated": decision.contract_violated,
                "reward": decision.reward,
                "retained": decision.retained,
                "operator_id": (
                    step.mutation_attempt.operator_id.value if step.mutation_attempt else None
                ),
            }
        )
    return {
        "decompress_campaign_schema": 1,
        "producer": producer,
        "label": label,
        "config": {
            "random_seed": result.config.random_seed,
            "execution_budget": result.config.execution_budget,
            "mutation_policy": result.config.mutation_policy.value,
            "search_policy": result.config.search_policy.value,
            "adaptive_scheduler": result.config.adaptive_scheduler,
        },
        "initial_case_ids": list(result.initial_case_ids),
        "discovered_violation": result.discovered_violation,
        "final_stats": {
            "observations": result.final_stats.observations,
            "eligible_observations": result.final_stats.eligible_observations,
            "retained_cases": result.final_stats.retained_cases,
            "unique_attempt_keys": result.final_stats.unique_attempt_keys,
            "unique_violation_fingerprints": result.final_stats.unique_violation_fingerprints,
            "unique_full_states": result.final_stats.unique_full_states,
        },
        "steps": steps,
        "retained_case_ids": list(result.retained_case_ids),
    }
