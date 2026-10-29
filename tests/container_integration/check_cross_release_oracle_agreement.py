"""Native closure for M2.2: the effect pipeline's oracle agrees with the M2.1 hand probe.

Runs the committed external-sentinel hardlink fixture (``oracle-c1``: a top-level hardlink
``alias -> ../outside/sentinel.txt``, the production-geometry twin of M2.1's toplevel_hardlink
probe) through the REAL effect pipeline ``run_node_tar_effect_case`` against whatever historical
node-tar image the controller provides, and asserts the generic C0/C1/C2 verdict equals the
hand probe's recorded per-release observation in ``experiments/repro/evidence/``.

This is a container_integration check: it is run by ``scripts/container_controller.py`` through
``pytest.main`` with the ``IntegrationFixtures`` plugin (which supplies ``container_backend`` and
``container_image``), e.g. ``--suite check_cross_release_oracle_agreement.py`` against the
``inodefence-node-tar-effect:7.5.2`` / ``7.5.3`` images. The ``check_`` prefix keeps it out of
the default ``make check`` collection, which has neither Docker nor the historical images.

Generic oracle only: ``tar_version`` is used solely as a key into the committed hand-probe
record, never as a decision condition. No CVE identifier, PoC seed, or answer path enters any
verdict. The CI-runnable companion is ``tests/test_cross_release_oracle_agreement.py``.
"""

import json
from pathlib import Path

import pytest
from scripts.generate_tar_fixtures import oracle_case

from inodefence.effect_pipeline import run_node_tar_effect_case
from inodefence.model import ExecutionStatus, IdentityEvidence
from inodefence.targets.node_tar_effect import NativeEffectProfile, NodeTarEffectTarget

_EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "experiments" / "repro" / "evidence"
_PER_RELEASE_SHARED = json.loads((_EVIDENCE_DIR / "summary.json").read_text(encoding="utf-8"))[
    "toplevel_hardlink"
]["per_release_shared"]


def test_native_effect_pipeline_oracle_matches_handprobe(container_backend, container_image):
    target = NodeTarEffectTarget.bind(
        container_backend, container_image, profile=NativeEffectProfile.FULL
    )
    expected_shared = _PER_RELEASE_SHARED.get(target.tar_version)
    if expected_shared is None:
        pytest.skip(f"node-tar {target.tar_version} is not in the M2.1 cross-release record")

    run = run_node_tar_effect_case(oracle_case("oracle-c1"), target)
    c0, c1, c2 = run.result.base_result.violations
    assert not c0.violated

    if expected_shared:
        # Affected release (7.5.2): node-tar follows the ``..`` hardlink, so an extract/ object
        # shares the sentinel inode and the sentinel gains a hard link -- the production oracle
        # must see exactly the C1+C2 the hand probe recorded as c1_identity_shared=true.
        assert run.result.base_result.execution.status == ExecutionStatus.SUCCESS
        assert c1.violated and c2.violated
        (identity,) = c1.evidence
        assert isinstance(identity, IdentityEvidence)
        assert (identity.internal_path, identity.sentinel_path) == (
            "extract/alias",
            "outside/sentinel.txt",
        )
    else:
        # Fixed release (7.5.3): node-tar declines the escaping linkpath, leaving nothing in
        # extract/ and the sentinel untouched -- the production oracle must report no violation.
        assert run.result.base_result.execution.status == ExecutionStatus.REJECTED
        assert not c1.violated and not c2.violated
