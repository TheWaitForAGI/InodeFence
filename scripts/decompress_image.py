"""decompress image recipe (target-specific; attached to its adapter on the interface PR).

The original package (``decompress``) and the maintained fork (``@xhmikosr/decompress``) are
different packages, so a request is ``<package>@<X.Y.Z>`` and both parts must match. Supported:
exactly the specs pinned by a committed ``tools/decompress/<role>/package.json`` (single
dependency) with its ``package-lock.json``. Built from ``tools/decompress/Dockerfile`` with
``ROLE=<role>`` (``npm ci --ignore-scripts`` from the committed lock). After the build, the image
is run offline and must report that package name and version. Anything else is refused with the
list of buildable specs; widening it would need a committed, reviewed lock first.
"""

from __future__ import annotations

import json
import re
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
    single_dependency,
)

TOOLS_DIR = REPO_ROOT / "tools" / "decompress"
SPEC = re.compile(
    r"(?P<package>(?:@[a-z0-9][a-z0-9._-]*/)?decompress)@(?P<version>[0-9]+\.[0-9]+\.[0-9]+)"
)


def pinned_specs(tools_dir: Path = TOOLS_DIR) -> dict[str, str]:
    """``<package>@<version>`` -> recipe role, from the committed per-role package files."""
    pinned: dict[str, str] = {}
    for role in sorted(p for p in tools_dir.iterdir() if p.is_dir()):
        manifest = role / "package.json"
        if manifest.is_file() and (role / "package-lock.json").is_file():
            dependency = single_dependency(json.loads(manifest.read_text(encoding="utf-8")))
            if dependency is not None:
                pinned[f"{dependency[0]}@{dependency[1]}"] = role.name
    return pinned


def recipe(spec: str, tools_dir: Path = TOOLS_DIR) -> Recipe:
    match = SPEC.fullmatch(spec)
    if match is None:
        raise UnsupportedVersionError(
            f"decompress version must be <package>@X.Y.Z, e.g. decompress@4.2.1: {spec!r}"
        )
    pinned = pinned_specs(tools_dir)
    if spec not in pinned:
        raise UnsupportedVersionError(
            f"decompress {spec}: not pinned by a committed recipe "
            f"(buildable: {', '.join(sorted(pinned)) or 'none'}); the original package and the "
            "maintained fork are different packages"
        )
    return Recipe(
        label=f"decompress {spec}",
        expected=f"{match['package']} {match['version']}",
        build=("-f", "tools/decompress/Dockerfile", "--build-arg", f"ROLE={pinned[spec]}"),
        check=(
            "--entrypoint",
            "/usr/local/bin/node",
            IMAGE_SLOT,
            "-e",
            "const p=require('/target/package.json');const n=Object.keys(p.dependencies)[0];"
            "console.log(n, require('/target/node_modules/'+n+'/package.json').version)",
        ),
    )


def prepare(spec: str, image_ref: str, runner: Runner = subprocess.run) -> PreparedImage:
    return ensure_image(recipe(spec), image_ref, runner)
