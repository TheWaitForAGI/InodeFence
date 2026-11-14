"""Python tarfile counterpart of ``cross_release_identity.run_one``: one fixture, one container.

Runs Python's stdlib ``tarfile`` inside a disposable ``python:<runtime>-slim`` container with the
same layout and the same post-extraction observation as the node-tar repro program: an external
``ext/reference.bin`` beside ``extract/``, then one JSON line reporting the reference's state
before/after and which extracted objects share its inode (lstat ``dev``/``ino``). The JSON keys
match the node program, so ``scripts.regression_check.c1_from_raw`` / ``c2_from_raw`` and
``cross_release_identity.verdict`` read it unchanged. The host is never the extraction target.

Python tarfile has two independent configuration axes, and callers vary only one at a time:

- ``extraction_filter`` (``fully_trusted`` / ``data``): a setting of the same library on the same
  interpreter. Comparing the two is a configuration comparison, not a release comparison.
- ``runtime_version`` (exact ``X.Y.Z``): the interpreter, and therefore the ``tarfile`` module,
  that runs. It selects the image ``python:<runtime_version>-slim``. The program reports the
  interpreter version it actually ran; a mismatch is a run error, never a result.

No release id or CVE id is a decision condition here; both axes are plain inputs.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
from collections.abc import Callable
from typing import Any

from experiments.repro.cross_release_identity import REFERENCE_CONTENT

IMAGE = "python:{runtime}-slim"
FILTERS = ("fully_trusted", "data")
RUNTIME_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
TIMEOUT_SECONDS = 90

# Python program run inside the container. WORK defaults to /work; tests point it at a tmp dir.
PY_PROGRAM = r"""
import base64, json, os, platform, sys, tarfile
work = os.environ.get("WORK", "/work")
flt = os.environ["EXTRACTION_FILTER"]
for d in ("extract", "ext", "archive"):
    os.makedirs(os.path.join(work, d), exist_ok=True)
ref = os.path.join(work, "ext", "reference.bin")
with open(ref, "wb") as f:
    f.write(base64.b64decode(os.environ["REF_B64"]))
os.chmod(ref, 0o600)
archive = os.path.join(work, "archive", "input.tar")
with open(archive, "wb") as f:
    f.write(base64.b64decode(os.environ["TAR_B64"]))

def st(p):
    try:
        s = os.lstat(p)
    except OSError as e:
        import errno
        return {"error": errno.errorcode.get(e.errno, str(e.errno))}
    import stat
    m = s.st_mode
    kind = ("sym" if stat.S_ISLNK(m) else "dir" if stat.S_ISDIR(m)
            else "reg" if stat.S_ISREG(m) else "other")
    target = os.readlink(p) if kind == "sym" else None
    return {"dev": str(s.st_dev), "ino": str(s.st_ino), "nlink": s.st_nlink,
            "type": kind, "size": s.st_size, "target": target}

def walk(d, base):
    out = {}
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        full = os.path.join(d, n)
        rel = base + "/" + n if base else n
        s = st(full)
        out[rel] = s
        if s.get("type") == "dir":
            out.update(walk(full, rel))
    return out

runtime = platform.python_version()
if not hasattr(tarfile, "data_filter"):
    print(json.dumps({"runtime": runtime, "filter_unsupported": True}))
    sys.exit(0)
before = st(ref)
outcome = None
try:
    with tarfile.open(archive, mode="r:") as tar:
        tar.errorlevel = 2
        tar.extractall(os.path.join(work, "extract"), filter=flt)
except Exception as e:
    outcome = {"code": type(e).__name__, "message": str(e)[:200]}
after = st(ref)
extract = walk(os.path.join(work, "extract"), "")
shared = []
if after.get("ino"):
    for k, o in extract.items():
        if o.get("dev") == after["dev"] and o.get("ino") == after["ino"]:
            shared.append("extract/" + k)
print(json.dumps({
    "runtime": runtime,
    "extraction_filter": flt,
    "declined": outcome,
    "reference_before": before,
    "reference_after": after,
    "nlink_before": before.get("nlink"),
    "nlink_after": after.get("nlink"),
    "shared_identity": shared,
    "extract_tree": extract,
}))
"""

Runner = Callable[..., subprocess.CompletedProcess[str]]


def image_ref(runtime_version: str) -> str:
    return IMAGE.format(runtime=runtime_version)


def docker_command(runtime_version: str, extraction_filter: str, tar_b64: str) -> list[str]:
    """The disposable-container command: no network, removed on exit, nothing mounted."""
    if RUNTIME_RE.fullmatch(runtime_version) is None:
        raise ValueError(f"runtime_version must be exact X.Y.Z, got {runtime_version!r}")
    if extraction_filter not in FILTERS:
        raise ValueError(f"extraction_filter must be one of {FILTERS}, got {extraction_filter!r}")
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "0:0",
        "-e",
        f"TAR_B64={tar_b64}",
        "-e",
        f"REF_B64={base64.b64encode(REFERENCE_CONTENT).decode()}",
        "-e",
        f"EXTRACTION_FILTER={extraction_filter}",
        "--entrypoint",
        "python",
        image_ref(runtime_version),
        "-c",
        PY_PROGRAM,
    ]


def parse_output(stdout: str, runtime_version: str) -> dict[str, Any] | None:
    """Last JSON line of the program, or None. A different interpreter version is rejected."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        if raw.get("runtime") != runtime_version:
            return {
                "_run_error": True,
                "_reason": f"runtime mismatch: ran {raw.get('runtime')!r}",
                "observed": raw,
            }
        if raw.get("filter_unsupported"):
            return {"_run_error": True, "_reason": "extraction filter unsupported", "observed": raw}
        return raw
    return None


def run_one(
    runtime_version: str,
    extraction_filter: str,
    tar_b64: str,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Extract one TAR in a fresh container; a failed or unverifiable run is ``_run_error``."""
    cmd = docker_command(runtime_version, extraction_filter, tar_b64)
    try:
        done = runner(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        return {"_run_error": True, "_reason": f"{type(error).__name__}: {error}"[:400]}
    raw = parse_output(done.stdout or "", runtime_version)
    if raw is None:
        return {"_run_error": True, "_rc": done.returncode, "_stderr": (done.stderr or "")[-400:]}
    return raw
