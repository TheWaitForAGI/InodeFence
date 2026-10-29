"""M2.2: the hand-probe cross-release verdict agrees with the production Observer + Oracle.

Background. M2.1 (``experiments/repro/cross_release_identity.py``) is a hand probe: it extracts
a top-level external-reference hardlink through real node-tar releases inside disposable
containers and records, with its OWN inline logic, whether an extracted object shares the
reference file's ``(st_dev, st_ino)`` identity. Its committed evidence
(``experiments/repro/evidence/``) records node-tar 7.5.2 sharing the external reference inode
(reference nlink 1 -> 2) and 7.5.3 declining the ``..`` linkpath.

What this module pins. The hand probe's verdict is an ad-hoc inode-identity comparison. This
module shows the UNCHANGED production path (Observer ``capture_state``/``compare_states`` +
Oracle ``evaluate_contracts``, reached through ``pipeline.run_case``) reaches the SAME verdict
on the SAME external-sentinel hardlink outcome: C1 (an extract/ object shares the protected
sentinel's inode) together with C2 (the sentinel's nlink changed). Two independent
implementations of the same inode-identity predicate agreeing is stronger oracle evidence than
either alone.

observed vs reproduced (research invariant). The real node-tar behaviour is OBSERVED and lives
in the committed M2.1 evidence; ``test_committed_handprobe_evidence_...`` pins it. The
``run_case`` test REPRODUCES 7.5.2's shared-inode post-state on a real disposable sandbox with a
controlled extractor and judges it with the production oracle -- the oracle is outcome-based, so
its verdict on that post-state is the verdict the production path assigns. The native closure,
driving the REAL node-tar historical image through ``run_node_tar_effect_case``, is the
controller-run companion ``tests/container_integration/check_cross_release_oracle_agreement.py``
(not collected by ``make check``; needs Docker + the historical images).

Generic oracle only: the release strings below are evidence labels, never decision conditions,
and no CVE identifier, PoC seed, or answer path is baked into any verdict. This test is purely
additive -- it changes no oracle, fixture, or N01 path.
"""

import json
from pathlib import Path

from scripts.oracle_fixture_check import ORACLE_FIXTURES, UncheckedControlledExtractor

from inodefence.model import ExecutionStatus, IdentityEvidence
from inodefence.pipeline import run_case

_EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "experiments" / "repro" / "evidence"
# The production-geometry twin of M2.1's toplevel_hardlink probe: a single top-level hardlink
# entry whose link target escapes the extraction root to the external sentinel.
_C1_FIXTURE = next(fixture for fixture in ORACLE_FIXTURES if fixture.name == "c1")


def _evidence(name: str) -> dict:
    return json.loads((_EVIDENCE_DIR / name).read_text(encoding="utf-8"))


def test_committed_handprobe_evidence_records_the_cross_release_boundary() -> None:
    """Pin the OBSERVED real-node-tar result: 7.5.2 shares the external inode, 7.5.3 declines."""
    toplevel = _evidence("summary.json")["toplevel_hardlink"]
    assert toplevel["fixed_pair"] == ["7.5.2", "7.5.3"]
    assert toplevel["earlier_shared"] is True
    assert toplevel["later_shared"] is False
    assert toplevel["boundary_ok"] is True

    releases = _evidence("toplevel_hardlink.json")["releases"]
    affected = releases["7.5.2"]
    assert affected["verdict"]["outcome"] == "resolved"
    assert affected["verdict"]["c1_identity_shared"] is True
    # An extracted object aliases the external reference, and the reference gains a hard link.
    assert affected["verdict"]["shared_objects"]
    assert affected["raw"]["nlink_before"] == 1
    assert affected["raw"]["nlink_after"] == 2

    fixed = releases["7.5.3"]
    assert fixed["verdict"]["outcome"] == "declined"
    assert fixed["verdict"]["c1_identity_shared"] is False
    assert fixed["raw"]["extract_tree"] == {}


def test_production_oracle_matches_handprobe_on_the_external_sentinel_hardlink() -> None:
    """The production Observer + Oracle judge 7.5.2's post-state exactly as the hand probe does.

    The controlled extractor recreates the observed outcome (``extract/alias`` hardlinked to the
    sentinel) on a real disposable sandbox; the production oracle, unchanged, then judges it.
    """
    result = run_case(_C1_FIXTURE.case, UncheckedControlledExtractor())
    assert result.execution.status == ExecutionStatus.SUCCESS

    c0, c1, c2 = result.violations
    assert (c0.violated, c1.violated, c2.violated) == (False, True, True)
    (identity,) = c1.evidence
    assert isinstance(identity, IdentityEvidence)
    # The same relation the hand probe computes inline: an extract/ object shares the external
    # sentinel's inode (the probe calls it shared_identity; the oracle calls it C1 evidence).
    assert (identity.internal_path, identity.sentinel_path) == (
        "extract/alias",
        "outside/sentinel.txt",
    )

    # Agreement, stated against the committed M2.1 record rather than a literal expectation.
    earlier_shared = _evidence("summary.json")["toplevel_hardlink"]["earlier_shared"]
    assert earlier_shared is True
    assert c1.violated == earlier_shared
