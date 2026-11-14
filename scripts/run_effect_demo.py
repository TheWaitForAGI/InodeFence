"""P0-5 effect loop demo: seed -> producer -> oracle -> feedback -> next mutation.

The CLI runs only the synthetic producer; its results are fixtures, not node-tar
evidence. `native_demo_report` runs inside the trusted Linux controller
(container_host effect-demo, `make demo`) against the real node-tar image.
"""

import argparse
import base64
import json
import sys
import traceback
from collections import Counter
from collections.abc import Callable, Mapping
from hashlib import sha256
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import cast

from inodefence.builder import build_tar
from inodefence.campaign_hooks import CampaignHooks, LightCampaignResult
from inodefence.effect_campaign import (
    EffectCampaignConfig,
    EffectCampaignResult,
    run_effect_campaign,
)
from inodefence.effect_demo import (
    DEMO_REPORT_SCHEMA,
    EffectStepReporter,
    effect_campaign_report,
    render_effect_campaign_report,
)
from inodefence.effect_pipeline import NativeEffectRun, run_node_tar_effect_case
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation import rds as _rds
from inodefence.execution.base import ExecutionBackend
from inodefence.execution.stall_recovery import StallRecovery
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.live_effect import live_step_from_effect
from inodefence.live_exploration import REPLAY_COMMAND_TEMPLATE, LiveRecorder, LiveRunMeta
from inodefence.model import (
    ArchiveCase,
    EffectRunResult,
    EffectStreamCompleteness,
    ExecutionStatus,
)
from inodefence.mutator import MutationPolicy
from inodefence.runtime import SentinelSpec
from inodefence.sentinel_set import (
    MAX_SENTINEL_COUNT,
    GeneratedSentinelSet,
    generate_sentinel_set,
)
from inodefence.target_result import JUDGED
from inodefence.targets.node_tar_effect import (
    NativeEffectProfile,
    NodeTarEffectTarget,
    archive_references,
)
from inodefence.targets.node_tar_recipe import demo_image_recipe

NATIVE_UNAVAILABLE = (
    "native producer is not runnable from this entrypoint: "
    "실제 실행은 controller 안에서 container_host effect-demo 모드로 (make demo)"
)
# Top-level report label; native reports carry "demo run" instead.
SYNTHETIC_LABEL = "SYNTHETIC (not node-tar)"
DEFAULT_NATIVE_BUDGET = 20
# Per-campaign execution ceiling (number of cases/steps). Raised from 100 to allow
# real-scale autonomous-discovery studies that need many thousands of executions across
# seeds; 100 was a toy ceiling. This is only the step-count ceiling — the safety
# boundary, container isolation, disposable sandbox + sentinel, pinned/frozen target
# versions and the oracle are all unchanged.
MAX_NATIVE_BUDGET = 2000
NODE_TAR_PIN = Path(__file__).resolve().parents[1] / "tools" / "node-tar" / "package.json"

# P2-c historical state-aware campaign. This is a separate path from the benign
# demo: native_demo_report stays pinned to the repository node-tar (7.5.22), and
# this path admits only the catalog-registered historical pair (7.5.2/7.5.3),
# cross-checked against the retained wrapper locks. Arbitrary images/versions are
# rejected; seeds are RNG integers only; results are labeled "demo run", never
# rediscovery or vulnerability.
_REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = _REPO_ROOT / "experiments" / "benchmarks" / "catalog-v1.json"
HISTORICAL_LOCKS_DIR = _REPO_ROOT / "experiments" / "benchmarks" / "locks"
HISTORICAL_BENCHMARK_ID = "node-link-sanitize"
# EXP-2 holdout (D040-D2: this one row is the human-approved extension; FROZEN_TARGETS and the
# catalog stay as they are). (node-tar version, sha256 of its wrapper lock in
# HISTORICAL_LOCKS_DIR), set from the D4 qualification result as the last engine diff before
# freeze. None: no holdout version is admitted, so a holdout registration is refused at dry-run.
HOLDOUT_TARGET: tuple[str, str] | None = (
    "7.4.4",
    "38b636640f941953189084d01a37db2f919049d6e0c7388cf86af1bc07e19c84",
)
HISTORICAL_DEMO_MODE = "effect-demo-historical"
EXPLORE_DEMO_MODE = "effect-demo-explore"
# M4 self-discovery: the effect campaign over a second extractor (decompress). Shares the
# --seed/--budget/--mutation-policy demo arguments. --policy (EffectSearchPolicy) now selects the
# decompress search arm on the same gradient-rung ladder node-tar uses: P3_EXTERNAL_RESOLVE (C,
# identity-state) admits both the boundary-attempt and external-resolve rungs, P3_BOUNDARY_ATTEMPT
# (D, coverage) admits only the boundary-attempt rung, and the P1 floor (A) admits neither. When
# --policy is absent the loop's default admits both rungs, unchanged from before the arm split.
DECOMPRESS_CAMPAIGN_MODE = "decompress-effect-campaign"
# M4 self-discovery over a THIRD extractor (oras-go). Shares the --seed/--budget/--mutation-policy
# demo arguments; --policy (EffectSearchPolicy) does not apply (its own novelty channels) and is
# ignored for this mode, exactly like the decompress campaign.
ORAS_GO_CAMPAIGN_MODE = "oras-go-effect-campaign"
DEMO_MODES = (
    "effect-demo",
    HISTORICAL_DEMO_MODE,
    EXPLORE_DEMO_MODE,
    DECOMPRESS_CAMPAIGN_MODE,
    ORAS_GO_CAMPAIGN_MODE,
)
HISTORICAL_LABEL = "demo run"
EXPLORATION_LABEL = "exploratory demo run"
HISTORICAL_SEARCH_POLICY = EffectSearchPolicy.P2_EFFECT_ADAPTIVE
HISTORICAL_MUTATION_POLICY = MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK

