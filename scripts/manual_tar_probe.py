"""Extract a small baseline TAR in the Linux runtime and print its filesystem state."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

RUNTIME_BASE = Path("/var/lib/inodefence")


def runtime_root() -> Path:
    """Require an existing Linux runtime directory within /var/lib/inodefence."""
    if sys.platform != "linux":
        raise ValueError("Run this probe in the Linux Dev Container.")
    root = Path(os.environ.get("INODEFENCE_RUNTIME_ROOT", str(RUNTIME_BASE)))
    if not root.is_absolute():
        raise ValueError("INODEFENCE_RUNTIME_ROOT must be an absolute path.")
    root = root.resolve(strict=True)
    if not root.is_relative_to(RUNTIME_BASE) or not root.is_dir():
        raise ValueError("INODEFENCE_RUNTIME_ROOT must be a directory within /var/lib/inodefence.")
    return root


@contextmanager
def extract_archive(archive_path: Path) -> Iterator[Path]:
    """Use a fresh disposable sandbox and Python's data extraction filter."""
    with tempfile.TemporaryDirectory(prefix="tar-probe-", dir=runtime_root()) as temporary:
        root = Path(temporary) / "extract"
        root.mkdir()
        with tarfile.open(archive_path, "r:") as archive:
            archive.extractall(root, filter="data")
        yield root


def _file_type(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "regular"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "other"


def print_state(root: Path) -> None:
    """Observe entries with lstat; never descend through symlinks."""
    paths = []
    for directory, directories, files in os.walk(root, followlinks=False):
        paths.extend(Path(directory) / name for name in directories + files)

    regular_objects: dict[tuple[int, int], str] = {}
    for path in sorted(paths, key=lambda path: path.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        file_type = _file_type(metadata.st_mode)
        print(f"path: {relative}")
        print(f"type: {file_type}")
        print(f"st_dev: {metadata.st_dev}")
        print(f"st_ino: {metadata.st_ino}")
        print(f"st_nlink: {metadata.st_nlink}")
        print(f"mode: {stat.S_IMODE(metadata.st_mode):04o}")
        print(f"size: {metadata.st_size}")
        print(f"symlink_target: {os.readlink(path) if file_type == 'symlink' else '-'}")
        if file_type == "regular":
            identity = (metadata.st_dev, metadata.st_ino)
            print(f"same_object_as: {regular_objects.get(identity, '-')}")
            regular_objects.setdefault(identity, relative)
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Uncompressed baseline TAR to inspect")
    arguments = parser.parse_args()
    try:
        with extract_archive(arguments.archive) as root:
            print(f"archive: {arguments.archive.resolve()}")
            print(f"extraction_root: {root} (removed after the probe)")
            print("extractor: Python tarfile, filter=data")
            print()
            print_state(root)
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(1, f"Probe failed: {error}\n")


if __name__ == "__main__":
    main()
