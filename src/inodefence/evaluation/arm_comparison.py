"""Single-path A/B/C/D arm comparison: a fixed arm->policy realization plus a
reused common-metric readout over in-memory ``SearchCampaignResult`` objects.

This is a measurement/harness scaffold, not a second search engine and not a new
effectiveness metric. It realizes the A/B/C/D experiment arms of
``docs/research/benchmarks/evaluation-protocol-v1.md`` ("Coverage baseline D and
the A/B/C/D common metric set") as concrete ``SearchCampaignConfig`` values so
every arm runs through the one ``run_search_campaign`` path, and it scores each
arm only with metrics already defined in that protocol's "Exact metrics" table,
computed the same way: the observation arithmetic is reused verbatim from
``evaluation.summary`` so any difference between arms reflects the policy, not the
measurement.

Honest boundaries (carried by naming and the emitted record, not enforced by
code, because they are research-interpretation limits):

* The violation counts are generic C0/C1/C2 contract OBSERVATIONS, never
  known-class rediscovery. Rediscovery needs the replay/pair layer and human
  root-cause review (see the protocol's rediscovery definition); a first observed
  violation index is not a confirmed hit index.
* No effectiveness ranking of the arms is produced or implied. A single
  unified-path A/B/C/D run is a scaffold; promoting any rate/latency claim needs
  the M3.4 pilot power and a frozen protocol (BACKLOG M3.4/M3.5), and
  comparison across arms is descriptive only.
* First-violation no-hit is right-censored at the budget ``N`` (reported as
  ``> N``), never imputed to a fictitious hit at ``N``.
* D is deliberately NOT scored by its own structure-coverage feature count
  (audit EN-008: more coverage features is search behavior, not effectiveness);
  it is scored with the same common metrics as every other arm.
* Repeatability and paired vulnerable/fixed discrimination are NOT computed here.
  They require multi-replay / cross-version evidence (``candidate_replay``,
  ``pair``) and are out of scope for a single in-memory comparison.

B0/B1/B3 policy semantics are untouched: this module only reads ``SearchDecision``
and ``RunResult`` fields produced by the existing ``SearchState``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from inodefence.campaign import (
    CampaignOrigin,
    SearchCampaignConfig,
    SearchCampaignResult,
    run_search_campaign,
)
from inodefence.feedback import FeedbackProjection, SearchPolicy
from inodefence.model import ArchiveCase, ExecutionStatus
from inodefence.model.provenance import ExecutionProvenance
from inodefence.mutator import MutationPolicy
from inodefence.runtime import SentinelSpec
from inodefence.targets.base import CampaignTarget

from .summary import _observation_counts

_MEASUREMENT_NOTE = (
    "generic C0/C1/C2 contract observations, not known-class rediscovery; "
    "a first observed violation index is not a confirmed hit index"
)
_COMPARISON_NOTE = (
    "descriptive per-arm metrics only; no effectiveness ranking is claimed. A "
    "single unified-path A/B/C/D run is a measurement scaffold; a rate/latency "
    "claim requires the M3.4 pilot power and a frozen protocol (BACKLOG M3.4/M3.5)"
)
_CENSORING_NOTE = (
    "first-violation no-hit is right-censored at the execution budget N (> N); "
    "no hit index is imputed at N"
)


class Arm(StrEnum):
    """The four experiment arms of the evaluation protocol's A/B/C/D metric set."""

    A = "A-random"
    B = "B-structure-aware"
    C = "C-state-aware"
    D = "D-coverage-guided"


@dataclass(frozen=True, slots=True)
class ArmSpec:
    """How one A/B/C/D arm is realized in the final-state ``run_search_campaign`` path.

    The realization follows ``evaluation-protocol-v1`` ("Coverage baseline D and
    the A/B/C/D common metric set"): A is the unretained walk (``SearchPolicy.B0``)
    with generic mutation; B adds a structure-aware input-mutation policy (the M1
    grammar) with no execution-feedback retention; C adds identity/external-effect
    state retention (``SearchPolicy.B3``, InodeFence); D adds target-agnostic
    structure-coverage retention (``SearchPolicy.D``). B, C and D share the M1
    mutation so C-vs-D isolates the retention TYPE (identity-specific vs
    coverage-general) and B is the no-retention pivot, while A is the random floor.

    ``feedback_projection`` stays ``FULL`` in the default arms; the A1/A2 projection
    ablation (RQ3) is a separate declared knob, not fixed by the arm label. This is
    an explicit, documented realization of a config the protocol leaves partly open
    (notably B's retention, fixed here to B0); it is not a validated choice and
    callers may override ``arm_specs`` for an ablation.
    """

    arm: Arm
    search_policy: SearchPolicy
    mutation_policy: MutationPolicy
    feedback_projection: FeedbackProjection
    description: str

    def __post_init__(self) -> None:
        for name, expected in (
            ("arm", Arm),
            ("search_policy", SearchPolicy),
            ("mutation_policy", MutationPolicy),
            ("feedback_projection", FeedbackProjection),
        ):
            if not isinstance(getattr(self, name), expected):
                raise ValueError(f"{name} must be a supported {expected.__name__}")
        if not isinstance(self.description, str) or not self.description:
            raise ValueError("arm spec requires a nonempty description")

    def config(self, *, random_seed: int, execution_budget: int) -> SearchCampaignConfig:
        """Materialize this arm as a campaign config; validation is delegated downstream."""
        return SearchCampaignConfig(
            random_seed,
            execution_budget,
            self.search_policy,
            self.mutation_policy,
            self.feedback_projection,
        )


