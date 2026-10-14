"""One-case native effect observation without changing the legacy pipeline."""

from dataclasses import dataclass
from hashlib import sha256

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.feedback import state_signature
from inodefence.model import ArchiveCase, EffectRunResult, RunResult, SnapshotPhase
from inodefence.observer import capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.runtime import SentinelSpec, disposable_sandbox
from inodefence.targets.node_tar_effect import (
    NativeEffectCapture,
    NodeTarEffectTarget,
    effect_trace_from_capture,
)


@dataclass(frozen=True, slots=True)
class NativeEffectRun:
    """Typed result plus the exact producer frame needed by an independent reader."""

    result: EffectRunResult
    raw_stream: bytes
    archive_sha256: str
    controller_flush_verified: bool
    transport_error: str | None

    def __post_init__(self) -> None:
        if self.result.base_result.archive_sha256 != self.archive_sha256:
            raise ValueError("native effect raw archive binding differs from RunResult")
        if self.result.trace.provenance.raw_stream_sha256 != sha256(self.raw_stream).hexdigest():
            raise ValueError("native effect raw stream differs from trace provenance")


def run_node_tar_effect_case(
    case: ArchiveCase,
    target: NodeTarEffectTarget,
    *,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
) -> NativeEffectRun:
    """Execute the same whole TAR and compose unchanged final-state evidence.

    The target adapter validates the terminal frame after the target stops and
    before this function captures AFTER. Invalid or incomplete frames still get
    an AFTER snapshot and a fail-closed trace; backend/observer failures retain
    the legacy behavior of propagating instead of inventing a result.
    """
    archive = build_tar(case)
    with disposable_sandbox(sentinels) as sandbox:
        sandbox.archive_path.write_bytes(archive)
        with target.prepare(sandbox.archive_path, sandbox.extraction_root) as execute:
            before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
            capture: NativeEffectCapture = execute()
            # execute() has already classified the terminal transport handshake.
            after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
            base = RunResult(
                case,
                sha256(archive).hexdigest(),
                BUILDER_FORMAT,
                capture.execution,
                before,
                after,
                compare_states(before, after),
                state_signature(before, after),
                evaluate_contracts(before, after),
            )
            trace = effect_trace_from_capture(capture, target, case, before, after)
            return NativeEffectRun(
                EffectRunResult(base, trace),
                capture.raw_stream,
                capture.expected_archive_sha256,
                capture.controller_flush_verified,
                capture.transport_error,
            )
