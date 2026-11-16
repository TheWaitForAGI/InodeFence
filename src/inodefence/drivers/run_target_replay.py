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
   The files the hook copied back under ``<work>/evidence/`` (controller report, round journal)
   are kept in that folder's ``evidence/``; an incomplete replay also records where and why it
   stopped (``replay.diagnosis``: stage x category, the shared abort classifier's categories), and
   every replay records which checkout ran it without its path (``replay.repository``).

Docker's answer to "is the exact image here?" has three states: present, absent (exit 3, never
prepared) and no usable answer (timeout / no daemon; also exit 3, named as Docker not answering,
with a follow-up ``docker info`` to tell a stalled daemon from a stopped one).

Exit codes: 0 replay complete; 1 replay incomplete or the hook failed (finished rounds are kept);
2 the case folder cannot be replayed as the same input/conditions; 3 the image is not on this
host, the folder is inside the repository, or the arguments are refused (usage error; 2 is kept for
the case folder); 4 the target has no replay support.

    python -m inodefence.drivers.run_target_replay <case folder> [--rounds 3] [--dry-run]
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from inodefence.case_replay import (
    DEFAULT_ROUNDS,
    MAX_ROUNDS,
    CaseReplayError,
    ReplayRequest,
    ReplayRun,
    build_replay_record,
    load_replay_request,
    publish_replay,
    replay_brief,
)
from inodefence.drivers.repo import code_checkout, require_repository_or_exit
from inodefence.drivers.run_target import TARGETS, RefusalParser, _git, load_adapter
from inodefence.drivers.runtime import health
from inodefence.drivers.runtime.diagnosis import replay_diagnosis
from inodefence.drivers.runtime.hooks import LaunchBlocked
from inodefence.drivers.runtime.session import RuntimeSession

#: The session's runtime record, kept in the published replay folder's ``evidence/``.
RUNTIME_RECORD_NAME = "runtime-record.json"

REPO_ROOT = code_checkout()


def local_image_lookup(image_id: str, runner=subprocess.run) -> health.ImageLookup:
    """Is ``image_id`` here: present (with the id Docker reports) / absent / no usable answer."""
    return health.lookup_image(image_id, runner=runner, timeout=30)


def local_image_id(image_id: str, runner=subprocess.run) -> str | None:
    """The id ``docker image inspect`` reports for ``image_id``, or ``None`` if it is absent.

    Also ``None`` when Docker did not answer; :func:`local_image_lookup` tells the two apart.
    """
    return local_image_lookup(image_id, runner).image_id


def checkout_record() -> dict[str, object]:
    """Which checkout ran the replay, without writing its path into the record.

    ``checkout_id`` is the first 12 hex digits of SHA-256 over the resolved checkout path: it tells
    two replays from the same clone apart from others. It is an identification aid, not a secret --
    a guessable path can be recovered by hashing candidates. ``dirty_tracked_files`` counts tracked
    files with uncommitted changes (``None`` when git cannot say).
    """
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "checkout_id": sha256(str(REPO_ROOT.resolve()).encode()).hexdigest()[:12],
        "dirty_tracked_files": None if status is None else len(status.splitlines()),
    }


def _evidence_report(evidence: Path) -> Path | None:
    """The one controller report (``*.json``) the hook copied back, if there is exactly one."""
    if not evidence.is_dir():
        return None
    reports = sorted(
        path
        for path in evidence.iterdir()
        if path.suffix == ".json" and path.name != RUNTIME_RECORD_NAME
    )
    return reports[0] if len(reports) == 1 else None


def engine_commit() -> str | None:
    sha = _git("rev-parse", "HEAD")
    if sha is None:
        return None
    dirty = _git("status", "--porcelain", "--untracked-files=no")
    return f"{sha}-dirty" if dirty else sha


