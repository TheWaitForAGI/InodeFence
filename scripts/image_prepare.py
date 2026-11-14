"""Generic image-preparation helpers for target adapters (no target-specific knowledge).

A target module describes how one image version is obtained with a ``Recipe`` (``docker build``
arguments from a recipe committed in this repository, or one image to pull) plus an offline
version check. ``prepare_step`` turns it into the common ``scripts.run_target.PrepareStep``
command list, which ``run_target`` runs from the repository root only when the cell's image is
missing (an existing image is reused untouched):

1. build into ``<image_ref>-unverified`` (or: pull the official image if it is absent locally,
   then tag it ``<image_ref>-unverified``) -- the only steps that use the network;
2. ``python -m scripts.image_prepare check`` runs that image with ``--network none`` and fails
   unless it reports exactly the expected version;
3. tag it ``<image_ref>`` and untag ``<image_ref>-unverified``.

So ``image_ref`` comes into existence only after the version inside was confirmed: a failed build,
pull or check leaves ``image_ref`` absent (the run reports an error, makes no verdict, and a later
run tries again). No other existing tag is retagged, overwritten or removed; a pulled official tag
is created only when it was absent. (If ``image_ref`` *is* the official tag being pulled, step 1
creates it before the check; the extraction program also re-checks the runtime it ran on.)

Version strings are validated by the target module (``exact_version`` for ``X.Y.Z``) and matched to
a committed recipe before they become build arguments.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

from scripts.run_target import PrepareStep, RunCell, image_id

EXACT_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
IMAGE_SLOT = "{image}"
UNVERIFIED = "-unverified"
CHECK_TIMEOUT = 120


class UnsupportedVersionError(ValueError):
    """The requested version is malformed or has no committed recipe (the message says which)."""


def exact_version(version: str, what: str) -> str:
    if EXACT_VERSION.fullmatch(version) is None:
        raise UnsupportedVersionError(f"{what} must be exact X.Y.Z: {version!r}")
    return version


def single_dependency(package_json: dict[str, object]) -> tuple[str, str] | None:
    """The one ``dependencies`` entry of a committed package.json, or None."""
    deps = package_json.get("dependencies")
    if not isinstance(deps, dict) or len(deps) != 1:
        return None
    ((name, pin),) = deps.items()
    return (str(name), str(pin))


@dataclass(frozen=True, slots=True)
class Recipe:
    """How to obtain one image version, and what its offline check must print."""

    description: str
    expected: str
    check: tuple[str, ...]  # ``docker run`` arguments; IMAGE_SLOT is replaced by the image ref
    build: tuple[str, ...] | None = None  # ``docker build`` arguments; context is the repo root
    pull: str | None = None  # official image to pull when nothing is built
    json_key: str | None = None  # read the version from this key of the last output line

    def __post_init__(self) -> None:
        if (self.build is None) == (self.pull is None):
            raise ValueError("a recipe either builds or pulls")
        if IMAGE_SLOT not in self.check:
            raise ValueError("check must contain the image slot")


def unsupported(cell: RunCell, reason: str) -> PrepareStep:
    return PrepareStep(image_ref=cell.image_ref or "", commands=None, reason=reason)


def prepare_step(
    recipe: Recipe,
    image_ref: str,
    *,
    python: str = sys.executable,
    present: Callable[[str], str | None] = image_id,
) -> PrepareStep:
    """The build/pull -> offline check -> tag command list that makes exactly ``image_ref``."""
    staging = f"{image_ref}{UNVERIFIED}"
    commands: list[tuple[str, ...]] = []
    if recipe.build is not None:
        commands.append(("docker", "build", "-q", *recipe.build, "-t", staging, "."))
    else:
        assert recipe.pull is not None
        if present(recipe.pull) is None:
            commands.append(("docker", "pull", "-q", recipe.pull))
        commands.append(("docker", "tag", recipe.pull, staging))
    check = [python, "-m", "scripts.image_prepare", "check", "--expect", recipe.expected]
    if recipe.json_key:
        check += ["--json-key", recipe.json_key]
    check += ["--", *(staging if part == IMAGE_SLOT else part for part in recipe.check)]
    commands.append(tuple(check))
    commands.append(("docker", "tag", staging, image_ref))
    commands.append(("docker", "rmi", "--no-prune", staging))
    return PrepareStep(image_ref=image_ref, commands=tuple(commands), reason=recipe.description)


def recipe_step(cell: RunCell, make: Callable[[], Recipe]) -> PrepareStep:
    """``prepare_step`` for a cell, or an unsupported step carrying the refusal reason."""
    if cell.image_ref is None:
        return unsupported(cell, "cell has no image")
    try:
        return prepare_step(make(), cell.image_ref)
    except UnsupportedVersionError as error:
        return unsupported(cell, str(error))


# ---- offline version check (the command prepare_step inserts) ----


def observed(stdout: str, json_key: str | None) -> str:
    lines = stdout.strip().splitlines()
    last = lines[-1] if lines else ""
    if json_key is None:
        return last
    value = json.loads(last)[json_key]
    return str(value)


def check(
    argv: list[str], runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.image_prepare check")
    parser.add_argument("--expect", required=True)
    parser.add_argument("--json-key")
    parser.add_argument("docker_run_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    run_args = [a for a in args.docker_run_args if a != "--"]
    try:
        done = runner(
            ["docker", "run", "--rm", "--network", "none", *run_args],
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"IMAGE-CHECK FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    if done.returncode != 0:
        print(f"IMAGE-CHECK FAIL: exit {done.returncode}: {done.stderr[-300:]}", file=sys.stderr)
        return 1
    try:
        seen = observed(done.stdout, args.json_key)
    except (ValueError, KeyError) as error:
        print(f"IMAGE-CHECK FAIL: unreadable output: {error}", file=sys.stderr)
        return 1
    if seen != args.expect:
        print(
            f"IMAGE-CHECK FAIL: image reports {seen!r}, expected {args.expect!r}", file=sys.stderr
        )
        return 1
    print(f"IMAGE-CHECK OK {seen}")
    return 0


# ---- verify an already-present image before it is reused ----


def check_existing(
    recipe: Recipe,
    image_ref: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str | None:
    """Run the recipe's offline check against an already-present ``image_ref``.

    Unlike preparation this never builds, pulls or retags: it only runs the committed check
    against the existing image. Returns ``None`` when the image reports exactly the expected
    version, or a one-line reason when it does not -- so a caller can refuse to reuse an image
    that carries the right tag but the wrong contents instead of trusting the tag name.
    """
    argv = ["--expect", recipe.expected]
    if recipe.json_key:
        argv += ["--json-key", recipe.json_key]
    argv += ["--", *(image_ref if part == IMAGE_SLOT else part for part in recipe.check)]
    if check(argv, runner) == 0:
        return None
    return f"present image does not report the expected version {recipe.expected!r}"


def recipe_verify_existing(
    make: Callable[[RunCell], Recipe],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Callable[[RunCell, str], str | None]:
    """A ``TargetAdapter.verify_existing`` built from a target's recipe.

    Before a present image is reused, run its recipe's offline check against it. A version with
    no committed recipe (``UnsupportedVersionError``) or a failed check returns a reason so the
    common runner refuses the reuse; a cell with no image is skipped (``None``).
    """

    def verify(cell: RunCell, image_id: str) -> str | None:
        if cell.image_ref is None:
            return None
        try:
            recipe = make(cell)
        except UnsupportedVersionError as error:
            return str(error)
        return check_existing(recipe, cell.image_ref, runner)

    return verify


if __name__ == "__main__":
    if sys.argv[1:2] != ["check"]:
        raise SystemExit(
            "usage: python -m scripts.image_prepare check --expect V [--json-key K] -- ARGS"
        )
    raise SystemExit(check(sys.argv[2:]))
