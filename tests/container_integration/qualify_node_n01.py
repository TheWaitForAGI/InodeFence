"""N01 isolated qualification; known-class control, not a fuzzing result."""

import json
import os
import random
import subprocess
import traceback
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.feedback import state_signature
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ContractId, EntryType, RunResult, SnapshotPhase, canonical_json
from inodefence.mutator.dispatch import (
    MutationOperatorId,
    mutate_attempt_with_policy,
)
from inodefence.mutator.policy import MutationPolicy
from inodefence.observer import capture_state, compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.pipeline import run_case
from inodefence.provenance import capture_environment, capture_source
from inodefence.runtime import SentinelSpec, disposable_sandbox
from inodefence.targets.node_tar import NodeTarTarget

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ID = "n01-node-tar-historical-qualification-v1"
EXPECTED_VERSIONS = ("7.5.2", "7.5.3")
MUTATION_SEED = 2450
REPETITIONS = 5
ROOT_SENTINEL = "a"
ROOT_SENTINEL_CONTENT = b"inodefence n01 controlled sentinel\n"


def _encoded(value: object) -> dict:
    return json.loads(canonical_json(value))


@contextmanager
def _root_sentinel_sandbox():
    """Add an explicit root-level EXTERNAL sentinel addressable as ../a."""
    with disposable_sandbox((SentinelSpec("unused"),)) as base:
        sentinel = base.root / ROOT_SENTINEL
        with sentinel.open("xb") as stream:
            stream.write(ROOT_SENTINEL_CONTENT)
        sentinel.chmod(0o600)
        yield replace(base, protected_paths=(ROOT_SENTINEL,))


