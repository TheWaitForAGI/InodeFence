"""Read-only admission for the exact Track A pilot and retained N05 evidence.

The caller must obtain ``expected_pilot_authorization_sha256`` and
``trusted_approval_reference`` through a trusted human-controlled approval
channel.  A digest and the record's ``authorized_by`` text preserve a selected
approval binding; neither authenticates a person.  This module reads evidence
only.  It cannot create execution roots, claim campaigns, launch controllers,
or execute targets.
"""

import re
from collections import Counter
from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import ClassVar
from weakref import ReferenceType, ref

import inodefence.evaluation.track_a_exploratory as track_a
from inodefence.evaluation.encoding import decode, json_bytes, read_json
from inodefence.evaluation.failure import ArtifactReference
from inodefence.evaluation.n05_preflight import (
    ATTEMPT_ID as N05_ATTEMPT_ID,
)
from inodefence.evaluation.n05_preflight import (
    MODE_ID as N05_MODE_ID,
)
from inodefence.evaluation.n05_preflight import (
    NODE_VERSION,
    WORKER_SHA256,
    N05AdmissionRecord,
    N05ArtifactReference,
    N05PreflightAuthorization,
    N05PreflightRole,
    N05RawManifest,
    authorization_from_bytes,
)
from inodefence.evaluation.n05_preflight_reader import (
    N05FinalStatus,
    N05IndependentStatus,
    VerifiedN05Preflight,
    read_n05_preflight,
)
from inodefence.evaluation.policy_repeated import PolicyRepetitionPlan
from inodefence.evaluation.storage import read_record
from inodefence.evaluation.verify import VerificationError, _digest, _read_file
from inodefence.feedback import FeedbackProjection
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ContractId, canonical_json
from inodefence.model.provenance import (
    EnvironmentProvenance,
    ExecutionProvenance,
    SentinelProvenance,
    SourceProvenance,
)
from inodefence.mutator import MutationPolicy
from inodefence.provenance import sentinel_provenance
from inodefence.runtime import SentinelSpec

PILOT_AUTHORIZATION_SCOPE = "TRACK_A_FINAL_STATE_4000_PILOT"
PILOT_DECISION = "AUTHORIZE_EXACT_TRACK_A_PILOT"
PILOT_HUMAN_REVIEW_STATEMENT = (
    "I separately authorize exactly the Track A 20-campaign, 4000-execution pilot; "
    "the N05 authorization does not authorize this pilot."
)
TRACK_A_N05_ENVIRONMENT_PROFILE = track_a.ENVIRONMENT_PROFILE
PILOT_RESUME_POLICY = "NONE_NEW_AUTHORIZATION_REQUIRED"
PILOT_STOP_CONDITIONS = (
    "prior-campaign-non-complete",
    "campaign-watchdog",
    "identity-or-admission-failure",
    "cleanup-failure",
)


def _text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError(f"{label} must be nonempty text without NUL")


def _timestamp(value: str) -> None:
    if not isinstance(value, str) or datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError("pilot authorization timestamp requires a timezone")


