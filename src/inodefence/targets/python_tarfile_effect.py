"""In-process Python-``tarfile`` effect producer (M4.1b extractor → effect campaign).

Runs the Python standard-library ``tarfile`` extractor as an ``EffectResultProducer``
so the *same* snapshot Observer + C0/C1/C2 Oracle + feedback + abort classification
that drive the node-tar effect campaign also exercise a second, independent extractor
(generality, H-B). This is NOT a node-tar result and NOT a fuzzer finding.

Isolation is the host ``disposable_sandbox`` + sentinels under the runtime root only:
there is **no container boundary**, so every trace carries
``mechanism = "python-tarfile-inprocess"`` and must never be reported as a node-tar
(native) observation.

SAFETY: the ``data`` policy (PEP 706) is designed to confine extraction to ``extract/``,
but whether it does so for arbitrary (fuzzed/mutated) archives in-process depends on the
CPython patch level: upstream PEP 706 filter bypasses were fixed in 3.12.11, and distro
builds may or may not carry the backports. The lock (:func:`python_tarfile_lock`) only
records the interpreter version string and the ``tarfile.py`` hash; it does not verify
those fixes. Using this in-process producer in a registered campaign therefore needs
지웅's approval under D022 (untrusted targets run behind a container boundary); this
module does not grant that approval. The ``fully_trusted`` policy
applies no sanitation, so a ``..``/absolute member can escape the disposable sandbox
to the host -- it is only for TRUSTED, bounded inputs (the committed M4.1b control
fixtures, whose escape reaches the in-sandbox sentinel, not the host). Do NOT run a
``fully_trusted`` fuzzing campaign through this in-process producer; that requires
container isolation like the node-tar path.

Because the extractor is a trusted reference run in-process, the trace is assembled
directly from the real BEFORE/AFTER observation rather than from a verified transport
frame (the node-tar crypto frame reader ``effect_trace_from_capture`` is bound to
node-tar's source identity and is not reused).

The snapshot Oracle verdict on ``base_result`` is the generality signal and is
independent of the trace. Per-entry lifecycle events give coverage; per-entry effect
events read the *real* object the entry produced from the ``after`` snapshot (honest
observation — unresolved objects, e.g. a boundary escape landing outside ``extract/``,
contribute lifecycle only). A successful run yields a COMPLETE, integrity-valid trace;
a rejected run yields a COMPLETE, feedback-ineligible trace (termination REJECTED); a
failed/observer-error run yields an INCOMPLETE fail-closed trace.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.feedback import state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntryReference,
    AssociationKind,
    CausalRelation,
    CausalRelationKind,
    EffectClass,
    EffectEventTrace,
    EffectEvidenceStrength,
    EffectObjectObservation,
    EffectObservationStatus,
    EffectPathEvidence,
    EffectRunResult,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EffectTraceProvenance,
    EntryLifecycleEvent,
    EntryLifecycleKind,
    EntryType,
    EvidenceSourceIdentity,
    ExecutionResult,
    ExecutionStatus,
    FilesystemEffectEvent,
    LifecycleStatus,
    MonotonicInterval,
    ObjectSnapshot,
    ObjectType,
    ObservationFailure,
    ObservationFailureKind,
    ObservedOperationType,
    OperationOutcome,
    RawEvidenceReference,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
)
from inodefence.observer import capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.runtime import SentinelSpec, disposable_sandbox

PYTHON_TARFILE_MECHANISM = "python-tarfile-inprocess"
PYTHON_TARFILE_SOURCE_ID = "python-tarfile"
PYTHON_TARFILE_POLICIES = ("fully_trusted", "data")
_EVENT_BOUND = 1024
_REQUIRED_LIFECYCLE = (EntryLifecycleKind.READ, EntryLifecycleKind.EFFECT_WORK_STARTED)
_TRACE_SCHEMA = "entry-effect-trace-v2"


@dataclass(frozen=True, slots=True)
class PythonTarfileLock:
    """Reproducible identity material for the in-process interpreter + ``tarfile``.

    PR-A exposes the raw material only; the launcher (PR-B) composes ``lock_digest``
    = ``sha256(python_version + "\\n" + tarfile_sha256 + "\\n" + uname_sr + "\\n")``.
    """

    python_version: str
    tarfile_sha256: str
    uname_sr: str


def python_tarfile_lock() -> PythonTarfileLock:
    """The lock material for the interpreter that will run the extraction."""
    probe = subprocess.run([sys.executable, "-VV"], capture_output=True, text=True, check=True)
    python_version = probe.stdout or probe.stderr
    tarfile_sha256 = sha256(Path(tarfile.__file__).read_bytes()).hexdigest()
    uname = platform.uname()
    return PythonTarfileLock(python_version, tarfile_sha256, f"{uname.system} {uname.release}")


@dataclass(frozen=True, slots=True)
class PythonTarfileEffectTarget:
    """A Python-``tarfile`` extraction policy, run in-process as an effect producer."""

    policy: str = "fully_trusted"

    def __post_init__(self) -> None:
        if self.policy not in PYTHON_TARFILE_POLICIES:
            raise ValueError(f"policy must be one of {PYTHON_TARFILE_POLICIES}")

    @property
    def target_id(self) -> str:
        return f"python-tarfile-{self.policy.replace('_', '-')}"

    @property
    def lock(self) -> PythonTarfileLock:
        return python_tarfile_lock()


@dataclass(frozen=True, slots=True)
class _EntryExtraction:
    reference: ArchiveEntryReference
    status: LifecycleStatus
    normalized_error: str | None


@dataclass(frozen=True, slots=True)
class PythonTarfileEffectRun:
    """EffectRunResult plus the in-process lock material (for the launcher/report)."""

    result: EffectRunResult
    lock: PythonTarfileLock
    mechanism: str = PYTHON_TARFILE_MECHANISM


def _interval(sequence: int) -> MonotonicInterval:
    return MonotonicInterval(sequence * 10, sequence * 10 + 1)


def _source(mechanism: str = PYTHON_TARFILE_MECHANISM) -> EvidenceSourceIdentity:
    return EvidenceSourceIdentity(
        PYTHON_TARFILE_SOURCE_ID,
        mechanism,
        "1",
        sha256(PYTHON_TARFILE_SOURCE_ID.encode()).hexdigest(),
    )


def _raw(record: str) -> RawEvidenceReference:
    return RawEvidenceReference(PYTHON_TARFILE_SOURCE_ID, record)


def _provenance(
    stream_digest: str, mechanism: str = PYTHON_TARFILE_MECHANISM
) -> EffectTraceProvenance:
    return EffectTraceProvenance(
        _TRACE_SCHEMA,
        "1",
        "python-tarfile-feedback",
        (_source(mechanism),),
        _EVENT_BOUND,
        _REQUIRED_LIFECYCLE,
        stream_digest,
    )


def _lifecycle(
    sequence: int,
    reference: ArchiveEntryReference,
    kind: EntryLifecycleKind,
    status: LifecycleStatus,
    normalized_error: str | None,
) -> EntryLifecycleEvent:
    return EntryLifecycleEvent(
        sequence,
        reference,
        kind,
        _interval(sequence),
        status,
        normalized_error,
        PYTHON_TARFILE_SOURCE_ID,
        _raw(f"lifecycle-{sequence}"),
    )


def _observation(obj: ObjectSnapshot | None) -> EffectObjectObservation:
    return EffectObjectObservation(
        EffectObservationStatus.ABSENT if obj is None else EffectObservationStatus.PRESENT,
        obj,
    )


def _effect_for_entry(
    start: int,
    completion: int,
    reference: ArchiveEntryReference,
    before_by_path: dict[str, ObjectSnapshot],
    after_obj: ObjectSnapshot,
    after_objects: tuple[ObjectSnapshot, ...],
) -> FilesystemEffectEvent:
    """One observed effect, keyed to the real ``after`` object.

    A hardlink entry whose created object shares identity ``(st_dev, st_ino)`` with a
    distinct object in the ``after`` snapshot is recorded as an identity-relation
    creation over that observed path pair (the C1 signal, read from real inodes);
    everything else is a single-path namespace/symlink creation.
    """
    before_obj = before_by_path.get(after_obj.path)
    if reference.entry_type == EntryType.HARDLINK:
        partner = next(
            (
                obj
                for obj in after_objects
                if obj.identity == after_obj.identity and obj.path != after_obj.path
            ),
            None,
        )
        if partner is not None:
            affected = (partner.path, after_obj.path)
            evidence = (
                EffectPathEvidence(
                    partner.path,
                    _observation(before_by_path.get(partner.path)),
                    _observation(partner),
                ),
                EffectPathEvidence(
                    after_obj.path, _observation(before_obj), _observation(after_obj)
                ),
            )
            return FilesystemEffectEvent(
                start,
                completion,
                reference,
                AssociationKind.ASYNC_CONTEXT,
                EffectClass.HARDLINK_IDENTITY_RELATION_CREATION,
                EffectEvidenceStrength.IDENTITY_VERIFIED,
                affected,
                ObservedOperationType.LINK,
                _interval(start),
                _interval(completion),
                OperationOutcome.SUCCEEDED,
                evidence,
                PYTHON_TARFILE_SOURCE_ID,
                f"operation-{start}",
                _raw(f"effect-{completion}"),
            )
    if reference.entry_type == EntryType.SYMLINK and after_obj.object_type == ObjectType.SYMLINK:
        effect_class = EffectClass.SYMLINK_CREATION
        operation = ObservedOperationType.SYMLINK
    else:
        effect_class = EffectClass.NAMESPACE_CREATION
        operation = ObservedOperationType.OPEN
    path = after_obj.path
    return FilesystemEffectEvent(
        start,
        completion,
        reference,
        AssociationKind.ASYNC_CONTEXT,
        effect_class,
        EffectEvidenceStrength.STATE_CHANGE_VERIFIED,
        (path,),
        operation,
        _interval(start),
        _interval(completion),
        OperationOutcome.SUCCEEDED,
        (EffectPathEvidence(path, _observation(before_obj), _observation(after_obj)),),
        PYTHON_TARFILE_SOURCE_ID,
        f"operation-{start}",
        _raw(f"effect-{completion}"),
    )


def _edge(before: int, after: int, kind: CausalRelationKind, token: str) -> CausalRelation:
    return CausalRelation(
        before, after, kind, PYTHON_TARFILE_SOURCE_ID, token, _raw(f"edge-{before}-{after}")
    )


def _extracted_path(reference: ArchiveEntryReference, root: Path, extraction_root: Path) -> str:
    """Sandbox-relative path where ``reference`` is expected to land under ``extract/``."""
    rel_root = extraction_root.relative_to(root).as_posix()
    cleaned = reference.path.strip("/")
    candidate = f"{rel_root}/{cleaned}" if cleaned else rel_root
    # Normalize without resolving ``..`` past the sandbox root (keep it relative evidence).
    parts: list[str] = []
    for segment in candidate.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if parts:
                parts.pop()
            continue
        parts.append(segment)
    return "/".join(parts)


def _build_trace(
    before: StateSnapshot,
    after: StateSnapshot,
    references: tuple[ArchiveEntryReference, ...],
    extractions: tuple[_EntryExtraction, ...],
    status: ExecutionStatus,
    root: Path,
    extraction_root: Path,
    mechanism: str = PYTHON_TARFILE_MECHANISM,
) -> EffectEventTrace:
    # ``archive_entries`` is the FULL declared case structure (every entry by ordinal
    # + path, duplicates and order preserved), NOT only the entries reached before an
    # early rejection -- the EffectRunResult identity invariant requires it to equal
    # ArchiveCase. This matches the node-tar producer, whose canonical records are keyed
    # per ordinal too. Lifecycle/effect events below cover only the observed (succeeded)
    # entries; a rejected/failed run is therefore feedback-ineligible, not a crash.
    after_by_path = {obj.path: obj for obj in after.objects}
    before_by_path = {obj.path: obj for obj in before.objects}

    succeeded = [item for item in extractions if item.status == LifecycleStatus.SUCCEEDED]
    lifecycle: list[EntryLifecycleEvent] = []
    effects: list[FilesystemEffectEvent] = []
    edges: list[CausalRelation] = []
    failures: list[ObservationFailure] = []
    # Assign sequences by actual emission so observed event points stay contiguous:
    # every entry contributes READ + EFFECT_WORK_STARTED; an entry whose object
    # resolves in the real ``after`` snapshot also contributes one effect (start +
    # completion). Entries that escaped the ``extract/`` prefix keep lifecycle only.
    seq = 0
    for item in succeeded:
        read = seq
        work = seq + 1
        seq += 2
        lifecycle.append(
            _lifecycle(
                read, item.reference, EntryLifecycleKind.READ, LifecycleStatus.SUCCEEDED, None
            )
        )
        lifecycle.append(
            _lifecycle(
                work,
                item.reference,
                EntryLifecycleKind.EFFECT_WORK_STARTED,
                LifecycleStatus.SUCCEEDED,
                None,
            )
        )
        path = _extracted_path(item.reference, root, extraction_root)
        after_obj = after_by_path.get(path)
        if after_obj is not None:
            begin = seq
            done = seq + 1
            seq += 2
            effect = _effect_for_entry(
                begin, done, item.reference, before_by_path, after_obj, after.objects
            )
            effects.append(effect)
            edges.append(
                _edge(work, begin, CausalRelationKind.ENTRY_CONTEXT_PROPAGATION, "context")
            )
            edges.append(
                _edge(begin, done, CausalRelationKind.OPERATION_INTERVAL, effect.correlation_id)
            )

    terminated = {
        ExecutionStatus.SUCCESS: EffectTargetTermination.SUCCESS,
        ExecutionStatus.REJECTED: EffectTargetTermination.REJECTED,
        ExecutionStatus.FAILED: EffectTargetTermination.FAILED,
        ExecutionStatus.TIMED_OUT: EffectTargetTermination.TIMED_OUT,
    }[status]

    # A clean success (all entries) or a rejection with at least one observed entry is
    # a complete observation up to the target's stop; everything else (failure, timeout,
    # rejection before any entry) is observer-incomplete and fails closed.
    all_entries = len(succeeded) == len(references) and bool(references)
    if (status == ExecutionStatus.SUCCESS and all_entries) or (
        status == ExecutionStatus.REJECTED and seq > 0
    ):
        completeness = EffectStreamCompleteness.COMPLETE
    else:
        completeness = EffectStreamCompleteness.INCOMPLETE
        failures.append(
            ObservationFailure(
                ObservationFailureKind.EXECUTION_BACKEND_FAILURE,
                f"python tarfile extraction did not complete cleanly: {status.value}",
                PYTHON_TARFILE_SOURCE_ID,
            )
        )

    last = seq - 1 if seq else 0
    stream_digest = sha256(
        f"{mechanism}:{status.value}:{len(succeeded)}:{after.phase.value}".encode()
    ).hexdigest()
    return EffectEventTrace(
        before,
        references,
        tuple(lifecycle),
        tuple(effects),
        tuple(edges),
        (),
        after,
        completeness,
        terminated,
        _provenance(stream_digest, mechanism),
        last,
        last,
        last,
        tuple(failures),
    )


def _extract_in_process(
    target: PythonTarfileEffectTarget, archive_path: Path, extraction_root: Path, case: ArchiveCase
) -> tuple[tuple[ArchiveEntryReference, ...], tuple[_EntryExtraction, ...], ExecutionResult]:
    references = tuple(
        ArchiveEntryReference(index, entry.path, entry.entry_type, entry.link_target)
        for index, entry in enumerate(case.entries)
    )
    results: list[_EntryExtraction] = []
    status, code, stderr = ExecutionStatus.SUCCESS, 0, ""
    command = (sys.executable, "tarfile.extractall", f"filter={target.policy}")
    started = perf_counter()
    try:
        with tarfile.open(archive_path, mode="r:") as archive:
            archive.errorlevel = 2
            members = archive.getmembers()
            if len(members) != len(references):
                status, code, stderr = (
                    ExecutionStatus.FAILED,
                    3,
                    "archive member/entry count mismatch",
                )
            else:
                for reference, member in zip(references, members, strict=True):
                    try:
                        # policy is runtime-validated to a valid PEP 706 filter name.
                        archive.extract(
                            member,
                            extraction_root,
                            filter=target.policy,  # pyright: ignore[reportArgumentType]
                        )
                        results.append(_EntryExtraction(reference, LifecycleStatus.SUCCEEDED, None))
                    except tarfile.FilterError as error:
                        status, code = ExecutionStatus.REJECTED, 2
                        stderr = f"{type(error).__name__}: {error}"
                        results.append(
                            _EntryExtraction(
                                reference, LifecycleStatus.ERRORED, type(error).__name__
                            )
                        )
                        break
    except tarfile.FilterError as error:
        status, code, stderr = ExecutionStatus.REJECTED, 2, f"{type(error).__name__}: {error}"
    except tarfile.TarError as error:
        status, code, stderr = ExecutionStatus.FAILED, 3, f"{type(error).__name__}: {error}"
    except OSError as error:
        # errorlevel=2 (and the ``data`` filter's realpath check) surface extractor
        # filesystem errors -- e.g. an entry whose parent path was already extracted as a
        # regular file -- as OSError. That is a target-side step failure, mapped to the
        # same FAILED / INCOMPLETE fail-closed trace as a TarError; letting it propagate
        # would make the campaign driver count it as a cell abort (censoring) instead.
        status, code, stderr = ExecutionStatus.FAILED, 3, f"{type(error).__name__}: {error}"
    elapsed = perf_counter() - started
    execution = ExecutionResult(
        target.target_id,
        platform.python_version(),
        command,
        status,
        code,
        "",
        stderr[:200],
        duration_seconds=elapsed,
    )
    return references, tuple(results), execution


def run_python_tarfile_effect_case(
    case: ArchiveCase,
    target: PythonTarfileEffectTarget,
    *,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    trusted_fixture: bool = False,
) -> PythonTarfileEffectRun:
    """Extract one whole TAR with Python ``tarfile`` and compose an EffectRunResult.

    Mirrors :func:`inodefence.effect_pipeline.run_node_tar_effect_case` for the
    in-process reference extractor: unchanged BEFORE/AFTER snapshot evidence and the
    generic C0/C1/C2 Oracle verdict on ``base_result``; the trace is built from the
    real observation and marked ``mechanism = "python-tarfile-inprocess"``.

    Safety (fail-closed, per the surgery safety boundary): ``fully_trusted`` applies no
    sanitation, so in-process it can escape the disposable sandbox to the host. It is
    therefore permitted ONLY when the caller asserts a trusted, bounded input via
    ``trusted_fixture=True`` (the committed M4.1b control fixtures). Any arbitrary or
    fuzzed archive must use the ``data`` filter (designed to confine extraction; whether
    it does so for fuzzed input depends on the CPython patch level, and registered
    in-process use still needs D022 approval -- see the module docstring), so a
    campaign/fuzzing driver -- which never sets ``trusted_fixture`` -- is rejected under
    ``fully_trusted``. ``fully_trusted`` fuzzing requires a container-isolated path.
    """
    if target.policy == "fully_trusted" and not trusted_fixture:
        raise ValueError(
            "fully_trusted in-process extraction is permitted only for a trusted, bounded "
            "fixture (pass trusted_fixture=True for the committed M4.1b control fixtures); "
            "arbitrary/fuzzed archives must use the 'data' filter, or a container-isolated "
            "path for fully_trusted fuzzing"
        )
    archive = build_tar(case)
    lock = target.lock
    with disposable_sandbox(sentinels) as sandbox:
        sandbox.archive_path.write_bytes(archive)
        before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
        references, extractions, execution = _extract_in_process(
            target, sandbox.archive_path, sandbox.extraction_root, case
        )
        after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
        trace = _build_trace(
            before,
            after,
            references,
            extractions,
            execution.status,
            sandbox.root,
            sandbox.extraction_root,
        )
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
    return PythonTarfileEffectRun(EffectRunResult(base, trace), lock)
