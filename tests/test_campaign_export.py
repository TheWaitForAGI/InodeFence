"""Deterministic writer contracts; no campaign reader or deserializer API."""

import base64
import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.campaign import CampaignConfig, CampaignOrigin, CampaignResult, CampaignStep
from inodefence.campaign_export import export_campaign
from inodefence.feedback import Corpus, state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    ObjectSnapshot,
    ObjectType,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
    canonical_json,
)
from inodefence.model.provenance import SourceProvenance, TargetProvenance
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.provenance import freeze_provenance
from inodefence.runtime import SentinelSpec


def _campaign() -> CampaignResult:
    case = ArchiveCase((ArchiveEntry("./한글//a", EntryType.REGULAR, content=b"\0\xff"),))
    sentinel = ObjectSnapshot(
        "outside/sentinel",
        ObjectType.REGULAR,
        41,
        1234,
        1,
        0o600,
        2,
        1000,
        1000,
        123456,
        654321,
        content_digest=sha256(b"ok").hexdigest(),
    )
    before = StateSnapshot(
        "/var/lib/inodefence/synthetic", SnapshotPhase.BEFORE, (sentinel,), (sentinel.path,)
    )
    after = replace(before, phase=SnapshotPhase.AFTER)
    corpus = Corpus()
    steps = []
    for index, status in enumerate(ExecutionStatus):
        execution = ExecutionResult(
            "controlled",
            "test",
            ("worker", "fixed"),
            status,
            None
            if status == ExecutionStatus.TIMED_OUT
            else 0
            if status == ExecutionStatus.SUCCESS
            else 1,
            "line\n\udcff",
            "stderr\n",
            0.25,
            5.0,
        )
        result = RunResult(
            case,
            case.case_id,
            "synthetic-test",
            execution,
            before,
            after,
            (),
            state_signature(before, after),
            (),
        )
        steps.append(
            CampaignStep(
                index,
                CampaignOrigin.SEED if index == 0 else CampaignOrigin.MUTATION,
                None if index == 0 else case.case_id,
                result,
                corpus.consider(result),
            )
        )
    return CampaignResult(
        CampaignConfig(17, 4),
        (case.case_id,),
        tuple(steps),
        corpus.stats,
        (case.case_id,),
        freeze_provenance(
            TargetProvenance("controlled", "test", 5.0),
            (SentinelSpec(),),
            source=SourceProvenance("a" * 40, False),
        ),
    )


def test_same_completed_result_exports_identical_bytes_to_different_paths(tmp_path: Path) -> None:
    result = _campaign()
    first = export_campaign(result, tmp_path / "first")
    second = export_campaign(result, tmp_path / "second")
    assert tuple(path.name for path in first) == ("manifest.json", "steps.jsonl")
    assert tuple(path.read_bytes() for path in first) == tuple(path.read_bytes() for path in second)
    for path in first:
        assert path.read_bytes().endswith(b"\n")
        assert b"\r" not in path.read_bytes()


def test_manifest_records_campaign_stored_provenance_and_observed_contexts(tmp_path: Path) -> None:
    result = _campaign()
    manifest_path, steps_path = export_campaign(result, tmp_path / "output")
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["format"] == "inodefence-bounded-campaign"
    assert manifest["schema_version"] == 3
    assert manifest["evidence_classification"] == "raw-campaign"
    assert manifest["config"] == {"random_seed": 17, "execution_budget": 4}
    assert manifest["initial_case_ids"] == list(result.initial_case_ids)
    assert manifest["retained_case_ids"] == list(result.retained_case_ids)
    assert manifest["number_of_steps"] == 4
    assert manifest["final_corpus_stats"] == {
        "observations": 4,
        "interesting_observations": 1,
        "retained_cases": 1,
        "unique_states": 1,
        "unique_violation_fingerprints": 0,
    }
    assert manifest["execution_contexts"] == [
        {
            "target_id": "controlled",
            "target_version": "test",
            "builder_format": "synthetic-test",
            "timeout_seconds": 5.0,
        }
    ]
    assert manifest["steps_sha256"] == sha256(steps_path.read_bytes()).hexdigest()
    assert manifest["steps_file"] == steps_path.name
    assert "analysis" not in manifest and "source_revision" not in manifest
    assert "execution_environment" not in manifest
    assert manifest["export_environment"]["python_version"]
    assert manifest["execution_provenance"]["source"] == {"revision": "a" * 40, "dirty": False}


