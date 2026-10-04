"""Deterministic structured evidence export of a completed bounded campaign."""

import ctypes
import json
import os
import platform
import sys
import tempfile
from dataclasses import asdict
from hashlib import file_digest, sha256
from pathlib import Path

from inodefence.campaign import CampaignResult
from inodefence.model import canonical_json


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_directory(staged: Path, destination: Path) -> None:
    """Linux renameat2(RENAME_NOREPLACE): even a concurrent empty dir stays intact.

    No ordinary rename fallback: that could overwrite an existing destination.
    The trusted caller owns the parent directory; both paths are siblings.
    """
    if sys.platform != "linux":
        raise NotImplementedError("evidence publication requires supported Linux")
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename = libc.renameat2
    except AttributeError as error:
        raise NotImplementedError(
            "libc renameat2 is required for no-replace publication"
        ) from error
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        if rename(
            descriptor, os.fsencode(staged.name), descriptor, os.fsencode(destination.name), 1
        ):
            number = ctypes.get_errno()
            raise OSError(number, os.strerror(number), str(destination))
    finally:
        os.close(descriptor)


def _write_file(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def export_campaign(
    result: CampaignResult, destination: Path, *, experiment_config_json: str | None = None
) -> tuple[Path, Path]:
    """Write manifest.json and canonical steps.jsonl into a new directory.

    Same completed result and exporter environment produce identical bytes,
    independent of destination. Raw allocation/timing evidence is preserved;
    separate campaign runs need not have byte-identical exports. Execution
    contexts come from every RunResult in first-occurrence order. Environment
    information describes this exporter, not the earlier target execution.
    Manifest v4 exports the stored pre-execution provenance unchanged. Observed
    execution_contexts remain separate evidence, including any caller-built drift.

    Optional config JSON must hash to the result's stored config ID. Its file is
    published with the evidence, never appended afterwards. Files are flushed,
    synced and checksummed in a temporary sibling before Linux no-replace atomic
    publication. The containing directory is then synced. No unsupported-platform
    fallback or overwrite is permitted. Before-publication errors clean staging
    and leave the final destination absent. Hard interruption can leave staging;
    a post-publication directory-sync error leaves the complete published bundle
    and propagates. This is no database, reader or resume/checkpoint facility.
    """
    config_bytes = None
    if experiment_config_json is not None:
        encoded_config = experiment_config_json.encode("ascii")
        if sha256(encoded_config).hexdigest() != result.experiment_config_id:
            raise ValueError("exported config JSON must match the stored experiment_config_id")
        config_bytes = encoded_config + b"\n"
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".inodefence-export-", dir=destination.parent) as name:
        staged = Path(name)
        _write_campaign(result, staged, config_bytes)
        _sync_directory(staged)
        _publish_directory(staged, destination)
        _sync_directory(destination.parent)
    return destination / "manifest.json", destination / "steps.jsonl"


def _write_campaign(result: CampaignResult, destination: Path, config_bytes: bytes | None) -> None:
    contexts = tuple(
        dict.fromkeys(
            (
                step.result.execution.target_id,
                step.result.execution.target_version,
                step.result.archive_format,
                step.result.execution.timeout_seconds,
            )
            for step in result.steps
        )
    )
    steps_path = destination / "steps.jsonl"
    digest = sha256()
    # Encode one step at a time rather than duplicating the whole campaign in memory.
    with steps_path.open("xb") as stream:
        for step in result.steps:
            line = (canonical_json(step) + "\n").encode("ascii")
            stream.write(line)
            digest.update(line)
        stream.flush()
        os.fsync(stream.fileno())
    with steps_path.open("rb") as stream:
        if file_digest(stream, "sha256").hexdigest() != digest.hexdigest():
            raise OSError("staged steps checksum differs from generated evidence")
    if config_bytes is not None:
        _write_file(destination / "experiment.json", config_bytes)
        if (destination / "experiment.json").read_bytes() != config_bytes:
            raise OSError("staged config differs from stored configuration")
    manifest = {
        "format": "inodefence-bounded-campaign",
        "schema_version": 4,
        "evidence_classification": "raw-campaign",
        "config": asdict(result.config),
        "experiment_config_id": result.experiment_config_id,
        "experiment_config_file": "experiment.json" if config_bytes is not None else None,
        "experiment_config_sha256": sha256(config_bytes).hexdigest()
        if config_bytes is not None
        else None,
        "execution_provenance": asdict(result.provenance),
        "initial_case_ids": result.initial_case_ids,
        "number_of_steps": len(result.steps),
        "final_corpus_stats": asdict(result.final_corpus_stats),
        "retained_case_ids": result.retained_case_ids,
        "execution_contexts": [
            {
                "target_id": target_id,
                "target_version": target_version,
                "builder_format": builder_format,
                "timeout_seconds": timeout,
            }
            for target_id, target_version, builder_format, timeout in contexts
        ],
        "export_environment": {
            "python_version": platform.python_version(),
            "system": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
        },
        "steps_file": steps_path.name,
        "steps_sha256": digest.hexdigest(),
    }
    encoded = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
    manifest_path = destination / "manifest.json"
    manifest_bytes = (encoded + "\n").encode("ascii")
    _write_file(manifest_path, manifest_bytes)
    if manifest_path.read_bytes() != manifest_bytes:
        raise OSError("staged manifest differs from generated evidence")
