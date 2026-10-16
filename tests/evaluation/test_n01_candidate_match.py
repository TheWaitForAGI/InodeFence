"""Controlled reader tests; no historical package is executed here."""

import json
import os
import shutil
import sys
import tarfile
from contextlib import contextmanager
from pathlib import Path

import inodefence.campaign as campaign_module
from inodefence.campaign import SearchCampaignConfig, run_search_campaign
from inodefence.evaluation.candidate_replay import run_candidate_replays
from inodefence.evaluation.n01 import (
    NODE_VERSION,
    WORKER_SHA256,
    N01Role,
    frozen_target,
    reconstruct_n01_case,
)
from inodefence.evaluation.n01_candidate_match import (
    N01CandidateMachineStatus,
    N01Relation,
    assess_n01_candidate_replay,
    main,
)
from inodefence.evaluation.policy_binding import (
    PolicyEvaluationConfig,
    export_bound_policy_result,
)
from inodefence.execution.base import ContainerOutcome, ContainerRequest, ExecutionBackend
from inodefence.feedback import FeedbackProjection, SearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, ExecutionStatus
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance
from inodefence.model.provenance import SourceProvenance
from inodefence.mutator import MutationAttempt, MutationOperatorId, MutationPolicy
from inodefence.targets.isolated import IsolatedTarget
from inodefence.targets.node_tar import NodeTarTarget


class ControlledN01Backend(ExecutionBackend):
    """Test double for matcher mechanics, never real containment evidence."""

    def __init__(self, role: N01Role, image_id: str, *, allow_relation: bool) -> None:
        self.role = role
        self.image_id = image_id
        self.allow_relation = allow_relation
        expected = frozen_target(role)
        self.metadata = {
            "node_version": NODE_VERSION,
            "tar_version": expected.tar_version,
            "worker_sha256": WORKER_SHA256,
            "package_lock_sha256": expected.lock_sha256,
        }

    def validate_image(self, image_id: str) -> None:
        assert image_id == self.image_id

    def policy(self, image_id: str) -> IsolationPolicy:
        self.validate_image(image_id)
        return IsolationPolicy(image_id, 1000, 1000)

    def capture_isolation(self, image_id: str) -> IsolationProvenance:
        return IsolationProvenance(
            self.policy(image_id),
            "controlled-test-double",
            "test",
            "test",
            "linux",
            "arm64",
            "arm64",
        )

    @contextmanager
    def prepare(self, request: ContainerRequest):
        backend = self

        class Prepared:
            def execute(self) -> ContainerOutcome:
                if "--identify" in request.command:
                    return ContainerOutcome(
                        0,
                        json.dumps(backend.metadata).encode("ascii"),
                        b"",
                        0.001,
                        False,
                    )
                archive = Path(request.command[3])
                extraction = Path(request.command[4])
                return backend._extract(archive, extraction)

        yield Prepared()

    def _extract(self, archive_path: Path, extraction_root: Path) -> ContainerOutcome:
        with tarfile.open(archive_path, mode="r:") as archive:
            for member in archive.getmembers():
                destination = extraction_root / member.name.rstrip("/")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if member.isdir():
                    destination.mkdir(exist_ok=True)
                elif member.isfile():
                    stream = archive.extractfile(member)
                    assert stream is not None
                    destination.write_bytes(stream.read())
                elif member.issym():
                    os.symlink(member.linkname, destination)
                elif member.islnk():
                    if member.linkname == "../outside/sentinel.txt" and not self.allow_relation:
                        return ContainerOutcome(2, b"", b"controlled rejection", 0.001, False)
                    os.link(extraction_root / member.linkname, destination)
                else:  # pragma: no cover - controlled corpus contains no other member
                    raise AssertionError("unexpected controlled member")
        return ContainerOutcome(0, b"", b"", 0.001, False)


def _target(role: N01Role, image_digit: str, *, allow_relation: bool) -> IsolatedTarget:
    image_id = "sha256:" + image_digit * 64
    expected = frozen_target(role)
    invocation = NodeTarTarget(
        image_id,
        NODE_VERSION,
        expected.tar_version,
        WORKER_SHA256,
        expected.lock_sha256,
        10,
    )
    return IsolatedTarget(
        invocation,
        ControlledN01Backend(role, image_id, allow_relation=allow_relation),
    )


