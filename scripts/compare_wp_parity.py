"""Judge worker-pool vs per-case parity from two emitted demo reports (host-side, no Docker).

Both runs are ``effect-demo-historical --emit-parity`` with the same seed, arm and budget;
the candidate adds ``--worker-pool`` (the ResettingProducer path). Each report carries a
serialized ``parity_subject`` (extracted inside the controller from the typed campaign
result). This reads both back, compares them with the parity comparator across the four
G1 dimensions, confirms the worker-pool run needed zero infrastructure retries, and reads
the two wall-clocks side by side (EXP-0 measurement 4).

Usage:

    PYTHONPATH=src python3.12 -m scripts.compare_wp_parity \
        --baseline <per-case>.json --candidate <worker-pool>.json \
        --output ~/inodefence-evidence/wp-parity-20261104/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inodefence.evaluation.execution_parity import compare_subjects, parity_subject_from_dict
from inodefence.evaluation.throughput import (
    CampaignTiming,
    MethodMeasurement,
    build_comparison,
    render_report,
)


def _subject(report: dict, which: str):
    subject = report.get("parity_subject")
    if subject is None:
        raise SystemExit(f"{which} report has no parity_subject; rerun with --emit-parity")
    return parity_subject_from_dict(subject)


def _timing(report: dict, run_id: str, retries: int) -> CampaignTiming:
    timing = report.get("timing") or {}
    wall = float(timing.get("total_seconds", 0.0))
    steps = report.get("steps") or []
    return CampaignTiming(
        run_id=run_id,
        seed=int((report.get("config") or {}).get("random_seed", 0)),
        arm=str(report.get("requested_tar_version", "")),
        version=report.get("node_tar_version"),
        wall_seconds=wall,
        cases=len(steps),
        aborts=len(report.get("invalid_cases") or []),
        retries=retries,
    )


def compare_reports(baseline: dict, candidate: dict, run_id: str = "cell") -> dict[str, object]:
    """Compare two emitted demo reports; return the full parity + throughput result."""
    base_subject = _subject(baseline, "baseline")
    cand_subject = _subject(candidate, "candidate")
    report = compare_subjects(base_subject, cand_subject)

    retries = candidate.get("worker_pool_retries") or {"total": 0, "by_step": []}
    retries_total = int(retries.get("total", 0))

    per_case = MethodMeasurement(
        "per-case-container",
        0.0,
        _timing(baseline, run_id, 0).wall_seconds,
        (_timing(baseline, run_id, 0),),
    )
    worker_pool = MethodMeasurement(
        "worker-pool",
        0.0,
        _timing(candidate, run_id, retries_total).wall_seconds,
        (_timing(candidate, run_id, retries_total),),
    )
    throughput = render_report(
        build_comparison(per_case, worker_pool, {run_id: base_subject}, {run_id: cand_subject})
    )

    four_dim_pass = report.core_parity
    retries_zero = retries_total == 0 and not (candidate.get("invalid_cases") or [])
    return {
        "schema": "wp-parity-result-v1",
        "run_id": run_id,
        "parity": {
            "passed": report.passed,
            "core_parity_4dim": four_dim_pass,
            "both_retry_free": report.both_retry_free,
            "dimensions": [
                {"name": d.name, "agree": d.agree, "detail": list(d.detail)}
                for d in report.dimensions
            ],
            "retried_steps": [
                {
                    "index": v.index,
                    "candidate_retries": v.candidate_retries,
                    "matches_retry_free": v.matches_retry_free,
                }
                for v in report.retried_steps
            ],
        },
        "worker_pool_retries": {"total": retries_total, "by_step": retries.get("by_step", [])},
        "throughput": throughput,
        "verdict": {
            "four_dimension_parity_pass": four_dim_pass,
            "retries_zero": retries_zero,
            "overall_pass": four_dim_pass and retries_zero,
        },
        "scope_note": (
            "dim1 case_sequence, dim2 oracle+feedback, dim3 snapshots (st_dev/st_ino/mtime_ns/"
            "ctime_ns/sandbox_root excluded + inode-sharing partition), dim4 isolation+reset are "
            "all judged from the emitted parity_subject (full typed campaign evidence). "
            "Effect-event raw sequence numbers are async and are not parity_subject fields, so "
            "they do not enter the judgment (EN-008)."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--baseline", type=Path, required=True, help="per-case report .json")
    parser.add_argument("--candidate", type=Path, required=True, help="worker-pool report .json")
    parser.add_argument("--output", type=Path, required=True, help="result directory")
    parser.add_argument("--run-id", default="cell")
    args = parser.parse_args(argv)

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    result = compare_reports(baseline, candidate, args.run_id)

    args.output.mkdir(parents=True, exist_ok=True)
    result_path = args.output / "wp-parity-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verdict = result["verdict"]
    assert isinstance(verdict, dict)
    print(
        f"parity 4-dim: {'PASS' if verdict['four_dimension_parity_pass'] else 'FAIL'}; "
        f"retries zero: {verdict['retries_zero']}; "
        f"overall: {'PASS' if verdict['overall_pass'] else 'FAIL'}; report {result_path}"
    )
    return 0 if verdict["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
