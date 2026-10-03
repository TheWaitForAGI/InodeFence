"""Disposable Linux runtime storage, separate from the source bind mount.

This controls harness paths and cleanup. It is not an OS security boundary for
an arbitrary untrusted executable; target adapters must supply that isolation.
"""

import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from inodefence.model.filesystem import validate_observed_path

RUNTIME_BASE = Path("/var/lib/inodefence")


@contextmanager
def open_runtime_directory(path: Path) -> Iterator[int]:
    """Open every directory component with O_NOFOLLOW, including the final one.

    Absolute runtime configuration paths are trusted configuration, not archive
    paths. Reject symlinks rather than resolving them. Concurrent replacement of
    harness-owned directories is outside the initial threat model.
    """
    if sys.platform != "linux":
        raise ValueError("Filesystem runs require the Linux Dev Container")
    if not path.is_absolute() or not path.is_relative_to(RUNTIME_BASE) or ".." in path.parts:
        raise ValueError("runtime directories must be absolute paths within /var/lib/inodefence")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def runtime_root() -> Path:
    """Require an existing, nonsymlink Linux runtime directory."""
    path = Path(os.environ.get("INODEFENCE_RUNTIME_ROOT", str(RUNTIME_BASE)))
    with open_runtime_directory(path):
        return path


@dataclass(frozen=True, slots=True)
class SentinelSpec:
    """A controlled regular file under outside/, with a safe relative name."""

    name: str = "sentinel.txt"
    content: bytes = b"inodefence protected sentinel\n"
    mode: int = 0o600

    def __post_init__(self) -> None:
        validate_observed_path(self.name)
        if self.name == "." or not isinstance(self.content, bytes):
            raise ValueError("sentinel requires a file name and bytes content")
        if type(self.mode) is not int or not 0 <= self.mode <= 0o7777:
            raise ValueError("sentinel mode must be a permission mask")


@dataclass(frozen=True, slots=True)
class RuntimeSandbox:
    root: Path
    extraction_root: Path
    archive_path: Path
    protected_paths: tuple[str, ...]


@contextmanager
def disposable_sandbox(
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
) -> Iterator[RuntimeSandbox]:
    """Create fresh roots and sentinels; clean up even when a run raises.

    TemporaryDirectory uses Python's fd-based, symlink-resistant rmtree on Linux.
    No saved artifacts or extraction results are written back into the source.
    """
    if (
        not isinstance(sentinels, tuple)
        or not sentinels
        or not all(isinstance(spec, SentinelSpec) for spec in sentinels)
    ):
        raise ValueError("at least one SentinelSpec is required in a tuple")
    if len({spec.name for spec in sentinels}) != len(sentinels):
        raise ValueError("sentinel names must be unique")
    with tempfile.TemporaryDirectory(prefix="core-run-", dir=runtime_root()) as temporary:
        root = Path(temporary)
        extract = root / "extract"
        extract.mkdir(mode=0o755)
        (root / "outside").mkdir(mode=0o755)
        (root / "archive").mkdir(mode=0o755)
        for spec in sentinels:
            sentinel = root / "outside" / spec.name
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            with sentinel.open("xb") as stream:
                stream.write(spec.content)
            sentinel.chmod(spec.mode)
        yield RuntimeSandbox(
            root,
            extract,
            root / "archive" / "input.tar",
            tuple(sorted(f"outside/{spec.name}" for spec in sentinels)),
        )
