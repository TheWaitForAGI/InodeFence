"""One-case orchestration; no mutation, target policy, or corpus scheduling."""

from hashlib import sha256

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.feedback import state_signature
from inodefence.model import ArchiveCase, RunResult, SnapshotPhase
from inodefence.observer import capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.runtime import SentinelSpec, disposable_sandbox
from inodefence.targets import TargetAdapter


def run_case(
    case: ArchiveCase,
    target: TargetAdapter,
    *,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
) -> RunResult:
    """Build, run, observe and evaluate, then dispose of the runtime directory.

    Target failure/rejection still gets an after snapshot. Builder, environment,
    observer and unexpected adapter errors propagate as harness failures instead
    of invented passing results. Returned evidence contains no live Path objects.

    The observation window contains only target.run and observation: setup and
    input creation precede BEFORE, and AFTER precedes any post-run bookkeeping
    or cleanup. Adapters must not perform harness namespace writes in this window.
    """
    archive = build_tar(case)
    with disposable_sandbox(sentinels) as sandbox:
        sandbox.archive_path.write_bytes(archive)
        # Harness baseline is complete; region ownership never exempts target effects.
        before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
        execution = target.run(sandbox.archive_path, sandbox.extraction_root)
        # Capture target effects before any harness bookkeeping or sandbox cleanup.
        after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
        return RunResult(
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
