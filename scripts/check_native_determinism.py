"""Native per-case determinism probe (EN-008): do two identical-input runs agree?

G1 worker-pool parity assumes the *per-case path itself is deterministic* -- the
same archive, extractor image, policy and budget must produce the same observed
evidence every run. This wrapper measures that premise. It runs (or is handed)
two demo reports from the same ``seed``/``policy``/``budget`` and decides whether
they agree, reusing lane 4's ``evaluation.execution_parity`` comparator rather
than re-spelling the parity logic.

Two layers, because the demo report does not serialize raw ``StateSnapshot``s:

1. ``compare_report_pair`` (the native deliverable). Builds a ``ParitySubject``
   from each report and reports the two parity dimensions the report fully backs
   -- ``case_sequence`` (per-step case id) and ``oracle_and_feedback`` (C0/C1/C2
   verdict and fed-back keys) -- plus a *full-report equality* check over the
   deterministic loop record (``steps`` and the deterministic summaries). Because
   the report omits per-step filesystem snapshots and isolation provenance, the
   ``snapshots`` and ``isolation_and_reset`` dimensions are not independently
   report-backed; full-report equality subsumes them (identical reports carry
   identical serialized observations), and ``coverage`` says so explicitly. The
   determinism verdict is report equality AND the two report-backed dimensions.

2. ``selftest_inprocess`` (``--dry-run``, no docker). Runs the synthetic campaign
   in process twice for the same seed and feeds the two ``EffectCampaignResult``s
   -- which DO carry real before/after snapshots -- straight through
   ``extract_parity_subject`` + ``compare_subjects``. This exercises all four
   dimensions (including ``snapshots``) on real data and confirms the comparator
   wiring and the generic path's determinism without any container.

The native six-run plan (2 seeds x 2 reruns x budget 100 stop, plus the same two
seeds under invalid-continue x 1 rerun each) is printed by ``--emit-run-plan``;
it is executed only when the docker slot returns (team-gated), never here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.execution_parity import (
    CanonicalSnapshot,
    ParityStep,
    ParitySubject,
    compare_subjects,
    extract_parity_subject,
)
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.mutator import MutationPolicy

# Report-backed parity dimensions: the demo report fully determines these. The
# other two compare_subjects dimensions (snapshots, isolation_and_reset) need
# evidence the report does not serialize, so report pairs defer them to
# full-report equality rather than claim a verdict from absent data.
REPORT_BACKED_DIMENSIONS = ("case_sequence", "oracle_and_feedback")

# A report pair cannot build per-step snapshots, so every step shares this one
# empty canonical snapshot. Identical on both sides, it keeps the snapshots
# dimension from inventing a difference; coverage marks it not report-backed.
_OMITTED_SNAPSHOT = CanonicalSnapshot(
    phase="report_omitted", protected_paths=(), objects=(), identity_groups=()
)

# Top-level report keys that legitimately differ between two runs of the same
# input (wall-clock time only; image id / versions / recipe are identical on one
# host). Everything else in the deterministic loop record must match byte-for-byte.
_NONDETERMINISTIC_KEYS = frozenset({"timing"})

# The deterministic loop record compared for full-report equality.
_DETERMINISTIC_KEYS = (
    "steps",
    "config",
    "initial_case_ids",
    "retained_case_ids",
    "observer_integrity_summary",
    "final_search_stats",
    "demo_report_schema",
    "mutation_policy",
    "producer",
)


def _oracle(step: dict[str, Any]) -> tuple[tuple[str, bool], ...]:
    oracle = step.get("oracle") or {}
    return tuple(sorted((str(cid), bool(violated)) for cid, violated in oracle.items()))


def _feedback_keys(step: dict[str, Any]) -> tuple[str, ...]:
    feedback = step.get("feedback") or {}
    keys = [
        json.dumps(key, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        for key in feedback.get("new_effect_keys", [])
    ]
    keys += [
        json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        for item in feedback.get("new_violation_fingerprints", [])
    ]
    return tuple(keys)


def subject_from_report(report: dict[str, Any], *, label: str) -> ParitySubject:
    """Build a ParitySubject from a demo report's loop record.

    Populates the report-backed fields (case id, oracle verdict, fed-back keys)
    faithfully; per-step snapshots are not in the report, so each step carries the
    shared ``_OMITTED_SNAPSHOT`` placeholder. The demo loop never retries, so every
    step's retry count is zero.
    """
    steps_in = report.get("steps")
    if not isinstance(steps_in, list):
        raise ValueError("report has no steps array")
    steps = tuple(
        ParityStep(
            index=int(step["index"]),
            case_id=str(step["case_id"]),
            oracle=_oracle(step),
            feedback_keys=_feedback_keys(step),
            before=_OMITTED_SNAPSHOT,
            after=_OMITTED_SNAPSHOT,
            retry_count=0,
        )
        for step in steps_in
    )
    return ParitySubject(label=label, steps=steps, isolation=None, resets=())


def _first_step_difference(a: list[dict], b: list[dict]) -> dict[str, Any] | None:
    """The first step index whose record differs, with the differing keys named."""
    if len(a) != len(b):
        return {"kind": "step_count", "baseline": len(a), "candidate": len(b)}
    for index, (left, right) in enumerate(zip(a, b, strict=True)):
        if left != right:
            keys = sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))
            return {"kind": "step_fields", "index": index, "fields": keys}
    return None


def report_equality(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare the deterministic loop record of two reports (timing excluded)."""
    differing = [
        key
        for key in _DETERMINISTIC_KEYS
        if key not in _NONDETERMINISTIC_KEYS and baseline.get(key) != candidate.get(key)
    ]
    step_diff = None
    if "steps" in differing:
        step_diff = _first_step_difference(
            baseline.get("steps") or [], candidate.get("steps") or []
        )
    return {
        "equal": not differing,
        "differing_keys": differing,
        "first_step_difference": step_diff,
    }


