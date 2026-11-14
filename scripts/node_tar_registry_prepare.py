"""Exploratory node-tar image from the public npm registry (``ALLOW_REGISTRY_PREPARE=1``).

For a node-tar version that has **no** committed lock in ``tools/node-tar/versions/``, this builds
``--image`` the same way the committed versions are built, except that the lock is generated now:

1. ``npm view tar@<v> version dist.integrity`` in a disposable container of the pinned Node image
   (the ``FROM`` digest of ``tools/node-tar/effect/Dockerfile``): the version must exist.
2. ``npm install --package-lock-only --ignore-scripts`` in another disposable container (no
   install scripts, nothing installed); the lock comes back on stdout and is never written into
   this repository.
3. The lock is checked on the host: root depends on exactly ``tar@<v>``; ``tar`` resolves to
   ``<v>``; every entry's ``resolved`` is on ``https://registry.npmjs.org/``; every ``integrity``
   equals the one the registry publishes (``npm view <name>@<version> dist.integrity``); no entry
   declares an install script; every package name already appears in a committed 7.5.x lock.
4. ``tools/node-tar/effect/Dockerfile`` (unchanged: pinned base digests, ``npm ci
   --ignore-scripts``, the committed worker files) is built from a temporary context outside the
   repository that holds only that lock, its ``package.json`` and the two worker files, into
   ``<image>-unverified``.
5. The staged image runs with ``--network none`` and must report ``tar`` ``<v>`` installed.
6. Only then is ``<image>`` tagged; the staging tag and the temporary context are removed.

Any failure (unknown version, registry/network error, integrity mismatch, unexpected package,
build failure, wrong installed version) exits non-zero and leaves ``<image>`` absent, so no run,
verdict or result file follows and a rerun starts over. An existing ``<image>`` is never rebuilt.
This does **not** make a registry package safe: it only pins and checks what was downloaded. The
extraction run itself stays offline in the usual isolated container.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "tools" / "node-tar" / "effect" / "Dockerfile"
VERSIONS_DIR = REPO_ROOT / "tools" / "node-tar" / "versions"
WORKER_FILES = (
    "src/inodefence/targets/_node_worker.cjs",
    "src/inodefence/targets/_node_effect_producer.cjs",
)
REGISTRY = "https://registry.npmjs.org/"
EXACT = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
IMAGE_REF = re.compile(r"[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
STAGING = "-unverified"
NPM_TIMEOUT = 300
BUILD_TIMEOUT = 1800
#: The verified path's package.json shape, with only the tar pin changing.
PACKAGE_NAME = "inodefence-node-benchmark"

Runner = Callable[..., subprocess.CompletedProcess[str]]


class RegistryPrepareError(RuntimeError):
    """A step failed; the requested image must not exist afterwards."""


def node_image(dockerfile: Path = DOCKERFILE) -> str:
    """The pinned Node build image (``FROM node:...@sha256:...``) of the existing Dockerfile."""
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        match = re.match(r"FROM\s+(node:\S+@sha256:[0-9a-f]{64})\s", line)
        if match:
            return match.group(1)
    raise RegistryPrepareError(f"no pinned node image in {dockerfile}")


def check_inputs(version: str, image: str) -> None:
    """Exact X.Y.Z and a plain image reference, before any docker or npm call."""
    if EXACT.fullmatch(version) is None:
        raise RegistryPrepareError(f"node-tar version must be exact X.Y.Z: {version!r}")
    if IMAGE_REF.fullmatch(image) is None or image.endswith(STAGING):
        raise RegistryPrepareError(f"not a plain image reference: {image!r}")


def package_json(version: str) -> str:
    data = {
        "name": PACKAGE_NAME,
        "version": "1.0.0",
        "private": True,
        "dependencies": {"tar": version},
    }
    return json.dumps(data, indent=2) + "\n"


def allowed_packages(versions_dir: Path = VERSIONS_DIR) -> set[str]:
    """Every package name in the committed 7.5.x locks (the expected dependency closure)."""
    names: set[str] = set()
    for lock in sorted(versions_dir.glob("7.5.*/package-lock.json")):
        for key in json.loads(lock.read_text(encoding="utf-8"))["packages"]:
            if key:
                names.add(key.split("node_modules/")[-1])
    if "tar" not in names:
        raise RegistryPrepareError("no committed 7.5.x lock to compare dependencies with")
    return names


def _npm(runner: Runner, node: str, script: str, env: dict[str, str]) -> str:
    """Run ``script`` in a disposable container of the pinned Node image (registry access)."""
    command = ["docker", "run", "--rm"]
    for key, value in env.items():
        command += ["-e", f"{key}={value}"]
    command += ["--entrypoint", "sh", node, "-c", script]
    try:
        done = runner(command, capture_output=True, text=True, timeout=NPM_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise RegistryPrepareError(f"npm container failed: {type(error).__name__}") from error
    if done.returncode != 0:
        raise RegistryPrepareError(f"npm step failed: {(done.stderr or '').strip()[-300:]}")
    return done.stdout or ""


def registry_integrity(runner: Runner, node: str, specs: list[str]) -> dict[str, str]:
    """``name@version`` -> the registry's published ``dist.integrity`` (all must exist)."""
    script = (
        'for s in $SPECS; do i=$(npm view "$s" dist.integrity) || exit 1; '
        'printf "%s %s\\n" "$s" "$i"; done'
    )
    out = _npm(runner, node, script, {"SPECS": " ".join(specs)})
    found: dict[str, str] = {}
    for line in out.splitlines():
        spec, _, integrity = line.strip().partition(" ")
        if spec and integrity.startswith("sha512-"):
            found[spec] = integrity
    missing = [s for s in specs if s not in found]
    if missing:
        raise RegistryPrepareError(f"registry has no integrity for {', '.join(missing)}")
    return found


