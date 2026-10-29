"""Generality (M4.2): the unchanged generic C0/C1/C2 oracle catches an archive boundary
violation in a THIRD, independent extractor -- decompress (JavaScript) -- and the maintained
fork's fixed release contains it.

This is a controlled reference differential on real decompress releases, judged by the
production Observer + Oracle through ``run_case``. It is NOT a node-tar/oras-go result and NOT a
fuzzer finding: it shows the SAME outcome-based oracle, unchanged, fires on a third extractor
(which uses the ``decompress-tar`` / ``tar-stream`` parser, distinct from node-tar's ``tar``).

The OBSERVED real-decompress behaviour lives in the committed capability-probe evidence
(``experiments/repro/decompress_hardlink.py`` -> ``experiments/repro/evidence/
decompress_hardlink.json``): decompress 4.2.1 (CVE-2026-39243) passes a tar hardlink's Linkname
to ``fs.link`` without validation, so a relative target resolves against the process CWD and an
``extract/`` object aliases the external sentinel (reference nlink 1 -> 2); the maintained fork
@xhmikosr/decompress 11.1.4 redirects the target inside the extraction root and refuses the
link. ``test_committed_probe_evidence_...`` pins that observation.

The ``run_case`` test REPRODUCES 4.2.1's shared-inode post-state on a real disposable sandbox
with a controlled extractor and judges it with the production oracle, unchanged. The native
closure, driving the REAL decompress image through the ``DecompressJsTarget`` adapter + the
container backend, is the controller-run companion (host Docker + the pinned images), out of
``make check``.

Generic oracle only: the release strings are evidence labels, never decision conditions, and no
CVE identifier, PoC seed, or answer path is baked into any verdict. Purely additive.
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
    / "decompress_hardlink.json"
)

# The controlled fixture, same geometry as the capability probe: one hardlink whose link target
# has no "..", yet decompress resolves it (via fs.link) against the process working directory.
_DECOMPRESS_CASE = ArchiveCase(
    (ArchiveEntry("evil", EntryType.HARDLINK, link_target="outside/sentinel.txt"),)
)


class DecompressHardlinkReproExtractor:
    """Reproduce decompress 4.2.1's observed post-state on a real disposable sandbox.

    decompress 4.2.1 passes the raw hardlink Linkname to ``fs.link``, which resolves a relative
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
                raise AssertionError(f"decompress repro left the sandbox: {path}")
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
                    # The decompress bug: the raw relative Linkname is resolved against the
                    # working directory (sandbox root), not the extraction root.
                    os.link(inside(sandbox_root / member.linkname), destination)
                else:
                    raise AssertionError(f"unexpected repro TAR member: {member.name}")
        return ExecutionResult(
            "decompress-4.2.1-hardlink-repro", "4.2.1", (), ExecutionStatus.SUCCESS, 0, "", "", 0.0
        )


class DecompressFixedReproExtractor:
    """Reproduce the fixed fork's observed outcome: the escaping link is refused.

    @xhmikosr/decompress 11.1.4 redirects the hardlink target inside the extraction root (a path
    that does not exist), so ``fs.link`` fails and nothing is created in ``extract/``. The
    adapter records this as REJECTED; the post-state carries no boundary violation.
    """

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        return ExecutionResult(
            "decompress-11.1.4-hardlink-repro",
            "11.1.4",
            (),
            ExecutionStatus.REJECTED,
            2,
            "",
            "ENOENT: no such file or directory, link inside extraction root",
            0.0,
        )


def _evidence() -> dict:
    return json.loads(_EVIDENCE.read_text(encoding="utf-8"))


def test_committed_probe_evidence_records_the_hardlink_boundary() -> None:
    """Pin the OBSERVED real-decompress result (4.2.1 shares the inode; the fork declines)."""
    evidence = _evidence()
    assert evidence["fixture"] == "decompress_hardlink"
    assert evidence["roles"] == {"affected": "4.2.1", "fixed": "11.1.4"}
    assert evidence["affected_shared"] is True
    assert evidence["fixed_shared"] is False
    assert evidence["boundary_ok"] is True

    affected = evidence["per_role"]["affected"]
    assert affected["decompress_module"] == "decompress"
    assert affected["verdict"]["outcome"] == "resolved"
    assert affected["verdict"]["c1_identity_shared"] is True
    assert affected["verdict"]["shared_objects"] == ["extract/evil"]
    assert affected["raw"]["nlink_before"] == 1
    assert affected["raw"]["nlink_after"] == 2

    fixed = evidence["per_role"]["fixed"]
    assert fixed["decompress_module"] == "@xhmikosr/decompress"
    assert fixed["verdict"]["outcome"] == "declined"
    assert fixed["verdict"]["c1_identity_shared"] is False
    assert fixed["raw"]["shared_identity"] == []


def test_production_oracle_matches_probe_on_the_affected_hardlink() -> None:
    """The unchanged production Observer + Oracle judge 4.2.1's post-state as C1+C2.

    The controlled extractor recreates the observed outcome (``extract/evil`` hardlinked to the
    sentinel) on a real disposable sandbox; the production oracle, unchanged, then judges it.
    """
    result = run_case(_DECOMPRESS_CASE, DecompressHardlinkReproExtractor())
    assert result.execution.status == ExecutionStatus.SUCCESS
    assert "node" not in result.execution.target_id

    c0, c1, c2 = result.violations
    assert (c0.violated, c1.violated, c2.violated) == (False, True, True)
    (identity,) = c1.evidence
    assert isinstance(identity, IdentityEvidence)
    # The same relation the probe computes inline: an extract/ object shares the external
    # sentinel's inode (the probe calls it shared_identity; the oracle calls it C1 evidence).
    assert (identity.internal_path, identity.sentinel_path) == (
        "extract/evil",
        "outside/sentinel.txt",
    )

    assert c1.violated == _evidence()["affected_shared"]


def test_production_oracle_matches_probe_on_the_fixed_release() -> None:
    """The fixed fork refuses the escaping link, so the oracle reports no violation."""
    result = run_case(_DECOMPRESS_CASE, DecompressFixedReproExtractor())
    assert result.execution.status == ExecutionStatus.REJECTED
    assert tuple(verdict.violated for verdict in result.violations) == (False, False, False)
    assert result.violations[1].violated == _evidence()["fixed_shared"]
