"""Bounded N04 five-second historical-target preflight; never a fuzzing pilot."""

import math
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Protocol

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.evaluation.failure import (
    ArtifactReference,
    CleanupStatus,
    FailureContext,
    FailurePhase,
    failure_record,
    write_failure,
)
from inodefence.evaluation.node_packaging import (
    NODE_VERSION,
    validate_node_build,
    validate_node_release,
)
from inodefence.evaluation.pair import PairArm
from inodefence.evaluation.storage import publish_bytes, write_record
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ContractId,
    ObjectType,
    RunResult,
    SnapshotPhase,
    StateChange,
    StateSnapshot,
    ViolationResult,
)
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance
from inodefence.model.provenance import (
    EnvironmentProvenance,
    ExecutionProvenance,
    SourceProvenance,
    TargetProvenance,
)
from inodefence.observer import capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.pipeline import run_case
from inodefence.provenance import capture_environment, capture_source, sentinel_provenance
from inodefence.runtime import SentinelSpec, disposable_sandbox
from inodefence.targets.isolated import IsolatedTarget
from inodefence.targets.node_tar import NodeTarTarget

EXPERIMENT_ID = "n04-node-tar-five-second-preflight-v1"
ATTEMPT_ID = "n04-five-second-preflight-20261016T130000Z"
EVIDENCE_ROOT = Path("/var/lib/inodefence/evidence/n04-five-second-preflight-20261016T130000Z")
CONTRACT_PATH = "docs/research/benchmarks/n04-five-second-preflight-task-contract-v1.md"
TIMEOUT_SECONDS = 5.0
MAX_WALL_SECONDS = 30 * 60
HOST_CLEANUP_RESERVE_SECONDS = 5 * 60
CONTROLLER_FINALIZATION_RESERVE_SECONDS = 130
HOST_LEDGER_ROOT = Path(
    "/Users/choijiwng/Projects/InodeFence-n04-5s-preflight-20261016T130000Z-host-ledger"
)
HOST_SOURCE_WORKTREE = "/Users/choijiwng/Projects/InodeFence-n04-preflight-execution-source"
CONTROLLER_IMAGE_ID = "sha256:8ea6aad0328af475f0060809bf9bf642399edecee818cb9b771eb19ac635ac09"
HOST_BUILD_CONTEXTS = (
    Path("/Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z/build/affected"),
    Path("/Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z/build/fixed"),
)
HOST_PACKAGE_TARBALLS = (
    Path("/Users/choijiwng/Projects/InodeFence-n04-package-inputs-20261017/tar-7.5.2.tgz"),
    Path("/Users/choijiwng/Projects/InodeFence-n04-package-inputs-20261017/tar-7.5.3.tgz"),
)
RUNTIME_VOLUME_NAME = "inodefence-n04-preflight-runtime-20261016T130000Z"
WORKER_SHA256 = "feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b"
SENTINEL_SHA256 = "caed2ac112733b3f5e3f56d9372f7ce6ba88dfafd57eb58807bb29f16548e36b"
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


def _digest(value: str, *, prefix: bool = False) -> str:
    pattern = r"sha256:[0-9a-f]{64}" if prefix else r"[0-9a-f]{64}"
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise ValueError("expected immutable SHA-256 identity")
    return value


def _timestamp(value: str) -> None:
    if datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError("timestamp requires a timezone")


class N04PreflightRole(StrEnum):
    AFFECTED = "affected"
    FIXED = "fixed"


class N04PreflightStatus(StrEnum):
    COMPLETE = "complete"
    READINESS_FAILED = "readiness_failed"
    INFRASTRUCTURE_INVALID = "infrastructure_invalid"


class N04PreflightVerdict(StrEnum):
    PASS = "PREFLIGHT_PASS"
    FAIL = "PREFLIGHT_FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class N04FrozenTarget:
    role: N04PreflightRole
    tar_version: str
    image_id: str
    platform_manifest_sha256: str
    package_tarball_sha256: str
    lock_sha256: str
    build_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, N04PreflightRole):
            raise ValueError("frozen target requires a role")
        _text(self.tar_version, "tar version")
        _digest(self.image_id, prefix=True)
        for value in (
            self.platform_manifest_sha256,
            self.package_tarball_sha256,
            self.lock_sha256,
            self.build_sha256,
        ):
            _digest(value)


