"""Host Ledger (scripts/host_ledger.py): one host file, atomic, no contents, honest remote state."""

import json
import subprocess
from pathlib import Path

import pytest
from scripts import host_ledger as ledger


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    _git(work, "config", "user.email", "t@example.invalid")
    _git(work, "config", "user.name", "t")
    (work / "a.txt").write_text("a\n")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-q", "-m", "a")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "-u", "origin", "main")
    return work, remote


def test_parse_status_keeps_code_and_path_and_rename_origin() -> None:
    raw = " M src/x.py\0R  new.py\0old.py\0?? notes.txt\0"
    assert ledger.parse_status(raw) == [
        {"status": " M", "path": "src/x.py"},
        {"status": "R ", "path": "new.py", "from": "old.py"},
        {"status": "??", "path": "notes.txt"},
    ]


def test_parse_worktrees_branch_and_detached() -> None:
    raw = "worktree /a\nHEAD 1111\nbranch refs/heads/main\n\nworktree /b\nHEAD 2222\ndetached\n"
    assert ledger.parse_worktrees(raw) == [
        {"path": "/a", "head": "1111", "branch": "main", "detached": False},
        {"path": "/b", "head": "2222", "branch": None, "detached": True},
    ]


def test_records_head_remote_unpushed_and_dirty_paths_without_content(
    repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    work, _ = repo
    pushed = _git(work, "rev-parse", "HEAD")
    (work / "b.txt").write_text("b\n")
    _git(work, "add", "b.txt")
    _git(work, "commit", "-q", "-m", "b")
    (work / "a.txt").write_text("TOP-SECRET-CONTENT\n")
    (work / "new.txt").write_text("TOP-SECRET-CONTENT\n")
    monkeypatch.setenv("GH_TOKEN", "TOKEN-VALUE-MUST-NOT-APPEAR")

    record = ledger.build_ledger("HOST4", [work], check_pr=False)
    text = json.dumps(record)
    assert "TOP-SECRET-CONTENT" not in text
    assert "TOKEN-VALUE-MUST-NOT-APPEAR" not in text

    (repo_record,) = record["repositories"]
    assert repo_record["remote_base"]["status"] == "ok"
    assert repo_record["remote_base"]["sha"] == pushed
    (worktree,) = repo_record["worktrees"]
    assert worktree["branch"] == "main"
    assert worktree["head"] == _git(work, "rev-parse", "HEAD")
    assert worktree["upstream"] == "origin/main"
    assert worktree["upstream_sha"] == pushed
    assert worktree["unpushed_commits"] == 1
    assert {(e["status"], e["path"]) for e in worktree["uncommitted"]} == {
        (" M", "a.txt"),
        ("??", "new.txt"),
    }


def test_unreachable_remote_is_recorded_as_failed_never_as_a_sha(
    repo: tuple[Path, Path],
) -> None:
    work, remote = repo
    remote.rename(remote.with_suffix(".gone"))
    record = ledger.build_ledger("HOST4", [work], check_pr=False)
    base = record["repositories"][0]["remote_base"]
    assert base["status"] == ledger.REMOTE_FAILED
    assert "sha" not in base
    assert base["checked_at"]


def test_writes_only_its_own_host_file_atomically(tmp_path: Path) -> None:
    other = tmp_path / "HOST1.json"
    other.write_text("keep me\n")
    ledger.write_ledger({"host_id": "HOST4", "x": 1}, tmp_path)
    ledger.write_ledger({"host_id": "HOST4", "x": 2}, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["HOST1.json", "HOST4.json"]
    assert other.read_text() == "keep me\n"
    assert json.loads((tmp_path / "HOST4.json").read_text())["x"] == 2


@pytest.mark.parametrize("host_id", ["../HOST1", "HOST4/x", "", ".hidden"])
def test_host_id_cannot_name_another_path(tmp_path: Path, host_id: str) -> None:
    with pytest.raises(ValueError):
        ledger.write_ledger({"host_id": host_id}, tmp_path)


def test_missing_out_dir_warns_and_uses_local_fallback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "Drive-not-mounted" / "host-ledger"
    fallback = tmp_path / "local"
    assert ledger.write_with_fallback({"host_id": "HOST4"}, missing, fallback, False) == 0
    assert not missing.exists()
    written = json.loads((fallback / "HOST4.json").read_text())
    assert written["destination"] == "fallback"
    assert "does not exist" in written["primary_problem"]
    assert "WARNING" in capsys.readouterr().err


def test_expect_mount_rejects_a_directory_on_the_root_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unmounted = tmp_path / "g"
    unmounted.mkdir()
    monkeypatch.setattr(ledger, "mount_point", lambda path: Path("/"))
    fallback = tmp_path / "local"
    assert ledger.write_with_fallback({"host_id": "HOST4"}, unmounted, fallback, True) == 0
    assert list(unmounted.iterdir()) == []
    assert json.loads((fallback / "HOST4.json").read_text())["destination"] == "fallback"


def test_primary_write_and_failure_of_both_still_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ledger.write_with_fallback({"host_id": "HOST4"}, tmp_path, tmp_path / "f", False) == 0
    assert json.loads((tmp_path / "HOST4.json").read_text())["destination"] == "primary"
    blocker = tmp_path / "file"
    blocker.write_text("")
    assert (
        ledger.write_with_fallback({"host_id": "HOST4"}, tmp_path / "no", blocker / "x", False) == 0
    )
    assert "fallback not written either" in capsys.readouterr().err


def test_main_requires_a_plain_host_id(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        ledger.main(["--host-id", "../x", "--out-dir", str(tmp_path), "--no-remote", "--no-pr"])
