"""Generic Docker image preparation helpers for target adapters (no target-specific knowledge).

A target module describes its image with a ``Recipe``: either ``docker build`` arguments from a
recipe committed in this repository, or one image to pull, plus an offline check that prints the
version installed inside. ``ensure_image`` then:

- reuses an image that already exists under the requested reference (no build, pull or retag),
  and never overwrites or removes a tag; an image to pull is pulled only when it is absent, so a
  local tag is never moved either;
- otherwise builds or pulls it (the only network step) and, when the pulled reference differs from
  the requested one, tags it;
- in both cases runs the image with ``--network none`` and compares what it reports with
  ``Recipe.expected``. A mismatch, or a failed build/pull/check, raises ``ImagePrepareError``; the
  caller must not run an extraction or make a verdict after that.

Version strings are validated by the target module (``exact_version`` here for ``X.Y.Z``) and
matched to a committed recipe before they become build arguments.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_TIMEOUT = 1800
CHECK_TIMEOUT = 120
EXACT_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
IMAGE_SLOT = "{image}"

Runner = Callable[..., subprocess.CompletedProcess[str]]


class ImagePrepareError(RuntimeError):
    """The image could not be prepared or verified; no extraction or verdict may follow."""


class UnsupportedVersionError(ImagePrepareError, ValueError):
    """The requested version is malformed or has no committed recipe."""


def exact_version(version: str, what: str) -> str:
    if EXACT_VERSION.fullmatch(version) is None:
        raise UnsupportedVersionError(f"{what} must be exact X.Y.Z: {version!r}")
    return version


def _last_line(out: str) -> str:
    lines = out.strip().splitlines()
    return lines[-1] if lines else ""


@dataclass(frozen=True, slots=True)
class Recipe:
    """How to obtain one image, and what its offline check must print."""

    label: str  # for messages only, e.g. "<target> <version>"
    expected: str
    check: tuple[str, ...]  # ``docker run`` arguments; IMAGE_SLOT is replaced by the image ref
    build: tuple[str, ...] | None = None  # ``docker build`` arguments; context is the repo root
    pull: str | None = None  # image to pull when there is nothing to build
    parse: Callable[[str], str] = field(default=_last_line)

    def __post_init__(self) -> None:
        if (self.build is None) == (self.pull is None):
            raise ValueError("a recipe either builds or pulls")
        if IMAGE_SLOT not in self.check:
            raise ValueError("check must contain the image slot")


@dataclass(frozen=True, slots=True)
class PreparedImage:
    image_ref: str
    image_id: str
    prepared: bool  # False: the image already existed and was reused
    observed: str


def _docker(runner: Runner, args: Sequence[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            ["docker", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ImagePrepareError(f"docker {args[0]}: {type(error).__name__}: {error}") from error


def _tail(done: subprocess.CompletedProcess[str]) -> str:
    return (done.stderr or "").strip()[-400:]


def image_id(image_ref: str, runner: Runner = subprocess.run) -> str | None:
    """The local image id, or None when ``image_ref`` does not exist locally."""
    done = _docker(runner, ("image", "inspect", "--format", "{{.Id}}", image_ref), 60)
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def observed_version(recipe: Recipe, image_ref: str, runner: Runner = subprocess.run) -> str:
    check = tuple(image_ref if part == IMAGE_SLOT else part for part in recipe.check)
    done = _docker(runner, ("run", "--rm", "--network", "none", *check), CHECK_TIMEOUT)
    if done.returncode != 0:
        raise ImagePrepareError(
            f"{recipe.label}: version check failed in {image_ref}: {_tail(done)}"
        )
    try:
        return recipe.parse(done.stdout or "")
    except (ValueError, KeyError, IndexError) as error:
        raise ImagePrepareError(f"{recipe.label}: unreadable version check output") from error


def _verified(recipe: Recipe, image_ref: str, runner: Runner, prepared: bool) -> PreparedImage:
    seen = observed_version(recipe, image_ref, runner)
    if seen != recipe.expected:
        raise ImagePrepareError(
            f"{recipe.label}: {image_ref} contains {seen!r}, expected {recipe.expected!r}"
        )
    found = image_id(image_ref, runner)
    if found is None:
        raise ImagePrepareError(f"{image_ref} disappeared after verification")
    return PreparedImage(image_ref, found, prepared, seen)


def ensure_image(recipe: Recipe, image_ref: str, runner: Runner = subprocess.run) -> PreparedImage:
    """Reuse ``image_ref`` if present, else prepare it from ``recipe``; verify either way."""
    if image_id(image_ref, runner) is not None:
        return _verified(recipe, image_ref, runner, prepared=False)
    if recipe.build is not None:
        done = _docker(runner, ("build", "-q", *recipe.build, "-t", image_ref, "."), BUILD_TIMEOUT)
        if done.returncode != 0:
            raise ImagePrepareError(f"{recipe.label}: build failed: {_tail(done)}")
    else:
        assert recipe.pull is not None
        if image_id(recipe.pull, runner) is None:
            done = _docker(runner, ("pull", "-q", recipe.pull), BUILD_TIMEOUT)
            if done.returncode != 0:
                raise ImagePrepareError(f"{recipe.label}: pull {recipe.pull} failed: {_tail(done)}")
        if recipe.pull != image_ref:
            done = _docker(runner, ("tag", recipe.pull, image_ref), 60)
            if done.returncode != 0:
                raise ImagePrepareError(f"{recipe.label}: tag {recipe.pull} -> {image_ref} failed")
    return _verified(recipe, image_ref, runner, prepared=True)


def single_dependency(package_json: dict[str, object]) -> tuple[str, str] | None:
    """The one ``dependencies`` entry of a committed package.json, or None."""
    deps = package_json.get("dependencies")
    if not isinstance(deps, dict) or len(deps) != 1:
        return None
    ((name, pin),) = deps.items()
    return (str(name), str(pin))
