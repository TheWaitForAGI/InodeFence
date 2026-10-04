"""Exact-lock Node target build contexts, separate from all evaluation runs."""

import argparse
import base64
import os
import re
import subprocess
import tempfile
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from inodefence.model.provenance import SourceProvenance
from inodefence.provenance import capture_source

from .encoding import decode, json_bytes, object_fields, read_json
from .verify import _digest, _read_file

NODE_VERSION = "22.22.0"
NODE_BASE = (
    "node:22.22.0-bookworm-slim@sha256:"
    "dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94"
)
RUNTIME_BASE = (
    "gcr.io/distroless/cc-debian12:nonroot@sha256:"
    "9dac0a79194e45a7da0158a9c6da57b217585af0786db3845d1f0ec1a0dd182f"
)
_FILES = ("Dockerfile", "package.json", "package-lock.json", "worker.cjs")
_FIELDS = {
    "format",
    "schema_version",
    "tar_version",
    "node_version",
    "node_base",
    "runtime_base",
    "source",
    "files_sha256",
}


def _version(value: object) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(
            r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?",
            value,
        )
        is None
    ):
        raise ValueError("an exact package release is required; no range/tag/latest")
    if "-" in value:
        for identifier in value.split("-", 1)[1].split("."):
            if not identifier or (
                identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0")
            ):
                raise ValueError("invalid exact prerelease identifier")
    return value


def _lock(content: bytes) -> tuple[str, dict]:
    if b"\r" in content or not content.endswith(b"\n"):
        raise ValueError("exact lockfile must use LF and a final newline")
    lock = read_json(content)
    if (
        not isinstance(lock, dict)
        or type(lock.get("lockfileVersion")) is not int
        or lock["lockfileVersion"] != 3
        or lock.get("requires") is not True
        or not isinstance(lock.get("packages"), dict)
    ):
        raise ValueError("complete npm lockfile v3 required")
    packages = lock["packages"]
    root = packages.get("")
    if (
        not isinstance(root, dict)
        or not isinstance(root.get("name"), str)
        or not root["name"]
        or not isinstance(root.get("dependencies"), dict)
        or set(root.get("dependencies", {})) != {"tar"}
        or root.get("name") != lock.get("name")
        or root.get("version") != lock.get("version")
    ):
        raise ValueError("root lock metadata requires exactly the tar dependency")
    _version(root.get("version"))
    version = _version(root["dependencies"]["tar"])
    package = packages.get("node_modules/tar")
    if (
        not isinstance(package, dict)
        or package.get("version") != version
        or package.get("resolved") != f"https://registry.npmjs.org/tar/-/tar-{version}.tgz"
    ):
        raise ValueError("root tar release differs from resolved lock version")
    for name, item in packages.items():
        if not name:
            continue
        if (
            not isinstance(name, str)
            or not name.startswith("node_modules/")
            or any(part in ("", ".", "..") for part in name.split("/"))
            or not isinstance(item, dict)
            or item.get("link")
        ):
            raise ValueError("host-local/link dependencies are forbidden")
        _version(item.get("version"))
        if not isinstance(item.get("resolved"), str) or not item["resolved"].startswith(
            "https://registry.npmjs.org/"
        ):
            raise ValueError("all installed dependencies must resolve to the official registry")
        integrity = item.get("integrity")
        if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
            raise ValueError("every resolved dependency requires SHA-512 integrity")
        encoded = integrity.removeprefix("sha512-")
        digest = base64.b64decode(encoded, validate=True)
        if len(digest) != 64 or base64.b64encode(digest).decode("ascii") != encoded:
            raise ValueError("noncanonical package integrity")
    return version, {
        "name": root["name"],
        "version": root["version"],
        "private": True,
        "dependencies": {"tar": version},
    }


def _dockerfile(version: str) -> bytes:
    return (
        f"FROM {NODE_BASE} AS dependencies\n"
        "WORKDIR /target\n"
        "COPY package.json package-lock.json ./\n"
        "RUN npm ci --ignore-scripts --engine-strict --no-audit --no-fund\n"
        f'RUN test "$(node --version)" = "v{NODE_VERSION}" && '
        "node -e \"if(require('./node_modules/tar/package.json').version !== "
        f"'{version}') process.exit(1)\"\n"
        f"FROM {RUNTIME_BASE}\n"
        "COPY --from=dependencies /usr/local/bin/node /usr/local/bin/node\n"
        "COPY --from=dependencies /target/node_modules /target/node_modules\n"
        "COPY --from=dependencies /target/package-lock.json /target/package-lock.json\n"
        "COPY worker.cjs /target/worker.cjs\n"
        "USER 1000:1000\n"
        'ENTRYPOINT ["/usr/local/bin/node", "/target/worker.cjs"]\n'
    ).encode("ascii")