def _run_root_sentinel_case(case, target) -> RunResult:
    archive = build_tar(case)
    with _root_sentinel_sandbox() as sandbox:
        sandbox.archive_path.write_bytes(archive)
        with target.prepare(sandbox.archive_path, sandbox.extraction_root) as execute:
            before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
            execution = execute()
            after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
            return RunResult(
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


def _oracle_control(create_alias: bool) -> dict:
    with _root_sentinel_sandbox() as sandbox:
        before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
        if create_alias:
            os.link(sandbox.root / ROOT_SENTINEL, sandbox.extraction_root / "control-alias")
        after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
        verdicts = evaluate_contracts(before, after)
        return {
            "create_alias": create_alias,
            "before": _encoded(before),
            "after": _encoded(after),
            "verdicts": [_encoded(verdict) for verdict in verdicts],
        }


def _violated(result: RunResult, contract_id: ContractId) -> bool:
    return next(
        verdict.violated for verdict in result.violations if verdict.contract_id == contract_id
    )


def _qualification_record(result: RunResult) -> dict:
    sentinel = result.after.get(ROOT_SENTINEL)
    alias = result.after.get("extract/b.txt")
    return {
        "result": _encoded(result),
        "status": result.execution.status,
        "duration_seconds": result.execution.duration_seconds,
        "violated_contracts": [
            verdict.contract_id for verdict in result.violations if verdict.violated
        ],
        "sentinel_present": sentinel is not None,
        "alias_present": alias is not None,
        "alias_matches_sentinel": (
            sentinel is not None and alias is not None and sentinel.identity == alias.identity
        ),
    }


def _environment() -> dict:
    status: dict[str, str] = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        name, separator, value = line.partition(":")
        if separator and name in {"CapEff", "NoNewPrivs", "Seccomp"}:
            status[name] = value.strip()
    mount = subprocess.run(
        ("findmnt", "-J", "-T", "/var/lib/inodefence", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"),
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {
        "provenance": _encoded(capture_environment()),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "process_status": status,
        "runtime_mount": json.loads(mount.stdout),
    }


def _write_evidence(path: Path, evidence: dict) -> None:
    encoded = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    print(
        "INODEFENCE_N01_QUALIFICATION="
        + json.dumps(
            {"path": str(path), "sha256": sha256(encoded).hexdigest(), "bytes": len(encoded)},
            sort_keys=True,
        )
    )


def test_n01_isolated_runtime_oracle_reachability_and_pair(
    container_backend, container_images, campaign_evidence
) -> None:
    started = datetime.now(UTC)
    evidence: dict = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "evidence_tier": "RAW_ONLY",
        "started_at_utc": started.isoformat(),
        "source": _encoded(capture_source(ROOT)),
        "environment": _environment(),
        "config": {
            "candidate_id": "N01",
            "versions": list(EXPECTED_VERSIONS),
            "mutation_policy": MutationPolicy.M1,
            "mutation_seed": MUTATION_SEED,
            "repetitions": REPETITIONS,
            "timeout_seconds": 10,
            "root_sentinel": ROOT_SENTINEL,
            "root_sentinel_sha256": sha256(ROOT_SENTINEL_CONTENT).hexdigest(),
            "root_sentinel_mode": 0o600,
            "root_sentinel_region": "external",
            "root_sentinel_target_text": "../a",
        },
    }
    try:
        assert len(container_images) == 2
        targets = [
            NodeTarTarget.bind(container_backend, image, timeout_seconds=10)
            for image in container_images
        ]
        invocations = []
        for target in targets:
            assert isinstance(target.invocation, NodeTarTarget)
            invocations.append(target.invocation)
        assert tuple(invocation.tar_version for invocation in invocations) == EXPECTED_VERSIONS
        evidence["targets"] = [
            {
                "invocation": _encoded(invocation),
                "isolation": _encoded(target.capture_isolation()),
            }
            for target, invocation in zip(targets, invocations, strict=True)
        ]

        negative_control = _oracle_control(False)
        positive_control = _oracle_control(True)
        negative_violations = [item["value"]["violated"] for item in negative_control["verdicts"]]
        positive_by_contract = {
            item["value"]["contract_id"]: item["value"]["violated"]
            for item in positive_control["verdicts"]
        }
        assert not any(negative_violations)
        assert positive_by_contract[ContractId.C1] and positive_by_contract[ContractId.C2]
        evidence["oracle_controls"] = {
            "unchanged_negative": negative_control,
            "harness_alias_positive": positive_control,
        }

        parent = minimal_seed_corpus()[2]
        attempt = mutate_attempt_with_policy(
            parent, random.Random(MUTATION_SEED), MutationPolicy.M1
        )
        assert attempt.operator_id == MutationOperatorId.MUTATE_LINK_TARGET
        assert attempt.applied
        hardlinks = [
            entry for entry in attempt.child_case.entries if entry.entry_type == EntryType.HARDLINK
        ]
        assert len(hardlinks) == 1 and hardlinks[0].link_target == "../a"
        evidence["reachability"] = {
            "parent": _encoded(parent),
            "attempt": _encoded(attempt),
            "qualified_case": _encoded(attempt.child_case),
            "archive_sha256": sha256(build_tar(attempt.child_case)).hexdigest(),
        }

        benign: dict[str, list[dict]] = {}
        for version, target in zip(EXPECTED_VERSIONS, targets, strict=True):
            benign[version] = []
            for case in minimal_seed_corpus():
                result = run_case(case, target)
                assert result.execution.status == "success"
                assert not any(verdict.violated for verdict in result.violations)
                benign[version].append(_qualification_record(result))
        evidence["benign_compatibility"] = benign

        pair: dict[str, list[dict]] = {}
        for version, target in zip(EXPECTED_VERSIONS, targets, strict=True):
            pair[version] = [
                _qualification_record(_run_root_sentinel_case(attempt.child_case, target))
                for _ in range(REPETITIONS)
            ]
        for record in pair["7.5.2"]:
            assert record["status"] == "success"
            assert record["alias_matches_sentinel"]
            assert set(record["violated_contracts"]) == {ContractId.C1, ContractId.C2}
        for record in pair["7.5.3"]:
            assert record["status"] not in {"failed", "timed_out"}
            assert not record["alias_matches_sentinel"]
            assert not record["violated_contracts"]
        evidence["known_class_pair"] = pair
        evidence["mechanical_summary"] = {
            "benign_successes": {
                version: sum(record["status"] == "success" for record in records)
                for version, records in benign.items()
            },
            "affected_alias_observations": sum(
                record["alias_matches_sentinel"] for record in pair["7.5.2"]
            ),
            "fixed_alias_observations": sum(
                record["alias_matches_sentinel"] for record in pair["7.5.3"]
            ),
            "affected_statuses": [record["status"] for record in pair["7.5.2"]],
            "fixed_statuses": [record["status"] for record in pair["7.5.3"]],
            "qualification": "AUTOMATED_REPRODUCTION_COMPLETE",
            "root_cause": "HUMAN_CONFIRMATION_PENDING",
            "formal_evaluation": "NOT_RUN",
        }
        evidence["completed_at_utc"] = datetime.now(UTC).isoformat()
        evidence["infrastructure_failure"] = None
    except Exception as error:
        evidence["completed_at_utc"] = datetime.now(UTC).isoformat()
        evidence["infrastructure_failure"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        _write_evidence(campaign_evidence, evidence)
        raise
    _write_evidence(campaign_evidence, evidence)
