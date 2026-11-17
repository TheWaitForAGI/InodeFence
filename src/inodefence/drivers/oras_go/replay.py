"""oras-go's replay hook: one recorded case on its exact image, the input bytes untouched.

oras-go unpacks a directory artifact under its title, ``d/`` (``adapter.ARTIFACT_DIR``): a member
outside that frame is refused by the library before it extracts anything. ``verify`` relocates its
fixtures under ``d/`` for that reason, and the product's exploration sends each case with its
relative entry names under ``d/`` (``targets.oras_go_effect.under_artifact_dir``); the input it
stores for a violating run is those sent bytes. A replay re-runs the recorded bytes as they are,
so it never adds the prefix again: an input stored with ``d/`` runs with ``d/``, and an input an
older exploration saw rejected for lacking it is rejected again. The hook never rewrites member
names; it records how many members lie outside the frame
(``runner.members_outside_artifact_dir``) so a rejected replay can be read for what it is.

:func:`check` (before anything runs, and on ``--dry-run``) refuses settings that are not exactly
``target_version``, a version that is not exact, and one that differs from the case's recorded
version. The image is the recorded id; the controller binds it as exploration does
(``OrasGoFrameTarget``) and compares the oras-go version the image reports. Each round is the
exploration's own ``run_oras_go_frame_case``, judged by its rule: only a run that ended
``success`` or ``rejected`` carries a verdict (``scripts.effect_replay_targets``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from inodefence.case_replay import CaseReplayError, ReplayRequest, ReplayRun
from inodefence.drivers import replay_launch
from inodefence.drivers.image_prepare import EXACT_VERSION
from inodefence.drivers.oras_go import adapter as og

TARGET = "oras-go"
SETTINGS = ("target_version",)


def controller_settings(request: ReplayRequest) -> dict[str, str]:
    """The checked conditions as the controller takes them (``CaseReplayError`` refuses)."""
    replay_launch.exact_keys(request, SETTINGS)
    version = request.run_settings["target_version"]
    if not isinstance(version, str) or EXACT_VERSION.fullmatch(version) is None:
        raise CaseReplayError(
            f"oras-go target_version must be an exact X.Y.Z, got {version!r}: a replay pins "
            "one extractor version"
        )
    if request.version != version:
        raise CaseReplayError(
            f"the case's version {request.version!r} is not its target_version {version!r}"
        )
    return {replay_launch.TARGET_KEY: TARGET, "version": version}


def members_outside_frame(request: ReplayRequest) -> int:
    """How many members of the input are not under oras-go's artifact directory ``d/``."""
    frame = og.ARTIFACT_DIR
    return sum(
        1
        for entry in request.case.entries
        if entry.path != frame and not entry.path.startswith(frame + "/")
    )


def check(request: ReplayRequest) -> None:
    """``TargetAdapter.replay_check`` for oras-go."""
    controller_settings(request)


def replay(request: ReplayRequest, work_dir: Path, *, runner=subprocess.run) -> ReplayRun:
    """``TargetAdapter.replay`` for oras-go."""
    outside = members_outside_frame(request)
    return replay_launch.controller_replay(
        request,
        work_dir,
        controller_settings(request),
        runner=runner,
        runner_info={
            "artifact_dir": og.ARTIFACT_DIR,
            "members": len(request.case.entries),
            "members_outside_artifact_dir": outside,
            "input_rewritten": False,
        },
    )
