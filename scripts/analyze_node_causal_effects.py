"""Recompute the mechanical node causal-effect qualification summary."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.qualify_node_causal_effects import (
    EXPERIMENT_ID,
    archive_bytes,
    qualification_cases,
    summarize,
)


def analyze_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    if evidence.get("schema_version") != 1 or evidence.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("unexpected causal-effect evidence schema or experiment ID")
    cases = qualification_cases()
    configured = evidence.get("config", {}).get("cases", {})
    if set(configured) != set(cases):
        raise ValueError("qualification case set mismatch")
    for name, case in cases.items():
        if configured[name].get("case_id") != case.case_id:
            raise ValueError(f"case identity mismatch: {name}")
        expected_archive = hashlib.sha256(archive_bytes(name, case)).hexdigest()
        if configured[name].get("archive_sha256") != expected_archive:
            raise ValueError(f"archive identity mismatch: {name}")
    return summarize(cases, evidence["runs"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    evidence = json.loads(args.evidence.read_text())
    summary = analyze_evidence(evidence)
    if summary != evidence.get("mechanical_summary"):
        raise ValueError("stored mechanical summary does not match raw evidence")
    encoded = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            stream.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