# Exploration defaults to the registered experiment's S-u arm (state-retention + observed-names
# vocabulary), taken from ``evaluation.rds`` by reference -- not copied values -- so the two can
# never drift. The registered-experiment path (rds.py's arm/vocabulary definitions, run_exp0,
# FROZEN_TARGETS) is only read here, never modified. The demo paths keep HISTORICAL_* above.
EXPLORE_SEARCH_POLICY = _rds.arm_search_policy(_rds.RdsArm.S_U)
EXPLORE_VOCABULARY_MODE = _rds.VocabularyMode.OBSERVED_NAMES
EXPLORE_MUTATION_POLICY = _rds.VOCABULARY_MUTATION_POLICY[EXPLORE_VOCABULARY_MODE]

#: An exception chain longer than this is cut; the record says so.
ERROR_CHAIN_LIMIT = 8
ERROR_CHAIN_MESSAGE_LIMIT = 2000
#: Frames kept per exception, innermost first to survive; ``frames_cut`` counts the rest.
ERROR_CHAIN_FRAME_LIMIT = 24


def _frame_file(path: str) -> str:
    """Repository-relative when recognizable, otherwise the base name. Never an absolute path."""
    parts = PurePosixPath(path).parts
    for root in ("inodefence", "scripts"):
        if root in parts:
            last = len(parts) - 1 - parts[::-1].index(root)
            return "/".join(parts[last:])
    return parts[-1] if parts else ""


def _frames(error: BaseException) -> tuple[list[dict[str, object]], int]:
    """Where an exception travelled: file, line and function of each frame, outermost first.

    The last frame is the ``raise``. Reads code object names and line numbers only: no source
    line, no local variable, no argument. The same message can come from several call sites, so
    this is what tells them apart.
    """
    frames: list[dict[str, object]] = [
        {
            "file": _frame_file(frame.f_code.co_filename),
            "line": line,
            "function": frame.f_code.co_qualname,
        }
        for frame, line in traceback.walk_tb(error.__traceback__)
    ]
    return frames[-ERROR_CHAIN_FRAME_LIMIT:], max(0, len(frames) - ERROR_CHAIN_FRAME_LIMIT)


def exception_chain(error: BaseException) -> list[dict[str, object]]:
    """The raised exception and everything it replaced, outermost first; the last came first.

    A cleanup failure raised in a ``finally`` replaces the error in flight, so ``str(error)``
    can name only the cleanup. Python keeps the replaced error on ``__context__``, and ``raise
    ... from`` keeps it on ``__cause__``. Reporting only: nothing classifies on this.
    """
    chain: list[dict[str, object]] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if len(chain) == ERROR_CHAIN_LIMIT:
            chain.append({"truncated": True})
            break
        seen.add(id(current))
        frames, frames_cut = _frames(current)
        chain.append(
            {
                "type": f"{type(current).__module__}.{type(current).__qualname__}",
                "message": str(current)[:ERROR_CHAIN_MESSAGE_LIMIT],
                "frames": frames,
                "frames_cut": frames_cut,
            }
        )
        current = current.__cause__ or current.__context__
    return chain


def case_shape(case: ArchiveCase) -> dict[str, object]:
    """Size of the aborted case, so an abort can be compared with the campaign's other steps.

    A step that aborts leaves no step record. Counts only: no path or link target.
    """
    types = Counter(entry.entry_type.value for entry in case.entries)
    return {
        "entries": len(case.entries),
        "entry_types": dict(sorted(types.items())),
        "content_bytes": sum(len(entry.content or b"") for entry in case.entries),
    }


class NativeDemoAborted(RuntimeError):
    """Infrastructure failure: stop the demo instead of recording a result.

    Raised for backend/identity/observer exceptions and for broken evidence after a
    successful target run. Target outcomes (rejected/failed/timed_out) are results,
    even when their trace is invalid: node-tar can reject while an fs operation is
    still in flight, and the producer stops recording when tar.x() rejects. Such
    traces stay feedback-ineligible and keep their observation_failures.
    """

    def __init__(
        self,
        step_index: int,
        case_id: str | None,
        reason: str,
        observed: dict[str, object] | None = None,
        error_chain: list[dict[str, object]] | None = None,
        case_shape: dict[str, object] | None = None,
    ) -> None:
        super().__init__(f"step {step_index} case {case_id}: {reason}")
        self.step_index = step_index
        self.case_id = case_id
        self.reason = reason
        # Raw target output of the aborted case, kept as observed (not reinterpreted).
        self.observed = observed
        # The raised exception and what it replaced. `reason` keeps naming the outermost one.
        self.error_chain = error_chain
        self.case_shape = case_shape


def synthetic_demo_report(
    seed: int,
    budget: int,
    policy: EffectSearchPolicy,
    mutation_policy: MutationPolicy,
) -> dict[str, object]:
    config = EffectCampaignConfig(
        random_seed=seed,
        execution_budget=budget,
        search_policy=policy,
        mutation_policy=mutation_policy,
    )
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    report = effect_campaign_report(result, "synthetic")
    report.update(label=SYNTHETIC_LABEL)
    return report


def synthetic_demo_json(
    seed: int,
    budget: int,
    policy: EffectSearchPolicy,
    mutation_policy: MutationPolicy,
) -> str:
    return render_effect_campaign_report(
        synthetic_demo_report(seed, budget, policy, mutation_policy)
    )


DEMO_ARGUMENTS = ("seed", "budget", "policy", "mutation_policy")
# The opt-in multi-sentinel flags are restricted to the node-tar effect demos
# (both go through run_node_tar_effect_case over a disposable sandbox).
SENTINEL_DEMO_MODES = ("effect-demo", HISTORICAL_DEMO_MODE, EXPLORE_DEMO_MODE)
# Arguments the host broker forwards verbatim to the controller. tar_version is
# historical-only; the four DEMO_ARGUMENTS are shared by both effect demos;
# observer-integrity-policy and the two opt-in sentinel flags default to the
# frozen single-sentinel behavior.
DEMO_FORWARDED_ARGUMENTS = (
    *DEMO_ARGUMENTS,
    "tar_version",
    "observer_integrity_policy",
    "sentinel_count",
    "sentinel_seed",
    "live_dir",
    "engine_commit",
)


