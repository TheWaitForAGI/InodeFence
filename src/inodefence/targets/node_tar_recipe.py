"""Content-addressed provenance of the `make demo` node-tar image build recipe.

The demo report already records the built image's observed ``image_id`` (the local
``docker image inspect`` config digest). That digest is produced at build time and
can absorb nondeterministic metadata, so it does not by itself establish that the
same recipe yields the same image. This module records the other half of the
provenance: a deterministic fingerprint of the *committed build recipe* that the
image is built from.

The recipe is the set of files that fully determine the build context of
``tools/node-tar/Dockerfile`` (what ``make demo`` builds, see
``scripts/local_node_tar_smoke.sh``): the Dockerfile itself (which pins both base
images by ``@sha256:`` digest and fixes the install/COPY/entrypoint steps), the
pinned ``package.json`` / ``package-lock.json`` (exact node-tar release with
per-dependency integrity), and the two sources COPYed into the image. Because
those inputs are content-addressed and the build is otherwise fully pinned
(digest-pinned bases, ``npm ci --ignore-scripts`` from the locked tree), an
identical ``recipe_sha256`` means an identical build context, which is the
honest "same recipe -> same image" guarantee.

This computation is pure: it reads committed files only, never a container
runtime, and makes no network or Docker call. ``base_images`` and ``tar_version``
are values *derived from* those files, surfaced for human provenance; the digest
is taken over the raw file bytes (via ``files_sha256``), which already cover them.
"""

import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import TypedDict

RECIPE_FORMAT = "inodefence-demo-image-recipe"
RECIPE_SCHEMA = 1


class DemoImageRecipe(TypedDict):
    """Content-addressed provenance of the committed `make demo` image recipe.

    ``recipe_sha256`` is taken over ``files_sha256`` (the byte content of every
    build-context input); ``base_images`` and ``tar_version`` are derived from
    those files and surfaced for human provenance.
    """

    format: str
    schema_version: int
    dockerfile: str
    tar_version: str
    base_images: list[str]
    files_sha256: dict[str, str]
    recipe_sha256: str


# Build file (-f) of the `make demo` image, relative to the repository root.
DEMO_IMAGE_DOCKERFILE = "tools/node-tar/Dockerfile"
# Every file whose bytes enter the Dockerfile's build context, relative to the
# repository root. The Dockerfile is included so the base-image digest pins and
# the install/COPY/entrypoint steps are covered by the fingerprint too.
DEMO_IMAGE_RECIPE_FILES = (
    DEMO_IMAGE_DOCKERFILE,
    "tools/node-tar/package.json",
    "tools/node-tar/package-lock.json",
    "src/inodefence/targets/_node_worker.cjs",
    "src/inodefence/targets/_node_effect_producer.cjs",
)


def repository_root() -> Path:
    """The source checkout root (src/inodefence/targets/ -> repository root)."""
    return Path(__file__).resolve().parents[3]


def _read_recipe_file(root: Path, relative: str) -> bytes:
    """Read one committed recipe file, rejecting symlinks and non-files.

    A symlinked build input would make the fingerprint depend on something outside
    the committed bytes, so it is refused rather than silently dereferenced.
    """
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"recipe input must be a committed regular file: {relative}")
    return path.read_bytes()


def _base_images(dockerfile: bytes) -> tuple[str, ...]:
    """Digest-pinned base image references from the Dockerfile's FROM lines.

    Every FROM must pin its image by ``@sha256:`` digest; an unpinned base would
    break the reproducibility guarantee, so it is rejected. Returns sorted unique
    references (the ``AS <stage>`` alias, if any, is not part of the identity).
    """
    references: set[str] = set()
    for line in dockerfile.decode("utf-8").splitlines():
        tokens = line.split()
        if len(tokens) < 2 or tokens[0].upper() != "FROM":
            continue
        reference = tokens[1]
        if "@sha256:" not in reference:
            raise ValueError(f"demo image base is not digest-pinned: {reference}")
        references.add(reference)
    if not references:
        raise ValueError("demo image Dockerfile declares no FROM base image")
    return tuple(sorted(references))


def _tar_version(package_json: bytes) -> str:
    """The exact node-tar release the demo image pins (package.json dependency)."""
    dependencies = json.loads(package_json).get("dependencies")
    version = dependencies.get("tar") if isinstance(dependencies, dict) else None
    if not isinstance(version, str) or not version:
        raise ValueError("demo image package.json does not pin a node-tar version")
    return version


def recipe_digest(files_sha256: Mapping[str, str]) -> str:
    """Deterministic fingerprint of the recipe's build-context file digests.

    Taken over the file digests alone (sorted, compact JSON), so it depends only
    on the recipe's byte content and not on record metadata such as the schema
    version. The same committed files always yield the same ``recipe_sha256``.
    """
    canonical = json.dumps(
        dict(sorted(files_sha256.items())),
        separators=(",", ":"),
        ensure_ascii=True,
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def demo_image_recipe(repository: Path | None = None) -> DemoImageRecipe:
    """Content-addressed provenance of the committed `make demo` image recipe.

    Returns a JSON-ready mapping with the per-file SHA-256 of every build-context
    input (``files_sha256``), the digest-pinned base images and node-tar version
    derived from them, and ``recipe_sha256`` over the file digests. Pure and
    deterministic: identical committed files render an identical mapping.
    """
    root = repository if repository is not None else repository_root()
    contents = {name: _read_recipe_file(root, name) for name in DEMO_IMAGE_RECIPE_FILES}
    files_sha256 = {name: sha256(data).hexdigest() for name, data in contents.items()}
    return {
        "format": RECIPE_FORMAT,
        "schema_version": RECIPE_SCHEMA,
        "dockerfile": DEMO_IMAGE_DOCKERFILE,
        "tar_version": _tar_version(contents["tools/node-tar/package.json"]),
        "base_images": list(_base_images(contents[DEMO_IMAGE_DOCKERFILE])),
        "files_sha256": dict(sorted(files_sha256.items())),
        "recipe_sha256": recipe_digest(files_sha256),
    }
