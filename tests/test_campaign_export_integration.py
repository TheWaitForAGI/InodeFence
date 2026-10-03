"""Completed safe reference evidence exports after Linux runtime cleanup."""

import json
from pathlib import Path

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.generator import minimal_seed_corpus
from inodefence.model import canonical_json
from inodefence.targets import PythonTarfileTarget


def test_reference_campaign_evidence_survives_cleanup_and_exports(tmp_path: Path) -> None:
    result = run_campaign(minimal_seed_corpus(), PythonTarfileTarget(), CampaignConfig(11, 8))
    assert all(not Path(step.result.after.sandbox_root).exists() for step in result.steps)
    manifest_path, steps_path = export_campaign(result, tmp_path / "export")
    assert json.loads(manifest_path.read_bytes())["number_of_steps"] == 8
    assert steps_path.read_text().splitlines() == [canonical_json(step) for step in result.steps]
    repeated = export_campaign(result, tmp_path / "repeated")
    assert repeated[0].read_bytes() == manifest_path.read_bytes()
    assert repeated[1].read_bytes() == steps_path.read_bytes()
