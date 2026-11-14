"""Exploratory decompress image from the public npm registry (part of ``AUTO_PREPARE=1``).

The target is identified by package **and** version: the original ``decompress`` (unmaintained;
4.2.1 is its last release) and the maintained fork ``@xhmikosr/decompress`` are different packages
and are never mixed. Only these two package names are accepted (target identity, not a version
allowlist). A spec pinned by a committed recipe (``tools/decompress/<role>/package.json``) always
uses that verified recipe; any other exact version of either package is built here:

1. ``npm view <package>@<v> dist.integrity`` and ``npm install --package-lock-only
   --ignore-scripts`` in disposable containers of the pinned Node image of
   ``tools/decompress/Dockerfile`` (nothing mounted; the lock comes back on stdout).
2. The lock is refused unless the root depends on exactly ``<package>@<v>``, the package resolves
   to ``<v>``, every entry is resolved from the official registry and every integrity equals the
   registry's. Packages absent from the committed decompress locks and packages declaring install
   scripts are recorded, not refused (scripts stay disabled: ``npm ci --ignore-scripts``).
3. ``tools/decompress/Dockerfile`` (unchanged) is built from a temporary context outside the
   repository (``tools/decompress/registry/`` with that lock + the committed ``worker/worker.cjs``)
   into ``<image>-unverified``.
4. Offline (``--network none``, read-only rootfs, tmpfs, all capabilities dropped, ``--pull never``)
   the staged image must: report that package name and version installed; extract a benign archive
   (a file and an internal hard link to it) with the regression run's program; and, through the
   exploration path's worker (``worker.cjs identify`` / ``frame``), identify that package and
   version and emit a usable boundary-attempt frame that observed the hard link. Otherwise
   "harness incompatible" / "worker incompatible (decompress worker)" with the reason.
5. Only then is ``<image>`` tagged; the staging tag and the temporary context are removed.

Any failure leaves ``<image>`` absent. This does not make a registry package safe; see ``LIMITS``.
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

from scripts import npm_registry as npm
from scripts.npm_registry import EXACT, REGISTRY, RegistryPrepareError, Runner

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools" / "decompress"
DOCKERFILE = TOOLS_DIR / "Dockerfile"
WORKER = "tools/decompress/worker/worker.cjs"
#: The two packages that are this target; anything else is a different target and is refused.
PACKAGES = ("decompress", "@xhmikosr/decompress")
#: Registry-prepared images live only in this repository name, never a committed-recipe name.
REGISTRY_REPOSITORY = "inodefence-decompress-registry"
#: The temporary build context's role directory (the Dockerfile copies tools/decompress/${ROLE}/).
ROLE = "registry"
LATEST = "latest"
SPEC = re.compile(r"(?P<package>(?:@[a-z0-9][a-z0-9._-]*/)?decompress)@(?P<version>[^@\s]+)")
#: The same isolation the regression run uses (``run_decompress_target.docker_command``).
OFFLINE = [
    "--pull",
    "never",
    "--network",
    "none",
    "--read-only",
    "--tmpfs",
    "/work:rw,size=16m,mode=1777",
    "--tmpfs",
    "/tmp:rw,size=16m,mode=1777",
    "--cap-drop",
    "ALL",
]


def split_spec(spec: str) -> tuple[str, str]:
    """``<package>@<X.Y.Z|latest>`` -> (package, version); only the two target packages."""
    match = SPEC.fullmatch(spec)
    if match is None or match["package"] not in PACKAGES:
        raise RegistryPrepareError(
            f"decompress spec must be <package>@<X.Y.Z|latest> with package one of "
            f"{', '.join(PACKAGES)}: {spec!r}"
        )
    version = match["version"]
    if version != LATEST and EXACT.fullmatch(version) is None:
        raise RegistryPrepareError(f"decompress version must be exact X.Y.Z or latest: {spec!r}")
    return match["package"], version


def committed_specs(tools_dir: Path = TOOLS_DIR) -> set[str]:
    from scripts.decompress_image import pinned_specs

    return set(pinned_specs(tools_dir))


def check_inputs(package: str, version: str, image: str, tools_dir: Path = TOOLS_DIR) -> None:
    """Before any docker or npm call: a target package, exact version, registry-only image name."""
    split_spec(f"{package}@{version}")
    if EXACT.fullmatch(version) is None:
        raise RegistryPrepareError(f"decompress version must be exact X.Y.Z: {version!r}")
    npm.check_image_ref(image, REGISTRY_REPOSITORY)
    if f"{package}@{version}" in committed_specs(tools_dir):
        raise RegistryPrepareError(
            f"{package}@{version} has a committed recipe; it uses the verified recipe, never the "
            "registry path"
        )


def package_json(package: str, version: str) -> str:
    data = {
        "name": "inodefence-decompress-registry",
        "version": "0.0.0",
        "private": True,
        "dependencies": {package: version},
    }
    return json.dumps(data, indent=2) + "\n"


def allowed_packages(tools_dir: Path = TOOLS_DIR) -> set[str]:
    """Every package name in the committed decompress locks (recorded comparison only)."""
    return npm.committed_lock_names(sorted(tools_dir.glob("*/package-lock.json")))


def resolve_latest(package: str, runner: Runner = subprocess.run) -> str:
    split_spec(f"{package}@{LATEST}")
    return npm.resolve_dist_tag(runner, npm.node_image(DOCKERFILE), package)


def build_context(package: str, version: str, lock: bytes, root: Path) -> Path:
    """A temporary build context outside the repository with the Dockerfile's expected layout."""
    role = root / "tools" / "decompress" / ROLE
    role.mkdir(parents=True)
    (role / "package.json").write_text(package_json(package, version), encoding="utf-8")
    (role / "package-lock.json").write_bytes(lock)
    worker = root / WORKER
    worker.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / WORKER, worker)
    return root


