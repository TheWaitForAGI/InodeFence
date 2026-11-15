"""npm registry preparation shared by npm-based targets (no target-specific knowledge).

What every registry-prepared npm image needs, independent of which package it pins:

- ``node_image``: the pinned ``FROM node:...@sha256:...`` of the target's existing Dockerfile; npm
  runs only in disposable containers of that image, with nothing mounted (inputs in environment
  variables, output on stdout).
- ``registry_integrity`` / ``resolve_dist_tag``: what the official registry publishes now.
- ``generate_lock``: ``npm install --package-lock-only --ignore-scripts`` (nothing installed, no
  scripts run).
- ``lock_from_registry``: the steps above plus the checks that refuse a lock (root dependency not
  exactly ``package@version``, the package resolving to another version, a ``resolved`` outside
  the official registry, an ``integrity`` different from the registry's) and the findings that are
  only recorded (packages absent from the committed locks, packages declaring install scripts).
- ``stage_and_tag``: build into ``<image>-unverified``, run the target's offline checks, and only
  then tag ``<image>``; the staging tag is always removed.

The target module supplies the Dockerfile, the temporary build context, the allowed-name set and
the offline checks. Every failure raises ``RegistryPrepareError`` and leaves ``<image>`` absent.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

REGISTRY = "https://registry.npmjs.org/"
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
_NETWORK_CODES = (
    "ENOTFOUND",
    "EAI_AGAIN",
    "ETIMEDOUT",
    "ECONNREFUSED",
    "ECONNRESET",
    "ENETUNREACH",
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


class RegistryPrepareError(RuntimeError):
    """A step failed; the requested image must not exist afterwards."""


def node_image(dockerfile: Path) -> str:
    """The pinned Node image (``FROM node:...@sha256:...``) of an existing Dockerfile."""
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        match = re.match(r"FROM\s+(node:\S+@sha256:[0-9a-f]{64})(?:\s|$)", line)
        if match:
            return match.group(1)
    raise RegistryPrepareError(f"no pinned node image in {dockerfile}")


def check_image_ref(image: str, repository: str) -> None:
    """A plain reference in the registry-only repository (never a committed-recipe name)."""
    if IMAGE_REF.fullmatch(image) is None or image.endswith(STAGING):
        raise RegistryPrepareError(f"not a plain image reference: {image!r}")
    if image.partition(":")[0] != repository:
        raise RegistryPrepareError(
            f"registry-prepared images are tagged only as {repository}:<tag>, not {image!r}"
        )


def docker(runner: Runner, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RegistryPrepareError(f"docker {args[0]} failed: {type(error).__name__}") from error


def exists(runner: Runner, image: str) -> bool:
    return docker(runner, ["image", "inspect", image], 60).returncode == 0


def npm(runner: Runner, node: str, script: str, env: dict[str, str]) -> str:
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
    out = npm(runner, node, script, {"SPECS": " ".join(specs)})
    found: dict[str, str] = {}
    for line in out.splitlines():
        spec, _, integrity = line.strip().partition(" ")
        if spec and integrity.startswith("sha512-"):
            found[spec] = integrity
    missing = [s for s in specs if s not in found]
    if missing:
        raise RegistryPrepareError(f"registry has no integrity for {', '.join(missing)}")
    return found


def resolve_dist_tag(runner: Runner, node: str, package: str, tag: str = "latest") -> str:
    """The registry's current ``tag`` of ``package`` as an exact version."""
    out = npm(runner, node, f"npm view {package} dist-tags.{tag}", {})
    version = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if EXACT.fullmatch(version) is None:
        raise RegistryPrepareError(
            f"registry {tag} for {package} is not an exact version: {version!r}"
        )
    return version


def generate_lock(runner: Runner, node: str, package_json_text: str) -> bytes:
    pkg = base64.b64encode(package_json_text.encode()).decode()
    script = (
        'cd /tmp && echo "$PKG" | base64 -d > package.json && '
        "npm install --package-lock-only --ignore-scripts --no-audit --no-fund >/dev/null 2>&1 "
        "&& cat package-lock.json"
    )
    out = npm(runner, node, script, {"PKG": pkg})
    if not out.strip():
        raise RegistryPrepareError("npm produced no lock")
    return out.encode()


def lock_specs(lock: dict[str, Any]) -> list[str]:
    return sorted(
        f"{key.split('node_modules/')[-1]}@{entry.get('version')}"
        for key, entry in lock.get("packages", {}).items()
        if key
    )


def check_lock(lock: dict[str, Any], package: str, version: str, published: dict[str, str]) -> None:
    """Fail unless the lock pins exactly ``package@version`` and what the registry published."""
    packages = lock.get("packages")
    if not isinstance(packages, dict) or lock.get("lockfileVersion") != 3:
        raise RegistryPrepareError("unexpected lock format")
    if packages.get("", {}).get("dependencies") != {package: version}:
        raise RegistryPrepareError(f"lock root does not depend on exactly {package}@{version}")
    if packages.get(f"node_modules/{package}", {}).get("version") != version:
        raise RegistryPrepareError(
            f"lock resolves {package} to {packages.get(f'node_modules/{package}')}"
        )
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


def committed_lock_names(locks: list[Path]) -> set[str]:
    """Every package name appearing in the given committed lock files."""
    names: set[str] = set()
    for lock in locks:
        for key in json.loads(lock.read_text(encoding="utf-8"))["packages"]:
            if key:
                names.add(key.split("node_modules/")[-1])
    return names


def lock_from_registry(
    runner: Runner,
    node: str,
    package: str,
    version: str,
    package_json_text: str,
    allowed: set[str],
    log: Callable[[str], None],
) -> tuple[bytes, str, dict[str, Any]]:
    """Steps 1-3: existence, lock generation, refusing checks, recorded findings.

    Returns ``(lock bytes, lock SHA-256, findings)``.
    """
    spec = f"{package}@{version}"
    published = registry_integrity(runner, node, [spec])
    log(f"REGISTRY-PREPARE {spec} exists; registry integrity {published[spec]}")
    lock_bytes = generate_lock(runner, node, package_json_text)
    try:
        lock = json.loads(lock_bytes)
    except ValueError as error:
        raise RegistryPrepareError("npm lock is not JSON") from error
    published.update(registry_integrity(runner, node, lock_specs(lock)))
    check_lock(lock, package, version, published)
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
    return lock_bytes, lock_sha, findings


def stage_and_tag(
    runner: Runner,
    *,
    dockerfile: Path,
    context: Path,
    build_args: list[str],
    image: str,
    verify: Callable[[str], str],
    log: Callable[[str], None],
) -> None:
    """Build ``<image>-unverified``, run ``verify(staging)``, then tag ``image``; always untag.

    ``verify`` raises ``RegistryPrepareError`` to refuse and returns a line to log on success.
    """
    staging = f"{image}{STAGING}"
    build = ["build", "-q", "-f", str(dockerfile)]
    for arg in build_args:
        build += ["--build-arg", arg]
    build += ["-t", staging, str(context)]
    done = docker(runner, build, BUILD_TIMEOUT)
    if done.returncode != 0:
        raise RegistryPrepareError(f"build failed: {(done.stderr or '').strip()[-300:]}")
    try:
        message = verify(staging)
        if docker(runner, ["tag", staging, image], 60).returncode != 0:
            raise RegistryPrepareError(f"tag {staging} -> {image} failed")
        log(message.replace("{image}", image))
    finally:
        docker(runner, ["rmi", "--no-prune", staging], 60)