FROZEN_TARGETS = (
    N04FrozenTarget(
        N04PreflightRole.AFFECTED,
        "7.5.2",
        "sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520",
        "b5ae7f5d2f85f12fa417ecece3e9089001266cc6bf4a997724c225a40ce8b542",
        "22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a",
        "31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243",
        "960b28e0699af5c6ac35709d2d14d7a8818ea8cfed0039f86b3b0217c68997ef",
    ),
    N04FrozenTarget(
        N04PreflightRole.FIXED,
        "7.5.3",
        "sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f",
        "3a1bcf4dffcd21ddc4fa6645980bebd96dceda4ceee0ddfe033abd0d50dd6ee0",
        "9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66",
        "a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24",
        "e6adeae1456771dce3e0d20acb3e231ceefd5e726a4c8bf554fc402f62ac8960",
    ),
)


def frozen_target(role: N04PreflightRole) -> N04FrozenTarget:
    return next(item for item in FROZEN_TARGETS if item.role == role)


@dataclass(frozen=True, slots=True)
class N04ArtifactReference:
    path: str
    sha256: str

    def __post_init__(self) -> None:
        _text(self.path, "artifact path")
        path = PurePosixPath(self.path)
        if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
            raise ValueError("artifact path must be canonical and relative")
        _digest(self.sha256)


@dataclass(frozen=True, slots=True)
class N04BuildFile:
    name: str
    content: bytes

    def __post_init__(self) -> None:
        if self.name not in EXPECTED_BUILD_FILES or not isinstance(self.content, bytes):
            raise ValueError("preflight build input requires one exact context file")


@dataclass(frozen=True, slots=True)
class N04BuildContext:
    role: N04PreflightRole
    files: tuple[N04BuildFile, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.role, N04PreflightRole)
            or tuple(item.name for item in self.files) != EXPECTED_BUILD_FILES
        ):
            raise ValueError("preflight build context requires canonical exact files")


@dataclass(frozen=True, slots=True)
class N04PackageTarball:
    role: N04PreflightRole
    content: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.role, N04PreflightRole) or not isinstance(self.content, bytes):
            raise ValueError("preflight package input requires exact tarball bytes")


@dataclass(frozen=True, slots=True)
class N04ControllerMount:
    mount_type: str
    source: str
    destination: str
    read_write: bool

    def __post_init__(self) -> None:
        for label in ("mount_type", "source", "destination"):
            _text(getattr(self, label), label)
        if self.mount_type not in ("bind", "volume") or type(self.read_write) is not bool:
            raise ValueError("unsupported controller mount")


@dataclass(frozen=True, slots=True)
class N04BrokerImage:
    image_id: str
    operating_system: str
    architecture: str
    repo_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        _digest(self.image_id, prefix=True)
        if self.operating_system != "linux" or self.architecture != "arm64":
            raise ValueError("preflight requires Linux arm64 images")
        if (
            not isinstance(self.repo_digests, tuple)
            or self.repo_digests != tuple(sorted(set(self.repo_digests)))
            or not all(
                isinstance(item, str) and re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", item)
                for item in self.repo_digests
            )
        ):
            raise ValueError("repo digests must be sorted immutable identities")


