#!/usr/bin/env python3
"""Controlled cross-release filesystem-identity observation (student research).

Goal: for a fixed pair of pinned node-tar library releases, extract one
controlled archive fixture through each release inside a disposable Linux
container, and record the observed post-extraction filesystem-identity state of
an external reference file that sits beside the extraction directory.

For each (fixture, release) we record:
  - extraction outcome: resolved, or declined with the library's reason,
  - whether any extracted object shares the reference file's (st_dev, st_ino)
    identity -- this is exactly the observation our C1 oracle evaluates,
  - the reference file's hard-link count before and after.

Honesty / research invariants:
  - The fixtures are plain, generic archive entries (a hard-link entry whose
    link target is a relative path leaving the extraction directory). This is a
    hand-built controlled fixture, not an input discovered by the fuzzer.
  - No release identifier is used as a decision condition, and no "answer" path
    is baked into any verdict logic: the verdict is just "does an extracted
    object share the reference file's inode identity", applied uniformly.
  - Each release runs in its own disposable container (ephemeral Linux fs =
    clean inode semantics); the host is never the extraction target.

Output: one JSON file per fixture plus a combined summary, under --out.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import tarfile
from pathlib import Path

REFERENCE_CONTENT = b"external reference file for identity comparison\n"

# Generic hard-link fixtures. Same relative link target in both; they differ
# only in where the entry is placed (top-level vs inside one subdirectory).
FIXTURES: dict[str, list[dict]] = {
    "toplevel_hardlink": [
        {"name": "link", "type": "link", "linkname": "../ext/reference.bin"},
    ],
    "nested_hardlink": [
        {"name": "sub/", "type": "dir"},
        {"name": "sub/link", "type": "link", "linkname": "../ext/reference.bin"},
    ],
}

# Fixed release pair per fixture: (earlier release, later release).
PAIRS: dict[str, tuple[str, str]] = {
    "toplevel_hardlink": ("7.5.2", "7.5.3"),
    "nested_hardlink": ("7.5.6", "7.5.7"),
}

# Full release set, so the output also shows where the behaviour boundary sits.
ALL_RELEASES = ["7.5.2", "7.5.3", "7.5.6", "7.5.7", "7.5.8"]

IMAGE = "inodefence-node-tar-effect:{release}"

# Node program: set up a disposable layout, extract the fixture, then report the
# observed identity state of the external reference file as one JSON line.
NODE_PROGRAM = r"""
const tar = require("/target/node_modules/tar");
const fs = require("fs");
fs.mkdirSync("/work/extract", {recursive:true});
fs.mkdirSync("/work/ext", {recursive:true});
fs.mkdirSync("/work/archive", {recursive:true});
fs.writeFileSync("/work/ext/reference.bin", Buffer.from(process.env.REF_B64, "base64"));
fs.chmodSync("/work/ext/reference.bin", 0o600);
fs.writeFileSync("/work/archive/input.tar", Buffer.from(process.env.TAR_B64, "base64"));
function st(p){ try { const s = fs.lstatSync(p); let target=null;
  try{ if(s.isSymbolicLink()) target=fs.readlinkSync(p);}catch(e){}
  return {dev:String(s.dev), ino:String(s.ino), nlink:s.nlink,
    type:(s.isSymbolicLink()?"sym":s.isDirectory()?"dir":s.isFile()?"reg":"other"),
    size:s.size, target}; } catch(e){ return {error:e.code}; } }
function walk(dir, base){ let out={}; let ents=[];
  try{ents=fs.readdirSync(dir);}catch(e){return out;}
  for(const n of ents){ const full=dir+"/"+n; const rel=base?base+"/"+n:n;
    const s=st(full); out[rel]=s; if(s.type==="dir"){ Object.assign(out, walk(full, rel)); } }
  return out; }