def _image_digest(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ValueError("expected immutable image SHA-256 identity")


def _absolute_path(value: str, label: str) -> Path:
    _text(value, label)
    path = Path(value)
    if (
        not path.is_absolute()
        or str(path) != value
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise ValueError(f"{label} must be a canonical absolute path")
    return path


def _existing_nonsymlink_file(path: Path, label: str) -> bytes:
    if path.is_symlink() or path.resolve() != path or not path.is_file():
        raise ValueError(f"{label} must be an existing nonsymlink regular file")
    return _read_file(path)


def _existing_nonsymlink_directory(path: Path, label: str) -> None:
    if path.is_symlink() or path.resolve() != path or not path.is_dir():
        raise ValueError(f"{label} must be an existing nonsymlink directory")


class PilotTargetRole(StrEnum):
    AFFECTED = "affected"
    FIXED = "fixed"


@dataclass(frozen=True, slots=True)
class PilotCampaignCell:
    run_id: str
    arm_id: str
    random_seed: int

    def __post_init__(self) -> None:
        for value, label in ((self.run_id, "run ID"), (self.arm_id, "arm ID")):
            _text(value, label)
            if re.fullmatch(r"[A-Za-z0-9._-]+", value) is None:
                raise ValueError(f"{label} requires a stable identifier")
        if type(self.random_seed) is not int or self.random_seed < 0:
            raise ValueError("campaign RNG seed must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class PilotTargetIdentity:
    role: PilotTargetRole
    node_version: str
    tar_version: str
    image_id: str
    platform_manifest_sha256: str
    package_tarball_sha256: str
    lock_sha256: str
    build_sha256: str
    worker_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, PilotTargetRole):
            raise ValueError("pilot target requires an affected/fixed role")
        _text(self.node_version, "Node version")
        _text(self.tar_version, "tar version")
        _image_digest(self.image_id)
        for value in (
            self.platform_manifest_sha256,
            self.package_tarball_sha256,
            self.lock_sha256,
            self.build_sha256,
            self.worker_sha256,
        ):
            _digest(value)


@dataclass(frozen=True, slots=True)
class PilotResourceLimits:
    target_memory_bytes: int
    target_pids: int
    target_open_files: int
    target_file_size_bytes: int
    target_tmpfs_bytes: int
    target_shm_bytes: int
    target_capture_bytes_per_stream: int
    controller_memory_bytes: int
    controller_memory_swap_bytes: int
    controller_pids: int
    controller_tmpfs_bytes: int

    def __post_init__(self) -> None:
        if any(
            type(getattr(self, field)) is not int or getattr(self, field) <= 0
            for field in self.__dataclass_fields__
        ):
            raise ValueError("pilot resource limits must be positive integers")


@dataclass(frozen=True, slots=True)
class N05EvidenceBinding:
    attempt_id: str
    mode_id: str
    host_ledger_root: str
    linux_evidence_root: str
    authorization_sha256: str
    host_manifest_sha256: str
    final_manifest_sha256: str
    raw_manifest_sha256: str
    independent_verification_sha256: str
    source_revision: str

    def __post_init__(self) -> None:
        _text(self.attempt_id, "N05 attempt ID")
        _text(self.mode_id, "N05 mode ID")
        host_root = _absolute_path(self.host_ledger_root, "N05 host ledger root")
        linux_root = _absolute_path(self.linux_evidence_root, "N05 Linux evidence root")
        if host_root == linux_root:
            raise ValueError("N05 host and Linux evidence roots must differ")
        for value in (
            self.authorization_sha256,
            self.host_manifest_sha256,
            self.final_manifest_sha256,
            self.raw_manifest_sha256,
            self.independent_verification_sha256,
        ):
            _digest(value)
        SourceProvenance(self.source_revision, False)


@dataclass(frozen=True, slots=True)
class TrackAPilotAuthorization:
    """Canonical human-selected pilot record; not proof of the named human."""

    schema_version: int
    authorization_scope: str
    authorization_id: str
    decision: str
    authorized_by: str
    authorized_at: str
    approval_reference: str
    human_review_statement: str
    source_revision: str
    protocol_version: str
    protocol_config: ArtifactReference
    repetition_plan_sha256: str
    campaigns: tuple[PilotCampaignCell, ...]
    total_campaigns: int
    campaign_execution_budget: int
    total_executions: int
    initial_case_ids: tuple[str, ...]
    seed_profile: str
    campaign_rng_seeds: tuple[int, ...]
    scheduling_rng_seed: int
    repetitions_per_arm: int
    initial_seeds_in_budget: bool
    target_timeout_seconds: float
    mutation_policy: MutationPolicy
    feedback_projection: FeedbackProjection
    oracle_contracts: tuple[ContractId, ...]
    sentinels: tuple[SentinelProvenance, ...]
    sentinel_profile: str
    targets: tuple[PilotTargetIdentity, PilotTargetIdentity]
    controller_id: str
    controller_image_id: str
    host_docker_context: str
    daemon_id: str
    daemon_version: str
    daemon_api_version: str
    environment: EnvironmentProvenance
    environment_profile: str
    runtime_volume_name: str
    runtime_root: str
    controller_isolation_profile: str
    target_isolation_profile: str
    resource_limits: PilotResourceLimits
    campaign_watchdog_seconds: int
    sequential: bool
    fresh_controller_per_campaign: bool
    stop_conditions: tuple[str, ...]
    no_retry: bool
    resume_policy: str
    track_a_output_root: str
    track_a_host_ledger_root: str
    n05: N05EvidenceBinding

    def __post_init__(self) -> None:
        for value, label in (
            (self.authorization_id, "pilot authorization ID"),
            (self.authorized_by, "authorizing reviewer attribution"),
            (self.approval_reference, "trusted approval reference"),
            (self.seed_profile, "seed profile"),
            (self.sentinel_profile, "sentinel profile"),
            (self.host_docker_context, "Docker context"),
            (self.daemon_id, "Docker daemon ID"),
            (self.daemon_version, "Docker daemon version"),
            (self.daemon_api_version, "Docker daemon API version"),
            (self.environment_profile, "environment profile"),
            (self.runtime_volume_name, "runtime volume"),
            (self.controller_isolation_profile, "controller isolation profile"),
            (self.target_isolation_profile, "target isolation profile"),
        ):
            _text(value, label)
        _timestamp(self.authorized_at)
        SourceProvenance(self.source_revision, False)
        _digest(self.controller_id)
        _image_digest(self.controller_image_id)
        _digest(self.repetition_plan_sha256)
        _absolute_path(self.runtime_root, "runtime root")
        output_root = _absolute_path(self.track_a_output_root, "Track A output root")
        host_root = _absolute_path(self.track_a_host_ledger_root, "Track A host ledger root")
        if output_root == host_root:
            raise ValueError("Track A output and host ledger roots must differ")
        expected_campaigns = tuple(
            PilotCampaignCell(item.run_id, item.arm_id, item.random_seed)
            for item in track_a.TRACK_A_SCHEDULE
        )
        arm_counts = Counter(item.arm_id for item in self.campaigns)
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or self.authorization_scope != PILOT_AUTHORIZATION_SCOPE
            or self.decision != PILOT_DECISION
            or self.human_review_statement != PILOT_HUMAN_REVIEW_STATEMENT
            or self.protocol_version != track_a.PROTOCOL_VERSION
            or not isinstance(self.protocol_config, ArtifactReference)
            or self.protocol_config.name != track_a.PROTOCOL_CONFIG_RELATIVE.as_posix()
            or self.campaigns != expected_campaigns
            or self.total_campaigns != 20
            or self.campaign_execution_budget != track_a.EXECUTION_BUDGET
            or self.total_executions != 4000
            or self.total_executions != self.total_campaigns * self.campaign_execution_budget
            or self.initial_case_ids != tuple(case.case_id for case in minimal_seed_corpus())
            or self.seed_profile != track_a.SEED_PROFILE
            or self.campaign_rng_seeds != (9001, 9002, 9003, 9004, 9005)
            or self.scheduling_rng_seed != 4242
            or self.repetitions_per_arm != 5
            or arm_counts
            != {
                "affected-b0": 5,
                "affected-b1": 5,
                "affected-b3": 5,
                "fixed-b3": 5,
            }
            or self.initial_seeds_in_budget is not True
            or self.target_timeout_seconds != track_a.TARGET_TIMEOUT_SECONDS
            or self.mutation_policy != MutationPolicy.M1_PROTECTED_COMPONENTS
            or self.feedback_projection != FeedbackProjection.FULL
            or self.oracle_contracts != (ContractId.C0, ContractId.C1, ContractId.C2)
            or self.sentinels != sentinel_provenance((SentinelSpec(),))
            or self.sentinel_profile != track_a.SENTINEL_PROFILE
            or tuple(item.role for item in self.targets)
            != (PilotTargetRole.AFFECTED, PilotTargetRole.FIXED)
            or not isinstance(self.environment, EnvironmentProvenance)
            or self.environment_profile != TRACK_A_N05_ENVIRONMENT_PROFILE
            or not isinstance(self.resource_limits, PilotResourceLimits)
            or self.campaign_watchdog_seconds != 7200
            or self.sequential is not True
            or self.fresh_controller_per_campaign is not True
            or self.stop_conditions != PILOT_STOP_CONDITIONS
            or self.no_retry is not True
            or self.resume_policy != PILOT_RESUME_POLICY
            or not isinstance(self.n05, N05EvidenceBinding)
        ):
            raise ValueError("pilot authorization differs from the exact Track A pilot")


@dataclass(frozen=True, slots=True)
class VerifiedN05HostSummary:
    authorization_sha256: str
    final_manifest_sha256: str
    overall_status: str
    raw_manifest_sha256: str
    source_revision: str

    def __post_init__(self) -> None:
        for value in (
            self.authorization_sha256,
            self.final_manifest_sha256,
            self.raw_manifest_sha256,
        ):
            _digest(value)
        SourceProvenance(self.source_revision, False)
        if self.overall_status != "PREFLIGHT_PASS":
            raise ValueError("N05 host ledger did not produce PREFLIGHT_PASS")


@dataclass(frozen=True, slots=True)
class TrackAAdmissionRecord:
    """Retained integrity binding created from an externally anchored admission.

    This record preserves the digest and approval reference selected by the
    caller.  Reading it verifies the retained evidence graph; the record does
    not authenticate the named human or create its own trusted approval anchor.
    """

    serialization_schema: ClassVar[int] = 1

    authorization_id: str
    approval_reference: str
    pilot_authorization: ArtifactReference
    n05_evidence: ArtifactReference
    protocol_config: ArtifactReference
    repetition_plan: ArtifactReference
    source_revision: str
    output_root: str
    host_ledger_root: str
    evidence_role: str = "retained-integrity-binding-not-human-authentication"

    def __post_init__(self) -> None:
        _text(self.authorization_id, "pilot authorization ID")
        _text(self.approval_reference, "retained approval reference")
        if (
            not isinstance(self.pilot_authorization, ArtifactReference)
            or self.pilot_authorization.name != "admission/pilot-authorization.json"
            or not isinstance(self.n05_evidence, ArtifactReference)
            or self.n05_evidence.name != "admission/n05-evidence-reference.json"
            or not isinstance(self.protocol_config, ArtifactReference)
            or self.protocol_config.name != track_a.PROTOCOL_CONFIG_RELATIVE.as_posix()
            or not isinstance(self.repetition_plan, ArtifactReference)
            or self.repetition_plan.name != "repetitions/plan.json"
            or self.evidence_role != "retained-integrity-binding-not-human-authentication"
        ):
            raise ValueError("invalid retained Track A admission references")
        SourceProvenance(self.source_revision, False)
        output_root = _absolute_path(self.output_root, "retained Track A output root")
        host_root = _absolute_path(self.host_ledger_root, "retained Track A host ledger root")
        if output_root == host_root:
            raise ValueError("retained Track A output and host roots must differ")


_FREEZE_ADMISSION_SEAL = object()


@dataclass(frozen=True, slots=True, weakref_slot=True)
class VerifiedTrackAAdmission:
    """Typed result returned after every pilot/N05/plan binding passes.

    Only objects minted by :func:`validate_track_a_admission` carry the
    process-local freeze capability.  Retained readers can reconstruct the
    same evidence values, but cannot manufacture that capability.
    """

    pilot_authorization: TrackAPilotAuthorization
    pilot_authorization_path: Path
    pilot_authorization_bytes: bytes
    pilot_authorization_sha256: str
    trusted_approval_reference: str
    n05_authorization: N05PreflightAuthorization
    host: VerifiedN05HostSummary
    n05_preflight: VerifiedN05Preflight
    n05_raw_manifest: N05RawManifest
    repetition_plan: PolicyRepetitionPlan
    repetition_plan_sha256: str
    protocol_config_sha256: str
    _freeze_admission_seal: object = field(init=False, repr=False, compare=False, default=None)


_LIVE_FREEZE_ADMISSIONS: dict[int, tuple[ReferenceType[VerifiedTrackAAdmission], str]] = {}


@dataclass(frozen=True, slots=True)
class _FreezeAdmissionFingerprint:
    components: tuple[str, ...]


def _fingerprint_component(value: object) -> str:
    if is_dataclass(value) and not isinstance(value, type):
        return canonical_json(value)
    if isinstance(value, bytes):
        return sha256(value).hexdigest()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"unsupported freeze admission component: {type(value).__name__}")


