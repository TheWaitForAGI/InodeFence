"""One tiny BENIGN plumbing campaign; raw engineering evidence, no effectiveness claim."""

import json
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from scripts.benign_validation import preserve_unexpected, validate_benign_case

from inodefence.campaign import CampaignConfig
from inodefence.campaign_export import export_campaign
from inodefence.experiment_config import (
    FEEDBACK_POLICY,
    MUTATION_POLICY,
    SEED_PROFILE,
    ExperimentConfig,
    run_configured_campaign,
)
from inodefence.generator import minimal_seed_corpus
from inodefence.model import EntryType, ObjectType, canonical_json
from inodefence.pipeline import run_case
from inodefence.provenance import freeze_provenance
from inodefence.runtime import SentinelSpec, runtime_root
from inodefence.targets.node_tar import NodeTarTarget


def test_tiny_benign_configured_node_campaign(
    container_backend, container_image, campaign_evidence, monkeypatch
):
    roots_before = set(runtime_root().iterdir())
    identities = []
    requests = []
    frozen = []
    original_prepare = type(container_backend).prepare

    @contextmanager
    def tracked_prepare(backend, request):
        with original_prepare(backend, request) as prepared:
            identities.append(prepared.identity)
            requests.append(request)
            yield prepared
            state = backend.inspect(prepared.identity)["State"]
            assert not state["Running"] and state["Pid"] == 0
            assert backend.client.run(("container", "top", prepared.identity), 10).returncode != 0
        assert backend.client.run(("container", "inspect", prepared.identity), 10).returncode != 0

    monkeypatch.setattr(type(container_backend), "prepare", tracked_prepare)
    target = NodeTarTarget.bind(container_backend, container_image, timeout_seconds=10)
    assert target.provenance.target_version == "node=22.22.0;tar=7.5.22"
    seeds = minimal_seed_corpus()
    config = ExperimentConfig(
        target.provenance,
        SEED_PROFILE,
        tuple(case.case_id for case in seeds),
        CampaignConfig(11, 8),
        MUTATION_POLICY,
        FEEDBACK_POLICY,
        (SentinelSpec(),),
        "ubuntu2404-python312-node-container-benign-v1",
        target.isolation_policy,
    )
    encoded_config = config.to_json()
    assert ExperimentConfig.from_json(encoded_config) == config

    def freeze(*args, **kwargs):
        assert not frozen
        value = freeze_provenance(*args, **kwargs)
        frozen.append(value)
        return value

    def guarded_run(case, adapter, *, sentinels):
        # Validation-only input guard: never alter RNG, mutation, budget or target outcomes.
        validate_benign_case(case)
        assert frozen and frozen[0].isolation is not None
        result = run_case(case, adapter, sentinels=sentinels)
        preserve_unexpected(result, frozen[0], encoded_config, campaign_evidence)
        return result

    monkeypatch.setattr("inodefence.campaign.freeze_provenance", freeze)
    monkeypatch.setattr("inodefence.campaign.run_case", guarded_run)
    result = run_configured_campaign(config, seeds, target)
    assert result.provenance is frozen[0]
    assert result.experiment_config_id == config.config_id
    assert result.provenance.isolation is not None
    assert result.provenance.isolation.policy == config.isolation
    assert result.provenance.isolation.policy.image_id == container_image
    assert len(result.steps) == 8
    assert [step.index for step in result.steps] == list(range(8))
    admitted = set()
    for step in result.steps:
        assert step.result.signature.schema_version == 3
        input_before = step.result.before.get("archive/input.tar")
        input_after = step.result.after.get("archive/input.tar")
        assert input_before is not None and input_after is not None
        assert (
            input_before.content_digest == input_after.content_digest == step.result.archive_sha256
        )
        if step.index < 4:
            assert step.parent_case_id is None
            for entry in seeds[step.index].entries:
                if entry.entry_type == EntryType.REGULAR:
                    assert entry.content is not None
                    observed = step.result.after.get("extract/" + entry.path)
                    assert observed is not None and observed.object_type == ObjectType.REGULAR
                    assert observed.content_digest == sha256(entry.content).hexdigest()
        else:
            assert step.parent_case_id in admitted
        if step.feedback.retained:
            admitted.add(step.feedback.case_id)
        assert not Path(step.result.after.sandbox_root).exists()
        signature = canonical_json(step.result.signature)
        assert container_image not in signature and config.config_id not in signature
    # Bind discovery + pre-freeze verification + eight per-run verifications + eight archives.
    assert len(identities) == len(set(identities)) == 18
    assert sum("--identify" in request.command for request in requests) == 10
    assert sum("--identify" not in request.command for request in requests) == 8
    assert all(not request.run_root.exists() for request in requests)
    assert set(runtime_root().iterdir()) == roots_before
    manifest, steps = export_campaign(
        result, campaign_evidence, experiment_config_json=encoded_config
    )
    manifest_value = json.loads(manifest.read_bytes())
    assert manifest_value["experiment_config_id"] == config.config_id
    assert manifest_value["schema_version"] == 4
    isolation = manifest_value["execution_provenance"]["isolation"]
    assert isolation["schema_version"] == 2
    assert isolation["artifact_origin"] == "image-identification-v1"
    assert isolation["artifacts"] == [
        {"name": item.name, "sha256": item.sha256} for item in target.invocation.artifacts
    ]
    assert manifest_value["experiment_config_file"] == "experiment.json"
    assert (
        manifest_value["experiment_config_sha256"]
        == sha256((campaign_evidence / "experiment.json").read_bytes()).hexdigest()
    )
    assert (
        manifest_value["execution_provenance"]
        == json.loads(canonical_json(result.provenance))["value"]
    )
    assert manifest_value["steps_sha256"] == sha256(steps.read_bytes()).hexdigest()
    assert steps.read_text().splitlines() == [canonical_json(step) for step in result.steps]
    assert all(
        json.loads(line)["value"]["index"] == index
        for index, line in enumerate(steps.read_text().splitlines())
    )
    assert all(
        json.loads(line)["value"]["result"]["signature"]["schema_version"] == 3
        for line in steps.read_text().splitlines()
    )
    summary = {
        "config_id": config.config_id,
        "target": asdict(target.provenance),
        "image_id": container_image,
        "isolation": asdict(result.provenance.isolation),
        "executions": len(result.steps),
        "statuses": dict(Counter(step.result.execution.status for step in result.steps)),
        "corpus_stats": asdict(result.final_corpus_stats),
        "violation_fingerprints": [],
        "retained_case_ids": result.retained_case_ids,
        "containers_created": len(identities),
        "containers_removed": len(identities),
        "archive_contexts": 8,
        "runtime_cleanup": True,
        "steps_sha256": manifest_value["steps_sha256"],
        "evidence": str(campaign_evidence),
    }
    print("INODEFENCE_BENIGN_SMOKE=" + json.dumps(summary, sort_keys=True))
