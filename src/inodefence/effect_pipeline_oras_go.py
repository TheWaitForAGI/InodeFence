"""One oras-go case: real extraction + the boundary-attempt frame, judged by the generic oracle.

This is the oras-go twin of ``effect_pipeline_decompress.run_decompress_frame_case``. It runs the
real pinned oras-go image (via the ``OrasGoFrameTarget`` ``frame`` worker) on a disposable sandbox
with a sentinel, captures the production before/after snapshots and C0/C1/C2 verdict with the
UNCHANGED Observer/Oracle, and keeps the worker's ``inodefence-boundary-attempt-v1`` stdout frame
as the per-operation observation channel for self-discovery feedback.

Honesty: the oracle verdict (the C1/C2 "hit") is the production path on real before/after snapshots
-- target-agnostic, no oras-go-specific condition. The frame is the set-based boundary-attempt
signal derived from the observed post-extraction filesystem state (oras-go is a compiled
third-party extractor, so its link calls cannot be interposed; the feasible channel is the
post-state SET, which does not observe a cleanly refused attempt). A malformed/absent frame fails
the gradient channel closed (no attempt keys) without affecting the independent oracle verdict.
"""

import json
from dataclasses import dataclass
from hashlib import sha256

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.feedback import state_signature
from inodefence.feedback.boundary_attempt_frame import FRAME_FORMAT
from inodefence.model import ArchiveCase, RunResult, SnapshotPhase
from inodefence.observer import capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.runtime import SentinelSpec, disposable_sandbox
from inodefence.targets.isolated import IsolatedTarget


@dataclass(frozen=True, slots=True)
class OrasGoFrameRun:
    """A real oras-go run: the production ``RunResult`` plus its boundary-attempt frame.

    ``frame`` is the validated ``inodefence-boundary-attempt-v1`` payload, or ``None`` when the
    worker emitted no parseable frame (``frame_error`` then says why). The base result's oracle
    verdict is independent of the frame.
    """

    base_result: RunResult
    frame: dict | None
    frame_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.base_result, RunResult):
            raise ValueError("oras-go frame run requires a typed RunResult")
        if (self.frame is None) == (self.frame_error is None):
            raise ValueError("exactly one of frame / frame_error must be set")
        if self.frame is not None and not isinstance(self.frame, dict):
            raise ValueError("oras-go frame must be a mapping when present")


def _parse_frame(stdout: str) -> tuple[dict | None, str | None]:
    """Parse the worker's last stdout line as a v1 boundary-attempt frame.

    Returns ``(frame, None)`` for a well-formed ``inodefence-boundary-attempt-v1`` frame whose
    ``attempts`` is a list, else ``(None, reason)``. Validation is deliberately shallow here; the
    sanctioned ``frame_boundary_attempt_keys`` normalizer re-checks the format before deriving keys.
    """
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None, "oras-go frame worker produced no stdout frame"
    try:
        frame = json.loads(lines[-1])
    except ValueError as error:
        return None, f"oras-go frame is not valid JSON: {error}"
    if not isinstance(frame, dict) or frame.get("format") != FRAME_FORMAT:
        return None, f"stdout frame is not an {FRAME_FORMAT} frame"
    if frame.get("schema_version") != 1 or not isinstance(frame.get("attempts"), list):
        return None, "boundary-attempt frame is missing schema_version 1 / attempts list"
    return frame, None


def run_oras_go_frame_case(
    case: ArchiveCase,
    target: IsolatedTarget,
    *,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
) -> OrasGoFrameRun:
    """Build the case's TAR, run real oras-go, and compose the oracle verdict plus the frame.

    Mirrors the node-tar effect pipeline's BEFORE/execute/AFTER bracket so the generic Observer and
    Oracle judge the real post-state unchanged; the worker's stdout frame is parsed afterwards.
    """
    if not isinstance(target, IsolatedTarget):
        raise ValueError("oras-go frame run requires a bound IsolatedTarget")
    archive = build_tar(case)
    with disposable_sandbox(sentinels) as sandbox:
        sandbox.archive_path.write_bytes(archive)
        with target.prepare(sandbox.archive_path, sandbox.extraction_root) as execute:
            before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
            execution = execute()
            after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
        base = RunResult(
            case,
            sha256(archive).hexdigest(),
            BUILDER_FORMAT,
            execution,
            before,
            after,
            compare_states(before, after),
            state_signature(before, after),
            evaluate_contracts(before, after),
        )
        frame, frame_error = _parse_frame(execution.stdout)
        return OrasGoFrameRun(base, frame, frame_error)
