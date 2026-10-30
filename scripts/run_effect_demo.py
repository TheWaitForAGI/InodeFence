"""P0-5 effect loop demo: seed -> producer -> oracle -> feedback -> next mutation.

The CLI runs only the synthetic producer; its results are fixtures, not node-tar
evidence. `native_demo_report` runs inside the trusted Linux controller
(container_host effect-demo, `make demo`) against the real node-tar image.
"""

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from inodefence.effect_campaign import (
    EffectCampaignConfig,
    EffectCampaignResult,
    run_effect_campaign,
)
from inodefence.effect_demo import (
    EffectStepReporter,
    effect_campaign_report,
    render_effect_campaign_report,
)
from inodefence.effect_pipeline import run_node_tar_effect_case
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.execution.base import ExecutionBackend
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ArchiveCase,
    EffectRunResult,
    EffectStreamCompleteness,
    ExecutionStatus,
)
from inodefence.mutator import MutationPolicy
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
HISTORICAL_DEMO_MODE = "effect-demo-historical"
# M4 self-discovery: the effect campaign over a second extractor (decompress). Shares the
# --seed/--budget/--mutation-policy demo arguments. --policy (EffectSearchPolicy) now selects the
# decompress search arm on the same gradient-rung ladder node-tar uses: P3_EXTERNAL_RESOLVE (C,
# identity-state) admits both the boundary-attempt and external-resolve rungs, P3_BOUNDARY_ATTEMPT
# (D, coverage) admits only the boundary-attempt rung, and the P1 floor (A) admits neither. When
# --policy is absent the loop's default admits both rungs, unchanged from before the arm split.
DECOMPRESS_CAMPAIGN_MODE = "decompress-effect-campaign"
DEMO_MODES = ("effect-demo", HISTORICAL_DEMO_MODE, DECOMPRESS_CAMPAIGN_MODE)
HISTORICAL_LABEL = "demo run"
HISTORICAL_SEARCH_POLICY = EffectSearchPolicy.P2_EFFECT_ADAPTIVE
HISTORICAL_MUTATION_POLICY = MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK


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
    ) -> None:
        super().__init__(f"step {step_index} case {case_id}: {reason}")
        self.step_index = step_index
        self.case_id = case_id
        self.reason = reason
        # Raw target output of the aborted case, kept as observed (not reinterpreted).
        self.observed = observed


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
# Arguments the host broker forwards verbatim to the controller. tar_version is
# historical-only; the other four are shared by both effect demos.
DEMO_FORWARDED_ARGUMENTS = (*DEMO_ARGUMENTS, "tar_version")


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


def check_demo_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    given = [name for name in DEMO_ARGUMENTS if getattr(args, name) is not None]
    if given and args.mode not in DEMO_MODES:
        parser.error("--seed/--budget/--policy/--mutation-policy are restricted to effect demos")
    if args.budget is not None and not 1 <= args.budget <= MAX_NATIVE_BUDGET:
        parser.error(f"effect demo budget must be in 1..{MAX_NATIVE_BUDGET}")
    tar_version = getattr(args, "tar_version", None)
    if tar_version is not None and args.mode != HISTORICAL_DEMO_MODE:
        parser.error("--tar-version is restricted to effect-demo-historical")
    if args.mode == HISTORICAL_DEMO_MODE and tar_version is None:
        parser.error("effect-demo-historical requires --tar-version")


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
    return options


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


def native_demo_report(
    backend: ExecutionBackend,
    image_id: str,
    *,
    seed: int = 123,
    budget: int = DEFAULT_NATIVE_BUDGET,
    policy: EffectSearchPolicy = EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
    mutation_policy: MutationPolicy = MutationPolicy.M1,
    step_sink: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Run the effect loop on real node-tar (FULL profile); label the result a demo run.

    Must run inside the controller: `backend` creates disposable target containers
    over sandboxes with sentinels. Mutated cases may carry `../` or `/` paths.
    `step_sink` gets each finished step's report record (identical to `steps[i]`
    of the returned report) before the next case runs, so a NativeDemoAborted
    later still leaves the completed loop record with the caller.
    """
    if type(budget) is not int or not 1 <= budget <= MAX_NATIVE_BUDGET:
        raise ValueError(f"native demo budget must be in 1..{MAX_NATIVE_BUDGET}")
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

    def produce(case: ArchiveCase) -> EffectRunResult:
        index = len(checks)
        started = perf_counter()
        try:
            run = run_node_tar_effect_case(case, target)
        except Exception as error:
            reason = f"{type(error).__module__}.{type(error).__qualname__}: {error}"
            raise NativeDemoAborted(index, case.case_id, reason) from error
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
            execution = run.result.base_result.execution
            raise NativeDemoAborted(
                index,
                case.case_id,
                f"evidence integrity failed after target success: {check}",
                {
                    "raw_stream": run.raw_stream.decode("utf-8", "surrogateescape"),
                    "target_stderr": execution.stderr,
                },
            )
        return run.result

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
    """
    allowed = historical_target_versions()
    _require_historical_request(tar_version, budget, allowed)
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
            run = run_node_tar_effect_case(case, target)
        except Exception as error:
            reason = f"{type(error).__module__}.{type(error).__qualname__}: {error}"
            raise NativeDemoAborted(index, case.case_id, reason) from error
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
            execution = run.result.base_result.execution
            raise NativeDemoAborted(
                index,
                case.case_id,
                f"evidence integrity failed after target success: {check}",
                {
                    "raw_stream": run.raw_stream.decode("utf-8", "surrogateescape"),
                    "target_stderr": execution.stderr,
                },
            )
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