def generate_lock(runner: Runner, node: str, version: str) -> bytes:
    pkg = base64.b64encode(package_json(version).encode()).decode()
    script = (
        'cd /tmp && echo "$PKG" | base64 -d > package.json && '
        "npm install --package-lock-only --ignore-scripts --no-audit --no-fund >/dev/null 2>&1 "
        "&& cat package-lock.json"
    )
    out = _npm(runner, node, script, {"PKG": pkg})
    if not out.strip():
        raise RegistryPrepareError("npm produced no lock")
    return out.encode()


def lock_specs(lock: dict[str, Any]) -> list[str]:
    return sorted(
        f"{key.split('node_modules/')[-1]}@{entry.get('version')}"
        for key, entry in lock.get("packages", {}).items()
        if key
    )


def check_lock(
    lock: dict[str, Any], version: str, published: dict[str, str], allowed: set[str]
) -> None:
    """Fail unless the lock pins exactly what the registry published, within the known closure."""
    packages = lock.get("packages")
    if not isinstance(packages, dict) or lock.get("lockfileVersion") != 3:
        raise RegistryPrepareError("unexpected lock format")
    if packages.get("", {}).get("dependencies") != {"tar": version}:
        raise RegistryPrepareError("lock root does not depend on exactly tar@" + version)
    if packages.get("node_modules/tar", {}).get("version") != version:
        raise RegistryPrepareError(f"lock resolves tar to {packages.get('node_modules/tar')}")
    for key, entry in packages.items():
        if not key:
            continue
        name = key.split("node_modules/")[-1]
        spec = f"{name}@{entry.get('version')}"
        if name not in allowed:
            raise RegistryPrepareError(f"unexpected package not in committed 7.5.x locks: {spec}")
        if not str(entry.get("resolved", "")).startswith(REGISTRY):
            raise RegistryPrepareError(f"{spec} is not resolved from {REGISTRY}")
        if entry.get("integrity") != published.get(spec):
            raise RegistryPrepareError(f"{spec} integrity differs from the registry's")
        if entry.get("hasInstallScript"):
            raise RegistryPrepareError(f"{spec} declares an install script")


def build_context(version: str, lock: bytes, root: Path) -> Path:
    """A temporary build context outside the repository with the Dockerfile's expected layout."""
    target = root / "tools" / "node-tar" / "versions" / version
    target.mkdir(parents=True)
    (target / "package.json").write_text(package_json(version), encoding="utf-8")
    (target / "package-lock.json").write_bytes(lock)
    for relative in WORKER_FILES:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, destination)
    return root


