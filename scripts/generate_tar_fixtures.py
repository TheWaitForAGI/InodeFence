"""Regenerate small, deterministic TAR fixtures without reading host metadata.

Besides the four normal baselines, three oracle-check fixtures reach the default
sentinel outside/sentinel.txt. They validate C0/C1/C2 verdicts only; they are not
seeds and never enter the fuzzing corpus.
"""

from __future__ import annotations

from pathlib import Path

from inodefence.builder import build_tar
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tar"
CASE_NAMES = ("regular-file", "directory", "hardlink", "symlink")
CONTENT = b"hello inodefence"
ORACLE_CASE_NAMES = ("oracle-c0", "oracle-c1", "oracle-c2")
_ORACLE_CASES = {
    # Creates escape.txt at the sandbox root, outside extract/.
    "oracle-c0": ArchiveCase((ArchiveEntry("../escape.txt", EntryType.REGULAR, content=CONTENT),)),
    # An extract/ object that is the sentinel's own inode.
    "oracle-c1": ArchiveCase(
        (ArchiveEntry("alias", EntryType.HARDLINK, link_target="../outside/sentinel.txt"),)
    ),
    # A later regular entry written through an earlier symlink to the sentinel.
    "oracle-c2": ArchiveCase(
        (
            ArchiveEntry(
                "link", EntryType.SYMLINK, link_target="../outside/sentinel.txt", mode=0o777
            ),
            ArchiveEntry("link", EntryType.REGULAR, content=CONTENT),
        )
    ),
}


def baseline_case(case_name: str) -> ArchiveCase:
    """Small normal cases, sharing the core encoding rather than duplicating it."""
    if case_name not in CASE_NAMES:
        raise ValueError(f"unknown baseline case: {case_name}")
    return minimal_seed_corpus()[CASE_NAMES.index(case_name)]


def oracle_case(case_name: str) -> ArchiveCase:
    """Oracle-check inputs; their verdicts depend on an extractor without boundary checks."""
    if case_name not in _ORACLE_CASES:
        raise ValueError(f"unknown oracle case: {case_name}")
    return _ORACLE_CASES[case_name]


def generate_fixtures(destination: Path = FIXTURE_ROOT) -> tuple[Path, ...]:
    """Write USTAR archives with fixed order, modes, and TarInfo's zero/empty metadata."""
    paths = []
    cases = [(name, baseline_case(name)) for name in CASE_NAMES]
    cases += [(name, oracle_case(name)) for name in ORACLE_CASE_NAMES]
    for case_name, case in cases:
        path = destination / case_name / "fixture.tar"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(build_tar(case))
        paths.append(path)
    return tuple(paths)


def main() -> None:
    for path in generate_fixtures():
        print(f"Generated: {path}")


if __name__ == "__main__":
    main()