def add_demo_arguments(parser: argparse.ArgumentParser) -> None:
    """effect-demo(s) only; defaults apply inside the reports (P2, 123, 20, policy)."""
    parser.add_argument("--seed", type=int)
    parser.add_argument("--budget", type=int)
    parser.add_argument("--policy", choices=tuple(policy.value for policy in EffectSearchPolicy))
    parser.add_argument(
        "--mutation-policy", choices=tuple(policy.value for policy in MutationPolicy)
    )
    parser.add_argument(
        "--tar-version",
        help="catalog-registered historical node-tar version; effect-demo-historical only",
    )
    parser.add_argument(
        "--sentinel-count",
        type=int,
        help=f"opt-in: number of randomly named external sentinels (1..{MAX_SENTINEL_COUNT}); "
        "node-tar effect demos only; requires --sentinel-seed (default: one sentinel)",
    )
    parser.add_argument(
        "--sentinel-seed",
        type=int,
        help="opt-in: PRNG seed for generated sentinel names; requires --sentinel-count",
    )
    parser.add_argument(
        "--observer-integrity-policy",
        choices=("stop", "invalid-continue"),
        help=(
            "observer-integrity STOP policy; effect-demo and effect-demo-historical only. "
            "'stop' (default) aborts the campaign on a successful run with an untrustworthy "
            "trace; 'invalid-continue' keeps the step as validity=invalid and continues"
        ),
    )
    parser.add_argument(
        "--live-dir",
        help="exploration only: the controller writes live progress/violation snapshots here",
    )
    parser.add_argument(
        "--engine-commit",
        help="exploration only: host-side engine revision, recorded in the live meta for replay",
    )


def check_demo_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    given = [name for name in DEMO_ARGUMENTS if getattr(args, name) is not None]
    if given and args.mode not in DEMO_MODES:
        parser.error("--seed/--budget/--policy/--mutation-policy are restricted to effect demos")
    if args.budget is not None:
        if args.budget < 1:
            parser.error("effect demo budget must be >= 1")
        # Exploration has NO upper budget cap: it streams steps (retain_steps=False) so memory does
        # not grow with the run count, and a long single campaign is the point. Every other mode
        # (demo, historical, qualification) keeps the cap so a bounded run cannot be asked for an
        # unbounded one by mistake. This is the only budget rule the explore mode relaxes.
        if args.mode != EXPLORE_DEMO_MODE and args.budget > MAX_NATIVE_BUDGET:
            parser.error(f"effect demo budget must be in 1..{MAX_NATIVE_BUDGET}")
    tar_version = getattr(args, "tar_version", None)
    if tar_version is not None and args.mode not in (HISTORICAL_DEMO_MODE, EXPLORE_DEMO_MODE):
        parser.error("--tar-version is restricted to effect-demo-historical / effect-demo-explore")
    if args.mode in (HISTORICAL_DEMO_MODE, EXPLORE_DEMO_MODE) and tar_version is None:
        parser.error(f"{args.mode} requires --tar-version (the resolved node-tar version)")
    count = getattr(args, "sentinel_count", None)
    seed = getattr(args, "sentinel_seed", None)
    if (count is None) != (seed is None):
        parser.error("--sentinel-count and --sentinel-seed must be given together")
    if count is not None:
        if args.mode not in SENTINEL_DEMO_MODES:
            parser.error("--sentinel-count/--sentinel-seed are restricted to node-tar effect demos")
        if not 1 <= count <= MAX_SENTINEL_COUNT:
            parser.error(f"--sentinel-count must be in 1..{MAX_SENTINEL_COUNT}")
    if getattr(args, "observer_integrity_policy", None) is not None and args.mode not in (
        "effect-demo",
        HISTORICAL_DEMO_MODE,
        EXPLORE_DEMO_MODE,
    ):
        parser.error("--observer-integrity-policy is restricted to the effect demos")


def demo_options(args: argparse.Namespace) -> dict:
    options: dict = {}
    if args.seed is not None:
        options["seed"] = args.seed
    if args.budget is not None:
        options["budget"] = args.budget
    if args.policy is not None:
        options["policy"] = EffectSearchPolicy(args.policy)
    if args.mutation_policy is not None:
        options["mutation_policy"] = MutationPolicy(args.mutation_policy)
    if getattr(args, "observer_integrity_policy", None) == "invalid-continue":
        options["observer_integrity_continue"] = True
    return options


def sentinel_set_from_args(args: argparse.Namespace) -> GeneratedSentinelSet | None:
    """Build the opt-in generated sentinel set, or None for the default single sentinel.

    Returns None unless both --sentinel-count and --sentinel-seed are set, so a demo
    run with neither flag keeps the unchanged single-sentinel sandbox byte-for-byte.
    """
    count = getattr(args, "sentinel_count", None)
    seed = getattr(args, "sentinel_seed", None)
    if count is None or seed is None:
        return None
    return generate_sentinel_set(seed, count)


def apply_sentinel_set_record(
    report: dict[str, object], sentinel_set: GeneratedSentinelSet | None
) -> dict[str, object]:
    """Record the generated sentinel set (generator seed/count/names) in a report.

    No-op when ``sentinel_set`` is None, so default single-sentinel reports gain no
    ``sentinel_set`` key and stay identical to before. Mutates and returns ``report``.
    """
    if sentinel_set is not None:
        report["sentinel_set"] = sentinel_set.describe()
    return report


