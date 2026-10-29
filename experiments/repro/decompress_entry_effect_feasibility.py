#!/usr/bin/env python3
"""Feasibility probe: can a per-entry entry-completion observation boundary be exposed for the
generality extractors, to feed a transition / boundary-attempt gradient signal (North Star:
releasing the final-state all-or-nothing adaptive-search ceiling)?

This is an OBSERVED feasibility finding, not a production observer. It runs the real affected
decompress (4.2.1) in a disposable container with its callback ``fs`` wrapped (the same
interposition the node-tar effect producer uses; see ``experiments/repro/decompress_effect_probe/
fswrap_probe.cjs``) and records, per extraction operation: the operation, source/destination,
call vs completion order, and whether the operation points an extract/ object at a target outside
the extraction root (a boundary attempt) or aliases the external sentinel inode.

Findings (see the recorded evidence JSON):

  1. The full per-entry entry-completion boundary -- an ORDERED, entry-identity-correlated
     operation stream (the production v2 ``EffectEventTrace`` contract in
     ``targets/node_tar_effect.py``) -- is NOT cleanly exposable:
       * decompress parses the whole archive, then writes entries CONCURRENTLY and REORDERED
         (observed: call order differs from archive order), and passes NO entry context to the
         fs operations (there is no AsyncLocalStorage-style hook into decompress's write loop
         without modifying decompress -- which would break real-extractor fidelity). So an
         ordered per-entry completion sequence with faithful entry correlation cannot be built.
         This is the same class of obstacle that left node-tar's native completion boundary
         ``V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`` (out-of-order completion, inode reuse).
       * oras-go is Go: ``file.Store.Push`` is an opaque call and Go's ``os`` package cannot be
         monkeypatched, so per-operation observation would need syscall tracing, not a library
         hook. (Inferred for oras-go; only decompress is run here.)

  2. A LIGHTER, SET-BASED boundary-attempt signal IS observable for decompress via fs-wrapping:
     each link/symlink operation's resolved target and the resulting inode are recoverable, so
     "an extraction operation created/pointed an extract/ object outside the extraction root"
     (the relation the C1 oracle and the M3.1 boundary-attempt gradient already use) is a
     derivable per-operation key. This signal is a SET (unordered), which is exactly what a
     boundary-attempt / transition gradient consumes -- it does not need the ordered,
     entry-correlated checkpoint that is infeasible above.

Interface proposal (to align with the Observation lane before any adapter integration): emit,
per observed operation, ``{operation, entry_dest, target_region, aliases_external}`` and map it
to the existing M3.1 ``BoundaryAttemptSignature`` (entry_type, target_region, outcome,
escape_shape). Integration into the decompress adapter is deferred until the M3.1 boundary-attempt
interface is merged and the format is agreed, so this file only demonstrates observability.

Honesty: observed = what this probe recorded running real decompress; inferred = the oras-go
reasoning (not run here). This is a feasibility demonstrator, not a qualified observer, and makes
no fuzzer-discovery or effectiveness claim. Hardened isolation, no isolation-relaxing flag.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import tarfile
from pathlib import Path

PROBE_DIR = Path(__file__).resolve().parent / "decompress_effect_probe"
SENTINEL_CONTENT = b"inodefence protected sentinel\n"
IMAGE = "inodefence-decompress-effect-probe:4.2.1"


def build_tar() -> bytes:
    """A 3-entry fixture: a benign regular file, a hardlink escaping to the sentinel, and a
    symlink whose target escapes the extraction root. Archive order: a.txt, evil, slink."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        reg = tarfile.TarInfo("a.txt")
        reg.type, reg.size, data = tarfile.REGTYPE, 5, b"hello"
        reg.uid = reg.gid = reg.mtime = 0
        tf.addfile(reg, io.BytesIO(data))
        hard = tarfile.TarInfo("evil")
        hard.type, hard.linkname = tarfile.LNKTYPE, "outside/sentinel.txt"
        hard.uid = hard.gid = hard.mtime = 0
        tf.addfile(hard)
        sym = tarfile.TarInfo("slink")
        sym.type, sym.linkname = tarfile.SYMTYPE, "../outside/sentinel.txt"
        sym.uid = sym.gid = sym.mtime = 0
        tf.addfile(sym)
    return buf.getvalue()


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=600, check=check
    )


def build_image() -> str:
    _docker("build", "-q", "-f", str(PROBE_DIR / "Dockerfile"), "-t", IMAGE, str(PROBE_DIR))
    return _docker("image", "inspect", IMAGE, "--format", "{{.Id}}").stdout.strip()


def run_probe(tar_b64: str, sentinel_b64: str) -> dict:
    result = _docker(
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
        "-e",
        f"TAR_B64={tar_b64}",
        "-e",
        f"SENTINEL_B64={sentinel_b64}",
        IMAGE,
        check=False,
    )
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except Exception:
            continue
    return {"_run_error": True, "_rc": result.returncode, "_stderr": result.stderr[-400:]}


def main() -> None:
    ap = argparse.ArgumentParser(description="decompress entry-effect feasibility probe")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    image_id = build_image()
    raw = run_probe(
        base64.b64encode(build_tar()).decode(),
        base64.b64encode(SENTINEL_CONTENT).decode(),
    )
    records = raw.get("records", [])

    call_order_ops = [r["op"] for r in sorted(records, key=lambda r: r["call_order"])]
    boundary_attempts = [
        {
            "op": r["op"],
            "dest": r["dest"],
            "target_region": r.get("target_region"),
            "aliases_external_sentinel": r.get("aliases_external_sentinel"),
        }
        for r in records
        if r.get("boundary_attempt")
    ]
    record = {
        "fixture": "decompress_entry_effect_feasibility",
        "extractor": "decompress@4.2.1",
        "image_id": image_id,
        "raw_error": raw.get("error"),
        "records": records,
        "assessment": {
            # OBSERVED (decompress run):
            "per_operation_effect_observable": len(records) > 0,
            "call_order_ops": call_order_ops,
            # archive order is a.txt (writeFile), evil (link), slink (symlink):
            "preserves_archive_order": call_order_ops == ["writeFile", "link", "symlink"],
            "entry_context_propagated": any(r.get("entry_context") is not None for r in records),
            "boundary_attempts_observed": boundary_attempts,
            # CONCLUSION (observed for decompress; oras-go inferred -- see module docstring):
            "ordered_entry_completion_boundary_feasible": False,
            "set_based_boundary_attempt_signal_feasible": len(boundary_attempts) > 0,
        },
    }
    (out / "decompress_entry_effect_feasibility.json").write_text(
        json.dumps(record, indent=2, sort_keys=True)
    )
    print(json.dumps(record["assessment"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