@dataclass(frozen=True, slots=True)
class N04BrokerAttestation:
    docker_executable: str
    context_name: str
    broker_started_at: str
    daemon_id: str
    daemon_name: str
    daemon_version: str
    daemon_api_version: str
    daemon_os: str
    daemon_architecture: str
    controller_id: str
    controller_image_id: str
    controller_created_at: str
    controller_running: bool
    controller_privileged: bool
    controller_label: str
    controller_network_mode: str
    controller_readonly_rootfs: bool
    controller_cap_add: tuple[str, ...]
    controller_cap_drop: tuple[str, ...]
    controller_security_opt: tuple[str, ...]
    controller_device_count: int
    controller_device_request_count: int
    controller_device_cgroup_rule_count: int
    controller_pid_mode: str
    controller_ipc_mode: str
    controller_cgroupns_mode: str
    controller_memory_bytes: int
    controller_memory_swap_bytes: int
    controller_pids_limit: int
    controller_tmpfs: tuple[tuple[str, str], ...]
    controller_mounts: tuple[N04ControllerMount, ...]
    runtime_volume_name: str
    runtime_volume_created_at: str
    runtime_volume_driver: str
    runtime_volume_scope: str
    runtime_volume_label: str
    runtime_volume_options: tuple[tuple[str, str], ...]
    runtime_volume_mountpoint: str
    runtime_volume_container_ids: tuple[str, ...]
    target_images: tuple[N04BrokerImage, N04BrokerImage]
    max_wall_seconds: int

    def __post_init__(self) -> None:
        for label in (
            "docker_executable",
            "context_name",
            "broker_started_at",
            "daemon_id",
            "daemon_name",
            "daemon_version",
            "daemon_api_version",
            "controller_id",
            "controller_created_at",
            "controller_label",
            "controller_network_mode",
            "controller_ipc_mode",
            "controller_cgroupns_mode",
            "runtime_volume_name",
            "runtime_volume_created_at",
            "runtime_volume_driver",
            "runtime_volume_scope",
            "runtime_volume_label",
            "runtime_volume_mountpoint",
        ):
            _text(getattr(self, label), label)
        _digest(self.controller_id)
        _digest(self.controller_image_id, prefix=True)
        if any(
            type(value) is not int
            for value in (
                self.controller_device_count,
                self.controller_device_request_count,
                self.controller_device_cgroup_rule_count,
                self.controller_memory_bytes,
                self.controller_memory_swap_bytes,
                self.controller_pids_limit,
                self.max_wall_seconds,
            )
        ):
            raise ValueError("controller resource facts require integers")
        if (
            self.context_name != "orbstack"
            or self.daemon_os != "linux"
            or self.daemon_architecture != "arm64"
            or self.controller_running is not True
            or self.controller_privileged is not False
            or self.controller_image_id != CONTROLLER_IMAGE_ID
            or self.controller_label != "v1"
            or self.controller_network_mode != "none"
            or self.controller_readonly_rootfs is not True
            or self.controller_cap_add
            or self.controller_cap_drop != ("ALL",)
            or self.controller_security_opt != ("no-new-privileges",)
            or self.controller_device_count != 0
            or self.controller_device_request_count != 0
            or self.controller_device_cgroup_rule_count != 0
            or self.controller_pid_mode != ""
            or self.controller_ipc_mode != "private"
            or self.controller_cgroupns_mode != "private"
            or self.controller_memory_bytes != 1024 * 1024 * 1024
            or self.controller_memory_swap_bytes != 1024 * 1024 * 1024
            or self.controller_pids_limit != 256
            or self.controller_tmpfs != (("/tmp", "rw,nosuid,nodev,size=256m"),)
            or self.runtime_volume_name != RUNTIME_VOLUME_NAME
            or self.runtime_volume_driver != "local"
            or self.runtime_volume_scope != "local"
            or self.runtime_volume_label != "v1"
            or self.runtime_volume_options
            or self.runtime_volume_container_ids != (self.controller_id,)
            or self.max_wall_seconds != MAX_WALL_SECONDS
            or tuple(item.image_id for item in self.target_images)
            != tuple(item.image_id for item in FROZEN_TARGETS)
        ):
            raise ValueError("broker identity differs from the authorized preflight")
        controller_created = datetime.fromisoformat(self.controller_created_at)
        broker_started = datetime.fromisoformat(self.broker_started_at)
        volume_created = datetime.fromisoformat(self.runtime_volume_created_at)
        if (
            controller_created.utcoffset() is None
            or broker_started.utcoffset() is None
            or volume_created.utcoffset() is None
        ):
            raise ValueError("broker/controller timestamps require timezone")
        controller_age = (broker_started - controller_created).total_seconds()
        volume_age = (broker_started - volume_created).total_seconds()
        if not 0 <= controller_age <= 15 * 60 or not 0 <= volume_age <= 15 * 60:
            raise ValueError("controller/volume is not fresh for this preflight broker invocation")
        if (
            self.controller_cap_add != tuple(sorted(set(self.controller_cap_add)))
            or self.controller_cap_drop != tuple(sorted(set(self.controller_cap_drop)))
            or self.controller_security_opt != tuple(sorted(set(self.controller_security_opt)))
            or self.controller_tmpfs != tuple(sorted(set(self.controller_tmpfs)))
            or self.runtime_volume_options != tuple(sorted(set(self.runtime_volume_options)))
            or self.runtime_volume_container_ids
            != tuple(sorted(set(self.runtime_volume_container_ids)))
        ):
            raise ValueError("controller containment facts must be canonical")
        if self.controller_mounts != tuple(
            sorted(self.controller_mounts, key=lambda item: item.destination)
        ):
            raise ValueError("controller mounts must be sorted")
        destinations = {item.destination: item for item in self.controller_mounts}
        source = destinations.get("/workspaces/InodeFence")
        runtime = destinations.get("/var/lib/inodefence")
        if (
            source is None
            or source.mount_type != "bind"
            or source.source != HOST_SOURCE_WORKTREE
            or source.read_write
            or runtime is None
            or runtime.mount_type != "volume"
            or runtime.source != self.runtime_volume_name
            or not runtime.read_write
            or set(destinations) != {"/workspaces/InodeFence", "/var/lib/inodefence"}
            or any(
                "docker.sock" in item.source or "docker.sock" in item.destination
                for item in self.controller_mounts
            )
        ):
            raise ValueError("controller source/runtime boundary is not authorized")