DEFAULT_ARMS: Mapping[Arm, ArmSpec] = MappingProxyType(
    {
        Arm.A: ArmSpec(
            Arm.A,
            SearchPolicy.B0,
            MutationPolicy.LEGACY,
            FeedbackProjection.FULL,
            "random floor: unretained walk, generic mutation, no execution feedback",
        ),
        Arm.B: ArmSpec(
            Arm.B,
            SearchPolicy.B0,
            MutationPolicy.M1,
            FeedbackProjection.FULL,
            "structure-aware mutation (M1 grammar) with no execution-feedback retention",
        ),
        Arm.C: ArmSpec(
            Arm.C,
            SearchPolicy.B3,
            MutationPolicy.M1,
            FeedbackProjection.FULL,
            "state-aware: identity/external-effect retention key (InodeFence), M1 mutation",
        ),
        Arm.D: ArmSpec(
            Arm.D,
            SearchPolicy.D,
            MutationPolicy.M1,
            FeedbackProjection.FULL,
            "coverage-guided: target-agnostic structure-coverage retention, M1 mutation",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class CampaignMetrics:
    """Common metrics for one completed campaign, computed from in-memory evidence.

    Every field is a metric already defined in the protocol's "Exact metrics"
    table; the observation arithmetic (status counts, first violation, unique
    states/fingerprints) is the reused ``evaluation.summary`` computation. ``E`` is
    the number of complete ``RunResult`` records (all returned statuses count).
    Fields are labelled by the realizing policy/mutation/projection, not by arm, so
    the same readout serves any single-path campaign.
    """

    search_policy: SearchPolicy
    mutation_policy: MutationPolicy
    feedback_projection: FeedbackProjection
    total_executions: int
    execution_budget: int
    status_counts: Mapping[str, int]
    process_success_rate: float
    valid_input_rate: float
    executions_to_first_violation: int | None
    first_violation_censored: bool
    right_censored_at: int
    cumulative_target_seconds_to_first_violation: float | None
    unique_state_signatures: int
    unique_violation_fingerprints: int
    contract_observed_counts: Mapping[str, int]
    any_violation_executions: int
    admission_eligible_count: int
    admission_eligible_rate: float
    retained_after_seed: int
    retained_end: int
    corpus_growth: int


def campaign_metrics(result: SearchCampaignResult) -> CampaignMetrics:
    """Score one ``SearchCampaignResult`` with the protocol's common metrics.

    The violation/status/unique-signature arithmetic is reused verbatim from
    ``evaluation.summary`` so it matches the verified-export path exactly.
    Admission-eligible I/E and corpus growth read the per-step ``SearchDecision``
    (``admission_eligible`` and ``retained``), so B0 reports zero admission and zero
    growth by construction. ``executions_to_first_violation`` is 1-based and is
    ``None`` with ``first_violation_censored`` when no step observed a violation
    within the budget. ``cumulative_target_seconds_to_first_violation`` sums only
    ``ExecutionResult.duration_seconds`` through the first-violation step and is
    target-process time, not the protocol's full-latency metric.
    """
    runs = tuple(step.result for step in result.steps)
    counts = _observation_counts(runs)
    executions = counts["total_executions"]
    status = dict(counts["status_counts"])
    first = counts["first_observed_contract_violation"]
    budget = result.config.execution_budget

    admission_eligible = sum(1 for step in result.steps if step.feedback.admission_eligible)
    retained_after_seed = sum(
        1 for step in result.steps if step.origin == CampaignOrigin.SEED and step.feedback.retained
    )
    retained_end = len(result.retained_case_ids)

    seconds_to_first: float | None = None
    if first is not None:
        seconds_to_first = sum(
            step.result.execution.duration_seconds
            for step in result.steps[: first["execution_count"]]
        )

    rejected = status.get(ExecutionStatus.REJECTED.value, 0)
    success = status.get(ExecutionStatus.SUCCESS.value, 0)
    return CampaignMetrics(
        search_policy=result.config.search_policy,
        mutation_policy=result.config.mutation_policy,
        feedback_projection=result.config.feedback_projection,
        total_executions=executions,
        execution_budget=budget,
        status_counts=status,
        process_success_rate=success / executions if executions else 0.0,
        valid_input_rate=(executions - rejected) / executions if executions else 0.0,
        executions_to_first_violation=first["execution_count"] if first is not None else None,
        first_violation_censored=first is None,
        right_censored_at=budget,
        cumulative_target_seconds_to_first_violation=seconds_to_first,
        unique_state_signatures=counts["unique_state_signature_count"],
        unique_violation_fingerprints=counts["unique_violation_fingerprint_count"],
        contract_observed_counts=dict(counts["contract_observed_counts"]),
        any_violation_executions=counts["any_contract_observed_count"],
        admission_eligible_count=admission_eligible,
        admission_eligible_rate=admission_eligible / executions if executions else 0.0,
        retained_after_seed=retained_after_seed,
        retained_end=retained_end,
        corpus_growth=retained_end - retained_after_seed,
    )


@dataclass(frozen=True, slots=True)
class ArmComparison:
    """Per-arm common metrics from one shared seed/budget, plus honest caveats.

    Every arm ran through the same ``run_search_campaign`` path over identical
    initial cases, random seed, execution budget, target and sentinels; only the
    arm's declared policy/mutation/projection differs. The three note fields record
    the interpretation limits that this record cannot enforce in code.
    """

    random_seed: int
    execution_budget: int
    initial_case_ids: tuple[str, ...]
    arm_specs: Mapping[Arm, ArmSpec]
    metrics: Mapping[Arm, CampaignMetrics]
    measurement: str = _MEASUREMENT_NOTE
    comparison_status: str = _COMPARISON_NOTE
    censoring: str = _CENSORING_NOTE


def run_abcd_comparison(
    initial_cases: Sequence[ArchiveCase],
    target: CampaignTarget,
    *,
    random_seed: int,
    execution_budget: int,
    arms: Sequence[Arm] = (Arm.A, Arm.B, Arm.C, Arm.D),
    arm_specs: Mapping[Arm, ArmSpec] = DEFAULT_ARMS,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    provenance: ExecutionProvenance | None = None,
) -> ArmComparison:
    """Run each arm through ``run_search_campaign`` and score it identically.

    Everything except the arm's declared policy/mutation/projection is held
    constant across arms, so the comparison is single-path by construction. Each
    arm receives its own RNG seeded with the shared ``random_seed``; equal seeds do
    not imply identical evolved inputs because feedback changes parent pools (that
    is the point of the comparison). Campaign execution, isolation gating and
    completion are owned by ``run_search_campaign``; this driver adds no fallback
    and makes no effectiveness claim. The result's note fields carry the honest
    boundaries. Does not execute a formal/validated run on its own.
    """
    requested = tuple(arms)
    if not requested:
        raise ValueError("at least one arm is required")
    if any(not isinstance(arm, Arm) for arm in requested):
        raise ValueError("arms must be Arm members")
    if len(set(requested)) != len(requested):
        raise ValueError("arms must be distinct")
    missing = [arm for arm in requested if arm not in arm_specs]
    if missing:
        raise ValueError(f"arm_specs is missing specs for {missing}")

    cases = tuple(initial_cases)
    used_specs: dict[Arm, ArmSpec] = {}
    metrics: dict[Arm, CampaignMetrics] = {}
    for arm in requested:
        spec = arm_specs[arm]
        if spec.arm != arm:
            raise ValueError(f"arm_specs[{arm}] declares a different arm {spec.arm}")
        result = run_search_campaign(
            cases,
            target,
            spec.config(random_seed=random_seed, execution_budget=execution_budget),
            sentinels=sentinels,
            provenance=provenance,
        )
        used_specs[arm] = spec
        metrics[arm] = campaign_metrics(result)

    return ArmComparison(
        random_seed,
        execution_budget,
        tuple(case.case_id for case in cases),
        MappingProxyType(used_specs),
        MappingProxyType(metrics),
    )


def comparison_markdown(comparison: ArmComparison) -> str:
    """Render a descriptive per-arm table; the caveats below it are not decoration.

    The table reports the common metrics side by side with no ranking. A censored
    first violation prints as ``> N``. This renders recorded contract observations,
    never a rediscovery, effectiveness or vulnerability claim.
    """
    header = (
        "| Arm | Policy / mutation | E | exec→1st viol. | valid-input | "
        "success | uniq states | uniq viol. fp | admit I/E | corpus growth |"
    )
    separator = "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    rows = []
    for arm in comparison.metrics:
        metric = comparison.metrics[arm]
        first = (
            f"> {metric.right_censored_at}"
            if metric.first_violation_censored
            else str(metric.executions_to_first_violation)
        )
        rows.append(
            f"| {arm.value} | `{metric.search_policy.value}` / "
            f"`{metric.mutation_policy.value}` | {metric.total_executions} | {first} | "
            f"{metric.valid_input_rate:.3f} | {metric.process_success_rate:.3f} | "
            f"{metric.unique_state_signatures} | {metric.unique_violation_fingerprints} | "
            f"{metric.admission_eligible_rate:.3f} | {metric.corpus_growth} |"
        )
    lines = [
        "# A/B/C/D single-path arm comparison",
        "",
        f"Shared seed: {comparison.random_seed}; budget N: {comparison.execution_budget}; "
        f"seeds: {len(comparison.initial_case_ids)}.",
        "",
        header,
        separator,
        *rows,
        "",
        f"Measurement: {comparison.measurement}.",
        f"Comparison: {comparison.comparison_status}.",
        f"Censoring: {comparison.censoring}.",
    ]
    return "\n".join(lines) + "\n"
