"""Minimize one saved violation case on its exact image and re-check it (#519, exploratory).

    python scripts/analysis/triage_violation_case.py <result folder> --case step-N \
        --out <folder outside the repository> [--baseline-runs 10] [--keep-runs 5]
        [--keep-min-hits 1] [--final-runs 20] [--rounds 3] [--budget 200]
    python scripts/analysis/triage_violation_case.py <case folder> --out <...>

Composes, without changing them:

* :func:`inodefence.case_replay.load_request` — reads the saved case (TAR hash, byte-identical
  reconstruction, exact image id, the exploration's run settings);
* the target adapter's own replay check and replay hook (``inodefence.drivers.<target>.replay``) —
  every candidate runs through the same launcher, controller, broker and isolation as
  ``inodefence replay``, one fresh controller per run, on the recorded image id (never prepared
  again or replaced);
* :mod:`inodefence.violation_triage` — :func:`~inodefence.violation_triage.triage`: measure the
  original n times, classify it (deterministic / nondeterministic / not reproduced), minimize
  under that class's keep rule (1-of-1, or k-of-n for nondeterministic cases), then check the
  minimum (re-run check, or an n-run re-measurement beside the original's rate).

Writes to ``--out`` (refused inside the repository): ``triage.json`` (record without TAR bytes),
``original.tar`` and the minimum (violating inputs: private, never published; SECURITY.md) --
``minimal.tar`` only for a result, ``minimal.reference-only.tar`` for a nondeterministic target,
and no minimum file (and no signature) when the case is not reproduced -- the record's
``code`` field names the commit and dirty flag of the code that ran,
and one work folder per run. Exit codes and summary line (first word after ``TRIAGE``):

* 0 ``CONSISTENT`` — deterministic original (n/n), minimized, re-run check matches;
* 1 ``NOT REPRODUCED`` — the original never showed a violation in n runs, or a deterministic
  minimum failed its re-run check (do not use the minimum);
* 4 ``NONDETERMINISTIC`` — 0 < original rate < 1: k-of-n minimization ran and the minimum was
  re-measured; the line shows both rates; the result is reference only;
* 2 refused/stopped before running; 3 a run failed.

**The minimized input and its signature are never used as a seed or corpus entry of any
exploration, benchmark or comparison arm.** This is not a product command (0.2.0 feature freeze)
and not part of any registered experiment. node-tar versions reserved for the v2 holdout are
refused.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

from inodefence.builder import build_tar
from inodefence.case_replay import CaseReplayError, ReplayRequest, load_request
from inodefence.drivers.repo import code_checkout
from inodefence.drivers.run_target import engine_provenance, load_adapter
from inodefence.drivers.run_target_replay import local_image_lookup
from inodefence.drivers.runtime import health
from inodefence.model import ArchiveCase
from inodefence.violation_triage import (
    CONTRACTS,
    Determinism,
    KeepRule,
    ResultStatus,
    TriagePolicy,
    TrialVerdict,
    triage,
    triage_record,
)

#: Where the minimum is written per status; none for a case that is not a result.
MINIMUM_FILE = {
    ResultStatus.RESULT: "minimal.tar",
    ResultStatus.REFERENCE_ONLY: "minimal.reference-only.tar",
}

EXIT_CONSISTENT = 0
EXIT_NOT_REPRODUCED = 1
EXIT_NONDETERMINISTIC = 4

#: node-tar ranges reserved for the v2 holdout (RESERVED.md 46cc970f): no run of any kind.
RESERVED_NODE_TAR = ((7, 0, 0, 7, 4, 3), (6, 0, 0, 6, 2, 1), (4, 4, 0, 5, 0, 999))


def reserved(target: str, version: str) -> bool:
    if target != "node-tar":
        return False
    found = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version.strip())
    if found is None:
        return True  # unknown spelling: refuse rather than guess
    current = tuple(int(part) for part in found.groups())
    for low_a, low_b, low_c, high_a, high_b, high_c in RESERVED_NODE_TAR:
        if (low_a, low_b, low_c) <= current <= (high_a, high_b, high_c):
            return True
    return False


def candidate_request(request: ReplayRequest, case: ArchiveCase) -> ReplayRequest:
    tar = build_tar(case)
    return dataclasses.replace(
        request,
        case=case,
        tar_bytes=tar,
        tar_sha256=sha256(tar).hexdigest(),
        case_id=case.case_id,
        rounds=1,
        runtime=None,
    )


def verdict_of(run: Any) -> TrialVerdict:
    """One finished round -> verdict; anything else is un-judged (never kept)."""
    detail: dict[str, Any] = {"complete": run.complete, "stop_reason": run.stop_reason}
    if not run.complete or len(run.rounds) != 1:
        return TrialVerdict(False, frozenset(), detail)
    round_ = run.rounds[0]
    detail.update(
        outcome=round_.get("outcome"),
        termination=round_.get("termination"),
        observation_complete=round_.get("observation_complete"),
    )
    values = {name: round_.get(name.lower()) for name in CONTRACTS}
    judged = (
        round_.get("outcome") == "judged"
        and round_.get("observation_complete") is not False
        and any(value is not None for value in values.values())
    )
    if not judged:
        return TrialVerdict(False, frozenset(), detail)
    return TrialVerdict(True, frozenset(name for name, value in values.items() if value), detail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("path", type=Path, help="exploration result folder or case folder")
    parser.add_argument("--case", help="step-N of a result folder")
    parser.add_argument("--out", type=Path, required=True, help="new folder outside the repository")
    parser.add_argument("--baseline-runs", type=int, default=10, help="original runs (10)")
    parser.add_argument("--keep-runs", type=int, default=5, help="nondeterministic: runs (5)")
    parser.add_argument("--keep-min-hits", type=int, default=1, help="... of which hits (1)")
    parser.add_argument("--final-runs", type=int, default=20, help="minimum re-measure (20)")
    parser.add_argument("--rounds", type=int, default=3, help="deterministic re-run check (3)")
    parser.add_argument("--budget", type=int, default=200, help="max minimization runs (200)")
    parser.add_argument("--label", default="exploratory (demo run, not registered)")
    args = parser.parse_args(argv)

    out = args.out.resolve()
    repo = code_checkout().resolve()
    if out == repo or repo in out.parents:
        print("TRIAGE REFUSED: --out is inside the repository (violating inputs)", file=sys.stderr)
        return 2
    if out.exists() and any(out.iterdir()):
        print(f"TRIAGE REFUSED: {out} exists and is not empty", file=sys.stderr)
        return 2
    try:
        request = load_request(args.path, case=args.case, rounds=1)
    except CaseReplayError as error:
        print(f"TRIAGE REFUSED: {error}", file=sys.stderr)
        return 2
    version = str(request.run_settings.get("target_version") or request.version)
    if reserved(request.target, version):
        print(f"TRIAGE REFUSED: {request.target} {version} is reserved (v2)", file=sys.stderr)
        return 2
    adapter = load_adapter(request.target)
    hook = adapter.replay
    if hook is None:
        print(f"TRIAGE REFUSED: {request.target} has no replay hook", file=sys.stderr)
        return 2
    check = getattr(adapter, "replay_check", None)
    if check is not None:
        try:
            check(request)
        except CaseReplayError as error:
            print(f"TRIAGE REFUSED: {error}", file=sys.stderr)
            return 2
    lookup = local_image_lookup(request.image_id)
    if lookup.state is not health.ImageState.PRESENT or lookup.image_id != request.image_id:
        print(f"TRIAGE STOPPED: image {request.image_id} is not on this host", file=sys.stderr)
        return 2

    try:
        policy = TriagePolicy(
            baseline_runs=args.baseline_runs,
            nondeterministic_keep=KeepRule(args.keep_runs, args.keep_min_hits),
            final_runs=args.final_runs,
            verify_rounds=args.rounds,
            execution_budget=args.budget,
        )
    except ValueError as error:
        print(f"TRIAGE REFUSED: {error}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    runs = out / "runs"
    runs.mkdir()
    counter = {"n": 0}

    def evaluate(case: ArchiveCase) -> TrialVerdict:
        counter["n"] += 1
        work = runs / f"{counter['n']:03d}-{case.case_id[:12]}"
        work.mkdir()
        run = hook(candidate_request(request, case), work)
        verdict = verdict_of(run)
        (work / "verdict.json").write_text(
            json.dumps(
                {
                    "case_id": case.case_id,
                    "entries": len(case.entries),
                    "judged": verdict.judged,
                    "violated": sorted(verdict.violated),
                    "detail": dict(verdict.detail),
                    "runner": run.runner,
                },
                indent=1,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )
        print(
            f"TRIAGE RUN {counter['n']}: entries={len(case.entries)} judged={verdict.judged} "
            f"violated={','.join(sorted(verdict.violated)) or '-'}",
            flush=True,
        )
        return verdict

    try:
        outcome = triage(request.case, evaluate, policy)
    except ValueError as error:
        print(f"TRIAGE STOPPED: {error}", file=sys.stderr)
        return 3
    record = triage_record(outcome, label=args.label)
    record["source"] = {
        "target": request.target,
        "version": version,
        "image_id": request.image_id,
        "case_id": request.case_id,
        "tar_sha256": request.tar_sha256,
        "engine_commit_of_exploration": request.engine_commit,
        "run_settings": request.run_settings,
    }
    provenance = engine_provenance(None)
    record["code"] = {"commit": provenance.engine_sha, "dirty": provenance.engine_dirty}
    (out / "original.tar").write_bytes(build_tar(request.case))
    name = MINIMUM_FILE.get(outcome.status)
    if outcome.run is not None and name is not None:
        (out / name).write_bytes(build_tar(outcome.run.minimal))
    (out / "triage.json").write_text(json.dumps(record, indent=1, sort_keys=True), "utf-8")
    print(summary_line(outcome, request.target, version))
    return exit_code(outcome)


def exit_code(outcome) -> int:
    if outcome.determinism is Determinism.NONDETERMINISTIC:
        return EXIT_NONDETERMINISTIC
    if outcome.determinism is Determinism.DETERMINISTIC and outcome.consistent:
        return EXIT_CONSISTENT
    return EXIT_NOT_REPRODUCED


def summary_line(outcome, target: str, version: str) -> str:
    base = outcome.baseline
    head = (
        f"{target} {version}: contracts={','.join(sorted(base.contracts)) or '-'} "
        f"original {base.hits}/{base.runs}"
    )
    if outcome.determinism is Determinism.NOT_REPRODUCED:
        return (
            f"TRIAGE NOT REPRODUCED {head} (no violation in the baseline runs; nothing minimized)"
        )
    run = outcome.run
    assert run is not None
    sizes = f"entries {len(run.original.entries)} -> {len(run.minimal.entries)}"
    if outcome.determinism is Determinism.NONDETERMINISTIC:
        final = outcome.final
        assert final is not None
        return (
            f"TRIAGE NONDETERMINISTIC {head} minimal {final.hits}/{final.runs} {sizes} "
            f"keep={run.keep.min_hits}-of-{run.keep.runs} executions={run.executions} "
            "(reference only)"
        )
    word = "CONSISTENT" if outcome.consistent else "NOT REPRODUCED"
    return f"TRIAGE {word} {head} {sizes} executions={run.executions}"


if __name__ == "__main__":
    raise SystemExit(main())
