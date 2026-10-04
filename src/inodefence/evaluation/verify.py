"""Fail-closed reader for completed manifest-v4 campaign exports."""

import os
import re
import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.campaign import CampaignConfig, CampaignOrigin, CampaignResult, CampaignStep
from inodefence.feedback import Corpus, CorpusStats, state_signature
from inodefence.model import RunResult, SnapshotPhase, canonical_json
from inodefence.model.provenance import ExecutionProvenance, ExecutionSafety
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts

from .encoding import decode, object_fields, read_json

_MANIFEST_FIELDS = {
    "format",
    "schema_version",
    "evidence_classification",
    "config",
    "experiment_config_id",
    "experiment_config_file",
    "experiment_config_sha256",
    "execution_provenance",
    "initial_case_ids",
    "number_of_steps",
    "final_corpus_stats",
    "retained_case_ids",
    "execution_contexts",
    "export_environment",
    "steps_file",
    "steps_sha256",
}


class VerificationError(ValueError):
    """The bundle cannot be consumed as verified evidence."""


@dataclass(frozen=True, slots=True)
class VerifiedCampaign:
    """Immutable verified evidence, not authenticated authorship or a finding.

    The original manifest bytes and digest anchor the complete input consumed
    by this reader. A caller needing authenticity must supply a trusted digest.
    """

    result: CampaignResult
    manifest_bytes: bytes
    manifest_sha256: str
    steps_sha256: str


