"""Prepare the python-tarfile exploration image: the official runtime image plus the worker.

The base is the cell image the common prepare layer already resolved and version-checked
(``python:X.Y.Z-slim``, see ``scripts.run_python_tarfile_target``). On top of it this adds only
``/target/worker.py`` (``tools/python-tarfile/effect/``): no package installs, no RUN step, built
with ``--network none`` from a temporary context outside the repository, nothing mounted.

Every image is checked offline before it is used -- a freshly built one before it gets its name,
and an existing one before it is reused -- in a throwaway container with no network, a read-only
root, all capabilities dropped and a non-root user:

1. ``--identify``: the interpreter must be exactly the requested ``X.Y.Z``, the worker's SHA-256
   must equal this checkout's worker, and the runtime must have extraction filters;
2. ``--self-test``: the worker extracts one harmless member with the ``data`` filter.

A failed check is an error naming the reason (``worker incompatible``); an existing image that
fails is never used and never silently rebuilt -- remove it and run again. The extraction runs
themselves use the common container backend (``inodefence.execution``), unchanged.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from scripts.run_target import image_id

REPO_ROOT = Path(__file__).resolve().parents[1]
RECIPE_DIR = REPO_ROOT / "tools" / "python-tarfile" / "effect"
WORKER = RECIPE_DIR / "worker.py"
DOCKERFILE = RECIPE_DIR / "Dockerfile"
IMAGE = "inodefence-python-tarfile-effect:{version}"
UNVERIFIED = "-unverified"
TIMEOUT = 120
_EXACT = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
#: Throwaway check container: no network, read-only root, no capabilities, non-root, small /tmp.
CHECK_FLAGS = (
    "--rm",
    "--network",
    "none",
    "--read-only",
    "--cap-drop",
    "ALL",
    "--user",
    "65534:65534",
    "--tmpfs",
    "/tmp:rw,noexec,nosuid,nodev,size=16m",
    "--entrypoint",
    "/usr/local/bin/python",
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


class ProducerImageError(ValueError):
    """The producer image could not be prepared or failed its offline check."""


@dataclass(frozen=True, slots=True)
class ProducerImage:
    image_ref: str
    image_id: str
    python_version: str
    worker_sha256: str
    tarfile_sha256: str
    check: str  # what happened: "built, checked" or "reused, checked"


def worker_sha256() -> str:
    return sha256(WORKER.read_bytes()).hexdigest()


def producer_ref(version: str, suffix: str = "") -> str:
    if _EXACT.fullmatch(version) is None:
        raise ProducerImageError(f"producer image needs an exact runtime X.Y.Z: {version!r}")
    return IMAGE.format(version=version) + suffix


def verify_producer(image: str, version: str, runner: Runner = subprocess.run) -> dict[str, str]:
    """Offline identity + self-test of ``image``; ``ProducerImageError`` names what failed."""

    def run(*args: str) -> str:
        try:
            done = runner(
                ["docker", "run", *CHECK_FLAGS, image, "-I", "/target/worker.py", *args],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ProducerImageError(f"worker incompatible: {type(error).__name__}") from error
        if done.returncode != 0:
            tail = (done.stderr or done.stdout or "").strip()[-200:]
            raise ProducerImageError(
                f"worker incompatible: {args[0]} exit {done.returncode} {tail}"
            )
        lines = (done.stdout or "").strip().splitlines()
        return lines[-1] if lines else ""

    try:
        identity = json.loads(run("--identify"))
        test = json.loads(run("--self-test"))
    except ValueError as error:
        if isinstance(error, ProducerImageError):
            raise
        raise ProducerImageError(f"worker incompatible: unreadable output ({error})") from error
    if not isinstance(identity, dict) or identity.get("python_version") != version:
        seen = identity.get("python_version") if isinstance(identity, dict) else None
        raise ProducerImageError(f"worker incompatible: image runs python {seen!r}, not {version}")
    if identity.get("worker_sha256") != worker_sha256():
        raise ProducerImageError(
            "worker incompatible: the image's worker differs from this checkout's; "
            f"remove {image} and run again"
        )
    if identity.get("has_data_filter") is not True:
        raise ProducerImageError("worker incompatible: this runtime has no extraction filters")
    if not isinstance(test, dict) or test.get("self_test") != "ok":
        raise ProducerImageError("worker incompatible: self-test extraction failed")
    tarfile_sha = identity.get("tarfile_sha256")
    if not isinstance(tarfile_sha, str) or re.fullmatch(r"[0-9a-f]{64}", tarfile_sha) is None:
        raise ProducerImageError("worker incompatible: no tarfile module hash")
    return {"python_version": version, "tarfile_sha256": tarfile_sha}


def _checked(runner: Runner, command: list[str], what: str) -> None:
    try:
        done = runner(command, capture_output=True, text=True, timeout=TIMEOUT * 5)
    except (OSError, subprocess.SubprocessError) as error:
        raise ProducerImageError(f"{what} failed: {type(error).__name__}: {error}") from error
    if done.returncode != 0:
        raise ProducerImageError(f"{what} failed: {(done.stderr or '').strip()[-300:]}")


def ensure_producer_image(
    base_ref: str,
    version: str,
    *,
    suffix: str = "",
    runner: Runner = subprocess.run,
    present: Callable[[str], str | None] = image_id,
) -> ProducerImage:
    """Reuse (after the offline check) or build-check-tag the producer image for ``version``."""
    ref = producer_ref(version, suffix)
    found = present(ref)
    if found is not None:
        facts = verify_producer(ref, version, runner)
        return ProducerImage(
            ref, found, version, worker_sha256(), facts["tarfile_sha256"], "reused, checked"
        )
    if present(base_ref) is None:
        raise ProducerImageError(f"base image {base_ref} is not prepared")
    staging = ref + UNVERIFIED
    context = Path(tempfile.mkdtemp(prefix="inodefence-python-producer-"))
    try:
        shutil.copyfile(DOCKERFILE, context / "Dockerfile")
        shutil.copyfile(WORKER, context / "worker.py")
        _checked(
            runner,
            ["docker", "build", "-q", "--network", "none", "--build-arg", f"BASE={base_ref}"]
            + ["-t", staging, str(context)],
            f"building {ref}",
        )
        try:
            facts = verify_producer(staging, version, runner)
        except ProducerImageError:
            runner(["docker", "rmi", "--no-prune", staging], capture_output=True, text=True)
            raise
        _checked(runner, ["docker", "tag", staging, ref], f"tagging {ref}")
        runner(["docker", "rmi", "--no-prune", staging], capture_output=True, text=True)
    finally:
        shutil.rmtree(context, ignore_errors=True)
    built = present(ref)
    if built is None:
        raise ProducerImageError(f"{ref} is not present after the build")
    return ProducerImage(
        ref, built, version, worker_sha256(), facts["tarfile_sha256"], "built, checked"
    )
