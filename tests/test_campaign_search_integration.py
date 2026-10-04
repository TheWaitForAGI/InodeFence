"""Tiny trusted-reference campaigns; no benchmark effectiveness claims."""

from hashlib import sha256

import pytest

from inodefence.builder import build_tar
from inodefence.campaign import SearchCampaignConfig, run_search_campaign
from inodefence.feedback import FeedbackProjection, SearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.mutator import MutationPolicy
from inodefence.targets import PythonTarfileTarget


@pytest.mark.parametrize("policy", tuple(SearchPolicy))
def test_search_campaign_runs_existing_trusted_pipeline_with_bound_raw_archives(policy):
    cases = minimal_seed_corpus()
    config = SearchCampaignConfig(
        11, 6, policy, MutationPolicy.M1_NO_REORDER, FeedbackProjection.A1
    )
    result = run_search_campaign(cases, PythonTarfileTarget(), config)
    assert len(result.steps) == result.final_corpus_stats.observations == 6
    assert result.provenance.target == PythonTarfileTarget().provenance
    assert result.provenance.isolation is None
    for step in result.steps:
        assert step.result.archive_sha256 == sha256(build_tar(step.result.case)).hexdigest()
        assert step.result.after.sandbox_root.startswith("/var/lib/inodefence/")
        assert len(step.result.violations) == 3  # all C0/C1/C2 verdicts, including nonviolations
    assert len(result.retained_case_ids) == result.final_corpus_stats.retained_cases
    if policy == SearchPolicy.B0:
        assert result.retained_case_ids == ()
        assert result.steps[-1].parent_case_id == result.steps[-2].result.case.case_id