def _freeze_admission_fingerprint(value: VerifiedTrackAAdmission) -> str:
    encoded = _FreezeAdmissionFingerprint(
        tuple(
            f"{item.name}={_fingerprint_component(getattr(value, item.name))}"
            for item in fields(VerifiedTrackAAdmission)
            if item.name != "_freeze_admission_seal"
        )
    )
    return sha256(canonical_json(encoded).encode("ascii")).hexdigest()


def _register_freeze_admission(value: VerifiedTrackAAdmission) -> VerifiedTrackAAdmission:
    object.__setattr__(value, "_freeze_admission_seal", _FREEZE_ADMISSION_SEAL)
    identity = id(value)

    def discard(reference: ReferenceType[VerifiedTrackAAdmission]) -> None:
        current = _LIVE_FREEZE_ADMISSIONS.get(identity)
        if current is not None and current[0] is reference:
            _LIVE_FREEZE_ADMISSIONS.pop(identity, None)

    reference = ref(value, discard)
    _LIVE_FREEZE_ADMISSIONS[identity] = (
        reference,
        _freeze_admission_fingerprint(value),
    )
    return value


def _has_live_freeze_capability(value: object) -> bool:
    if type(value) is not VerifiedTrackAAdmission:
        return False
    registration = _LIVE_FREEZE_ADMISSIONS.get(id(value))
    return (
        value._freeze_admission_seal is _FREEZE_ADMISSION_SEAL
        and registration is not None
        and registration[0]() is value
        and registration[1] == _freeze_admission_fingerprint(value)
    )


