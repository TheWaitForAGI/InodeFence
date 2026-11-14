"""Exploratory node-tar image from the public npm registry (part of ``AUTO_PREPARE=1``).

For a node-tar version that has **no** committed lock in ``tools/node-tar/versions/`` (a committed
lock always wins; it is the reproducibility baseline, not an allowlist), this builds ``--image`` the
same way the committed versions are built, except that the lock is generated now:

1. ``npm view tar@<v> dist.integrity`` in a disposable container of the pinned Node image (the
   ``FROM`` digest of ``tools/node-tar/effect/Dockerfile``; nothing mounted): the version exists.
2. ``npm install --package-lock-only --ignore-scripts`` in another disposable container (nothing
   installed, no scripts run); the lock comes back on stdout and is never written into the
   repository.
3. The lock is checked on the host and **refused** unless: the root depends on exactly
   ``tar@<v>``; ``tar`` resolves to ``<v>``; every entry is ``resolved`` from
   ``https://registry.npmjs.org/``; every ``integrity`` equals what the registry publishes for that
   ``name@version`` in this run. It is **recorded, not refused**: packages that appear in no
   committed 7.5.x lock (name, version, integrity) and packages that declare install scripts
   (scripts are always disabled: ``--ignore-scripts`` here and ``npm ci --ignore-scripts`` in the
   build).
4. ``tools/node-tar/effect/Dockerfile`` (unchanged: pinned base digests, the committed worker
   files) is built from a temporary context outside the repository into ``<image>-unverified``.
5. With ``--network none`` the staged image must report ``tar`` ``<v>`` installed; the regression
   run's extraction program (``cross_release_identity.NODE_PROGRAM``) must extract a benign
   one-file archive with that ``tar``; and the exploration path's effect producer
   (``/target/effect-producer.cjs``, run exactly as the controller runs it, ``full`` profile) must
   be present, identify that ``tar`` and extract the same archive with a usable frame and no
   producer failures. Otherwise: "worker incompatible" with the reason, fail-closed.
6. Only then is ``<image>`` tagged; the staging tag and the temporary context are removed.

Every failure (unknown version, registry/network error, integrity mismatch, non-registry source,
build failure, wrong installed version, incompatible harness) exits non-zero with its reason and
leaves ``<image>`` absent: no run, verdict or result file, and a rerun starts over. An existing
``<image>`` is never rebuilt. This does **not** make a registry package safe; it only pins and
checks what was downloaded in this run. The extraction run itself is offline (``--network none``).
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
#: Registry-prepared images live only in this repository name, never a committed-recipe name.
REGISTRY_REPOSITORY = "inodefence-node-tar-registry"
LIMITS = (
    "The integrity check shows only that the generated lock matches what the registry published "
    "during this run; it cannot detect a registry that changed or was compromised. That is why "
    "these runs are exploratory: they are reproducible only from the saved lock file and its "
    "SHA-256, not from a committed recipe."
)
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


def check_inputs(version: str, image: str, versions_dir: Path = VERSIONS_DIR) -> None:
    """Before any docker or npm call: exact X.Y.Z, an unregistered version, a registry-only name."""
    if EXACT.fullmatch(version) is None:
        raise RegistryPrepareError(f"node-tar version must be exact X.Y.Z: {version!r}")
    if IMAGE_REF.fullmatch(image) is None or image.endswith(STAGING):
        raise RegistryPrepareError(f"not a plain image reference: {image!r}")
    if image.partition(":")[0] != REGISTRY_REPOSITORY:
        raise RegistryPrepareError(
            f"registry-prepared images are tagged only as {REGISTRY_REPOSITORY}:<tag>, "
            f"not {image!r}"
        )
    if (versions_dir / version / "package-lock.json").exists():
        raise RegistryPrepareError(
            f"node-tar {version} has a committed lock; it uses the verified recipe, never the "
            "registry path"
        )


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
        raise RegistryPrepareError(npm_failure(done.stderr or ""))
    return done.stdout or ""


_NETWORK_CODES = (
    "ENOTFOUND",
    "EAI_AGAIN",
    "ETIMEDOUT",
    "ECONNREFUSED",
    "ECONNRESET",
    "ENETUNREACH",
)


def npm_failure(stderr: str) -> str:
    """A precise reason from npm's error output: not found / registry unreachable / other."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    detail = next(
        (
            line
            for key in ("No match found", "not in this registry")
            for line in lines
            if key in line
        ),
        "",
    )
    if "E404" in stderr or "No match found" in stderr:
        return f"version not found on {REGISTRY}: {detail or lines[0] if lines else ''}".strip()
    if any(code in stderr for code in _NETWORK_CODES):
        code = next(c for c in _NETWORK_CODES if c in stderr)
        return f"registry unreachable ({code}); nothing was prepared"
    return f"npm step failed: {(lines[0] if lines else 'no output')[:200]}"


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


