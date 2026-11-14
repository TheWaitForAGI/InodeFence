"""One contained python-tarfile case -> ``EffectRunResult`` for the shared effect loop.

The python-tarfile twin of ``effect_pipeline.run_node_tar_effect_case``: build the case's TAR, run
the contained worker (``PythonTarfileContainedTarget``) on a disposable sandbox with sentinels,
capture BEFORE/AFTER with the unchanged Observer, judge with the unchanged C0/C1/C2 Oracle, and
build the effect trace host-side from the real snapshots with the in-process producer's trace
builder (``python_tarfile_effect._build_trace``, mechanism ``python-tarfile-container``).

The result plugs into ``effect_campaign.run_effect_campaign`` unchanged: mutation, scheduling and
feedback keys are the same as node-tar's; nothing python-specific enters the loop.

A worker report that cannot be read leaves every member unobserved, so the trace is INCOMPLETE
(fail-closed, feedback-ineligible) while the snapshot verdict on ``base_result`` stays the real one.
"""

from __future__ import annotations

from hashlib import sha256

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.feedback import state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntryReference,
    EffectRunResult,
    ExecutionStatus,
    LifecycleStatus,
    RunResult,
    SnapshotPhase,
)
from inodefence.observer import capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.runtime import SentinelSpec, disposable_sandbox
from inodefence.targets.python_tarfile_contained import (
    CONTAINER_MECHANISM,
    PythonTarfileCapture,
    PythonTarfileContainedTarget,
)
from inodefence.targets.python_tarfile_effect import _build_trace, _EntryExtraction


def member_extractions(
    capture: PythonTarfileCapture, references: tuple[ArchiveEntryReference, ...]
) -> tuple[_EntryExtraction, ...]:
    """Pair the worker's member lines with the case's entries; disagreement drops them all.

    The worker reads members from the TAR the host built from the same case, so member ``i`` is
    entry ``i``. An unreadable report, more members than entries, or a success exit with fewer
    members than entries leaves no observed member: the trace is then INCOMPLETE (fail-closed)
    while its termination still matches the real execution status.
    """
    members = capture.members
    if capture.report_error is not None or len(members) > len(references):
        return ()
    if capture.execution.status is ExecutionStatus.SUCCESS and len(members) != len(references):
        return ()
    return tuple(
        _EntryExtraction(
            references[member.ordinal],
            LifecycleStatus.SUCCEEDED if member.succeeded else LifecycleStatus.ERRORED,
            None if member.succeeded else member.error,
        )
        for member in members
    )


def run_python_tarfile_contained_case(
    case: ArchiveCase,
    target: PythonTarfileContainedTarget,
    *,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
) -> EffectRunResult:
    """Execute one whole TAR in the contained worker and compose the shared effect result."""
    if not isinstance(target, PythonTarfileContainedTarget):
        raise ValueError("python-tarfile case requires a bound PythonTarfileContainedTarget")
    archive = build_tar(case)
    references = tuple(
        ArchiveEntryReference(index, entry.path, entry.entry_type, entry.link_target)
        for index, entry in enumerate(case.entries)
    )
    with disposable_sandbox(sentinels) as sandbox:
        sandbox.archive_path.write_bytes(archive)
        with target.prepare(sandbox.archive_path, sandbox.extraction_root) as execute:
            before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
            capture = execute()
            after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
        extractions = member_extractions(capture, references)
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
        trace = _build_trace(
            before,
            after,
            references,
            extractions,
            capture.execution.status,
            sandbox.root,
            sandbox.extraction_root,
            CONTAINER_MECHANISM,
        )
    return EffectRunResult(base, trace)
