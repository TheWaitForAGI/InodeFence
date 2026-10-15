"""Bounded N01 historical pair qualification orchestration and raw evidence.

This module owns only the approved N01 experiment schedule and evidence. It
composes the existing builder, mutation API, isolated Node target, observer,
oracle and pair storage without changing their generic semantics.
"""

import os
import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import ClassVar, Protocol

from inodefence.builder import build_tar
from inodefence.evaluation.failure import (
    ArtifactReference,
    CleanupStatus,
    FailureContext,
    FailurePhase,
    failure_record,
    write_failure,
)
from inodefence.evaluation.node_packaging import validate_node_build, validate_node_release
from inodefence.evaluation.pair import PairArm, compare_pair, export_pair
from inodefence.evaluation.storage import publish_bytes, write_record
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ArchiveCase,
    ContractId,
    EntryType,
    ExecutionStatus,
    ObjectType,
    RunResult,
    SnapshotPhase,
    StateChange,
    StateSnapshot,
    ViolationResult,
)
from inodefence.model.isolation import IsolationProvenance
from inodefence.model.provenance import (
    EnvironmentProvenance,
    ExecutionProvenance,
    SourceProvenance,
    TargetProvenance,
)
from inodefence.mutator import MutationOperatorId, MutationPolicy, apply_operator
from inodefence.observer import capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.pipeline import run_case
from inodefence.provenance import capture_environment, capture_source, sentinel_provenance
from inodefence.runtime import SentinelSpec, disposable_sandbox
from inodefence.targets.node_tar import NodeTarTarget

EXPERIMENT_ID = "n01-contained-pair-qualification-v1"
AUTOMATED_TOKEN = "N01_PAIR_AUTOMATED_REPLAY_COMPLETE"
APPROVED_REVIEW_REVISION = "d8827893ed758ee0437820373964d13564727c6d"
APPROVED_CONTRACT_SHA256 = "9fa75405e7f5f26310af0e35052c282ad8de45542f9beffcfb9623536c331205"
CONTRACT_PATH = "docs/research/benchmarks/n01-pair-qualification-contract-v1.md"
NODE_VERSION = "22.22.0"
WORKER_SHA256 = "feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b"
PARENT_CASE_ID = "de8ddc5ca4c15fccb638257bbbe671c4fcc9c707962cb92de6589a09f6418620"
CHILD_CASE_ID = "55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87"
INPUT_TAR_SHA256 = "2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6"
SENTINEL_SHA256 = "caed2ac112733b3f5e3f56d9372f7ce6ba88dfafd57eb58807bb29f16548e36b"
TIMEOUT_SECONDS = 10.0
REPETITIONS = 5
EXPECTED_BUILD_FILES = (
    "Dockerfile",
    "package.json",
    "package-lock.json",
    "worker.cjs",
    "packaging.json",
    "build.json",
)


def _text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError(f"{label} must be nonempty text without NUL")


def _digest(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("expected lowercase SHA-256")
    return value


def _timestamp(value: str) -> None:
    if datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError("timestamp requires a timezone")


class N01Role(StrEnum):
    AFFECTED = "affected"
    FIXED = "fixed"


class N01RunPhase(StrEnum):
    READINESS = "readiness"
    PAIR = "pair"


class N01AttemptStatus(StrEnum):
    COMPLETE = "complete"
    ADMISSION_BLOCKED = "admission_blocked"
    ORACLE_CONTROL_BLOCKED = "oracle_control_blocked"
    READINESS_BLOCKED = "readiness_blocked"
    INFRASTRUCTURE_INVALID = "infrastructure_invalid"


class N01QualificationVerdict(StrEnum):
    AUTOMATED_REPLAY_COMPLETE = AUTOMATED_TOKEN
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class N01FrozenTarget:
    role: N01Role
    tar_version: str
    lock_sha256: str
    package_tarball_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, N01Role):
            raise ValueError("frozen target requires a role")
        _text(self.tar_version, "tar version")
        _digest(self.lock_sha256)
        _digest(self.package_tarball_sha256)


