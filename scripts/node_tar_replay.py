"""node-tar's replay hook: re-run one recorded case on its exact image through the controller.

This is the node-tar implementation of ``TargetAdapter.replay`` (see
:mod:`inodefence.case_replay`). The common driver (``scripts.run_target_replay``) has already
checked the input (byte-identical case, same ``case_id``), the exact image id being present, and
the recorded run settings. Here:

1. write the one-line controller input (:func:`inodefence.case_replay.replay_input_line`) into
   the scratch folder;
2. run ``scripts/local_node_tar_smoke.sh replay`` -- the same isolation path exploration uses:
   disposable controller and volume, host broker, controller mode ``effect-replay-case``, which
   re-validates the input and runs the rounds with the exploration producer;
3. read the copied-back report (or, if the controller died before writing it, the copied-back
   ``<name>.steps.jsonl`` journal of finished rounds) and return them as a ``ReplayRun``.

Nothing is prepared or rebuilt here: the smoke script refuses an image that does not resolve to the
exact recorded id, and it never builds the node-tar image in this mode.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from inodefence.case_replay import CaseReplayError, ReplayRequest, ReplayRun, replay_input_line

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE = REPO_ROOT / "scripts" / "local_node_tar_smoke.sh"


def run_id_for(request: ReplayRequest) -> str:
    """A RUN_ID unique per replay process (the smoke script names controller/volume after it)."""
    return f"replay-{request.case_id[:12]}-{os.getpid()}"


def report_paths(evidence_dir: Path, run_id: str) -> tuple[Path, Path]:
    """Where the smoke script copies the controller report and its round journal back to."""
    report = evidence_dir / f"inodefence-case-replay-{run_id}.json"
    return report, report.with_suffix(".steps.jsonl")


def _read_rounds(report: dict[str, Any] | None, journal: Path) -> list[dict[str, Any]]:
    if report is not None and isinstance(report.get("rounds"), list):
        return list(report["rounds"])
    if not journal.is_file():
        return []
    rounds = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rounds.append(json.loads(line))
    return rounds


def replay(request: ReplayRequest, work_dir: Path, *, runner=subprocess.run) -> ReplayRun:
    """``TargetAdapter.replay`` for node-tar."""
    input_path = work_dir / "replay-input.jsonl"
    input_path.write_text(replay_input_line(request), encoding="utf-8")
    evidence_dir = work_dir / "evidence"
    run_id = run_id_for(request)
    env = {
        **os.environ,
        "INODEFENCE_EVIDENCE_DIR": str(evidence_dir),
        "RUN_ID": run_id,
        "REPLAY_IMAGE": request.image_id,
        "REPLAY_INPUT": str(input_path),
        "PYTHON": os.environ.get("PYTHON", sys.executable),
    }
    done = runner(["bash", str(SMOKE), "replay"], env=env, cwd=str(REPO_ROOT))
    report_path, journal_path = report_paths(evidence_dir, run_id)
    report: dict[str, Any] | None = None
    if report_path.is_file():
        loaded: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
        for key, expected in (
            ("case_id", request.case_id),
            ("tar_sha256", request.tar_sha256),
            ("image_id", request.image_id),
        ):
            if loaded.get(key) != expected:
                raise CaseReplayError(
                    f"controller report {key} {loaded.get(key)!r} is not this case's {expected!r}"
                )
        report = loaded
    rounds = _read_rounds(report, journal_path)
    complete = report is not None and report.get("complete") is True and done.returncode == 0
    stop_reason = None
    if not complete:
        if report is not None and report.get("stop_reason"):
            stop_reason = str(report["stop_reason"])
        elif report is None:
            stop_reason = (
                f"no controller report (smoke script exit {done.returncode}); "
                f"{len(rounds)} finished round(s) read from the journal"
            )
        else:
            stop_reason = f"smoke script exit {done.returncode}"
    runner_info = {
        "path": "scripts/local_node_tar_smoke.sh replay -> effect-replay-case",
        "smoke_exit": done.returncode,
        "run_id": run_id,
    }
    if report is not None:
        runner_info["node_tar_version"] = report.get("node_tar_version")
        runner_info["node_version"] = report.get("node_version")
    return ReplayRun(
        rounds=tuple(rounds), complete=complete, stop_reason=stop_reason, runner=runner_info
    )
