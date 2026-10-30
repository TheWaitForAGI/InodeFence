"""Generality (M4.1): the unchanged generic C0/C1/C2 oracle catches an archive boundary
violation in a SECOND, independent extractor -- oras-go (Go) -- and the fixed release
contains it.

This is a controlled reference differential on real oras-go releases, judged by the
production Observer + Oracle through ``run_case``. It is NOT a node-tar result and NOT a
fuzzer finding: it shows the SAME outcome-based oracle, unchanged, fires on a third extractor.

The OBSERVED real-oras-go behaviour lives in the committed capability-probe evidence
(``experiments/repro/oras_go_cwd_hardlink.py`` -> ``experiments/repro/evidence/
oras_go_cwd_hardlink.json``): v2.6.1 (CVE-2026-50163) resolves a tar hardlink's Linkname
against the process CWD, so an ``extract/`` object aliases the external sentinel (reference
nlink 1 -> 2); v2.6.2 redirects the target inside the extraction root and refuses the link.
``test_committed_probe_evidence_...`` pins that observation.

The ``run_case`` test REPRODUCES v2.6.1's shared-inode post-state on a real disposable sandbox
with a controlled extractor and judges it with the production oracle -- the oracle is
outcome-based, so its verdict on that post-state is the verdict the production path assigns.
The native closure, driving the REAL oras-go image through the ``OrasGoTarget`` adapter + the
container backend, is the controller-run companion (host Docker + the pinned images), out of
``make check``.

Generic oracle only: the release strings are evidence labels, never decision conditions, and
no CVE identifier, PoC seed, or answer path is baked into any verdict. Purely additive -- it
changes no oracle, fixture, or N01 path.
"""

import json
import os
import tarfile
from pathlib import Path

from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    IdentityEvidence,
)
from inodefence.pipeline import run_case

_EVIDENCE = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "repro"
    / "evidence"
    / "oras_go_cwd_hardlink.json"
)

# The controlled fixture, same geometry as the capability probe: one hardlink whose link
# target has no "..", so it passes oras-go's lexical containment check, yet oras-go v2.6.1
# resolves it (as os.Link does) against the process working directory. The "d/" prefix is
# oras-go's directory-artifact title.
_ORAS_GO_CASE = ArchiveCase(
    (ArchiveEntry("d/evil", EntryType.HARDLINK, link_target="outside/sentinel.txt"),)
)


class OrasGoCwdHardlinkReproExtractor:
    """Reproduce oras-go v2.6.1's observed post-state on a real disposable sandbox.

    oras-go v2.6.1 passes the raw hardlink Linkname to ``os.Link``, which resolves a relative
    target against the process working directory -- here the sandbox root, not ``extract/``.
    This extractor follows the tar entries with exactly that resolution, so the hardlink aliases
    the external sentinel, recreating the outcome recorded in the committed probe evidence. Every
    resolved path is asserted to stay inside the disposable sandbox, so the fixture reaches the
    sandbox sentinel but never the host.
    """

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        sandbox_root = Path(os.path.realpath(extraction_root.parent))

        def inside(path: Path) -> Path:
            resolved = Path(os.path.realpath(path))
            if not resolved.is_relative_to(sandbox_root):
                raise AssertionError(f"oras-go repro left the sandbox: {path}")
            return path

        with tarfile.open(archive_path, mode="r:") as archive:
            for member in archive.getmembers():
                destination = inside(extraction_root / member.name.rstrip("/"))
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    stream = archive.extractfile(member)
                    assert stream is not None
                    destination.write_bytes(stream.read())
                elif member.islnk():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    # The oras-go v2.6.1 bug: the raw relative Linkname is resolved against
                    # the working directory (sandbox root), not the extraction root.
                    os.link(inside(sandbox_root / member.linkname), destination)
                else:
                    raise AssertionError(f"unexpected repro TAR member: {member.name}")
        return ExecutionResult(
            "oras-go-v2.6.1-cwd-hardlink-repro",
            "v2.6.1",
            (),
            ExecutionStatus.SUCCESS,
            0,
            "",
            "",
            0.0,
        )