def _dimensions_payload(dimensions: tuple) -> list[dict[str, Any]]:
    return [
        {"name": dim.name, "agree": dim.agree, "detail": list(dim.detail)} for dim in dimensions
    ]


def compare_report_pair(
    baseline: dict[str, Any], candidate: dict[str, Any], *, labels: tuple[str, str] = ("a", "b")
) -> dict[str, Any]:
    """Decide per-case determinism from two demo reports of the same input.

    Returns the parity dimensions compare_subjects produced, the subset that is
    report-backed, a full-report equality verdict, and an overall determinism
    PASS/FAIL (report equality AND every report-backed dimension agrees).
    """
    left = subject_from_report(baseline, label=labels[0])
    right = subject_from_report(candidate, label=labels[1])
    report = compare_subjects(left, right)
    equality = report_equality(baseline, candidate)
    backed = {
        dim.name: dim.agree for dim in report.dimensions if dim.name in REPORT_BACKED_DIMENSIONS
    }
    determinism_pass = equality["equal"] and all(backed.values())
    return {
        "mode": "report_pair",
        "labels": {"baseline": labels[0], "candidate": labels[1]},
        "determinism_pass": determinism_pass,
        "report_equality": equality,
        "dimensions": _dimensions_payload(report.dimensions),
        "report_backed_dimensions": sorted(backed),
        "coverage": {
            "case_sequence": "report-backed",
            "oracle_and_feedback": "report-backed",
            "snapshots": "not serialized in demo report; subsumed by report_equality",
            "isolation_and_reset": "not serialized in demo report; subsumed by report_equality",
        },
    }


def _run_synthetic(seed: int, policy: EffectSearchPolicy, mutation: MutationPolicy, budget: int):
    config = EffectCampaignConfig(
        random_seed=seed, execution_budget=budget, search_policy=policy, mutation_policy=mutation
    )
    return run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)


