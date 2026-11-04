"""Check that each validated summary's raw pointer is accounted for.

The evidence chain is ``raw -> validated summary -> finding -> claim``. Raw bytes
are never committed, so a summary that cites raw must cite something checkable: an
in-repo file, or a path under a host's ``~/inodefence-evidence/`` tree that a
committed manifest (``raw-manifest-*.sha256``) covers. This tool walks every
``experiments/summaries/*.json`` summary, extracts its raw/evidence pointers, and
classifies each:

    MANIFEST-COVERED   evidence-tree path whose top directory is in a manifest
    MANIFEST-ABSENT    evidence-tree path no committed manifest lists  (gap)
    REPO-PRESENT       in-repo path that exists
    REPO-MISSING       in-repo path that does not exist                (broken)
    RAW-GITIGNORED     experiments/raw/... (expected absent by policy)
    RAW-FILENAME       bare raw file name cited by basename (expected absent)
    UNRESOLVED         path-like pointer that could not be classified

Exit non-zero if any pointer is REPO-MISSING. With ``--strict`` a MANIFEST-ABSENT
or UNRESOLVED pointer also fails. ``--json`` prints the rows as JSON.

    python -m scripts.check_evidence_chain
    python -m scripts.check_evidence_chain --strict --json
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.make_raw_manifest import parse_manifest

#: Keys whose string descendants may hold a raw/evidence pointer.
POINTER_KEY = re.compile(r"raw|evidence|source|rollup|pointer", re.IGNORECASE)
EVIDENCE_MARK = "inodefence-evidence/"
#: In-repo top directories a pointer may legitimately name.
REPO_PREFIXES = ("experiments/", "paper/", "docs/", "scripts/", "src/", "tests/", "tools/")
_BRACE = re.compile(r"\{([^}]*)\}")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def looks_like_path(value: str) -> bool:
    """A string worth classifying as a pointer (vs. a digest or free prose)."""
    core = value.strip().split()[0] if value.strip() else ""
    if not core:
        return False
    return "/" in core or core.endswith((".json", ".sha256")) or "*" in core


def iter_pointer_values(obj: object, under_key: bool = False) -> Iterator[str]:
    """Yield path-like strings living under a pointer-ish key."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            hit = under_key or bool(POINTER_KEY.search(key))
            if isinstance(value, str):
                if hit and looks_like_path(value):
                    yield value
            else:
                yield from iter_pointer_values(value, hit)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_pointer_values(item, under_key)


def manifest_index(summaries_dir: Path) -> dict[str, set[str]]:
    """Map each committed manifest file name to its set of top-level entries."""
    index: dict[str, set[str]] = {}
    for manifest in sorted(summaries_dir.glob("raw-manifest-*.sha256")):
        entries = parse_manifest(manifest.read_text(encoding="utf-8"))
        index[manifest.name] = {name.split("/", 1)[0] for _, name in entries}
    return index


@dataclass(frozen=True, slots=True)
class ChainRow:
    summary: str
    pointer: str
    status: str
    detail: str


def _expand_braces(core: str) -> list[str]:
    """Expand a single ``{a,b}`` group (e.g. ``name.{md,json}``); else return [core]."""
    match = _BRACE.search(core)
    if match is None:
        return [core]
    pre, post = core[: match.start()], core[match.end() :]
    return [f"{pre}{option}{post}" for option in match[1].split(",")]


def classify_pointer(pointer: str, repo_root: Path, index: dict[str, set[str]]) -> ChainRow:
    core = pointer.strip().split()[0].rstrip("/),;")
    if EVIDENCE_MARK in core:
        name = core.split(EVIDENCE_MARK, 1)[1].split("/", 1)[0].split("*", 1)[0]
        for manifest_name, tops in index.items():
            if name and name in tops:
                return ChainRow("", pointer, "MANIFEST-COVERED", f"{name} in {manifest_name}")
        return ChainRow("", pointer, "MANIFEST-ABSENT", f"{name or core}: no manifest lists it")
    if core.startswith("experiments/raw/") or "/experiments/raw/" in core:
        return ChainRow("", pointer, "RAW-GITIGNORED", core)
    if core.startswith(REPO_PREFIXES):
        candidates = _expand_braces(core)
        missing = [name for name in candidates if not (repo_root / name).exists()]
        if missing:
            return ChainRow("", pointer, "REPO-MISSING", ", ".join(missing))
        return ChainRow("", pointer, "REPO-PRESENT", core)
    if "/" not in core and core.endswith((".json", ".jsonl")):
        return ChainRow("", pointer, "RAW-FILENAME", core)
    return ChainRow("", pointer, "UNRESOLVED", core)


def check_summaries(summaries_dir: Path, repo_root: Path) -> list[ChainRow]:
    index = manifest_index(summaries_dir)
    rows: list[ChainRow] = []
    for summary in sorted(summaries_dir.glob("*.json")):
        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        seen: set[str] = set()
        for pointer in iter_pointer_values(data):
            if pointer in seen:
                continue
            seen.add(pointer)
            row = classify_pointer(pointer, repo_root, index)
            rows.append(ChainRow(summary.name, row.pointer, row.status, row.detail))
    return rows


def _failed(rows: list[ChainRow], strict: bool) -> bool:
    bad = {"REPO-MISSING"}
    if strict:
        bad |= {"MANIFEST-ABSENT", "UNRESOLVED"}
    return any(row.status in bad for row in rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="also fail on absent/unresolved")
    parser.add_argument("--json", action="store_true", help="print rows as JSON")
    parser.add_argument("--summaries", type=Path, help="override experiments/summaries directory")
    args = parser.parse_args(argv)

    repo_root = repository_root()
    summaries_dir = args.summaries or repo_root / "experiments" / "summaries"
    rows = check_summaries(summaries_dir, repo_root)

    if args.json:
        print(json.dumps([asdict(row) for row in rows], indent=2, ensure_ascii=False))
    else:
        width = max((len(row.summary) for row in rows), default=0)
        for row in rows:
            print(f"{row.summary:<{width}}  {row.status:<16}  {row.pointer}  [{row.detail}]")
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        print("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    return 1 if _failed(rows, args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
