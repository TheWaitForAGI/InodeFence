"""Re-run one recorded violation case N times on the same image and record how often it repeats.

``inodefence replay <violation case folder>`` (this driver) is target-agnostic:

1. read and check the case folder (:func:`inodefence.case_replay.load_replay_request`): the TAR's
   SHA-256, a byte-identical reconstruction with the same ``case_id``, an exact image id and the
   exploration's ``run_settings``;
2. refuse a case folder inside this repository (it is public; results may hold real violating
   inputs), like ``run_target_explore`` refuses ``--out`` inside it;
3. confirm the exact image id is present on this host -- it is never prepared again or replaced by
   another image (that would not be the same conditions);
4. call the target's replay hook (``TargetAdapter.replay``), which re-runs the case through the
   same isolation path as exploration;
5. write ``replay.json`` in a new folder beside the case folder; the case folder is not touched.

Exit codes: 0 replay complete; 1 replay incomplete or the hook failed (finished rounds are kept);
2 the case folder cannot be replayed as the same input/conditions; 3 the image is not on this
host or the folder is inside the repository; 4 the target has no replay support.

    python -m scripts.run_target_replay <case folder> [--rounds 3] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from scripts.run_target import TARGETS, _git, load_adapter

from inodefence.case_replay import (
    DEFAULT_ROUNDS,
    MAX_ROUNDS,
    CaseReplayError,
    ReplayRun,
    build_replay_record,
    load_replay_request,
    publish_replay,
    replay_brief,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def local_image_id(image_id: str, runner=subprocess.run) -> str | None:
    """The id ``docker image inspect`` reports for ``image_id``, or ``None`` if it is absent."""
    try:
        done = runner(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image_id],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def engine_commit() -> str | None:
    sha = _git("rev-parse", "HEAD")
    if sha is None:
        return None
    dirty = _git("status", "--porcelain", "--untracked-files=no")
    return f"{sha}-dirty" if dirty else sha


def main(argv: list[str] | None = None, *, runner=subprocess.run) -> int:
    parser = argparse.ArgumentParser(
        prog="inodefence replay",
        description="Re-run one violation case folder N times on the same image (same isolation, "
        "same run settings) and record how often it reproduces.",
    )
    parser.add_argument("case_dir", type=Path, help="a live/violations/run-NNNNNN folder")
    parser.add_argument(
        "--rounds",
        type=int,
        default=DEFAULT_ROUNDS,
        help=f"how many times to re-run it (1..{MAX_ROUNDS}, default {DEFAULT_ROUNDS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="check everything (input, image, support) and print the plan; run nothing",
    )
    args = parser.parse_args(argv)

    try:
        request = load_replay_request(args.case_dir.expanduser(), rounds=args.rounds)
    except CaseReplayError as error:
        print(f"REPLAY REFUSED: {error}", file=sys.stderr)
        return 2
    if request.case_dir.is_relative_to(REPO_ROOT):
        print(
            f"REPLAY REFUSED: {request.case_dir} is inside the repository (it is public and a "
            "replay writes next to the case); keep exploration output outside it",
            file=sys.stderr,
        )
        return 3
    if request.target not in TARGETS:
        print(f"REPLAY REFUSED: unknown target {request.target!r}", file=sys.stderr)
        return 2
    adapter = load_adapter(request.target)
    present = local_image_id(request.image_id, runner)
    plan = {
        "case_dir": str(request.case_dir),
        "case_id": request.case_id,
        "tar_sha256": request.tar_sha256,
        "target": request.target,
        "version": request.version,
        "image_id": request.image_id,
        "image_present": present == request.image_id,
        "rounds": request.rounds,
        "run_settings": request.run_settings,
        "replay_supported": adapter.replay is not None,
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
    if adapter.replay is None:
        print(
            f"REPLAY UNSUPPORTED: target {request.target} has no replay hook yet", file=sys.stderr
        )
        return 4
    if present != request.image_id:
        print(
            f"REPLAY STOPPED: image {request.image_id} is not on this host. It is not prepared "
            "again or replaced: a replay on another image would not be the same conditions.",
            file=sys.stderr,
        )
        return 3
    if args.dry_run:
        return 0

    started = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="inodefence-replay-") as work:
        try:
            run = adapter.replay(request, Path(work))
            failure = None
        except Exception as error:  # noqa: BLE001 -- the record must say why it stopped
            run = ReplayRun(rounds=(), complete=False)
            failure = f"{type(error).__name__}: {error}"
    finished = datetime.now(UTC)
    if run.engine_commit is None:
        run = ReplayRun(
            rounds=run.rounds,
            complete=run.complete,
            stop_reason=run.stop_reason,
            engine_commit=engine_commit(),
            runner=run.runner,
        )
    if failure is not None:
        run = ReplayRun(
            rounds=run.rounds,
            complete=False,
            stop_reason=failure,
            engine_commit=run.engine_commit,
            runner=run.runner,
        )
    try:
        record = build_replay_record(request, run, started_at=started, finished_at=finished)
    except CaseReplayError as error:
        print(f"REPLAY FAILED: the target returned an invalid round: {error}", file=sys.stderr)
        return 1
    folder = publish_replay(request.case_dir, record, moment=finished)
    print(f"{replay_brief(record)}\nrecord: {folder / 'replay.json'}")
    if not record["replay"]["complete"]:
        print(f"REPLAY INCOMPLETE: {record['replay']['stop_reason']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
