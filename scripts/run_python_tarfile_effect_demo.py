"""Host-side controller for the in-process python-tarfile effect demo (no docker).

The EXP-3 launcher (``scripts/run_exp0.py``) runs this script for cells whose target
extractor is ``python-tarfile``, with the same ``DEMO_*`` cell environment it gives the
node-tar smoke script, and reads back the same files:

    <INODEFENCE_EVIDENCE_DIR>/inodefence-effect-demo-python-tarfile-<RUN_ID>.json
    <INODEFENCE_EVIDENCE_DIR>/inodefence-effect-demo-python-tarfile-<RUN_ID>.steps.jsonl

Environment (flags override): RUN_ID (required), INODEFENCE_EVIDENCE_DIR, DEMO_SEED,
DEMO_BUDGET, DEMO_POLICY, DEMO_MUTATION_POLICY, DEMO_SENTINEL_SEED, DEMO_SENTINEL_COUNT,
DEMO_OBSERVER_INTEGRITY_POLICY (recorded only). Each finished step is appended to the
steps file and fsynced before the next case, so an abort keeps the completed loop
record; an abort writes a report with an ``aborted`` record and exits 1. The report
carries the top-level ``lock_digest`` the registration gate compares. Only the
``data`` filter is used (the producer refuses ``fully_trusted`` for fuzzed input).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_effect_demo import (  # noqa: E402
    DEFAULT_NATIVE_BUDGET,
    HISTORICAL_LABEL,
    HISTORICAL_MUTATION_POLICY,
    HISTORICAL_SEARCH_POLICY,
    PYTHON_TARFILE_EXECUTION_MODE,
    PYTHON_TARFILE_MODE,
    python_tarfile_demo_report,
)

from inodefence.effect_demo import (  # noqa: E402
    render_effect_campaign_report,
    render_effect_campaign_summary,
    render_effect_step_line,
    render_effect_step_summary,
)
from inodefence.feedback import EffectSearchPolicy  # noqa: E402
from inodefence.mutator import MutationPolicy  # noqa: E402

EVIDENCE_STEM = "inodefence-effect-demo-python-tarfile"


def evidence_paths(evidence_dir: Path, run_id: str) -> tuple[Path, Path]:
    report = evidence_dir / f"{EVIDENCE_STEM}-{run_id}.json"
    return report, report.with_name(report.name[: -len(".json")] + ".steps.jsonl")


def _env_int(name: str) -> int | None:
    value = os.environ.get(name)
    return int(value) if value not in (None, "") else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=os.environ.get("RUN_ID"))
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path(os.environ.get("INODEFENCE_EVIDENCE_DIR", "~/inodefence-evidence")),
    )
    parser.add_argument("--seed", type=int, default=_env_int("DEMO_SEED") or 123)
    parser.add_argument(
        "--budget", type=int, default=_env_int("DEMO_BUDGET") or DEFAULT_NATIVE_BUDGET
    )
    parser.add_argument(
        "--policy",
        choices=tuple(p.value for p in EffectSearchPolicy),
        default=os.environ.get("DEMO_POLICY") or HISTORICAL_SEARCH_POLICY.value,
    )
    parser.add_argument(
        "--mutation-policy",
        choices=tuple(p.value for p in MutationPolicy),
        default=os.environ.get("DEMO_MUTATION_POLICY") or HISTORICAL_MUTATION_POLICY.value,
    )
    parser.add_argument("--sentinel-seed", type=int, default=_env_int("DEMO_SENTINEL_SEED"))
    parser.add_argument("--sentinel-count", type=int, default=_env_int("DEMO_SENTINEL_COUNT"))
    parser.add_argument(
        "--observer-integrity-policy",
        default=os.environ.get("DEMO_OBSERVER_INTEGRITY_POLICY") or None,
        help="recorded only (no transport frame in-process)",
    )
    args = parser.parse_args(argv)
    if not args.run_id:
        parser.error("RUN_ID (or --run-id) is required")
    evidence_dir = args.evidence_dir.expanduser()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_path, steps_path = evidence_paths(evidence_dir, args.run_id)
    print(
        f"effect-demo-python-tarfile: run_id={args.run_id} seed={args.seed} budget={args.budget} "
        f"policy={args.policy} mutation_policy={args.mutation_policy} "
        f"execution_mode={PYTHON_TARFILE_EXECUTION_MODE}",
        file=sys.stderr,
        flush=True,
    )
    with steps_path.open("x", encoding="ascii") as steps_stream:

        def persist_step(record: dict[str, object]) -> None:
            steps_stream.write(render_effect_step_line(record))
            steps_stream.flush()
            os.fsync(steps_stream.fileno())
            print(render_effect_step_summary(record, args.budget), file=sys.stderr, flush=True)

        try:
            report = python_tarfile_demo_report(
                seed=args.seed,
                budget=args.budget,
                policy=EffectSearchPolicy(args.policy),
                mutation_policy=MutationPolicy(args.mutation_policy),
                step_sink=persist_step,
                sentinel_count=args.sentinel_count,
                sentinel_seed=args.sentinel_seed,
                observer_integrity_policy=args.observer_integrity_policy,
            )
            print(render_effect_campaign_summary(report), file=sys.stderr)
            returncode = 0
        except Exception as error:  # noqa: BLE001 - any failure is an abort record
            report = {
                "label": HISTORICAL_LABEL,
                "producer": "native",
                "mode": PYTHON_TARFILE_MODE,
                "extractor": PYTHON_TARFILE_MODE,
                "execution_mode": PYTHON_TARFILE_EXECUTION_MODE,
                "aborted": {
                    "step_index": sum(1 for _ in open(steps_path, encoding="ascii")),
                    "case_id": None,
                    "reason": f"{type(error).__name__}: {error}",
                    "observed": None,
                },
            }
            print(f"effect-demo-python-tarfile aborted: {error}", file=sys.stderr)
            returncode = 1
    with report_path.open("x", encoding="ascii") as stream:
        stream.write(render_effect_campaign_report(report))
    print(f"effect demo report: {report_path}", file=sys.stderr)
    print(f"effect demo completed steps: {steps_path}", file=sys.stderr)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
