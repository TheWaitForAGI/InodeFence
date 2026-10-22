"""Frozen Track A final-state exploratory schedule, evidence, and analysis.

This module composes existing B0/B1/B3 execution and readers.  It does not
change mutation, observer, C0/C1/C2, feedback, or N01 matching semantics and it
cannot manufacture resource authorization or a historical qualification token.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from statistics import median
from typing import TYPE_CHECKING, ClassVar

from inodefence.campaign import CampaignOrigin, SearchCampaignCompletedStep, SearchCampaignConfig
from inodefence.feedback import FeedbackProjection, SearchPolicy, violation_fingerprints
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ContractId, ExecutionStatus, IdentityEvidence, canonical_json
from inodefence.model.isolation import ArtifactDigest, IsolationPolicy
from inodefence.model.provenance import ExecutionProvenance, SourceProvenance
from inodefence.mutator import MutationOperatorId, MutationPolicy
from inodefence.provenance import capture_environment, capture_source, sentinel_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.isolated import IsolatedTarget

from .encoding import json_bytes, object_fields, read_json
from .failure import ArtifactReference
from .n01 import NODE_VERSION, WORKER_SHA256
from .n01_candidate_match import nominate_n01_policy_candidates
from .policy_binding import PolicyEvaluationConfig
from .policy_journal import PolicyJournalSnapshot, read_policy_journal
from .policy_repeated import (
    PolicyRepetitionController,
    PolicyRepetitionPlan,
    PolicyRepetitionSnapshot,
    PolicyScheduledRun,
    read_policy_repetitions,
)
from .policy_timing import PolicyCampaignTiming, VerifiedTimedPolicyEvidence
from .repeated import RunState
from .storage import publish_bytes, read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file

if TYPE_CHECKING:
    from .track_a_admission import VerifiedTrackAAdmission

PROTOCOL_VERSION = "track-a-final-state-exploratory-feasibility-v1"
EXPERIMENT_ID = PROTOCOL_VERSION
OUTPUT_ROOT = Path("/var/lib/inodefence/evidence/track-a-final-state-exploratory-feasibility-v1")
PROTOCOL_CONFIG_RELATIVE = Path(
    "experiments/configs/track-a-final-state-exploratory-feasibility-v1.json"
)
EXECUTION_BUDGET = 200
TARGET_TIMEOUT_SECONDS = 5.0
SEED_PROFILE = "minimal-generic-v1"
ENVIRONMENT_PROFILE = "n05-arm64-orbstack-five-second-v2"
SENTINEL_PROFILE = "default-outside-sentinel-v1"
FINAL_MANIFEST_NAME = "final-manifest.json"

AFFECTED_IMAGE_ID = "sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520"
FIXED_IMAGE_ID = "sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f"
AFFECTED_PLATFORM_MANIFEST = "b5ae7f5d2f85f12fa417ecece3e9089001266cc6bf4a997724c225a40ce8b542"
FIXED_PLATFORM_MANIFEST = "3a1bcf4dffcd21ddc4fa6645980bebd96dceda4ceee0ddfe033abd0d50dd6ee0"
AFFECTED_LOCK_SHA256 = "31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243"
FIXED_LOCK_SHA256 = "a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24"
AFFECTED_TARBALL_SHA256 = "22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a"
FIXED_TARBALL_SHA256 = "9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66"


@dataclass(frozen=True, slots=True)
class TrackAScheduleCell:
    run_id: str
    arm_id: str
    random_seed: int


TRACK_A_SCHEDULE = tuple(
    TrackAScheduleCell(*values)
    for values in (
        ("n01-affected-b3-9002", "affected-b3", 9002),
        ("n01-fixed-b3-9003", "fixed-b3", 9003),
        ("n01-affected-b3-9004", "affected-b3", 9004),
        ("n01-affected-b1-9003", "affected-b1", 9003),
        ("n01-fixed-b3-9001", "fixed-b3", 9001),
        ("n01-fixed-b3-9005", "fixed-b3", 9005),
        ("n01-affected-b1-9001", "affected-b1", 9001),
        ("n01-fixed-b3-9004", "fixed-b3", 9004),
        ("n01-affected-b3-9003", "affected-b3", 9003),
        ("n01-affected-b1-9005", "affected-b1", 9005),
        ("n01-fixed-b3-9002", "fixed-b3", 9002),
        ("n01-affected-b0-9003", "affected-b0", 9003),
        ("n01-affected-b3-9001", "affected-b3", 9001),
        ("n01-affected-b3-9005", "affected-b3", 9005),
        ("n01-affected-b1-9002", "affected-b1", 9002),
        ("n01-affected-b0-9005", "affected-b0", 9005),
        ("n01-affected-b0-9004", "affected-b0", 9004),
        ("n01-affected-b0-9001", "affected-b0", 9001),
        ("n01-affected-b0-9002", "affected-b0", 9002),
        ("n01-affected-b1-9004", "affected-b1", 9004),
    )
)

_ARM_POLICY = {
    "affected-b0": SearchPolicy.B0,
    "affected-b1": SearchPolicy.B1,
    "affected-b3": SearchPolicy.B3,
    "fixed-b3": SearchPolicy.B3,
}


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _protocol_path() -> Path:
    return _repository_root() / PROTOCOL_CONFIG_RELATIVE


def _expected_schedule_json() -> list[dict[str, object]]:
    return [asdict(cell) for cell in TRACK_A_SCHEDULE]


def load_track_a_protocol(
    path: Path | None = None, *, expected_sha256: str | None = None
) -> tuple[dict, str]:
    """Read the prospective protocol bytes and reject schedule/identity drift."""
    selected = _protocol_path() if path is None else path
    content = _read_file(selected)
    digest = sha256(content).hexdigest()
    if expected_sha256 is not None and digest != _digest(expected_sha256):
        raise VerificationError("Track A protocol checksum mismatch")
    try:
        value = object_fields(
            read_json(content),
            {
                "analysis",
                "authorization",
                "evidence",
                "execution",
                "initial_case_ids",
                "policies",
                "protocol_version",
                "resource_limits",
                "schedule",
                "schema_version",
                "scientific_scope",
                "source",
                "targets",
                "worker_sha256",
            },
        )
        execution = object_fields(
            value["execution"],
            {
                "campaign_execution_budget",
                "campaign_rng_seeds",
                "campaign_watchdog_seconds",
                "fresh_controller_process_per_campaign",
                "initial_seed_count",
                "scheduling_rng_seed",
                "sequential",
                "target_timeout_seconds",
                "total_campaigns",
                "total_executions",
            },
        )
        authorization = object_fields(
            value["authorization"], {"pilot", "preflight", "prompt_is_not_authorization"}
        )
        evidence = object_fields(
            value["evidence"],
            {
                "controller_memory",
                "failure_policy",
                "final_manifest",
                "independent_reader_required",
                "output_root",
                "raw_policy_journal",
                "repetition_ledger",
            },
        )
        analysis = object_fields(
            value["analysis"],
            {
                "candidate_rule",
                "full_step_timing",
                "meaningful_observation",
                "p95",
                "reader",
                "state_novelty_is_not_vulnerability",
            },
        )
        policies = object_fields(
            value["policies"],
            {
                "affected-b0",
                "affected-b1",
                "affected-b3",
                "feedback_projection",
                "fixed-b3",
                "mutation",
                "tar_builder",
            },
        )
        resources = object_fields(
            value["resource_limits"],
            {
                "capture_bytes_per_stream",
                "file_size_bytes",
                "memory_bytes",
                "open_files",
                "pids",
                "shm_bytes",
                "tmpfs_bytes",
            },
        )
        scientific_scope = object_fields(
            value["scientific_scope"],
            {
                "central_hypothesis",
                "comparison",
                "known_class_rediscovery",
                "purpose",
                "transition_policies",
            },
        )
        source = object_fields(value["source"], {"execution_revision", "preparation_base_revision"})
        target_values = value["targets"]
        if not isinstance(target_values, list) or len(target_values) != 2:
            raise ValueError("Track A requires exactly two target records")
        target_fields = {
            "image_id",
            "lock_sha256",
            "node_version",
            "package_tarball_sha256",
            "platform_manifest_sha256",
            "role",
            "tar_version",
        }
        targets = [object_fields(item, target_fields) for item in target_values]
        expected_targets = (
            (
                "affected",
                "7.5.2",
                AFFECTED_IMAGE_ID,
                AFFECTED_LOCK_SHA256,
                AFFECTED_PLATFORM_MANIFEST,
                AFFECTED_TARBALL_SHA256,
            ),
            (
                "fixed",
                "7.5.3",
                FIXED_IMAGE_ID,
                FIXED_LOCK_SHA256,
                FIXED_PLATFORM_MANIFEST,
                FIXED_TARBALL_SHA256,
            ),
        )
        if any(
            (
                item["role"],
                item["tar_version"],
                item["image_id"],
                item["lock_sha256"],
                item["platform_manifest_sha256"],
                item["package_tarball_sha256"],
            )
            != expected
            or item["node_version"] != NODE_VERSION
            for item, expected in zip(targets, expected_targets, strict=True)
        ):
            raise ValueError("Track A target identities changed")
        seed_ids = tuple(case.case_id for case in minimal_seed_corpus())
        if (
            value["schema_version"] != 1
            or value["protocol_version"] != PROTOCOL_VERSION
            or value["worker_sha256"] != WORKER_SHA256
            or value["initial_case_ids"] != list(seed_ids)
            or value["schedule"] != _expected_schedule_json()
            or execution["campaign_execution_budget"] != EXECUTION_BUDGET
            or execution["campaign_rng_seeds"] != [9001, 9002, 9003, 9004, 9005]
            or execution["campaign_watchdog_seconds"] != 7200
            or execution["initial_seed_count"] != 4
            or execution["scheduling_rng_seed"] != 4242
            or execution["target_timeout_seconds"] != TARGET_TIMEOUT_SECONDS
            or execution["total_campaigns"] != 20
            or execution["total_executions"] != 4000
            or execution["sequential"] is not True
            or execution["fresh_controller_process_per_campaign"] is not True
            or evidence["output_root"] != str(OUTPUT_ROOT)
            or evidence["failure_policy"] != "preserve-stop-no-retry"
            or evidence["controller_memory"] != "linux-proc-self-vmhwm-v1"
            or evidence["final_manifest"] != "track-a-final-manifest-v1"
            or evidence["independent_reader_required"] is not True
            or evidence["raw_policy_journal"] != "policy-journal-v1"
            or evidence["repetition_ledger"] != "policy-repeated-v1"
            or policies
            != {
                "affected-b0": SearchPolicy.B0.value,
                "affected-b1": SearchPolicy.B1.value,
                "affected-b3": SearchPolicy.B3.value,
                "feedback_projection": "state-signature-v3-full",
                "fixed-b3": SearchPolicy.B3.value,
                "mutation": MutationPolicy.M1_PROTECTED_COMPONENTS.value,
                "tar_builder": "ustar-v1",
            }
            or resources
            != {
                "capture_bytes_per_stream": 1024 * 1024,
                "file_size_bytes": 64 * 1024 * 1024,
                "memory_bytes": 512 * 1024 * 1024,
                "open_files": 1024,
                "pids": 64,
                "shm_bytes": 16 * 1024 * 1024,
                "tmpfs_bytes": 32 * 1024 * 1024,
            }
            or analysis
            != {
                "candidate_rule": "n01-policy-candidate-machine-match-v1",
                "full_step_timing": "policy-full-step-monotonic-v1",
                "meaningful_observation": (
                    "first-1-based-execution-with-generic-C0-C1-or-C2-violation"
                ),
                "p95": "nearest-rank",
                "reader": "python -m inodefence.evaluation.track_a_exploratory analyze",
                "state_novelty_is_not_vulnerability": True,
            }
            or scientific_scope
            != {
                "central_hypothesis": "not_evaluated",
                "comparison": "final-state-feedback-only",
                "known_class_rediscovery": "not_confirmed-by-machine-match",
                "purpose": "bounded-exploratory-feasibility",
                "transition_policies": "out-of-scope",
            }
            or source
            != {
                "execution_revision": "freeze-clean-full-sha-in-execution-manifest",
                "preparation_base_revision": "21e317281a2d2a7faf6198f66302f3912b429011",
            }
            or authorization
            != {
                "pilot": "required-not-recorded",
                "preflight": "required-not-recorded",
                "prompt_is_not_authorization": True,
            }
        ):
            raise ValueError("Track A protocol constants changed")
        return value, digest
    except (ValueError, TypeError, KeyError) as error:
        raise VerificationError(f"invalid Track A protocol: {error}") from error


def _expected_artifacts(lock_sha256: str) -> tuple[ArtifactDigest, ...]:
    return (
        ArtifactDigest("node-tar-package-lock", lock_sha256),
        ArtifactDigest("node-tar-worker", WORKER_SHA256),
    )


def _validate_target_provenance(
    provenance: ExecutionProvenance,
    *,
    tar_version: str,
    image_id: str,
    lock_sha256: str,
) -> None:
    isolation = provenance.isolation
    if (
        provenance.source.revision is None
        or provenance.source.dirty is not False
        or provenance.environment.system != "Linux"
        or provenance.environment.machine not in {"arm64", "aarch64"}
        or provenance.target.target_id != "node-tar-strict"
        or provenance.target.target_version != f"node={NODE_VERSION};tar={tar_version}"
        or provenance.target.timeout_seconds != TARGET_TIMEOUT_SECONDS
        or provenance.sentinels != sentinel_provenance((SentinelSpec(),))
        or isolation is None
        or isolation.policy != IsolationPolicy(image_id, 1000, 1000)
        or isolation.runtime_architecture not in {"arm64", "aarch64"}
        or isolation.image_architecture not in {"arm64", "aarch64"}
        or isolation.artifacts != _expected_artifacts(lock_sha256)
    ):
        raise ValueError("Track A target/source/environment/isolation provenance mismatch")


def make_track_a_plan(
    affected_provenance: ExecutionProvenance,
    fixed_provenance: ExecutionProvenance,
) -> PolicyRepetitionPlan:
    """Build the exact N03 20-cell order after an authorized preflight captured provenance."""
    _validate_target_provenance(
        affected_provenance,
        tar_version="7.5.2",
        image_id=AFFECTED_IMAGE_ID,
        lock_sha256=AFFECTED_LOCK_SHA256,
    )
    _validate_target_provenance(
        fixed_provenance,
        tar_version="7.5.3",
        image_id=FIXED_IMAGE_ID,
        lock_sha256=FIXED_LOCK_SHA256,
    )
    if (
        affected_provenance.source != fixed_provenance.source
        or affected_provenance.environment != fixed_provenance.environment
    ):
        raise ValueError("Track A target arms require one clean source/environment")
    initial_ids = tuple(case.case_id for case in minimal_seed_corpus())
    runs = []
    for cell in TRACK_A_SCHEDULE:
        provenance = fixed_provenance if cell.arm_id == "fixed-b3" else affected_provenance
        campaign = SearchCampaignConfig(
            cell.random_seed,
            EXECUTION_BUDGET,
            _ARM_POLICY[cell.arm_id],
            MutationPolicy.M1_PROTECTED_COMPONENTS,
            FeedbackProjection.FULL,
        )
        runs.append(
            PolicyScheduledRun(
                cell.run_id,
                cell.arm_id,
                PolicyEvaluationConfig(
                    campaign,
                    initial_ids,
                    provenance,
                    SEED_PROFILE,
                    ENVIRONMENT_PROFILE,
                    SENTINEL_PROFILE,
                    PROTOCOL_VERSION,
                ),
            )
        )
    return PolicyRepetitionPlan(EXPERIMENT_ID, PROTOCOL_VERSION, tuple(runs))


def validate_track_a_plan(plan: PolicyRepetitionPlan) -> None:
    if type(plan) is not PolicyRepetitionPlan or len(plan.runs) != len(TRACK_A_SCHEDULE):
        raise ValueError("Track A requires the exact 20-cell policy plan")
    affected = next(
        run.evaluation_config.provenance for run in plan.runs if run.arm_id.startswith("affected-")
    )
    fixed = next(run.evaluation_config.provenance for run in plan.runs if run.arm_id == "fixed-b3")
    if plan != make_track_a_plan(affected, fixed):
        raise ValueError("Track A repetition plan differs from the frozen schedule")


@dataclass(frozen=True, slots=True)
class TrackAExecutionManifest:
    """Pre-execution marker binding retained admission/config/plan and source."""

    serialization_schema: ClassVar[int] = 2

    protocol_version: str
    protocol_config: ArtifactReference
    pilot_authorization: ArtifactReference
    admission_record: ArtifactReference
    n05_evidence: ArtifactReference
    source_revision: str
    output_root: str
    repetition_plan: ArtifactReference
    created_at_utc: str
    state: str = "frozen-pre-execution"

    def __post_init__(self) -> None:
        if (
            self.protocol_version != PROTOCOL_VERSION
            or not isinstance(self.protocol_config, ArtifactReference)
            or self.protocol_config.name != PROTOCOL_CONFIG_RELATIVE.as_posix()
            or not isinstance(self.pilot_authorization, ArtifactReference)
            or self.pilot_authorization.name != "admission/pilot-authorization.json"
            or not isinstance(self.admission_record, ArtifactReference)
            or self.admission_record.name != "admission/verified-admission.json"
            or not isinstance(self.n05_evidence, ArtifactReference)
            or self.n05_evidence.name != "admission/n05-evidence-reference.json"
            or not isinstance(self.repetition_plan, ArtifactReference)
            or self.repetition_plan.name != "repetitions/plan.json"
            or self.state != "frozen-pre-execution"
        ):
            raise ValueError("invalid Track A execution binding")
        SourceProvenance(self.source_revision, False)
        if not isinstance(self.output_root, str) or not self.output_root:
            raise ValueError("Track A output root must be explicit")
        parsed = datetime.fromisoformat(self.created_at_utc)
        if parsed.utcoffset() is None:
            raise ValueError("Track A execution timestamp requires a timezone")


@dataclass(frozen=True, slots=True)
class VerifiedTrackAExecution:
    manifest: TrackAExecutionManifest
    execution_sha256: str
    repetitions: PolicyRepetitionSnapshot
    protocol_config_sha256: str
    admission: VerifiedTrackAAdmission


def freeze_track_a_execution(
    root: Path,
    affected_provenance: ExecutionProvenance,
    fixed_provenance: ExecutionProvenance,
    *,
    admission: VerifiedTrackAAdmission,
    protocol_config_path: Path | None = None,
) -> VerifiedTrackAExecution:
    """Freeze a live, externally anchored admission before any campaign."""
    from .track_a_admission import (
        TrackAAdmissionRecord,
        revalidate_track_a_admission_for_freeze,
        track_a_plan_sha256,
    )

    verified_admission = revalidate_track_a_admission_for_freeze(
        admission, protocol_config_path=protocol_config_path
    )
    authorization = verified_admission.pilot_authorization
    protocol, protocol_digest = load_track_a_protocol(protocol_config_path)
    if (
        not root.is_absolute()
        or root != Path(authorization.track_a_output_root)
        or root != Path(protocol["evidence"]["output_root"])
        or root.exists()
        or root.is_symlink()
        or root.resolve() != root
    ):
        raise ValueError("Track A requires its exact new absolute output root")
    plan = make_track_a_plan(affected_provenance, fixed_provenance)
    if (
        plan != verified_admission.repetition_plan
        or track_a_plan_sha256(plan) != verified_admission.repetition_plan_sha256
        or protocol_digest != verified_admission.protocol_config_sha256
    ):
        raise ValueError("Track A execution plan/protocol differs from the verified admission")
    root.mkdir(parents=True, exist_ok=False)
    sync_directory(root.parent)
    admission_root = root / "admission"
    admission_root.mkdir(exist_ok=False)
    sync_directory(root)
    pilot_path = admission_root / "pilot-authorization.json"
    pilot_sha256 = publish_bytes(pilot_path, verified_admission.pilot_authorization_bytes)
    if pilot_sha256 != verified_admission.pilot_authorization_sha256:
        raise ValueError("published pilot authorization differs from the verified bytes")
    n05_path = admission_root / "n05-evidence-reference.json"
    n05_sha256 = write_record(n05_path, authorization.n05)
    admission_record = TrackAAdmissionRecord(
        authorization.authorization_id,
        verified_admission.trusted_approval_reference,
        ArtifactReference("admission/pilot-authorization.json", pilot_sha256),
        ArtifactReference("admission/n05-evidence-reference.json", n05_sha256),
        ArtifactReference(PROTOCOL_CONFIG_RELATIVE.as_posix(), protocol_digest),
        ArtifactReference("repetitions/plan.json", verified_admission.repetition_plan_sha256),
        authorization.source_revision,
        authorization.track_a_output_root,
        authorization.track_a_host_ledger_root,
    )
    admission_sha256 = write_record(admission_root / "verified-admission.json", admission_record)
    controller = PolicyRepetitionController.create(root / "repetitions", plan)
    plan_sha256 = controller.snapshot().plan_sha256
    if plan_sha256 != verified_admission.repetition_plan_sha256:
        raise ValueError("published Track A plan differs from the verified admission")
    source_revision = affected_provenance.source.revision
    assert source_revision is not None
    manifest = TrackAExecutionManifest(
        PROTOCOL_VERSION,
        ArtifactReference(PROTOCOL_CONFIG_RELATIVE.as_posix(), protocol_digest),
        ArtifactReference("admission/pilot-authorization.json", pilot_sha256),
        ArtifactReference("admission/verified-admission.json", admission_sha256),
        ArtifactReference("admission/n05-evidence-reference.json", n05_sha256),
        source_revision,
        str(root),
        ArtifactReference("repetitions/plan.json", plan_sha256),
        datetime.now(UTC).isoformat(),
    )
    execution_sha256 = write_record(root / "execution.json", manifest)
    return read_track_a_execution(
        root,
        expected_execution_sha256=execution_sha256,
        protocol_config_path=protocol_config_path,
    )


def read_track_a_execution(
    root: Path,
    *,
    expected_execution_sha256: str,
    protocol_config_path: Path | None = None,
) -> VerifiedTrackAExecution:
    """Reopen local admission bytes and authoritative N05 evidence read-only."""
    try:
        from .track_a_admission import (
            N05EvidenceBinding,
            TrackAAdmissionRecord,
            revalidate_retained_track_a_admission,
        )

        if (
            not root.is_absolute()
            or root.is_symlink()
            or root.resolve() != root
            or not root.is_dir()
        ):
            raise ValueError("expected Track A evidence directory")
        permitted = {"admission", "execution.json", "repetitions", FINAL_MANIFEST_NAME}
        if any(path.name not in permitted for path in root.iterdir()):
            raise ValueError("unexpected Track A top-level artifact")
        admission_root = root / "admission"
        if (
            admission_root.is_symlink()
            or admission_root.resolve() != admission_root
            or not admission_root.is_dir()
            or {path.name for path in admission_root.iterdir()}
            != {
                "n05-evidence-reference.json",
                "pilot-authorization.json",
                "verified-admission.json",
            }
            or any(path.is_symlink() or not path.is_file() for path in admission_root.iterdir())
        ):
            raise ValueError("invalid Track A admission evidence directory")
        execution_path = root / "execution.json"
        digest = sha256(_read_file(execution_path)).hexdigest()
        if digest != _digest(expected_execution_sha256):
            raise ValueError("Track A execution checksum mismatch")
        manifest = read_record(execution_path, TrackAExecutionManifest, expected_sha256=digest)
        _, protocol_digest = load_track_a_protocol(
            protocol_config_path, expected_sha256=manifest.protocol_config.sha256
        )
        if manifest.output_root != str(root):
            raise ValueError("Track A output root differs from execution binding")
        admission_record = read_record(
            root / manifest.admission_record.name,
            TrackAAdmissionRecord,
            expected_sha256=manifest.admission_record.sha256,
        )
        n05_binding = read_record(
            root / manifest.n05_evidence.name,
            N05EvidenceBinding,
            expected_sha256=manifest.n05_evidence.sha256,
        )
        if (
            admission_record.pilot_authorization != manifest.pilot_authorization
            or admission_record.n05_evidence != manifest.n05_evidence
            or admission_record.protocol_config != manifest.protocol_config
            or admission_record.repetition_plan != manifest.repetition_plan
            or admission_record.source_revision != manifest.source_revision
            or admission_record.output_root != manifest.output_root
        ):
            raise ValueError("Track A execution and admission records disagree")
        reverified_admission = revalidate_retained_track_a_admission(
            pilot_authorization_path=root / manifest.pilot_authorization.name,
            expected_pilot_authorization_sha256=manifest.pilot_authorization.sha256,
            retained_approval_reference=admission_record.approval_reference,
            expected_n05_binding=n05_binding,
            expected_output_root=root,
            protocol_config_path=protocol_config_path,
        )
        authorization = reverified_admission.pilot_authorization
        if (
            admission_record.authorization_id != authorization.authorization_id
            or admission_record.approval_reference != authorization.approval_reference
            or admission_record.host_ledger_root != authorization.track_a_host_ledger_root
            or reverified_admission.protocol_config_sha256 != protocol_digest
        ):
            raise ValueError("retained admission identity differs from its verified originals")
        repetitions = read_policy_repetitions(
            root / "repetitions",
            expected_plan_sha256=manifest.repetition_plan.sha256,
            require_controller_memory=True,
        )
        validate_track_a_plan(repetitions.plan)
        if (
            repetitions.plan != reverified_admission.repetition_plan
            or repetitions.plan_sha256 != reverified_admission.repetition_plan_sha256
        ):
            raise ValueError("Track A plan differs from the retained admission")
        sources = {
            run.evaluation_config.provenance.source.revision for run in repetitions.plan.runs
        }
        if sources != {manifest.source_revision}:
            raise ValueError("Track A plan source differs from execution binding")
        return VerifiedTrackAExecution(
            manifest, digest, repetitions, protocol_digest, reverified_admission
        )
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        if isinstance(error, VerificationError):
            raise
        raise VerificationError(f"invalid Track A execution evidence: {error}") from error


def execute_track_a_slot(
    root: Path,
    index: int,
    target: IsolatedTarget,
    *,
    attempt_id: str,
    expected_execution_sha256: str,
    repository: Path,
    protocol_config_path: Path | None = None,
) -> VerifiedTimedPolicyEvidence:
    """Execute one next-in-order cell; caller must provide a fresh controller process."""
    if (root / FINAL_MANIFEST_NAME).exists():
        raise ValueError("finalized Track A evidence cannot execute another cell")
    if type(target) is not IsolatedTarget:
        raise ValueError("Track A requires the enforced isolated target composition")
    verified = read_track_a_execution(
        root,
        expected_execution_sha256=expected_execution_sha256,
        protocol_config_path=protocol_config_path,
    )
    slots = verified.repetitions.slots
    if type(index) is not int or not 0 <= index < len(slots):
        raise ValueError("Track A run index is outside the frozen schedule")
    if any(slot.state != RunState.COMPLETED for slot in slots[:index]):
        raise ValueError("Track A execution must stop after a prior non-complete slot")
    if slots[index].state != RunState.PENDING or any(
        slot.state != RunState.PENDING for slot in slots[index:]
    ):
        raise ValueError("Track A executes the next pending cell exactly once in order")
    scheduled = verified.repetitions.plan.runs[index]
    source = capture_source(repository)
    if source.revision != verified.manifest.source_revision or source.dirty is not False:
        raise ValueError("Track A execution requires the frozen clean source revision")
    isolation = target.capture_isolation()
    observed = ExecutionProvenance(
        source,
        capture_environment(),
        target.provenance,
        sentinel_provenance((SentinelSpec(),)),
        isolation,
    )
    if observed != scheduled.evaluation_config.provenance:
        raise ValueError("Track A current target/environment differs from the frozen plan")
    controller = PolicyRepetitionController(
        root / "repetitions", expected_plan_sha256=verified.repetitions.plan_sha256
    )
    return controller.execute_measured(
        index,
        minimal_seed_corpus(),
        target,
        attempt_id=attempt_id,
        sentinels=(SentinelSpec(),),
    )


class TrackAFinalStatus(StrEnum):
    COMPLETE = "complete"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class TrackAFileDigest:
    path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, str)
            or not self.path
            or self.path.startswith("/")
            or ".." in Path(self.path).parts
            or type(self.size_bytes) is not int
            or self.size_bytes < 0
        ):
            raise ValueError("invalid Track A artifact inventory path/size")
        _digest(self.sha256)


@dataclass(frozen=True, slots=True)
class TrackAFinalManifest:
    serialization_schema: ClassVar[int] = 1

    protocol_version: str
    status: TrackAFinalStatus
    stop_reason: str | None
    execution: ArtifactReference
    repetition_plan: ArtifactReference
    scheduled_campaigns: int
    completed_campaigns: int
    failed_campaigns: int
    invalid_campaigns: int
    started_campaigns: int
    pending_campaigns: int
    completed_steps: int
    artifacts: tuple[TrackAFileDigest, ...]
    recorded_at_utc: str

    def __post_init__(self) -> None:
        counts = (
            self.completed_campaigns,
            self.failed_campaigns,
            self.invalid_campaigns,
            self.started_campaigns,
            self.pending_campaigns,
        )
        if (
            self.protocol_version != PROTOCOL_VERSION
            or not isinstance(self.status, TrackAFinalStatus)
            or not isinstance(self.execution, ArtifactReference)
            or self.execution.name != "execution.json"
            or not isinstance(self.repetition_plan, ArtifactReference)
            or self.repetition_plan.name != "repetitions/plan.json"
            or type(self.scheduled_campaigns) is not int
            or self.scheduled_campaigns != len(TRACK_A_SCHEDULE)
            or any(type(value) is not int or value < 0 for value in counts)
            or sum(counts) != self.scheduled_campaigns
            or type(self.completed_steps) is not int
            or self.completed_steps < 0
            or not isinstance(self.artifacts, tuple)
            or not self.artifacts
            or not all(isinstance(item, TrackAFileDigest) for item in self.artifacts)
            or tuple(item.path for item in self.artifacts)
            != tuple(sorted({item.path for item in self.artifacts}))
        ):
            raise ValueError("invalid Track A final manifest")
        if self.status == TrackAFinalStatus.COMPLETE:
            if self.completed_campaigns != self.scheduled_campaigns or self.stop_reason is not None:
                raise ValueError("complete Track A manifest has incomplete slots or stop reason")
        elif not isinstance(self.stop_reason, str) or not self.stop_reason:
            raise ValueError("stopped Track A manifest requires an explicit reason")
        if datetime.fromisoformat(self.recorded_at_utc).utcoffset() is None:
            raise ValueError("Track A final timestamp requires a timezone")


@dataclass(frozen=True, slots=True)
class VerifiedTrackAFinal:
    manifest: TrackAFinalManifest
    final_manifest_sha256: str
    execution: VerifiedTrackAExecution


def _inventory(root: Path) -> tuple[TrackAFileDigest, ...]:
    records = []
    for path in sorted(root.rglob("*")):
        if path.name == FINAL_MANIFEST_NAME and path.parent == root:
            continue
        if path.is_symlink():
            raise ValueError("Track A evidence inventory cannot contain symlinks")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Track A evidence inventory requires regular files")
        content = _read_file(path)
        records.append(
            TrackAFileDigest(
                path.relative_to(root).as_posix(), sha256(content).hexdigest(), len(content)
            )
        )
    return tuple(records)


def finalize_track_a_execution(
    root: Path,
    *,
    expected_execution_sha256: str,
    stop_reason: str | None = None,
    protocol_config_path: Path | None = None,
) -> str:
    """Seal all available valid/invalid/prefix evidence without retry or deletion."""
    if (root / FINAL_MANIFEST_NAME).exists():
        raise ValueError("Track A execution is already finalized")
    verified = read_track_a_execution(
        root,
        expected_execution_sha256=expected_execution_sha256,
        protocol_config_path=protocol_config_path,
    )
    counts = Counter(slot.state for slot in verified.repetitions.slots)
    complete = counts[RunState.COMPLETED] == len(verified.repetitions.slots)
    if complete and stop_reason is not None:
        raise ValueError("complete Track A execution cannot have a stop reason")
    if not complete and (not isinstance(stop_reason, str) or not stop_reason):
        raise ValueError("incomplete Track A execution requires a stop reason")
    manifest = TrackAFinalManifest(
        PROTOCOL_VERSION,
        TrackAFinalStatus.COMPLETE if complete else TrackAFinalStatus.STOPPED,
        stop_reason,
        ArtifactReference("execution.json", verified.execution_sha256),
        ArtifactReference("repetitions/plan.json", verified.repetitions.plan_sha256),
        len(verified.repetitions.slots),
        counts[RunState.COMPLETED],
        counts[RunState.FAILED],
        counts[RunState.INVALID],
        counts[RunState.STARTED],
        counts[RunState.PENDING],
        sum(slot.completed_steps for slot in verified.repetitions.slots),
        _inventory(root),
        datetime.now(UTC).isoformat(),
    )
    return write_record(root / FINAL_MANIFEST_NAME, manifest)


def verify_track_a_final(
    root: Path,
    *,
    expected_final_manifest_sha256: str,
    protocol_config_path: Path | None = None,
) -> VerifiedTrackAFinal:
    """Independently verify the sealed artifact inventory and repetition accounting."""
    try:
        final_path = root / FINAL_MANIFEST_NAME
        digest = sha256(_read_file(final_path)).hexdigest()
        if digest != _digest(expected_final_manifest_sha256):
            raise ValueError("Track A final manifest checksum mismatch")
        manifest = read_record(final_path, TrackAFinalManifest, expected_sha256=digest)
        execution = read_track_a_execution(
            root,
            expected_execution_sha256=manifest.execution.sha256,
            protocol_config_path=protocol_config_path,
        )
        if manifest.repetition_plan.sha256 != execution.repetitions.plan_sha256:
            raise ValueError("Track A final manifest plan checksum mismatch")
        actual = _inventory(root)
        if actual != manifest.artifacts:
            raise ValueError("Track A final artifact inventory changed")
        counts = Counter(slot.state for slot in execution.repetitions.slots)
        expected_counts = (
            counts[RunState.COMPLETED],
            counts[RunState.FAILED],
            counts[RunState.INVALID],
            counts[RunState.STARTED],
            counts[RunState.PENDING],
        )
        if expected_counts != (
            manifest.completed_campaigns,
            manifest.failed_campaigns,
            manifest.invalid_campaigns,
            manifest.started_campaigns,
            manifest.pending_campaigns,
        ) or manifest.completed_steps != sum(
            slot.completed_steps for slot in execution.repetitions.slots
        ):
            raise ValueError("Track A final accounting differs from repetition evidence")
        return VerifiedTrackAFinal(manifest, digest, execution)
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        if isinstance(error, VerificationError):
            raise
        raise VerificationError(f"invalid Track A final evidence: {error}") from error


def nearest_rank_percentile(values: Sequence[float], probability: float) -> float:
    if not values or not 0 < probability <= 1:
        raise ValueError("nearest-rank percentile requires values and probability in (0,1]")
    ordered = sorted(values)
    return ordered[math.ceil(probability * len(ordered)) - 1]


def _descriptive(values: Sequence[float]) -> dict:
    if not values:
        return {"count": 0, "median": None, "p95_nearest_rank": None, "min": None, "max": None}
    return {
        "count": len(values),
        "median": median(values),
        "p95_nearest_rank": nearest_rank_percentile(values, 0.95),
        "min": min(values),
        "max": max(values),
    }


def _fingerprint_id(value: object) -> str:
    return sha256(canonical_json(value).encode("ascii")).hexdigest()


def summarize_track_a_records(
    records: tuple[SearchCampaignCompletedStep, ...],
    timing: PolicyCampaignTiming | None,
) -> dict:
    """Summarize one verified journal prefix; missing full-step timing stays unavailable."""
    if not isinstance(records, tuple) or not all(
        isinstance(record, SearchCampaignCompletedStep) for record in records
    ):
        raise ValueError("Track A summary requires verified completed-step records")
    if timing is not None and len(timing.steps) != len(records):
        raise ValueError("Track A timing count differs from journal records")
    signatures: set[str] = set()
    fingerprints: set[str] = set()
    signature_curve = []
    fingerprint_curve = []
    statuses = Counter({status.value: 0 for status in ExecutionStatus})
    contracts = Counter({contract.value: 0 for contract in ContractId})
    operators = Counter({operator.value: 0 for operator in MutationOperatorId})
    mutation_applied = 0
    first_contract_observation = None
    candidate_occurrences: list[dict[str, object]] = []
    initial_ids = {case.case_id for case in minimal_seed_corpus()}
    for record in records:
        step = record.step
        result = step.result
        signatures.add(_fingerprint_id(result.signature))
        for fingerprint in violation_fingerprints(result.violations):
            fingerprints.add(_fingerprint_id(fingerprint))
        signature_curve.append(len(signatures))
        fingerprint_curve.append(len(fingerprints))
        statuses[result.execution.status.value] += 1
        violated = False
        for verdict in result.violations:
            if verdict.violated:
                contracts[verdict.contract_id.value] += 1
                violated = True
        if violated and first_contract_observation is None:
            first_contract_observation = step.index + 1
        attempt = record.mutation_attempt
        if attempt is not None:
            operators[attempt.operator_id.value] += 1
            mutation_applied += int(attempt.applied)
        if (
            step.origin == CampaignOrigin.MUTATION
            and result.case.case_id not in initial_ids
            and any(
                verdict.contract_id == ContractId.C1
                and verdict.violated
                and any(
                    isinstance(evidence, IdentityEvidence)
                    and evidence.sentinel_path == "outside/sentinel.txt"
                    for evidence in verdict.evidence
                )
                for verdict in result.violations
            )
        ):
            candidate_occurrences.append({"step_index": step.index, "case_id": result.case.case_id})
    durations = () if timing is None else tuple(step.duration_seconds for step in timing.steps)
    mutation_attempts = sum(operators.values())
    return {
        "executions": len(records),
        "seed_executions": sum(record.step.origin == CampaignOrigin.SEED for record in records),
        "mutation_attempts": mutation_attempts,
        "mutation_operator_counts": dict(operators),
        "mutation_applied": mutation_applied,
        "mutation_noop": mutation_attempts - mutation_applied,
        "target_status_counts": dict(statuses),
        "contract_observation_counts": dict(contracts),
        "unique_state_signatures": len(signatures),
        "state_signature_ids": sorted(signatures),
        "state_signature_curve": signature_curve,
        "unique_violation_fingerprints": len(fingerprints),
        "violation_fingerprint_ids": sorted(fingerprints),
        "violation_fingerprint_curve": fingerprint_curve,
        "admission_eligible": sum(record.step.feedback.admission_eligible for record in records),
        "retained": sum(record.step.feedback.retained for record in records),
        "first_contract_observation_execution": first_contract_observation,
        "generic_n01_like_occurrences": candidate_occurrences,
        "generic_n01_like_unique_cases": len({item["case_id"] for item in candidate_occurrences}),
        "full_step_durations_seconds": list(durations),
        "full_step_seconds": _descriptive(durations),
        "timing_limitation": None
        if timing is not None
        else "full-step timing unavailable for non-complete journal prefix",
    }


def _directory_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        if item.is_symlink():
            raise VerificationError("Track A evidence storage contains a symlink")
        if item.is_file():
            total += item.stat().st_size
    return total


def _campaign_analysis(root: Path, slot, scheduled: PolicyScheduledRun) -> dict:
    directory = root / "repetitions" / slot.result_directory
    journal: PolicyJournalSnapshot | None = None
    if slot.claim is not None and (directory / "evidence").is_dir():
        journal = read_policy_journal(directory / "evidence")
    records = () if journal is None else journal.records
    timing = (
        None
        if journal is None or journal.completed_campaign is None
        else journal.completed_campaign.timing
    )
    summary = summarize_track_a_records(records, timing)
    nominations = ()
    if journal is not None and journal.complete and scheduled.arm_id.startswith("affected-"):
        nominations = nominate_n01_policy_candidates(directory / "evidence" / "timed" / "campaign")
    summary.update(
        run_index=slot.run_index,
        run_id=slot.run_id,
        arm_id=slot.arm_id,
        random_seed=slot.random_seed,
        state=slot.state.value,
        completed_steps=slot.completed_steps,
        planned_steps=scheduled.evaluation_config.campaign.execution_budget,
        controller_process_lifetime_peak_bytes=None
        if slot.controller_memory is None
        else slot.controller_memory.observation.lifetime_peak_resident_bytes,
        evidence_storage_bytes=_directory_bytes(directory),
        machine_candidate_nominations=len(nominations),
        machine_candidate_case_ids=[item.nomination.case.case_id for item in nominations],
        machine_candidate_occurrences=sum(len(item.nomination.occurrences) for item in nominations),
        candidate_interpretation=(
            "nomination-only; no 3+3 replay or human known-class disposition"
        ),
    )
    return summary


def _checkpoint_summary(campaigns: Sequence[dict], key: str) -> dict:
    result = {}
    for checkpoint in (4, 25, 50, 100, 150, 200):
        values = [item[key][checkpoint - 1] for item in campaigns if len(item[key]) >= checkpoint]
        result[str(checkpoint)] = _descriptive(values)
    return result


def _arm_analysis(arm_id: str, campaigns: Sequence[dict]) -> dict:
    states = Counter({state.value: 0 for state in RunState})
    statuses = Counter({status.value: 0 for status in ExecutionStatus})
    contracts = Counter({contract.value: 0 for contract in ContractId})
    operators = Counter({operator.value: 0 for operator in MutationOperatorId})
    signatures: set[str] = set()
    fingerprints: set[str] = set()
    timings = []
    memory = []
    candidate_ids: set[str] = set()
    for item in campaigns:
        states[item["state"]] += 1
        statuses.update(item["target_status_counts"])
        contracts.update(item["contract_observation_counts"])
        operators.update(item["mutation_operator_counts"])
        signatures.update(item["state_signature_ids"])
        fingerprints.update(item["violation_fingerprint_ids"])
        timings.extend(item["full_step_durations_seconds"])
        if item["controller_process_lifetime_peak_bytes"] is not None:
            memory.append(item["controller_process_lifetime_peak_bytes"])
        candidate_ids.update(item["machine_candidate_case_ids"])
    actual = sum(item["executions"] for item in campaigns)
    planned = len(campaigns) * EXECUTION_BUDGET
    complete = states[RunState.COMPLETED.value]
    infrastructure_noncomplete = len(campaigns) - complete
    infrastructure_failures = sum(
        states[state.value] for state in (RunState.FAILED, RunState.INVALID, RunState.STARTED)
    )
    return {
        "arm_id": arm_id,
        "scheduled_campaigns": len(campaigns),
        "campaign_state_counts": dict(states),
        "completed_campaigns": complete,
        "campaign_completion_rate": complete / len(campaigns),
        "actual_executions": actual,
        "planned_executions": planned,
        "execution_completion_rate": actual / planned,
        "target_status_counts": dict(statuses),
        "target_rejection_rate": statuses[ExecutionStatus.REJECTED.value] / actual
        if actual
        else None,
        "target_timeout_rate": statuses[ExecutionStatus.TIMED_OUT.value] / actual
        if actual
        else None,
        "infrastructure_noncomplete_campaigns": infrastructure_noncomplete,
        "infrastructure_noncomplete_rate": infrastructure_noncomplete / len(campaigns),
        "infrastructure_failure_campaigns": infrastructure_failures,
        "infrastructure_failure_rate": infrastructure_failures / len(campaigns),
        "pending_campaigns": states[RunState.PENDING.value],
        "contract_observation_counts": dict(contracts),
        "mutation_operator_counts": dict(operators),
        "mutation_applied": sum(item["mutation_applied"] for item in campaigns),
        "mutation_noop": sum(item["mutation_noop"] for item in campaigns),
        "arm_union_unique_state_signatures": len(signatures),
        "arm_union_unique_violation_fingerprints": len(fingerprints),
        "state_signature_discovery": _checkpoint_summary(campaigns, "state_signature_curve"),
        "violation_fingerprint_discovery": _checkpoint_summary(
            campaigns, "violation_fingerprint_curve"
        ),
        "machine_candidate_nominations": sum(
            item["machine_candidate_nominations"] for item in campaigns
        ),
        "machine_candidate_unique_case_ids": len(candidate_ids),
        "full_step_seconds": _descriptive(timings),
        "controller_process_lifetime_peak_bytes": _descriptive(memory),
        "evidence_storage_bytes": sum(item["evidence_storage_bytes"] for item in campaigns),
        "first_contract_observation_execution_by_campaign": [
            {
                "run_id": item["run_id"],
                "execution": item["first_contract_observation_execution"],
            }
            for item in campaigns
        ],
    }


def analyze_track_a(
    root: Path,
    *,
    expected_final_manifest_sha256: str,
    protocol_config_path: Path | None = None,
) -> dict:
    """Derive exploratory statistics only after fresh full-tree verification."""
    verified = verify_track_a_final(
        root,
        expected_final_manifest_sha256=expected_final_manifest_sha256,
        protocol_config_path=protocol_config_path,
    )
    snapshot = verified.execution.repetitions
    campaigns = [
        _campaign_analysis(root, slot, scheduled)
        for slot, scheduled in zip(snapshot.slots, snapshot.plan.runs, strict=True)
    ]
    arms = {
        arm: _arm_analysis(arm, [item for item in campaigns if item["arm_id"] == arm])
        for arm in _ARM_POLICY
    }
    comparison = {
        arm: {
            "completed_campaigns": arms[arm]["completed_campaigns"],
            "actual_executions": arms[arm]["actual_executions"],
            "arm_union_unique_state_signatures": arms[arm]["arm_union_unique_state_signatures"],
            "arm_union_unique_violation_fingerprints": arms[arm][
                "arm_union_unique_violation_fingerprints"
            ],
            "machine_candidate_nominations": arms[arm]["machine_candidate_nominations"],
            "full_step_seconds": arms[arm]["full_step_seconds"],
        }
        for arm in ("affected-b0", "affected-b1", "affected-b3")
    }
    all_complete = verified.manifest.status == TrackAFinalStatus.COMPLETE
    return {
        "schema_version": 1,
        "classification": "exploratory-final-state-feasibility-analysis",
        "protocol_version": PROTOCOL_VERSION,
        "evidence_stage": "RAW ONLY",
        "reproducibility_support": (
            "complete-checksummed-independent-reader"
            if all_complete
            else "incomplete-checksummed-independent-reader"
        ),
        "final_manifest_sha256": verified.final_manifest_sha256,
        "execution_manifest_sha256": verified.execution.execution_sha256,
        "plan_sha256": snapshot.plan_sha256,
        "protocol_config_sha256": verified.execution.protocol_config_sha256,
        "source_revision": verified.execution.manifest.source_revision,
        "final_status": verified.manifest.status.value,
        "stop_reason": verified.manifest.stop_reason,
        "campaigns": campaigns,
        "arms": arms,
        "affected_policy_exploratory_comparison": comparison,
        "evidence_storage_bytes": _directory_bytes(root),
        "claim_boundary": {
            "final_state_feedback_only": True,
            "state_novelty_is_not_vulnerability": True,
            "machine_match_is_not_confirmed_rediscovery": True,
            "formal_superiority": "not_evaluated",
            "central_intermediate_state_hypothesis": "not_evaluated",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("root", type=Path)
    verify.add_argument("--final-manifest-sha256", required=True)
    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("root", type=Path)
    analyze.add_argument("--final-manifest-sha256", required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("root", type=Path)
    finalize.add_argument("--execution-sha256", required=True)
    finalize.add_argument("--stop-reason")
    args = parser.parse_args()
    try:
        if args.operation == "finalize":
            digest = finalize_track_a_execution(
                args.root,
                expected_execution_sha256=args.execution_sha256,
                stop_reason=args.stop_reason,
            )
            result = {"classification": "track-a-finalized-v1", "final_manifest_sha256": digest}
        elif args.operation == "verify":
            verified = verify_track_a_final(
                args.root,
                expected_final_manifest_sha256=args.final_manifest_sha256,
            )
            result = {
                "classification": "verified-track-a-final-evidence-v1",
                "final_manifest_sha256": verified.final_manifest_sha256,
                "status": verified.manifest.status.value,
                "scheduled_campaigns": verified.manifest.scheduled_campaigns,
                "completed_campaigns": verified.manifest.completed_campaigns,
                "completed_steps": verified.manifest.completed_steps,
            }
        else:
            result = analyze_track_a(
                args.root,
                expected_final_manifest_sha256=args.final_manifest_sha256,
            )
    except (VerificationError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json_bytes(result).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