def check_lock(lock: dict[str, Any], version: str, published: dict[str, str]) -> None:
    """Fail unless the lock pins exactly ``tar@version`` and what the registry published."""
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
        if not str(entry.get("resolved", "")).startswith(REGISTRY):
            raise RegistryPrepareError(f"{spec} is not resolved from {REGISTRY}")
        if entry.get("integrity") != published.get(spec):
            raise RegistryPrepareError(f"{spec} integrity differs from the registry's")


def lock_findings(lock: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    """Recorded, not refused: packages new to the committed locks; packages with install scripts."""
    new, scripts = [], []
    for key, entry in lock.get("packages", {}).items():
        if not key:
            continue
        name = key.split("node_modules/")[-1]
        if name not in allowed:
            new.append(
                {
                    "name": name,
                    "version": str(entry.get("version")),
                    "integrity": str(entry.get("integrity")),
                }
            )
        if entry.get("hasInstallScript"):
            scripts.append(name)
    return {"new_dependencies": new, "install_scripts_disabled": sorted(scripts)}


def resolve_latest(runner: Runner = subprocess.run, node: str | None = None) -> str:
    """The registry's current ``latest`` dist-tag of ``tar`` as an exact version."""
    out = _npm(runner, node or node_image(), "npm view tar dist-tags.latest", {})
    version = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if EXACT.fullmatch(version) is None:
        raise RegistryPrepareError(f"registry latest for tar is not an exact version: {version!r}")
    return version


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


def harness_check(runner: Runner, image: str) -> None:
    """Offline: the run's own extraction program must extract a benign one-file archive."""
    from experiments.repro import cross_release_identity as cri

    tar = base64.b64encode(cri.build_tar([{"name": "ok.txt", "type": "reg", "content": b"ok\n"}]))
    ref = base64.b64encode(cri.REFERENCE_CONTENT).decode()
    done = _docker(
        runner,
        [
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "0:0",
            "-e",
            f"TAR_B64={tar.decode()}",
            "-e",
            f"REF_B64={ref}",
            "--entrypoint",
            "node",
            image,
            "-e",
            cri.NODE_PROGRAM,
        ],
        120,
    )
    try:
        raw = json.loads((done.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        raw = None
    ok = (
        done.returncode == 0
        and isinstance(raw, dict)
        and raw.get("declined") is None
        and "ok.txt" in (raw.get("extract_tree") or {})
    )
    if not ok:
        detail = (done.stderr or "").strip()[-200:] or str(raw)[:200]
        raise RegistryPrepareError(f"harness incompatible with the tar in {image}: {detail}")


#: Offline check that the exploration path's effect producer works with the installed tar: it
#: fingerprints the module (``--identify``), then runs the producer exactly as the controller does
#: (12 arguments, ``full`` profile) on a benign one-file archive and reports what happened.
PRODUCER = "/target/effect-producer.cjs"
_PRODUCER_PROGRAM = r"""
const cp = require('child_process'), fs = require('fs'), path = require('path')
const crypto = require('crypto')
const P = '/target/effect-producer.cjs', M = '/target/node_modules/tar'
const L = '/target/package-lock.json'
const out = {present: fs.existsSync(P)}
const done = () => { console.log(JSON.stringify(out)); process.exit(0) }
if (!out.present) done()
out.producer_sha256 = crypto.createHash('sha256').update(fs.readFileSync(P)).digest('hex')
const id = cp.spawnSync(process.execPath, [P, '--identify', M, L], {encoding: 'utf8'})
out.identify_status = id.status
out.identify_stderr = (id.stderr || '').slice(-300)
if (id.status !== 0) done()
const ident = JSON.parse(id.stdout)
out.identity_tar_version = ident.tar_version
const dir = fs.mkdtempSync('/tmp/producer-check-')
const archive = path.join(dir, 'input.tar'), dest = path.join(dir, 'extract')
fs.writeFileSync(archive, Buffer.from(process.env.TAR_B64, 'base64'))
fs.mkdirSync(dest)
const r = cp.spawnSync(process.execPath, [P, M, L, archive, dest, 'full', '256',
  ident.node_version, ident.tar_version, ident.producer_sha256, ident.package_lock_sha256,
  ident.package_entrypoint_sha256, ident.unpack_sha256], {encoding: 'utf8', maxBuffer: 8e6})
out.run_status = r.status
out.run_stderr = (r.stderr || '').slice(-300)
try {
  const frame = JSON.parse((r.stdout || '').trim().split('\n').pop())
  out.frame = {format: frame.format, outcome: frame.target.outcome,
    error: frame.target.error, records: frame.records.length,
    producer_failures: frame.terminal.producer_failures}
} catch (e) { out.frame_error = String(e).slice(0, 200) }
const extracted = path.join(dest, 'ok.txt')
out.extracted = fs.existsSync(extracted) && fs.readFileSync(extracted, 'utf8') === 'ok\n'
done()
"""


def producer_check(runner: Runner, image: str, version: str) -> dict[str, Any]:
    """Run the effect producer offline in ``image``; ``ok`` plus the reason it is (not) usable."""
    from experiments.repro import cross_release_identity as cri

    tar = base64.b64encode(cri.build_tar([{"name": "ok.txt", "type": "reg", "content": b"ok\n"}]))
    done = _docker(
        runner,
        [
            "run",
            "--rm",
            "--network",
            "none",
            "-e",
            f"TAR_B64={tar.decode()}",
            "--entrypoint",
            "/usr/local/bin/node",
            image,
            "-e",
            _PRODUCER_PROGRAM,
        ],
        180,
    )
    try:
        out = json.loads((done.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {
            "ok": False,
            "reason": f"producer check produced no report: {(done.stderr or '')[-200:]}",
        }
    frame = out.get("frame") or {}
    if not out.get("present"):
        reason = f"{PRODUCER} is missing from the image"
    elif out.get("identify_status") != 0:
        reason = f"producer --identify failed: {out.get('identify_stderr', '').strip()}"
    elif out.get("identity_tar_version") != version:
        reason = f"producer identifies tar {out.get('identity_tar_version')!r}, expected {version}"
    elif out.get("run_status") != 0 or frame.get("outcome") != "success":
        detail = out.get("run_stderr", "").strip() or frame.get("error") or out.get("frame_error")
        reason = f"producer run failed (exit {out.get('run_status')}): {detail}"
    elif frame.get("format") != "inodefence-node-tar-effect-stream" or not frame.get("records"):
        reason = f"producer frame unusable: {frame}"
    elif frame.get("producer_failures"):
        reason = f"producer reported failures: {frame.get('producer_failures')}"
    elif not out.get("extracted"):
        reason = "producer finished but the benign file was not extracted"
    else:
        reason = f"effect producer extracted a benign archive ({frame.get('records')} records)"
    return {
        "ok": reason.startswith("effect producer extracted"),
        "reason": reason,
        "producer_sha256": out.get("producer_sha256"),
    }


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
    check_lock(lock, version, published)
    lock_sha = hashlib.sha256(lock_bytes).hexdigest()
    log(f"REGISTRY-PREPARE lock ok sha256={lock_sha} packages={','.join(lock_specs(lock))}")
    findings = lock_findings(lock, allowed)
    for dep in findings["new_dependencies"]:
        log(
            "REGISTRY-PREPARE new dependency (recorded, not in committed locks): "
            f"{dep['name']}@{dep['version']} {dep['integrity']}"
        )
    for name in findings["install_scripts_disabled"]:
        log(f"REGISTRY-PREPARE {name} declares install scripts; they stay disabled")
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
        harness_check(runner, staging)
        producer = producer_check(runner, staging, version)
        if not producer["ok"]:
            raise RegistryPrepareError(
                f"worker incompatible (effect-producer): {producer['reason']}"
            )
        log(f"REGISTRY-PREPARE {producer['reason']}; producer sha256={producer['producer_sha256']}")
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
