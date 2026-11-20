"""#542 decision A (W4 condition): the M4 record mode itself writes the same bytes after streaming.

``decompress-effect-campaign`` and ``oras-go-effect-campaign`` are the modes the past M4 runs used.
Decision A makes their controller functions stream steps into the report collectors instead of
keeping every run. The W4 condition is that the old and the new path give byte-identical records
**in that mode itself**, not only in the collectors: so the controller functions
(``run_native_decompress_campaign``, ``run_native_oras_go_campaign``) are run end to end here
against the targets' no-Docker extracting backends, and the evidence file's sha256 is compared
with ``tests/fixtures/m4-record-mode-542/golden.json``. The golden values were written from the
controller **before** the change (``f523f63`` = ``bd20920``'s base); a change in any byte fails.

Configurations: both targets, two seeds, two budgets, the default and FAST identity schedule, and
for oras-go the opt-in artifact layout; decompress also over its accepted search policies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.container_controller import (
    run_native_decompress_campaign,
    run_native_oras_go_campaign,
)
from tests import test_decompress_effect_campaign as dtest
from tests import test_oras_go_effect_campaign as otest

from inodefence.feedback import EffectSearchPolicy

pytestmark = pytest.mark.skipif(
    not Path("/var/lib/inodefence").is_dir(),
    reason="disposable sandbox requires the Linux runtime root (Dev Container)",
)

GOLDEN = Path(__file__).parent / "fixtures" / "m4-record-mode-542" / "golden.json"

#: The default (absent: the gradient arm) and two other accepted search policies.
DECOMPRESS_POLICIES = (
    None,
    EffectSearchPolicy.P0_FINAL_STATE.value,
    EffectSearchPolicy.P1_EFFECT_RETENTION.value,
)


def _configs() -> list[tuple[str, dict[str, Any]]]:
    configs: list[tuple[str, dict[str, Any]]] = []
    for seed in (7, 11):
        for budget in (6, 20):
            for every in (None, 2):
                for policy in DECOMPRESS_POLICIES:
                    configs.append(
                        (
                            "decompress",
                            {"seed": seed, "budget": budget, "every": every, "policy": policy},
                        )
                    )
                for layout in (None, "on"):
                    configs.append(
                        (
                            "oras-go",
                            {"seed": seed, "budget": budget, "every": every, "layout": layout},
                        )
                    )
    return configs


def _key(name: str, config: dict[str, Any]) -> str:
    return name + ":" + ",".join(f"{k}={config[k]}" for k in sorted(config))


def run_record(name: str, config: dict[str, Any], tmp_path: Path) -> tuple[int, bytes]:
    """Run one controller campaign function; return its exit code and evidence bytes."""
    evidence = tmp_path / f"{_key(name, config).replace(':', '_').replace(',', '_')}.json"
    args = argparse.Namespace(
        seed=config["seed"],
        budget=config["budget"],
        mutation_policy=None,
        policy=config.get("policy"),
        identity_check_every=config["every"],
        oras_go_artifact_layout=config.get("layout"),
    )
    # The targets' no-Docker extracting backends stand in for the container backend.
    backend: Any
    if name == "decompress":
        backend = dtest._ExtractingBackend(dtest._identity_bytes())
        code = run_native_decompress_campaign(backend, dtest._IMAGE, evidence, args)
    else:
        backend = otest._ExtractingBackend(otest._identity_bytes())
        code = run_native_oras_go_campaign(backend, otest._IMAGE, evidence, args)
    return code, evidence.read_bytes()


def test_the_golden_covers_every_configuration() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert set(golden) == {_key(name, config) for name, config in _configs()}


@pytest.mark.parametrize(("name", "config"), _configs(), ids=[_key(n, c) for n, c in _configs()])
def test_the_m4_record_mode_writes_the_same_bytes(
    name: str, config: dict[str, Any], tmp_path: Path
) -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    code, record = run_record(name, config, tmp_path)
    assert code == 0, record[:400]
    assert hashlib.sha256(record).hexdigest() == golden[_key(name, config)]
