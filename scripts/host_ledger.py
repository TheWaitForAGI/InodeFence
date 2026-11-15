"""Host Ledger: record what one host has checked out, so hosts can see each other's state.

Writes exactly one file, ``<out-dir>/<HOST_ID>.json``, atomically (temp file + rename in the same
directory). It never writes any other file, never touches ``.git`` beyond read-only git queries,
and never records file contents, environment-variable values, tokens or keys.

Recorded per host: host id and check time; every worktree of each given repository with branch,
HEAD SHA, upstream SHA, commits not pushed, and uncommitted paths (status code + path only); the
remote base branch SHA and when it was checked (``git ls-remote``; on failure the record says
"remote check failed", never a guessed SHA); the PR for each branch when ``gh`` can answer; and
caller-reported test results / artifact locations, labelled as reported.

If the output directory is missing, or ``--expect-mount`` is given and the directory is not on its
own mounted filesystem (e.g. an unmounted shared-drive folder that would silently fill the local
disk), it prints a WARNING and writes to the local fallback directory instead. Every write failure
is a WARNING with exit 0: the ledger is advisory and must not block git work. Do not install it as
a git hook. A local write says nothing about cloud sync; the ledger never claims sync.

Usage::

    python scripts/host_ledger.py --host-id HOST4 --out-dir "$INODEFENCE_HOST_LEDGER_DIR" \
        [--repo PATH ...] [--base-branch main] [--no-remote] [--no-pr] \
        [--test-result "pytest: 4 failed / 5392 passed"] [--artifact PATH ...]

``--out-dir`` defaults to ``$INODEFENCE_HOST_LEDGER_DIR``, ``--fallback-dir`` to
``$INODEFENCE_HOST_LEDGER_FALLBACK_DIR`` or ``~/.local/state/inodefence/host-ledger``, and
``--host-id`` to ``$INODEFENCE_HOST_ID``; no shared-drive path is built into the code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "inodefence-host-ledger/v1"
HOST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
REMOTE_FAILED = "remote check failed"
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
    code, out = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], path)
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
    state["unpushed_basis"] = "upstream" if upstream else "no upstream: not on any remote ref"
    if branch is None:
        state["unpushed_basis"] += " (detached HEAD)"
    return state


def remote_base(repo: Path, remote: str, base_branch: str, run: Runner) -> dict[str, Any]:
    checked_at = now()
    code, out = run(["git", "ls-remote", remote, f"refs/heads/{base_branch}"], repo)
    sha = out.split()[0] if code == 0 and out.split() else None
    if sha is None:
        return {"ref": f"{remote}/{base_branch}", "checked_at": checked_at, "status": REMOTE_FAILED}
    return {"ref": f"{remote}/{base_branch}", "checked_at": checked_at, "status": "ok", "sha": sha}


def pull_request(repo: Path, branch: str, run: Runner) -> dict[str, Any]:
    argv = ["gh", "pr", "list", "--head", branch, "--state", "all", "--limit", "5"]
    code, out = run([*argv, "--json", "number,state,url,baseRefName"], repo)
    if code != 0:
        return {"status": "unavailable"}
    try:
        prs = json.loads(out or "[]")
    except json.JSONDecodeError:
        return {"status": "unavailable"}
    return {"status": "ok", "prs": prs}


def repo_record(
    repo: Path, *, remote: str, base_branch: str, check_remote: bool, check_pr: bool, run: Runner
) -> dict[str, Any]:
    code, out = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], repo)
    if code != 0:
        return {"path": str(repo), "error": "not a git repository"}
    record: dict[str, Any] = {"path": str(repo), "git_common_dir": out.strip()}
    record["remote_base"] = (
        remote_base(repo, remote, base_branch, run)
        if check_remote
        else {"ref": f"{remote}/{base_branch}", "status": "not checked (--no-remote)"}
    )
    code, out = run(["git", "worktree", "list", "--porcelain"], repo)
    worktrees = parse_worktrees(out) if code == 0 else []
    for worktree in worktrees:
        path = Path(worktree["path"])
        if worktree.get("prunable") or worktree.get("bare") or not path.is_dir():
            continue
        worktree.update(worktree_state(path, worktree["branch"], run))
        if check_pr and worktree["branch"]:
            worktree["pr"] = pull_request(path, worktree["branch"], run)
    record["worktrees"] = worktrees
    return record


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
    run: Runner = run_command,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "host_id": host_id,
        "checked_at": now(),
        "repositories": [
            repo_record(
                repo,
                remote=remote,
                base_branch=base_branch,
                check_remote=check_remote,
                check_pr=check_pr,
                run=run,
            )
            for repo in repos
        ],
        "reported": {
            "note": "given by the caller on the command line; not re-run by the ledger",
            "test_results": list(test_results),
            "artifacts": list(artifacts),
        },
    }


def mount_point(path: Path) -> Path:
    """The nearest ancestor of ``path`` (itself included) that is a mount point."""
    current = path.resolve()
    while not os.path.ismount(current) and current != current.parent:
        current = current.parent
    return current


def destination_problem(out_dir: Path, *, expect_mount: bool) -> str | None:
    """Why ``out_dir`` must not be used, or ``None`` when it may be."""
    if not out_dir.is_dir():
        return f"output directory {out_dir} does not exist (not mounted?)"
    if expect_mount and mount_point(out_dir) == Path("/"):
        return f"output directory {out_dir} is on the root filesystem, not on a mounted drive"
    return None


def write_ledger(ledger: dict[str, Any], out_dir: Path) -> Path:
    """Atomically replace ``out_dir/<host_id>.json``; never writes any other final file."""
    host_id = ledger["host_id"]
    if not HOST_ID_PATTERN.fullmatch(host_id):
        raise ValueError(f"host id {host_id!r} is not a plain name")
    if not out_dir.is_dir():
        raise FileNotFoundError(f"output directory {out_dir} does not exist (not mounted?)")
    target = out_dir / f"{host_id}.json"
    fd, tmp = tempfile.mkstemp(prefix=f".{host_id}.", suffix=".tmp", dir=out_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(ledger, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def write_with_fallback(
    ledger: dict[str, Any], out_dir: Path, fallback_dir: Path, expect_mount: bool
) -> int:
    """Write to ``out_dir``, else warn and write to ``fallback_dir``; always exit 0."""
    problem = destination_problem(out_dir, expect_mount=expect_mount)
    if problem is None:
        try:
            target = write_ledger({**ledger, "destination": "primary"}, out_dir)
        except (OSError, ValueError) as error:
            problem = str(error)
        else:
            print(f"host ledger written: {target} (local write; cloud sync not checked)")
            return 0
    print(f"WARNING: host ledger not written to {out_dir}: {problem}", file=sys.stderr)
    try:
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback = {**ledger, "destination": "fallback", "primary_problem": problem}
        target = write_ledger(fallback, fallback_dir)
    except (OSError, ValueError) as error:
        print(f"WARNING: host ledger fallback not written either: {error}", file=sys.stderr)
        return 0
    print(f"WARNING: host ledger written to local fallback {target}", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record this host's repository state in one host ledger file."
    )
    parser.add_argument("--host-id", default=os.environ.get("INODEFENCE_HOST_ID"))
    parser.add_argument(
        "--out-dir", type=Path, default=os.environ.get("INODEFENCE_HOST_LEDGER_DIR")
    )
    parser.add_argument(
        "--fallback-dir",
        type=Path,
        default=os.environ.get(
            "INODEFENCE_HOST_LEDGER_FALLBACK_DIR", "~/.local/state/inodefence/host-ledger"
        ),
    )
    parser.add_argument(
        "--expect-mount", action="store_true", help="out-dir must be on its own mounted filesystem"
    )
    parser.add_argument("--repo", type=Path, action="append", help="repeatable (default: cwd)")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--no-remote", action="store_true", help="skip git ls-remote")
    parser.add_argument("--no-pr", action="store_true", help="skip gh pr lookup")
    parser.add_argument("--test-result", action="append", default=[], help="repeatable")
    parser.add_argument("--artifact", action="append", default=[], help="repeatable")
    parser.add_argument("--stdout", action="store_true", help="print the ledger; write nothing")
    args = parser.parse_args(argv)
    if not args.host_id or not HOST_ID_PATTERN.fullmatch(args.host_id):
        parser.error("--host-id (or INODEFENCE_HOST_ID) must be a plain name like HOST4")
    if args.out_dir is None and not args.stdout:
        parser.error("--out-dir (or INODEFENCE_HOST_LEDGER_DIR) is required unless --stdout")
    ledger = build_ledger(
        args.host_id,
        [path.expanduser().resolve() for path in (args.repo or [Path.cwd()])],
        remote=args.remote,
        base_branch=args.base_branch,
        check_remote=not args.no_remote,
        check_pr=not args.no_pr,
        test_results=args.test_result,
        artifacts=args.artifact,
    )
    if args.stdout:
        print(json.dumps(ledger, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    out_dir: Path | None = args.out_dir
    if out_dir is None:  # unreachable: checked above unless --stdout
        return 0
    return write_with_fallback(
        ledger, out_dir.expanduser(), args.fallback_dir.expanduser(), args.expect_mount
    )


if __name__ == "__main__":
    raise SystemExit(main())
