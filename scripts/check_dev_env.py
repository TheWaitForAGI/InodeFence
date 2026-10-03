from __future__ import annotations

import os
import platform
import sys
import tempfile
from pathlib import Path

RUNTIME_ROOT = Path(os.environ.get("INODEFENCE_RUNTIME_ROOT", "/var/lib/inodefence"))


def main() -> None:
    print("=== InodeFence Environment Check ===")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print(f"Python: {platform.python_version()}")
    print(f"Interpreter: {sys.executable}")
    print(f"Runtime root: {RUNTIME_ROOT}")

    assert sys.version_info[:2] == (3, 12)
    assert RUNTIME_ROOT.exists()
    assert RUNTIME_ROOT.is_dir()

    with tempfile.TemporaryDirectory(dir=RUNTIME_ROOT) as temp_dir:
        root = Path(temp_dir)
        outside = root / "outside"
        extract = root / "extract"

        outside.mkdir()
        extract.mkdir()

        sentinel = outside / "sentinel.txt"
        hardlink = extract / "hardlink.txt"
        symlink = extract / "symlink.txt"

        sentinel.write_text("sentinel\n")

        os.link(sentinel, hardlink)
        os.symlink("../outside/sentinel.txt", symlink)

        sentinel_stat = sentinel.stat()
        hardlink_stat = hardlink.stat()

        assert sentinel_stat.st_dev == hardlink_stat.st_dev
        assert sentinel_stat.st_ino == hardlink_stat.st_ino
        assert sentinel_stat.st_nlink >= 2
        assert symlink.is_symlink()

        hardlink.write_text("modified-through-hardlink\n")

        assert sentinel.read_text() == "modified-through-hardlink\n"

        print(f"Hardlink device: {sentinel_stat.st_dev}")
        print(f"Hardlink inode: {sentinel_stat.st_ino}")
        print(f"Link count: {sentinel_stat.st_nlink}")
        print("Hardlink semantics: PASS")
        print("Symlink semantics: PASS")
        print("Shared-object effect: PASS")

    print("Environment check: PASS")


if __name__ == "__main__":
    main()