def test_every_step_and_raw_evidence_uses_existing_canonical_encoding(tmp_path: Path) -> None:
    result = _campaign()
    _, steps_path = export_campaign(result, tmp_path / "output")
    lines = steps_path.read_text().splitlines()
    assert lines == [canonical_json(step) for step in result.steps]
    for index, line in enumerate(lines):
        encoded = json.loads(line)
        assert encoded["schema_version"] == 1 and encoded["model"] == "CampaignStep"
        step = encoded["value"]
        assert step["index"] == index
        assert step["origin"] == ("seed" if index == 0 else "mutation")
        assert step["parent_case_id"] == (None if index == 0 else result.initial_case_ids[0])
        assert step["feedback"]["case_id"] == result.initial_case_ids[0]
        raw = step["result"]
        assert raw["execution"]["status"] == tuple(ExecutionStatus)[index].value
        assert raw["execution"]["stdout"] == "line\n\udcff"
        assert raw["before"]["objects"][0]["st_ino"] == 1234
        assert raw["before"]["objects"][0]["mtime_ns"] == 123456
        assert raw["case"]["entries"][0]["path"] == "./한글//a"
        assert base64.b64decode(raw["case"]["entries"][0]["content"]["data"]) == b"\0\xff"


def test_manifest_preserves_context_variation_in_first_occurrence_order(tmp_path: Path) -> None:
    result = _campaign()
    changed = replace(
        result.steps[1].result,
        archive_format="other-builder",
        execution=replace(
            result.steps[1].result.execution, target_version="other-version", timeout_seconds=None
        ),
    )
    step = replace(result.steps[1], result=changed)
    result = replace(result, steps=(result.steps[0], step, *result.steps[2:]))
    manifest_path, _ = export_campaign(result, tmp_path / "output")
    contexts = json.loads(manifest_path.read_bytes())["execution_contexts"]
    assert len(contexts) == 2
    assert [context["target_version"] for context in contexts] == ["test", "other-version"]
    assert contexts[1]["builder_format"] == "other-builder"
    assert contexts[1]["timeout_seconds"] is None
    # Observed variation never reconstructs or overwrites frozen configuration.
    stored = json.loads(manifest_path.read_bytes())["execution_provenance"]["target"]
    assert stored == {
        "target_id": "controlled",
        "target_version": "test",
        "timeout_seconds": 5.0,
        "execution_safety": "isolation_required",
    }


def test_export_does_not_capture_execution_environment_again(tmp_path: Path, monkeypatch) -> None:
    result = _campaign()
    monkeypatch.setattr("platform.release", lambda: "different-export-kernel")
    manifest_path, _ = export_campaign(result, tmp_path / "output")
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["export_environment"]["release"] == "different-export-kernel"
    assert (
        manifest["execution_provenance"]["environment"]["release"]
        == result.provenance.environment.release
    )


def test_existing_output_is_not_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "output"
    export_campaign(_campaign(), output)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(FileExistsError):
        export_campaign(_campaign(), output)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before


def test_write_error_propagates_without_completed_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path.open
    error = OSError("controlled export write failure")

    def fail_steps(path: Path, mode: str = "r"):
        if path.name == "steps.jsonl":
            raise error
        return original(path, mode)

    monkeypatch.setattr(Path, "open", fail_steps)
    with pytest.raises(OSError) as caught:
        export_campaign(_campaign(), tmp_path / "output")
    assert caught.value is error
    assert not (tmp_path / "output" / "manifest.json").exists()


def test_contract_evidence_and_feedback_decision_are_preserved(tmp_path: Path) -> None:
    original = _campaign()
    raw = original.steps[1].result
    changed_sentinel = replace(raw.before.objects[0], mode=0o640)
    after = replace(raw.after, objects=(changed_sentinel,))
    raw = replace(
        raw,
        after=after,
        changes=compare_states(raw.before, after),
        signature=state_signature(raw.before, after),
        violations=evaluate_contracts(raw.before, after),
    )
    corpus = Corpus()
    steps = []
    for index, old in enumerate(original.steps):
        evidence = raw if index == 1 else old.result
        steps.append(replace(old, result=evidence, feedback=corpus.consider(evidence)))
    result = replace(
        original,
        steps=tuple(steps),
        final_corpus_stats=corpus.stats,
        retained_case_ids=tuple(entry.case.case_id for entry in corpus.entries),
    )
    _, path = export_campaign(result, tmp_path / "output")
    step = json.loads(path.read_text().splitlines()[1])["value"]
    assert step["result"]["violations"][2]["violated"]
    assert step["result"]["violations"][2]["evidence"][0]["fields"] == ["mode"]
    assert step["feedback"]["new_violation_fingerprints"][0]["contract_id"] == "C2"
    assert step["feedback"]["already_retained"]