const before = st("/work/ext/reference.bin");
let outcome=null;
tar.x({file:"/work/archive/input.tar", C:"/work/extract", strict:true, preservePaths:false})
  .then(()=>finish())
  .catch(e=>{outcome={code:e.code, message:String(e.message).slice(0,200)}; finish();});
function finish(){
  const after = st("/work/ext/reference.bin");
  const extract = walk("/work/extract", "");
  let shared=[];
  if(after && after.ino){ for(const k in extract){ const o=extract[k];
    if(o.dev===after.dev && o.ino===after.ino) shared.push("extract/"+k); } }
  console.log(JSON.stringify({
    declined: outcome,
    reference_before: before,
    reference_after: after,
    nlink_before: before.nlink,
    nlink_after: (after&&after.nlink),
    shared_identity: shared,
    extract_tree: extract,
  }));
}
"""


def build_tar(entries: list[dict]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as tf:
        for e in entries:
            ti = tarfile.TarInfo(e["name"])
            if e["type"] == "dir":
                ti.type = tarfile.DIRTYPE
                ti.mode = 0o755
                tf.addfile(ti)
            elif e["type"] == "reg":
                data = e.get("content", b"x")
                ti.type = tarfile.REGTYPE
                ti.size = len(data)
                ti.mode = 0o644
                tf.addfile(ti, io.BytesIO(data))
            elif e["type"] == "link":
                ti.type = tarfile.LNKTYPE
                ti.linkname = e["linkname"]
                ti.mode = 0o644
                tf.addfile(ti)
            else:
                raise ValueError(e["type"])
    return buf.getvalue()


def run_one(release: str, tar_b64: str) -> dict:
    cmd = [
        "docker",
        "run",
        "--rm",
        "--user",
        "0:0",
        "-e",
        f"TAR_B64={tar_b64}",
        "-e",
        f"REF_B64={base64.b64encode(REFERENCE_CONTENT).decode()}",
        "--entrypoint",
        "node",
        IMAGE.format(release=release),
        "-e",
        NODE_PROGRAM,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    for line in reversed(p.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except Exception:
            continue
    return {"_run_error": True, "_rc": p.returncode, "_stderr": p.stderr[-400:]}


def verdict(r: dict) -> dict:
    """Uniform C1 verdict: did an extracted object share the reference inode."""
    if r.get("_run_error"):
        return {"outcome": "run_error", "c1_identity_shared": None}
    if r.get("declined"):
        return {
            "outcome": "declined",
            "reason": r["declined"].get("message"),
            "c1_identity_shared": bool(r.get("shared_identity")),
        }
    return {
        "outcome": "resolved",
        "c1_identity_shared": bool(r.get("shared_identity")),
        "shared_objects": r.get("shared_identity"),
        "nlink_before": r.get("nlink_before"),
        "nlink_after": r.get("nlink_after"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    summary = {}
    for fixture, entries in FIXTURES.items():
        tar_b64 = base64.b64encode(build_tar(entries)).decode()
        per_release = {}
        for release in ALL_RELEASES:
            raw = run_one(release, tar_b64)
            per_release[release] = {"verdict": verdict(raw), "raw": raw}
        record = {
            "fixture": fixture,
            "entries": entries,
            "fixed_pair": PAIRS[fixture],
            "releases": per_release,
        }
        (out / f"{fixture}.json").write_text(json.dumps(record, indent=2, sort_keys=True))
        earlier, later = PAIRS[fixture]
        summary[fixture] = {
            "fixed_pair": [earlier, later],
            "earlier_shared": per_release[earlier]["verdict"]["c1_identity_shared"],
            "later_shared": per_release[later]["verdict"]["c1_identity_shared"],
            "boundary_ok": per_release[earlier]["verdict"]["c1_identity_shared"] is True
            and per_release[later]["verdict"]["c1_identity_shared"] is False,
            "per_release_shared": {
                r: per_release[r]["verdict"]["c1_identity_shared"] for r in ALL_RELEASES
            },
        }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
