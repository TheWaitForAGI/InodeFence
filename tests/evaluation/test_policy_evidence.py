"""Policy evidence ingest on four benign fixtures; never execute mutations."""

from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.campaign import (
    CampaignOrigin,
    SearchCampaignConfig,
    SearchCampaignResult,
    SearchCampaignStep,
    run_search_campaign,
)
from inodefence.evaluation.encoding import json_bytes, read_json
from inodefence.evaluation.policy_evidence import (
    export_policy_result,
    validate_policy_result,
    verify_policy_evidence,
)
from inodefence.evaluation.verify import VerificationError, verify_campaign
from inodefence.feedback import FeedbackProjection, SearchPolicy, SearchState
from inodefence.mutator import MutationPolicy
from inodefence.replay.benign import benign_replay_cases
from inodefence.targets.python_tarfile import PythonTarfileTarget


@pytest.fixture(scope="module", params=list(SearchPolicy))
def policy_result(request):
    """Actual reference executions, budget exactly the seed count: zero mutations."""
    cases = benign_replay_cases()
    projection, mutation = {
        SearchPolicy.B0: (FeedbackProjection.FULL, MutationPolicy.LEGACY),
        SearchPolicy.B1: (FeedbackProjection.A1, MutationPolicy.M1),
        SearchPolicy.B3: (FeedbackProjection.A2, MutationPolicy.M1_NO_REORDER),
        SearchPolicy.D: (FeedbackProjection.FULL, MutationPolicy.M1),
    }[request.param]
    return run_search_campaign(
        cases,
        PythonTarfileTarget(),
        SearchCampaignConfig(-17, len(cases), request.param, mutation, projection),
    )


def write_modified_record(path, change):
    record = read_json(path.read_bytes())
    assert isinstance(record, dict)
    change(record["payload"]["value"])
    record["payload_sha256"] = sha256(json_bytes(record["payload"])).hexdigest()
    path.write_bytes(json_bytes(record) + b"\n")
    return sha256(path.read_bytes()).hexdigest()


def rebind_result(directory, digest):
    write_modified_record(
        directory / "manifest.json", lambda value: value["result"].update(sha256=digest)
    )


def test_whole_raw_result_and_explicit_policies_roundtrip(policy_result, tmp_path):
    directory = tmp_path / "export"
    digest = export_policy_result(policy_result, directory)
    verified = verify_policy_evidence(directory, expected_manifest_sha256=digest)
    assert verified.result == policy_result
    assert verified.manifest_sha256 == digest
    assert verified.manifest.number_of_steps == len(benign_replay_cases())
    assert verified.result.config.random_seed == -17
    # Legacy ingest must refuse this distinct schema, not silently apply B3.
    with pytest.raises(VerificationError):
        verify_campaign(directory)
    if policy_result.config.search_policy == SearchPolicy.B0:
        assert verified.result.retained_case_ids == ()
        assert verified.result.active_case_id is None


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["steps"][0]["result"].update(archive_sha256="0" * 64),
        lambda value: value["steps"][0]["result"]["case"]["entries"][0].update(path="other.txt"),
        lambda value: value["steps"][0]["feedback"].update(state_novel=False),
        lambda value: value["steps"][0].update(index=True),
        lambda value: value.update(unique_feedback_keys=999),
        lambda value: value.update(active_case_id="0" * 64),
        lambda value: value.update(initial_case_ids=[]),
        lambda value: value["config"].update(search_policy="unknown-policy"),
        lambda value: value["config"].update(execution_budget=999),
    ],
)
def test_semantic_corruption_rejected_even_with_all_checksums_recomputed(
    policy_result, tmp_path, change
):
    directory = tmp_path / "export"
    export_policy_result(policy_result, directory)
    digest = write_modified_record(directory / "result.json", change)
    rebind_result(directory, digest)
    with pytest.raises(VerificationError):
        verify_policy_evidence(directory)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(decision_schema=1),
        lambda value: value.update(signature_schema=2),
        lambda value: value.update(builder_format="floating"),
        lambda value: value.update(number_of_steps=99),
        lambda value: value.update(policy_config_sha256="0" * 64),
        lambda value: value["result"].update(name="../result.json"),
    ],
)
def test_invalid_manifest_binding_or_version_is_rejected(policy_result, tmp_path, change):
    directory = tmp_path / "export"
    export_policy_result(policy_result, directory)
    write_modified_record(directory / "manifest.json", change)
    with pytest.raises(VerificationError):
        verify_policy_evidence(directory)