FROZEN_TARGETS = (
    N01FrozenTarget(
        N01Role.AFFECTED,
        "7.5.2",
        "31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243",
        "22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a",
    ),
    N01FrozenTarget(
        N01Role.FIXED,
        "7.5.3",
        "a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24",
        "9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66",
    ),
)


def frozen_target(role: N01Role) -> N01FrozenTarget:
    return next(target for target in FROZEN_TARGETS if target.role == role)


@dataclass(frozen=True, slots=True)
class N01FrozenInput:
    mutation_policy: str
    operator_id: str
    parent_case_id: str
    child_case_id: str
    input_tar_sha256: str
    worker_sha256: str
    sentinel_path: str
    sentinel_sha256: str
    sentinel_mode: int
    timeout_seconds: float

    def __post_init__(self) -> None:
        for value in (
            self.parent_case_id,
            self.child_case_id,
            self.input_tar_sha256,
            self.worker_sha256,
            self.sentinel_sha256,
        ):
            _digest(value)
        if (
            self.mutation_policy != MutationPolicy.M1_PROTECTED_COMPONENTS
            or self.operator_id != MutationOperatorId.MUTATE_LINK_TARGET
            or self.sentinel_path != "outside/sentinel.txt"
            or self.sentinel_mode != 0o600
            or self.timeout_seconds != TIMEOUT_SECONDS
        ):
            raise ValueError("unsupported N01 frozen input")


FROZEN_INPUT = N01FrozenInput(
    MutationPolicy.M1_PROTECTED_COMPONENTS,
    MutationOperatorId.MUTATE_LINK_TARGET,
    PARENT_CASE_ID,
    CHILD_CASE_ID,
    INPUT_TAR_SHA256,
    WORKER_SHA256,
    "outside/sentinel.txt",
    SENTINEL_SHA256,
    0o600,
    TIMEOUT_SECONDS,
)


@dataclass(frozen=True, slots=True)
class N01ArtifactReference:
    path: str
    sha256: str

    def __post_init__(self) -> None:
        _text(self.path, "artifact path")
        path = PurePosixPath(self.path)
        if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
            raise ValueError("artifact path must be canonical and relative")
        _digest(self.sha256)


@dataclass(frozen=True, slots=True)
class N01BuildFile:
    name: str
    content: bytes

    def __post_init__(self) -> None:
        if self.name not in EXPECTED_BUILD_FILES or not isinstance(self.content, bytes):
            raise ValueError("N01 build input requires one exact context file")


@dataclass(frozen=True, slots=True)
class N01BuildContext:
    role: N01Role
    files: tuple[N01BuildFile, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.role, N01Role) or tuple(item.name for item in self.files) != (
            EXPECTED_BUILD_FILES
        ):
            raise ValueError("N01 build context requires all exact files in canonical order")


@dataclass(frozen=True, slots=True)
class N01AdmissionRecord:
    role: N01Role
    image_id: str
    target: TargetProvenance
    isolation: IsolationProvenance
    packaging: N01ArtifactReference
    build: N01ArtifactReference
    admitted_at: str

    def __post_init__(self) -> None:
        expected = frozen_target(self.role)
        if (
            not isinstance(self.target, TargetProvenance)
            or not isinstance(self.isolation, IsolationProvenance)
            or self.image_id != self.isolation.policy.image_id
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id) is None
            or self.target.target_id != "node-tar-strict"
            or self.target.target_version != f"node={NODE_VERSION};tar={expected.tar_version}"
            or self.target.timeout_seconds != TIMEOUT_SECONDS
            or self.isolation.policy.uid != 1000
            or self.isolation.policy.gid != 1000
        ):
            raise ValueError("historical target admission differs from the frozen identity")
        observed = {artifact.name: artifact.sha256 for artifact in self.isolation.artifacts}
        if observed != {
            "node-tar-package-lock": expected.lock_sha256,
            "node-tar-worker": WORKER_SHA256,
        }:
            raise ValueError("historical image artifact identity differs from the frozen pair")
        _timestamp(self.admitted_at)