def pinned_node_tar_version(package_json: Path = NODE_TAR_PIN) -> str:
    """The node-tar version the repository pins for the target image build."""
    return json.loads(package_json.read_text(encoding="utf-8"))["dependencies"]["tar"]


def _native_check(case: ArchiveCase, result: EffectRunResult, flush: bool, error: str | None):
    trace = result.trace
    observed = {event.entry.entry_index for event in trace.lifecycle_events}
    return {
        "case_id": case.case_id,
        "status": result.base_result.execution.status.value,
        "exit_code": result.base_result.execution.exit_code,
        "termination": trace.termination.value,
        "completeness": trace.completeness.value,
        "integrity_valid": trace.integrity_valid,
        "controller_flush_verified": flush,
        "transport_error": error,
        "archive_entries_match": trace.archive_entries == archive_references(case),
        "entries_total": len(case.entries),
        "entries_with_lifecycle_events": len(observed),
        "entries": [
            {"type": entry.entry_type.value, "path": entry.path, "link_target": entry.link_target}
            for entry in case.entries
        ],
        "observation_failures": [
            {"kind": item.kind.value, "message": item.message, "sequence": item.sequence}
            for item in trace.observation_failures
        ],
    }


def _target_timed_out(run: NativeEffectRun) -> bool:
    return run.result.base_result.execution.status == ExecutionStatus.TIMED_OUT


def _run_native_case(
    case: ArchiveCase,
    target: NodeTarEffectTarget,
    sentinels: tuple[SentinelSpec, ...],
    stall_recovery: StallRecovery | None,
    index: int,
) -> NativeEffectRun:
    """One case; with ``stall_recovery`` a Docker stall re-executes it in a new container.

    Each attempt is a whole ``run_node_tar_effect_case`` call (new sandbox, run root and
    containers). Without ``stall_recovery`` this is exactly the single call it replaces.
    """

    def attempt() -> NativeEffectRun:
        return run_node_tar_effect_case(case, target, sentinels=sentinels)

    if stall_recovery is None:
        return attempt()
    return stall_recovery.run(
        attempt,
        timed_out=_target_timed_out,
        step_index=index,
        case_id=case.case_id,
    )


def apply_infra_reexecutions(
    report: dict[str, object], stall_recovery: StallRecovery | None
) -> None:
    """Add the re-execution count and discarded-attempt records only when there are any.

    Both keys are absent when nothing stalled, so a stall-free report is unchanged. A
    discarded attempt's oracle result is never recorded (outcome-blind).
    """
    if stall_recovery is not None and stall_recovery.events:
        report["infra_reexecution_count"] = stall_recovery.reexecution_count
        report["infra_reexecutions"] = list(stall_recovery.events)


def native_demo_report(
    backend: ExecutionBackend,
    image_id: str,
    *,
    seed: int = 123,
    budget: int = DEFAULT_NATIVE_BUDGET,
    policy: EffectSearchPolicy = EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
    mutation_policy: MutationPolicy = MutationPolicy.M1,
    step_sink: Callable[[dict[str, object]], None] | None = None,
    sentinel_set: GeneratedSentinelSet | None = None,
    observer_integrity_continue: bool = False,
    stall_recovery: StallRecovery | None = None,
) -> dict[str, object]:
    """Run the effect loop on real node-tar (FULL profile); label the result a demo run.

    Must run inside the controller: `backend` creates disposable target containers
    over sandboxes with sentinels. Mutated cases may carry `../` or `/` paths.
    `step_sink` gets each finished step's report record (identical to `steps[i]`
    of the returned report) before the next case runs, so a NativeDemoAborted
    later still leaves the completed loop record with the caller.

    `sentinel_set` is the opt-in multi-sentinel set (generator seed, count and
    randomly generated names); None keeps the unchanged single default sentinel.
    When set, its specs feed every sandbox and the report records describe().

    `observer_integrity_continue` selects the observer-integrity STOP policy. When
    False (default, the frozen behavior) a target that succeeds with an
    untrustworthy effect trace aborts the campaign. When True the step is kept
    instead: the reader already keeps it feedback-ineligible and off the retained
    corpus, so it consumes one budget unit, is marked `validity=invalid`
    (`invalid_reason=observer_integrity`) in the report, and the loop continues.
    The snapshot C0/C1/C2 oracle verdict is independent of the trace and is
    recorded either way, so the preregistration hit count is unchanged.

    `stall_recovery` (built by the controller over the backend's client) re-executes a
    case after a Docker infrastructure stall instead of aborting or recording the stall
    as a target timeout (`inodefence.execution.stall_recovery`). Discarded attempts
    appear as the report's `infra_reexecution_count` and `infra_reexecutions`, keys that are
    absent when there were none; steps and native_checks are unchanged.
    """
    if type(budget) is not int or not 1 <= budget <= MAX_NATIVE_BUDGET:
        raise ValueError(f"native demo budget must be in 1..{MAX_NATIVE_BUDGET}")
    sentinels = sentinel_set.specs if sentinel_set is not None else (SentinelSpec(),)
    config = EffectCampaignConfig(
        random_seed=seed,
        execution_budget=budget,
        search_policy=policy,
        mutation_policy=mutation_policy,
    )
    target = NodeTarEffectTarget.bind(backend, image_id, profile=NativeEffectProfile.FULL)
    pinned = pinned_node_tar_version()
    if target.tar_version != pinned:
        raise NativeDemoAborted(
            0, None, f"image node-tar {target.tar_version} differs from repository pin {pinned}"
        )
    checks: list[dict[str, object]] = []
    timing: list[dict[str, object]] = []

    produce = _native_effect_producer(
        target,
        sentinels,
        stall_recovery,
        checks=checks,
        timing=timing,
        observer_integrity_continue=observer_integrity_continue,
    )

    reporter = EffectStepReporter()

    def record_step(step) -> None:
        record = reporter.add(step)
        if step_sink is not None:
            step_sink(record)

    started = perf_counter()
    result = run_effect_campaign(minimal_seed_corpus(), produce, config, on_step=record_step)
    total = perf_counter() - started
    report = effect_campaign_report(result, "native")
    report.update(
        label="demo run",
        node_tar_version=target.tar_version,
        node_version=target.node_version,
        image_id=image_id,
        # Content-addressed provenance of the committed recipe this image is built
        # from: binds the observed image_id to a reproducible "same recipe -> same
        # build context" fingerprint (additive; no existing field changes).
        image_recipe=demo_image_recipe(),
        native_checks=checks,
        # Wall-clock values differ per run; keep them apart from the loop record.
        timing={"total_seconds": total, "per_case": timing},
    )
    apply_sentinel_set_record(report, sentinel_set)
    apply_infra_reexecutions(report, stall_recovery)
    return report


