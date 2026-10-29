"""Engineering reference run of the single-path A/B/C/D comparison.

NOT a formal experiment, NOT node-tar, NOT an H1 effectiveness result. It runs the
merged final-state A/B/C/D arms (``arm_comparison.run_abcd_comparison``) through
the one ``run_search_campaign`` path against the SAFE Python ``tarfile`` ``data``
reference adapter (PEP 706), in the disposable sandbox, with no container or
host-docker. The ``data`` filter sanitizes boundary escapes, so a first contract
violation is **right-censored by construction** here — that is a property of the
safe reference filter, NOT a safety claim about any extractor and NOT evidence of
absence. The run validates the single-path harness end to end and reports honest
per-arm process/diversity metrics with the metrics fixed before the run.

Why the safe adapter and not a ``fully_trusted`` one: an uncontained
``fully_trusted`` extraction of a FUZZED archive could write outside the disposable
sandbox, which the isolation contract forbids. Observing C1/C2 on fuzzed inputs
therefore needs the containerized node-tar target (host docker); that affected-mode
node-tar single-path run is the H1-relevant variant and is a separate task.

Run in the Linux Dev Container:
  python -m scripts.run_abcd_comparison --output ~/inodefence-evidence/abcd-reference-<ts>
Output must not already exist.
"""

import argparse
import json
import platform
import subprocess
import time
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path

from scripts.generate_tar_fixtures import CASE_NAMES, baseline_case

from inodefence.evaluation.arm_comparison import (
    DEFAULT_ARMS,
    Arm,
    ArmComparison,
    ArmSpec,
    CampaignMetrics,
    comparison_markdown,
    run_abcd_comparison,
)
from inodefence.runtime import runtime_root
from inodefence.targets import PythonTarfileTarget


def _spec_dict(spec: ArmSpec) -> dict:
    return {
        "search_policy": spec.search_policy.value,
        "mutation_policy": spec.mutation_policy.value,
        "feedback_projection": spec.feedback_projection.value,
        "description": spec.description,
    }


def _metrics_dict(metrics: CampaignMetrics) -> dict:
    return {
        "search_policy": metrics.search_policy.value,
        "mutation_policy": metrics.mutation_policy.value,
        "feedback_projection": metrics.feedback_projection.value,
        "total_executions": metrics.total_executions,
        "execution_budget": metrics.execution_budget,
        "status_counts": metrics.status_counts,
        "process_success_rate": metrics.process_success_rate,
        "valid_input_rate": metrics.valid_input_rate,
        "executions_to_first_violation": metrics.executions_to_first_violation,
        "first_violation_censored": metrics.first_violation_censored,
        "right_censored_at": metrics.right_censored_at,
        "cumulative_target_seconds_to_first_violation": (
            metrics.cumulative_target_seconds_to_first_violation
        ),
        "unique_state_signatures": metrics.unique_state_signatures,
        "unique_violation_fingerprints": metrics.unique_violation_fingerprints,
        "contract_observed_counts": metrics.contract_observed_counts,
        "any_violation_executions": metrics.any_violation_executions,
        "admission_eligible_count": metrics.admission_eligible_count,
        "admission_eligible_rate": metrics.admission_eligible_rate,
        "retained_after_seed": metrics.retained_after_seed,
        "retained_end": metrics.retained_end,
        "corpus_growth": metrics.corpus_growth,
    }


def _comparison_dict(comparison: ArmComparison) -> dict:
    arms = tuple(comparison.metrics)
    return {
        "random_seed": comparison.random_seed,
        "execution_budget": comparison.execution_budget,
        "initial_case_ids": list(comparison.initial_case_ids),
        "arm_specs": {arm.value: _spec_dict(comparison.arm_specs[arm]) for arm in arms},
        "metrics": {arm.value: _metrics_dict(comparison.metrics[arm]) for arm in arms},
        "measurement": comparison.measurement,
        "comparison_status": comparison.comparison_status,
        "censoring": comparison.censoring,
    }


def run(
    seeds: Sequence[int], budget: int, timeout_seconds: float
) -> tuple[dict, list[ArmComparison]]:
    """Run A/B/C/D over each seed against the safe data reference.

    Captures provenance and verifies disposable-sandbox cleanup, mirroring
    ``reference_campaign_pilot``. Returns the provenance/timing metadata and the
    live per-seed comparisons (engineering run; full raw step retention belongs to
    a formal run, which this explicitly is not).
    """
    root = runtime_root()
    baseline_directories = set(root.iterdir())
    initial = tuple(baseline_case(name) for name in CASE_NAMES)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "src/inodefence"]).returncode:
        raise ValueError("reference run requires unchanged engine code at the recorded revision")

    target = PythonTarfileTarget(timeout_seconds=timeout_seconds)
    provenance = {
        "classification": "engineering-reference-run-only",
        "is_node_tar": False,
        "is_formal_experiment": False,
        "effectiveness_claim": "none",
        "engine_revision": revision,
        "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "target_id": target.provenance.target_id,
        "target_version": target.provenance.target_version,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "runtime_root": str(root),
        "timeout_seconds": timeout_seconds,
        "seeds": list(seeds),
        "execution_budget": budget,
        "initial_case_ids": [case.case_id for case in initial],
        "arm_specs": {arm.value: _spec_dict(DEFAULT_ARMS[arm]) for arm in Arm},
    }

    comparisons: list[ArmComparison] = []
    started = time.perf_counter()
    for seed in seeds:
        comparisons.append(
            run_abcd_comparison(initial, target, random_seed=seed, execution_budget=budget)
        )
    provenance["elapsed_seconds"] = time.perf_counter() - started
    if set(root.iterdir()) != baseline_directories:
        raise ValueError("disposable sandbox cleanup left residue under the runtime root")
    return provenance, comparisons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seeds", default="11,23,37")
    parser.add_argument("--budget", type=int, default=50)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    args = parser.parse_args()
    seeds = tuple(int(token) for token in args.seeds.split(","))

    provenance, comparisons = run(seeds, args.budget, args.timeout_seconds)
    evidence = {
        "provenance": provenance,
        "comparisons": [_comparison_dict(comparison) for comparison in comparisons],
    }
    args.output.mkdir(parents=True, exist_ok=False)
    raw = (json.dumps(evidence, sort_keys=True, indent=2) + "\n").encode("ascii")
    (args.output / "abcd-reference.json").write_bytes(raw)
    (args.output / "abcd-reference.sha256").write_text(sha256(raw).hexdigest() + "\n")

    for comparison in comparisons:
        print(f"## seed {comparison.random_seed}")
        print(comparison_markdown(comparison))
    summary_keys = ("target_id", "engine_revision", "elapsed_seconds")
    print(json.dumps({key: provenance[key] for key in summary_keys}, sort_keys=True))


if __name__ == "__main__":
    main()