@dataclass(frozen=True, slots=True)
class N01OracleControlRecord:
    control_id: str
    before: StateSnapshot
    after: StateSnapshot
    changes: tuple[StateChange, ...]
    violations: tuple[ViolationResult, ...]
    runtime_root_absent_after_return: bool

    def __post_init__(self) -> None:
        if self.control_id not in ("unchanged-negative", "harness-hardlink-positive"):
            raise ValueError("unsupported oracle control")
        if (
            self.before.phase != SnapshotPhase.BEFORE
            or self.after.phase != SnapshotPhase.AFTER
            or self.before.sandbox_root != self.after.sandbox_root
            or self.before.protected_paths != self.after.protected_paths
            or self.changes != compare_states(self.before, self.after)
            or self.violations != evaluate_contracts(self.before, self.after)
            or type(self.runtime_root_absent_after_return) is not bool
        ):
            raise ValueError("oracle control evidence is inconsistent")


@dataclass(frozen=True, slots=True)
class N01RunRecord:
    run_id: str
    phase: N01RunPhase
    role: N01Role
    execution_index: int
    seed_index: int | None
    repetition: int | None
    schedule_position: int | None
    arm: PairArm
    runtime_root_absent_after_return: bool
    recorded_at: str

    def __post_init__(self) -> None:
        _text(self.run_id, "run ID")
        if (
            not isinstance(self.phase, N01RunPhase)
            or not isinstance(self.role, N01Role)
            or type(self.execution_index) is not int
            or self.execution_index < 0
            or not isinstance(self.arm, PairArm)
            or type(self.runtime_root_absent_after_return) is not bool
        ):
            raise ValueError("invalid N01 run record")
        if self.phase == N01RunPhase.READINESS:
            if (
                type(self.seed_index) is not int
                or not 0 <= self.seed_index < 4
                or self.repetition is not None
                or self.schedule_position is not None
            ):
                raise ValueError("readiness run requires one benign seed index")
        elif (
            self.seed_index is not None
            or type(self.repetition) is not int
            or not 0 <= self.repetition < REPETITIONS
            or type(self.schedule_position) is not int
            or self.schedule_position not in (0, 1)
        ):
            raise ValueError("pair run requires repetition and schedule position")
        _timestamp(self.recorded_at)


@dataclass(frozen=True, slots=True)
class N01ScheduleEntry:
    repetition: int
    order: tuple[N01Role, N01Role]

    def __post_init__(self) -> None:
        if (
            type(self.repetition) is not int
            or not 0 <= self.repetition < REPETITIONS
            or set(self.order) != set(N01Role)
        ):
            raise ValueError("invalid N01 counterbalanced schedule entry")


PAIR_SCHEDULE = tuple(
    N01ScheduleEntry(
        repetition,
        (N01Role.AFFECTED, N01Role.FIXED)
        if repetition % 2 == 0
        else (N01Role.FIXED, N01Role.AFFECTED),
    )
    for repetition in range(REPETITIONS)
)


@dataclass(frozen=True, slots=True)
class N01PairReference:
    repetition: int
    order: tuple[N01Role, N01Role]
    affected_run: N01ArtifactReference
    fixed_run: N01ArtifactReference
    comparison: N01ArtifactReference

    def __post_init__(self) -> None:
        if N01ScheduleEntry(self.repetition, self.order) != PAIR_SCHEDULE[self.repetition]:
            raise ValueError("pair reference differs from the frozen schedule")