def selftest_inprocess(
    *,
    seed: int,
    policy: EffectSearchPolicy,
    mutation: MutationPolicy,
    budget: int,
) -> dict[str, Any]:
    """Run the synthetic campaign twice in process and compare all four dimensions.

    The synthetic EffectCampaignResult carries real before/after snapshots, so this
    genuinely exercises the ``snapshots`` dimension and confirms the comparator
    wiring on real data -- the one path a report pair cannot cover. No container.
    ``isolation_and_reset`` stays "not provided" (no isolation provenance in the
    synthetic path), which is expected and excluded from the determinism verdict.
    """
    first = extract_parity_subject(_run_synthetic(seed, policy, mutation, budget), label="run-1")
    second = extract_parity_subject(_run_synthetic(seed, policy, mutation, budget), label="run-2")
    report = compare_subjects(first, second)
    observer_dimensions = ("case_sequence", "oracle_and_feedback", "snapshots")
    agree = {dim.name: dim.agree for dim in report.dimensions}
    determinism_pass = all(agree[name] for name in observer_dimensions)
    return {
        "mode": "selftest_inprocess",
        "seed": seed,
        "search_policy": policy.value,
        "mutation_policy": mutation.value,
        "budget": budget,
        "determinism_pass": determinism_pass,
        "observer_dimensions": list(observer_dimensions),
        "dimensions": _dimensions_payload(report.dimensions),
        "note": (
            "isolation_and_reset is 'not provided' for the in-process synthetic path "
            "and is excluded from the determinism verdict (a cross-worker signal, not a "
            "per-case determinism one)"
        ),
    }


def native_run_plan(*, seeds: tuple[int, ...], budget: int) -> dict[str, Any]:
    """The native six-run determinism plan: a rerun pair per (seed, policy) measured.

    stop policy is rerun twice for each of the two seeds (four runs); the
    invalid-continue policy is rerun twice for the first seed only (two runs), so
    every policy/seed cell measured has a genuine two-run determinism pair. Six
    runs, three compare pairs. docker is executed by the caller under the team
    slot, never inside this function.
    """
    if len(seeds) < 2:
        raise ValueError("determinism plan needs at least two seeds")
    runs = []
    for seed in seeds[:2]:
        for rerun in (1, 2):
            runs.append(
                {
                    "run_id": f"s3det-stop-s{seed}-r{rerun}",
                    "seed": seed,
                    "policy": "stop",
                    "budget": budget,
                    "rerun": rerun,
                }
            )
    cont_seed = seeds[0]
    for rerun in (1, 2):
        runs.append(
            {
                "run_id": f"s3det-cont-s{cont_seed}-r{rerun}",
                "seed": cont_seed,
                "policy": "invalid-continue",
                "budget": budget,
                "rerun": rerun,
            }
        )
    compare_pairs = [
        {"baseline": f"s3det-stop-s{seed}-r1", "candidate": f"s3det-stop-s{seed}-r2"}
        for seed in seeds[:2]
    ]
    compare_pairs.append(
        {"baseline": f"s3det-cont-s{cont_seed}-r1", "candidate": f"s3det-cont-s{cont_seed}-r2"}
    )
    return {
        "mode": "run_plan",
        "note": "docker executed by the caller under the team slot, not inside this function",
        "jobs": 2,
        "tar_version": "7.5.2",
        "historical_image": "inodefence-node-tar-effect:7.5.2",
        "evidence_dir": "~/inodefence-evidence/s3-determinism-20261104/",
        "compare_pairs": compare_pairs,
        "runs": runs,
    }


def _load_report(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"report is not a JSON object: {path}")
    return data


def _emit(result: dict[str, Any], out: Path | None) -> None:
    text = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if out is None:
        sys.stdout.write(text)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="ascii")
        print(f"native determinism probe: {out}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-a", type=Path, help="baseline demo report JSON")
    parser.add_argument("--report-b", type=Path, help="candidate demo report JSON")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="in-process synthetic self-test of the comparator (no docker)",
    )
    parser.add_argument(
        "--emit-run-plan", action="store_true", help="print the deferred native six-run plan"
    )
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--budget", type=int, default=20)
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
    parser.add_argument("--seeds", type=int, nargs="+", default=(118, 124))
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args(argv)

    if args.emit_run_plan:
        _emit(native_run_plan(seeds=tuple(args.seeds), budget=args.budget), args.out)
        return 0
    if args.dry_run:
        result = selftest_inprocess(
            seed=args.seed,
            policy=EffectSearchPolicy(args.policy),
            mutation=MutationPolicy(args.mutation_policy),
            budget=args.budget,
        )
        _emit(result, args.out)
        return 0 if result["determinism_pass"] else 1
    if args.report_a is None or args.report_b is None:
        parser.error("report-pair mode requires --report-a and --report-b (or use --dry-run)")
    result = compare_report_pair(
        _load_report(args.report_a),
        _load_report(args.report_b),
        labels=(args.report_a.stem, args.report_b.stem),
    )
    _emit(result, args.out)
    return 0 if result["determinism_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
