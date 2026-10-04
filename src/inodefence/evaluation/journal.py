"""Incremental evidence sink; completion is explicit, never inferred from files."""

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from inodefence.campaign import CampaignConfig, CampaignOrigin, CampaignResult, CampaignStep
from inodefence.campaign_export import export_campaign
from inodefence.feedback import Corpus
from inodefence.model.provenance import ExecutionProvenance

from .storage import read_record, sync_directory, write_record
from .verify import (
    VerificationError,
    VerifiedCampaign,
    _digest,
    _read_file,
    verify_binding,
    verify_campaign,
    verify_run,
)


@dataclass(frozen=True, slots=True)
class JournalHeader:
    config: CampaignConfig
    initial_case_ids: tuple[str, ...]
    provenance: ExecutionProvenance
    experiment_config_id: str | None = None
    experiment_config_json: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.config, CampaignConfig) or not isinstance(
            self.provenance, ExecutionProvenance
        ):
            raise ValueError("journal requires explicit configuration and provenance")
        if (
            not isinstance(self.initial_case_ids, tuple)
            or not self.initial_case_ids
            or len(self.initial_case_ids) > self.config.execution_budget
            or len(set(self.initial_case_ids)) != len(self.initial_case_ids)
        ):
            raise ValueError("journal requires unique initial cases within budget")
        for case_id in self.initial_case_ids:
            _digest(case_id)
        if self.experiment_config_id is not None:
            _digest(self.experiment_config_id)
        if (
            self.experiment_config_json is not None
            and sha256(self.experiment_config_json.encode("ascii")).hexdigest()
            != self.experiment_config_id
        ):
            raise ValueError("journal config JSON differs from config identifier")


@dataclass(frozen=True, slots=True)
class JournalCompletion:
    header_sha256: str
    record_sha256: tuple[str, ...]
    manifest_sha256: str
    steps_sha256: str

    def __post_init__(self) -> None:
        for value in (self.header_sha256, self.manifest_sha256, self.steps_sha256):
            _digest(value)
        if not isinstance(self.record_sha256, tuple) or not self.record_sha256:
            raise ValueError("completion requires record digests")
        for value in self.record_sha256:
            _digest(value)


@dataclass(frozen=True, slots=True)
class JournalSnapshot:
    header: JournalHeader
    steps: tuple[CampaignStep, ...]
    record_sha256: tuple[str, ...]
    header_sha256: str
    completed_campaign: VerifiedCampaign | None

    @property
    def complete(self) -> bool:
        return self.completed_campaign is not None


def _step_name(index: int) -> str:
    return f"step-{index:08d}.json"


def _consume(header: JournalHeader, steps: tuple[CampaignStep, ...]) -> Corpus:
    if len(steps) > header.config.execution_budget:
        raise ValueError("journal exceeds execution budget")
    corpus = Corpus()
    for index, step in enumerate(steps):
        if step.index != index:
            raise ValueError("journal step index gap/mismatch")
        if index < len(header.initial_case_ids):
            if (
                step.origin != CampaignOrigin.SEED
                or step.parent_case_id is not None
                or step.result.case.case_id != header.initial_case_ids[index]
            ):
                raise ValueError("journal seed lineage mismatch")
        elif step.origin != CampaignOrigin.MUTATION or step.parent_case_id not in {
            entry.case.case_id for entry in corpus.entries
        }:
            raise ValueError("journal mutation parent not previously retained")
        verify_run(step.result)
        verify_binding(step.result, header.provenance)
        if step.feedback != corpus.consider(step.result):
            raise ValueError("journal case/feedback mismatch")
    return corpus


def _result(header: JournalHeader, steps: tuple[CampaignStep, ...]) -> CampaignResult:
    if len(steps) != header.config.execution_budget:
        raise ValueError("incomplete journal cannot be finalized")
    corpus = _consume(header, steps)
    return CampaignResult(
        header.config,
        header.initial_case_ids,
        steps,
        corpus.stats,
        tuple(entry.case.case_id for entry in corpus.entries),
        header.provenance,
        header.experiment_config_id,
    )


