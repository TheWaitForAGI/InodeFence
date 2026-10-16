"""Candidate 3+3 replay keeps raw evidence separate from class judgment."""

import json
import shutil
import sys
from dataclasses import replace

import pytest

import inodefence.campaign as campaign_module
import inodefence.evaluation.candidate_replay as candidate_module
from inodefence.campaign import SearchCampaignConfig, run_search_campaign
from inodefence.evaluation.candidate_replay import (
    CandidateReplayRole,
    main,
    nominate_policy_candidate,
    read_candidate_replay,
    run_candidate_replays,
)
from inodefence.evaluation.failure import write_failure
from inodefence.evaluation.policy_binding import (
    PolicyEvaluationConfig,
    export_bound_policy_result,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import SearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.mutator import MutationPolicy
from inodefence.targets.python_tarfile import PythonTarfileTarget


def _source(tmp_path):
    cases = minimal_seed_corpus()
    target = PythonTarfileTarget()
    result = run_search_campaign(
        cases,
        target,
        SearchCampaignConfig(
            9001,
            len(cases),
            SearchPolicy.B3,
            MutationPolicy.M1_PROTECTED_COMPONENTS,
        ),
    )
    config = PolicyEvaluationConfig(
        result.config,
        result.initial_case_ids,
        result.provenance,
        "minimal-benign-v1",
        "candidate-replay-test-linux-v1",
        "default-sentinel-v1",
        "candidate-replay-source-v1",
    )
    directory = tmp_path / "source"
    digest = export_bound_policy_result(result, config, directory)
    return cases, directory, digest


def test_nomination_and_exact_three_plus_three_replay(tmp_path, capsys, monkeypatch):
    cases, source, binding = _source(tmp_path)
    nomination = nominate_policy_candidate(
        source, cases[2].case_id, expected_binding_sha256=binding
    )
    assert nomination.case == cases[2]
    assert [item.step_index for item in nomination.occurrences] == [2]

    evidence = tmp_path / "replay"
    snapshot = run_candidate_replays(
        source,
        cases[2].case_id,
        evidence,
        PythonTarfileTarget(),
        PythonTarfileTarget(),
        attempt_id="candidate-test-complete",
        expected_source_binding_sha256=binding,
    )
    assert snapshot.complete
    assert not snapshot.infrastructure_invalid
    assert len(snapshot.runs) == 6
    assert len(snapshot.pairs) == 3
    assert [item.role for item in snapshot.runs] == [
        CandidateReplayRole.AFFECTED,
        CandidateReplayRole.FIXED,
        CandidateReplayRole.FIXED,
        CandidateReplayRole.AFFECTED,
        CandidateReplayRole.AFFECTED,
        CandidateReplayRole.FIXED,
    ]
    assert all(item.result.case == cases[2] for item in snapshot.runs)
    assert all(item.runtime_root_absent_after_return for item in snapshot.runs)
    assert all(pair.case_id == cases[2].case_id for pair in snapshot.pairs)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "candidate-replay",
            str(evidence),
            str(source),
            "--completion-sha256",
            snapshot.completion_sha256,
        ],
    )
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "complete"
    assert output["runs"] == 6
    assert output["pairs"] == 3
    with pytest.raises(ValueError, match="new path"):
        run_candidate_replays(
            source,
            cases[2].case_id,
            evidence,
            PythonTarfileTarget(),
            PythonTarfileTarget(),
            attempt_id="candidate-test-forbidden-retry",
        )
    with pytest.raises(ValueError, match="equal adapter, timeout and safety"):
        run_candidate_replays(
            source,
            cases[2].case_id,
            tmp_path / "mismatched-targets",
            PythonTarfileTarget(10),
            PythonTarfileTarget(11),
            attempt_id="candidate-test-mismatched-targets",
        )