@dataclass(frozen=True, slots=True)
class N01RawManifest:
    serialization_schema: ClassVar[int] = 1

    experiment_id: str
    approved_review_revision: str
    contract: N01ArtifactReference
    source: SourceProvenance
    environment: EnvironmentProvenance
    frozen_input: N01FrozenInput
    frozen_targets: tuple[N01FrozenTarget, N01FrozenTarget]
    schedule: tuple[N01ScheduleEntry, ...]
    build_files: tuple[N01ArtifactReference, ...]
    admissions: tuple[N01ArtifactReference, ...]
    oracle_controls: tuple[N01ArtifactReference, ...]
    readiness_runs: tuple[N01ArtifactReference, ...]
    pair_runs: tuple[N01ArtifactReference, ...]
    pairs: tuple[N01PairReference, ...]
    failures: tuple[N01ArtifactReference, ...]
    attempt_status: N01AttemptStatus
    declared_verdict: N01QualificationVerdict
    extractions_started: int
    extractions_completed: int
    started_at: str
    completed_at: str
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.experiment_id != EXPERIMENT_ID
            or self.approved_review_revision != APPROVED_REVIEW_REVISION
            or self.contract.sha256 != APPROVED_CONTRACT_SHA256
            or self.frozen_input != FROZEN_INPUT
            or self.frozen_targets != FROZEN_TARGETS
            or self.schedule != PAIR_SCHEDULE
            or not isinstance(self.attempt_status, N01AttemptStatus)
            or not isinstance(self.declared_verdict, N01QualificationVerdict)
        ):
            raise ValueError("manifest differs from the approved N01 contract")
        for value in (self.extractions_started, self.extractions_completed):
            if type(value) is not int or not 0 <= value <= 18:
                raise ValueError("N01 extraction count exceeds the approved budget")
        if self.extractions_completed > self.extractions_started:
            raise ValueError("completed extraction count exceeds starts")
        for references in (
            self.build_files,
            self.admissions,
            self.oracle_controls,
            self.readiness_runs,
            self.pair_runs,
            self.failures,
        ):
            if not isinstance(references, tuple) or not all(
                isinstance(item, N01ArtifactReference) for item in references
            ):
                raise ValueError("manifest artifact references must be immutable")
        paths = [
            self.contract.path,
            *(item.path for item in self.build_files),
            *(item.path for item in self.admissions),
            *(item.path for item in self.oracle_controls),
            *(item.path for item in self.readiness_runs),
            *(item.path for item in self.pair_runs),
            *(item.comparison.path for item in self.pairs),
            *(item.path for item in self.failures),
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest artifact paths must be unique")
        if not isinstance(self.source, SourceProvenance) or not isinstance(
            self.environment, EnvironmentProvenance
        ):
            raise ValueError("manifest requires source and environment provenance")
        if not isinstance(self.diagnostics, tuple) or not all(
            isinstance(item, str) and item for item in self.diagnostics
        ):
            raise ValueError("manifest diagnostics must be immutable nonempty text")
        _timestamp(self.started_at)
        _timestamp(self.completed_at)


@dataclass(frozen=True, slots=True)
class N01RunOutcome:
    manifest: N01RawManifest
    manifest_sha256: str


class HistoricalTarget(Protocol):
    @property
    def invocation(self) -> object: ...

    @property
    def provenance(self) -> TargetProvenance: ...

    def capture_isolation(self) -> IsolationProvenance: ...


class _ScriptedRandom(random.Random):
    def __init__(self) -> None:
        super().__init__(0)
        self._choices = iter((1, False, False, "../", "/", "outside", "sentinel.txt"))
        self._ranges = iter((2,))

    def choice(self, seq: Sequence):
        value = next(self._choices)
        if value not in seq:
            raise ValueError("frozen mutation transcript no longer matches the selected policy")
        return value

    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        value = next(self._ranges)
        permitted = range(0, start) if stop is None else range(start, stop, step)
        if value not in permitted:
            raise ValueError("frozen mutation range transcript is invalid")
        return value


def reconstruct_n01_case() -> ArchiveCase:
    """Reconstruct and verify the frozen case through the versioned mutation API."""
    parent = minimal_seed_corpus()[2]
    if parent.case_id != PARENT_CASE_ID:
        raise ValueError("N01 parent case identity drift")
    attempt = apply_operator(
        parent,
        _ScriptedRandom(),
        MutationPolicy.M1_PROTECTED_COMPONENTS,
        MutationOperatorId.MUTATE_LINK_TARGET,
    )
    hardlinks = tuple(
        entry for entry in attempt.child_case.entries if entry.entry_type == EntryType.HARDLINK
    )
    if (
        not attempt.applied
        or attempt.child_case.case_id != CHILD_CASE_ID
        or len(hardlinks) != 1
        or hardlinks[0].link_target != "../outside/sentinel.txt"
        or sha256(build_tar(attempt.child_case)).hexdigest() != INPUT_TAR_SHA256
    ):
        raise ValueError("N01 child case/TAR identity drift")
    return attempt.child_case


def _reference(root: Path, path: Path, digest: str) -> N01ArtifactReference:
    return N01ArtifactReference(path.relative_to(root).as_posix(), digest)


def _publish_contract(root: Path, repository: Path) -> N01ArtifactReference:
    content = (repository / CONTRACT_PATH).read_bytes()
    if sha256(content).hexdigest() != APPROVED_CONTRACT_SHA256:
        raise ValueError("approved N01 contract bytes changed")
    path = root / "contract" / "n01-pair-qualification-contract-v1.md"
    return _reference(root, path, publish_bytes(path, content))


def _publish_build_context(
    root: Path,
    context: N01BuildContext,
    source: SourceProvenance,
    retained_references: list[N01ArtifactReference],
) -> tuple[dict, dict]:
    directory = root / "build" / context.role.value
    directory.mkdir(parents=True, exist_ok=False)
    references = []
    for item in context.files:
        path = directory / item.name
        references.append(_reference(root, path, publish_bytes(path, item.content)))
    retained_references.extend(references)
    packaging = validate_node_release(directory)
    build = validate_node_build(directory)
    expected = frozen_target(context.role)
    if (
        packaging["tar_version"] != expected.tar_version
        or packaging["node_version"] != NODE_VERSION
        or packaging["files_sha256"]["package-lock.json"] != expected.lock_sha256
        or packaging["files_sha256"]["worker.cjs"] != WORKER_SHA256
        or build["tar_version"] != expected.tar_version
        or packaging["source"] != {"revision": source.revision, "dirty": source.dirty}
    ):
        raise ValueError("historical build context differs from frozen source/identity")
    return packaging, build


def admit_historical_target(
    role: N01Role,
    target: HistoricalTarget,
    packaging_ref: N01ArtifactReference,
    build_ref: N01ArtifactReference,
    build: dict,
) -> N01AdmissionRecord:
    """Metadata-only admission. No archive bytes or archive command are accepted."""
    invocation = target.invocation
    expected = frozen_target(role)
    if (
        not isinstance(invocation, NodeTarTarget)
        or invocation.image_id != build["image_id"]
        or invocation.node_version != NODE_VERSION
        or invocation.tar_version != expected.tar_version
        or invocation.worker_sha256 != WORKER_SHA256
        or invocation.package_lock_sha256 != expected.lock_sha256
        or invocation.timeout_seconds != TIMEOUT_SECONDS
    ):
        raise ValueError("historical target metadata did not match its exact admitted build")
    isolation = target.capture_isolation()
    if isolation.image_architecture != build["image_architecture"]:
        raise ValueError("historical image architecture differs from its build record")
    return N01AdmissionRecord(
        role,
        invocation.image_id,
        target.provenance,
        isolation,
        packaging_ref,
        build_ref,
        datetime.now(UTC).isoformat(),
    )


def _oracle_control(create_alias: bool) -> N01OracleControlRecord:
    retained: tuple[
        StateSnapshot,
        StateSnapshot,
        tuple[StateChange, ...],
        tuple[ViolationResult, ...],
    ]
    with disposable_sandbox() as sandbox:
        before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
        if create_alias:
            os.link(
                sandbox.root / "outside" / "sentinel.txt",
                sandbox.extraction_root / "control-alias",
            )
        after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
        retained = before, after, compare_states(before, after), evaluate_contracts(before, after)
        root = sandbox.root
    return N01OracleControlRecord(
        "harness-hardlink-positive" if create_alias else "unchanged-negative",
        *retained,
        not root.exists(),
    )


def _violated(result: RunResult, contract: ContractId) -> bool:
    return next(item.violated for item in result.violations if item.contract_id == contract)


def _archive_unchanged(result: RunResult) -> bool:
    return result.before.get("archive/input.tar") == result.after.get("archive/input.tar")


def _readiness_passes(records: Sequence[N01RunRecord]) -> bool:
    if len(records) != 8:
        return False
    for record in records:
        result = record.arm.result
        if record.seed_index is None or not (
            result.execution.succeeded
            and not any(verdict.violated for verdict in result.violations)
            and _archive_unchanged(result)
            and record.runtime_root_absent_after_return
        ):
            return False
        if record.seed_index == 0:
            file = result.after.get("extract/a.txt")
            if file is None or file.content_digest != sha256(b"hello inodefence").hexdigest():
                return False
        elif record.seed_index == 1:
            directory = result.after.get("extract/dir")
            file = result.after.get("extract/dir/a.txt")
            if (
                directory is None
                or directory.object_type != ObjectType.DIRECTORY
                or file is None
                or file.content_digest != sha256(b"hello inodefence").hexdigest()
            ):
                return False
        elif record.seed_index == 2:
            first = result.after.get("extract/a.txt")
            second = result.after.get("extract/b.txt")
            if first is None or second is None or first.identity != second.identity:
                return False
        else:
            link = result.after.get("extract/b.txt")
            if (
                link is None
                or link.object_type != ObjectType.SYMLINK
                or link.symlink_target != "a.txt"
            ):
                return False
    return True


def _runner_pair_verdict(records: Sequence[N01RunRecord]) -> N01QualificationVerdict:
    if len(records) != 10:
        return N01QualificationVerdict.INCONCLUSIVE
    affected = [record.arm.result for record in records if record.role == N01Role.AFFECTED]
    fixed = [record.arm.result for record in records if record.role == N01Role.FIXED]
    if len(affected) != 5 or len(fixed) != 5:
        return N01QualificationVerdict.INCONCLUSIVE

    def affected_result_passes(result: RunResult) -> bool:
        alias = result.after.get("extract/b.txt")
        sentinel = result.after.get("outside/sentinel.txt")
        return (
            result.execution.succeeded
            and alias is not None
            and sentinel is not None
            and alias.identity == sentinel.identity
            and _violated(result, ContractId.C1)
            and _violated(result, ContractId.C2)
            and not _violated(result, ContractId.C0)
            and _archive_unchanged(result)
        )

    def fixed_result_passes(result: RunResult) -> bool:
        alias = result.after.get("extract/b.txt")
        sentinel = result.after.get("outside/sentinel.txt")
        return (
            result.execution.status == ExecutionStatus.REJECTED
            and not _violated(result, ContractId.C0)
            and not _violated(result, ContractId.C1)
            and not _violated(result, ContractId.C2)
            and (alias is None or sentinel is None or alias.identity != sentinel.identity)
            and _archive_unchanged(result)
        )

    affected_ok = all(affected_result_passes(result) for result in affected)
    fixed_ok = all(fixed_result_passes(result) for result in fixed)
    return (
        N01QualificationVerdict.AUTOMATED_REPLAY_COMPLETE
        if affected_ok and fixed_ok
        else N01QualificationVerdict.FAIL
    )


def _run_record(
    root: Path,
    *,
    case: ArchiveCase,
    target: HistoricalTarget,
    provenance: ExecutionProvenance,
    phase: N01RunPhase,
    role: N01Role,
    execution_index: int,
    seed_index: int | None,
    repetition: int | None,
    schedule_position: int | None,
    execute_case: Callable[..., RunResult],
) -> tuple[N01RunRecord, N01ArtifactReference]:
    result = execute_case(case, target, sentinels=(SentinelSpec(),))
    record = N01RunRecord(
        f"{phase.value}-{execution_index:02d}-{role.value}",
        phase,
        role,
        execution_index,
        seed_index,
        repetition,
        schedule_position,
        PairArm(provenance, result),
        not Path(result.after.sandbox_root).exists(),
        datetime.now(UTC).isoformat(),
    )
    path = root / "runs" / f"{record.run_id}.json"
    return record, _reference(root, path, write_record(path, record))


def run_n01_qualification(
    evidence_root: Path,
    targets: tuple[HistoricalTarget, HistoricalTarget]
    | Callable[[], tuple[HistoricalTarget, HistoricalTarget]],
    build_contexts: tuple[N01BuildContext, N01BuildContext],
    *,
    repository: Path,
    source: SourceProvenance | None = None,
    environment: EnvironmentProvenance | None = None,
    execute_case: Callable[..., RunResult] = run_case,
) -> N01RunOutcome:
    """Run the single approved attempt and always publish a terminal raw manifest.

    Valid target outcomes are published before any expected-outcome decision.
    Infrastructure exceptions stop further extraction and are never converted to
    a target status or nonviolation.
    """
    if (
        not evidence_root.is_absolute()
        or evidence_root.is_relative_to(repository)
        or evidence_root.exists()
        or evidence_root.is_symlink()
    ):
        raise ValueError("evidence root must be a new absolute path outside the source tree")
    if tuple(context.role for context in build_contexts) != tuple(N01Role):
        raise ValueError("build contexts must be affected then fixed")
    evidence_root.mkdir(parents=True, exist_ok=False)
    started_at = datetime.now(UTC).isoformat()
    captured_source = capture_source(repository) if source is None else source
    captured_environment = capture_environment() if environment is None else environment
    references: dict[str, list] = {
        "build": [],
        "admission": [],
        "controls": [],
        "readiness": [],
        "pair_runs": [],
        "pairs": [],
        "failures": [],
    }
    diagnostics: list[str] = []
    extractions_started = 0
    extractions_completed = 0
    status = N01AttemptStatus.ADMISSION_BLOCKED
    verdict = N01QualificationVerdict.INCONCLUSIVE
    current_phase = FailurePhase.SETUP
    current_target: TargetProvenance | None = None
    contract_ref = _publish_contract(evidence_root, repository)
    try:
        if captured_source.revision is None or captured_source.dirty is not False:
            raise ValueError("N01 execution requires an available clean source revision")
        reconstruct_n01_case()
        build_records: dict[N01Role, dict] = {}
        build_refs: dict[N01Role, tuple[N01ArtifactReference, N01ArtifactReference]] = {}
        for context in build_contexts:
            current_phase = FailurePhase.BUILD
            _, build = _publish_build_context(
                evidence_root,
                context,
                captured_source,
                references["build"],
            )
            build_records[context.role] = build
            role_refs = tuple(
                item
                for item in references["build"]
                if item.path.startswith(f"build/{context.role.value}/")
            )
            by_name = {Path(item.path).name: item for item in role_refs}
            build_refs[context.role] = by_name["packaging.json"], by_name["build.json"]
        current_phase = FailurePhase.QUALIFICATION
        resolved_targets = targets() if callable(targets) else targets
        if len(resolved_targets) != 2:
            raise ValueError("N01 requires exactly two historical targets")
        admissions: dict[N01Role, N01AdmissionRecord] = {}
        for role, target in zip(N01Role, resolved_targets, strict=True):
            current_phase = FailurePhase.QUALIFICATION
            current_target = target.provenance
            packaging_ref, build_ref = build_refs[role]
            admission = admit_historical_target(
                role, target, packaging_ref, build_ref, build_records[role]
            )
            path = evidence_root / "admission" / f"{role.value}.json"
            reference = _reference(evidence_root, path, write_record(path, admission))
            references["admission"].append(reference)
            admissions[role] = admission
        status = N01AttemptStatus.ORACLE_CONTROL_BLOCKED
        controls = (_oracle_control(False), _oracle_control(True))
        for control in controls:
            path = evidence_root / "oracle" / f"{control.control_id}.json"
            references["controls"].append(
                _reference(evidence_root, path, write_record(path, control))
            )
        negative, positive = controls
        positive_contracts = {item.contract_id: item.violated for item in positive.violations}
        if (
            any(item.violated for item in negative.violations)
            or positive_contracts
            != {
                ContractId.C0: False,
                ContractId.C1: True,
                ContractId.C2: True,
            }
            or not all(item.runtime_root_absent_after_return for item in controls)
        ):
            diagnostics.append("oracle controls did not reproduce the frozen negative/positive")
        else:
            status = N01AttemptStatus.READINESS_BLOCKED
            provenance = {
                role: ExecutionProvenance(
                    captured_source,
                    captured_environment,
                    admissions[role].target,
                    sentinel_provenance((SentinelSpec(),)),
                    admissions[role].isolation,
                )
                for role in N01Role
            }
            readiness_records = []
            for role, target in zip(N01Role, resolved_targets, strict=True):
                current_target = target.provenance
                for seed_index, case in enumerate(minimal_seed_corpus()):
                    current_phase = FailurePhase.EXECUTION
                    extractions_started += 1
                    record, reference = _run_record(
                        evidence_root,
                        case=case,
                        target=target,
                        provenance=provenance[role],
                        phase=N01RunPhase.READINESS,
                        role=role,
                        execution_index=extractions_started - 1,
                        seed_index=seed_index,
                        repetition=None,
                        schedule_position=None,
                        execute_case=execute_case,
                    )
                    extractions_completed += 1
                    readiness_records.append(record)
                    references["readiness"].append(reference)
            if not _readiness_passes(readiness_records):
                diagnostics.append("eight-run benign readiness did not pass; pair phase not run")
            else:
                case = reconstruct_n01_case()
                pair_records = []
                for schedule in PAIR_SCHEDULE:
                    by_role: dict[N01Role, tuple[N01RunRecord, N01ArtifactReference]] = {}
                    for position, role in enumerate(schedule.order):
                        target = resolved_targets[tuple(N01Role).index(role)]
                        current_target = target.provenance
                        current_phase = FailurePhase.EXECUTION
                        extractions_started += 1
                        record, reference = _run_record(
                            evidence_root,
                            case=case,
                            target=target,
                            provenance=provenance[role],
                            phase=N01RunPhase.PAIR,
                            role=role,
                            execution_index=extractions_started - 1,
                            seed_index=None,
                            repetition=schedule.repetition,
                            schedule_position=position,
                            execute_case=execute_case,
                        )
                        extractions_completed += 1
                        pair_records.append(record)
                        references["pair_runs"].append(reference)
                        by_role[role] = record, reference
                    comparison = compare_pair(
                        case,
                        by_role[N01Role.AFFECTED][0].arm,
                        by_role[N01Role.FIXED][0].arm,
                    )
                    pair_path = evidence_root / "pairs" / f"repetition-{schedule.repetition}.json"
                    pair_ref = _reference(
                        evidence_root, pair_path, export_pair(comparison, pair_path)
                    )
                    references["pairs"].append(
                        N01PairReference(
                            schedule.repetition,
                            schedule.order,
                            by_role[N01Role.AFFECTED][1],
                            by_role[N01Role.FIXED][1],
                            pair_ref,
                        )
                    )
                status = N01AttemptStatus.COMPLETE
                verdict = _runner_pair_verdict(pair_records)
    except Exception as error:
        status = N01AttemptStatus.INFRASTRUCTURE_INVALID
        verdict = N01QualificationVerdict.INCONCLUSIVE
        diagnostics.append(f"{type(error).__module__}.{type(error).__qualname__}: {error}")
        context = FailureContext(
            "n01-attempt-v1",
            EXPERIMENT_ID,
            captured_source,
            current_target,
            extractions_started - 1 if extractions_started else None,
            current_phase,
            last_fully_completed_step=(
                extractions_completed - 1 if extractions_completed else None
            ),
            diagnostics=(diagnostics[-1],),
            cleanup_status=CleanupStatus.UNKNOWN,
            artifacts=tuple(
                ArtifactReference(item.path, item.sha256)
                for item in references["build"] + references["admission"]
            ),
        )
        path = evidence_root / "failures" / "infrastructure-invalid.json"
        references["failures"].append(
            _reference(
                evidence_root,
                path,
                write_failure(path, failure_record(error, context)),
            )
        )
    manifest = N01RawManifest(
        EXPERIMENT_ID,
        APPROVED_REVIEW_REVISION,
        contract_ref,
        captured_source,
        captured_environment,
        FROZEN_INPUT,
        FROZEN_TARGETS,
        PAIR_SCHEDULE,
        tuple(references["build"]),
        tuple(references["admission"]),
        tuple(references["controls"]),
        tuple(references["readiness"]),
        tuple(references["pair_runs"]),
        tuple(references["pairs"]),
        tuple(references["failures"]),
        status,
        verdict,
        extractions_started,
        extractions_completed,
        started_at,
        datetime.now(UTC).isoformat(),
        tuple(diagnostics),
    )
    path = evidence_root / "raw-manifest.json"
    digest = write_record(path, manifest)
    return N01RunOutcome(manifest, digest)
