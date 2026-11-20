"""The host half of a case replay that names its target to the controller (shared by the hooks).

python-tarfile, decompress and oras-go each have their own replay hook
(``inodefence.drivers.<target>.replay``): the hook checks the request against that target's own
options and input constraints and turns the recorded ``run_settings`` into what the controller
needs to pin the same extractor. Launching is the same for all three and lives here:

1. write the one-line controller input (:func:`inodefence.case_replay.replay_input_line`) with the
   hook's controller settings (``target`` plus that target's keys);
2. run the replay launcher (:data:`inodefence.drivers.launcher.REPLAY_LAUNCHER_TARGET`'s script,
   mode ``replay``): disposable controller and volume, host broker, controller mode
   ``effect-replay-case``. The launcher refuses an image that does not resolve to the exact
   recorded id and never builds a target image; the target containers are created by the same
   broker and backend, with the same isolation, as in that target's exploration;
3. read the copied-back report (or, if the controller died before writing it, the journal of
   finished rounds) and return a ``ReplayRun``.

node-tar's hook (``inodefence.drivers.node_tar.replay``) predates this module and is unchanged.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from inodefence.case_replay import CaseReplayError, ReplayRequest, ReplayRun, replay_input_line
from inodefence.drivers.launcher import REPLAY_LAUNCHER_TARGET, launcher_path, run_launcher
from inodefence.drivers.repo import code_checkout
from inodefence.drivers.runtime.hooks import LaunchArtifacts

REPO_ROOT = code_checkout()
LAUNCHER = launcher_path(REPLAY_LAUNCHER_TARGET, REPO_ROOT)
#: ``run_settings`` key that names the target to the controller (``scripts.effect_replay_targets``).
TARGET_KEY = "target"


def run_id_for(request: ReplayRequest) -> str:
    """A RUN_ID unique per replay process (the launcher names controller/volume after it)."""
    return f"replay-{request.case_id[:12]}-{os.getpid()}"


def report_paths(evidence_dir: Path, run_id: str) -> tuple[Path, Path]:
    """Where the launcher copies the controller report and its round journal back to."""
    report = evidence_dir / f"inodefence-case-replay-{run_id}.json"
    return report, report.with_suffix(".steps.jsonl")


def exact_keys(request: ReplayRequest, wanted: tuple[str, ...]) -> None:
    """Refuse a request whose recorded ``run_settings`` are not exactly ``wanted`` (with why)."""
    given = set(request.run_settings)
    if given != set(wanted):
        raise CaseReplayError(
            f"{request.target} run_settings must be exactly {sorted(wanted)} (the conditions "
            f"its exploration runs under); missing {sorted(set(wanted) - given)}, "
            f"unexpected {sorted(given - set(wanted))}"
        )


#: The shared replay launcher's closing line names node-tar for every target
#: (``scripts/local_node_tar_smoke.sh``, ``PASSED: node-tar $MODE (context=...)``; a protected
#: launcher, not changed here). The replay hooks of the other targets show it with their own name.
_LAUNCHER_PASSED = "PASSED: node-tar replay"


def relabel_launcher_line(line: str, target: str) -> str:
    """``line`` with the launcher's node-tar ``PASSED`` label replaced by ``target`` (#494)."""
    if line.startswith(_LAUNCHER_PASSED):
        return f"PASSED: {target} replay{line[len(_LAUNCHER_PASSED) :]}"
    return line


def relabeling_runner(target: str):  # type: ignore[no-untyped-def]
    """A ``subprocess.run`` stand-in that streams the launcher's stdout line by line through
    :func:`relabel_launcher_line` (stderr, the exit code and everything else unchanged)."""

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        kwargs.pop("check", None)
        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            text=True,
            errors="replace",
            bufsize=1,
            **kwargs,
        ) as process:
            assert process.stdout is not None
            for line in process.stdout:
                sys.stdout.write(relabel_launcher_line(line, target))
                sys.stdout.flush()
            returncode = process.wait()
        return subprocess.CompletedProcess(command, returncode)

    return run


def _read_rounds(report: dict[str, Any] | None, journal: Path) -> list[dict[str, Any]]:
    if report is not None and isinstance(report.get("rounds"), list):
        return list(report["rounds"])
    if not journal.is_file():
        return []
    return [
        json.loads(line)
        for line in journal.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def controller_replay(
    request: ReplayRequest,
    work_dir: Path,
    settings: Mapping[str, Any],
    *,
    runner=subprocess.run,
    runner_info: Mapping[str, Any] | None = None,
) -> ReplayRun:
    """Run ``request`` in the controller under ``settings`` (which must name the target)."""
    if settings.get(TARGET_KEY) != request.target:
        raise CaseReplayError(
            f"controller settings name {settings.get(TARGET_KEY)!r}, the case is {request.target}"
        )
    input_path = work_dir / "replay-input.jsonl"
    input_path.write_text(
        replay_input_line(dataclasses.replace(request, run_settings=dict(settings))),
        encoding="utf-8",
    )
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
    if runner is subprocess.run:  # a test's fake runner is used as given
        runner = relabeling_runner(request.target)
    done = run_launcher(
        LAUNCHER,
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
            ("target", request.target),
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
                f"no controller report (launcher exit {done.returncode}); "
                f"{len(rounds)} finished round(s) read from the journal"
            )
        else:
            stop_reason = f"launcher exit {done.returncode}"
    info: dict[str, Any] = {
        "path": f"scripts/{LAUNCHER.name} replay -> effect-replay-case[{request.target}]",
        "smoke_exit": done.returncode,
        "run_id": run_id,
        "controller_settings": dict(settings),
        **dict(runner_info or {}),
    }
    if report is not None:
        info["target_identity"] = report.get("target_identity")
    return ReplayRun(rounds=tuple(rounds), complete=complete, stop_reason=stop_reason, runner=info)
