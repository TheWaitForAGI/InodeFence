from __future__ import annotations

import os
import platform
import sys
import tempfile
from pathlib import Path

RUNTIME_ROOT = Path(os.environ.get("INODEFENCE_RUNTIME_ROOT", "/var/lib/inodefence"))


def setup_problems(runtime_root: Path) -> list[str]:
    """Missing prerequisites, each with the command that fixes it (empty if none)."""
    problems = []
    if sys.version_info[:2] != (3, 12):
        found = f"{sys.version_info[0]}.{sys.version_info[1]}"
        problems.append(
            f"Python 3.12 required, found {found}; "
            "use the Dev Container or run make with PYTHON=python3.12"
        )
    if not runtime_root.is_dir():
        problems.append(
            f"runtime root {runtime_root} does not exist; create it with: "
            f'sudo mkdir -p {runtime_root} && sudo chown "$(id -u):$(id -g)" {runtime_root}'
        )
    return problems


def main() -> None:
    print("=== InodeFence Environment Check ===")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print(f"Python: {platform.python_version()}")
    print(f"Interpreter: {sys.executable}")
    print(f"Runtime root: {RUNTIME_ROOT}")

    problems = setup_problems(RUNTIME_ROOT)
    for problem in problems:
        print(f"ENV-CHECK SETUP: {problem}", file=sys.stderr)
    if problems:
        raise SystemExit(1)

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