def exploration_demo_report(
    backend: ExecutionBackend,
    image_id: str,
    tar_version: str,
    *,
    seed: int = 123,
    budget: int = DEFAULT_NATIVE_BUDGET,
    policy: EffectSearchPolicy = EXPLORE_SEARCH_POLICY,
    mutation_policy: MutationPolicy = EXPLORE_MUTATION_POLICY,
    step_sink: Callable[[dict[str, object]], None] | None = None,
    sentinel_set: GeneratedSentinelSet | None = None,
    observer_integrity_continue: bool = False,
    stall_recovery: StallRecovery | None = None,
    requested_spec: str | None = None,
    live_dir: Path | None = None,
    engine_commit: str | None = None,
    stream: bool = True,
) -> dict[str, object]:
    """Run the state-aware effect loop on an arbitrary caller-prepared node-tar image.

    This is active exploration, NOT a qualification and NOT a historical demo: there is no
    version allow/deny list and no catalog check -- the host side prepared and verified the
    image (``inodefence-node-tar-registry:*``), and ``tar_version`` is the version it resolved
    (``requested_spec`` keeps the raw request such as "latest"). The report is labelled
    "exploratory demo run" and carries ``mode="exploration"`` and ``qualification=False`` so no
    consumer mistakes it for a qualified or historical result.

    Everything the loop does is the historical path, unchanged: the same ``run_effect_campaign``,
    the same per-case producer (``_native_effect_producer``), the same disposable sandbox,
    sentinels and strict container isolation (the controller's, applied by ``backend``), and the
    same mutator, scheduler, feedback, oracle and observer. The ONLY differences from
    ``historical_demo_report`` are the two absent allowlist gates and the exploration labelling.
    Seeds are RNG integers only; no PoC input is accepted.
    """
    sentinels = sentinel_set.specs if sentinel_set is not None else (SentinelSpec(),)
    config = EffectCampaignConfig(
        random_seed=seed,
        execution_budget=budget,
        search_policy=policy,
        mutation_policy=mutation_policy,
    )
    target = NodeTarEffectTarget.bind(backend, image_id, profile=NativeEffectProfile.FULL)
    vocab_mode = next(
        (
            mode.value
            for mode, mp in _rds.VOCABULARY_MUTATION_POLICY.items()
            if mp == mutation_policy
        ),
        None,
    )
    recorder: LiveRecorder | None = None
    if live_dir is not None:
        described = sentinel_set.describe() if sentinel_set is not None else {}
        recorder = LiveRecorder(
            live_dir,
            LiveRunMeta(
                target="node-tar",
                version=target.tar_version,
                seed=seed,
                budget=budget,
                image_id=image_id,
                search_policy=policy.value,
                vocab_mode=vocab_mode,
                engine_commit=engine_commit,
                replay_template=REPLAY_COMMAND_TEMPLATE,
                # The conditions a single case depends on, so a saved violation can be replayed
                # exactly (the same keys node-tar's replay accepts, with the values actually used).
                run_settings={
                    "sentinel_count": described.get("count"),
                    "sentinel_seed": described.get("generator_seed"),
                    "observer_integrity_policy": (
                        "invalid-continue" if observer_integrity_continue else "stop"
                    ),
                    "profile": "full",
                },
            ),
        )
    checks: list[dict[str, object]] = []
    timing: list[dict[str, object]] = []
    # Streaming (the explore default) keeps memory O(1) in the run count: the producer drops the
    # per-case check/timing (it uses ``run_counter`` for the index instead of ``len(checks)``), the
    # loop retains no steps, and the report below carries only aggregate counts plus the violating
    # cases. Streaming off reproduces the small-budget shape (every case listed) for a short run.
    run_counter = [0]
    base_produce = _native_effect_producer(
        target,
        sentinels,
        stall_recovery,
        checks=checks,
        timing=timing,
        observer_integrity_continue=observer_integrity_continue,
        run_counter=run_counter if stream else None,
    )
    # Keep the input of every case the oracle flags as a violation so a maintainer can reproduce it
    # off-repo; only violating cases are saved (a large budget makes keeping every case's TAR
    # wasteful). ``case_records`` lists every case only when streaming is off; when on, only the
    # aggregate counters and the violating cases are kept. The loop/feedback/oracle are unchanged.
    case_records: list[dict[str, object]] = []
    violation_cases: list[dict[str, object]] = []
    violation_inputs: list[dict[str, object]] = []
    terminations: Counter[str] = Counter()
    unjudged_steps = 0

    def produce(case: ArchiveCase) -> EffectRunResult:
        nonlocal unjudged_steps
        run_index = run_counter[0] if stream else len(checks)
        result = base_produce(case)
        base = result.base_result
        # Two independent axes (inodefence-target-result contract). Judgment: the oracle ran on the
        # before/after snapshots whatever the extractor's exit was, so every case here is "judged"
        # and keeps its C0/C1/C2 (RUN_ERROR -- oracle not evaluated -- is the abort path, recorded
        # separately). Termination: how the extractor exited, its own column. observation_complete:
        # whether the trace behind the verdicts was whole (integrity_valid already subsumes
        # completeness, no observation failures and flush). The converter derives needs_repro_check.
        hit = {v.contract_id.value: v.violated for v in base.violations}
        record = {
            "run_index": run_index,
            "outcome": JUDGED,
            "c0": hit.get("C0"),
            "c1": hit.get("C1"),
            "c2": hit.get("C2"),
            "termination": base.execution.status.value,
            "observation_complete": bool(result.trace.integrity_valid),
        }
        # Aggregates kept in O(1) whether or not every case is listed below.
        terminations[str(record["termination"])] += 1
        if (record["c0"], record["c1"], record["c2"]) == (None, None, None):
            unjudged_steps += 1
        is_violation = bool(record["c0"] or record["c1"] or record["c2"])
        if stream:
            if is_violation:
                violation_cases.append(record)  # streaming lists only the violating cases
        else:
            case_records.append(record)  # streaming off: every case, like the small-budget shape
        if is_violation:
            tar = build_tar(case)
            # termination and observation_complete live on the case record; the converter's
            # CaseVerdict.needs_repro_check flags a violation from a non-clean or incomplete run.
            violation_inputs.append(
                {
                    "run_index": run_index,
                    "tar_sha256": sha256(tar).hexdigest(),
                    "tar_b64": base64.b64encode(tar).decode("ascii"),
                }
            )
        return result

    reporter = EffectStepReporter()

    def record_step(step) -> None:
        record = reporter.add(step)
        if step_sink is not None:
            step_sink(record)
        if recorder is not None:
            # Live progress + immediate violation capture; the C0/C1/C2 are the producer's own,
            # so the live case.json never disagrees with the final result.json.
            recorder.on_step(live_step_from_effect(step))

    started = perf_counter()
    try:
        # Streaming retains no steps, so memory stays O(1) in the run count; the report is then
        # built from the aggregate counters, not from ``result.steps``. Streaming off keeps today's
        # full per-step result for a short run.
        if stream:
            result = run_effect_campaign(
                minimal_seed_corpus(),
                produce,
                config,
                hooks=CampaignHooks(on_step=record_step, retain_steps=False),
            )
        else:
            result = run_effect_campaign(
                minimal_seed_corpus(), produce, config, on_step=record_step
            )
    except KeyboardInterrupt as error:
        if recorder is not None:
            recorder.close(state="stopped", stop_reason=repr(error))
        raise
    except BaseException as error:
        if recorder is not None:
            recorder.close(state="failed", stop_reason=repr(error))
        raise
    else:
        if recorder is not None:
            recorder.close(state="finished")
    total = perf_counter() - started
    if stream:
        # retain_steps=False returns the lightweight result (aggregate counts, no steps).
        light = cast(LightCampaignResult, result)
        # Aggregate + violating cases only (the result's main off-report home for a large run's
        # violation inputs is the live folder; ``violation_inputs`` here still carries the TARs).
        report = {
            "demo_report_schema": DEMO_REPORT_SCHEMA,
            "producer": "native",
            "retained_case_ids": list(light.retained_case_ids),
            "aggregate": {
                "runs_executed": light.executed,
                "terminations": dict(terminations),
                "unjudged_steps": unjudged_steps,
                "errors": 0,  # run_error is the abort path (NativeDemoAborted), not a case here
            },
            "violation_cases": violation_cases,
        }
    else:
        full = cast(EffectCampaignResult, result)  # on_step path keeps the full result
        report = effect_campaign_report(full, "native")
        report.update(
            native_checks=checks,
            oracle_detected_events=_historical_oracle_events(full),
            case_records=case_records,
        )
    report.update(
        label=EXPLORATION_LABEL,
        mode="exploration",
        qualification=False,
        streaming=stream,
        observer_integrity_policy="invalid-continue" if observer_integrity_continue else "stop",
        vocabulary_mode=vocab_mode,
        node_tar_version=target.tar_version,
        requested_tar_version=tar_version,
        requested_spec=tar_version if requested_spec is None else requested_spec,
        node_version=target.node_version,
        image_id=image_id,
        timing={"total_seconds": total, "per_case": timing},
        violation_inputs=violation_inputs,
    )
    apply_sentinel_set_record(report, sentinel_set)
    apply_infra_reexecutions(report, stall_recovery)
    return report


