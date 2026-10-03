"""Observe lstat facts without following symlinks or opening special files."""

import hashlib
import os
import stat
from pathlib import Path

from inodefence.model import ObjectSnapshot, ObjectType, SnapshotPhase, StateSnapshot
from inodefence.runtime import open_runtime_directory


class ObservationError(RuntimeError):
    """An incomplete observation must never become an apparent contract pass."""


def _object_type(mode: int) -> ObjectType:
    if stat.S_ISREG(mode):
        return ObjectType.REGULAR
    if stat.S_ISDIR(mode):
        return ObjectType.DIRECTORY
    if stat.S_ISLNK(mode):
        return ObjectType.SYMLINK
    return ObjectType.OTHER


def _digest(directory_fd: int, name: str, metadata: os.stat_result) -> str:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory_fd
    )
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            metadata.st_dev,
            metadata.st_ino,
        ):
            raise ObservationError("object changed while opening for digest")
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        final = os.fstat(stream.fileno())
        if (final.st_size, final.st_mtime_ns, final.st_ctime_ns) != (
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        ):
            raise ObservationError("object changed while reading digest")
        return digest


def _observe(
    relative: str, metadata: os.stat_result, directory_fd: int, name: str
) -> ObjectSnapshot:
    kind = _object_type(metadata.st_mode)
    return ObjectSnapshot(
        path=relative,
        object_type=kind,
        st_dev=metadata.st_dev,
        st_ino=metadata.st_ino,
        st_nlink=metadata.st_nlink,
        mode=stat.S_IMODE(metadata.st_mode),
        size=metadata.st_size,
        uid=metadata.st_uid,
        gid=metadata.st_gid,
        mtime_ns=metadata.st_mtime_ns,
        ctime_ns=metadata.st_ctime_ns,
        symlink_target=os.readlink(name, dir_fd=directory_fd)
        if kind == ObjectType.SYMLINK
        else None,
        content_digest=_digest(directory_fd, name, metadata)
        if kind == ObjectType.REGULAR
        else None,
    )


def capture_state(
    sandbox_root: Path, phase: SnapshotPhase, protected_paths: tuple[str, ...]
) -> StateSnapshot:
    """Capture the entire reachable run tree, including external namespace paths.

    Missing sentinels remain in protected_paths. Permission/read failures raise;
    symlink referents (including dangling ones) are never stat'ed or hashed.
    """
    objects: list[ObjectSnapshot] = []

    def visit(descriptor: int, prefix: str) -> None:
        for name in sorted(os.listdir(descriptor)):
            relative = f"{prefix}/{name}" if prefix else name
            try:
                metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                objects.append(_observe(relative, metadata, descriptor, name))
                if stat.S_ISDIR(metadata.st_mode):
                    child = os.open(
                        name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=descriptor,
                    )
                    try:
                        visit(child, relative)
                    finally:
                        os.close(child)
            except OSError as error:
                raise ObservationError(f"cannot observe {relative}: {error}") from error

    try:
        with open_runtime_directory(sandbox_root) as descriptor:
            objects.append(_observe(".", os.fstat(descriptor), descriptor, "."))
            visit(descriptor, "")
    except OSError as error:
        raise ObservationError(f"cannot open sandbox: {error}") from error
    return StateSnapshot(
        str(sandbox_root), phase, tuple(sorted(objects, key=lambda obj: obj.path)), protected_paths
    )
