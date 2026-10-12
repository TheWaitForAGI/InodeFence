"""Run the benign pinned node-tar public-event timing qualification probe."""

import json
import shutil
import subprocess
from pathlib import Path

from inodefence.builder import build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.runtime import disposable_sandbox

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/node-tar/node_modules/tar"
PROBE = ROOT / "tools/node-tar/entry-timing-probe.cjs"


def benign_case() -> ArchiveCase:
    return ArchiveCase(
        (
            ArchiveEntry("regular", EntryType.REGULAR, content=b"first"),
            ArchiveEntry("dir", EntryType.DIRECTORY, mode=0o755),
            ArchiveEntry("hard", EntryType.HARDLINK, link_target="regular"),
            ArchiveEntry("sym", EntryType.SYMLINK, link_target="regular", mode=0o777),
            ArchiveEntry("regular", EntryType.REGULAR, content=b"second"),
        )
    )


def main() -> int:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("node executable is required for the benign timing probe")
    with disposable_sandbox() as sandbox:
        sandbox.archive_path.write_bytes(build_tar(benign_case()))
        completed = subprocess.run(
            (
                node,
                PROBE,
                MODULE,
                sandbox.archive_path,
                sandbox.extraction_root,
            ),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"node-tar timing probe failed: {completed.stderr}")
        events = json.loads(completed.stdout)
    print(json.dumps(events, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
