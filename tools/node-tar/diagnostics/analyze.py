"""Recompute a diagnostic summary from retained runs; never a qualification decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_bytes())


def semantic_state(snapshot: dict) -> dict:
    """Compare outcome and persistent semantics, excluding runtime inode/timestamp values."""
    selected = {name: value for name, value in snapshot.items() if name.startswith("extract/")}
    identities: dict[tuple[int, int], list[str]] = {}
    for name, value in selected.items():
        identities.setdefault((value["st_dev"], value["st_ino"]), []).append(name)
    groups = {name: sorted(group) for group in identities.values() for name in group}
    return {
        name: {
            **{
                key: value[key]
                for key in (
                    "object_type",
                    "st_nlink",
                    "mode",
                    "size",
                    "content_digest",
                    "link_target",
                )
            },
            "identity_paths": groups[name],
        }
        for name, value in selected.items()
    }


def analyze(root: Path) -> dict:
    config = load(root / "config.json")
    load(root / "completed.json")
    summary = {
        "classification": "REPRODUCIBLE_DIAGNOSTIC_ONLY",
        "config": config,
        "run_count": 0,
        "outcomes": {},
        "cases": {},
    }
    outcomes: Counter = Counter()
    for case in config["cases"]:
        name = case["name"]
        profiles = ("stock", "branches", "syscalls") + (() if case["options"] else ("native",))
        runs = []
        for repetition in range(config["repetitions"]):
            for profile in profiles:
                folder = root / f"{name}-{profile}-{repetition}"
                meta = load(folder / "run.json")
                archive_hash = hashlib.sha256((folder / "input.tar").read_bytes()).hexdigest()
                if archive_hash != meta["archive_sha256"]:
                    raise ValueError(f"archive digest mismatch: {folder.name}")
                before, after = load(folder / "before.json"), load(folder / "after.json")
                if before["outside/sentinel.txt"] != after["outside/sentinel.txt"]:
                    raise ValueError(f"sentinel changed: {folder.name}")
                if after["archive/input.tar"]["content_digest"] != archive_hash:
                    raise ValueError(f"input changed: {folder.name}")
                run = {
                    "id": folder.name,
                    "profile": profile,
                    "repetition": repetition,
                    "archive_sha256": archive_hash,
                    "returncode": meta["returncode"],
                    "semantic_after": semantic_state(after),
                }
                if profile == "branches":
                    probe = load(folder / "stdout.bin")
                    run["branches"] = probe["records"]
                    run["error"] = probe["error"]
                elif profile == "native":
                    reader = load(folder / "reader.json")
                    if not reader["integrity_valid"] or reader["completeness"] != "complete":
                        raise ValueError(f"invalid native trace: {folder.name}")
                    run["effects"] = reader["effects"]
                    run["effect_classes"] = dict(
                        Counter(event["effect_class"] for event in reader["effects"])
                    )
                elif profile == "syscalls":
                    trace = (folder / "stderr.bin").read_text()
                    if "+++ exited with" not in trace:
                        raise ValueError(f"missing syscall termination: {folder.name}")
                    run["syscall_extract_lines"] = [
                        line for line in trace.splitlines() if "/extract/" in line
                    ]
                outcomes[str(meta["returncode"])] += 1
                runs.append(run)
        if len({run["archive_sha256"] for run in runs}) != 1:
            raise ValueError(f"different archives within diagnostic case: {name}")
        signatures = {
            json.dumps((run["returncode"], run["semantic_after"]), sort_keys=True) for run in runs
        }
        if len(signatures) != 1:
            raise ValueError(f"persistent semantic mismatch across profiles/repetitions: {name}")
        summary["cases"][name] = {
            "options": case["options"],
            "setup": case["setup"],
            "run_count": len(runs),
            "outcome_and_semantics_match": True,
            "runs": runs,
        }
        summary["run_count"] += len(runs)
    summary["outcomes"] = dict(outcomes)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = analyze(args.evidence)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"run_count": result["run_count"], "outcomes": result["outcomes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
