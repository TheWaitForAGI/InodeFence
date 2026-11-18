"""Write or clear this host's sealed-run lock (#520 D3). Reserved ranges are not written here.

    python -m scripts.sealed_lineage_lock seal --run-id ID --target node-tar --version 7.4.4 \
        --source-doc PATH --source-sha SHA256
    python -m scripts.sealed_lineage_lock release --run-id ID

The lock path is ``inodefence.sealed_lineage.lock_path()``. Entries are merged; an existing id
with different content stops the command. The file holds version lists only, never results.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from inodefence.sealed_lineage import SCHEMA, LockError, load_lock, lock_path, parse_version


def _read(path: Path) -> dict:
    load_lock(path)  # validates; raises LockError on a malformed file
    if not path.exists():
        return {"schema": SCHEMA, "entries": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def seal(path: Path, run_id: str, target: str, versions: list[str], doc: str, sha: str) -> None:
    for v in versions:
        parse_version(v)
    data = _read(path)
    entry = {
        "id": run_id,
        "target": target,
        "versions": versions,
        "source": {"doc": doc, "sha256": sha},
    }
    for old in data["entries"]:
        if old["id"] == run_id:
            same = {k: old.get(k) for k in entry} == entry
            if same:
                return
            raise LockError(f"{path}: id {run_id} already sealed with different content")
    entry["since"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["entries"].append(entry)
    _write(path, data)


def release(path: Path, run_id: str) -> None:
    data = _read(path)
    kept = [e for e in data["entries"] if e["id"] != run_id]
    if len(kept) == len(data["entries"]):
        raise LockError(f"{path}: no sealed entry {run_id}")
    data["entries"] = kept
    _write(path, data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seal")
    s.add_argument("--run-id", required=True)
    s.add_argument("--target", required=True)
    s.add_argument("--version", action="append", required=True)
    s.add_argument("--source-doc", required=True)
    s.add_argument("--source-sha", required=True)
    r = sub.add_parser("release")
    r.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    path = lock_path()
    try:
        if args.cmd == "seal":
            seal(path, args.run_id, args.target, args.version, args.source_doc, args.source_sha)
        else:
            release(path, args.run_id)
    except (LockError, ValueError) as exc:
        print(f"sealed_lineage_lock: {exc}", file=sys.stderr)
        return 3
    print(f"{args.cmd} {args.run_id}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