def pilot_authorization_from_bytes(content: bytes) -> TrackAPilotAuthorization:
    """Decode exact canonical pilot bytes; this does not authenticate authorship."""
    try:
        value = decode(TrackAPilotAuthorization, read_json(content))
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError("invalid Track A pilot authorization record") from error
    if content != json_bytes(asdict(value)) + b"\n":
        raise ValueError("Track A pilot authorization record is not canonical JSON")
    return value


def _record_bytes(value: object) -> bytes:
    payload = canonical_json(value).encode("ascii")
    record = {
        "format": "inodefence-evaluation-record",
        "schema_version": 1,
        "payload": read_json(payload),
        "payload_sha256": sha256(payload).hexdigest(),
    }
    return json_bytes(record) + b"\n"


def track_a_plan_sha256(plan: PolicyRepetitionPlan) -> str:
    """Return the exact digest that ``write_record(..., plan)`` would publish."""
    if type(plan) is not PolicyRepetitionPlan:
        raise ValueError("Track A plan digest requires a PolicyRepetitionPlan")
    return sha256(_record_bytes(plan)).hexdigest()


def _artifact_path(root: Path, reference: N05ArtifactReference) -> Path:
    path = root / reference.path
    relative = Path(reference.path)
    ancestors = tuple(
        root.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts))
    )
    if (
        path.is_symlink()
        or any(item.is_symlink() for item in ancestors)
        or path.resolve().parent != path.parent.resolve()
        or not path.resolve().is_relative_to(root.resolve())
    ):
        raise VerificationError("N05 artifact path escapes its root or uses a symlink")
    return path


