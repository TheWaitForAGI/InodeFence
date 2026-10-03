"""Regenerate four small, deterministic TAR fixtures without reading host metadata."""

from __future__ import annotations

from pathlib import Path

from inodefence.builder import build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tar"
CASE_NAMES = ("regular-file", "directory", "hardlink", "symlink")
CONTENT = b"hello inodefence"


def baseline_case(case_name: str) -> ArchiveCase:
    """Small normal cases, sharing the core encoding rather than duplicating it."""
    if case_name not in CASE_NAMES:
        raise ValueError(f"unknown baseline case: {case_name}")
    if case_name == "directory":
        return ArchiveCase(
            (
                ArchiveEntry("dir/", EntryType.DIRECTORY, mode=0o755),
                ArchiveEntry("dir/a.txt", EntryType.REGULAR, content=CONTENT),
            )
        )
    entries = (ArchiveEntry("a.txt", EntryType.REGULAR, content=CONTENT),)
    if case_name in {"hardlink", "symlink"}:
        entries += (
            ArchiveEntry(
                "b.txt",
                EntryType.HARDLINK if case_name == "hardlink" else EntryType.SYMLINK,
                link_target="a.txt",
                mode=0o644 if case_name == "hardlink" else 0o777,
            ),
        )
    return ArchiveCase(entries)


def generate_fixtures(destination: Path = FIXTURE_ROOT) -> tuple[Path, ...]:
    """Write USTAR archives with fixed order, modes, and TarInfo's zero/empty metadata."""
    paths = []
    for case_name in CASE_NAMES:
        path = destination / case_name / "fixture.tar"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(build_tar(baseline_case(case_name)))
        paths.append(path)
    return tuple(paths)


def main() -> None:
    for path in generate_fixtures():
        print(f"Generated: {path}")


if __name__ == "__main__":
    main()