def _docker(runner: Runner, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RegistryPrepareError(f"docker {args[0]} failed: {type(error).__name__}") from error


def installed_version(runner: Runner, image: str) -> str:
    done = _docker(
        runner,
        [
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "/usr/local/bin/node",
            image,
            "-e",
            "console.log(require('/target/node_modules/tar/package.json').version)",
        ],
        120,
    )
    if done.returncode != 0:
        raise RegistryPrepareError(f"version check failed in {image}")
    return (done.stdout or "").strip().splitlines()[-1] if (done.stdout or "").strip() else ""


def exists(runner: Runner, image: str) -> bool:
    return _docker(runner, ["image", "inspect", image], 60).returncode == 0


def prepare(
    version: str,
    image: str,
    *,
    runner: Runner = subprocess.run,
    log: Callable[[str], None] = print,
) -> str:
    """Run steps 1-6; return the lock's SHA-256. Raises ``RegistryPrepareError`` on any failure."""
    check_inputs(version, image)
    if exists(runner, image):
        log(f"REGISTRY-PREPARE reuse {image} (already present; not rebuilt)")
        return ""
    node = node_image()
    allowed = allowed_packages()
    published = registry_integrity(runner, node, [f"tar@{version}"])
    log(f"REGISTRY-PREPARE tar@{version} exists; registry integrity {published[f'tar@{version}']}")
    lock_bytes = generate_lock(runner, node, version)
    try:
        lock = json.loads(lock_bytes)
    except ValueError as error:
        raise RegistryPrepareError("npm lock is not JSON") from error
    published.update(registry_integrity(runner, node, lock_specs(lock)))
    check_lock(lock, version, published, allowed)
    lock_sha = hashlib.sha256(lock_bytes).hexdigest()
    log(f"REGISTRY-PREPARE lock ok sha256={lock_sha} packages={','.join(lock_specs(lock))}")
    staging = f"{image}{STAGING}"
    with tempfile.TemporaryDirectory(prefix="inodefence-node-tar-registry-") as tmp:
        context = build_context(version, lock_bytes, Path(tmp))
        build = [
            "build",
            "-q",
            "-f",
            str(DOCKERFILE),
            "--build-arg",
            f"TAR_VERSION={version}",
            "-t",
            staging,
            str(context),
        ]
        done = _docker(runner, build, BUILD_TIMEOUT)
        if done.returncode != 0:
            raise RegistryPrepareError(f"build failed: {(done.stderr or '').strip()[-300:]}")
    try:
        seen = installed_version(runner, staging)
        if seen != version:
            raise RegistryPrepareError(f"{staging} has tar {seen!r} installed, expected {version}")
        if _docker(runner, ["tag", staging, image], 60).returncode != 0:
            raise RegistryPrepareError(f"tag {staging} -> {image} failed")
        log(f"REGISTRY-PREPARE verified tar {seen} offline; tagged {image}")
    finally:
        _docker(runner, ["rmi", "--no-prune", staging], 60)
    return lock_sha


_EVIDENCE_PROGRAM = (
    "const fs=require('fs'),c=require('crypto');"
    "const lock=fs.readFileSync('/target/package-lock.json');"
    "const worker=fs.readFileSync('/target/worker.cjs');"
    "console.log(JSON.stringify({tar:require('/target/node_modules/tar/package.json').version,"
    "lock:lock.toString('base64'),worker:c.createHash('sha256').update(worker).digest('hex')}))"
)


def image_evidence(image: str, runner: Runner = subprocess.run) -> dict[str, Any]:
    """Read, offline, the tar version, lock bytes and worker hash actually inside ``image``."""
    done = _docker(
        runner,
        [
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "/usr/local/bin/node",
            image,
            "-e",
            _EVIDENCE_PROGRAM,
        ],
        120,
    )
    if done.returncode != 0:
        raise RegistryPrepareError(f"cannot read evidence from {image}")
    data = json.loads((done.stdout or "").strip().splitlines()[-1])
    lock = base64.b64decode(data["lock"])
    return {
        "installed_version": str(data["tar"]),
        "lock": lock,
        "lock_sha256": hashlib.sha256(lock).hexdigest(),
        "worker_sha256": str(data["worker"]),
    }


RECIPE = (
    "tools/node-tar/effect/Dockerfile TAR_VERSION={version}; lock generated at run time from "
    + REGISTRY
    + " (npm install --package-lock-only --ignore-scripts, pinned node image)"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="exploratory node-tar image from the npm registry")
    parser.add_argument("--version", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args(argv)
    try:
        prepare(args.version, args.image)
    except RegistryPrepareError as error:
        print(f"REGISTRY-PREPARE FAIL: {error}; {args.image} not created", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