def _artifact_bytes(root: Path, reference: N05ArtifactReference) -> bytes:
    content = _read_file(_artifact_path(root, reference))
    if sha256(content).hexdigest() != reference.sha256:
        raise VerificationError(f"N05 artifact checksum mismatch: {reference.path}")
    return content


def _artifact_record[T](root: Path, reference: N05ArtifactReference, kind: type[T]) -> T:
    return read_record(_artifact_path(root, reference), kind, expected_sha256=reference.sha256)


def _host_summary(value: dict) -> VerifiedN05HostSummary:
    expected = {
        "authorization_sha256",
        "final_manifest_sha256",
        "overall_status",
        "raw_manifest_sha256",
        "source_revision",
    }
    if set(value) != expected or not all(isinstance(value[name], str) for name in expected):
        raise ValueError("N05 host verifier returned an incomplete PASS summary")
    return VerifiedN05HostSummary(**value)


def _pilot_target_from_n05(role: N05PreflightRole, raw: N05RawManifest) -> PilotTargetIdentity:
    target = next(item for item in raw.frozen_targets if item.role == role)
    return PilotTargetIdentity(
        PilotTargetRole(role.value),
        NODE_VERSION,
        target.tar_version,
        target.image_id,
        target.platform_manifest_sha256,
        target.package_tarball_sha256,
        target.lock_sha256,
        target.build_sha256,
        WORKER_SHA256,
    )


def _verify_protocol_and_resources(
    authorization: TrackAPilotAuthorization,
    protocol: dict,
    admissions: tuple[N05AdmissionRecord, N05AdmissionRecord],
    raw: N05RawManifest,
) -> None:
    protocol_targets = tuple(
        (
            item["role"],
            item["node_version"],
            item["tar_version"],
            item["image_id"],
            item["platform_manifest_sha256"],
            item["package_tarball_sha256"],
            item["lock_sha256"],
            protocol["worker_sha256"],
        )
        for item in protocol["targets"]
    )
    authorized_targets = tuple(
        (
            item.role.value,
            item.node_version,
            item.tar_version,
            item.image_id,
            item.platform_manifest_sha256,
            item.package_tarball_sha256,
            item.lock_sha256,
            item.worker_sha256,
        )
        for item in authorization.targets
    )
    if authorized_targets != protocol_targets:
        raise ValueError("pilot target identities differ from the Track A protocol")
    resources = authorization.resource_limits
    if protocol["resource_limits"] != {
        "capture_bytes_per_stream": resources.target_capture_bytes_per_stream,
        "file_size_bytes": resources.target_file_size_bytes,
        "memory_bytes": resources.target_memory_bytes,
        "open_files": resources.target_open_files,
        "pids": resources.target_pids,
        "shm_bytes": resources.target_shm_bytes,
        "tmpfs_bytes": resources.target_tmpfs_bytes,
    }:
        raise ValueError("pilot target resources differ from the Track A protocol")
    for admission in admissions:
        policy = admission.isolation.policy
        if (
            policy.resources.memory_bytes != resources.target_memory_bytes
            or policy.resources.pids != resources.target_pids
            or policy.resources.open_files != resources.target_open_files
            or policy.resources.file_size_bytes != resources.target_file_size_bytes
            or policy.resources.tmpfs_bytes != resources.target_tmpfs_bytes
            or policy.shm_bytes != resources.target_shm_bytes
            or policy.capture_bytes_per_stream != resources.target_capture_bytes_per_stream
        ):
            raise ValueError("pilot target resources differ from N05 admissions")
    controller_tmpfs_mib, controller_tmpfs_remainder = divmod(
        resources.controller_tmpfs_bytes, 1024 * 1024
    )
    if controller_tmpfs_remainder:
        raise ValueError("pilot controller tmpfs bytes must be an exact MiB value")
    broker = raw.broker
    if broker is None or (
        broker.controller_memory_bytes != resources.controller_memory_bytes
        or broker.controller_memory_swap_bytes != resources.controller_memory_swap_bytes
        or broker.controller_pids_limit != resources.controller_pids
        or broker.controller_tmpfs != (("/tmp", f"rw,nosuid,nodev,size={controller_tmpfs_mib}m"),)
    ):
        raise ValueError("pilot controller resources differ from N05 evidence")


def _prospective_plan(
    affected: ExecutionProvenance,
    fixed: ExecutionProvenance,
    *,
    environment_profile: str,
) -> PolicyRepetitionPlan:
    plan = track_a.make_track_a_plan(affected, fixed)
    return replace(
        plan,
        runs=tuple(
            replace(
                run,
                evaluation_config=replace(
                    run.evaluation_config,
                    environment_profile=environment_profile,
                ),
            )
            for run in plan.runs
        ),
    )