class OrasGoFixedReproExtractor:
    """Reproduce oras-go v2.6.2's observed outcome: the escaping link is refused.

    v2.6.2 redirects the hardlink target inside the extraction root (a path that does not
    exist), so ``os.Link`` fails and nothing is created in ``extract/``. The adapter records
    this as REJECTED; the post-state carries no boundary violation.
    """

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        return ExecutionResult(
            "oras-go-v2.6.2-cwd-hardlink-repro",
            "v2.6.2",
            (),
            ExecutionStatus.REJECTED,
            2,
            "",
            "failed to extract tar: link inside extraction root: no such file or directory",
            0.0,
        )


def _evidence() -> dict:
    return json.loads(_EVIDENCE.read_text(encoding="utf-8"))


def test_committed_probe_evidence_records_the_cwd_hardlink_boundary() -> None:
    """Pin the OBSERVED real-oras-go result: v2.6.1 shares the external inode, v2.6.2 declines."""
    evidence = _evidence()
    assert evidence["fixture"] == "oras_go_cwd_hardlink"
    assert evidence["roles"] == {"affected": "2.6.1", "fixed": "2.6.2"}
    assert evidence["affected_shared"] is True
    assert evidence["fixed_shared"] is False
    assert evidence["boundary_ok"] is True

    affected = evidence["per_role"]["affected"]
    assert affected["oras_go_version"] == "v2.6.1"
    assert affected["verdict"]["outcome"] == "resolved"
    assert affected["verdict"]["c1_identity_shared"] is True
    assert affected["verdict"]["shared_objects"] == ["extract/d/evil"]
    assert affected["raw"]["nlink_before"] == 1
    assert affected["raw"]["nlink_after"] == 2

    fixed = evidence["per_role"]["fixed"]
    assert fixed["oras_go_version"] == "v2.6.2"
    assert fixed["verdict"]["outcome"] == "declined"
    assert fixed["verdict"]["c1_identity_shared"] is False
    assert fixed["raw"]["shared_identity"] == []
    assert fixed["raw"]["nlink_after"] == 1


def test_production_oracle_matches_probe_on_the_affected_cwd_hardlink() -> None:
    """The unchanged production Observer + Oracle judge v2.6.1's post-state as C1+C2.

    The controlled extractor recreates the observed outcome (``extract/d/evil`` hardlinked to
    the sentinel) on a real disposable sandbox; the production oracle, unchanged, then judges it.
    """
    result = run_case(_ORAS_GO_CASE, OrasGoCwdHardlinkReproExtractor())
    assert result.execution.status == ExecutionStatus.SUCCESS
    assert "node" not in result.execution.target_id

    c0, c1, c2 = result.violations
    assert (c0.violated, c1.violated, c2.violated) == (False, True, True)
    (identity,) = c1.evidence
    assert isinstance(identity, IdentityEvidence)
    # The same relation the probe computes inline: an extract/ object shares the external
    # sentinel's inode (the probe calls it shared_identity; the oracle calls it C1 evidence).
    assert (identity.internal_path, identity.sentinel_path) == (
        "extract/d/evil",
        "outside/sentinel.txt",
    )

    # Agreement, stated against the committed probe record rather than a literal expectation.
    assert c1.violated == _evidence()["affected_shared"]


def test_production_oracle_matches_probe_on_the_fixed_release() -> None:
    """The fixed release refuses the escaping link, so the oracle reports no violation."""
    result = run_case(_ORAS_GO_CASE, OrasGoFixedReproExtractor())
    assert result.execution.status == ExecutionStatus.REJECTED
    assert tuple(verdict.violated for verdict in result.violations) == (False, False, False)
    assert result.violations[1].violated == _evidence()["fixed_shared"]
