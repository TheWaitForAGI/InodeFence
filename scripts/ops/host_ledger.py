"""Host Ledger: record what one host has checked out, so hosts can see each other's state.

Two separate steps, in this order:

1. **Local record** (always): ``<state-dir>/<HOST_ID>.json`` is written atomically (temp file +
   rename). ``--state-dir`` defaults to ``$INODEFENCE_HOST_LEDGER_STATE_DIR`` or
   ``~/.local/state/inodefence/host-ledger`` -- outside any repository and outside the shared drive.
2. **Drive copy** (optional, ``--drive-dir`` or ``$INODEFENCE_HOST_LEDGER_DRIVE_DIR``): the same
   record is copied atomically to ``<drive-dir>/<HOST_ID>.json``, but only if ``drive-dir`` already
   exists and sits on a mounted Windows drive (``9p``/``drvfs``). Otherwise the record says
   ``drive_unavailable`` and nothing is written there: this script never mounts, never creates or
   repairs links, never creates the drive folder and never writes on an unmounted ``/mnt/<x>``
   (that would silently fill the local disk). A successful copy is recorded as
   ``written_to_local_drive_folder``; cloud sync is always ``unverified`` -- this script cannot see
   it and never claims it.

Ownership: each record carries ``machine``, a salted SHA-256 of ``/etc/machine-id`` (never the raw
value). The drive copy refuses to replace ``<HOST_ID>.json`` when that file was written by another
machine or carries no fingerprint (a mistyped ``--host-id`` must not overwrite another host's
ledger): the record then says ``refused_not_ours``. ``--adopt`` takes such a file over once; it is
never put in the timer. The local record is unaffected.

Every failure after argument parsing is a WARNING and exits 0: the ledger is advisory and must not
block git work. Do not install it as a git hook.

Recorded: host id and observation time; for each repository, every worktree with branch, HEAD,
upstream and its SHA, commits not pushed, and uncommitted paths (status code + path only); the
remote base branch SHA from ``git ls-remote`` with its own check time and status (``ok``, ``remote
check failed``, ``remote branch not found`` or ``not checked``; otherwise than ``ok`` the last
successful check is carried over from the previous local record as ``last_success``, never as the
current value); the PRs for each branch when ``gh`` answers; caller-reported test results and
artifact paths (``PATH`` or ``PATH|note``) under ``reported`` with ``reported_at`` = when they were
given (fixed at timer install, not refreshed per run) and, per artifact, ``exists`` as checked on
this run. The timer unit gets every record-shaping option of the install command (``--remote``,
``--base-branch``, ``--no-remote``, ``--no-pr``, reported items); ``%`` is escaped for systemd.
Never recorded: file contents, ``.git``
contents, tokens, keys, environment-variable values.

Read-only toward git: ``git --no-optional-locks status`` (no index refresh lock), ``rev-parse``,
``rev-list``, ``worktree list``, ``ls-remote`` (no fetch: no ref or lock is touched), so a periodic
run cannot collide with another session's git work.

Usage::

    python scripts/ops/host_ledger.py --host-id HOST4 \
        --drive-dir "$HOME/Drive/00-Team-Ops/hosts/HOST4" --repo ~/Projects/InodeFence

Every 5 minutes with a systemd user timer (no sudo; WSL needs ``systemd=true`` in wsl.conf, and
without ``loginctl enable-linger`` the timer runs only while the distro has a user session)::

    # install: copy the script out of the checkout so branch switches do not change what runs
    install -D -m 0644 scripts/ops/host_ledger.py ~/.local/lib/inodefence/host_ledger.py
    python3 ~/.local/lib/inodefence/host_ledger.py --host-id HOST4 \
        --drive-dir "$HOME/Drive/00-Team-Ops/hosts/HOST4" --repo ~/Projects/InodeFence \
        --install-user-timer
    systemctl --user list-timers inodefence-host-ledger.timer   # check
    journalctl --user -u inodefence-host-ledger.service -n 20    # last runs
    # remove
    python3 ~/.local/lib/inodefence/host_ledger.py --host-id HOST4 --uninstall-user-timer
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "inodefence-host-ledger/v2"
HOST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
REMOTE_FAILED = "remote check failed"
REMOTE_BRANCH_MISSING = "remote branch not found"
DRIVE_FSTYPES = frozenset({"9p", "drvfs"})
DEFAULT_STATE_DIR = "~/.local/state/inodefence/host-ledger"
UNIT = "inodefence-host-ledger"
TIMEOUT_S = 30

# (argv, cwd) -> (returncode, stdout). Injected in tests; never runs a shell.
Runner = Callable[[Sequence[str], Path], tuple[int, str]]


def run_command(argv: Sequence[str], cwd: Path) -> tuple[int, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1"}
    try:
        done = subprocess.run(
            list(argv),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""
    return done.returncode, done.stdout


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---- git state (read-only) ----


def parse_worktrees(porcelain: str) -> list[dict[str, Any]]:
    """Parse ``git worktree list --porcelain`` into path/head/branch/detached records."""
    worktrees: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in [*porcelain.splitlines(), ""]:
        if not line:
            if current:
                worktrees.append(current)
            current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current = {"path": value, "head": None, "branch": None, "detached": False}
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "detached":
            current["detached"] = True
        elif key in ("prunable", "bare"):
            current[key] = True
    return worktrees


def parse_status(porcelain_z: str) -> list[dict[str, str]]:
    """Parse ``git status --porcelain=v1 -z``: status code and path only, never content."""
    entries: list[dict[str, str]] = []
    fields = porcelain_z.split("\0")
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if len(field) < 4:
            continue
        code, path = field[:2], field[3:]
        entry = {"status": code, "path": path}
        if code[0] in "RC":  # rename/copy: the next field is the original path
            entry["from"] = fields[index] if index < len(fields) else ""
            index += 1
        entries.append(entry)
    return entries


def worktree_state(path: Path, branch: str | None, run: Runner) -> dict[str, Any]:
    state: dict[str, Any] = {}
    status_argv = ["git", "--no-optional-locks", "status", "--porcelain=v1", "-z"]
    code, out = run([*status_argv, "--untracked-files=all"], path)
    state["uncommitted"] = parse_status(out) if code == 0 else None
    code, out = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], path)
    upstream = out.strip() if code == 0 and out.strip() else None
    state["upstream"] = upstream
    state["upstream_sha"] = None
    if upstream:
        code, out = run(["git", "rev-parse", "@{u}"], path)
        state["upstream_sha"] = out.strip() if code == 0 else None
        unpushed_range = ["@{u}..HEAD"]
    else:  # no upstream: commits on no remote-tracking ref at all
        unpushed_range = ["HEAD", "--not", "--remotes"]
    code, out = run(["git", "rev-list", "--count", *unpushed_range], path)
    state["unpushed_commits"] = int(out.strip()) if code == 0 and out.strip().isdigit() else None
    basis = "vs upstream (last fetched)" if upstream else "no upstream: on no remote-tracking ref"
    state["unpushed_basis"] = basis + (" (detached HEAD)" if branch is None else "")
    return state


def remote_base(
    repo: Path, remote: str, base_branch: str, run: Runner, previous: dict[str, Any] | None
) -> dict[str, Any]:
    """Remote base SHA via ``ls-remote``; a failure keeps the last success apart, not as current."""
    ref = f"{remote}/{base_branch}"
    checked_at = now()
    code, out = run(["git", "ls-remote", remote, f"refs/heads/{base_branch}"], repo)
    sha = out.split()[0] if code == 0 and out.split() else None
    if sha is not None:
        return {"ref": ref, "checked_at": checked_at, "status": "ok", "sha": sha}
    status = REMOTE_BRANCH_MISSING if code == 0 else REMOTE_FAILED
    record: dict[str, Any] = {"ref": ref, "checked_at": checked_at, "status": status}
    record["last_success"] = last_success(previous)  # None if never succeeded
    return record


def last_success(previous: dict[str, Any] | None) -> dict[str, Any] | None:
    """The last successful remote check carried by the previous local record."""
    if not previous:
        return None
    if previous.get("status") == "ok":
        return {"checked_at": previous.get("checked_at"), "sha": previous.get("sha")}
    return previous.get("last_success")


def pull_requests(path: Path, branch: str, run: Runner) -> dict[str, Any]:
    argv = ["gh", "pr", "list", "--head", branch, "--state", "all", "--limit", "5"]
    code, out = run([*argv, "--json", "number,state,url,baseRefName"], path)
    if code != 0:
        return {"status": "unavailable"}
    try:
        prs = json.loads(out or "[]")
    except json.JSONDecodeError:
        return {"status": "unavailable"}
    return {"status": "ok", "prs": prs}


def repo_record(
    repo: Path,
    *,
    remote: str,
    base_branch: str,
    check_remote: bool,
    check_pr: bool,
    run: Runner,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    code, out = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], repo)
    if code != 0:
        return {"path": str(repo), "error": "not a git repository"}
    record: dict[str, Any] = {"path": str(repo), "git_common_dir": out.strip()}
    prev_remote = (previous or {}).get("remote_base")
    record["remote_base"] = (
        remote_base(repo, remote, base_branch, run, prev_remote)
        if check_remote
        else {
            "ref": f"{remote}/{base_branch}",
            "status": "not checked (--no-remote)",
            "last_success": last_success(prev_remote),
        }
    )
    code, out = run(["git", "worktree", "list", "--porcelain"], repo)
    worktrees = parse_worktrees(out) if code == 0 else []
    for worktree in worktrees:
        path = Path(worktree["path"])
        if worktree.get("prunable") or worktree.get("bare") or not path.is_dir():
            continue
        worktree.update(worktree_state(path, worktree["branch"], run))
        if check_pr and worktree["branch"]:
            worktree["pr"] = pull_requests(path, worktree["branch"], run)
    record["worktrees"] = worktrees
    return record


def artifact_record(text: str) -> dict[str, Any]:
    """``PATH`` or ``PATH|note`` -> path, note, and whether the path exists right now."""
    path, _, note = text.partition("|")
    path = path.strip()
    return {
        "path": path,
        "note": note.strip() or None,
        "exists": Path(path).expanduser().exists() if path else False,
    }


def build_ledger(
    host_id: str,
    repos: Sequence[Path],
    *,
    remote: str = "origin",
    base_branch: str = "main",
    check_remote: bool = True,
    check_pr: bool = True,
    test_results: Sequence[str] = (),
    artifacts: Sequence[str] = (),
    reported_at: str | None = None,
    previous: dict[str, Any] | None = None,
    run: Runner = run_command,
) -> dict[str, Any]:
    prev_repos = {r.get("path"): r for r in (previous or {}).get("repositories", [])}
    return {
        "schema": SCHEMA,
        "host_id": host_id,
        "machine": machine_fingerprint(),
        "observed_at": now(),
        "repositories": [
            repo_record(
                repo,
                remote=remote,
                base_branch=base_branch,
                check_remote=check_remote,
                check_pr=check_pr,
                run=run,
                previous=prev_repos.get(str(repo)),
            )
            for repo in repos
        ],
        "reported": {
            "note": "given by the caller on the command line; not re-run by the ledger",
            # When the caller gave them (fixed at timer install), not when this record was made.
            "reported_at": (reported_at or now()) if (test_results or artifacts) else None,
            "test_results": list(test_results),
            # ``PATH`` or ``PATH|note``; ``exists`` is checked on every run (observed_at).
            "artifacts": [artifact_record(text) for text in artifacts],
        },
    }


# ---- writing ----


def machine_fingerprint() -> str:
    """A salted SHA-256 of this machine's id (``/etc/machine-id``, else the hostname).

    Only the hash is recorded, never the raw id; it lets a ledger file say which machine wrote it.
    """
    try:
        raw = Path("/etc/machine-id").read_text(encoding="utf-8").strip()
    except OSError:
        raw = ""
    raw = raw or socket.gethostname()
    return hashlib.sha256(f"inodefence-host-ledger:{raw}".encode()).hexdigest()


def existing_owner(target: Path) -> str | None:
    """None if ``target`` is absent; else its machine fingerprint ("" if none or unreadable)."""
    if not target.exists() and not target.is_symlink():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    owner = data.get("machine") if isinstance(data, dict) else None
    return owner if isinstance(owner, str) else ""


def write_atomic(
    record: dict[str, Any], directory: Path, *, guard_owner: bool = False, adopt: bool = False
) -> Path:
    """Atomically replace ``directory/<host_id>.json``; never writes any other final file."""
    host_id = record["host_id"]
    if not HOST_ID_PATTERN.fullmatch(host_id):
        raise ValueError(f"host id {host_id!r} is not a plain name")
    if not directory.is_dir():
        raise FileNotFoundError(f"directory {directory} does not exist")
    target = directory / f"{host_id}.json"
    if guard_owner:
        owner = existing_owner(target)
        mine = record.get("machine")
        if owner is not None and not adopt and owner != mine:
            raise PermissionError(
                f"{target} exists and was written by "
                + ("an unidentified writer" if owner == "" else "another machine")
                + "; refusing to overwrite it (wrong --host-id? pass --adopt once to take it over)"
            )
    fd, tmp = tempfile.mkstemp(prefix=f".{host_id}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def read_mounts(mountinfo: str) -> list[tuple[str, str]]:
    """``/proc/self/mountinfo`` -> [(mount point, fstype)] (octal escapes decoded)."""
    mounts = []
    for line in mountinfo.splitlines():
        left, sep, right = line.partition(" - ")
        fields = left.split()
        if not sep or len(fields) < 5 or not right.split():
            continue
        point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[4])
        mounts.append((point, right.split()[0]))
    return mounts


def drive_problem(drive_dir: Path, mountinfo: str | None = None) -> str | None:
    """Why ``drive_dir`` must not be written, or ``None`` when it is a mounted drive folder."""
    if not drive_dir.is_dir():
        return f"{drive_dir} does not exist (drive not mounted, or folder not created)"
    real = drive_dir.resolve()
    if mountinfo is None:
        try:
            mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
        except OSError as error:
            return f"cannot read mount table ({error})"
    best: tuple[str, str] | None = None
    for point, fstype in read_mounts(mountinfo):
        inside = real == Path(point) or real.is_relative_to(point)
        if inside and (best is None or len(point) > len(best[0])):
            best = (point, fstype)
    if best is None or best[1] not in DRIVE_FSTYPES:
        found = f"{best[1]} at {best[0]}" if best else "no mount"
        return f"{real} is not on a mounted drive ({found}; expected {sorted(DRIVE_FSTYPES)})"
    return None


def record_and_copy(
    ledger: dict[str, Any],
    state_dir: Path,
    drive_dir: Path | None,
    *,
    mountinfo: str | None = None,
    adopt: bool = False,
) -> dict[str, Any]:
    """Step 1: local atomic write. Step 2: drive copy. Returns the final record; never raises.

    The drive copy never replaces a file another machine wrote, nor one with no machine
    fingerprint, unless ``adopt`` (``--adopt``, one-off, never put in the timer) is given.
    """
    drive: dict[str, Any] = {"cloud_sync": "unverified"}
    if drive_dir is None:
        drive["local_drive_folder"] = "not configured"
    else:
        drive["dir"] = str(drive_dir)
        drive["local_drive_folder"] = "pending"
    record = {**ledger, "drive": drive}
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        local = write_atomic(record, state_dir)
    except (OSError, ValueError) as error:
        print(f"WARNING: local host ledger not written: {error}", file=sys.stderr)
        local = None
    if drive_dir is not None:
        problem = drive_problem(drive_dir, mountinfo)
        drive["attempted_at"] = now()
        if problem is not None:
            drive.update(local_drive_folder="drive_unavailable", problem=problem)
        else:
            drive["local_drive_folder"] = "written_to_local_drive_folder"
            try:
                write_atomic(record, drive_dir, guard_owner=True, adopt=adopt)
            except PermissionError as error:
                drive.update(local_drive_folder="refused_not_ours", problem=str(error))
            except (OSError, ValueError) as error:
                drive.update(local_drive_folder="write_failed", problem=str(error))
        if drive["local_drive_folder"] != "written_to_local_drive_folder":
            print(f"WARNING: drive copy skipped: {drive.get('problem')}", file=sys.stderr)
        if local is not None:  # step 1's record gets step 2's outcome
            try:
                write_atomic(record, state_dir)
            except (OSError, ValueError) as error:
                print(f"WARNING: local host ledger not updated: {error}", file=sys.stderr)
    return record


def load_previous(state_dir: Path, host_id: str) -> dict[str, Any] | None:
    try:
        data = json.loads((state_dir / f"{host_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ---- systemd user timer ----


def unit_files(python: str, script: Path, args: Sequence[str], minutes: int) -> dict[str, str]:
    command = shlex.join([python, str(script), *args]).replace("%", "%%")
    service = (
        "[Unit]\nDescription=InodeFence host ledger (advisory; read-only git)\n\n"
        f"[Service]\nType=oneshot\nExecStart={command}\n"
    )
    timer = (
        f"[Unit]\nDescription=InodeFence host ledger every {minutes} min\n\n"
        f"[Timer]\nOnBootSec=1min\nOnUnitActiveSec={minutes}min\nUnit={UNIT}.service\n\n"
        "[Install]\nWantedBy=timers.target\n"
    )
    return {f"{UNIT}.service": service, f"{UNIT}.timer": timer}


def user_unit_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "systemd" / "user"


def install_timer(units: dict[str, str], unit_dir: Path, run: Runner) -> int:
    if shutil.which("systemctl") is None:
        print("systemctl not found: use a user crontab instead", file=sys.stderr)
        return 3
    unit_dir.mkdir(parents=True, exist_ok=True)
    for name, text in units.items():
        (unit_dir / name).write_text(text, encoding="utf-8")
    for argv in (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", f"{UNIT}.timer"],
    ):
        code, _ = run(argv, unit_dir)
        if code != 0:
            print(f"failed: {shlex.join(argv)}", file=sys.stderr)
            return 3
    print(f"installed {UNIT}.timer in {unit_dir}")
    return 0


def uninstall_timer(unit_dir: Path, run: Runner) -> int:
    run(["systemctl", "--user", "disable", "--now", f"{UNIT}.timer"], unit_dir)
    for suffix in (".timer", ".service"):
        (unit_dir / f"{UNIT}{suffix}").unlink(missing_ok=True)
    run(["systemctl", "--user", "daemon-reload"], unit_dir)
    print(f"removed {UNIT}.timer")
    return 0


def main(argv: Sequence[str] | None = None, run: Runner = run_command) -> int:
    parser = argparse.ArgumentParser(
        description="Record this host's repository state in one host ledger file."
    )
    parser.add_argument("--host-id", default=os.environ.get("INODEFENCE_HOST_ID"))
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=os.environ.get("INODEFENCE_HOST_LEDGER_STATE_DIR", DEFAULT_STATE_DIR),
    )
    parser.add_argument(
        "--drive-dir", type=Path, default=os.environ.get("INODEFENCE_HOST_LEDGER_DRIVE_DIR")
    )
    parser.add_argument("--repo", type=Path, action="append", help="repeatable (default: cwd)")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--no-remote", action="store_true", help="skip git ls-remote")
    parser.add_argument("--no-pr", action="store_true", help="skip gh pr lookup")
    parser.add_argument("--test-result", action="append", default=[], help="repeatable")
    parser.add_argument("--artifact", action="append", default=[], help="repeatable")
    parser.add_argument("--stdout", action="store_true", help="print the ledger; write nothing")
    parser.add_argument(
        "--adopt",
        action="store_true",
        help="one-off: take over an existing drive file with no/other machine fingerprint",
    )
    parser.add_argument("--install-user-timer", action="store_true")
    parser.add_argument("--uninstall-user-timer", action="store_true")
    parser.add_argument("--every-minutes", type=int, default=5)
    parser.add_argument(
        "--reported-at", help="when --test-result/--artifact were given (default: now)"
    )
    args = parser.parse_args(argv)
    if not args.host_id or not HOST_ID_PATTERN.fullmatch(args.host_id):
        parser.error("--host-id (or INODEFENCE_HOST_ID) must be a plain name like HOST4")
    if args.uninstall_user_timer:
        return uninstall_timer(user_unit_dir(), run)
    repos = [path.expanduser().resolve() for path in (args.repo or [Path.cwd()])]
    state_dir = Path(args.state_dir).expanduser()
    drive_dir = None if args.drive_dir is None else Path(args.drive_dir).expanduser()
    if args.install_user_timer:
        if args.every_minutes < 1:
            parser.error("--every-minutes must be >= 1")
        forwarded = ["--host-id", args.host_id, "--state-dir", str(state_dir)]
        forwarded += ["--drive-dir", str(drive_dir)] if drive_dir is not None else []
        for repo in repos:
            forwarded += ["--repo", str(repo)]
        forwarded += ["--remote", args.remote, "--base-branch", args.base_branch]
        forwarded += ["--no-remote"] if args.no_remote else []
        forwarded += ["--no-pr"] if args.no_pr else []
        if args.test_result or args.artifact:  # fixed at install: record when they were given
            forwarded += ["--reported-at", args.reported_at or now()]
        for text in args.test_result:
            forwarded += ["--test-result", text]
        for path in args.artifact:
            forwarded += ["--artifact", path]
        script = Path(__file__).resolve()
        units = unit_files(sys.executable, script, forwarded, args.every_minutes)
        return install_timer(units, user_unit_dir(), run)
    ledger = build_ledger(
        args.host_id,
        repos,
        remote=args.remote,
        base_branch=args.base_branch,
        check_remote=not args.no_remote,
        check_pr=not args.no_pr,
        test_results=args.test_result,
        artifacts=args.artifact,
        reported_at=args.reported_at,
        previous=load_previous(state_dir, args.host_id),
        run=run,
    )
    if args.stdout:
        print(json.dumps(ledger, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    record = record_and_copy(ledger, state_dir, drive_dir, adopt=args.adopt)
    print(
        f"host ledger {args.host_id}: local {state_dir}; "
        f"drive {record['drive']['local_drive_folder']}; cloud sync unverified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