def _evidence(
    tmp_path: Path,
    monkeypatch,
    *,
    fixed_allows_relation: bool = False,
    candidate: ArchiveCase | None = None,
):
    candidate = reconstruct_n01_case() if candidate is None else candidate
    original_freeze = campaign_module.freeze_provenance

    def clean_freeze(target, sentinels, *, source=None, isolation=None):
        del source
        return original_freeze(
            target,
            sentinels,
            source=SourceProvenance("a" * 40, False),
            isolation=isolation,
        )

    def forced_mutation(parent, rng, policy):
        del rng
        return MutationAttempt(
            MutationOperatorId.MUTATE_LINK_TARGET,
            policy,
            parent.case_id,
            candidate,
            True,
        )

    monkeypatch.setattr(campaign_module, "mutate_attempt_with_policy", forced_mutation)
    monkeypatch.setattr(campaign_module, "freeze_provenance", clean_freeze)
    affected = _target(N01Role.AFFECTED, "1", allow_relation=True)
    fixed = _target(N01Role.FIXED, "2", allow_relation=fixed_allows_relation)
    seeds = minimal_seed_corpus()
    campaign = run_search_campaign(
        seeds,
        affected,
        SearchCampaignConfig(
            9001,
            5,
            SearchPolicy.B0,
            MutationPolicy.M1_PROTECTED_COMPONENTS,
            FeedbackProjection.FULL,
        ),
    )
    config = PolicyEvaluationConfig(
        campaign.config,
        campaign.initial_case_ids,
        campaign.provenance,
        "minimal-benign-v1",
        "controlled-n01-reader-linux-v1",
        "default-sentinel-v1",
        "controlled-n01-candidate-source-v1",
    )
    source = tmp_path / "source"
    binding = export_bound_policy_result(campaign, config, source)
    replay = tmp_path / "replay"
    snapshot = run_candidate_replays(
        source,
        candidate.case_id,
        replay,
        affected,
        fixed,
        attempt_id="controlled-n01-candidate-replay",
        expected_source_binding_sha256=binding,
    )
    return source, replay, snapshot


def test_n01_machine_contrast_is_separate_from_human_disposition(tmp_path, monkeypatch, capsys):
    source, replay, snapshot = _evidence(tmp_path, monkeypatch)
    assessment = assess_n01_candidate_replay(
        replay,
        source,
        expected_completion_sha256=snapshot.completion_sha256,
    )
    assert assessment.status == N01CandidateMachineStatus.MACHINE_CONTRAST_PASS_PENDING_HUMAN
    assert assessment.selected_relation == N01Relation("extract/b.txt", "outside/sentinel.txt")
    assert assessment.source_matching_steps == (4,)
    assert assessment.affected_matching_runs == 3
    assert assessment.fixed_matching_runs == 0
    assert all(
        item.execution_status == ExecutionStatus.SUCCESS
        for item in assessment.observations
        if item.role.value == "affected"
    )
    assert all(
        item.execution_status == ExecutionStatus.REJECTED
        for item in assessment.observations
        if item.role.value == "fixed"
    )
    assert assessment.human_disposition == "pending_human_root_cause_review"
    assert not assessment.confirmed_rediscovery
    assert assessment.qualification_token is None

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "n01-candidate-match",
            str(replay),
            str(source),
            "--completion-sha256",
            snapshot.completion_sha256,
        ],
    )
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["value"]["status"] == "machine_contrast_pass_pending_human"
    assert output["value"]["qualification_token"] is None


def test_fixed_matching_relation_is_ambiguous_not_a_pass(tmp_path, monkeypatch):
    source, replay, snapshot = _evidence(tmp_path, monkeypatch, fixed_allows_relation=True)
    assessment = assess_n01_candidate_replay(
        replay,
        source,
        expected_completion_sha256=snapshot.completion_sha256,
    )
    assert assessment.status == N01CandidateMachineStatus.AMBIGUOUS
    assert assessment.affected_matching_runs == 3
    assert assessment.fixed_matching_runs == 3
    assert not assessment.confirmed_rediscovery


def test_missing_completion_is_not_evaluable_and_never_no_hit(tmp_path, monkeypatch):
    source, replay, _ = _evidence(tmp_path, monkeypatch)
    incomplete = tmp_path / "incomplete"
    shutil.copytree(replay, incomplete)
    (incomplete / "completion.json").unlink()

    assessment = assess_n01_candidate_replay(incomplete, source)
    assert assessment.status == N01CandidateMachineStatus.NOT_EVALUABLE
    assert assessment.replay_completion_sha256 is None
    assert not assessment.confirmed_rediscovery


def test_mutation_without_source_c1_relation_is_not_nominated(tmp_path, monkeypatch):
    unrelated = ArchiveCase((ArchiveEntry("new.txt", EntryType.REGULAR, content=b"benign"),))
    source, replay, snapshot = _evidence(
        tmp_path,
        monkeypatch,
        candidate=unrelated,
    )
    assessment = assess_n01_candidate_replay(
        replay,
        source,
        expected_completion_sha256=snapshot.completion_sha256,
    )
    assert assessment.status == N01CandidateMachineStatus.NOT_NOMINATED
    assert assessment.selected_relation is None
    assert assessment.source_matching_steps == ()
    assert assessment.affected_matching_runs == assessment.fixed_matching_runs == 0
