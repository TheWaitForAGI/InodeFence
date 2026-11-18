"""Write replayable case folders for the #514 hand-labelled fixtures (exploratory; no run).

Design: Drive ``Research/02-엔진(…)/20261118-HOST1-514-실제추출기-표-설계.md`` §2.1 and §2b-6
(W5). For each fixture F01-F14 of ``scripts/oracle_accuracy_fixtures.CASES`` this writes one case
folder that ``inodefence replay`` accepts (``case.json`` in the live-violation schema plus
``input.tar`` = ``build_tar(case)``), and a ``manifest.json`` listing
``{fixture, tar_sha256, case_dir, target, version, extraction_filter}`` that the table
reader (``oracle_accuracy_real_table``) checks
each ``replay.json`` against. Nothing is extracted or run here.

The run conditions are never defaulted: ``--image-id`` (exact ``sha256:…``) and ``--run-settings``
(a JSON object, exactly the keys the target's replay hook requires) are required. Every folder is
read back with ``case_replay.load_replay_request`` and checked with the target's own
``replay_check`` (what ``inodefence replay`` does before it runs anything) before the manifest is
written, so a folder the replay driver would refuse is refused here. The case record says it is a
fixture (``origin: fixture``, ``fixture: Fxx``) and carries no original verdict.


Usage::

    PYTHONPATH=src python -m scripts.analysis.oracle_accuracy_real_cases \\
        --target node-tar --version 7.5.11 --image-id sha256:<64 hex> \\
        --run-settings '{"sentinel_count": null, ...}' --out <folder outside the repo>

Exit codes: 0 written, 2 refused (bad argument, folder exists, or a written folder that replay
would not accept).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any

from scripts.oracle_accuracy_fixtures import CASES

from inodefence.builder import build_tar
from inodefence.case_replay import (
    CASE_FILE,
    CASE_SCHEMA,
    CASE_TAR,
    CaseReplayError,
    load_replay_request,
)
from inodefence.drivers.run_target import load_adapter

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = "manifest.json"
MANIFEST_SCHEMA = "inodefence-514-fixture-cases-v1"
FIXTURES = tuple(f"F{i:02d}" for i in range(1, 15))
TARGETS = ("node-tar", "python-tarfile", "decompress", "oras-go")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")


class Refused(Exception):
    """An argument or written folder that cannot be used (exit 2)."""


def case_record(
    fixture: str,
    tar_bytes: bytes,
    *,
    target: str,
    version: str,
    image_id: str,
    run_settings: dict[str, Any],
) -> dict[str, Any]:
    """The ``case.json`` of one fixture: what ``load_replay_request`` reads, marked as a fixture,
    with no original verdict (the fixture was never explored)."""
    return {
        "schema": CASE_SCHEMA,
        "origin": "fixture",
        "fixture": fixture,
        "fixture_source": "experiments/configs/oracle-accuracy-fixtures-v1.md",
        "case_id": CASES[fixture].case_id,
        "target": target,
        "version": version,
        "image_id": image_id,
        "run_settings": run_settings,
        "engine_commit": None,
        "status": None,
        "c0": None,
        "c1": None,
        "c2": None,
        "fingerprints": [],
        "observation_complete": None,
        "tar": CASE_TAR,
        "tar_sha256": sha256(tar_bytes).hexdigest(),
        "tar_bytes": len(tar_bytes),
    }


def write_cases(
    out: Path,
    *,
    target: str,
    version: str,
    image_id: str,
    run_settings: dict[str, Any],
    fixtures: Sequence[str] = FIXTURES,
) -> list[dict[str, str]]:
    """Write one case folder per fixture under ``out/<target>-<version>/`` and return the
    manifest rows. Refuses an existing folder; checks each with ``load_replay_request`` and the
    target's ``replay_check``."""
    if target not in TARGETS:
        raise Refused(f"--target must be one of {TARGETS}")
    if _IMAGE_ID.fullmatch(image_id) is None:
        raise Refused("--image-id must be an exact sha256:<64 hex> image id")
    unknown = [f for f in fixtures if f not in FIXTURES]
    if unknown:
        raise Refused(f"unknown or non-executable fixtures {unknown} (F01-F14 only)")
    out = out.resolve()
    if out == REPO_ROOT or out.is_relative_to(REPO_ROOT):
        raise Refused(f"--out must be outside the repository ({REPO_ROOT})")
    cell = out / f"{target}-{version}"
    if cell.exists():
        raise Refused(f"{cell} exists; case folders are never overwritten")
    check = getattr(load_adapter(target), "replay_check", None)
    rows: list[dict[str, str]] = []
    cell.mkdir(parents=True)
    for fixture in fixtures:
        tar_bytes = build_tar(CASES[fixture])
        folder = cell / fixture
        folder.mkdir()
        (folder / CASE_TAR).write_bytes(tar_bytes)
        record = case_record(
            fixture,
            tar_bytes,
            target=target,
            version=version,
            image_id=image_id,
            run_settings=run_settings,
        )
        (folder / CASE_FILE).write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        try:
            request = load_replay_request(folder)
            if check is not None:
                check(request)
        except CaseReplayError as error:
            raise Refused(f"{fixture}: replay would refuse this folder: {error}") from error
        rows.append(
            {
                "fixture": fixture,
                "tar_sha256": record["tar_sha256"],
                "case_dir": str(folder.relative_to(out)),
                "target": target,
                "version": version,
                "extraction_filter": str(run_settings.get("extraction_filter") or ""),
            }
        )
    return rows


def write_manifest(out: Path, rows: list[dict[str, str]]) -> Path:
    """Add ``rows`` to ``out/manifest.json`` (created if missing); a fixture already listed for
    the same target and version is refused."""
    path = out.resolve() / MANIFEST
    existing: list[dict[str, str]] = []
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != MANIFEST_SCHEMA:
            raise Refused(f"{path} is not an {MANIFEST_SCHEMA} manifest")
        existing = list(data["cases"])

    def cell(row: dict[str, str]) -> tuple[str, ...]:
        return (row["fixture"], row["target"], row["version"], row.get("extraction_filter", ""))

    seen = {cell(r) for r in existing}
    clash = [r["fixture"] for r in rows if cell(r) in seen]
    if clash:
        raise Refused(f"manifest already lists {clash} for this target and version")
    path.write_text(
        json.dumps({"schema": MANIFEST_SCHEMA, "cases": existing + rows}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--version", required=True, help="the cell's version (as replay reads it)")
    parser.add_argument("--image-id", required=True, help="exact sha256:<64 hex> of the image")
    parser.add_argument(
        "--run-settings",
        required=True,
        help="JSON object: exactly the keys the target's replay hook requires (no defaults)",
    )
    parser.add_argument("--out", required=True, type=Path, help="folder outside the repository")
    parser.add_argument("--fixtures", nargs="+", default=list(FIXTURES))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return 2 if error.code else 0
    try:
        try:
            settings = json.loads(args.run_settings)
        except ValueError as error:
            raise Refused(f"--run-settings is not JSON: {error}") from error
        if not isinstance(settings, dict):
            raise Refused("--run-settings must be a JSON object")
        rows = write_cases(
            args.out,
            target=args.target,
            version=args.version,
            image_id=args.image_id,
            run_settings=settings,
            fixtures=args.fixtures,
        )
        manifest = write_manifest(args.out, rows)
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"written": len(rows), "manifest": str(manifest)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
