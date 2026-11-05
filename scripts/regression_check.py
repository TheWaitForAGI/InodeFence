"""Maintainer regression command: do known identity/effect fixtures still breach at a version?

`make regression TAR_VERSION=<x>` runs a fixed set of hand-built boundary fixtures against the
``inodefence-node-tar-effect:<x>`` image and prints a one-line PASS/FAIL plus JSON: did any
fixture make an extracted object share the external reference file's inode (C1) or change that
reference (C2)? PASS = no C1/C2 on any fixture at this version; FAIL = at least one. The node-tar
version is a plain input argument; no release id or CVE identifier is a decision condition.

Reuse, not reinvention (existing code is called, never modified):
- The execution engine is ``experiments.repro.cross_release_identity.run_one`` -- the same
  disposable-container path (host is never the extraction target) the M2.1 hand probe uses. Its
  node program sets up an external ``ext/reference.bin`` beside ``extract/`` and reports, after
  extraction, which extracted objects share the reference inode and the reference's before/after
  state. C1 is ``shared_identity``; C2 is a change in the reference's (ino, nlink, size, type).
- The hand hardlink fixtures (top-level, nested) are ``cross_release_identity.FIXTURES`` verbatim.
- The symlink-write fixtures are the #205 false-negative matrix placements (symlink-then-write,
  nested, and dir-symlink) in the repro's ``ext/reference.bin`` geometry; symlink entries are
  built with the production ``inodefence.builder`` (``cross_release_identity.build_tar`` has no
  symlink support) and handed to the same ``run_one``.

No oracle code is touched. ``--dry-run`` prints the plan and runs no container, so the wrapper is
verified without Docker; the real run is the maintainer's / Runtime lane's.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
from dataclasses import dataclass
from typing import Any

from experiments.repro import cross_release_identity as cri

from inodefence.builder import build_tar as build_case_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType

# The external reference the repro node program creates beside extract/ is ext/reference.bin.
_REF = "../ext/reference.bin"
_VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+)*")


@dataclass(frozen=True, slots=True)
class RegressionFixture:
    """One fixture plus a lineage note; ``tar`` is the raw archive bytes to extract."""

    name: str
    kind: str  # "hand-hardlink" (from cross_release_identity) or "fn-symlink" (#205 matrix)
    tar: bytes


def _symlink_write_case(symlink_name: str, link_target: str, write_name: str) -> bytes:
    """A symlink-then-write archive built with the production builder (symlink-capable)."""
    case = ArchiveCase(
        (
            ArchiveEntry(symlink_name, EntryType.SYMLINK, link_target=link_target, mode=0o777),
            ArchiveEntry(write_name, EntryType.REGULAR, content=b"regression-overwrite"),
        )
    )
    return build_case_tar(case)


def build_fixtures() -> tuple[RegressionFixture, ...]:
    """Assemble the regression fixture set: repro hand hardlinks + #205 symlink-write matrix.

    Every fixture targets the repro's external ``ext/reference.bin`` so the shared node program
    observes C1/C2 uniformly. Hand hardlinks reuse ``cross_release_identity`` verbatim.
    """
    fixtures = [
        RegressionFixture(name, "hand-hardlink", cri.build_tar(entries))
        for name, entries in cri.FIXTURES.items()
    ]
    fixtures += [
        RegressionFixture(
            "toplevel_symlink_write", "fn-symlink", _symlink_write_case("link", _REF, "link")
        ),
        RegressionFixture(
            "nested_symlink_write",
            "fn-symlink",
            _symlink_write_case("sub/link", f"../{_REF}", "sub/link"),
        ),
        RegressionFixture(
            "dir_symlink_write",
            "fn-symlink",
            _symlink_write_case("d", "../ext", "d/reference.bin"),
        ),
    ]
    return tuple(fixtures)


def c1_from_raw(raw: dict[str, Any]) -> bool | None:
    """C1: did an extracted object share the external reference's inode? None if the run failed."""
    if raw.get("_run_error"):
        return None
    return bool(raw.get("shared_identity"))


def c2_from_raw(raw: dict[str, Any]) -> bool | None:
    """C2: did the external reference's (ino, nlink, size, type) change? None if unknown."""
    if raw.get("_run_error"):
        return None
    before, after = raw.get("reference_before"), raw.get("reference_after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    if after.get("error"):
        return True
    return any(before.get(key) != after.get(key) for key in ("ino", "nlink", "size", "type"))


def evaluate_fixture(fixture: RegressionFixture, raw: dict[str, Any]) -> dict[str, Any]:
    c1, c2 = c1_from_raw(raw), c2_from_raw(raw)
    return {
        "fixture": fixture.name,
        "kind": fixture.kind,
        "c1_identity_shared": c1,
        "c2_reference_changed": c2,
        "outcome": "run_error" if raw.get("_run_error") else cri.verdict(raw).get("outcome"),
        "c1_or_c2": None if c1 is None or c2 is None else bool(c1 or c2),
    }


def summarize(tar_version: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    errored = [r for r in rows if r["c1_or_c2"] is None]
    breached = [r for r in rows if r["c1_or_c2"] is True]
    if errored:
        verdict = "ERROR"
    elif breached:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    return {
        "tar_version": tar_version,
        "image": cri.IMAGE.format(release=tar_version),
        "verdict": verdict,
        "breached_fixtures": [r["fixture"] for r in breached],
        "errored_fixtures": [r["fixture"] for r in errored],
        "fixtures": rows,
    }


def _validate_version(parser: argparse.ArgumentParser, version: str) -> None:
    if not version or _VERSION_RE.fullmatch(version) is None:
        parser.error("TAR_VERSION must be a dotted numeric node-tar version, e.g. 7.5.2")


def run(tar_version: str) -> dict[str, Any]:
    """Execute every fixture through the repro disposable-container path and summarize."""
    fixtures = build_fixtures()
    rows = []
    for fixture in fixtures:
        raw = cri.run_one(tar_version, base64.b64encode(fixture.tar).decode())
        rows.append(evaluate_fixture(fixture, raw))
    return summarize(tar_version, rows)


def dry_run(tar_version: str) -> dict[str, Any]:
    """Describe the plan without running any container (for CI/dev verification)."""
    fixtures = build_fixtures()
    return {
        "tar_version": tar_version,
        "image": cri.IMAGE.format(release=tar_version),
        "would_run": [
            {"fixture": f.name, "kind": f.kind, "tar_bytes": len(f.tar)} for f in fixtures
        ],
        "note": "dry-run: no container executed; real run requires the node-tar effect image",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="node-tar C1/C2 boundary regression check")
    parser.add_argument("--tar-version", required=True, help="node-tar version, e.g. 7.5.2")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan and run no container"
    )
    parser.add_argument("--out", help="also write the JSON summary to this path")
    args = parser.parse_args(argv)
    _validate_version(parser, args.tar_version)

    if args.dry_run:
        summary = dry_run(args.tar_version)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    summary = run(args.tar_version)
    print(
        f"REGRESSION {summary['verdict']} node-tar={summary['tar_version']} "
        f"c1_or_c2={len(summary['breached_fixtures'])}/{len(summary['fixtures'])}"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.out:
        from pathlib import Path

        Path(args.out).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[summary["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
