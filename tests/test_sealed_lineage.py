"""#520 D3: reserved ranges and sealed-run lock (design v1.3, W4 PASS). No Docker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import sealed_lineage_lock as tool

from inodefence import sealed_lineage as sl
from inodefence import v2_reservations


@pytest.fixture(autouse=True)
def lock_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home" / "sealed-lineage.json"
    monkeypatch.setenv("INODEFENCE_SEALED_LOCK", str(path))
    return path


def audit_lines() -> list[dict]:
    p = sl.overrides_path()
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


QUAL = sl.Override("RESERVED 고정 입력 점검", "탐색-실행-원장.tsv#509-q3", inputs=5)


def test_reserved_source_pinned_to_reserved_v12() -> None:
    assert v2_reservations.RESERVED_SOURCE[1] == (
        "90017217352b54d9f35454375377c260f0a9e8f83a59d79de1841c46e0a56835"
    )
    assert [r[0] for r in v2_reservations.RESERVED] == ["v2-R-A", "v2-R-B", "v2-R-C"]


def test_no_host_lock_still_refuses_reserved(lock_env: Path) -> None:
    assert not lock_env.exists()
    assert sl.load_lock() is None
    assert sl.sealed_conflict("node-tar", "7.2.0", mode="explore") is not None
    assert sl.sealed_conflict("node-tar", "7.5.23", mode="explore") is None
    assert audit_lines() == []


@pytest.mark.parametrize(
    ("version", "refused"),
    [
        ("7.0.0", True),
        ("7.0.1", True),
        ("7.3.0", True),
        ("7.4.3", True),
        ("7.4.4", False),
        ("7.4.4-rc.1", True),
        ("7.5.23", False),
        ("6.0.0", True),
        ("6.2.1", True),
        ("6.2.2", False),
        ("5.99.0", False),
        ("4.4.0", True),
        ("5.0.9", True),
        ("5.1.0", False),
        ("4.3.9", False),
        ("6.0.0-beta.1", True),
        ("7.0.0-rc.1", True),
        ("4.4.0-alpha", True),
        ("5.1.0-rc.1", True),
        ("6.2.2-rc.1", True),
        ("3.9.9", False),
        ("7.4.3+build.5", True),
    ],
)
def test_range_ends_on_parsed_versions(version: str, refused: bool) -> None:
    got = sl.sealed_conflict("node-tar", version, mode="explore")
    assert (got is not None) is refused


@pytest.mark.parametrize("bad", ["latest", "7.x", "", "v7.2.0", "07.2.0"])
def test_unparseable_version_refused_for_target_with_entries(bad: str) -> None:
    got = sl.sealed_conflict("node-tar", bad, mode="verify", override=QUAL)
    assert got is not None and "정확한 버전" in got.message
    assert audit_lines() == []


@pytest.mark.parametrize(
    ("target", "version"),
    [
        ("decompress", "decompress@4.2.1"),
        ("decompress", "@xhmikosr/decompress@11.1.4"),
        ("python-tarfile", "3.12.4"),
        ("oras-go", "2.5.0"),
    ],
)
def test_other_targets_and_decompress_specs_pass(target: str, version: str) -> None:
    assert sl.sealed_conflict(target, version, mode="explore") is None


def test_override_table_reserved() -> None:
    for mode in ("explore", "replay"):
        assert sl.sealed_conflict("node-tar", "6.1.0", mode=mode, override=QUAL) is not None
    assert sl.sealed_conflict("node-tar", "6.1.0", mode="verify") is not None
    no_ref = sl.Override("사유", "")
    assert sl.sealed_conflict("node-tar", "6.1.0", mode="verify", override=no_ref) is not None
    bad_ref = sl.Override("사유", "원장 행 3")
    assert sl.sealed_conflict("node-tar", "6.1.0", mode="verify", override=bad_ref) is not None
    no_reason = sl.Override("  ", "탐색-실행-원장.tsv#509-q3")
    assert sl.sealed_conflict("node-tar", "6.1.0", mode="verify", override=no_reason) is not None
    assert audit_lines() == []
    assert sl.sealed_conflict("node-tar", "6.1.0", mode="verify", override=QUAL) is None
    (line,) = audit_lines()
    assert line["entry_id"] == "v2-R-B" and line["inputs"] == 5 and line["kind_of_input"] == "fixed"
    assert not {"verdict", "oracle", "violations", "result"} & set(line)


def test_prepare_on_reserved_is_readiness_input() -> None:
    assert sl.sealed_conflict("node-tar", "7.4.0", mode="prepare") is not None
    assert audit_lines() == []
    assert sl.sealed_conflict("node-tar", "7.4.0", mode="prepare", override=QUAL) is None
    (line,) = audit_lines()
    assert line["mode"] == "prepare" and line["inputs"] == 1
    assert line["kind_of_input"] == "readiness"


def test_sealed_run_lock(lock_env: Path) -> None:
    tool.seal(lock_env, "exp9-holdout", "node-tar", ["7.5.30"], "prereg/exp9.md", "ab" * 32)
    assert sl.sealed_conflict("node-tar", "7.5.30", mode="replay") is not None
    assert sl.sealed_conflict("node-tar", "7.5.31", mode="explore") is None
    reason = sl.Override("봉인 중 인프라 점검")
    assert sl.sealed_conflict("node-tar", "7.5.30", mode="explore", override=reason) is None
    (line,) = audit_lines()
    assert line["kind"] == "sealed" and line["entry_id"] == "exp9-holdout"
    tool.release(lock_env, "exp9-holdout")
    assert sl.sealed_conflict("node-tar", "7.5.30", mode="explore") is None


def test_reserved_and_sealed_overlap_needs_both() -> None:
    path = sl.lock_path()
    tool.seal(path, "run-x", "node-tar", ["7.1.0"], "doc", "cd" * 32)
    reason_only = sl.Override("사유")
    assert sl.sealed_conflict("node-tar", "7.1.0", mode="verify", override=reason_only) is not None
    assert audit_lines() == []
    assert sl.sealed_conflict("node-tar", "7.1.0", mode="verify", override=QUAL) is None
    assert {x["kind"] for x in audit_lines()} == {"reserved", "sealed"}


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        json.dumps({"schema": "other/1", "entries": []}),
        json.dumps({"schema": sl.SCHEMA, "entries": [{"id": "x", "target": "node-tar"}]}),
        json.dumps(
            {
                "schema": sl.SCHEMA,
                "entries": [{"id": "x", "target": "node-tar", "versions": ["latest"]}],
            }
        ),
    ],
)
def test_malformed_lock_is_an_error(lock_env: Path, content: str) -> None:
    lock_env.parent.mkdir(parents=True)
    lock_env.write_text(content)
    with pytest.raises(sl.LockError):
        sl.sealed_conflict("node-tar", "7.5.23", mode="explore")


@pytest.mark.parametrize(
    "rows",
    [
        (("bad", "node-tar", "7.4.4", "7.0.0"),),
        (("bad", "node-tar", "7.0", "7.4.4"),),
        (("bad", "node-tar", "7.0.0"),),
    ],
)
def test_broken_reservation_module_is_an_error(monkeypatch: pytest.MonkeyPatch, rows) -> None:
    monkeypatch.setattr(v2_reservations, "RESERVED", rows)
    with pytest.raises(sl.LockError):
        sl.sealed_conflict("node-tar", "7.5.23", mode="explore")


def test_unknown_mode_rejected() -> None:
    with pytest.raises(ValueError):
        sl.sealed_conflict("node-tar", "7.5.23", mode="run")


def _seal(run_id: str, version: str) -> int:
    argv = ["seal", "--run-id", run_id, "--target", "node-tar", "--version", version]
    return tool.main([*argv, "--source-doc", "d", "--source-sha", "ab"])


def _ids() -> list[str]:
    lock = sl.load_lock()
    assert lock is not None
    return [e.id for e in lock.entries]


def test_tool_merge_conflict_and_missing_release() -> None:
    assert _seal("a", "7.5.30") == 0
    assert _seal("a", "7.5.30") == 0  # same content: no-op
    assert _seal("b", "7.5.31") == 0
    assert _seal("a", "7.5.32") == 3  # same id, different content
    assert _ids() == ["a", "b"]
    assert tool.main(["release", "--run-id", "zzz"]) == 3
    assert tool.main(["release", "--run-id", "a"]) == 0
    assert _ids() == ["b"]
