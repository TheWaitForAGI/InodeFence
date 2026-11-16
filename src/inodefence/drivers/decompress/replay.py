"""decompress's replay hook: one recorded case on its exact image, pinned to ``<package>@<X.Y.Z>``.

The original ``decompress`` and the fork ``@xhmikosr/decompress`` are different targets that share
one worker, so the version alone does not say which extractor ran: the case's recorded
``run_settings`` must hold the whole spec (``target_version`` = ``<package>@<X.Y.Z>``, the result
folder's axis). :func:`check` (before anything runs, and on ``--dry-run``) refuses settings that
are not exactly that key, a spec that is not exact (``parse_spec``: ``@latest`` names no fixed
extractor), and a spec that differs from the case's recorded version.

The image is the recorded id. The controller binds it as exploration does
(``DecompressFrameTarget``) and compares the package name and version the image itself reports
with the spec; a mismatch stops the replay. Each round is the exploration's own
``run_decompress_frame_case`` (the ``frame`` worker in a disposable sandbox with the default
sentinel), judged as the exploration judges a step: a violation is always judged, otherwise the
worker must have finished and emitted its frame (``scripts.effect_replay_targets``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from inodefence.case_replay import CaseReplayError, ReplayRequest, ReplayRun
from inodefence.drivers import replay_launch
from inodefence.drivers.decompress import adapter as dt

TARGET = "decompress"
SETTINGS = ("target_version",)


def controller_settings(request: ReplayRequest) -> dict[str, str]:
    """The checked conditions as the controller takes them (``CaseReplayError`` refuses)."""
    replay_launch.exact_keys(request, SETTINGS)
    spec = request.run_settings["target_version"]
    try:
        package, version = dt.parse_spec(spec if isinstance(spec, str) else "")
    except ValueError as error:
        raise CaseReplayError(
            f"decompress target_version {spec!r} is not a spec: {error}"
        ) from None
    if request.version != spec:
        raise CaseReplayError(
            f"the case's version {request.version!r} is not its target_version {spec!r}"
        )
    return {replay_launch.TARGET_KEY: TARGET, "package": package, "version": version}


def check(request: ReplayRequest) -> None:
    """``TargetAdapter.replay_check`` for decompress."""
    controller_settings(request)


def replay(request: ReplayRequest, work_dir: Path, *, runner=subprocess.run) -> ReplayRun:
    """``TargetAdapter.replay`` for decompress."""
    return replay_launch.controller_replay(
        request, work_dir, controller_settings(request), runner=runner
    )