@dataclass(frozen=True, slots=True)
class N04SeedBinding:
    index: int
    case_id: str
    archive_sha256: str
    builder_format: str = BUILDER_FORMAT

    def __post_init__(self) -> None:
        if type(self.index) is not int or not 0 <= self.index < 4:
            raise ValueError("seed index is outside the frozen corpus")
        _digest(self.case_id)
        _digest(self.archive_sha256)
        if self.builder_format != BUILDER_FORMAT:
            raise ValueError("preflight requires the deterministic USTAR builder")


@dataclass(frozen=True, slots=True)
class N04AdmissionRecord:
    role: N04PreflightRole
    image_id: str
    target: TargetProvenance
    isolation: IsolationProvenance
    packaging: N04ArtifactReference
    build: N04ArtifactReference
    admitted_at: str

    def __post_init__(self) -> None:
        frozen = frozen_target(self.role)
        if (
            not isinstance(self.target, TargetProvenance)
            or not isinstance(self.isolation, IsolationProvenance)
            or self.image_id != frozen.image_id
            or self.image_id != self.isolation.policy.image_id
            or self.target.target_id != "node-tar-strict"
            or self.target.target_version != f"node={NODE_VERSION};tar={frozen.tar_version}"
            or self.target.timeout_seconds != TIMEOUT_SECONDS
            or self.isolation.policy != IsolationPolicy(self.image_id, 1000, 1000)
            or {(item.name, item.sha256) for item in self.isolation.artifacts}
            != {
                ("node-tar-package-lock", frozen.lock_sha256),
                ("node-tar-worker", WORKER_SHA256),
            }
        ):
            raise ValueError("preflight admission differs from the frozen identity")
        _timestamp(self.admitted_at)


@dataclass(frozen=True, slots=True)
class N04OracleControlRecord:
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
class N04ReadinessRecord:
    run_id: str
    role: N04PreflightRole
    execution_index: int
    seed_index: int
    arm: PairArm
    runtime_root_absent_after_return: bool
    recorded_at: str

    def __post_init__(self) -> None:
        _text(self.run_id, "run ID")
        if (
            not isinstance(self.role, N04PreflightRole)
            or type(self.execution_index) is not int
            or not 0 <= self.execution_index < 8
            or type(self.seed_index) is not int
            or not 0 <= self.seed_index < 4
            or not isinstance(self.arm, PairArm)
            or type(self.runtime_root_absent_after_return) is not bool
        ):
            raise ValueError("invalid readiness record")
        _timestamp(self.recorded_at)


