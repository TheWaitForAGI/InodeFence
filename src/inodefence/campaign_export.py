"""Deterministic structured evidence export of a completed bounded campaign."""

import json
import platform
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from inodefence.campaign import CampaignResult
from inodefence.model import canonical_json


def export_campaign(result: CampaignResult, destination: Path) -> tuple[Path, Path]:
    """Write manifest.json and canonical steps.jsonl into a new directory.

    Same completed result and exporter environment produce identical bytes,
    independent of destination. Raw allocation/timing evidence is preserved;
    separate campaign runs need not have byte-identical exports. Execution
    contexts come from every RunResult in first-occurrence order. Environment
    information describes this exporter, not the earlier target execution.
    Manifest v2 exports the stored pre-execution provenance unchanged. Observed
    execution_contexts remain separate evidence, including any caller-built drift.

    Existing destinations are rejected. IO/encoding exceptions propagate and
    may leave partial files; the manifest is written last. This is no database,
    reader, resume/checkpoint facility or promotion to validated analysis.
    """
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
    destination.mkdir(parents=True, exist_ok=False)
    steps_path = destination / "steps.jsonl"
    digest = sha256()
    # Encode one step at a time rather than duplicating the whole campaign in memory.
    with steps_path.open("xb") as stream:
        for step in result.steps:
            line = (canonical_json(step) + "\n").encode("ascii")
            stream.write(line)
            digest.update(line)
    manifest = {
        "format": "inodefence-bounded-campaign",
        "schema_version": 2,
        "evidence_classification": "raw-campaign",
        "config": asdict(result.config),
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
    with manifest_path.open("xb") as stream:
        stream.write((encoded + "\n").encode("ascii"))
    return manifest_path, steps_path
