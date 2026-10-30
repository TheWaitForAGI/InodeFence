#!/usr/bin/env python3
"""Controlled decompress hardlink identity observation (student research, M4.2).

Goal: for a fixed pair of pinned decompress releases, extract one controlled archive
fixture through each inside a disposable Linux container, and record the observed
post-extraction filesystem-identity state of an external sentinel file beside the
extraction directory. This is a THIRD independent extractor for the generality milestone
(after node-tar and oras-go): the observed relation ("does an extracted object share the
sentinel's (st_dev, st_ino)") is exactly the one the generic C1 oracle evaluates, unchanged.

The fixture is one hardlink entry ``evil`` whose link target ``outside/sentinel.txt`` contains
no ``..``. decompress (CVE-2026-39243) passes the raw linkname to ``fs.link`` without validation,
so a relative target is resolved against the process working directory. With the extractor
running from the disposable sandbox root (the natural extraction working dir), it aliases the
external sentinel. On the affected release this creates ``extract/evil`` sharing the sentinel
inode (reference nlink 1 -> 2); the fixed fork redirects the target inside the extraction root
and refuses the link.

Honesty / research invariants:
  - A hand-built controlled fixture, not an input discovered by the fuzzer; an oracle
    target-agnostic observation, not an effectiveness or discovery claim.
  - No release identifier is a decision condition and no "answer" path enters any verdict:
    the verdict is uniformly "does an extracted object share the sentinel's inode identity".
  - Each release runs in its own disposable, network-isolated, read-only container (writable
    /work and /tmp tmpfs only, --cap-drop ALL, non-root). The sandbox and sentinel are built
    INSIDE the ephemeral container; the host is never the extraction target. No
    isolation-relaxing flag is used.

Output: one JSON evidence file under --out. Requires Docker; builds the two pinned images from
tools/decompress/Dockerfile unless --skip-build is given.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL_CONTENT = b"inodefence protected sentinel\n"

# Role -> pinned image tag. affected = original decompress (unmaintained, CVE-2026-39243);
# fixed = the maintained @xhmikosr/decompress fork's patched release. The worker auto-detects
# which package the image installed and reports it.
ROLES: dict[str, str] = {"affected": "4.2.1", "fixed": "11.1.4"}
IMAGE = "inodefence-decompress:{tag}"

# One hardlink entry: target has no '..', yet decompress resolves it (via fs.link) against the
# sandbox-root CWD -> the external sentinel. decompress extracts into the output dir directly.
FIXTURE = [{"name": "evil", "type": "link", "linkname": "outside/sentinel.txt"}]


def build_tar(entries: list[dict]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for entry in entries:
            info = tarfile.TarInfo(entry["name"])
            info.uid = info.gid = info.mtime = 0
            if entry["type"] == "dir":
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tf.addfile(info)
            elif entry["type"] == "reg":
                data = entry.get("content", b"x")
                info.type = tarfile.REGTYPE
                info.size = len(data)
                info.mode = 0o644
                tf.addfile(info, io.BytesIO(data))
            elif entry["type"] == "link":
                info.type = tarfile.LNKTYPE
                info.linkname = entry["linkname"]
                info.mode = 0o644
                tf.addfile(info)
            else:
                raise ValueError(entry["type"])
    return buf.getvalue()


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=600, check=check
    )


def build_image(role: str, tag: str) -> str:
    _docker(
        "build",
        "-q",
        "-f",
        "tools/decompress/Dockerfile",
        "--build-arg",
        f"ROLE={role}",
        "-t",
        IMAGE.format(tag=tag),
        ".",
    )
    return image_id(tag)


def image_id(tag: str) -> str:
    return _docker("image", "inspect", IMAGE.format(tag=tag), "--format", "{{.Id}}").stdout.strip()


def run_probe(tag: str, tar_b64: str, sentinel_b64: str) -> dict:
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
        IMAGE.format(tag=tag),
        "probe",
        check=False,
    )
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except Exception:
            continue
    return {"_run_error": True, "_rc": result.returncode, "_stderr": result.stderr[-400:]}


def verdict(raw: dict) -> dict:
    """Uniform C1 verdict: did an extracted object share the sentinel inode."""
    if raw.get("_run_error"):
        return {"outcome": "run_error", "c1_identity_shared": None}
    if raw.get("declined"):
        return {
            "outcome": "declined",
            "reason": raw["declined"].get("message"),
            "c1_identity_shared": bool(raw.get("shared_identity")),
        }
    return {
        "outcome": "resolved",
        "c1_identity_shared": bool(raw.get("shared_identity")),
        "shared_objects": raw.get("shared_identity"),
        "nlink_before": raw.get("nlink_before"),
        "nlink_after": raw.get("nlink_after"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-build", action="store_true", help="reuse already-built images")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tar_b64 = base64.b64encode(build_tar(FIXTURE)).decode()
    sentinel_b64 = base64.b64encode(SENTINEL_CONTENT).decode()

    per_role = {}
    for role, tag in ROLES.items():
        img = image_id(tag) if args.skip_build else build_image(role, tag)
        raw = run_probe(tag, tar_b64, sentinel_b64)
        per_role[role] = {
            "decompress_module": raw.get("decompress_module"),
            "decompress_version": tag,
            "image_id": img,
            "verdict": verdict(raw),
            "raw": raw,
        }

    affected_shared = per_role["affected"]["verdict"]["c1_identity_shared"]
    fixed_shared = per_role["fixed"]["verdict"]["c1_identity_shared"]
    record = {
        "fixture": "decompress_hardlink",
        "cve": "CVE-2026-39243",
        "roles": dict(ROLES),
        "entries": FIXTURE,
        "affected_shared": affected_shared,
        "fixed_shared": fixed_shared,
        "boundary_ok": affected_shared is True and fixed_shared is False,
        "per_role": per_role,
    }
    (out / "decompress_hardlink.json").write_text(json.dumps(record, indent=2, sort_keys=True))
    print(json.dumps({k: record[k] for k in ("affected_shared", "fixed_shared", "boundary_ok")}))


if __name__ == "__main__":
    main()
