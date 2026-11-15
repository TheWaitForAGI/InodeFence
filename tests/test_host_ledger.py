"""Host Ledger (scripts/host_ledger.py): local first, drive copy only on a mounted drive, honest."""

import json
import subprocess
from pathlib import Path

import pytest
from scripts import host_ledger as ledger

DRVFS = "248 170 0:125 / {point} rw,relatime - 9p G: rw,aname=drvfs;path=G:\n"
ROOT_EXT4 = "1 0 8:1 / / rw,relatime - ext4 /dev/sdd rw\n"


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


def test_records_every_worktree_head_remote_unpushed_and_dirty_paths_without_content(
    repo: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work, _ = repo
    pushed = _git(work, "rev-parse", "HEAD")
    _git(work, "worktree", "add", "-q", "-b", "side", str(tmp_path / "wt2"))
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
    assert record["observed_at"]

    (repo_record,) = record["repositories"]
    assert repo_record["remote_base"]["status"] == "ok"
    assert repo_record["remote_base"]["sha"] == pushed
    main_wt, side_wt = repo_record["worktrees"]
    assert (main_wt["branch"], side_wt["branch"]) == ("main", "side")
    assert main_wt["head"] == _git(work, "rev-parse", "HEAD")
    assert main_wt["upstream"] == "origin/main" and main_wt["upstream_sha"] == pushed
    assert main_wt["unpushed_commits"] == 1
    assert {(e["status"], e["path"]) for e in main_wt["uncommitted"]} == {
        (" M", "a.txt"),
        ("??", "new.txt"),
    }
    assert side_wt["upstream"] is None and side_wt["unpushed_commits"] == 0


def test_status_never_takes_the_index_lock() -> None:
    calls: list[list[str]] = []

    def run(argv, cwd):  # type: ignore[no-untyped-def]
        calls.append(list(argv))
        return 1, ""

    ledger.worktree_state(Path("."), "main", run)
    status = [c for c in calls if "status" in c]
    assert status and all("--no-optional-locks" in c for c in status)
    assert not any(c[1:2] == ["fetch"] for c in calls)


def test_remote_failure_keeps_last_success_apart(repo: tuple[Path, Path]) -> None:
    work, remote = repo
    first = ledger.build_ledger("HOST4", [work], check_pr=False)
    ok = first["repositories"][0]["remote_base"]
    remote.rename(remote.with_suffix(".gone"))
    second = ledger.build_ledger("HOST4", [work], check_pr=False, previous=first)
    base = second["repositories"][0]["remote_base"]
    assert base["status"] == ledger.REMOTE_FAILED and "sha" not in base
    assert base["checked_at"]
    assert base["last_success"] == {"checked_at": ok["checked_at"], "sha": ok["sha"]}
    third = ledger.build_ledger("HOST4", [work], check_pr=False, previous=second)
    assert third["repositories"][0]["remote_base"]["last_success"]["sha"] == ok["sha"]


def test_write_atomic_touches_only_its_own_host_file(tmp_path: Path) -> None:
    other = tmp_path / "HOST1.json"
    other.write_text("keep me\n")
    ledger.write_atomic({"host_id": "HOST4", "x": 1}, tmp_path)
    ledger.write_atomic({"host_id": "HOST4", "x": 2}, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["HOST1.json", "HOST4.json"]
    assert other.read_text() == "keep me\n"
    assert json.loads((tmp_path / "HOST4.json").read_text())["x"] == 2


@pytest.mark.parametrize("host_id", ["../HOST1", "HOST4/x", "", ".hidden"])
def test_host_id_cannot_name_another_path(tmp_path: Path, host_id: str) -> None:
    with pytest.raises(ValueError):
        ledger.write_atomic({"host_id": host_id}, tmp_path)


def test_mounted_drive_gets_a_copy_and_sync_stays_unverified(tmp_path: Path) -> None:
    drive = tmp_path / "g" / "hosts" / "HOST4"
    drive.mkdir(parents=True)
    other = drive.parent / "HOST1.json"
    other.write_text("other host\n")
    state = tmp_path / "state"
    mounts = ROOT_EXT4 + DRVFS.format(point=tmp_path / "g")
    record = ledger.record_and_copy({"host_id": "HOST4"}, state, drive, mountinfo=mounts)
    assert record["drive"]["local_drive_folder"] == "written_to_local_drive_folder"
    assert record["drive"]["cloud_sync"] == "unverified"
    local = json.loads((state / "HOST4.json").read_text())
    copied = json.loads((drive / "HOST4.json").read_text())
    assert local == copied == record
    assert other.read_text() == "other host\n"
    assert sorted(p.name for p in drive.iterdir()) == ["HOST4.json"]


def test_unmounted_drive_folder_is_never_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The /mnt/g shape before G: is mounted: the folder exists but lives on the root ext4.
    drive = tmp_path / "g"
    drive.mkdir()
    state = tmp_path / "state"
    record = ledger.record_and_copy({"host_id": "HOST4"}, state, drive, mountinfo=ROOT_EXT4)
    assert record["drive"]["local_drive_folder"] == "drive_unavailable"
    assert "not on a mounted drive" in record["drive"]["problem"]
    assert list(drive.iterdir()) == []
    assert json.loads((state / "HOST4.json").read_text())["drive"]["local_drive_folder"] == (
        "drive_unavailable"
    )
    assert "WARNING" in capsys.readouterr().err


def test_missing_drive_folder_is_not_created(tmp_path: Path) -> None:
    drive = tmp_path / "Drive" / "00-Team-Ops" / "hosts" / "HOST4"
    record = ledger.record_and_copy(
        {"host_id": "HOST4"}, tmp_path / "state", drive, mountinfo=DRVFS.format(point=tmp_path)
    )
    assert record["drive"]["local_drive_folder"] == "drive_unavailable"
    assert not (tmp_path / "Drive").exists()


def test_drive_write_failure_is_a_status_and_main_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: tuple[Path, Path]
) -> None:
    work, _ = repo
    drive = tmp_path / "g"
    drive.mkdir()
    monkeypatch.setattr(ledger, "drive_problem", lambda d, m=None: None)
    real_write = ledger.write_atomic

    def flaky(record, directory):  # type: ignore[no-untyped-def]
        if directory == drive:
            raise OSError("drive went away")
        return real_write(record, directory)

    monkeypatch.setattr(ledger, "write_atomic", flaky)
    state = tmp_path / "state"
    argv = ["--host-id", "HOST4", "--state-dir", str(state), "--drive-dir", str(drive)]
    assert ledger.main([*argv, "--repo", str(work), "--no-pr"]) == 0
    local = json.loads((state / "HOST4.json").read_text())
    assert local["drive"]["local_drive_folder"] == "write_failed"
    assert "drive went away" in local["drive"]["problem"]


def test_unwritable_state_dir_still_exits_zero(tmp_path: Path, repo: tuple[Path, Path]) -> None:
    work, _ = repo
    blocker = tmp_path / "file"
    blocker.write_text("")
    argv = ["--host-id", "HOST4", "--state-dir", str(blocker / "x"), "--repo", str(work)]
    assert ledger.main([*argv, "--no-pr", "--no-remote"]) == 0


def test_mountinfo_parsing_decodes_escaped_paths() -> None:
    line = "248 170 0:125 / /mnt/my\\040drive rw - 9p G: rw\n"
    assert ledger.read_mounts(line) == [("/mnt/my drive", "9p")]


def test_timer_units_run_the_copied_script_every_five_minutes(tmp_path: Path) -> None:
    units = ledger.unit_files("/usr/bin/python3", Path("/x/host_ledger.py"), ["--host-id", "H"], 5)
    service, timer = units[f"{ledger.UNIT}.service"], units[f"{ledger.UNIT}.timer"]
    assert "ExecStart=/usr/bin/python3 /x/host_ledger.py --host-id H" in service
    assert "OnUnitActiveSec=5min" in timer and "WantedBy=timers.target" in timer


def test_install_forwards_the_record_arguments_to_the_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}
    monkeypatch.setattr(ledger, "user_unit_dir", lambda: tmp_path / "units")
    monkeypatch.setattr(ledger, "install_timer", lambda units, d, run: seen.update(units) or 0)
    argv = ["--host-id", "HOST4", "--state-dir", str(tmp_path / "s"), "--repo", str(tmp_path)]
    argv += ["--artifact", "/x/smoke dir", "--test-result", "pytest ok", "--install-user-timer"]
    assert ledger.main(argv) == 0
    service = seen[f"{ledger.UNIT}.service"]
    assert "--artifact '/x/smoke dir'" in service and "--test-result 'pytest ok'" in service
    assert "--install-user-timer" not in service


def test_main_requires_a_plain_host_id(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        ledger.main(["--host-id", "../x", "--state-dir", str(tmp_path), "--no-remote", "--no-pr"])
