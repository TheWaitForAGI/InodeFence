"""Native closure for M4.1: the generic oracle catches oras-go's boundary violation end to end.

Drives the REAL pinned oras-go image through the ``OrasGoTarget`` adapter and the production
``pipeline.run_case`` (Observer ``capture_state`` + Oracle ``evaluate_contracts``) against the
committed CWD-hardlink fixture, and asserts the generic C0/C1/C2 verdict equals the capability
probe's recorded per-release observation in ``experiments/repro/evidence/``.

This is a container_integration check: it needs host Docker and the pinned images
(``inodefence-oras-go:2.6.1`` affected / ``inodefence-oras-go:2.6.2`` fixed, built from
``tools/oras-go/Dockerfile``), supplied via the ``container_backend`` / ``container_image``
fixtures. The ``check_`` prefix keeps it out of the default ``make check`` collection, which has
neither Docker nor these images; it is the production-path twin of the CI-runnable
``tests/test_oras_go_generality.py``.

Generic oracle only: ``oras_go_version`` is used solely as a key into the committed probe record,
never as a decision condition. No CVE identifier, PoC seed, or answer path enters any verdict.
"""

import json
from pathlib import Path

from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EntryType,
    ExecutionStatus,
    IdentityEvidence,
)
from inodefence.pipeline import run_case
from inodefence.targets.oras_go import OrasGoTarget

_EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "experiments"
    / "repro"
    / "evidence"
    / "oras_go_cwd_hardlink.json"
)
_PER_RELEASE = {
    role["oras_go_version"]: role["verdict"]["c1_identity_shared"]
    for role in json.loads(_EVIDENCE.read_text(encoding="utf-8"))["per_role"].values()
}

_ORAS_GO_CASE = ArchiveCase(
    (ArchiveEntry("d/evil", EntryType.HARDLINK, link_target="outside/sentinel.txt"),)
)


def test_native_oras_go_oracle_matches_probe(container_backend, container_image):
    target = OrasGoTarget.bind(container_backend, container_image)
    version = target.provenance.target_version  # oras-go=<ver>;go=<ver>
    oras_go_version = version.split(";", 1)[0].split("=", 1)[1]
    expected_shared = _PER_RELEASE.get(oras_go_version)
    if expected_shared is None:
        import pytest

        pytest.skip(f"oras-go {oras_go_version} is not in the capability-probe record")

    result = run_case(_ORAS_GO_CASE, target)
    c0, c1, c2 = result.violations
    assert not c0.violated

    if expected_shared:
        # Affected release (v2.6.1): oras-go resolves the hardlink target against the working
        # directory, so an extract/ object shares the sentinel inode and the sentinel gains a
        # hard link -- the production oracle must see exactly C1+C2.
        assert result.execution.status == ExecutionStatus.SUCCESS
        assert c1.violated and c2.violated
        (identity,) = c1.evidence
        assert isinstance(identity, IdentityEvidence)
        assert identity.internal_path.startswith("extract/")
        assert identity.sentinel_path == "outside/sentinel.txt"
    else:
        # Fixed release (v2.6.2): oras-go redirects the target inside the extraction root and
        # refuses the escaping link -- nothing aliases the sentinel, so no violation remains.
        assert result.execution.status == ExecutionStatus.REJECTED
        assert not c1.violated and not c2.violated