def _digest(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("expected lowercase SHA-256")
    return value


def _read_file(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("evidence must be a regular file")
        return stream.read()


def verify_run(result: RunResult) -> None:
    """Check current builder and derivations without executing a target."""
    if result.archive_format != BUILDER_FORMAT:
        raise ValueError("unsupported builder format")
    if sha256(build_tar(result.case)).hexdigest() != result.archive_sha256:
        raise ValueError("regenerated TAR checksum mismatch")
    before, after = result.before, result.after
    archive = before.get("archive/input.tar")
    if archive is None or archive.content_digest != result.archive_sha256:
        raise ValueError("BEFORE archive digest differs from TAR")
    if (
        before.phase != SnapshotPhase.BEFORE
        or after.phase != SnapshotPhase.AFTER
        or before.sandbox_root != after.sandbox_root
        or before.protected_paths != after.protected_paths
    ):
        raise ValueError("invalid snapshot lifecycle")
    if result.changes != compare_states(before, after):
        raise ValueError("recorded changes differ from snapshots")
    if result.signature != state_signature(before, after):
        raise ValueError("recorded signature differs from snapshots")
    if result.violations != evaluate_contracts(before, after):
        raise ValueError("recorded contracts differ from snapshots")


def verify_binding(result: RunResult, provenance: ExecutionProvenance) -> None:
    """Verify target/isolation/sentinel configuration against actual evidence."""
    execution = result.execution
    target = provenance.target
    if (execution.target_id, execution.target_version, execution.timeout_seconds) != (
        target.target_id,
        target.target_version,
        target.timeout_seconds,
    ):
        raise ValueError("target result differs from frozen provenance")
    if (
        provenance.isolation is None
        and target.execution_safety != ExecutionSafety.TRUSTED_REFERENCE
    ):
        raise ValueError("missing required isolation provenance")
    if result.before.protected_paths != tuple(
        f"outside/{item.name}" for item in provenance.sentinels
    ):
        raise ValueError("sentinel configuration differs from snapshots")
    for sentinel in provenance.sentinels:
        obj = result.before.get(f"outside/{sentinel.name}")
        if (
            obj is None
            or obj.content_digest != sentinel.content_sha256
            or obj.mode != sentinel.mode
        ):
            raise ValueError("BEFORE sentinel differs from configuration")


def verify_campaign(
    directory: Path, *, expected_manifest_sha256: str | None = None
) -> VerifiedCampaign:
    """Read all-or-nothing; never yield a record before the whole bundle passes.

    Supports only the current manifest v4 / step v1 / pinned builder. No target
    execution, source checkout, mutation replay or retrospective qualification.
    Caller owns the directory's parents; symlink bundle/files are rejected.
    """
    try:
        return _verify(directory, expected_manifest_sha256)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid campaign evidence: {error}") from error


def _verify(directory: Path, expected_digest: str | None) -> VerifiedCampaign:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("expected a completed experiment directory")
    manifest_bytes = _read_file(directory / "manifest.json")
    manifest_digest = sha256(manifest_bytes).hexdigest()
    if expected_digest is not None and manifest_digest != _digest(expected_digest):
        raise ValueError("manifest checksum mismatch")
    manifest = object_fields(read_json(manifest_bytes), _MANIFEST_FIELDS)
    if (
        type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 4
        or manifest["format"] != "inodefence-bounded-campaign"
        or manifest["evidence_classification"] != "raw-campaign"
        or manifest["steps_file"] != "steps.jsonl"
    ):
        raise ValueError("unsupported manifest schema/format")
    config = decode(CampaignConfig, manifest["config"])
    provenance = decode(ExecutionProvenance, manifest["execution_provenance"])
    config_id = manifest["experiment_config_id"]
    if config_id is not None:
        _digest(config_id)
    if manifest["experiment_config_file"] is None:
        if manifest["experiment_config_sha256"] is not None:
            raise ValueError("config checksum without a config file")
    else:
        if manifest["experiment_config_file"] != "experiment.json" or config_id is None:
            raise ValueError("unsupported/unbound experiment config")
        content = _read_file(directory / "experiment.json")
        if sha256(content).hexdigest() != _digest(manifest["experiment_config_sha256"]):
            raise ValueError("experiment config file checksum mismatch")
        if not content.endswith(b"\n") or sha256(content[:-1]).hexdigest() != config_id:
            raise ValueError("experiment config identifier mismatch")
        read_json(content)
    raw_steps = _read_file(directory / "steps.jsonl")
    steps_digest = sha256(raw_steps).hexdigest()
    if steps_digest != _digest(manifest["steps_sha256"]):
        raise ValueError("steps checksum mismatch")
    if not raw_steps.endswith(b"\n"):
        raise ValueError("incomplete steps file")
    lines = raw_steps[:-1].split(b"\n")
    count = manifest["number_of_steps"]
    if type(count) is not int or count != len(lines) or count != config.execution_budget:
        raise ValueError("record count/budget mismatch")
    initial_ids = decode(tuple[str, ...], manifest["initial_case_ids"])
    if not initial_ids or len(initial_ids) > count or len(set(initial_ids)) != len(initial_ids):
        raise ValueError("invalid initial case identifiers")
    corpus, steps, contexts = Corpus(), [], []
    for index, line in enumerate(lines):
        envelope = object_fields(read_json(line), {"model", "schema_version", "value"})
        if (
            envelope["model"] != "CampaignStep"
            or type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != 1
        ):
            raise ValueError("unsupported step schema")
        step = decode(CampaignStep, envelope["value"])
        if canonical_json(step).encode("ascii") != line:
            raise ValueError("noncanonical step representation")
        if step.index != index:
            raise ValueError("step index mismatch")
        case_id = step.result.case.case_id
        if step.feedback.case_id != case_id:
            raise ValueError("recomputed case_id mismatch")
        if index < len(initial_ids):
            if (
                step.origin != CampaignOrigin.SEED
                or step.parent_case_id is not None
                or case_id != initial_ids[index]
            ):
                raise ValueError("seed lineage/case_id mismatch")
        elif step.origin != CampaignOrigin.MUTATION or step.parent_case_id not in {
            entry.case.case_id for entry in corpus.entries
        }:
            raise ValueError("mutation parent was not previously retained")
        verify_run(step.result)
        verify_binding(step.result, provenance)
        execution = step.result.execution
        if step.feedback != corpus.consider(step.result):
            raise ValueError("feedback evidence mismatch")
        context = {
            "target_id": execution.target_id,
            "target_version": execution.target_version,
            "timeout_seconds": execution.timeout_seconds,
            "builder_format": BUILDER_FORMAT,
        }
        if context not in contexts:
            contexts.append(context)
        steps.append(step)
    if manifest["execution_contexts"] != contexts:
        raise ValueError("execution contexts mismatch")
    stats = decode(CorpusStats, manifest["final_corpus_stats"])
    retained = decode(tuple[str, ...], manifest["retained_case_ids"])
    if stats != corpus.stats or retained != tuple(entry.case.case_id for entry in corpus.entries):
        raise ValueError("final corpus evidence mismatch")
    environment = object_fields(
        manifest["export_environment"], {"python_version", "system", "release", "architecture"}
    )
    if any(not isinstance(value, str) for value in environment.values()):
        raise ValueError("invalid exporter environment")
    result = CampaignResult(
        config, initial_ids, tuple(steps), stats, retained, provenance, config_id
    )
    return VerifiedCampaign(result, manifest_bytes, manifest_digest, steps_digest)
