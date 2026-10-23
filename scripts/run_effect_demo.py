"""P0-5 effect loop demo: seed -> producer -> oracle -> feedback -> next mutation.

The CLI runs only the synthetic producer; its results are fixtures, not node-tar
evidence. `native_demo_report` runs inside the trusted Linux controller
(container_host effect-demo, `make demo-native`) against the real node-tar image.
"""

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_demo import effect_campaign_report, render_effect_campaign_report
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

NATIVE_UNAVAILABLE = (
    "native producer is not runnable from this entrypoint: "
    "실제 실행은 controller 안에서 container_host effect-demo 모드로 (make demo-native)"
)
DEFAULT_NATIVE_BUDGET = 20
MAX_NATIVE_BUDGET = 100
NODE_TAR_PIN = Path(__file__).resolve().parents[1] / "tools" / "node-tar" / "package.json"


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


def synthetic_demo_json(
    seed: int,
    budget: int,
    policy: EffectSearchPolicy,
    mutation_policy: MutationPolicy,
) -> str:
    config = EffectCampaignConfig(
        random_seed=seed,
        execution_budget=budget,
        search_policy=policy,
        mutation_policy=mutation_policy,
    )
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    return render_effect_campaign_report(effect_campaign_report(result, "synthetic"))


DEMO_ARGUMENTS = ("seed", "budget", "policy", "mutation_policy")


def add_demo_arguments(parser: argparse.ArgumentParser) -> None:
    """effect-demo only; defaults apply inside native_demo_report (P2, 123, 20, M1)."""
    parser.add_argument("--seed", type=int)
    parser.add_argument("--budget", type=int)
    parser.add_argument("--policy", choices=tuple(policy.value for policy in EffectSearchPolicy))
    parser.add_argument(
        "--mutation-policy", choices=tuple(policy.value for policy in MutationPolicy)
    )


def check_demo_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    given = [name for name in DEMO_ARGUMENTS if getattr(args, name) is not None]
    if given and args.mode != "effect-demo":
        parser.error("--seed/--budget/--policy/--mutation-policy are restricted to effect-demo")
    if args.budget is not None and not 1 <= args.budget <= MAX_NATIVE_BUDGET:
        parser.error(f"effect-demo budget must be in 1..{MAX_NATIVE_BUDGET}")


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
) -> dict[str, object]:
    """Run the effect loop on real node-tar (FULL profile); label the result a demo run.

    Must run inside the controller: `backend` creates disposable target containers
    over sandboxes with sentinels. Mutated cases may carry `../` or `/` paths.
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

    started = perf_counter()
    result = run_effect_campaign(minimal_seed_corpus(), produce, config)
    total = perf_counter() - started
    report = effect_campaign_report(result, "native")
    report.update(
        label="demo run",
        node_tar_version=target.tar_version,
        node_version=target.node_version,
        image_id=image_id,
        native_checks=checks,
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
        print(f"effect demo report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
