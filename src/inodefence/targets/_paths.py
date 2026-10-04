"""Harness layout validation shared by actual extractor adapters."""

from pathlib import Path

from inodefence.runtime import open_runtime_directory


def validate_run_paths(archive_path: Path, extraction_root: Path) -> None:
    if (
        extraction_root.name != "extract"
        or archive_path.parent.name != "archive"
        or archive_path.parent.parent != extraction_root.parent
    ):
        raise ValueError("target requires a run's archive/ and extract/ layout")
    with open_runtime_directory(extraction_root), open_runtime_directory(archive_path.parent):
        if archive_path.name != "input.tar":
            raise ValueError("target archive must be archive/input.tar")