def _new_file(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def prepare_node_release(lockfile: Path, destination: Path, *, repository: Path) -> dict:
    """Use a supplied exact lock, one source worker and common immutable runtime pins.

    No npm resolution/install occurs on the host. This does not execute archives.
    Existing contexts are never overwritten. Metadata is the completion marker;
    partial contexts fail validation and are left available for diagnostics.
    """
    lock_bytes = _read_file(lockfile)
    version, package = _lock(lock_bytes)
    worker = _read_file(repository / "src/inodefence/targets/_node_worker.cjs")
    if b"\r" in worker:
        raise ValueError("source worker must use LF")
    source = capture_source(repository)
    files = {
        "Dockerfile": _dockerfile(version),
        "package.json": json_bytes(package) + b"\n",
        "package-lock.json": lock_bytes,
        "worker.cjs": worker,
    }
    manifest = {
        "format": "inodefence-node-packaging",
        "schema_version": 1,
        "tar_version": version,
        "node_version": NODE_VERSION,
        "node_base": NODE_BASE,
        "runtime_base": RUNTIME_BASE,
        "source": asdict(source),
        "files_sha256": {name: sha256(content).hexdigest() for name, content in files.items()},
    }
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        _new_file(destination / name, content)
    _new_file(destination / "packaging.json", json_bytes(manifest) + b"\n")
    return validate_node_release(destination)


def validate_node_release(directory: Path) -> dict:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("expected a prepared build directory")
    if not {path.name for path in directory.iterdir()} <= {*_FILES, "packaging.json", "build.json"}:
        raise ValueError("unexpected files may not enter the Docker build context")
    manifest = object_fields(read_json(_read_file(directory / "packaging.json")), _FIELDS)
    if (
        manifest["format"] != "inodefence-node-packaging"
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["node_version"] != NODE_VERSION
        or manifest["node_base"] != NODE_BASE
        or manifest["runtime_base"] != RUNTIME_BASE
    ):
        raise ValueError("unsupported packaging/runtime pin")
    hashes = object_fields(manifest["files_sha256"], set(_FILES))
    decode(SourceProvenance, manifest["source"])
    for name in _FILES:
        if sha256(_read_file(directory / name)).hexdigest() != _digest(hashes[name]):
            raise ValueError(f"build context checksum mismatch: {name}")
    version, package = _lock(_read_file(directory / "package-lock.json"))
    if (
        version != manifest["tar_version"]
        or _read_file(directory / "package.json") != json_bytes(package) + b"\n"
        or _read_file(directory / "Dockerfile") != _dockerfile(version)
    ):
        raise ValueError("build contract differs from pinned package/runtime")
    return manifest


def build_node_release(directory: Path, *, docker_context: str) -> dict:
    """Build then record the immutable inspected image ID; never execute archives."""
    manifest = validate_node_release(directory)
    if (directory / "build.json").exists() or (directory / "build.json").is_symlink():
        raise FileExistsError(directory / "build.json")
    with tempfile.TemporaryDirectory(prefix="inodefence-node-build-") as temporary:
        iidfile = Path(temporary) / "image-id"
        command = (
            "docker",
            "--context",
            docker_context,
            "build",
            "--iidfile",
            str(iidfile),
            str(directory),
        )
        completed = subprocess.run(command, capture_output=True, check=True)
        image_id = iidfile.read_text(encoding="ascii").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise ValueError("builder did not produce an immutable image ID")
    inspected = subprocess.run(
        ("docker", "--context", docker_context, "image", "inspect", image_id),
        capture_output=True,
        check=True,
    )
    image = read_json(inspected.stdout)
    if (
        not isinstance(image, list)
        or len(image) != 1
        or not isinstance(image[0], dict)
        or image[0].get("Id") != image_id
    ):
        raise ValueError("built image identity differs from inspection")
    if validate_node_release(directory) != manifest:
        raise ValueError("build inputs changed during execution")
    record = {
        "format": "inodefence-node-image-build",
        "schema_version": 1,
        "image_id": image_id,
        "image_architecture": image[0]["Architecture"],
        "packaging_sha256": sha256(_read_file(directory / "packaging.json")).hexdigest(),
        "tar_version": manifest["tar_version"],
        "node_version": NODE_VERSION,
        "files_sha256": manifest["files_sha256"],
        "stdout": completed.stdout.decode("utf-8", "surrogateescape"),
        "stderr": completed.stderr.decode("utf-8", "surrogateescape"),
    }
    _new_file(directory / "build.json", json_bytes(record) + b"\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("lockfile", type=Path)
    prepare.add_argument("destination", type=Path)
    prepare.add_argument("--repository", required=True, type=Path)
    build = subparsers.add_parser("build")
    build.add_argument("directory", type=Path)
    build.add_argument("--docker-context", required=True)
    args = parser.parse_args()
    value = (
        prepare_node_release(args.lockfile, args.destination, repository=args.repository)
        if args.operation == "prepare"
        else build_node_release(args.directory, docker_context=args.docker_context)
    )
    print(json_bytes(value).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
