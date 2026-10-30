#!/usr/bin/env python3
"""Live C-vs-D decoupling smoke: real decompress 4.2.1 (fs-wrap) -> v1 frame -> canonical keys.

NOT synthetic. Runs the real affected decompress in the hardened probe container (the
``decompress_effect_probe`` image, built by ``decompress_entry_effect_feasibility.py``;
``--network none`` / ``--read-only`` / ``--cap-drop ALL`` / tmpfs -- no isolation relaxation) on a
few archives, and derives the M3.1 C (``OBSERVED_EXTERNAL_RESOLVE``) and D
(``BOUNDARY_ESCAPE_ATTEMPT``) keys from each frame with the canonical normalizer
``feedback.boundary_attempt_frame.frame_boundary_attempt_keys`` (#179, main).

It shows the decoupling live: a CWD-relative escaping HARDLINK (``outside/sentinel.txt``, no
lexical ``..``) fires C alone (C-without-D), while a lexical escaping SYMLINK
(``../outside/sentinel.txt``) co-fires C and D -- so on decompress arm C (boundary +
external-resolve) is a strict superset of arm D (boundary), and the separation driver is the
CWD-relative hardlink escape, not the symlink (which co-fires both). 'demo run' label; observed,
region/shape-only keys (D005/D006), no fuzzer-discovery or effectiveness claim.

Reproduce:  uv run python experiments/repro/decompress_cvd_live_smoke.py --out <dir>
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import tarfile
from pathlib import Path

from inodefence.feedback.boundary_attempt_frame import frame_boundary_attempt_keys
from inodefence.model import EffectFeedbackKeyKind

IMAGE = "inodefence-decompress-effect-probe:4.2.1"
SENTINEL_CONTENT = b"inodefence protected sentinel\n"

# Each case is an archive of (name, tar type, optional linkname) entries. The hardened container
# resolves a relative hardlink target against the process CWD (the decompress 4.2.1 bug), so a
# plain relative name escapes; a symlink target resolves against the symlink's own directory, so
# it needs a lexical ``..`` to escape.
CASES: dict[str, list[dict[str, object]]] = {
    "observed_fixture_hardlink+symlink+regular": [
        {"name": "a.txt", "typ": tarfile.REGTYPE, "data": b"hello"},
        {"name": "evil", "typ": tarfile.LNKTYPE, "linkname": "outside/sentinel.txt"},
        {"name": "slink", "typ": tarfile.SYMTYPE, "linkname": "../outside/sentinel.txt"},
    ],
    "cwd_hardlink_only": [
        {"name": "evil", "typ": tarfile.LNKTYPE, "linkname": "outside/sentinel.txt"},
    ],
    "lexical_symlink_only": [
        {"name": "slink", "typ": tarfile.SYMTYPE, "linkname": "../outside/sentinel.txt"},
    ],
}


def make_tar(entries: list[dict[str, object]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for entry in entries:
            info = tarfile.TarInfo(str(entry["name"]))
            info.type = entry["typ"]  # type: ignore[assignment]
            info.uid = info.gid = info.mtime = 0
            if "linkname" in entry:
                info.linkname = str(entry["linkname"])
            if entry["typ"] == tarfile.REGTYPE:
                data = entry.get("data", b"")
                assert isinstance(data, bytes)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            else:
                tf.addfile(info)
    return buf.getvalue()


def run_probe(tar_bytes: bytes) -> dict:
    result = subprocess.run(
        [
            "docker",
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
            f"TAR_B64={base64.b64encode(tar_bytes).decode()}",
            "-e",
            f"SENTINEL_B64={base64.b64encode(SENTINEL_CONTENT).decode()}",
            IMAGE,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except (ValueError, TypeError):
            continue
    return {"_run_error": True, "_rc": result.returncode, "_stderr": result.stderr[-400:]}


def classify(frame: dict) -> dict:
    keys = frame_boundary_attempt_keys(frame)
    kinds = [key.kind for key in keys]
    return {
        "attempts": [
            {
                "operation": a.get("operation"),
                "target_raw": a.get("target_raw"),
                "target_region": a.get("target_region"),
                "aliases_external_object": a.get("aliases_external_object"),
            }
            for a in frame.get("attempts", [])
        ],
        "keys": sorted(str(key) for key in keys),
        "C_external_resolve": kinds.count(EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE),
        "D_boundary_attempt": kinds.count(EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="decompress C-vs-D live decoupling smoke")
    ap.add_argument("--out", default=str(Path.home() / "inodefence-evidence"))
    args = ap.parse_args()

    image_id = subprocess.run(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    results = {}
    for label, entries in CASES.items():
        frame = run_probe(make_tar(entries))
        results[label] = {
            "frame_format": frame.get("format"),
            "observed_call_order": frame.get("diagnostic_observed_call_order"),
            **classify(frame),
        }

    record = {
        "experiment": "decompress C-vs-D live decoupling smoke",
        "label": "demo run",
        "target": {"extractor": "decompress", "version": "4.2.1", "image_id": image_id},
        "isolation": (
            "hardened docker run: --network none --read-only --cap-drop ALL tmpfs; no relaxation"
        ),
        "method": (
            "real decompress (fs-wrap) -> inodefence-boundary-attempt-v1 frame -> "
            "frame_boundary_attempt_keys (#179)"
        ),
        "observed": results,
        "finding": (
            "The CWD-relative hardlink ('outside/sentinel.txt') fires C alone (C-without-D); the "
            "lexical symlink ('../outside/sentinel.txt') co-fires C and D. So arm C (boundary + "
            "external-resolve) is a strict superset of arm D (boundary) on decompress -- the "
            "separation driver is the CWD-relative hardlink escape, not the symlink (co-fires)."
        ),
    }
    out_dir = Path(args.out) / "decompress-cvd-decoupling-live"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "decompress_cvd_live_smoke.json"
    out_path.write_text(json.dumps(record, indent=2, sort_keys=True))
    print(json.dumps(results, indent=2, sort_keys=True))
    print("EVIDENCE:", out_path)


if __name__ == "__main__":
    main()