def test_ordinary_exception_retains_invalid_prefix(tmp_path, monkeypatch):
    cases, source, binding = _source(tmp_path)
    original = campaign_module.run_case
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("controlled replay infrastructure failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(campaign_module, "run_case", fail_second)
    evidence = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="controlled replay infrastructure failure"):
        run_candidate_replays(
            source,
            cases[0].case_id,
            evidence,
            PythonTarfileTarget(),
            PythonTarfileTarget(),
            attempt_id="candidate-test-failed",
            expected_source_binding_sha256=binding,
        )
    snapshot = read_candidate_replay(evidence, source)
    assert not snapshot.complete
    assert snapshot.infrastructure_invalid
    assert len(snapshot.runs) == 1
    assert not snapshot.pairs
    assert snapshot.failure is not None
    assert snapshot.failure.context.last_fully_completed_step == 0

    tampered = tmp_path / "failed-tampered"
    shutil.copytree(evidence, tampered)
    (tampered / "failure.json").unlink()
    write_failure(
        tampered / "failure.json",
        replace(
            snapshot.failure,
            context=replace(snapshot.failure.context, config_id="0" * 64),
        ),
    )
    with pytest.raises(VerificationError, match="failure record differs"):
        read_candidate_replay(tampered, source)


def test_publication_error_after_link_retains_readable_run_prefix(tmp_path, monkeypatch):
    cases, source, binding = _source(tmp_path)
    original = candidate_module.write_record
    failed = False

    def fail_after_first_run_link(path, value):
        nonlocal failed
        digest = original(path, value)
        if not failed and path.parent.name == "runs":
            failed = True
            raise OSError("controlled directory fsync failure after run link")
        return digest

    monkeypatch.setattr(candidate_module, "write_record", fail_after_first_run_link)
    evidence = tmp_path / "publication-failed"
    with pytest.raises(OSError, match="after run link"):
        run_candidate_replays(
            source,
            cases[0].case_id,
            evidence,
            PythonTarfileTarget(),
            PythonTarfileTarget(),
            attempt_id="candidate-test-publication-failed",
            expected_source_binding_sha256=binding,
        )
    snapshot = read_candidate_replay(evidence, source)
    assert snapshot.infrastructure_invalid
    assert len(snapshot.runs) == 1
    assert snapshot.failure is not None
    assert snapshot.failure.context.phase.value == "publication"
    assert snapshot.failure.context.step_index == 0
    assert snapshot.failure.context.last_fully_completed_step == 0


def test_hard_interruption_preserves_readable_unclassified_prefix(tmp_path, monkeypatch):
    cases, source, binding = _source(tmp_path)
    original = campaign_module.run_case
    calls = 0

    def stop_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return original(*args, **kwargs)

    monkeypatch.setattr(campaign_module, "run_case", stop_second)
    evidence = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt):
        run_candidate_replays(
            source,
            cases[0].case_id,
            evidence,
            PythonTarfileTarget(),
            PythonTarfileTarget(),
            attempt_id="candidate-test-interrupted",
            expected_source_binding_sha256=binding,
        )
    snapshot = read_candidate_replay(evidence, source)
    assert not snapshot.complete
    assert not snapshot.infrastructure_invalid
    assert len(snapshot.runs) == 1
    assert snapshot.failure is None


def test_candidate_must_exist_in_exact_verified_source(tmp_path):
    cases, source, binding = _source(tmp_path)
    with pytest.raises(VerificationError, match="absent"):
        nominate_policy_candidate(source, "0" * 64, expected_binding_sha256=binding)

    evidence = tmp_path / "complete"
    snapshot = run_candidate_replays(
        source,
        cases[1].case_id,
        evidence,
        PythonTarfileTarget(),
        PythonTarfileTarget(),
        attempt_id="candidate-test-source-binding",
        expected_source_binding_sha256=binding,
    )
    assert snapshot.complete
    other_root = tmp_path / "other"
    other_root.mkdir()
    with pytest.raises(VerificationError):
        read_candidate_replay(evidence, other_root)

    missing_marker = tmp_path / "missing-marker"
    shutil.copytree(evidence, missing_marker)
    (missing_marker / "completion.json").unlink()
    incomplete = read_candidate_replay(missing_marker, source)
    assert not incomplete.complete
    assert len(incomplete.runs) == 6
    assert len(incomplete.pairs) == 3

    missing_run = tmp_path / "missing-run"
    shutil.copytree(evidence, missing_run)
    (missing_run / "runs" / "run-00000003.json").unlink()
    with pytest.raises(VerificationError, match="contiguous prefix"):
        read_candidate_replay(missing_run, source)
