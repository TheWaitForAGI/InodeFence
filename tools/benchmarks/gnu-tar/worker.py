"""Contained GNU tar worker restricted to four fixed benign TARs and an empty root."""

import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

PYTHON = Path("/usr/local/bin/python3.12")
TAR = Path("/bin/tar")
PROFILE = Path("/target/profile.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(pairs):
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError("duplicate JSON key")
    return value


def profile() -> dict:
    content = PROFILE.read_bytes()
    value = json.loads(content, object_pairs_hook=unique_object)
    if (
        not isinstance(value, dict)
        or set(value) != {"format", "schema_version", "builder_format", "cases"}
        or value["format"] != "benign-fixtures-v1"
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["builder_format"] != "ustar-utf8-v1"
        or not isinstance(value["cases"], list)
        or len(value["cases"]) != 4
        or content
        != (
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
            )
            + "\n"
        ).encode("ascii")
    ):
        raise ValueError("unsupported/noncanonical benign profile")
    for case in value["cases"]:
        if (
            not isinstance(case, dict)
            or set(case) != {"case_id", "archive_sha256"}
            or any(
                not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{64}", item) is None
                for item in case.values()
            )
        ):
            raise ValueError("profile identity requires SHA-256")
    if len({case["archive_sha256"] for case in value["cases"]}) != 4:
        raise ValueError("benign profile requires four unique TARs")
    return value


def identity() -> dict:
    profile()
    version = (
        subprocess.run((str(TAR), "--version"), capture_output=True, check=True, timeout=5)
        .stdout.decode("ascii")
        .splitlines()[0]
    )
    if version != "tar (GNU tar) 1.34" or platform.python_version() != "3.12.13":
        raise ValueError("unexpected pinned runtime/target version")
    return {
        "python_version": platform.python_version(),
        "tar_version": "1.34",
        "worker_sha256": digest(Path(__file__)),
        "profile_sha256": digest(PROFILE),
        "tar_binary_sha256": digest(TAR.resolve()),
        "python_binary_sha256": digest(PYTHON.resolve()),
    }


def extract(archive: Path, root: Path, expected: dict) -> int:
    if identity() != expected:
        raise RuntimeError("execution identity changed")
    if (
        not archive.is_absolute()
        or not root.is_absolute()
        or root.name != "extract"
        or archive != root.parent / "archive" / "input.tar"
        or archive.is_symlink()
        or root.is_symlink()
        or not root.is_dir()
        or any(root.iterdir())
        or digest(archive) not in {case["archive_sha256"] for case in profile()["cases"]}
    ):
        raise ValueError("requires fixed benign TAR and fresh empty extraction root")
    # stdout/stderr remain target data. Backend containment owns timeout and cleanup.
    return subprocess.run(
        (str(TAR), "--extract", "--file", str(archive), "--directory", str(root)), check=False
    ).returncode


def main() -> int:
    try:
        if sys.argv[1:] == ["--identify"]:
            print(json.dumps(identity(), sort_keys=True, separators=(",", ":")))
            return 0
        if len(sys.argv) != 5 or sys.argv[1] != "--extract":
            raise ValueError("unsupported worker invocation")
        expected = json.loads(sys.argv[4], object_pairs_hook=unique_object)
        return extract(Path(sys.argv[2]), Path(sys.argv[3]), expected)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 3
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
