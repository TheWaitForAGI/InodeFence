"""node-tar's replay hook: re-run one recorded case on its exact image through the controller.

This is the node-tar implementation of ``TargetAdapter.replay`` (see
:mod:`inodefence.case_replay`). The common driver (``inodefence.drivers.run_target_replay``) has
already
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
from inodefence.drivers.launcher import launcher_path, run_launcher
from inodefence.drivers.repo import code_checkout
from inodefence.drivers.runtime.hooks import LaunchArtifacts

REPO_ROOT = code_checkout()
SMOKE = launcher_path("node-tar", REPO_ROOT)


#: The ``run_settings`` keys node-tar exploration records in a live case folder (the controller
#: requires exactly these: ``scripts.effect_replay.NODE_TAR_SETTINGS``; a test keeps them in step).
NODE_TAR_SETTINGS = ("sentinel_count", "sentinel_seed", "observer_integrity_policy", "profile")


def check(request: ReplayRequest) -> None:
    """``TargetAdapter.replay_check`` for node-tar: the recorded conditions must be complete.

    A node-tar exploration's sandbox (sentinel set), observer-integrity policy and profile are
    recorded only in the live case folder's ``case.json``. A result folder's ``result.json`` holds
    the axes alone, so a case read from it cannot be re-run under the same conditions and is
    refused here, naming where the replayable record is.
    """
    given = set(request.run_settings)
    if given == set(NODE_TAR_SETTINGS):
        return
    where = (
        " A node-tar result folder does not record them; replay the live case folder instead "
        "(<out>/target-explore/<run>/live/violations/run-NNNNNN)."
        if request.source == "result-folder"
        else ""
    )
    raise CaseReplayError(
        f"node-tar run_settings must be exactly {sorted(NODE_TAR_SETTINGS)} (the sentinel set, "
        f"observer policy and profile the exploration ran under); missing "
        f"{sorted(set(NODE_TAR_SETTINGS) - given)}, unexpected "
        f"{sorted(given - set(NODE_TAR_SETTINGS))}.{where}"
    )


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
    report_path, journal_path = report_paths(evidence_dir, run_id)
    # The driver's STRICT runtime session rides on the request (none: a plain launch, as before).
    done = run_launcher(
        SMOKE,
        ["replay"],
        runner=runner,
        env=env,
        session=getattr(request, "runtime", None),
        artifacts=LaunchArtifacts(report=report_path),
        cwd=str(REPO_ROOT),
    )
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