def _track_a_roots(authorization: TrackAPilotAuthorization) -> tuple[Path, Path]:
    return (
        _absolute_path(authorization.track_a_output_root, "Track A output root"),
        _absolute_path(authorization.track_a_host_ledger_root, "Track A host ledger root"),
    )


def _validate_new_track_a_roots(authorization: TrackAPilotAuthorization) -> None:
    """Protect first admission with a strict no-existing-root rule."""
    output_root, host_root = _track_a_roots(authorization)
    if any(
        path.exists() or path.is_symlink() or path.resolve() != path
        for path in (output_root, host_root)
    ):
        raise ValueError("Track A authorization requires new output and host ledger roots")


def _validate_retained_track_a_roots(
    authorization: TrackAPilotAuthorization, *, expected_output_root: Path
) -> None:
    """Validate a stored execution without weakening first-admission checks."""
    output_root, host_root = _track_a_roots(authorization)
    if (
        expected_output_root != output_root
        or not expected_output_root.is_absolute()
        or expected_output_root.is_symlink()
        or expected_output_root.resolve() != expected_output_root
        or not expected_output_root.is_dir()
    ):
        raise ValueError("retained Track A output root differs from the authorization")
    if host_root.exists():
        if host_root.is_symlink() or host_root.resolve() != host_root or not host_root.is_dir():
            raise ValueError("retained Track A host ledger root is not a nonsymlink directory")
    elif host_root.is_symlink() or host_root.resolve() != host_root:
        raise ValueError("retained Track A host ledger path is not canonical")


