"""Benign core-produced evidence; no expected benchmark outcome fixtures."""

import pytest

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.generator import minimal_seed_corpus
from inodefence.targets.python_tarfile import PythonTarfileTarget


@pytest.fixture
def campaign():
    seeds = minimal_seed_corpus()
    return run_campaign(seeds, PythonTarfileTarget(), CampaignConfig(17, len(seeds)))


@pytest.fixture
def bundle(tmp_path, campaign):
    destination = tmp_path / "export"
    export_campaign(campaign, destination)
    return destination
