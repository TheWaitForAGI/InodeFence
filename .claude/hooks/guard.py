"""PreToolUse guard for autonomous InodeFence sessions.

Claude Code runs this for every tool call in the main session and in
subagents. Exit 0 allows the call; exit 2 blocks it and shows stderr to the
agent. settings.json wraps the call with `|| exit 2`, so a crash or a missing
interpreter also blocks (fail closed).

Rules for every session (see .claude/skills/autoloop/SKILL.md):
  R1  no new docs/ file whose path contains audit|readiness|handoff|qualification|preserve
  R2  no git push that targets main (branch pushes are allowed); no gh pr merge
  R3  no docker/podman isolation weakening (--privileged, --cap-add, --security-opt, host ns)
  R4  no edits to the isolation allowlist or to the agent's own guard configuration
  R5  no new isolation-weakening flags written into code/config files
Role rules (only when the session runs the .claude/agents roles):
  R6  orchestrator: metadata only (no source, diff, or run output); delegates to opus workers
  R7  runtime: writes only run-record docs, never code
  R8  verifier: read-only

Keep this file compatible with older python3 (macOS host) — stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

BANNED_DOC_WORDS = re.compile(r"audit|readiness|handoff|qualification|preserve", re.IGNORECASE)

# Repo-relative files that hold the Docker allowlist / isolation policy.
PROTECTED_ISOLATION_FILES = (
    "src/inodefence/execution/docker_client.py",
    "src/inodefence/execution/container.py",
    "src/inodefence/model/isolation.py",
)
# Paths matched anywhere (project and user-level Claude Code config).
PROTECTED_CONFIG = re.compile(r"\.claude/(settings(\.local)?\.json|hooks/)")

DOCKER_WORD = re.compile(r"(^|[^\w.-])(docker|podman|nerdctl)([^\w.-]|$)")
WEAKENING_FLAG = re.compile(
    r"--privileged|--cap-add|--security-opt"
    r"|--(pid|net|network|ipc|uts|userns|cgroupns)[= ]+host\b"
    r"|--device\b"
    r"|(-v|--volume|--mount)[= ]+(type=bind,\s*)?(source=|src=)?/(:|,|\s|$)"
)
# Same intent for files: compose/JSON spellings of the flags above.
WEAKENING_CONTENT = re.compile(
    r"--privileged|--cap-add|--security-opt"
    r"|\bprivileged\s*:\s*true|\"Privileged\"\s*:\s*true"
    r"|\bcap_add\s*:|\"CapAdd\"\s*:\s*\[\s*\""
    r"|\bsecurity_opt\s*:"
)
REDIRECT_PATTERN = r"(^|[^<>&0-9])>{1,2}\s*(?!&|/dev/null)"  # into a file (not 2>&1, >/dev/null)
REDIRECT = re.compile(REDIRECT_PATTERN)
WRITE_INDICATOR = re.compile(
    REDIRECT_PATTERN + r"|\bsed\b[^|;&]*\s-[a-zA-Z]*i"
    r"|\bperl\b[^|;&]*\s-[a-zA-Z]*i"
    r"|\b(tee|mv|cp|rm|truncate|install|ln|chmod|chown|dd|patch|touch|mkdir|unlink)\b"
    r"|\bgit\s+(checkout|restore|apply|am|mv|rm)\b"
    r"|\b(python[0-9.]*|node|ruby|perl)\b"
)
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n&]")


def block(rule: str, reason: str) -> None:
    sys.stderr.write(
        "[InodeFence guard " + rule + "] BLOCKED: " + reason + "\n"
        "Do not work around this. Stop this step, record it in docs/LOG.md "
        "(and WORKLOG as 막힘), and move to the next safe task.\n"
    )
    sys.exit(2)


def project_root(payload: dict) -> Path:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return Path(root).resolve()


def relative_to_root(path: str, payload: dict) -> str | None:
    root = project_root(payload)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(payload.get("cwd") or root) / candidate
    try:
        return candidate.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


# --- file tools -------------------------------------------------------------


def check_file_tool(tool: str, tool_input: dict, payload: dict) -> None:
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    rel = relative_to_root(path, payload)
    shown = rel if rel is not None else path

    if PROTECTED_CONFIG.search(Path(path).resolve().as_posix()):
        block("R4", shown + " is guard configuration; only a human may change it.")
    if rel in PROTECTED_ISOLATION_FILES:
        block(
            "R4",
            shown + " holds the Docker allowlist/isolation policy; only a human may change it.",
        )

    if tool == "Write" and rel is not None and rel.startswith("docs/"):
        if BANNED_DOC_WORDS.search(rel) and not Path(path).exists():
            block(
                "R1",
                "new docs file " + rel + " matches audit|readiness|handoff|qualification|preserve. "
                "Record in docs/STATUS.md or one line in docs/LOG.md instead (AGENTS.md 금지).",
            )

    if shown.endswith(".md"):
        return
    before, after = old_and_new_text(tool, tool_input, path)
    added = len(WEAKENING_CONTENT.findall(after)) - len(WEAKENING_CONTENT.findall(before))
    if added > 0:
        block(
            "R5",
            "change adds an isolation-weakening flag (privileged/cap-add/security-opt) to "
            + shown
            + ".",
        )


def old_and_new_text(tool: str, tool_input: dict, path: str) -> tuple[str, str]:
    if tool == "Write":
        try:
            before = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            before = ""
        return before, tool_input.get("content") or ""
    if tool == "Edit":
        return tool_input.get("old_string") or "", tool_input.get("new_string") or ""
    if tool == "MultiEdit":
        edits = tool_input.get("edits") or []
        return (
            "\n".join(e.get("old_string") or "" for e in edits),
            "\n".join(e.get("new_string") or "" for e in edits),
        )
    return "", tool_input.get("new_source") or ""


# --- Bash -------------------------------------------------------------------


def current_branch(payload: dict) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=payload.get("cwd") or None,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return segment.split()


def is_main_ref(ref: str) -> bool:
    return ref in ("main", "refs/heads/main")


def check_git_push(args: list[str], payload: dict) -> None:
    positional = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in ("--all", "--mirror", "--branches"):
            block("R2", "git push " + arg + " would also push main.")
        if arg in ("--repo", "-o", "--push-option", "--receive-pack", "--exec"):
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        positional.append(arg)
    refspecs = positional[1:]
    branch = current_branch(payload)
    if not refspecs and branch == "main":
        block("R2", "bare git push on branch main pushes main directly.")
    for spec in refspecs:
        spec = spec.lstrip("+")
        src, _, dst = spec.partition(":")
        dest = dst if dst else src
        if dest == "HEAD" and branch == "main":
            dest = "main"
        if is_main_ref(dest):
            block(
                "R2", "git push to main is not allowed; push a work branch and let a human merge."
            )


def check_bash(command: str, payload: dict) -> None:
    # R3: docker/podman isolation weakening (raw text, so nested `bash -c` is covered).
    weakening = WEAKENING_FLAG.search(command)
    if weakening and DOCKER_WORD.search(command):
        block("R3", "container command weakens isolation (" + weakening.group(0) + ").")

    # R4: shell writes to protected files.
    writes = WRITE_INDICATOR.search(command)
    if writes:
        for protected in PROTECTED_ISOLATION_FILES:
            if protected in command or Path(protected).name in command:
                block(
                    "R4", "shell command may modify " + protected + " (allowlist/isolation policy)."
                )
        if PROTECTED_CONFIG.search(command):
            block("R4", "shell command may modify Claude Code guard configuration.")
        # R1 via shell: creating docs files with banned words.
        for match in re.finditer(r"docs/[^\s'\"<>|;&]+", command):
            if BANNED_DOC_WORDS.search(match.group(0)):
                block(
                    "R1",
                    "shell command may create/modify " + match.group(0) + " (banned doc name).",
                )

    # R2: git push to main / gh pr merge.
    for words in simple_commands(command):
        if words[:3] == ["gh", "pr", "merge"]:
            block("R2", "merging PRs is a human action.")
        sub = git_subcommand(words)
        if sub is not None and sub[0] == "push":
            check_git_push(sub[1:], payload)


def simple_commands(command: str) -> list[list[str]]:
    """Split a shell line into simple commands, dropping VAR=value and sudo/env prefixes."""
    result = []
    for segment in SEGMENT_SPLIT.split(command):
        words = tokens(segment)
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]
        if words and words[0] in ("sudo", "env", "command", "exec"):
            words = words[1:]
        if words:
            result.append(words)
    return result


def git_subcommand(words: list[str]) -> list[str] | None:
    """Return [subcommand, args...] for a git command line, else None."""
    if not words or words[0] != "git":
        return None
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
    return words[i:] or None


# --- roles (.claude/agents/*.md) ---------------------------------------------
# The main thread started with `claude --agent orchestrator` reports
# agent_type=orchestrator and no agent_id; subagents always carry an agent_id.

WORKERS = ("builder", "runtime", "verifier")
WORKER_MODEL = "opus"
# Metadata the orchestrator may read: task titles, states, branch names, rules.
ORCHESTRATOR_READABLE = (
    "AGENTS.md",
    "CLAUDE.md",
    "docs/BACKLOG.md",
    "docs/WORKLOG.md",
    "docs/STATUS.md",
    "docs/MIDTERM_GOALS.md",
    ".claude/skills/autoloop/SKILL.md",
)
ORCHESTRATOR_TOOLS = (
    "Agent",
    "Task",
    "SendMessage",
    "ListAgents",
    "TaskStop",
    "Read",
    "Glob",
    "Bash",
    "TodoWrite",
    "Skill",
    "ToolSearch",
    "ScheduleWakeup",
)
# Doc files the runtime agent may write (run records only, never code).
RUNTIME_WRITABLE = ("docs/LOG.md", "docs/WORKLOG.md", "docs/BACKLOG.md", "docs/STATUS.md")
FILE_READERS = ("cat", "head", "tail", "wc")
METADATA_COMMANDS = ("echo", "pwd", "date", "ls", "which", "printenv", "true")
GIT_METADATA = ("status", "branch", "rev-parse", "fetch", "remote", "show-ref", "ls-remote")
GIT_SUMMARY_FLAGS = ("--stat", "--shortstat", "--name-only", "--name-status", "--numstat")


def role_of(payload: dict) -> str:
    agent_type = payload.get("agent_type") or ""
    if payload.get("agent_id"):
        return agent_type if agent_type in WORKERS else "subagent"
    return "orchestrator" if agent_type == "orchestrator" else "main"


def orchestrator_readable(path: str, payload: dict) -> bool:
    rel = relative_to_root(path, payload)
    if rel is None:
        return False
    return rel in ORCHESTRATOR_READABLE or bool(re.fullmatch(r"\.claude/agents/[\w-]+\.md", rel))


def check_orchestrator(tool: str, tool_input: dict, payload: dict) -> None:
    deny = "the orchestrator sees metadata only; delegate to builder/runtime/verifier and ask "
    deny += "for a metadata summary."
    if tool not in ORCHESTRATOR_TOOLS:
        block("R6", tool + " is not an orchestrator tool; " + deny)
    if tool in ("Agent", "Task"):
        kind = tool_input.get("subagent_type") or ""
        if kind not in WORKERS:
            block(
                "R6", "subagent_type must be one of " + "/".join(WORKERS) + ", got '" + kind + "'."
            )
        model = tool_input.get("model")
        if model not in (None, "", WORKER_MODEL):
            block("R6", "worker model override is not allowed (got '" + str(model) + "').")
    elif tool == "Read":
        path = tool_input.get("file_path") or ""
        if not orchestrator_readable(path, payload):
            block("R6", "reading " + path + " is not allowed; " + deny)
    elif tool == "Skill":
        if (tool_input.get("skill") or "") != "autoloop":
            block("R6", "only the autoloop skill is available to the orchestrator.")
    elif tool == "Bash":
        check_orchestrator_bash(tool_input.get("command") or "", payload, deny)


def check_orchestrator_bash(command: str, payload: dict, deny: str) -> None:
    if re.search(r"\$\(|`|(^|[^0-9&])>|<\(|<<", command):
        block("R6", "substitution/redirection is not allowed for the orchestrator.")
    for index, words in enumerate(simple_commands(command)):
        name = words[0]
        args = [arg for arg in words[1:] if not arg.startswith("-")]
        if name in METADATA_COMMANDS:
            if name == "ls" and any(not orchestrator_lists(arg, payload) for arg in args):
                block("R6", "ls outside metadata locations; " + deny)
            continue
        if name in FILE_READERS:
            args = [arg for arg in args if not arg.isdigit()]  # head -n 5
        if name in FILE_READERS + ("grep",) and index > 0 and not args:
            continue  # a filter reading the previous command's output
        if name in FILE_READERS or name == "grep":
            files = args[1:] if name == "grep" else args
            if "-r" in words or "-R" in words or not files:
                block("R6", name + " needs explicit metadata files; " + deny)
            for path in files:
                if not orchestrator_readable(path, payload):
                    block("R6", name + " " + path + " is not allowed; " + deny)
            continue
        sub = git_subcommand(words)
        if sub is not None:
            if sub[0] in GIT_METADATA:
                continue
            if sub[0] == "log" and not any(a in ("-p", "--patch", "-u") for a in sub):
                continue
            if sub[0] == "diff" and any(a in GIT_SUMMARY_FLAGS for a in sub):
                continue
        block("R6", "'" + " ".join(words)[:60] + "' is not an orchestrator command; " + deny)


def orchestrator_lists(path: str, payload: dict) -> bool:
    rel = relative_to_root(path, payload)
    return rel in (".", "docs", ".claude", ".claude/agents", ".claude/skills")


def check_runtime_files(tool_input: dict, payload: dict) -> None:
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if relative_to_root(path, payload) not in RUNTIME_WRITABLE:
        block("R7", "runtime may only write run records (" + ", ".join(RUNTIME_WRITABLE) + ").")


def check_verifier_bash(command: str) -> None:
    for words in simple_commands(command):
        sub = git_subcommand(words)
        if sub is not None and sub[0] in (
            "commit",
            "push",
            "merge",
            "rebase",
            "reset",
            "cherry-pick",
            "revert",
            "tag",
            "stash",
            "clean",
            "apply",
            "am",
        ):
            block("R8", "verifier is read-only (git " + sub[0] + ").")
    in_place = re.search(r"\b(sed|perl)\b[^|;&]*\s-[a-zA-Z]*i|\btee\b", command)
    if REDIRECT.search(command) or in_place:
        block("R8", "verifier is read-only (in-place edit, tee, or redirect into a file).")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError as error:
        block("input", "could not parse hook input: " + str(error))
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    role = role_of(payload)
    if role == "orchestrator":
        check_orchestrator(tool, tool_input, payload)
    if role == "verifier" and tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        block("R8", "verifier is read-only.")
    if role == "runtime" and tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_runtime_files(tool_input, payload)
    if tool == "Bash":
        check_bash(tool_input.get("command") or "", payload)
        if role == "verifier":
            check_verifier_bash(tool_input.get("command") or "")
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_file_tool(tool, tool_input, payload)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:  # fail closed
        block("internal", "guard error " + type(error).__name__ + ": " + str(error))