def _verify_track_a_admission_evidence(
    *,
    pilot_authorization_path: Path,
    pilot_authorization_bytes: bytes,
    pilot_authorization_sha256: str,
    authorization: TrackAPilotAuthorization,
    trusted_approval_reference: str,
    protocol_config_path: Path | None,
) -> VerifiedTrackAAdmission:
    expected_digest = _digest(pilot_authorization_sha256)
    _text(trusted_approval_reference, "trusted approval reference")
    content = pilot_authorization_bytes
    content_digest = sha256(content).hexdigest()
    if content_digest != expected_digest:
        raise ValueError("Track A pilot authorization checksum mismatch")
    if pilot_authorization_from_bytes(content) != authorization:
        raise ValueError("Track A pilot authorization object differs from its exact bytes")
    if authorization.approval_reference != trusted_approval_reference:
        raise ValueError("pilot approval reference differs from the trusted launch input")

    output_root, track_a_host_root = _track_a_roots(authorization)

    binding = authorization.n05
    if binding.attempt_id != N05_ATTEMPT_ID or binding.mode_id != N05_MODE_ID:
        raise ValueError("pilot authorization does not bind the N05 contract")
    host_root = _absolute_path(binding.host_ledger_root, "N05 host ledger root")
    linux_root = _absolute_path(binding.linux_evidence_root, "N05 Linux evidence root")
    _existing_nonsymlink_directory(host_root, "N05 host ledger root")
    _existing_nonsymlink_directory(linux_root, "N05 Linux evidence root")
    if any(
        future.is_relative_to(existing)
        for future in (output_root, track_a_host_root)
        for existing in (host_root, linux_root)
    ):
        raise ValueError("Track A roots cannot overlap authoritative N05 evidence")

    from scripts.container_host import verify_n05_host_ledger

    host = _host_summary(
        verify_n05_host_ledger(
            host_root,
            linux_root,
            expected_manifest_sha256=binding.host_manifest_sha256,
        )
    )
    if host != VerifiedN05HostSummary(
        binding.authorization_sha256,
        binding.final_manifest_sha256,
        "PREFLIGHT_PASS",
        binding.raw_manifest_sha256,
        binding.source_revision,
    ):
        raise ValueError("pilot N05 binding differs from the verified host summary")

    host_authorization_bytes = _existing_nonsymlink_file(
        host_root / "authorization.json", "N05 host authorization copy"
    )
    if sha256(host_authorization_bytes).hexdigest() != binding.authorization_sha256:
        raise ValueError("N05 host authorization checksum differs from pilot binding")
    n05_authorization = authorization_from_bytes(host_authorization_bytes)
    if (
        n05_authorization.attempt_id != binding.attempt_id
        or n05_authorization.mode_id != binding.mode_id
        or n05_authorization.host_ledger_root != binding.host_ledger_root
        or n05_authorization.evidence_root != binding.linux_evidence_root
        or n05_authorization.execution_source_revision != binding.source_revision
        or n05_authorization.pilot_authorized is not False
    ):
        raise ValueError("N05 authorization differs from the pilot evidence binding")

    n05_preflight = read_n05_preflight(
        linux_root,
        expected_final_manifest_sha256=binding.final_manifest_sha256,
    )
    if (
        n05_preflight.verification.status != N05IndependentStatus.PASS
        or n05_preflight.verification.recomputed_verdict.value != "PREFLIGHT_PASS"
        or n05_preflight.final_manifest.final_status != N05FinalStatus.PREFLIGHT_PASS
        or n05_preflight.final_manifest.pilot_authorized is not False
        or n05_preflight.final_manifest.host_cleanup_pending is not True
        or n05_preflight.final_manifest.raw_manifest.sha256 != binding.raw_manifest_sha256
        or n05_preflight.final_manifest.independent_verification.sha256
        != binding.independent_verification_sha256
        or n05_preflight.verification_sha256 != binding.independent_verification_sha256
    ):
        raise ValueError("N05 Linux evidence is not a complete independent PASS")
    raw = read_record(
        linux_root / "raw-manifest.json",
        N05RawManifest,
        expected_sha256=binding.raw_manifest_sha256,
    )
    linux_authorization_bytes = _artifact_bytes(linux_root, raw.authorization)
    if (
        raw.authorization.sha256 != binding.authorization_sha256
        or linux_authorization_bytes != host_authorization_bytes
        or authorization_from_bytes(linux_authorization_bytes) != n05_authorization
    ):
        raise ValueError("N05 host and Linux authorization bytes differ")
    if (
        raw.attempt_id != binding.attempt_id
        or raw.source != SourceProvenance(binding.source_revision, False)
        or authorization.source_revision != binding.source_revision
    ):
        raise ValueError("pilot and N05 source revisions differ")

    admissions_value = tuple(
        _artifact_record(linux_root, reference, N05AdmissionRecord) for reference in raw.admissions
    )
    if len(admissions_value) != 2:
        raise ValueError("N05 PASS must retain exactly two target admissions")
    admissions = (admissions_value[0], admissions_value[1])
    expected_targets = tuple(_pilot_target_from_n05(role, raw) for role in N05PreflightRole)
    if authorization.targets != expected_targets:
        raise ValueError("pilot target identities differ from N05 evidence")
    broker = raw.broker
    if broker is None or (
        authorization.controller_id != n05_authorization.controller_id
        or authorization.controller_id != broker.controller_id
        or authorization.controller_image_id != n05_authorization.controller_image_id
        or authorization.controller_image_id != broker.controller_image_id
        or authorization.host_docker_context != n05_authorization.host_docker_context
        or authorization.host_docker_context != broker.context_name
        or authorization.daemon_id != n05_authorization.daemon_id
        or authorization.daemon_id != broker.daemon_id
        or authorization.daemon_version != n05_authorization.daemon_version
        or authorization.daemon_version != broker.daemon_version
        or authorization.daemon_api_version != n05_authorization.daemon_api_version
        or authorization.daemon_api_version != broker.daemon_api_version
        or authorization.runtime_volume_name != n05_authorization.runtime_volume_name
        or authorization.runtime_volume_name != broker.runtime_volume_name
        or authorization.environment != raw.environment
        or authorization.target_timeout_seconds != n05_authorization.target_timeout_seconds
        or authorization.controller_isolation_profile
        != n05_authorization.controller_isolation_profile
        or authorization.target_isolation_profile != n05_authorization.target_isolation_profile
    ):
        raise ValueError("pilot controller/daemon/environment binding differs from N05")
    runtime_mount = next(
        (
            item
            for item in broker.controller_mounts
            if item.destination == authorization.runtime_root
        ),
        None,
    )
    if (
        runtime_mount is None
        or runtime_mount.mount_type != "volume"
        or runtime_mount.source != authorization.runtime_volume_name
        or runtime_mount.read_write is not True
        or any(
            item.target.timeout_seconds != authorization.target_timeout_seconds
            or item.isolation.policy.implementation_id != authorization.target_isolation_profile
            for item in admissions
        )
    ):
        raise ValueError("pilot timeout/runtime/isolation binding differs from N05")

    if protocol_config_path is not None:
        _existing_nonsymlink_file(protocol_config_path, "Track A protocol config")
    protocol, protocol_digest = track_a.load_track_a_protocol(
        protocol_config_path,
        expected_sha256=authorization.protocol_config.sha256,
    )
    if (
        protocol_digest != authorization.protocol_config.sha256
        or protocol["evidence"]["output_root"] != authorization.track_a_output_root
    ):
        raise ValueError("pilot output/protocol binding differs")
    _verify_protocol_and_resources(authorization, protocol, admissions, raw)

    provenance = {
        item.role: ExecutionProvenance(
            raw.source,
            raw.environment,
            item.target,
            authorization.sentinels,
            item.isolation,
        )
        for item in admissions
    }
    plan = _prospective_plan(
        provenance[N05PreflightRole.AFFECTED],
        provenance[N05PreflightRole.FIXED],
        environment_profile=authorization.environment_profile,
    )
    plan_digest = track_a_plan_sha256(plan)
    if plan_digest != authorization.repetition_plan_sha256:
        raise ValueError("pilot repetition plan checksum differs from the N05-bound plan")
    return VerifiedTrackAAdmission(
        authorization,
        pilot_authorization_path,
        content,
        content_digest,
        trusted_approval_reference,
        n05_authorization,
        host,
        n05_preflight,
        raw,
        plan,
        plan_digest,
        protocol_digest,
    )