def historical_target_versions() -> dict[str, str]:
    """Catalog-registered historical node-tar versions mapped to wrapper-lock SHA-256.

    The allowlist is derived only from frozen sources that must agree: the
    benchmark catalog's selected historical pair and the retained wrapper locks
    whose hashes equal the frozen n01 lock identities. This is read-only reuse of
    the existing lock verification and does not modify any frozen input. A version
    or image outside this set cannot enter the historical loop.
    """
    # Read-only import of the frozen identities; n01.py is never modified here.
    from inodefence.evaluation.n01 import FROZEN_TARGETS

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    record = next(
        item for item in catalog["benchmarks"] if item["benchmark_id"] == HISTORICAL_BENCHMARK_ID
    )
    pair = record["selected_pair"]
    catalog_versions = {pair["vulnerable"], pair["fixed"]}
    allowed: dict[str, str] = {}
    for frozen in FROZEN_TARGETS:
        if frozen.tar_version not in catalog_versions:
            raise ValueError("frozen historical target is not in the catalog selected pair")
        lock_path = HISTORICAL_LOCKS_DIR / f"node-tar-{frozen.tar_version}.package-lock.json"
        if sha256(lock_path.read_bytes()).hexdigest() != frozen.lock_sha256:
            raise ValueError(f"wrapper lock for {frozen.tar_version} drifted from frozen identity")
        allowed[frozen.tar_version] = frozen.lock_sha256
    if set(allowed) != catalog_versions:
        raise ValueError("catalog historical pair differs from the frozen targets")
    if HOLDOUT_TARGET is not None:
        version, lock_sha256 = HOLDOUT_TARGET
        if version in allowed:
            raise ValueError(f"holdout version {version} is a frozen train/fixed target")
        lock_path = HISTORICAL_LOCKS_DIR / f"node-tar-{version}.package-lock.json"
        if sha256(lock_path.read_bytes()).hexdigest() != lock_sha256:
            raise ValueError(f"wrapper lock for holdout {version} differs from HOLDOUT_TARGET")
        allowed[version] = lock_sha256
    return allowed


