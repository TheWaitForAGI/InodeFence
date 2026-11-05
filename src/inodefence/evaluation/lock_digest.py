"""Lock digest of an in-process extraction target (EXP-3 ``targets.<id>.lock_digest``).

A container target is pinned by its image digest. An in-process target (Python
``tarfile`` run as a host subprocess) has no image, so its registration pins the
interpreter and the stdlib module that will run instead::

    lock_digest = "sha256:" + sha256(
        python_version + "\\n" + tarfile_sha256 + "\\n" + uname_sr + "\\n"
    )

where ``python_version`` is the full ``python -VV`` output (not stripped),
``tarfile_sha256`` the hex digest of the running ``tarfile.py`` bytes and
``uname_sr`` the ``uname -sr`` string. The producer (``inodefence.targets``) exposes
the raw material; this module composes the digest the registration gate compares
and the launcher records in the report (top-level ``lock_digest`` next to the raw
``lock_material``). The digest is a freeze-detection proxy, not a full environment
freeze: other stdlib modules, locale and umask are not covered, and filesystem
semantics are host-fixed and shared by every arm.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol


class LockMaterial(Protocol):
    @property
    def python_version(self) -> str: ...
    @property
    def tarfile_sha256(self) -> str: ...
    @property
    def uname_sr(self) -> str: ...


@dataclass(frozen=True, slots=True)
class LockRecord:
    """What the report carries: the digest plus the material it was built from."""

    lock_digest: str
    python_version: str
    tarfile_sha256: str
    uname_sr: str

    def material(self) -> dict[str, str]:
        return {
            "python_version": self.python_version,
            "tarfile_sha256": self.tarfile_sha256,
            "uname_sr": self.uname_sr,
        }


def lock_digest(python_version: str, tarfile_sha256: str, uname_sr: str) -> str:
    """The canonical digest; inputs are used verbatim (no stripping) for reproducibility."""
    for name, value in (
        ("python_version", python_version),
        ("tarfile_sha256", tarfile_sha256),
        ("uname_sr", uname_sr),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"lock material {name} must be a nonempty string")
    payload = f"{python_version}\n{tarfile_sha256}\n{uname_sr}\n".encode()
    return "sha256:" + sha256(payload).hexdigest()


def lock_record(lock: LockMaterial) -> LockRecord:
    """Compose the record from a producer's lock material (e.g. ``PythonTarfileLock``)."""
    return LockRecord(
        lock_digest(lock.python_version, lock.tarfile_sha256, lock.uname_sr),
        lock.python_version,
        lock.tarfile_sha256,
        lock.uname_sr,
    )