def test_trusted_anchor_torn_payload_symlink_and_extra_file_fail_closed(policy_result, tmp_path):
    directory = tmp_path / "export"
    export_policy_result(policy_result, directory)
    with pytest.raises(VerificationError, match="checksum"):
        verify_policy_evidence(directory, expected_manifest_sha256="0" * 64)
    result = directory / "result.json"
    content = result.read_bytes()
    result.write_bytes(content[:-12])
    with pytest.raises(VerificationError):
        verify_policy_evidence(directory)
    result.unlink()
    target = tmp_path / "data.json"
    target.write_bytes(content)
    result.symlink_to(target)
    with pytest.raises(VerificationError):
        verify_policy_evidence(directory)
    result.unlink()
    result.write_bytes(content)
    (directory / "unrecognized.json").write_bytes(b"{}")
    with pytest.raises(VerificationError):
        verify_policy_evidence(directory)


def test_failed_marker_publication_preserves_unverified_prefix(
    policy_result, tmp_path, monkeypatch
):
    from inodefence.evaluation import policy_evidence

    original = policy_evidence.write_record

    def fail_marker(path, value):
        if path.name == "manifest.json":
            raise OSError("controlled marker publication failure")
        return original(path, value)

    monkeypatch.setattr(policy_evidence, "write_record", fail_marker)
    directory = tmp_path / "export"
    with pytest.raises(OSError, match="controlled marker"):
        export_policy_result(policy_result, directory)
    content = (directory / "result.json").read_bytes()
    with pytest.raises(VerificationError):
        verify_policy_evidence(directory)
    with pytest.raises(FileExistsError):
        export_policy_result(policy_result, directory)
    assert (directory / "result.json").read_bytes() == content


def synthetic_lineage(result):
    """Synthetic assembly reuses benign raw observations to test parent checking.

    This is not an executed campaign or research dataset. No mutation runs.
    """
    state = SearchState(
        benign_replay_cases(),
        result.config.search_policy,
        projection=result.config.feedback_projection,
    )
    steps = []
    for step in result.steps:
        steps.append(replace(step, feedback=state.consider(step.result)))
    parent = result.initial_case_ids[0]
    for raw in (result.steps[1].result, result.steps[2].result):
        steps.append(
            SearchCampaignStep(
                len(steps), CampaignOrigin.MUTATION, parent, raw, state.consider(raw)
            )
        )
        if state.policy == SearchPolicy.B0:
            parent = raw.case.case_id
    return SearchCampaignResult(
        replace(result.config, execution_budget=len(steps)),
        result.initial_case_ids,
        tuple(steps),
        state.stats,
        tuple(entry.case.case_id for entry in state.entries),
        state.unique_feedback_keys,
        None if state.active_case is None else state.active_case.case_id,
        result.provenance,
    )


def test_declared_policy_parent_and_final_accounting_validation(policy_result):
    assembled = synthetic_lineage(policy_result)
    validate_policy_result(assembled)
    invalid_parent = replace(assembled.steps[-1], parent_case_id="0" * 64)
    with pytest.raises(ValueError, match="mutation parent"):
        validate_policy_result(replace(assembled, steps=assembled.steps[:-1] + (invalid_parent,)))
    if policy_result.config.search_policy == SearchPolicy.B0:
        stale = replace(assembled.steps[-1], parent_case_id=assembled.initial_case_ids[0])
        with pytest.raises(ValueError, match="mutation parent"):
            validate_policy_result(replace(assembled, steps=assembled.steps[:-1] + (stale,)))
    with pytest.raises(ValueError, match="accounting"):
        validate_policy_result(replace(assembled, retained_case_ids=("0" * 64,)))


def test_invalid_result_never_creates_export_directory(policy_result, tmp_path):
    directory = tmp_path / "invalid"
    with pytest.raises(ValueError):
        export_policy_result(replace(policy_result, steps=()), directory)
    assert not directory.exists()


def test_reader_cli_success_and_fail_closed(policy_result, tmp_path, monkeypatch, capsys):
    from inodefence.evaluation.policy_evidence import main

    directory = tmp_path / "export"
    digest = export_policy_result(policy_result, directory)
    monkeypatch.setattr(
        "sys.argv", ["policy-evidence", str(directory), "--manifest-sha256", digest]
    )
    assert main() == 0
    output = read_json(capsys.readouterr().out.encode("ascii"))
    assert isinstance(output, dict)
    assert output["manifest_sha256"] == digest
    (directory / "manifest.json").unlink()
    assert main() == 1
    assert "invalid policy" in capsys.readouterr().err