def read_journal(directory: Path) -> JournalSnapshot:
    """Verify every published record; ignore temporary files, never ignore torn records."""
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("expected a journal directory")
        names = {path.name for path in directory.iterdir()}
        records = sorted(name for name in names if re.fullmatch(r"step-[0-9]{8}.json", name))
        allowed = {"header.json", "completion.json", "campaign", *records}
        if any(
            name not in allowed
            and not name.startswith(".record-")
            and not name.startswith(".inodefence-export-")
            for name in names
        ):
            raise ValueError("unexpected journal artifact")
        if records != [_step_name(index) for index in range(len(records))]:
            raise ValueError("journal record gap")
        header = read_record(directory / "header.json", JournalHeader)
        header_digest = sha256(_read_file(directory / "header.json")).hexdigest()
        digests = tuple(sha256(_read_file(directory / name)).hexdigest() for name in records)
        steps = tuple(read_record(directory / name, CampaignStep) for name in records)
        _consume(header, steps)
        campaign = None
        if "completion.json" in names:
            marker = read_record(directory / "completion.json", JournalCompletion)
            if marker.header_sha256 != header_digest or marker.record_sha256 != digests:
                raise ValueError("completion marker differs from journal records")
            campaign = verify_campaign(
                directory / "campaign", expected_manifest_sha256=marker.manifest_sha256
            )
            if marker.steps_sha256 != campaign.steps_sha256 or campaign.result != _result(
                header, steps
            ):
                raise ValueError("completed campaign differs from journal")
        return JournalSnapshot(header, steps, digests, header_digest, campaign)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid evidence journal: {error}") from error


class EvidenceJournal:
    """Single-writer append-only sink, reopened after interruption without reruns.

    Each append revalidates the published prefix. No search state, mutation,
    target execution, campaign checkpoint or resume is owned here.
    """

    def __init__(self, directory: Path):
        self.directory = directory

    @classmethod
    def create(cls, directory: Path, header: JournalHeader) -> "EvidenceJournal":
        if not isinstance(header, JournalHeader):
            raise ValueError("expected a JournalHeader")
        directory.mkdir(parents=True, exist_ok=False)
        write_record(directory / "header.json", header)
        sync_directory(directory.parent)
        return cls(directory)

    def append(self, step: CampaignStep) -> str:
        snapshot = read_journal(self.directory)
        if snapshot.complete or (self.directory / "campaign").exists():
            raise ValueError("journal publication already finalized/started")
        if (
            not isinstance(step, CampaignStep)
            or type(step.index) is not int
            or step.index != len(snapshot.steps)
        ):
            raise ValueError("append requires the next completed step")
        _consume(snapshot.header, (*snapshot.steps, step))
        return write_record(self.directory / _step_name(step.index), step)

    def finish(self) -> VerifiedCampaign:
        """Finalize only at the exact budget; interrupted publication can be retried.

        An existing campaign must equal the journal before a marker is written.
        Missing completion marker always means an incomplete journal, even when
        all records or a standalone completed export already exist.
        """
        snapshot = read_journal(self.directory)
        if snapshot.completed_campaign is not None:
            return snapshot.completed_campaign
        result = _result(snapshot.header, snapshot.steps)
        destination = self.directory / "campaign"
        if not destination.exists():
            export_campaign(
                result, destination, experiment_config_json=snapshot.header.experiment_config_json
            )
        verified = verify_campaign(destination)
        if verified.result != result:
            raise VerificationError("existing final export differs from journal")
        write_record(
            self.directory / "completion.json",
            JournalCompletion(
                snapshot.header_sha256,
                snapshot.record_sha256,
                verified.manifest_sha256,
                verified.steps_sha256,
            ),
        )
        return verified
