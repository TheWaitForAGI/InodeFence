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
    assert manifest["schema_version"] == 4
    assert manifest["experiment_config_file"] is None
    assert manifest["experiment_config_sha256"] is None
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


@pytest.mark.parametrize("failed_file", ("steps.jsonl", "manifest.json", "experiment.json"))
def test_write_error_leaves_final_absent_and_temporary_artifacts_cleaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_file: str
) -> None:
    original = Path.open
    error = OSError("controlled export write failure")

    def fail_steps(path: Path, mode: str = "r"):
        if path.name == failed_file:
            raise error
        return original(path, mode)

    monkeypatch.setattr(Path, "open", fail_steps)
    config = '{"controlled_config":true}'
    result = replace(_campaign(), experiment_config_id=sha256(config.encode("ascii")).hexdigest())
    with pytest.raises(OSError) as caught:
        export_campaign(result, tmp_path / "output", experiment_config_json=config)
    assert caught.value is error
    assert not (tmp_path / "output").exists()
    assert list(tmp_path.iterdir()) == []


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


@pytest.mark.parametrize("kind", ("empty-directory", "file", "dangling-symlink"))
def test_existing_destination_of_any_kind_is_preserved(tmp_path, kind):
    output = tmp_path / "output"
    if kind == "empty-directory":
        output.mkdir()
    elif kind == "file":
        output.write_bytes(b"existing evidence")
    else:
        output.symlink_to(tmp_path / "missing")
    identity = output.lstat().st_ino
    with pytest.raises(FileExistsError):
        export_campaign(_campaign(), output)
    assert output.lstat().st_ino == identity
    assert list(tmp_path.iterdir()) == [output]


def test_concurrent_empty_destination_is_never_replaced(tmp_path, monkeypatch):
    from inodefence import campaign_export

    original = campaign_export._publish_directory
    output = tmp_path / "output"
    existing = []

    def concurrent(staged, destination):
        destination.mkdir()
        existing.append(destination.stat().st_ino)
        original(staged, destination)

    monkeypatch.setattr(campaign_export, "_publish_directory", concurrent)
    with pytest.raises(FileExistsError):
        export_campaign(_campaign(), output)
    assert output.stat().st_ino == existing[0]
    assert list(output.iterdir()) == []
    assert list(tmp_path.iterdir()) == [output]


def test_unsupported_atomic_publication_fails_without_fallback(tmp_path, monkeypatch):
    import errno

    def unsupported(*args):
        raise OSError(errno.EOPNOTSUPP, "controlled filesystem does not support no-replace")

    monkeypatch.setattr("inodefence.campaign_export._publish_directory", unsupported)
    with pytest.raises(OSError) as caught:
        export_campaign(_campaign(), tmp_path / "output")
    assert caught.value.errno == errno.EOPNOTSUPP
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("unsupported", ("platform", "libc"))
def test_publication_requires_linux_and_libc_support(tmp_path, monkeypatch, unsupported):
    from types import SimpleNamespace

    result = _campaign()
    if unsupported == "platform":
        monkeypatch.setattr("inodefence.campaign_export.sys.platform", "unsupported")
    else:
        monkeypatch.setattr(
            "inodefence.campaign_export.ctypes.CDLL", lambda *a, **k: SimpleNamespace()
        )
    with pytest.raises(NotImplementedError):
        export_campaign(result, tmp_path / "output")
    assert list(tmp_path.iterdir()) == []


def test_encoding_failure_after_one_step_cleans_partial_staging(tmp_path, monkeypatch):
    result = _campaign()
    calls = []

    def encode(step):
        calls.append(step)
        if len(calls) == 2:
            raise ValueError("controlled second-step encoding failure")
        return canonical_json(step)

    monkeypatch.setattr("inodefence.campaign_export.canonical_json", encode)
    with pytest.raises(ValueError, match="second-step"):
        export_campaign(result, tmp_path / "output")
    assert len(calls) == 2
    assert list(tmp_path.iterdir()) == []


def test_corrupted_steps_are_rejected_before_publication(tmp_path, monkeypatch):
    from contextlib import contextmanager

    result = _campaign()
    original = Path.open

    @contextmanager
    def corrupt(path, mode="r", *args, **kwargs):
        with original(path, mode, *args, **kwargs) as stream:
            yield stream
        if path.name == "steps.jsonl" and mode == "xb":
            with original(path, "ab") as stream:
                stream.write(b"controlled corruption")

    monkeypatch.setattr(Path, "open", corrupt)
    with pytest.raises(OSError, match="checksum"):
        export_campaign(result, tmp_path / "output")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("after_publication", (False, True))
def test_directory_sync_failure_is_visible_with_documented_final_state(
    tmp_path, monkeypatch, after_publication
):
    from inodefence import campaign_export

    original = campaign_export._sync_directory
    result = _campaign()
    output = tmp_path / "output"

    def fail_sync(path):
        if (path == tmp_path) == after_publication:
            raise OSError("controlled directory sync failure")
        original(path)

    monkeypatch.setattr(campaign_export, "_sync_directory", fail_sync)
    with pytest.raises(OSError, match="directory sync"):
        export_campaign(result, output)
    if after_publication:
        manifest = json.loads((output / "manifest.json").read_bytes())
        assert manifest["steps_sha256"] == sha256((output / "steps.jsonl").read_bytes()).hexdigest()
        assert list(tmp_path.iterdir()) == [output]
    else:
        assert list(tmp_path.iterdir()) == []


def test_config_is_bound_checksummed_and_published_with_the_same_bundle(tmp_path):
    config = '{"controlled_config":true}'
    result = replace(_campaign(), experiment_config_id=sha256(config.encode("ascii")).hexdigest())
    first, _ = export_campaign(result, tmp_path / "first", experiment_config_json=config)
    second, _ = export_campaign(result, tmp_path / "second", experiment_config_json=config)
    value = json.loads(first.read_bytes())
    assert value["experiment_config_id"] == result.experiment_config_id
    assert value["experiment_config_file"] == "experiment.json"
    assert (first.parent / "experiment.json").read_bytes() == config.encode("ascii") + b"\n"
    assert (
        value["experiment_config_sha256"]
        == sha256((first.parent / "experiment.json").read_bytes()).hexdigest()
    )
    assert {p.name: p.read_bytes() for p in first.parent.iterdir()} == {
        p.name: p.read_bytes() for p in second.parent.iterdir()
    }


@pytest.mark.parametrize("stored_id", (None, "a" * 64))
def test_config_mismatch_is_rejected_before_staging(tmp_path, stored_id):
    result = replace(_campaign(), experiment_config_id=stored_id)
    with pytest.raises(ValueError, match="stored experiment_config_id"):
        export_campaign(result, tmp_path / "output", experiment_config_json='{"different":true}')
    assert list(tmp_path.iterdir()) == []
