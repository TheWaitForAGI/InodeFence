"""Phase-4A safe controller fixtures; no exploit archive or benchmark target."""

import json
import os
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256

import pytest

from inodefence import campaign, pipeline
from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.feedback import Corpus, violation_fingerprints
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    SnapshotPhase,
)
from inodefence.model.isolation import ArtifactDigest, IsolationPolicy, IsolationProvenance
from inodefence.model.provenance import ExecutionSafety, TargetProvenance
from inodefence.observer import ObservationError, capture_state
from inodefence.targets import PythonTarfileTarget


@pytest.mark.parametrize(
    "status,exit_code",
    (
        (ExecutionStatus.SUCCESS, 0),
        (ExecutionStatus.REJECTED, 2),
        (ExecutionStatus.FAILED, 1),
        (ExecutionStatus.TIMED_OUT, None),
    ),
)
@pytest.mark.parametrize(
    "effect,expected",
    (
        ("benign", (False, False, False)),
        ("harness-create", (True, False, False)),
        ("harness-delete", (True, False, False)),
        ("harness-identity", (True, False, False)),
        ("harness-type", (True, False, False)),
        ("sentinel-content", (False, False, True)),
        ("sentinel-delete", (True, False, True)),
        ("sentinel-identity", (True, False, True)),
        ("sentinel-mode", (False, False, True)),
        ("sentinel-alias", (False, True, True)),
    ),
)
def test_status_independent_contracts_lifecycle_corpus_and_export(
    status, exit_code, effect, expected, tmp_path, monkeypatch
):
    """Trusted code makes controlled effects directly, with inert empty TAR input.

    Statuses here are synthetic classification evidence, not subprocess outcomes.
    The real container suite separately verifies target stop and classification.
    """
    events = []
    roots = []

    class ControlledTarget:
        provenance = TargetProvenance(
            "audit-controlled", "1", 1.0, ExecutionSafety.TRUSTED_REFERENCE
        )

        @contextmanager
        def prepare(self, archive_path, extraction_root):
            root = extraction_root.parent
            roots.append(root)
            assert sha256(archive_path.read_bytes()).hexdigest()
            (root / "archive/setup-canary").write_bytes(b"before baseline")
            events.append("setup-and-input")

            def execute():
                events.append("execute")
                sentinel = root / "outside/sentinel.txt"
                if effect == "harness-create":
                    (root / "archive/target-canary").write_bytes(b"controlled")
                elif effect == "harness-delete":
                    archive_path.unlink()
                elif effect == "harness-identity":
                    replacement = extraction_root / "replacement"
                    replacement.write_bytes(archive_path.read_bytes())
                    replacement.replace(archive_path)
                elif effect == "harness-type":
                    archive_path.unlink()
                    archive_path.mkdir()
                elif effect == "sentinel-content":
                    sentinel.write_bytes(b"controlled sentinel content")
                elif effect == "sentinel-delete":
                    sentinel.unlink()
                elif effect == "sentinel-identity":
                    replacement = extraction_root / "replacement"
                    replacement.write_bytes(sentinel.read_bytes())
                    replacement.replace(sentinel)
                elif effect == "sentinel-mode":
                    sentinel.chmod(0o600)
                elif effect == "sentinel-alias":
                    os.link(sentinel, extraction_root / "alias")
                events.append("stopped")
                return ExecutionResult(
                    "audit-controlled", "1", (), status, exit_code, "", "", 0.0, 1.0
                )

            try:
                yield execute
            finally:
                assert root.exists()
                events.append("bookkeeping-and-cleanup")
                (root / "archive/post-canary").write_bytes(b"after observation")

        def run(self, archive_path, extraction_root):
            raise AssertionError("prepared execution is required")

    def capture(root, phase, protected):
        if phase == SnapshotPhase.AFTER:
            assert events[-1] == "stopped"
        events.append(phase.value)
        return capture_state(root, phase, protected)

    monkeypatch.setattr(pipeline, "capture_state", capture)
    result = run_campaign((ArchiveCase(()),), ControlledTarget(), CampaignConfig(11, 1))
    assert events == [
        "setup-and-input",
        "before",
        "execute",
        "stopped",
        "after",
        "bookkeeping-and-cleanup",
    ]
    run = result.steps[0].result
    assert run.execution.status == status
    assert tuple(verdict.violated for verdict in run.violations) == expected
    assert run.signature.schema_version == 3
    input_before = run.before.get("archive/input.tar")
    assert input_before is not None and input_before.content_digest == run.archive_sha256
    assert run.before.get("archive/setup-canary") == run.after.get("archive/setup-canary")
    assert run.after.get("archive/post-canary") is None
    assert all(not root.exists() for root in roots)
    assert not any(obj.path.startswith("archive") for obj in run.signature.objects)
    if effect == "sentinel-alias":
        alias = run.after.get("extract/alias")
        sentinel = run.after.get("outside/sentinel.txt")
        assert alias is not None and sentinel is not None
        assert alias.identity == sentinel.identity
        assert ("extract/alias", "outside/sentinel.txt") in run.signature.identity_groups

    # Exercise strengthened public key/entry validators using runtime-produced evidence.
    corpus = Corpus()
    assert corpus.consider(run) == result.steps[0].feedback
    entry = corpus.entries[0]
    assert entry.admission_signature == run.signature
    assert entry.admission_violation_fingerprints == violation_fingerprints(run.violations)
    assert hash(entry.admission_signature) == hash(run.signature)
    assert corpus.stats == result.final_corpus_stats
    manifest, steps = export_campaign(result, tmp_path / "evidence")
    stored = json.loads(steps.read_text())["value"]["result"]
    assert stored["signature"] == json.loads(json.dumps(asdict(run.signature)))
    assert stored["before"] == json.loads(json.dumps(asdict(run.before)))
    assert stored["after"] == json.loads(json.dumps(asdict(run.after)))
    assert stored["execution"]["status"] == status.value
    assert (
        json.loads(manifest.read_text())["steps_sha256"] == sha256(steps.read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("kind", tuple(EntryType))
def test_en001_rejection_never_reaches_runtime_target_after_or_corpus(kind, monkeypatch):
    entry = ArchiveEntry(
        "/" + "a" * 100,
        kind,
        content=b"inert" if kind == EntryType.REGULAR else None,
        link_target="inert" if kind in (EntryType.HARDLINK, EntryType.SYMLINK) else None,
    )
    corpus = Corpus()
    monkeypatch.setattr(campaign, "Corpus", lambda: corpus)

    def forbidden(*args, **kwargs):
        raise AssertionError("builder rejection must precede runtime/target/observation")

    monkeypatch.setattr(pipeline, "disposable_sandbox", forbidden)
    monkeypatch.setattr(pipeline, "capture_state", forbidden)
    monkeypatch.setattr(PythonTarfileTarget, "run", forbidden)
    with pytest.raises(ValueError, match="entry 0 cannot be represented in USTAR"):
        run_campaign((ArchiveCase((entry,)),), PythonTarfileTarget(), CampaignConfig(11, 1))
    assert corpus.stats.observations == 0
    assert corpus.entries == ()


@pytest.mark.parametrize("failure", ("before", "after", "signature"))
def test_infrastructure_failure_cannot_complete_campaign_or_admit_evidence(failure, monkeypatch):
    corpus = Corpus()
    monkeypatch.setattr(campaign, "Corpus", lambda: corpus)
    roots = []
    executions = []
    target = PythonTarfileTarget()
    original_run = PythonTarfileTarget.run

    def execute(self, archive_path, extraction_root):
        executions.append(archive_path)
        return original_run(self, archive_path, extraction_root)

    def capture(root, phase, protected):
        roots.append(root)
        if phase.value == failure:
            raise ObservationError("controlled incomplete capture")
        return capture_state(root, phase, protected)

    def invalid_signature(*args):
        raise ValueError("controlled signature validation failure")

    monkeypatch.setattr(PythonTarfileTarget, "run", execute)
    monkeypatch.setattr(pipeline, "capture_state", capture)
    if failure == "signature":
        monkeypatch.setattr(pipeline, "state_signature", invalid_signature)
    with pytest.raises((ObservationError, ValueError), match="controlled"):
        run_campaign((ArchiveCase(()),), target, CampaignConfig(11, 1))
    assert len(executions) == (0 if failure == "before" else 1)
    assert roots and all(not root.exists() for root in roots)
    assert corpus.stats.observations == 0
    assert corpus.entries == ()


def test_historical_isolation_v1_does_not_gain_verified_v2_origin():
    facts = IsolationProvenance(
        IsolationPolicy("sha256:" + "a" * 64, 1000, 1000),
        "docker-compatible",
        "29.4.0",
        "1.54",
        "linux",
        "arm64",
        "arm64",
    )
    legacy = {
        **{name: getattr(facts, name) for name in facts.__dataclass_fields__},
        "schema_version": 1,
        "artifacts": (ArtifactDigest("node-tar-worker", "b" * 64),),
    }
    legacy.pop("artifact_origin")
    with pytest.raises(ValueError, match="schema v2"):
        IsolationProvenance(**legacy)
    assert legacy["schema_version"] == 1 and "artifact_origin" not in legacy
