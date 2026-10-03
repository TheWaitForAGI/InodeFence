"""Seed composition preserves baseline artifacts and explicit campaign input."""

import pytest
from scripts.generate_tar_fixtures import CASE_NAMES, FIXTURE_ROOT, baseline_case

from inodefence.builder import build_tar
from inodefence.campaign import CampaignConfig, CampaignOrigin, run_campaign
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ObjectType
from inodefence.targets import PythonTarfileTarget


@pytest.mark.parametrize("index,name", tuple(enumerate(CASE_NAMES)))
def test_seed_builder_keeps_existing_baseline_bytes(index: int, name: str) -> None:
    seed = minimal_seed_corpus()[index]
    assert seed == baseline_case(name)
    assert build_tar(seed) == (FIXTURE_ROOT / name / "fixture.tar").read_bytes()


def test_seed_corpus_is_explicit_reference_campaign_input() -> None:
    seeds = minimal_seed_corpus()
    result = run_campaign(seeds, PythonTarfileTarget(), CampaignConfig(11, len(seeds)))
    assert tuple(step.result.case for step in result.steps) == seeds
    assert all(
        step.origin == CampaignOrigin.SEED and step.parent_case_id is None for step in result.steps
    )
    assert all(step.result.execution.succeeded for step in result.steps)
    assert all(not verdict.violated for step in result.steps for verdict in step.result.violations)
    hardlink = result.steps[2].result.after
    first, second = hardlink.get("extract/a.txt"), hardlink.get("extract/b.txt")
    assert first is not None and second is not None and first.identity == second.identity
    link = result.steps[3].result.after.get("extract/b.txt")
    assert link is not None and link.object_type == ObjectType.SYMLINK
    assert link.symlink_target == "a.txt"
