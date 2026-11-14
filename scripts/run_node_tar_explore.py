"""Explore campaign: drive the existing effect feedback loop on a prepared node-tar image.

This connects the existing search loop (``inodefence.effect_campaign.run_effect_campaign`` plus
``inodefence.effect_pipeline.run_node_tar_effect_case``) to any prepared node-tar image, and emits
the result in the common ``inodefence-target-result-v1`` format with the campaign block
(``mode=campaign``). It builds no new engine: the loop, the disposable sandbox, the sentinels, the
container isolation, and the C0/C1/C2 oracle are reused unchanged. Finding a violation is not the
goal and is not guaranteed; connecting the loop to a chosen version's prepared image is.

Mutation vocabulary is the TOKEN-CLEAN generic escaping-hardlink arm
(``MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK``): no ``sentinel.txt`` / ``outside`` or any other
victim-specific token enters the mutation vocabulary, the feedback, or the oracle, so an observed
violation is a blind find rather than a replay of a hardcoded path. (The historical demo uses the
*sighted* vocabulary on purpose; an exploration must not.) Only the hardlink slot is specialized to
aim outside the extraction root; there is no operator that coordinates one entry to write through a
link another entry created.

Confirmatory-experiment node-tar versions are refused with the reason printed: the catalog
train/fixed pair and the holdout, read from ``run_effect_demo.historical_target_versions`` (never a
duplicated constant), and anything before 7.5.0. The result is labeled an exploratory campaign; it
is never a qualification or confirmatory-experiment result. Image preparation runs on the host
(reusing the AUTO_PREPARE layer) before this runs inside the controller like the other effect
campaigns.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from scripts.run_effect_demo import historical_target_versions

from inodefence.builder import build_tar
from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_pipeline import NativeEffectRun, run_node_tar_effect_case
from inodefence.execution import ExecutionBackend
from inodefence.feedback.effect_search import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ArchiveCase, EffectRunResult, ExecutionStatus
from inodefence.mutator.policy import MutationPolicy
from inodefence.runtime import SentinelSpec
from inodefence.target_result import (
    RUN_ERROR,
    CampaignInfo,
    CaseVerdict,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)
from inodefence.targets.node_tar_effect import NativeEffectProfile, NodeTarEffectTarget

#: Exploratory search over a prepared image, never a qualification or confirmatory result.
EXPLORE_LABEL = "exploratory campaign"
#: node-tar before this is out of scope for exploration (a floor, not the confirmatory list).
EXPLORE_MIN_VERSION = (7, 5, 0)
#: The effect path captures a full before/after snapshot, so all three contracts are observed.
EXPLORE_OBSERVED_CONTRACTS = ("C0", "C1", "C2")
#: The InodeFence effect-adaptive retention/scheduling arm (same as the historical demo default).
EXPLORE_SEARCH_POLICY = EffectSearchPolicy.P2_EFFECT_ADAPTIVE
#: Token-clean escaping-hardlink operators: no victim-specific token in the vocabulary.
EXPLORE_MUTATION_POLICY = MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class ExploreVersionRefused(ValueError):
    """The requested node-tar version is out of scope for exploration (with the reason)."""

    def __init__(self, version: str, reason: str) -> None:
        super().__init__(f"explore refuses node-tar {version}: {reason}")
        self.version = version
        self.reason = reason


def _parse_version(version: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.fullmatch(version.strip())
    if match is None:
        return None
    return (int(match[1]), int(match[2]), int(match[3]))


def excluded_explore_version(
    version: str, *, confirmatory: Sequence[str] | None = None
) -> str | None:
    """Reason this version may not be explored, or ``None`` if it may.

    ``confirmatory`` defaults to the frozen catalog train/fixed pair plus the holdout, read from
    ``historical_target_versions()`` so the exclusion is never a duplicated constant. Anything in
    that set, anything before 7.5.0, and any unrecognizable version string is refused.
    """
    names = tuple(confirmatory) if confirmatory is not None else tuple(historical_target_versions())
    if version in names:
        return (
            "confirmatory-experiment target (catalog train/fixed or holdout); "
            "excluded from exploration until an unseal decision"
        )
    parsed = _parse_version(version)
    if parsed is None:
        return f"unrecognized node-tar version string {version!r}"
    if parsed < EXPLORE_MIN_VERSION:
        return "node-tar before 7.5.0 is out of scope for this exploration"
    return None


@dataclass(frozen=True, slots=True)
class ExploreCase:
    """One executed case: its outcome, the tri-state C0/C1/C2, and the exact TAR bytes run."""

    outcome: str
    c0: bool | None
    c1: bool | None
    c2: bool | None
    tar_bytes: bytes

    @property
    def violated(self) -> bool:
        return True in (self.c0, self.c1, self.c2)


def explore_case_from_run(run: NativeEffectRun, archive: bytes) -> ExploreCase:
    """Map one effect run to an ExploreCase: run error -> all ``None``, else the oracle verdicts."""
    base = run.result.base_result
    if base.execution.status is not ExecutionStatus.SUCCESS:
        return ExploreCase(RUN_ERROR, None, None, None, archive)
    verdicts = {verdict.contract_id.value: verdict.violated for verdict in base.violations}
    return ExploreCase(
        "extracted", verdicts.get("C0"), verdicts.get("C1"), verdicts.get("C2"), archive
    )


def build_explore_result(
    *,
    target_version: str,
    image_ref: str | None,
    image_id: str | None,
    engine_sha: str | None,
    engine_dirty: bool,
    seed: int,
    budget: int,
    cases: Sequence[ExploreCase],
) -> TargetResult:
    """Assemble the common campaign result from the per-case records, in run order.

    Case IDs are the run index (``step-<i>``); the real archive of each is saved beside the result
    as ``inputs/step-<i>.tar``. ``runs_to_first_violation`` is the 1-based index of the first case
    that violated an observed contract, or ``None`` when none did within the budget.
    """
    verdicts = tuple(
        CaseVerdict(f"step-{index}", case.outcome, case.c0, case.c1, case.c2)
        for index, case in enumerate(cases)
    )
    repro = tuple(
        repro_input(f"step-{index}", f"inputs/step-{index}.tar", case.tar_bytes)
        for index, case in enumerate(cases)
    )
    first_violation: int | None = None
    for index, case in enumerate(cases):
        if case.violated:
            first_violation = index + 1
            break
    return TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version=target_version),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=EXPLORE_OBSERVED_CONTRACTS,
        cases=verdicts,
        repro_inputs=repro,
        provenance=Provenance(engine_sha, engine_dirty, image_ref, image_id),
        campaign=CampaignInfo(seed=seed, budget=budget, runs_to_first_violation=first_violation),
    )


def run_explore_campaign(
    backend: ExecutionBackend,
    image_id: str,
    *,
    seed: int,
    budget: int,
    image_ref: str | None = None,
    engine_sha: str | None = None,
    engine_dirty: bool = False,
    search_policy: EffectSearchPolicy = EXPLORE_SEARCH_POLICY,
    mutation_policy: MutationPolicy = EXPLORE_MUTATION_POLICY,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
) -> TargetResult:
    """Bind the prepared image, refuse confirmatory/old versions, run the loop, map to the format.

    ``backend`` is the controller's ``ExecutionBackend`` (any object the effect target accepts). The
    archive each case runs is rebuilt here for the saved repro input and checked against the run's
    own archive hash, so the saved TAR is exactly what was extracted.
    """
    target = NodeTarEffectTarget.bind(backend, image_id, profile=NativeEffectProfile.FULL)
    reason = excluded_explore_version(target.tar_version)
    if reason is not None:
        raise ExploreVersionRefused(target.tar_version, reason)
    config = EffectCampaignConfig(
        random_seed=seed,
        execution_budget=budget,
        search_policy=search_policy,
        mutation_policy=mutation_policy,
    )
    records: list[ExploreCase] = []

    def produce(case: ArchiveCase) -> EffectRunResult:
        archive = build_tar(case)
        run = run_node_tar_effect_case(case, target, sentinels=sentinels)
        if run.archive_sha256 != run.result.base_result.archive_sha256:
            raise ValueError("explore archive binding differs from the effect run")
        records.append(explore_case_from_run(run, archive))
        return run.result

    run_effect_campaign(minimal_seed_corpus(), produce, config)
    return build_explore_result(
        target_version=target.tar_version,
        image_ref=image_ref,
        image_id=image_id,
        engine_sha=engine_sha,
        engine_dirty=engine_dirty,
        seed=seed,
        budget=budget,
        cases=records,
    )
