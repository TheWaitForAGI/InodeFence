"""Recompute the node internal-completion qualification summary from raw evidence."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.qualify_node_internal_completion import (
    EXPERIMENT_ID,
    qualification_cases,
    summarize,
)


def analyze_evidence(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != 1 or value.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("not node internal-completion qualification v3 evidence")
    cases = qualification_cases()
    configured_cases = value.get("config", {}).get("cases", {})
    if set(configured_cases) != set(cases):
        raise ValueError("qualification case set mismatch")
    for name, case in cases.items():
        if configured_cases[name].get("case_id") != case.case_id:
            raise ValueError(f"qualification case identity mismatch: {name}")
    recomputed = summarize(cases, value["runs"])
    if recomputed != value.get("mechanical_summary"):
        raise ValueError("stored mechanical summary does not match raw runs")
    return recomputed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    raw = args.evidence.read_bytes()
    value = json.loads(raw)
    summary = analyze_evidence(value)
    result = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "raw_evidence": str(args.evidence),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
        "source": value["source"],
        "target": value["target"],
        "config": value["config"],
        "mechanical_summary": summary,
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        if args.output.exists():
            raise FileExistsError(f"refusing to overwrite analysis: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
