from __future__ import annotations

import os
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest
from scripts.generate_tar_fixtures import CASE_NAMES, CONTENT, FIXTURE_ROOT, generate_fixtures
from scripts.manual_tar_probe import extract_archive, print_state, runtime_root


def test_regular_file_fixture() -> None:
    with extract_archive(FIXTURE_ROOT / "regular-file" / "fixture.tar") as root:
        path = root / "a.txt"
        assert stat.S_ISREG(path.lstat().st_mode)
        assert path.read_bytes() == b"hello inodefence"
        assert path.stat().st_size == 16
        assert path.stat().st_nlink == 1
        assert sorted(path.name for path in root.iterdir()) == ["a.txt"]


def test_directory_fixture() -> None:
    with extract_archive(FIXTURE_ROOT / "directory" / "fixture.tar") as root:
        assert stat.S_ISDIR((root / "dir").lstat().st_mode)
        assert (root / "dir" / "a.txt").read_bytes() == CONTENT


def test_hardlink_fixture() -> None:
    with extract_archive(FIXTURE_ROOT / "hardlink" / "fixture.tar") as root:
        first = (root / "a.txt").lstat()
        second = (root / "b.txt").lstat()
        assert stat.S_ISREG(first.st_mode)
        assert stat.S_ISREG(second.st_mode)
        assert (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)
        assert first.st_nlink == second.st_nlink >= 2
        assert (root / "b.txt").read_bytes() == CONTENT


def test_symlink_fixture() -> None:
    with extract_archive(FIXTURE_ROOT / "symlink" / "fixture.tar") as root:
        link = root / "b.txt"
        assert link.is_symlink()
        assert os.readlink(link) == "a.txt"
        first = (root / "a.txt").lstat()
        second = link.lstat()
        assert (first.st_dev, first.st_ino) != (second.st_dev, second.st_ino)
        assert (link.stat().st_dev, link.stat().st_ino) == (first.st_dev, first.st_ino)
        assert link.read_bytes() == CONTENT


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_archive_entries(case_name: str) -> None:
    with tarfile.open(FIXTURE_ROOT / case_name / "fixture.tar", "r:") as archive:
        entries = archive.getmembers()
        if case_name == "directory":
            assert [entry.name for entry in entries] == ["dir", "dir/a.txt"]
            assert entries[0].isdir()
            assert entries[1].isreg()
        else:
            names = ["a.txt"] if case_name == "regular-file" else ["a.txt", "b.txt"]
            assert [entry.name for entry in entries] == names
            assert entries[0].isreg()
            if case_name == "hardlink":
                assert entries[1].islnk()
                assert entries[1].linkname == "a.txt"
            elif case_name == "symlink":
                assert entries[1].issym()
                assert entries[1].linkname == "a.txt"
        for entry in entries:
            assert (entry.mtime, entry.uid, entry.gid) == (0, 0, 0)
            assert (entry.uname, entry.gname) == ("", "")


def test_fixture_regeneration_is_byte_identical() -> None:
    with tempfile.TemporaryDirectory(prefix="tar-fixtures-", dir=runtime_root()) as temporary:
        destination = Path(temporary)
        generated = generate_fixtures(destination)
        first_run = {path.relative_to(destination): path.read_bytes() for path in generated}
        for path in generate_fixtures(destination):
            relative = path.relative_to(destination)
            assert path.read_bytes() == first_run[relative]
            assert path.read_bytes() == (FIXTURE_ROOT / relative).read_bytes()


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_probe_reports_filesystem_metadata(
    case_name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with extract_archive(FIXTURE_ROOT / case_name / "fixture.tar") as root:
        print_state(root)
        output = capsys.readouterr().out
        for field in (
            "path",
            "type",
            "st_dev",
            "st_ino",
            "st_nlink",
            "mode",
            "size",
            "symlink_target",
        ):
            assert f"{field}:" in output
        if case_name == "hardlink":
            assert "same_object_as: a.txt" in output
        if case_name == "symlink":
            assert "type: symlink" in output
            assert "size: 5" in output
            assert "symlink_target: a.txt" in output
        if case_name == "directory":
            assert "path: dir\ntype: directory" in output
            assert "path: dir/a.txt\ntype: regular" in output
        assert root.is_relative_to(runtime_root())
    assert not root.exists()


def test_probe_cli() -> None:
    script = FIXTURE_ROOT.parents[2] / "scripts" / "manual_tar_probe.py"
    result = subprocess.run(
        [sys.executable, str(script), str(FIXTURE_ROOT / "hardlink" / "fixture.tar")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "extractor: Python tarfile, filter=data" in result.stdout
    assert "same_object_as: a.txt" in result.stdout
