"""Pinned fixed-benign GNU tar build context; independent of all research runs."""

import argparse
import os
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.model.provenance import SourceProvenance
from inodefence.provenance import capture_source
from inodefence.replay.benign import benign_replay_cases

from .encoding import decode, json_bytes, object_fields, read_json
from .verify import _digest, _read_file

BASE = (
    "python:3.12.13-slim-bookworm@sha256:"
    "4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2"
)
FILES = ("Dockerfile", "worker.py", "profile.json")


def _new_file(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def benign_profile_bytes() -> bytes:
    return (
        json_bytes(
            {
                "format": "benign-fixtures-v1",
                "schema_version": 1,
                "builder_format": BUILDER_FORMAT,
                "cases": [
                    {"case_id": case.case_id, "archive_sha256": sha256(build_tar(case)).hexdigest()}
                    for case in benign_replay_cases()
                ],
            }
        )
        + b"\n"
    )


def _dockerfile() -> bytes:
    return (
        f"FROM {BASE}\n"
        "COPY worker.py profile.json /target/\n"
        "RUN /usr/local/bin/python3.12 /target/worker.py --identify\n"
        "USER 1000:1000\n"
        'ENTRYPOINT ["/usr/local/bin/python3.12", "/target/worker.py"]\n'
    ).encode("ascii")


def worker_bytes(repository: Path) -> bytes:
    return _read_file(repository / "tools/benchmarks/gnu-tar/worker.py")


def prepare_gnu_benign(destination: Path, *, repository: Path) -> dict:
    files = {
        "Dockerfile": _dockerfile(),
        "worker.py": worker_bytes(repository),
        "profile.json": benign_profile_bytes(),
    }
    manifest = {
        "format": "inodefence-gnu-benign-packaging",
        "schema_version": 1,
        "base": BASE,
        "python_version": "3.12.13",
        "tar_version": "1.34",
        "source": asdict(capture_source(repository)),
        "files_sha256": {name: sha256(value).hexdigest() for name, value in files.items()},
    }
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        _new_file(destination / name, content)
    _new_file(destination / "packaging.json", json_bytes(manifest) + b"\n")
    return validate_gnu_benign(destination, repository=repository)


def validate_gnu_benign(directory: Path, *, repository: Path) -> dict:
    if (
        directory.is_symlink()
        or not directory.is_dir()
        or {path.name for path in directory.iterdir()} != {*FILES, "packaging.json"}
    ):
        raise ValueError("expected exact completed GNU benign build context")
    content = _read_file(directory / "packaging.json")
    manifest = object_fields(
        read_json(content),
        {
            "format",
            "schema_version",
            "base",
            "python_version",
            "tar_version",
            "source",
            "files_sha256",
        },
    )
    if (
        content != json_bytes(manifest) + b"\n"
        or manifest["format"] != "inodefence-gnu-benign-packaging"
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["base"] != BASE
        or manifest["python_version"] != "3.12.13"
        or manifest["tar_version"] != "1.34"
    ):
        raise ValueError("unsupported packaging/runtime pin")
    decode(SourceProvenance, manifest["source"])
    hashes = object_fields(manifest["files_sha256"], set(FILES))
    expected = {
        "Dockerfile": _dockerfile(),
        "worker.py": worker_bytes(repository),
        "profile.json": benign_profile_bytes(),
    }
    for name in FILES:
        actual = _read_file(directory / name)
        if sha256(actual).hexdigest() != _digest(hashes[name]) or actual != expected[name]:
            raise ValueError(f"GNU build context differs from trusted fixed profile: {name}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "validate"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--repository", type=Path, required=True)
    args = parser.parse_args()
    value = (prepare_gnu_benign if args.operation == "prepare" else validate_gnu_benign)(
        args.directory, repository=args.repository
    )
    print(json_bytes(value).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