@dataclass(frozen=True, slots=True)
class N04RawManifest:
    experiment_id: str
    attempt_id: str
    contract: N04ArtifactReference
    source: SourceProvenance
    environment: EnvironmentProvenance
    broker: N04BrokerAttestation | None
    frozen_targets: tuple[N04FrozenTarget, N04FrozenTarget]
    seeds: tuple[N04SeedBinding, N04SeedBinding, N04SeedBinding, N04SeedBinding]
    package_tarballs: tuple[N04ArtifactReference, ...]
    build_files: tuple[N04ArtifactReference, ...]
    admissions: tuple[N04ArtifactReference, ...]
    oracle_controls: tuple[N04ArtifactReference, ...]
    readiness_runs: tuple[N04ArtifactReference, ...]
    failures: tuple[N04ArtifactReference, ...]
    attempt_status: N04PreflightStatus
    declared_verdict: N04PreflightVerdict
    extractions_started: int
    extractions_completed: int
    started_at: str
    completed_at: str
    elapsed_seconds: float
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.experiment_id != EXPERIMENT_ID
            or self.attempt_id != ATTEMPT_ID
            or self.frozen_targets != FROZEN_TARGETS
            or self.seeds != seed_bindings()
            or not isinstance(self.source, SourceProvenance)
            or not isinstance(self.environment, EnvironmentProvenance)
            or (
                not isinstance(self.broker, N04BrokerAttestation)
                and not (
                    self.broker is None
                    and self.attempt_status == N04PreflightStatus.INFRASTRUCTURE_INVALID
                )
            )
            or not isinstance(self.attempt_status, N04PreflightStatus)
            or not isinstance(self.declared_verdict, N04PreflightVerdict)
        ):
            raise ValueError("manifest differs from the authorized preflight")
        for value in (self.extractions_started, self.extractions_completed):
            if type(value) is not int or not 0 <= value <= 8:
                raise ValueError("preflight extraction count exceeds the approved budget")
        if self.extractions_completed > self.extractions_started:
            raise ValueError("completed extractions exceed starts")
        if (
            type(self.elapsed_seconds) not in (int, float)
            or not math.isfinite(self.elapsed_seconds)
            or not 0 <= self.elapsed_seconds <= MAX_WALL_SECONDS
        ):
            raise ValueError("preflight exceeded its controller wall-clock bound")
        paths = [
            self.contract.path,
            *(item.path for item in self.package_tarballs),
            *(item.path for item in self.build_files),
            *(item.path for item in self.admissions),
            *(item.path for item in self.oracle_controls),
            *(item.path for item in self.readiness_runs),
            *(item.path for item in self.failures),
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest artifact paths must be unique")
        _timestamp(self.started_at)
        _timestamp(self.completed_at)


@dataclass(frozen=True, slots=True)
class N04PreflightOutcome:
    manifest: N04RawManifest
    manifest_sha256: str


class HistoricalTarget(Protocol):
    @property
    def invocation(self) -> object: ...

    @property
    def provenance(self) -> TargetProvenance: ...

    def capture_isolation(self) -> IsolationProvenance: ...


def seed_bindings() -> tuple[N04SeedBinding, N04SeedBinding, N04SeedBinding, N04SeedBinding]:
    values = tuple(
        N04SeedBinding(index, case.case_id, sha256(build_tar(case)).hexdigest())
        for index, case in enumerate(minimal_seed_corpus())
    )
    if len(values) != 4:
        raise ValueError("preflight requires exactly four benign seeds")
    return values  # type: ignore[return-value]


def _reference(root: Path, path: Path, digest: str) -> N04ArtifactReference:
    return N04ArtifactReference(path.relative_to(root).as_posix(), digest)


def _publish_contract(root: Path, repository: Path) -> N04ArtifactReference:
    path = root / "contract" / Path(CONTRACT_PATH).name
    return _reference(root, path, publish_bytes(path, (repository / CONTRACT_PATH).read_bytes()))


def _publish_build_context(
    root: Path,
    context: N04BuildContext,
    repository: Path,
    retained: list[N04ArtifactReference],
) -> tuple[dict, dict]:
    directory = root / "build" / context.role.value
    directory.mkdir(parents=True, exist_ok=False)
    for item in context.files:
        path = directory / item.name
        retained.append(_reference(root, path, publish_bytes(path, item.content)))
    packaging = validate_node_release(directory)
    build = validate_node_build(directory)
    frozen = frozen_target(context.role)
    current_lock = (
        repository
        / "experiments"
        / "benchmarks"
        / "locks"
        / (f"node-tar-{frozen.tar_version}.package-lock.json")
    )
    if (
        packaging["tar_version"] != frozen.tar_version
        or packaging["files_sha256"]["package-lock.json"] != frozen.lock_sha256
        or packaging["files_sha256"]["worker.cjs"] != WORKER_SHA256
        or build["image_id"] != frozen.image_id
        or build["tar_version"] != frozen.tar_version
        or f"exporting manifest sha256:{frozen.platform_manifest_sha256}" not in build["stderr"]
        or sha256((directory / "build.json").read_bytes()).hexdigest() != frozen.build_sha256
        or sha256(current_lock.read_bytes()).hexdigest() != frozen.lock_sha256
        or sha256((repository / "src/inodefence/targets/_node_worker.cjs").read_bytes()).hexdigest()
        != WORKER_SHA256
    ):
        raise ValueError("retained target build differs from the preflight binding")
    return packaging, build


def _publish_package_tarball(
    root: Path,
    package: N04PackageTarball,
) -> N04ArtifactReference:
    frozen = frozen_target(package.role)
    path = root / "packages" / package.role.value / f"tar-{frozen.tar_version}.tgz"
    return _reference(root, path, publish_bytes(path, package.content))


def _admit(
    role: N04PreflightRole,
    target: HistoricalTarget,
    packaging_ref: N04ArtifactReference,
    build_ref: N04ArtifactReference,
    build: dict,
    broker: N04BrokerAttestation | Callable[[], N04BrokerAttestation],
) -> N04AdmissionRecord:
    invocation = target.invocation
    frozen = frozen_target(role)
    if (
        not isinstance(invocation, NodeTarTarget)
        or invocation.image_id != frozen.image_id
        or invocation.image_id != build["image_id"]
        or invocation.node_version != NODE_VERSION
        or invocation.tar_version != frozen.tar_version
        or invocation.worker_sha256 != WORKER_SHA256
        or invocation.package_lock_sha256 != frozen.lock_sha256
        or invocation.timeout_seconds != TIMEOUT_SECONDS
    ):
        raise ValueError("target metadata differs from the five-second preflight")
    isolation = target.capture_isolation()
    broker_image = broker.target_images[tuple(N04PreflightRole).index(role)]
    if (
        isolation.image_architecture != build["image_architecture"]
        or isolation.runtime_version != broker.daemon_version
        or isolation.runtime_api_version != broker.daemon_api_version
        or isolation.runtime_os != broker.daemon_os
        or isolation.runtime_architecture != broker.daemon_architecture
        or isolation.image_architecture != broker_image.architecture
        or isolation.image_repo_digests != broker_image.repo_digests
    ):
        raise ValueError("target runtime/image inspection differs from the host broker")
    return N04AdmissionRecord(
        role,
        invocation.image_id,
        target.provenance,
        isolation,
        packaging_ref,
        build_ref,
        datetime.now(UTC).isoformat(),
    )


def _oracle_control(create_alias: bool) -> N04OracleControlRecord:
    with disposable_sandbox() as sandbox:
        before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
        if create_alias:
            os.link(
                sandbox.root / "outside" / "sentinel.txt",
                sandbox.extraction_root / "control-alias",
            )
        after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
        changes = compare_states(before, after)
        violations = evaluate_contracts(before, after)
        runtime_root = sandbox.root
    return N04OracleControlRecord(
        "harness-hardlink-positive" if create_alias else "unchanged-negative",
        before,
        after,
        changes,
        violations,
        not runtime_root.exists(),
    )


def _archive_unchanged(result: RunResult) -> bool:
    return result.before.get("archive/input.tar") == result.after.get("archive/input.tar")


def benign_output_passes(result: RunResult, seed_index: int) -> bool:
    if result.case != minimal_seed_corpus()[seed_index]:
        return False
    if not result.execution.succeeded or any(item.violated for item in result.violations):
        return False
    if result.execution.timeout_seconds != TIMEOUT_SECONDS or not _archive_unchanged(result):
        return False
    after = result.after
    if seed_index == 0:
        file = after.get("extract/a.txt")
        return file is not None and file.content_digest == sha256(b"hello inodefence").hexdigest()
    if seed_index == 1:
        directory, file = after.get("extract/dir"), after.get("extract/dir/a.txt")
        return (
            directory is not None
            and directory.object_type == ObjectType.DIRECTORY
            and file is not None
            and file.content_digest == sha256(b"hello inodefence").hexdigest()
        )
    if seed_index == 2:
        first, second = after.get("extract/a.txt"), after.get("extract/b.txt")
        return first is not None and second is not None and first.identity == second.identity
    link = after.get("extract/b.txt")
    return (
        link is not None
        and link.object_type == ObjectType.SYMLINK
        and link.symlink_target == "a.txt"
    )


def _controls_pass(controls: Sequence[N04OracleControlRecord]) -> bool:
    if len(controls) != 2 or any(item.violated for item in controls[0].violations):
        return False
    positive = {item.contract_id: item.violated for item in controls[1].violations}
    return positive == {ContractId.C0: False, ContractId.C1: True, ContractId.C2: True} and all(
        item.runtime_root_absent_after_return for item in controls
    )


def run_n04_preflight(
    evidence_root: Path,
    targets: tuple[HistoricalTarget, HistoricalTarget]
    | Callable[[], tuple[HistoricalTarget, HistoricalTarget]],
    build_contexts: tuple[N04BuildContext, N04BuildContext],
    package_tarballs: tuple[N04PackageTarball, N04PackageTarball],
    broker: N04BrokerAttestation | Callable[[], N04BrokerAttestation],
    *,
    repository: Path,
    source: SourceProvenance | None = None,
    environment: EnvironmentProvenance | None = None,
    execute_case: Callable[..., RunResult] = run_case,
    create_control: Callable[[bool], N04OracleControlRecord] = _oracle_control,
) -> N04PreflightOutcome:
    """Run the one authorized preflight and publish a terminal raw manifest."""
    if (
        evidence_root != EVIDENCE_ROOT
        or evidence_root.is_relative_to(repository)
        or evidence_root.exists()
        or evidence_root.is_symlink()
    ):
        raise ValueError("evidence root must be a new absolute path outside source")
    if tuple(item.role for item in build_contexts) != tuple(N04PreflightRole):
        raise ValueError("build contexts must be affected then fixed")
    if tuple(item.role for item in package_tarballs) != tuple(N04PreflightRole):
        raise ValueError("package tarballs must be affected then fixed")
    evidence_root.mkdir(parents=True, exist_ok=False)
    started_monotonic = monotonic()
    started_at = datetime.now(UTC).isoformat()
    captured_source = capture_source(repository) if source is None else source
    captured_environment = capture_environment() if environment is None else environment
    references: dict[str, list[N04ArtifactReference]] = {
        "package": [],
        "build": [],
        "admission": [],
        "controls": [],
        "readiness": [],
        "failures": [],
    }
    diagnostics: list[str] = []
    extractions_started = 0
    extractions_completed = 0
    current_phase = FailurePhase.SETUP
    current_target: TargetProvenance | None = None
    resolved_broker: N04BrokerAttestation | None = None
    status = N04PreflightStatus.INFRASTRUCTURE_INVALID
    verdict = N04PreflightVerdict.INCONCLUSIVE
    contract_ref = _publish_contract(evidence_root, repository)
    try:
        resolved_broker = broker() if callable(broker) else broker
        if not isinstance(resolved_broker, N04BrokerAttestation):
            raise ValueError("preflight broker attestation is unavailable")
        if (
            captured_source.revision is None
            or captured_source.dirty is not False
            or captured_environment.system != "Linux"
            or captured_environment.machine != "aarch64"
        ):
            raise ValueError("preflight requires a clean available Linux aarch64 source revision")
        for package in package_tarballs:
            current_phase = FailurePhase.QUALIFICATION
            reference = _publish_package_tarball(evidence_root, package)
            references["package"].append(reference)
            if reference.sha256 != frozen_target(package.role).package_tarball_sha256:
                raise ValueError("package tarball differs from the frozen SHA-256 identity")
        build_records: dict[N04PreflightRole, dict] = {}
        build_refs: dict[N04PreflightRole, tuple[N04ArtifactReference, N04ArtifactReference]] = {}
        for context in build_contexts:
            current_phase = FailurePhase.BUILD
            _, build = _publish_build_context(
                evidence_root, context, repository, references["build"]
            )
            build_records[context.role] = build
            by_name = {
                Path(item.path).name: item
                for item in references["build"]
                if item.path.startswith(f"build/{context.role.value}/")
            }
            build_refs[context.role] = by_name["packaging.json"], by_name["build.json"]
        resolved_targets = targets() if callable(targets) else targets
        if len(resolved_targets) != 2:
            raise ValueError("preflight requires exactly two historical targets")
        admissions: dict[N04PreflightRole, N04AdmissionRecord] = {}
        for role, target in zip(N04PreflightRole, resolved_targets, strict=True):
            current_phase = FailurePhase.QUALIFICATION
            current_target = target.provenance
            admission = _admit(
                role,
                target,
                *build_refs[role],
                build_records[role],
                resolved_broker,
            )
            path = evidence_root / "admission" / f"{role.value}.json"
            references["admission"].append(
                _reference(evidence_root, path, write_record(path, admission))
            )
            admissions[role] = admission
        controls = []
        current_target = None
        current_phase = FailurePhase.SETUP
        for create_alias in (False, True):
            control = create_control(create_alias)
            path = evidence_root / "oracle" / f"{control.control_id}.json"
            references["controls"].append(
                _reference(evidence_root, path, write_record(path, control))
            )
            controls.append(control)
        if not _controls_pass(controls):
            raise ValueError("oracle controls did not reproduce the frozen negative/positive")
        provenance = {
            role: ExecutionProvenance(
                captured_source,
                captured_environment,
                admissions[role].target,
                sentinel_provenance((SentinelSpec(),)),
                admissions[role].isolation,
            )
            for role in N04PreflightRole
        }
        readiness: list[N04ReadinessRecord] = []
        for role, target in zip(N04PreflightRole, resolved_targets, strict=True):
            current_target = target.provenance
            for seed_index, case in enumerate(minimal_seed_corpus()):
                current_phase = FailurePhase.EXECUTION
                extractions_started += 1
                result = execute_case(case, target, sentinels=(SentinelSpec(),))
                extractions_completed += 1
                record = N04ReadinessRecord(
                    f"readiness-{extractions_started - 1:02d}-{role.value}",
                    role,
                    extractions_started - 1,
                    seed_index,
                    PairArm(provenance[role], result),
                    not Path(result.after.sandbox_root).exists(),
                    datetime.now(UTC).isoformat(),
                )
                path = evidence_root / "runs" / f"{record.run_id}.json"
                references["readiness"].append(
                    _reference(evidence_root, path, write_record(path, record))
                )
                readiness.append(record)
        passed = all(
            benign_output_passes(record.arm.result, record.seed_index)
            and record.runtime_root_absent_after_return
            for record in readiness
        )
        if passed:
            status = N04PreflightStatus.COMPLETE
            verdict = N04PreflightVerdict.PASS
        else:
            status = N04PreflightStatus.READINESS_FAILED
            verdict = N04PreflightVerdict.FAIL
            diagnostics.append("one or more complete benign readiness records failed")
    except Exception as error:
        diagnostics.append(f"{type(error).__module__}.{type(error).__qualname__}: {error}")
        context = FailureContext(
            ATTEMPT_ID,
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
                for item in (
                    [contract_ref]
                    + references["package"]
                    + references["build"]
                    + references["admission"]
                    + references["controls"]
                    + references["readiness"]
                )
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
    elapsed = monotonic() - started_monotonic
    manifest = N04RawManifest(
        EXPERIMENT_ID,
        ATTEMPT_ID,
        contract_ref,
        captured_source,
        captured_environment,
        resolved_broker,
        FROZEN_TARGETS,
        seed_bindings(),
        tuple(references["package"]),
        tuple(references["build"]),
        tuple(references["admission"]),
        tuple(references["controls"]),
        tuple(references["readiness"]),
        tuple(references["failures"]),
        status,
        verdict,
        extractions_started,
        extractions_completed,
        started_at,
        datetime.now(UTC).isoformat(),
        elapsed,
        tuple(diagnostics),
    )
    path = evidence_root / "raw-manifest.json"
    return N04PreflightOutcome(manifest, write_record(path, manifest))


def bind_targets(backend, images: tuple[str, str]) -> tuple[IsolatedTarget, IsolatedTarget]:
    """Construct the exact affected/fixed pair at the predeclared five-second timeout."""
    if images != tuple(item.image_id for item in FROZEN_TARGETS):
        raise ValueError("preflight image order or identity mismatch")
    return (
        NodeTarTarget.bind(backend, images[0], timeout_seconds=TIMEOUT_SECONDS),
        NodeTarTarget.bind(backend, images[1], timeout_seconds=TIMEOUT_SECONDS),
    )