def _benign_tar_b64() -> str:
    from experiments.repro import cross_release_identity as cri

    entries = [
        {"name": "a.txt", "type": "reg", "content": b"ok\n"},
        {"name": "b.txt", "type": "link", "linkname": "a.txt"},
    ]
    return base64.b64encode(cri.build_tar(entries)).decode()


def _run_offline(runner: Runner, image: str, program: str, env: dict[str, str]) -> Any:
    args = ["run", "--rm", *OFFLINE]
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    args += ["--entrypoint", "/usr/local/bin/node", image, "-e", program]
    done = npm.docker(runner, args, 180)
    try:
        return done, json.loads((done.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return done, None


#: Same program as the committed recipe's offline check (``decompress_image.recipe``).
_INSTALLED_PROGRAM = (
    "const p=require('/target/package.json');const n=Object.keys(p.dependencies)[0];"
    "console.log(n, require('/target/node_modules/'+n+'/package.json').version)"
)


def installed(runner: Runner, image: str) -> tuple[str, str]:
    program = _INSTALLED_PROGRAM
    done = npm.docker(
        runner,
        ["run", "--rm", *OFFLINE, "--entrypoint", "/usr/local/bin/node", image, "-e", program],
        120,
    )
    out = (done.stdout or "").strip().splitlines()
    if done.returncode != 0 or not out:
        raise RegistryPrepareError(f"version check failed in {image}")
    name, _, version = out[-1].partition(" ")
    return name, version


def harness_check(runner: Runner, image: str, package: str, version: str) -> None:
    """The regression run's own program must extract the benign archive with this package."""
    from scripts.run_decompress_target import JS_PROGRAM, REFERENCE_CONTENT

    ref = base64.b64encode(REFERENCE_CONTENT).decode()
    done, raw = _run_offline(
        runner, image, JS_PROGRAM, {"TAR_B64": _benign_tar_b64(), "REF_B64": ref}
    )
    tree = (raw or {}).get("extract_tree") or {}
    ok = (
        done.returncode == 0
        and isinstance(raw, dict)
        and (raw.get("package"), raw.get("package_version")) == (package, version)
        and raw.get("declined") is None
        and "a.txt" in tree
        and "b.txt" in tree
    )
    if not ok:
        detail = (done.stderr or "").strip()[-200:] or str(raw)[:200]
        raise RegistryPrepareError(f"harness incompatible with {package}@{version}: {detail}")


#: The exploration path runs ``worker.cjs frame <archive> <dest>`` (``DecompressFrameTarget``) after
#: binding through ``worker.cjs identify``; this runs both offline on the benign archive.
_WORKER_PROGRAM = r"""
const cp = require('child_process'), fs = require('fs'), path = require('path')
const crypto = require('crypto')
const W = '/target/worker.cjs', out = {present: fs.existsSync(W)}
const done = () => { console.log(JSON.stringify(out)); process.exit(0) }
if (!out.present) done()
out.worker_sha256 = crypto.createHash('sha256').update(fs.readFileSync(W)).digest('hex')
const id = cp.spawnSync(process.execPath, [W, 'identify'], {encoding: 'utf8'})
out.identify_status = id.status
out.identify_stderr = (id.stderr || '').slice(-300)
try { out.identity = JSON.parse(id.stdout) } catch (e) { done() }
const root = fs.mkdtempSync('/work/worker-check-'), arc = path.join(root, 'archive')
fs.mkdirSync(arc)
const tar = path.join(arc, 'input.tar'), dest = path.join(root, 'extract')
fs.writeFileSync(tar, Buffer.from(process.env.TAR_B64, 'base64'))
fs.mkdirSync(dest)
const r = cp.spawnSync(process.execPath, [W, 'frame', tar, dest], {encoding: 'utf8', cwd: root})
out.frame_status = r.status
out.frame_stderr = (r.stderr || '').slice(-300)
try {
  const f = JSON.parse((r.stdout || '').trim().split('\n').pop())
  out.frame = {schema_version: f.schema_version,
    attempts: Array.isArray(f.attempts) ? f.attempts.length : null,
    hardlinks: Array.isArray(f.attempts)
      ? f.attempts.filter(a => a.operation === 'hardlink').length : 0}
} catch (e) { out.frame_error = String(e).slice(0, 200) }
out.extracted = fs.existsSync(path.join(dest, 'a.txt'))
out.link_created = fs.existsSync(path.join(dest, 'b.txt'))
done()
"""


def worker_check(runner: Runner, image: str, package: str, version: str) -> dict[str, Any]:
    """The exploration path's worker on the staged image: ``ok`` plus the reason."""
    done, out = _run_offline(runner, image, _WORKER_PROGRAM, {"TAR_B64": _benign_tar_b64()})
    if not isinstance(out, dict):
        return {
            "ok": False,
            "reason": f"worker check produced no report: {(done.stderr or '')[-200:]}",
        }
    identity, frame = out.get("identity") or {}, out.get("frame") or {}
    seen = (identity.get("decompress_module"), identity.get("decompress_version"))
    if not out.get("present"):
        reason = "/target/worker.cjs is missing from the image"
    elif out.get("identify_status") != 0:
        reason = f"worker identify failed: {out.get('identify_stderr', '').strip()}"
    elif seen != (package, version):
        reason = f"worker identifies {seen[0]}@{seen[1]}, expected {package}@{version}"
    elif out.get("frame_status") not in (0, 2):
        # 0 = extracted, 2 = the package refused/failed (still an observed attempt); only a
        # harness/IO failure (3) or a crash means the worker cannot drive this package.
        stderr = out.get("frame_stderr", "").strip()
        reason = f"worker frame failed (exit {out.get('frame_status')}): {stderr}"
    elif frame.get("schema_version") != 1 or frame.get("attempts") is None:
        reason = f"worker frame unusable: {frame or out.get('frame_error')}"
    elif not frame.get("hardlinks"):
        reason = "worker frame observed no hard link (the boundary-attempt channel sees nothing)"
    elif not out.get("extracted"):
        reason = "worker finished but the benign file was not extracted"
    else:
        # How the package resolves a hard-link target is its own behaviour (some versions resolve
        # it against the working directory and refuse); the frame observing it is what matters.
        link = (
            "created"
            if out.get("link_created")
            else f"not created (exit {out.get('frame_status')})"
        )
        reason = (
            f"decompress worker identify+frame ok ({frame.get('attempts')} attempts, "
            f"{frame.get('hardlinks')} hard link observed, internal link {link})"
        )
    return {
        "ok": reason.startswith("decompress worker identify+frame ok"),
        "reason": reason,
        "worker_sha256": out.get("worker_sha256"),
    }


def prepare(
    spec: str,
    image: str,
    *,
    runner: Runner = subprocess.run,
    log: Callable[[str], None] = print,
) -> str:
    """Build and verify ``image`` for ``<package>@<exact version>``; return the lock's SHA-256."""
    package, version = split_spec(spec)
    check_inputs(package, version, image)
    if npm.exists(runner, image):
        log(f"REGISTRY-PREPARE reuse {image} (already present; not rebuilt)")
        return ""
    node = npm.node_image(DOCKERFILE)
    lock_bytes, lock_sha, _ = npm.lock_from_registry(
        runner, node, package, version, package_json(package, version), allowed_packages(), log
    )

    def verify(staging: str) -> str:
        seen = installed(runner, staging)
        if seen != (package, version):
            raise RegistryPrepareError(
                f"{staging} has {seen[0]}@{seen[1]} installed, expected {package}@{version}"
            )
        harness_check(runner, staging, package, version)
        worker = worker_check(runner, staging, package, version)
        if not worker["ok"]:
            raise RegistryPrepareError(
                f"worker incompatible (decompress worker): {worker['reason']}"
            )
        log(f"REGISTRY-PREPARE {worker['reason']}; worker sha256={worker['worker_sha256']}")
        return f"REGISTRY-PREPARE verified {package}@{version} offline; tagged {{image}}"

    with tempfile.TemporaryDirectory(prefix="inodefence-decompress-registry-") as tmp:
        context = build_context(package, version, lock_bytes, Path(tmp))
        npm.stage_and_tag(
            runner,
            dockerfile=DOCKERFILE,
            context=context,
            build_args=[f"ROLE={ROLE}"],
            image=image,
            verify=verify,
            log=log,
        )
    return lock_sha


_EVIDENCE_PROGRAM = r"""
const fs = require('fs'), path = require('path'), c = require('crypto')
const pkg = JSON.parse(fs.readFileSync('/target/package.json', 'utf8'))
const name = Object.keys(pkg.dependencies)[0]
const version = JSON.parse(fs.readFileSync(
  path.join('/target/node_modules', ...name.split('/'), 'package.json'), 'utf8')).version
const lock = fs.readFileSync('/target/package-lock.json')
const worker = fs.readFileSync('/target/worker.cjs')
console.log(JSON.stringify({name, version, lock: lock.toString('base64'),
  worker: c.createHash('sha256').update(worker).digest('hex')}))
"""


def image_evidence(image: str, runner: Runner = subprocess.run) -> dict[str, Any]:
    """Read, offline, the package, lock bytes and worker hash actually inside ``image``."""
    done, data = _run_offline(runner, image, _EVIDENCE_PROGRAM, {})
    if done.returncode != 0 or not isinstance(data, dict):
        raise RegistryPrepareError(f"cannot read evidence from {image}")
    lock = base64.b64decode(data["lock"])
    return {
        "package": str(data["name"]),
        "installed_version": str(data["version"]),
        "lock": lock,
        "lock_sha256": hashlib.sha256(lock).hexdigest(),
        "worker_sha256": str(data["worker"]),
    }


RECIPE = (
    "tools/decompress/Dockerfile ROLE="
    + ROLE
    + " for {spec}; lock generated at run time from "
    + REGISTRY
    + " (npm install --package-lock-only --ignore-scripts, pinned node image)"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="exploratory decompress image from the npm registry"
    )
    parser.add_argument("--spec", required=True, help="<package>@<X.Y.Z>")
    parser.add_argument("--image", required=True)
    args = parser.parse_args(argv)
    try:
        prepare(args.spec, args.image)
    except RegistryPrepareError as error:
        print(f"REGISTRY-PREPARE FAIL: {error}; {args.image} not created", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
