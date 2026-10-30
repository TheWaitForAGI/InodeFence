"""Native closure for M4.2: the generic oracle catches decompress's boundary violation end to end.

Drives the REAL pinned decompress image through the ``DecompressJsTarget`` adapter and the
production ``pipeline.run_case`` (Observer ``capture_state`` + Oracle ``evaluate_contracts``)
against the committed hardlink fixture, and asserts the generic C0/C1/C2 verdict equals the
capability probe's recorded per-release observation in ``experiments/repro/evidence/``.

This is a container_integration check: it needs host Docker and the pinned images
(``inodefence-decompress:4.2.1`` affected / ``inodefence-decompress:11.1.4`` fixed, built from
``tools/decompress/Dockerfile``), supplied via the ``container_backend`` / ``container_image``
fixtures. The ``check_`` prefix keeps it out of the default ``make check`` collection; it is the
production-path twin of the CI-runnable ``tests/test_decompress_generality.py``.

Generic oracle only: the module@version string keys the committed probe record, never a decision
condition. No CVE identifier, PoC seed, or answer path enters any verdict.
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
from inodefence.targets.decompress_js import DecompressJsTarget

_EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "experiments"
    / "repro"
    / "evidence"
    / "decompress_hardlink.json"
)
_PER_RELEASE = {
    f"{role['decompress_module']}@{role['decompress_version']}": role["verdict"][
        "c1_identity_shared"
    ]
    for role in json.loads(_EVIDENCE.read_text(encoding="utf-8"))["per_role"].values()
}

_DECOMPRESS_CASE = ArchiveCase(
    (ArchiveEntry("evil", EntryType.HARDLINK, link_target="outside/sentinel.txt"),)
)


def test_native_decompress_oracle_matches_probe(container_backend, container_image):
    target = DecompressJsTarget.bind(container_backend, container_image)
    version = target.provenance.target_version  # decompress=<module>@<ver>;node=<ver>
    release = version.split(";", 1)[0].split("=", 1)[1]  # <module>@<ver>
    expected_shared = _PER_RELEASE.get(release)
    if expected_shared is None:
        import pytest

        pytest.skip(f"decompress {release} is not in the capability-probe record")

    result = run_case(_DECOMPRESS_CASE, target)
    c0, c1, c2 = result.violations
    assert not c0.violated

    if expected_shared:
        # Affected release (decompress 4.2.1): the hardlink target is resolved against the
        # working directory, so an extract/ object shares the sentinel inode and the sentinel
        # gains a hard link -- the production oracle must see exactly C1+C2.
        assert result.execution.status == ExecutionStatus.SUCCESS
        assert c1.violated and c2.violated
        (identity,) = c1.evidence
        assert isinstance(identity, IdentityEvidence)
        assert identity.internal_path.startswith("extract/")
        assert identity.sentinel_path == "outside/sentinel.txt"
    else:
        # Fixed fork (@xhmikosr/decompress 11.1.4): the target is redirected inside the
        # extraction root and the escaping link is refused -- no violation remains.
        assert result.execution.status == ExecutionStatus.REJECTED
        assert not c1.violated and not c2.violated
