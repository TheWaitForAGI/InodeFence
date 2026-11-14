"""Per-target Docker image preparation for ``make target-run`` (target-specific, not common code).

Each target's image is either reused, or prepared from a recipe that is already committed in this
repository, then verified offline before any extraction runs. Nothing else is automated:

- node-tar: versions with ``tools/node-tar/versions/<v>/`` whose ``package.json`` pins ``tar``
  to ``<v>``; built from ``tools/node-tar/effect/Dockerfile`` with ``TAR_VERSION=<v>``
  (``npm ci`` from the committed lock).
- python-tarfile: any exact ``X.Y.Z``; ``docker pull python:<X.Y.Z>-slim`` (official runtime
  image, no build).
- oras-go: the ``oras.land/oras-go/v2`` version in ``tools/oras-go/<role>/go.mod``; built from
  ``tools/oras-go/Dockerfile`` with ``ROLE=<role>`` (``go mod download`` checks ``go.sum``).
- decompress: ``<package>@<version>`` pinned in ``tools/decompress/<role>/package.json``; built
  from ``tools/decompress/Dockerfile`` with ``ROLE=<role>`` (``npm ci`` from the committed lock).

Rules:

- An image that already exists under the requested reference is reused: no build, no pull, no
  retag. A tag is never overwritten or removed. Python's official tag is pulled only when it is not
  present locally, so a local tag is never moved either.
- The version string is validated (format, then a committed recipe) before it reaches any build
  argument. A version without a committed recipe is refused with the reason; no lock is generated
  and no unpinned package is installed.
- Building and pulling use the network. Verification does not: it runs the prepared image with
  ``--network none`` and reads the version actually installed inside (node-tar: ``tar``'s
  ``package.json``; python: ``platform.python_version()``; oras-go: the worker's ``identify``;
  decompress: the pinned dependency's name and ``package.json`` version). A mismatch with the
  request, or a failed build/pull/verification, raises ``ImagePrepareError``; no verdict is made.
- ``image_ref`` is chosen by the caller, so a development tag (for example
  ``inodefence-dev/oras-go:2.6.1``) can be prepared without touching the experiment images.

No CVE id, release role name or reference-file name is a decision condition here; versions are
matched only against the committed recipe files.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
BUILD_TIMEOUT = 1800
VERIFY_TIMEOUT = 120

_EXACT = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_DECOMPRESS_SPEC = re.compile(
    r"(?P<package>(?:@[a-z0-9][a-z0-9._-]*/)?decompress)@(?P<version>[0-9]+\.[0-9]+\.[0-9]+)"
)
_ORAS_REQUIRE = re.compile(r"^\s*oras\.land/oras-go/v2\s+v([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.M)

Runner = Callable[..., subprocess.CompletedProcess[str]]


class ImagePrepareError(RuntimeError):
    """The image could not be prepared or verified; no extraction or verdict may follow."""


class UnsupportedVersionError(ImagePrepareError, ValueError):
    """The requested version has no committed recipe (or is malformed)."""


@dataclass(frozen=True, slots=True)
class Recipe:
    """How to obtain one target version's image and what its contents must report."""

    target: str
    version: str
    expected: str  # what the offline check must print, exactly
    build: tuple[str, ...] | None  # ``docker build`` arguments (context = repo root), or None
    pull: str | None  # official image to pull when no build applies
    check: tuple[str, ...]  # ``docker run`` arguments after the image ref is inserted


@dataclass(frozen=True, slots=True)
class PreparedImage:
    image_ref: str
    image_id: str
    prepared: bool  # False: the image already existed and was reused
    observed: str


# ---- recipes (all derived from committed files) ----


def node_tar_recipe(version: str, tools: Path = TOOLS) -> Recipe:
    if _EXACT.fullmatch(version) is None:
        raise UnsupportedVersionError(f"node-tar version must be exact X.Y.Z: {version!r}")
    package = tools / "node-tar" / "versions" / version / "package.json"
    lock = package.with_name("package-lock.json")
    if not package.is_file() or not lock.is_file():
        raise UnsupportedVersionError(
            f"node-tar {version}: no committed lock in tools/node-tar/versions/{version}/ "
            "(auto-prepare builds only versions with a committed package-lock.json)"
        )
    pinned = json.loads(package.read_text(encoding="utf-8")).get("dependencies", {}).get("tar")
    if pinned != version:
        raise UnsupportedVersionError(f"node-tar {version}: committed package.json pins {pinned!r}")
    return Recipe(
        "node-tar",
        version,
        expected=version,
        build=("-f", "tools/node-tar/effect/Dockerfile", "--build-arg", f"TAR_VERSION={version}"),
        pull=None,
        check=(
            "--entrypoint",
            "/usr/local/bin/node",
            "{image}",
            "-e",
            "console.log(require('/target/node_modules/tar/package.json').version)",
        ),
    )


def python_tarfile_recipe(version: str) -> Recipe:
    if _EXACT.fullmatch(version) is None:
        raise UnsupportedVersionError(f"python runtime must be exact X.Y.Z: {version!r}")
    return Recipe(
        "python-tarfile",
        version,
        expected=version,
        build=None,
        pull=f"python:{version}-slim",
        check=(
            "--entrypoint",
            "python",
            "{image}",
            "-c",
            "import platform; print(platform.python_version())",
        ),
    )


def _roles(target_dir: Path) -> list[Path]:
    return sorted(p for p in target_dir.iterdir() if p.is_dir() and p.name != "worker")


