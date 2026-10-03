"""Deterministic USTAR encoding; no source filesystem metadata is consulted."""

import io
import tarfile
from collections.abc import Mapping
from types import MappingProxyType

from inodefence.model import ArchiveCase, EntryType

BUILDER_FORMAT = "ustar-utf8-v1"

_TAR_TYPES = MappingProxyType(
    {
        EntryType.REGULAR: tarfile.REGTYPE,
        EntryType.DIRECTORY: tarfile.DIRTYPE,
        EntryType.HARDLINK: tarfile.LNKTYPE,
        EntryType.SYMLINK: tarfile.SYMTYPE,
    }
)


class _RawPathTarInfo(tarfile.TarInfo):
    def get_info(self) -> dict[str, str | int | bytes | Mapping[str, str]]:
        # TarInfo normally rewrites a directory name's trailing slashes. Keep
        # logical input spelling even there; delegate actual encoding to tarfile.
        info = dict(super().get_info())
        info["name"] = self.name
        return info


def build_tar(case: ArchiveCase) -> bytes:
    """Encode entries in order with strict UTF-8 and fixed zero/empty metadata.

    Unsupported USTAR names/targets fail explicitly rather than being truncated
    or silently promoted to PAX. Path normalization is never performed.
    """
    output = io.BytesIO()
    with tarfile.open(
        fileobj=output, mode="w", format=tarfile.USTAR_FORMAT, encoding="utf-8", errors="strict"
    ) as archive:
        for index, entry in enumerate(case.entries):
            info = _RawPathTarInfo(entry.path)
            info.type = _TAR_TYPES[entry.entry_type]
            info.mode = entry.mode
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            info.linkname = entry.link_target or ""
            info.size = len(entry.content) if entry.content is not None else 0
            try:
                archive.addfile(
                    info, io.BytesIO(entry.content) if entry.content is not None else None
                )
            except (ValueError, UnicodeError) as error:
                raise ValueError(
                    f"entry {index} cannot be represented in USTAR: {error}"
                ) from error
    return output.getvalue()