def main(argv: list[str] | None = None, *, runner=subprocess.run) -> int:
    parser = RefusalParser(
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
    require_repository_or_exit(parser, 3)

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
    lookup = local_image_lookup(request.image_id, runner)
    present = lookup.image_id
    plan = {
        "case_dir": str(request.case_dir),
        "case_id": request.case_id,
        "tar_sha256": request.tar_sha256,
        "target": request.target,
        "version": request.version,
        "image_id": request.image_id,
        "image_present": present == request.image_id,
        "image_lookup": lookup.state.value,
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
    if lookup.state is health.ImageState.UNKNOWN:
        daemon = health.probe_daemon(runner=runner)
        cause = daemon.problem or "the daemon answers `docker info` but not the image question"
        print(
            f"REPLAY STOPPED: Docker did not answer whether image {request.image_id} is on this "
            f"host ({lookup.detail}; {cause}). Nothing was prepared or run.",
            file=sys.stderr,
        )
        return 3
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
    # STRICT, the same session type explore launches through; the hook gets it on the request.
    session = new_session(request.target)
    request = dataclasses.replace(request, runtime=session)
    with tempfile.TemporaryDirectory(prefix="inodefence-replay-") as work:
        try:
            run = adapter.replay(request, Path(work))
            failure = None
        except LaunchBlocked as error:
            # Nothing ran (a condition the launcher would refuse anyway, checked first): no
            # replay folder is published. One line, exit 3 like the other "nothing ran" stops.
            session.finish(result_written=False)
            print(f"REPLAY STOPPED: {error}. Nothing was run.", file=sys.stderr)
            return 3
        except Exception as error:  # noqa: BLE001 -- the record must say why it stopped
            run = ReplayRun(rounds=(), complete=False)
            failure = f"{type(error).__name__}: {error}"
        finished = datetime.now(UTC)
        session.finish(result_written=run.complete and failure is None)
        evidence = Path(work) / "evidence"
        runtime_record = session.render() if session.launches else None
        if runtime_record is not None:
            evidence.mkdir(exist_ok=True)
            (evidence / RUNTIME_RECORD_NAME).write_text(runtime_record, encoding="utf-8")
        return _record(request, run, failure, started, finished, evidence, runtime_record)


def new_session(target: str) -> RuntimeSession:
    """The replay's runtime session: STRICT, kind ``replay`` (output prefix ``REPLAY``)."""
    return RuntimeSession(target=target, kind="replay")


def _record(
    request: ReplayRequest,
    run: ReplayRun,
    failure: str | None,
    started: datetime,
    finished: datetime,
    evidence: Path,
    runtime_record: str | None = None,
) -> int:
    """Build, annotate and publish the replay record (``evidence`` is still on disk here)."""
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
    record["replay"]["repository"] = checkout_record()
    diagnosis = None
    if not record["replay"]["complete"]:
        smoke_exit = run.runner.get("smoke_exit") if failure is None else None
        journal = list(evidence.glob("*.steps.jsonl")) if evidence.is_dir() else []
        diagnosis = replay_diagnosis(
            smoke_exit if isinstance(smoke_exit, int) else None,
            _evidence_report(evidence),
            evidence=journal,
            rounds_done=len(record["rounds"]),
            hook_failure=failure or record["replay"]["stop_reason"],
        )
    record["replay"]["diagnosis"] = None if diagnosis is None else diagnosis.as_record()
    try:
        folder = publish_replay(request.case_dir, record, moment=finished, evidence=evidence)
    except (OSError, CaseReplayError) as error:
        print(
            f"REPLAY FAILED: the record could not be written beside {request.case_dir} ({error}); "
            "it follows on standard output so the rounds that ran are not lost",
            file=sys.stderr,
        )
        print(json.dumps(record, indent=2, sort_keys=True))
        if runtime_record is not None:
            print(
                "REPLAY RUNTIME RECORD (not published; publish failed): "
                + json.dumps(json.loads(runtime_record), sort_keys=True),
                file=sys.stderr,
            )
        return 1
    print(f"{replay_brief(record)}\nrecord: {folder / 'replay.json'}")
    if diagnosis is not None:
        # The scratch folder is gone after this; name the files where they were kept.
        kept = folder / "evidence"
        moved = tuple(
            kept / path.name for path in diagnosis.evidence if (kept / path.name).exists()
        )
        print(dataclasses.replace(diagnosis, evidence=moved).line("REPLAY"), file=sys.stderr)
    if not record["replay"]["complete"]:
        print(f"REPLAY INCOMPLETE: {record['replay']['stop_reason']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
