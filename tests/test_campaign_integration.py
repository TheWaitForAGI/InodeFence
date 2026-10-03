"""Linux disposable runtime and safe Python reference campaign repeatability."""

from pathlib import Path

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.feedback import Corpus
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.targets import PythonTarfileTarget


def test_reference_campaign_repeats_semantic_lineage_and_feedback() -> None:
    initial = (
        ArchiveCase((ArchiveEntry("a.txt", EntryType.REGULAR, content=b"a"),)),
        ArchiveCase((ArchiveEntry("dir", EntryType.DIRECTORY, mode=0o755),)),
    )
    config = CampaignConfig(1234, 12)
    first = run_campaign(initial, PythonTarfileTarget(), config)
    second = run_campaign(initial, PythonTarfileTarget(), config)
    assert len(first.steps) == len(second.steps) == config.execution_budget
    for left, right in zip(first.steps, second.steps, strict=True):
        assert (left.index, left.origin, left.parent_case_id, left.result.case, left.feedback) == (
            right.index,
            right.origin,
            right.parent_case_id,
            right.result.case,
            right.feedback,
        )
        assert left.result.case.case_id == right.result.case.case_id
        assert not Path(left.result.after.sandbox_root).exists()
        assert not Path(right.result.after.sandbox_root).exists()
    assert first.retained_case_ids == second.retained_case_ids
    assert first.final_corpus_stats == second.final_corpus_stats
    replay = Corpus()
    for step in first.steps:
        assert replay.consider(step.result) == step.feedback
    assert replay.stats == first.final_corpus_stats
    assert tuple(entry.case.case_id for entry in replay.entries) == first.retained_case_ids
    assert len(first.retained_case_ids) > len(initial)
