"""Actual fixed benign reference executions; no benchmark outcome assumptions."""

import pytest

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.replay.benign import benign_replay_cases
from inodefence.targets.python_tarfile import PythonTarfileTarget


@pytest.fixture
def original(tmp_path):
    cases = benign_replay_cases()
    result = run_campaign(cases, PythonTarfileTarget(), CampaignConfig(19, len(cases)))
    directory = tmp_path / "original"
    export_campaign(result, directory)
    return directory