def validate_track_a_admission(
    *,
    pilot_authorization_path: Path,
    expected_pilot_authorization_sha256: str,
    trusted_approval_reference: str,
    protocol_config_path: Path | None = None,
) -> VerifiedTrackAAdmission:
    """Return a typed admission only after read-only validation of all bindings.

    The trusted digest and approval reference must be supplied by the trusted
    approval/launch route, not copied from the candidate authorization file.
    """
    try:
        expected_digest = _digest(expected_pilot_authorization_sha256)
        _text(trusted_approval_reference, "trusted approval reference")
        if not pilot_authorization_path.is_absolute():
            raise ValueError("pilot authorization path must be absolute")
        content = _existing_nonsymlink_file(pilot_authorization_path, "pilot authorization")
        if sha256(content).hexdigest() != expected_digest:
            raise ValueError("Track A pilot authorization checksum mismatch")
        authorization = pilot_authorization_from_bytes(content)
        _validate_new_track_a_roots(authorization)
        verified = _verify_track_a_admission_evidence(
            pilot_authorization_path=pilot_authorization_path,
            pilot_authorization_bytes=content,
            pilot_authorization_sha256=expected_digest,
            authorization=authorization,
            trusted_approval_reference=trusted_approval_reference,
            protocol_config_path=protocol_config_path,
        )
        return _register_freeze_admission(verified)
    except Exception as error:
        if isinstance(error, VerificationError) and str(error).startswith(
            "invalid Track A admission:"
        ):
            raise
        raise VerificationError(f"invalid Track A admission: {error}") from error


def revalidate_track_a_admission_for_freeze(
    admission: VerifiedTrackAAdmission,
    *,
    protocol_config_path: Path | None = None,
) -> VerifiedTrackAAdmission:
    """Reopen a live, externally anchored admission immediately before freeze.

    Type identity is insufficient: only the exact object minted by the public
    validator is accepted, and all original pilot/N05/protocol bytes are read
    again.  Manual construction, copying and ``dataclasses.replace`` do not
    inherit the process-local capability.
    """
    if not _has_live_freeze_capability(admission):
        raise VerificationError(
            "invalid Track A admission: freeze requires the exact live validator result"
        )
    current = validate_track_a_admission(
        pilot_authorization_path=admission.pilot_authorization_path,
        expected_pilot_authorization_sha256=admission.pilot_authorization_sha256,
        trusted_approval_reference=admission.trusted_approval_reference,
        protocol_config_path=protocol_config_path,
    )
    if current != admission:
        raise VerificationError("invalid Track A admission: validator result changed before freeze")
    return current


def revalidate_retained_track_a_admission(
    *,
    pilot_authorization_path: Path,
    expected_pilot_authorization_sha256: str,
    retained_approval_reference: str,
    expected_n05_binding: N05EvidenceBinding,
    expected_output_root: Path,
    protocol_config_path: Path | None = None,
) -> VerifiedTrackAAdmission:
    """Reopen stored bytes and authoritative N05 roots without minting a freeze capability.

    The digest/reference arguments are retained integrity bindings anchored by
    the caller's expected execution manifest.  They preserve, but do not by
    themselves authenticate, the original human approval.
    """
    try:
        expected_digest = _digest(expected_pilot_authorization_sha256)
        _text(retained_approval_reference, "retained approval reference")
        content = _existing_nonsymlink_file(
            pilot_authorization_path, "retained pilot authorization"
        )
        if sha256(content).hexdigest() != expected_digest:
            raise ValueError("retained pilot authorization checksum mismatch")
        authorization = pilot_authorization_from_bytes(content)
        if authorization.n05 != expected_n05_binding:
            raise ValueError("retained N05 binding differs from the pilot authorization")
        _validate_retained_track_a_roots(authorization, expected_output_root=expected_output_root)
        return _verify_track_a_admission_evidence(
            pilot_authorization_path=pilot_authorization_path,
            pilot_authorization_bytes=content,
            pilot_authorization_sha256=expected_digest,
            authorization=authorization,
            trusted_approval_reference=retained_approval_reference,
            protocol_config_path=protocol_config_path,
        )
    except Exception as error:
        if isinstance(error, VerificationError) and str(error).startswith(
            "invalid retained Track A admission:"
        ):
            raise
        raise VerificationError(f"invalid retained Track A admission: {error}") from error