def oras_go_recipe(version: str, tools: Path = TOOLS) -> Recipe:
    if _EXACT.fullmatch(version) is None:
        raise UnsupportedVersionError(f"oras-go version must be exact X.Y.Z: {version!r}")
    pinned = {}
    for role in _roles(tools / "oras-go"):
        gomod = role / "go.mod"
        found = _ORAS_REQUIRE.search(gomod.read_text(encoding="utf-8")) if gomod.is_file() else None
        if found and (role / "go.sum").is_file():
            pinned[found.group(1)] = role.name
    if version not in pinned:
        raise UnsupportedVersionError(
            f"oras-go {version}: no committed go.mod/go.sum pins it "
            f"(buildable: {', '.join(sorted(pinned)) or 'none'})"
        )
    return Recipe(
        "oras-go",
        version,
        expected=f"v{version}",
        build=("-f", "tools/oras-go/Dockerfile", "--build-arg", f"ROLE={pinned[version]}"),
        pull=None,
        check=("{image}", "identify"),
    )


def decompress_recipe(spec: str, tools: Path = TOOLS) -> Recipe:
    match = _DECOMPRESS_SPEC.fullmatch(spec)
    if match is None:
        raise UnsupportedVersionError(
            f"decompress version must be <package>@X.Y.Z, e.g. decompress@4.2.1: {spec!r}"
        )
    package, version = match["package"], match["version"]
    pinned = {}
    for role in _roles(tools / "decompress"):
        manifest, lock = role / "package.json", role / "package-lock.json"
        if manifest.is_file() and lock.is_file():
            deps = json.loads(manifest.read_text(encoding="utf-8")).get("dependencies", {})
            if len(deps) == 1:
                ((name, pin),) = deps.items()
                pinned[f"{name}@{pin}"] = role.name
    if spec not in pinned:
        raise UnsupportedVersionError(
            f"decompress {spec}: not pinned by a committed recipe "
            f"(buildable: {', '.join(sorted(pinned)) or 'none'}); the original package and the "
            "maintained fork are different packages"
        )
    return Recipe(
        "decompress",
        spec,
        expected=f"{package} {version}",
        build=("-f", "tools/decompress/Dockerfile", "--build-arg", f"ROLE={pinned[spec]}"),
        pull=None,
        check=(
            "--entrypoint",
            "/usr/local/bin/node",
            "{image}",
            "-e",
            "const p=require('/target/package.json');const n=Object.keys(p.dependencies)[0];"
            "console.log(n, require('/target/node_modules/'+n+'/package.json').version)",
        ),
    )


RECIPES: dict[str, Callable[[str], Recipe]] = {
    "node-tar": node_tar_recipe,
    "python-tarfile": python_tarfile_recipe,
    "oras-go": oras_go_recipe,
    "decompress": decompress_recipe,
}


# ---- docker steps ----


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


def image_id(image_ref: str, runner: Runner = subprocess.run) -> str | None:
    done = _docker(runner, ("image", "inspect", "--format", "{{.Id}}", image_ref), 60)
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def observed_version(recipe: Recipe, image_ref: str, runner: Runner = subprocess.run) -> str:
    """Run the image offline and return the version it reports (oras-go: from its JSON)."""
    check = tuple(image_ref if part == "{image}" else part for part in recipe.check)
    done = _docker(runner, ("run", "--rm", "--network", "none", *check), VERIFY_TIMEOUT)
    if done.returncode != 0:
        raise ImagePrepareError(
            f"{recipe.target} {recipe.version}: version check failed in {image_ref}: "
            f"{(done.stderr or '').strip()[-300:]}"
        )
    out = (done.stdout or "").strip()
    if recipe.target == "oras-go":
        try:
            return str(json.loads(out.splitlines()[-1])["oras_go_version"])
        except (ValueError, KeyError, IndexError) as error:
            raise ImagePrepareError(f"oras-go identify output unreadable: {out[:200]!r}") from error
    return out.splitlines()[-1] if out else ""


def _verified(recipe: Recipe, image_ref: str, runner: Runner, prepared: bool) -> PreparedImage:
    seen = observed_version(recipe, image_ref, runner)
    if seen != recipe.expected:
        raise ImagePrepareError(
            f"{recipe.target} {recipe.version}: {image_ref} contains {seen!r}, "
            f"expected {recipe.expected!r}"
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
            raise ImagePrepareError(
                f"{recipe.target} {recipe.version}: build failed: "
                f"{(done.stderr or '').strip()[-400:]}"
            )
    else:
        assert recipe.pull is not None
        if image_id(recipe.pull, runner) is None:
            done = _docker(runner, ("pull", "-q", recipe.pull), BUILD_TIMEOUT)
            if done.returncode != 0:
                raise ImagePrepareError(
                    f"{recipe.target} {recipe.version}: pull {recipe.pull} failed: "
                    f"{(done.stderr or '').strip()[-400:]}"
                )
        if recipe.pull != image_ref:
            done = _docker(runner, ("tag", recipe.pull, image_ref), 60)
            if done.returncode != 0:
                raise ImagePrepareError(f"tag {recipe.pull} -> {image_ref} failed")
    return _verified(recipe, image_ref, runner, prepared=True)


def prepare(
    target: str, version: str, image_ref: str, runner: Runner = subprocess.run
) -> PreparedImage:
    """Validate ``version`` for ``target`` against committed recipes, then ``ensure_image``."""
    if target not in RECIPES:
        raise UnsupportedVersionError(f"no image recipe for target {target!r}")
    return ensure_image(RECIPES[target](version), image_ref, runner)
