"""Minimize one saved violation case on its exact image and re-check it (#519, exploratory).

    python scripts/analysis/triage_violation_case.py <result folder> --case step-N \
        --out <folder outside the repository> [--budget 40] [--rounds 3]
    python scripts/analysis/triage_violation_case.py <case folder> --out <...>

Composes, without changing them:

* :func:`inodefence.case_replay.load_request` — reads the saved case (TAR hash, byte-identical
  reconstruction, exact image id, the exploration's run settings);
* the target adapter's own replay check and replay hook (``inodefence.drivers.<target>.replay``) —
  every candidate runs through the same launcher, controller, broker and isolation as
  ``inodefence replay``, one fresh controller per run, on the recorded image id (never prepared
  again or replaced);
* :mod:`inodefence.violation_triage` — entry-level ddmin keeping the exact C0/C1/C2 set, the
  re-run check of original and minimum, and the cause signature.

Writes to ``--out`` (refused inside the repository): ``triage.json`` (record without TAR bytes),
``original.tar`` and ``minimal.tar`` (violating inputs: private, never published; SECURITY.md),
and one work folder per run. Exit codes: 0 done and consistent, 1 done but the re-run check did
not reproduce the verdict (do not use the minimum), 2 refused/stopped before running, 3 a run
failed.

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
from inodefence.drivers.run_target import load_adapter
from inodefence.drivers.run_target_replay import local_image_lookup
from inodefence.drivers.runtime import health
from inodefence.model import ArchiveCase
from inodefence.violation_triage import (
    CONTRACTS,
    TrialVerdict,
    minimize_entries,
    triage_record,
    verify,
)

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
    parser.add_argument("--budget", type=int, default=40, help="max minimization runs (default 40)")
    parser.add_argument("--rounds", type=int, default=3, help="re-run check rounds (default 3)")
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
        result = minimize_entries(request.case, evaluate, execution_budget=args.budget)
        checked = verify(result, evaluate, rounds=args.rounds)
    except ValueError as error:
        print(f"TRIAGE STOPPED: {error}", file=sys.stderr)
        return 3
    record = triage_record(result, checked, label=args.label)
    record["source"] = {
        "target": request.target,
        "version": version,
        "image_id": request.image_id,
        "case_id": request.case_id,
        "tar_sha256": request.tar_sha256,
        "engine_commit_of_exploration": request.engine_commit,
        "run_settings": request.run_settings,
    }
    (out / "original.tar").write_bytes(build_tar(result.original))
    (out / "minimal.tar").write_bytes(build_tar(result.minimal))
    (out / "triage.json").write_text(json.dumps(record, indent=1, sort_keys=True), "utf-8")
    print(
        f"TRIAGE {'CONSISTENT' if checked.consistent else 'NOT REPRODUCED'} "
        f"{request.target} {version}: contracts={','.join(sorted(result.contracts))} "
        f"entries {len(result.original.entries)} -> {len(result.minimal.entries)} "
        f"executions={result.executions} rounds={args.rounds} signature={record['signature']['id']}"
    )
    return 0 if checked.consistent else 1


if __name__ == "__main__":
    raise SystemExit(main())
