"""Run the real effect producer on the locked node-tar for the two silent-exit shapes.

These are the input shapes that aborted native demo runs (LOG 2026-10-24): node-tar
dropping an entry with no filesystem work, and node-tar never settling tar.x(). Both
must now end in one terminal frame instead of a success exit with missing evidence.
Needs `node` and `make target-tools` (tools/node-tar/node_modules); skipped otherwise.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from inodefence.builder import build_tar
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType

REPO = Path(__file__).resolve().parents[1]
PRODUCER = REPO / "src" / "inodefence" / "targets" / "_node_effect_producer.cjs"
MODULE = REPO / "tools" / "node-tar" / "node_modules" / "tar"
LOCK = REPO / "tools" / "node-tar" / "package-lock.json"
NODE = shutil.which("node")
EVENT_BOUND = 256  # MAX_EVENT_BOUND of the producer and NodeTarEffectTarget

pytestmark = pytest.mark.skipif(
    NODE is None or not (MODULE / "package.json").exists(),
    reason="needs node and the locked node-tar module (make target-tools)",
)


@pytest.fixture(scope="module")
def identity() -> dict[str, str]:
    assert NODE is not None
    completed = subprocess.run(
        [NODE, str(PRODUCER), "--identify", str(MODULE), str(LOCK)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(completed.stdout)


def run_producer(case: ArchiveCase, identity: dict[str, str], sandbox: Path):
    assert NODE is not None
    archive = sandbox / "archive" / "input.tar"
    extract = sandbox / "extract"
    archive.parent.mkdir(parents=True)
    extract.mkdir()
    archive.write_bytes(build_tar(case))
    completed = subprocess.run(
        [
            NODE,
            str(PRODUCER),
            str(MODULE),
            str(LOCK),
            str(archive),
            str(extract),
            "full",
            str(EVENT_BOUND),
            identity["node_version"],
            identity["tar_version"],
            identity["producer_sha256"],
            identity["package_lock_sha256"],
            identity["package_entrypoint_sha256"],
            identity["unpack_sha256"],
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    raw = completed.stdout
    assert raw.endswith(b"\n") and b"\n" not in raw[:-1], "exactly one LF-terminated frame"
    return completed.returncode, json.loads(raw), completed.stderr.decode()


def lifecycle_by_entry(frame: dict) -> dict[int, dict[str, dict]]:
    grouped: dict[int, dict[str, dict]] = {}
    for record in frame["records"]:
        if record["record_type"] == "lifecycle":
            grouped.setdefault(record["entry"]["ordinal"], {})[record["kind"]] = record
    return grouped


def test_regular_file_still_succeeds_with_full_lifecycle(identity, tmp_path: Path) -> None:
    case = ArchiveCase((ArchiveEntry("a.txt", EntryType.REGULAR, content=b"hello"),))

    returncode, frame, _ = run_producer(case, identity, tmp_path / "sandbox")

    assert returncode == 0
    assert frame["target"]["outcome"] == "success" and frame["target"]["error"] is None
    kinds = lifecycle_by_entry(frame)[0]
    assert set(kinds) == {"read", "effect_work_started", "effect_work_settled"}
    assert all(record["success"] for record in kinds.values())
    assert (tmp_path / "sandbox" / "extract" / "a.txt").read_bytes() == b"hello"


def test_entry_dropped_by_check_path_is_recorded_not_missing(identity, tmp_path: Path) -> None:
    """A link whose path resolves to the extraction root: node-tar drops it silently."""
    case = ArchiveCase(
        (
            ArchiveEntry("./.", EntryType.HARDLINK, link_target="a.txt"),
            ArchiveEntry("a.txt", EntryType.REGULAR, content=b"x"),
            ArchiveEntry("b.txt", EntryType.SYMLINK, link_target="a.txt"),
        )
    )

    returncode, frame, _ = run_producer(case, identity, tmp_path / "sandbox")

    assert returncode == 0
    assert frame["target"]["outcome"] == "success"
    grouped = lifecycle_by_entry(frame)
    assert set(grouped) == {0, 1, 2}
    for ordinal in (0, 1, 2):
        assert set(grouped[ordinal]) == {"read", "effect_work_started", "effect_work_settled"}
    dropped = grouped[0]
    assert dropped["read"]["success"] is True
    for kind in ("effect_work_started", "effect_work_settled"):
        assert dropped[kind]["success"] is False
        assert dropped[kind]["error"]["code"] == "TAR_ENTRY_SKIPPED"
    assert all(grouped[1][kind]["success"] for kind in grouped[1])
    # No filesystem operation was ever attributed to the dropped entry.
    assert not any(
        record["record_type"] != "lifecycle" and record.get("entry", {}).get("ordinal") == 0
        for record in frame["records"]
    )


def test_never_settling_extraction_ends_as_failed_frame(identity, tmp_path: Path) -> None:
    """A symlink whose target is an ancestor of its own path: tar.x() never settles."""
    case = ArchiveCase(
        (
            ArchiveEntry("dir/a.txt", EntryType.REGULAR, content=b"x"),
            ArchiveEntry("dir/", EntryType.DIRECTORY),
            ArchiveEntry("dir/a.txt", EntryType.SYMLINK, link_target="dir/"),
        )
    )

    returncode, frame, stderr = run_producer(case, identity, tmp_path / "sandbox")

    assert returncode == 1
    assert frame["target"]["outcome"] == "failed"
    assert frame["target"]["error"]["code"] == "TARGET_NEVER_SETTLED"
    assert "TARGET_NEVER_SETTLED" in stderr
    assert frame["terminal"]["flush"] == "synchronous_stdout_write"
    # The entries were read; the unsettled one never reached filesystem work.
    grouped = lifecycle_by_entry(frame)
    assert set(grouped) == {0, 1, 2}
    assert "read" in grouped[2]
