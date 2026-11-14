"""node-tar image recipe (target-specific; attached to the node-tar adapter on the interface PR).

Supported: versions with a committed ``tools/node-tar/versions/<v>/package.json`` +
``package-lock.json`` whose ``tar`` dependency is pinned to exactly ``<v>``. Built from
``tools/node-tar/effect/Dockerfile`` with ``TAR_VERSION=<v>`` (``npm ci --ignore-scripts`` from the
committed lock; the Dockerfile also checks the installed version). After the build, the image is
run offline and ``tar``'s own ``package.json`` version must equal ``<v>``. Any other version is
refused: no lock is generated and nothing unpinned is installed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.image_prepare import (
    IMAGE_SLOT,
    REPO_ROOT,
    PreparedImage,
    Recipe,
    Runner,
    UnsupportedVersionError,
    ensure_image,
    exact_version,
    single_dependency,
)

VERSIONS_DIR = REPO_ROOT / "tools" / "node-tar" / "versions"


def recipe(version: str, versions_dir: Path = VERSIONS_DIR) -> Recipe:
    exact_version(version, "node-tar version")
    package = versions_dir / version / "package.json"
    if not package.is_file() or not package.with_name("package-lock.json").is_file():
        raise UnsupportedVersionError(
            f"node-tar {version}: no committed lock in tools/node-tar/versions/{version}/ "
            "(auto-prepare builds only versions with a committed package-lock.json)"
        )
    dependency = single_dependency(json.loads(package.read_text(encoding="utf-8")))
    if dependency != ("tar", version):
        raise UnsupportedVersionError(
            f"node-tar {version}: committed package.json pins {dependency}"
        )
    return Recipe(
        label=f"node-tar {version}",
        expected=version,
        build=("-f", "tools/node-tar/effect/Dockerfile", "--build-arg", f"TAR_VERSION={version}"),
        check=(
            "--entrypoint",
            "/usr/local/bin/node",
            IMAGE_SLOT,
            "-e",
            "console.log(require('/target/node_modules/tar/package.json').version)",
        ),
    )


def prepare(version: str, image_ref: str, runner: Runner = subprocess.run) -> PreparedImage:
    return ensure_image(recipe(version), image_ref, runner)
