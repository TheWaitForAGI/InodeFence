"""Regenerate four small, deterministic TAR fixtures without reading host metadata."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tar"
CASE_NAMES = ("regular-file", "directory", "hardlink", "symlink")
CONTENT = b"hello inodefence"


def _add_regular(archive: tarfile.TarFile, name: str) -> None:
    entry = tarfile.TarInfo(name)
    entry.mode = 0o644
    entry.size = len(CONTENT)
    archive.addfile(entry, io.BytesIO(CONTENT))


def generate_fixtures(destination: Path = FIXTURE_ROOT) -> tuple[Path, ...]:
    """Write USTAR archives with fixed order, modes, and TarInfo's zero/empty metadata."""
    paths = []
    for case_name in CASE_NAMES:
        path = destination / case_name / "fixture.tar"
        path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as archive:
            if case_name == "directory":
                directory = tarfile.TarInfo("dir/")
                directory.type = tarfile.DIRTYPE
                directory.mode = 0o755
                archive.addfile(directory)
                _add_regular(archive, "dir/a.txt")
            else:
                _add_regular(archive, "a.txt")
                if case_name in {"hardlink", "symlink"}:
                    link = tarfile.TarInfo("b.txt")
                    link.type = tarfile.LNKTYPE if case_name == "hardlink" else tarfile.SYMTYPE
                    link.linkname = "a.txt"
                    link.mode = 0o644 if case_name == "hardlink" else 0o777
                    archive.addfile(link)
        paths.append(path)
    return tuple(paths)


def main() -> None:
    for path in generate_fixtures():
        print(f"Generated: {path}")


if __name__ == "__main__":
    main()
