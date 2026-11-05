#!/usr/bin/env python3
"""Rust ``tar`` crate fixed-fixture probe: Tier-B role-assignment input (D039, student research).

Goal: for the pinned affected/fixed Rust ``tar`` crate images (``tools/rust-tar/``), run a FIXED
fixture set through the real crate (``Archive::unpack``, default settings) inside disposable,
hardened containers and record the raw observations, so the preregistered role rule can be applied
BEFORE any fuzzing campaign touches this extractor. Nothing here fuzzes, mutates or searches.

Two fixture groups, kept apart:

* **Role fixtures** = ``scripts.regression_check.build_fixtures()`` verbatim -- the same
  advisory-blind set ``make regression`` runs for node-tar hold-out candidates (hand hardlink
  top-level/nested + symlink-write top-level/nested/dir, external ``ext/reference.bin`` geometry).
  C1/C2 are derived with ``regression_check.evaluate_fixture`` unchanged. The role rule is the one
  frozen in the EXP-3 preregistration draft before any result: any C1/C2 on a role fixture ->
  ``role=holdout`` / H-A, none -> ``role=fix-verification`` / H-B. The script only applies that
  rule to what it observed; registering the target stays with the preregistration owner.
* **Ground truth** = one fixture transcribed from the pinned pair's advisory description (a symlink
  to the parent directory, then a regular file beneath it). It is reported separately as an
  outside-extraction-root namespace differential that checks the affected/fixed pin. It never enters
  the role rule, the oracle, the feedback or any seed corpus (D005/D006; research rule 3).

Honesty / research invariants:
  - Hand-built fixed fixtures, not fuzzer-discovered inputs; no effectiveness or discovery claim.
  - No release string or advisory id is a decision condition; versions are evidence keys only.
  - Each run uses its own disposable, network-isolated, read-only container (writable /work and
    /tmp tmpfs only, all capabilities dropped, non-root distroless image). The whole sandbox and
    reference file are built INSIDE the ephemeral container by the worker's ``probe`` subcommand;
    the host is never the extraction target. No isolation-relaxing flag is used.

Run from the repository root with ``PYTHONPATH=src:.`` (like ``make regression``). Requires Docker
(except ``--dry-run``, which prints the plan and runs no container). Writes one JSON evidence file
under ``--out`` and refuses to overwrite an existing one.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import scripts.regression_check as rc
from experiments.repro import cross_release_identity as cri

from inodefence.builder import build_tar as build_case_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = "tools/rust-tar/Dockerfile"
# `tar` crate release per role (tools/rust-tar/{affected,fixed}/Cargo.toml); evidence keys only.
ROLES: dict[str, str] = {"affected": "0.4.35", "fixed": "0.4.36"}
IMAGE = "inodefence-rust-tar:{version}"
# Ground-truth provenance label for the pinned pair (README); never a decision condition.
GROUND_TRUTH_ADVISORY = "RUSTSEC-2021-0080"
ROLE_RULE = (
    "any C1/C2 on a role fixture -> role=holdout, hypothesis=H-A; "
    "none -> role=fix-verification, hypothesis=H-B "
    "(EXP-3 preregistration (a)3, fixed before results)"
)
EVIDENCE_NAME = "rust_tar_fixture_probe.json"
# Same hardened run shape as experiments/repro/oras_go_cwd_hardlink.py.
_HARDENED_RUN = (
    "run",
    "--rm",
    "--network",
    "none",
    "--read-only",
    "--tmpfs",
    "/work:rw,size=16m,mode=1777",
    "--tmpfs",
    "/tmp:rw,size=16m,mode=1777",
    "--cap-drop",
    "ALL",
)


@dataclass(frozen=True, slots=True)
class GroundTruthFixture:
    """The advisory-described geometry, kept out of the role rule."""

    name: str
    tar: bytes


def ground_truth_fixture() -> GroundTruthFixture:
    """A symlink to the parent directory followed by a regular file beneath it (advisory text)."""
    case = ArchiveCase(
        (
            ArchiveEntry("up", EntryType.SYMLINK, link_target="..", mode=0o777),
            ArchiveEntry("up/created/nested/file", EntryType.REGULAR, content=b"ground-truth"),
        )
    )
    return GroundTruthFixture("symlink_parent_then_nested_file", build_case_tar(case))


def probe_command(image: str, tar_b64: str, ref_b64: str) -> list[str]:
    """The hardened ``docker run`` argv for one fixture through the worker's ``probe`` mode."""
    return [
        "docker",
        *_HARDENED_RUN,
        "-e",
        f"TAR_B64={tar_b64}",
        "-e",
        f"REF_B64={ref_b64}",
        image,
        "probe",
    ]


def identify_command(image: str) -> list[str]:
    return ["docker", *_HARDENED_RUN, image, "identify"]


def build_command(role: str, version: str) -> list[str]:
    return [
        "docker",
        "build",
        "-q",
        "-f",
        DOCKERFILE,
        "--build-arg",
        f"ROLE={role}",
        "-t",
        IMAGE.format(version=version),
        ".",
    ]


def _run(argv: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout, check=False
    )


