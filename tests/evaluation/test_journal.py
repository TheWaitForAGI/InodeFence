from dataclasses import replace

import pytest

from inodefence.campaign import CampaignConfig, CampaignOrigin, CampaignStep
from inodefence.evaluation import journal as journal_module
from inodefence.evaluation.journal import EvidenceJournal, JournalHeader, read_journal
from inodefence.evaluation.verify import VerificationError
from inodefence.feedback import Corpus
from inodefence.generator import minimal_seed_corpus
from inodefence.pipeline import run_case
from inodefence.provenance import freeze_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.python_tarfile import PythonTarfileTarget


def test_each_step_is_durable_before_the_next_execution(tmp_path):
    seeds = minimal_seed_corpus()
    target = PythonTarfileTarget()
    header = JournalHeader(
        CampaignConfig(17, len(seeds)),
        tuple(case.case_id for case in seeds),
        freeze_provenance(target.provenance, (SentinelSpec(),)),
    )
    path = tmp_path / "journal"
    writer = EvidenceJournal.create(path, header)
    corpus = Corpus()
    for index, case in enumerate(seeds):
        result = run_case(case, target)
        step = CampaignStep(index, CampaignOrigin.SEED, None, result, corpus.consider(result))
        writer.append(step)
        reopened = read_journal(path)
        assert not reopened.complete
        assert len(reopened.steps) == index + 1
        assert reopened.steps[-1] == step
        writer = EvidenceJournal(path)
    completed = writer.finish()
    assert read_journal(path).complete
    assert completed.result.steps == read_journal(path).steps
    assert writer.finish() == completed
    with pytest.raises(ValueError, match="finalized"):
        writer.append(step)


@pytest.fixture
def journal(tmp_path, campaign):
    header = JournalHeader(campaign.config, campaign.initial_case_ids, campaign.provenance)
    return EvidenceJournal.create(tmp_path / "journal", header)


def test_incomplete_prefix_cannot_be_finalized(journal, campaign):
    journal.append(campaign.steps[0])
    with pytest.raises(ValueError, match="incomplete"):
        journal.finish()
    assert not read_journal(journal.directory).complete
    with pytest.raises(ValueError, match="next completed"):
        journal.append(campaign.steps[2])
    with pytest.raises(ValueError, match="next completed"):
        journal.append(campaign.steps[0])
    with pytest.raises(ValueError, match="feedback"):
        journal.append(replace(campaign.steps[1], feedback=campaign.steps[0].feedback))
    assert len(read_journal(journal.directory).steps) == 1


def test_io_failure_preserves_previously_completed_steps(journal, campaign, monkeypatch):
    journal.append(campaign.steps[0])
    original = (journal.directory / "step-00000000.json").read_bytes()

    def fail(*args, **kwargs):
        raise OSError("controlled disk failure")

    with monkeypatch.context() as patch:
        patch.setattr("inodefence.evaluation.journal.write_record", fail)
        with pytest.raises(OSError, match="controlled"):
            journal.append(campaign.steps[1])
    assert (journal.directory / "step-00000000.json").read_bytes() == original
    assert read_journal(journal.directory).steps == campaign.steps[:1]
    journal.append(campaign.steps[1])
    assert read_journal(journal.directory).steps == campaign.steps[:2]


def test_torn_published_record_and_missing_record_are_rejected(journal, campaign):
    for step in campaign.steps[:2]:
        journal.append(step)
    first = journal.directory / "step-00000000.json"
    original = first.read_bytes()
    first.write_bytes(original[:-10])
    with pytest.raises(VerificationError):
        read_journal(journal.directory)
    first.unlink()
    with pytest.raises(VerificationError, match="gap"):
        read_journal(journal.directory)


def test_missing_completion_is_incomplete_and_publication_can_be_retried(
    journal, campaign, monkeypatch
):
    for step in campaign.steps:
        journal.append(step)
    original_write = journal_module.write_record

    def fail_marker(path, value):
        if path.name == "completion.json":
            raise OSError("controlled marker failure")
        return original_write(path, value)

    with monkeypatch.context() as patch:
        patch.setattr("inodefence.evaluation.journal.write_record", fail_marker)
        with pytest.raises(OSError, match="marker"):
            journal.finish()
    assert (journal.directory / "campaign" / "manifest.json").is_file()
    assert not read_journal(journal.directory).complete
    original_export = (journal.directory / "campaign" / "steps.jsonl").read_bytes()
    assert journal.finish().result == campaign
    assert (journal.directory / "campaign" / "steps.jsonl").read_bytes() == original_export
    (journal.directory / "step-00000003.json").unlink()
    with pytest.raises(VerificationError, match="completion marker"):
        read_journal(journal.directory)


def test_orphan_temporary_file_is_ignored_but_never_a_completed_record(journal):
    (journal.directory / ".record-interrupted").write_bytes(b"partial")
    assert read_journal(journal.directory).steps == ()
    assert not read_journal(journal.directory).complete