def _require_historical_request(tar_version: str, budget: int, allowed: Mapping[str, str]) -> None:
    """Reject out-of-range budgets and versions outside the catalog pair (pre-bind)."""
    if type(budget) is not int or not 1 <= budget <= MAX_NATIVE_BUDGET:
        raise ValueError(f"historical demo budget must be in 1..{MAX_NATIVE_BUDGET}")
    if tar_version not in allowed:
        raise ValueError(
            f"historical demo version {tar_version!r} is not a catalog-registered "
            f"historical target {sorted(allowed)}"
        )


def _require_historical_image(
    observed_version: str, requested: str, allowed: Mapping[str, str]
) -> None:
    """Reject a bound image whose node-tar is not the requested catalog pair member (post-bind)."""
    if observed_version != requested or observed_version not in allowed:
        raise NativeDemoAborted(
            0,
            None,
            f"image node-tar {observed_version} is not the requested catalog-registered "
            f"historical target {requested}",
        )


def _historical_oracle_events(result: EffectCampaignResult) -> list[dict[str, object]]:
    """Label each oracle contract violation an 'oracle-detected Cx event' (not rediscovery)."""
    events: list[dict[str, object]] = []
    for step in result.steps:
        base = step.result.base_result
        for verdict in base.violations:
            if verdict.violated:
                events.append(
                    {
                        "index": step.index,
                        "case_id": base.case.case_id,
                        "contract_id": verdict.contract_id.value,
                        "label": f"oracle-detected {verdict.contract_id.value} event",
                    }
                )
    return events


def _native_effect_producer(
    target: NodeTarEffectTarget,
    sentinels: tuple[SentinelSpec, ...],
    stall_recovery: StallRecovery | None,
    *,
    checks: list[dict[str, object]],
    timing: list[dict[str, object]],
    observer_integrity_continue: bool,
    run_counter: list[int] | None = None,
) -> Callable[[ArchiveCase], EffectRunResult]:
    """Per-case producer shared by both node-tar effect demos (historical and exploration).

    Runs the case, checks evidence integrity, and returns the result or raises
    ``NativeDemoAborted``. This is the producer native_demo_report uses (historical_demo_report
    keeps an equivalent inline copy); the loop, feedback, oracle and observer are unchanged.

    ``run_counter`` is the streaming escape hatch: when ``None`` (the demo/historical default) the
    case index is ``len(checks)`` and each case's native check and timing are appended to the
    caller's ``checks``/``timing`` lists -- byte-identical to before. When a one-element counter is
    passed (exploration streaming), the index comes from it instead and the per-case check/timing
    are NOT retained, so memory does not grow with the run count; the integrity decision below still
    uses the check locally."""

    def produce(case: ArchiveCase) -> EffectRunResult:
        index = run_counter[0] if run_counter is not None else len(checks)
        started = perf_counter()
        try:
            run = _run_native_case(case, target, sentinels, stall_recovery, index)
        except Exception as error:
            reason = f"{type(error).__module__}.{type(error).__qualname__}: {error}"
            raise NativeDemoAborted(
                index,
                case.case_id,
                reason,
                error_chain=exception_chain(error),
                case_shape=case_shape(case),
            ) from error
        check = _native_check(case, run.result, run.controller_flush_verified, run.transport_error)
        if run_counter is None:
            checks.append(check)
            timing.append(
                {
                    "case_id": case.case_id,
                    "wall_seconds": perf_counter() - started,
                    "target_seconds": run.result.base_result.execution.duration_seconds,
                }
            )
        else:
            run_counter[0] += 1
        if run.result.base_result.execution.status == ExecutionStatus.SUCCESS and not (
            check["integrity_valid"]
            and run.result.trace.completeness == EffectStreamCompleteness.COMPLETE
            and run.controller_flush_verified
            and run.transport_error is None
            and check["archive_entries_match"]
        ):
            # Only a pure observer-integrity failure is eligible for the
            # continue policy: the trace itself is not integrity_valid while the
            # host/transport trust signals are all good. Flush/transport/
            # archive-identity failures are infrastructure trust failures the
            # runtime lane classifies, so they keep aborting regardless of policy
            # and are never recorded as observer_integrity or fed back.
            observer_integrity_only = (
                not check["integrity_valid"]
                and run.controller_flush_verified
                and run.transport_error is None
                and check["archive_entries_match"]
            )
            if not (observer_integrity_continue and observer_integrity_only):
                execution = run.result.base_result.execution
                raise NativeDemoAborted(
                    index,
                    case.case_id,
                    f"evidence integrity failed after target success: {check}",
                    {
                        "raw_stream": run.raw_stream.decode("utf-8", "surrogateescape"),
                        "target_stderr": execution.stderr,
                    },
                    case_shape=case_shape(case),
                )
            # Kept as an observer-integrity invalid step; the trace is not
            # integrity_valid, so feedback and corpus admission already exclude it.
        return run.result

    return produce