def _last_json_line(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return {"_run_error": True, "_rc": result.returncode, "_stderr": result.stderr[-400:]}


def outside_namespace_changed(raw: dict[str, Any]) -> bool | None:
    """Did any object outside the extraction root appear, disappear or change identity/type?"""
    if raw.get("_run_error"):
        return None
    keys = ("outside_created", "outside_removed", "outside_changed")
    if not all(isinstance(raw.get(key), list) for key in keys):
        return None
    return any(raw[key] for key in keys)


def role_by_rule(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    """Apply the preregistered role rule to observed role-fixture rows (no prediction)."""
    if not rows or any(row["c1_or_c2"] is None for row in rows):
        return {"role": None, "hypothesis": None, "reason": "a role fixture did not complete"}
    if any(row["c1_or_c2"] for row in rows):
        return {"role": "holdout", "hypothesis": "H-A", "reason": "C1/C2 observed"}
    return {"role": "fix-verification", "hypothesis": "H-B", "reason": "no C1/C2 observed"}


def evaluate_role_fixture(fixture: rc.RegressionFixture, raw: dict[str, Any]) -> dict[str, Any]:
    row = rc.evaluate_fixture(fixture, raw)
    row["outside_namespace_changed"] = outside_namespace_changed(raw)
    row["raw"] = raw
    return row


def evaluate_ground_truth(fixture: GroundTruthFixture, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture": fixture.name,
        "outcome": "run_error" if raw.get("_run_error") else cri.verdict(raw).get("outcome"),
        "outside_namespace_changed": outside_namespace_changed(raw),
        "outside_created": raw.get("outside_created"),
        "raw": raw,
    }


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def dry_run() -> dict[str, Any]:
    """Describe the plan without running any container (verifiable without Docker)."""
    fixtures = rc.build_fixtures()
    truth = ground_truth_fixture()
    return {
        "roles": ROLES,
        "images": {role: IMAGE.format(version=version) for role, version in ROLES.items()},
        "build": {role: build_command(role, version) for role, version in ROLES.items()},
        "role_rule": ROLE_RULE,
        "role_fixtures": [
            {
                "fixture": f.name,
                "kind": f.kind,
                "tar_bytes": len(f.tar),
                "tar_sha256": hashlib.sha256(f.tar).hexdigest(),
            }
            for f in fixtures
        ],
        "ground_truth": {
            "fixture": truth.name,
            "advisory": GROUND_TRUTH_ADVISORY,
            "tar_bytes": len(truth.tar),
            "tar_sha256": hashlib.sha256(truth.tar).hexdigest(),
            "in_role_rule": False,
        },
        "runs_per_image": len(fixtures) + 1,
        "probe_argv_shape": probe_command("<image>", "<TAR_B64>", "<REF_B64>"),
        "note": "dry-run: no container executed; the real run needs Docker and the built images",
    }


def probe_role(role: str, version: str, *, skip_build: bool) -> dict[str, Any]:
    image = IMAGE.format(version=version)
    if not skip_build:
        built = _run(build_command(role, version), timeout=1800)
        if built.returncode != 0:
            return {"tar_crate_version": version, "build_error": built.stderr[-800:]}
    image_id = _run(["docker", "image", "inspect", image, "--format", "{{.Id}}"]).stdout.strip()
    identity = _last_json_line(_run(identify_command(image), timeout=60))
    ref_b64 = _b64(cri.REFERENCE_CONTENT)
    rows = [
        evaluate_role_fixture(
            fixture, _last_json_line(_run(probe_command(image, _b64(fixture.tar), ref_b64), 90))
        )
        for fixture in rc.build_fixtures()
    ]
    truth = ground_truth_fixture()
    truth_raw = _last_json_line(_run(probe_command(image, _b64(truth.tar), ref_b64), 90))
    return {
        "tar_crate_version": version,
        "image": image,
        "image_id": image_id,
        "identify": identity,
        "role_fixtures": rows,
        "role_by_rule": role_by_rule(rows),
        "ground_truth": evaluate_ground_truth(truth, truth_raw),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rust tar crate fixed-fixture probe (Tier-B)")
    parser.add_argument("--out", help="evidence directory (required unless --dry-run)")
    parser.add_argument("--skip-build", action="store_true", help="reuse already-built images")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, run no container")
    args = parser.parse_args(argv)
    if args.dry_run:
        print(json.dumps(dry_run(), indent=2, sort_keys=True))
        return 0
    if not args.out:
        parser.error("--out is required unless --dry-run")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    evidence = out / EVIDENCE_NAME
    if evidence.exists():
        parser.error(f"{evidence} exists; raw evidence is never overwritten")

    per_role = {
        role: probe_role(role, version, skip_build=args.skip_build)
        for role, version in ROLES.items()
    }
    truth = {
        role: result.get("ground_truth", {}).get("outside_namespace_changed")
        for role, result in per_role.items()
    }
    record = {
        "probe": "rust_tar_fixture_probe",
        "label": "fixed-fixture probe (Tier-B role input; not a campaign, not qualification)",
        "roles": ROLES,
        "role_rule": ROLE_RULE,
        "ground_truth_advisory": GROUND_TRUTH_ADVISORY,
        "ground_truth_pair_distinguished": truth.get("affected") is True
        and truth.get("fixed") is False,
        "per_role": per_role,
    }
    with evidence.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
    summary = {
        role: {
            "role_by_rule": result.get("role_by_rule"),
            "ground_truth_outside_namespace_changed": truth.get(role),
        }
        for role, result in per_role.items()
    }
    print(json.dumps(summary, sort_keys=True))
    completed = all(
        result.get("role_by_rule", {}).get("role") is not None for result in per_role.values()
    )
    return 0 if completed else 2


if __name__ == "__main__":
    raise SystemExit(main())
