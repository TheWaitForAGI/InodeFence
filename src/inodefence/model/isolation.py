"""Concrete container policy and recorded runtime facts, never security novelty."""

import re
from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class ResourcePolicy:
    """Per-container bounds, not a volume quota; units are bytes/counts."""

    memory_bytes: int = 512 * 1024 * 1024
    pids: int = 64
    open_files: int = 1024
    file_size_bytes: int = 64 * 1024 * 1024
    tmpfs_bytes: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class ArtifactDigest:
    name: str
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", self.name):
            raise ValueError("artifact requires a stable name")
        if not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("artifact requires lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class IsolationPolicy:
    """Research-relevant v1 policy, independent of a container's allocated identity.

    Only the implemented default-deny namespace/view policies are supported.
    Mutable tags, volume names, temporary paths, PIDs and timestamps are excluded.
    Resources and content image identity may vary through explicit binding.
    """

    image_id: str
    uid: int
    gid: int
    resources: ResourcePolicy = ResourcePolicy()
    implementation_id: str = "docker-volume-subpath-v1"
    filesystem_view: str = "current-run-volume-subpath-same-path-v1"
    network_policy: str = "none"
    rootfs_mode: str = "read-only"
    cap_drop: tuple[str, ...] = ("ALL",)
    no_new_privileges: bool = True
    pid_namespace: str = "private"
    ipc_namespace: str = "private"
    cgroup_namespace: str = "private"
    environment_policy: str = "image-cleared-path-lang-v1"
    shm_bytes: int = 16 * 1024 * 1024
    capture_bytes_per_stream: int = 1024 * 1024
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.image_id, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", self.image_id
        ):
            raise ValueError("policy requires immutable local image ID")
        for name in ("uid", "gid", "shm_bytes", "capture_bytes_per_stream"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.resources, ResourcePolicy):
            raise ValueError("policy requires immutable ResourcePolicy")
        if not isinstance(self.implementation_id, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9._-]*", self.implementation_id
        ):
            raise ValueError("implementation requires a stable ID")
        expected = {
            "filesystem_view": "current-run-volume-subpath-same-path-v1",
            "network_policy": "none",
            "rootfs_mode": "read-only",
            "cap_drop": ("ALL",),
            "no_new_privileges": True,
            "pid_namespace": "private",
            "ipc_namespace": "private",
            "cgroup_namespace": "private",
            "environment_policy": "image-cleared-path-lang-v1",
            "schema_version": 1,
        }
        for name, value in expected.items():
            actual = getattr(self, name)
            if actual != value or type(actual) is not type(value):
                raise ValueError(f"unsupported v1 isolation {name}")

    @classmethod
    def from_dict(cls, value: object) -> "IsolationPolicy":
        if not isinstance(value, dict) or set(value) != {field.name for field in fields(cls)}:
            raise ValueError("isolation policy requires all fields and no unknown fields")
        raw = dict(value)
        limits = raw["resources"]
        if not isinstance(limits, dict) or set(limits) != {
            field.name for field in fields(ResourcePolicy)
        }:
            raise ValueError("resource policy requires all fields and no unknown fields")
        raw["resources"] = ResourcePolicy(**limits)
        if not isinstance(raw["cap_drop"], list):
            raise ValueError("cap_drop requires an array")
        raw["cap_drop"] = tuple(raw["cap_drop"])
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class IsolationProvenance:
    """Backend-inspected runtime/image facts and verified image probe digests.

    artifacts are observations, never descriptor expectations. artifact_origin
    records their method; image content/probe code remain trusted mechanisms.
    """

    policy: IsolationPolicy
    runtime_name: str
    runtime_version: str
    runtime_api_version: str
    runtime_os: str
    runtime_architecture: str
    image_architecture: str
    image_repo_digests: tuple[str, ...] = ()
    artifacts: tuple[ArtifactDigest, ...] = ()
    schema_version: int = 2
    artifact_origin: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.policy, IsolationPolicy):
            raise ValueError("isolation provenance requires policy")
        for name in (
            "runtime_name",
            "runtime_version",
            "runtime_api_version",
            "runtime_architecture",
            "image_architecture",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or "\0" in value:
                raise ValueError(f"{name} must be known nonempty text")
        if (
            self.runtime_os != "linux"
            or type(self.schema_version) is not int
            or self.schema_version != 2
        ):
            raise ValueError("isolation provenance requires Linux/schema v2")
        if (
            not isinstance(self.image_repo_digests, tuple)
            or not all(
                isinstance(item, str) and re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", item)
                for item in self.image_repo_digests
            )
            or self.image_repo_digests != tuple(sorted(set(self.image_repo_digests)))
        ):
            raise ValueError("image repo digests require sorted unique immutable identities")
        if (
            not isinstance(self.artifacts, tuple)
            or not all(isinstance(item, ArtifactDigest) for item in self.artifacts)
            or tuple(item.name for item in self.artifacts)
            != tuple(sorted({item.name for item in self.artifacts}))
        ):
            raise ValueError("artifacts require sorted unique typed digests")
        if self.artifact_origin != ("image-identification-v1" if self.artifacts else None):
            raise ValueError("observed artifacts require their image identification origin")