def historical_demo_report(
    backend: ExecutionBackend,
    image_id: str,
    tar_version: str,
    *,
    seed: int = 123,
    budget: int = DEFAULT_NATIVE_BUDGET,
    policy: EffectSearchPolicy = HISTORICAL_SEARCH_POLICY,
    mutation_policy: MutationPolicy = HISTORICAL_MUTATION_POLICY,
    step_sink: Callable[[dict[str, object]], None] | None = None,
    sentinel_set: GeneratedSentinelSet | None = None,
    observer_integrity_continue: bool = False,
    stall_recovery: StallRecovery | None = None,
) -> dict[str, object]:
    """Run the state-aware effect loop on a frozen historical node-tar; label it a demo run.

    Parallel to native_demo_report but scoped to the catalog-registered historical
    pair (7.5.2/7.5.3) instead of the repository benign pin, which is left
    unchanged. Defaults are the P2 adaptive arm and the escape-hardlink mutation
    policy. Must run inside the controller: `backend` creates disposable target
    containers over sandboxes with sentinels. Mutated cases may carry escaping
    link targets. Seeds are RNG integers only; no PoC input is accepted. The
    result is labeled "demo run" with oracle hits labeled "oracle-detected Cx
    event"; it is never labeled rediscovery or vulnerability.

    `observer_integrity_continue` selects the same observer-integrity STOP policy
    as native_demo_report (default False = the frozen abort). The powered matched
    campaigns run on this path, so the step-level policy is wired here too: a
    successful target run with an untrustworthy trace is kept as an
    observer-integrity invalid step and the loop continues.

    `stall_recovery` has the same meaning as in native_demo_report.
    """
    allowed = historical_target_versions()
    _require_historical_request(tar_version, budget, allowed)
    sentinels = sentinel_set.specs if sentinel_set is not None else (SentinelSpec(),)
    config = EffectCampaignConfig(
        random_seed=seed,
        execution_budget=budget,
        search_policy=policy,
        mutation_policy=mutation_policy,
    )
    target = NodeTarEffectTarget.bind(backend, image_id, profile=NativeEffectProfile.FULL)
    _require_historical_image(target.tar_version, tar_version, allowed)
    checks: list[dict[str, object]] = []
    timing: list[dict[str, object]] = []

    def produce(case: ArchiveCase) -> EffectRunResult:
        index = len(checks)
        started = perf_counter()
        try:
            run = _run_native_case(case, target, sentinels, stall_recovery, index)
        except Exception as error:
            reason = f"{type(error).__module__}.{type(error).__qualname__}: {error}"
            raise NativeDemoAborted(
                index,
                case.case_id,
                reason,
                error_chain=exception_chain(error),
                case_shape=case_shape(case),
            ) from error
        check = _native_check(case, run.result, run.controller_flush_verified, run.transport_error)
        checks.append(check)
        timing.append(
            {
                "case_id": case.case_id,
                "wall_seconds": perf_counter() - started,
                "target_seconds": run.result.base_result.execution.duration_seconds,
            }
        )
        if run.result.base_result.execution.status == ExecutionStatus.SUCCESS and not (
            check["integrity_valid"]
            and run.result.trace.completeness == EffectStreamCompleteness.COMPLETE
            and run.controller_flush_verified
            and run.transport_error is None
            and check["archive_entries_match"]
        ):
            # Only a pure observer-integrity failure is eligible for the
            # continue policy: the trace itself is not integrity_valid while the
            # host/transport trust signals are all good. Flush/transport/
            # archive-identity failures are infrastructure trust failures the
            # runtime lane classifies, so they keep aborting regardless of policy
            # and are never recorded as observer_integrity or fed back.
            observer_integrity_only = (
                not check["integrity_valid"]
                and run.controller_flush_verified
                and run.transport_error is None
                and check["archive_entries_match"]
            )
            if not (observer_integrity_continue and observer_integrity_only):
                execution = run.result.base_result.execution
                raise NativeDemoAborted(
                    index,
                    case.case_id,
                    f"evidence integrity failed after target success: {check}",
                    {
                        "raw_stream": run.raw_stream.decode("utf-8", "surrogateescape"),
                        "target_stderr": execution.stderr,
                    },
                    case_shape=case_shape(case),
                )
            # Kept as an observer-integrity invalid step; the trace is not
            # integrity_valid, so feedback and corpus admission already exclude it.
        return run.result

    reporter = EffectStepReporter()

    def record_step(step) -> None:
        # Persist each finished step so an abort mid-campaign still leaves the completed
        # loop record (including any oracle event); large-budget runs abort more often.
        record = reporter.add(step)
        if step_sink is not None:
            step_sink(record)

    started = perf_counter()
    result = run_effect_campaign(minimal_seed_corpus(), produce, config, on_step=record_step)
    total = perf_counter() - started
    report = effect_campaign_report(result, "native")
    report.update(
        label=HISTORICAL_LABEL,
        mode="historical",
        node_tar_version=target.tar_version,
        requested_tar_version=tar_version,
        node_version=target.node_version,
        image_id=image_id,
        native_checks=checks,
        oracle_detected_events=_historical_oracle_events(result),
        # Wall-clock values differ per run; keep them apart from the loop record.
        timing={"total_seconds": total, "per_case": timing},
    )
    apply_sentinel_set_record(report, sentinel_set)
    apply_infra_reexecutions(report, stall_recovery)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", choices=("synthetic", "native"), default="synthetic")
    parser.add_argument(
        "--policy",
        choices=tuple(policy.value for policy in EffectSearchPolicy),
        default=EffectSearchPolicy.P2_EFFECT_ADAPTIVE.value,
    )
    parser.add_argument(
        "--mutation-policy",
        choices=tuple(policy.value for policy in MutationPolicy),
        default=MutationPolicy.M1.value,
    )
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args(argv)
    if args.producer == "native":
        print(NATIVE_UNAVAILABLE, file=sys.stderr)
        return 2
    text = synthetic_demo_json(
        args.seed,
        args.budget,
        EffectSearchPolicy(args.policy),
        MutationPolicy(args.mutation_policy),
    )
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="ascii")
        print(f"effect demo report [{SYNTHETIC_LABEL}]: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
