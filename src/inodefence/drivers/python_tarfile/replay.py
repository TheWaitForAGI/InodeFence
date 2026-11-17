"""python-tarfile's replay hook: one recorded case on its exact producer image, ONE filter.

A python-tarfile exploration runs on two axes that are both part of the conditions: the exact
interpreter ``X.Y.Z`` inside the producer image and ONE ``--extraction-filter``. Both are read from
the case's recorded ``run_settings`` (``runtime_version`` + ``extraction_filter``; from a result
folder these are its axes) -- never from a command-line option, so a replay cannot run the case
under another filter than the one it was explored with.

:func:`check` (before anything runs, and on ``--dry-run``) refuses:

- settings that are not exactly those two keys;
- a filter the target does not have, or one exploration does not run: ``fully_trusted``
  exploration is held (``EXPLORE_HELD_REASON``), so no explored case can carry it and replay does
  not offer a way around that;
- a runtime that is not exact, or that differs from the case's recorded version.

The image is the recorded id (the producer image: official ``python:X.Y.Z-slim`` plus the effect
worker). The controller binds it with ``expected_python``, so an image whose interpreter is not
the recorded ``X.Y.Z`` stops the replay; each round is the exploration's own
``run_python_tarfile_contained_case`` and is judged by its ``case_record`` rule
(``scripts.effect_replay_targets``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from inodefence.case_replay import CaseReplayError, ReplayRequest, ReplayRun
from inodefence.drivers import replay_launch
from inodefence.drivers.image_prepare import EXACT_VERSION
from inodefence.drivers.python_tarfile import adapter as rpt

TARGET = "python-tarfile"
SETTINGS = ("extraction_filter", "runtime_version")


def controller_settings(request: ReplayRequest) -> dict[str, str]:
    """The checked conditions as the controller takes them (``CaseReplayError`` refuses)."""
    replay_launch.exact_keys(request, SETTINGS)
    extraction_filter = request.run_settings["extraction_filter"]
    runtime = request.run_settings["runtime_version"]
    if extraction_filter not in rpt.FILTERS:
        raise CaseReplayError(
            f"python-tarfile has no extraction filter {extraction_filter!r} "
            f"(one of {', '.join(rpt.FILTERS)})"
        )
    if extraction_filter not in rpt.EXPLORE_FILTERS:
        raise CaseReplayError(
            f"extraction filter {extraction_filter} is not explored, so it is not replayed: "
            f"{rpt.EXPLORE_HELD_REASON}"
        )
    if not isinstance(runtime, str) or EXACT_VERSION.fullmatch(runtime) is None:
        raise CaseReplayError(f"runtime_version must be an exact X.Y.Z, got {runtime!r}")
    if request.version != runtime:
        raise CaseReplayError(
            f"the case's version {request.version!r} is not its runtime_version {runtime!r}"
        )
    return {
        replay_launch.TARGET_KEY: TARGET,
        "extraction_filter": extraction_filter,
        "runtime_version": runtime,
    }


def check(request: ReplayRequest) -> None:
    """``TargetAdapter.replay_check`` for python-tarfile."""
    controller_settings(request)


def replay(request: ReplayRequest, work_dir: Path, *, runner=subprocess.run) -> ReplayRun:
    """``TargetAdapter.replay`` for python-tarfile."""
    return replay_launch.controller_replay(
        request, work_dir, controller_settings(request), runner=runner
    )
