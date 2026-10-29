"""Allow/block contract of the autonomous-session guard hook (.claude/hooks/guard.py)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".claude" / "hooks" / "guard.py"
SETTINGS = ROOT / ".claude" / "settings.json"
WORKER = {"agent_id": "a1", "agent_type": "builder"}
ORCHESTRATOR = {"agent_type": "orchestrator"}


def bash(command: str, **who: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, **who}


def write(path: str, content: str = "x", **who: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}, **who}


def edit(path: str, old: str, new: str, **who: str) -> dict:
    return {
        "tool_name": "Edit",
        "tool_input": {"file_path": path, "old_string": old, "new_string": new},
        **who,
    }


def tool(name: str, tool_input: dict, **who: str) -> dict:
    return {"tool_name": name, "tool_input": tool_input, **who}


def run_guard(payload: dict) -> subprocess.CompletedProcess[str]:
    payload = {"cwd": str(ROOT), **payload}
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"CLAUDE_PROJECT_DIR": str(ROOT), "PATH": "/usr/bin:/bin"},
        check=False,
    )


ALLOWED = [
    bash("make check"),
    bash("make demo"),
    bash("make demo-native"),
    bash("make demo-synthetic"),
    bash("make probe CASE=hardlink"),
    bash("make node-tar-smoke"),
    bash("DEMO_BUDGET=20 make demo-native 2>&1 | tail -20"),
    bash("bash scripts/local_node_tar_smoke.sh demo"),
    bash("git push -u origin jiwoong/autonomous-setup"),
    bash("git push --force-with-lease origin jiwoong/x:jiwoong/x"),
    bash("git fetch origin main && git log origin/main..HEAD --oneline"),
    bash("git checkout -b jiwoong/p2-c1-impact main"),
    bash("grep -rn -- --security-opt src/"),
    bash("cat src/inodefence/execution/docker_client.py"),
    bash("docker ps"),
    bash("docker context show"),
    bash("PYTHONPATH=src python -m pytest tests/test_container_backend.py -q"),
    bash("echo '- 2026-10-23 | x' >> docs/LOG.md"),
    write(f"{ROOT}/docs/WORKLOG.md"),
    write(f"{ROOT}/docs/research/notes/c1-impact.md"),
    write(f"{ROOT}/src/inodefence/oracle/contracts.py"),
    edit(f"{ROOT}/src/inodefence/mutator/m1.py", "a", "b"),
    edit(f"{ROOT}/src/inodefence/execution/README.md", "a", "--privileged"),
    # subagents doing their own job
    bash("make check", **WORKER),
    edit(f"{ROOT}/src/inodefence/mutator/m1.py", "a", "b", **WORKER),
    edit(f"{ROOT}/docs/LOG.md", "a", "b", agent_id="a2", agent_type="runtime"),
    bash("git switch jiwoong/x && make check 2>&1 | tail -5", agent_id="a3", agent_type="verifier"),
    # orchestrator metadata access
    tool("Agent", {"subagent_type": "builder", "prompt": "P2-a"}, **ORCHESTRATOR),
    tool("Agent", {"subagent_type": "verifier", "prompt": "x", "model": "opus"}, **ORCHESTRATOR),
    tool("Read", {"file_path": f"{ROOT}/docs/BACKLOG.md"}, **ORCHESTRATOR),
    tool("Read", {"file_path": f"{ROOT}/.claude/agents/builder.md"}, **ORCHESTRATOR),
    tool("Glob", {"pattern": "src/**/*.py"}, **ORCHESTRATOR),
    tool("Skill", {"skill": "autoloop"}, **ORCHESTRATOR),
    bash("echo $DEVCONTAINER; which docker", **ORCHESTRATOR),
    bash("git status --short && git branch -a", **ORCHESTRATOR),
    bash("git log --oneline -5 main..jiwoong/x", **ORCHESTRATOR),
    bash("git diff --stat main...jiwoong/x", **ORCHESTRATOR),
    bash("tail -5 docs/WORKLOG.md | head -2", **ORCHESTRATOR),
    bash("grep -n 막힘 docs/WORKLOG.md", **ORCHESTRATOR),
    bash("grep -n 대기 docs/BACKLOG.md", **ORCHESTRATOR),
]

BLOCKED = [
    # R1 banned documents
    write(f"{ROOT}/docs/c1-impact-audit.md"),
    write(f"{ROOT}/docs/Phase2-Readiness.md"),
    write(f"{ROOT}/docs/research/handoff-2026.md"),
    write(f"{ROOT}/docs/audits/new.md"),
    write(f"{ROOT}/docs/preserve-notes.md"),
    write("docs/n05-qualification-v2.md"),
    bash("touch docs/handoff.md"),
    # R2 main pushes and merges
    bash("git push origin main"),
    bash("git push origin HEAD:main"),
    bash("git push -f origin +main"),
    bash("git push origin :main"),
    bash("git push origin jiwoong/x:refs/heads/main"),
    bash("git push --all origin"),
    bash("git -C /workspaces/InodeFence push origin main"),
    bash("git add . && git commit -m x && git push origin main"),
    bash("git push origin main", **WORKER),
    bash("gh pr merge 130 --squash"),
    # R3 isolation weakening
    bash("docker run --privileged alpine true"),
    bash("docker run --cap-add SYS_ADMIN alpine"),
    bash("docker run --security-opt seccomp=unconfined alpine"),
    bash("docker run --pid=host alpine"),
    bash("docker run --network host alpine"),
    bash("docker run -v /:/host alpine"),
    bash("bash -c 'docker run --privileged x'"),
    # R4 allowlist and guard configuration
    edit(f"{ROOT}/src/inodefence/execution/docker_client.py", "a", "b"),
    write(f"{ROOT}/src/inodefence/execution/container.py"),
    edit(f"{ROOT}/src/inodefence/model/isolation.py", "a", "b"),
    edit(f"{ROOT}/.claude/settings.json", "a", "b"),
    write(f"{ROOT}/.claude/settings.local.json"),
    write(f"{ROOT}/.claude/hooks/guard.py"),
    write("/home/vscode/.claude/settings.json"),
    bash("sed -i 's/version/run/' src/inodefence/execution/docker_client.py"),
    bash("echo '{\"disableAllHooks\": true}' > .claude/settings.local.json"),
    bash("rm .claude/hooks/guard.py"),
    edit(f"{ROOT}/src/inodefence/execution/docker_client.py", "a", "b", **WORKER),
    # R5 weakening flags written into files
    edit(f"{ROOT}/scripts/local_node_tar_smoke.sh", "docker run", "docker run --privileged"),
    write(f"{ROOT}/docker-compose.yml", "services:\n  t:\n    privileged: true\n"),
    # R6 orchestrator sees metadata only
    tool("Read", {"file_path": f"{ROOT}/src/inodefence/oracle/contracts.py"}, **ORCHESTRATOR),
    tool("Read", {"file_path": f"{ROOT}/docs/LOG.md"}, **ORCHESTRATOR),
    tool("Grep", {"pattern": "C1", "path": "src"}, **ORCHESTRATOR),
    tool("Edit", {"file_path": f"{ROOT}/docs/WORKLOG.md"}, **ORCHESTRATOR),
    tool("WebFetch", {"url": "https://github.com/x/y/pull/1.diff"}, **ORCHESTRATOR),
    tool("Agent", {"subagent_type": "general-purpose", "prompt": "x"}, **ORCHESTRATOR),
    tool("Agent", {"subagent_type": "builder", "prompt": "x", "model": "fable"}, **ORCHESTRATOR),
    tool("Skill", {"skill": "code-review"}, **ORCHESTRATOR),
    bash("cat src/inodefence/oracle/contracts.py", **ORCHESTRATOR),
    bash("git diff main...jiwoong/x", **ORCHESTRATOR),
    bash("git show HEAD", **ORCHESTRATOR),
    bash("git log -p -1", **ORCHESTRATOR),
    bash("make check", **ORCHESTRATOR),
    bash("grep -rn C1 src", **ORCHESTRATOR),
    bash("echo $(cat src/inodefence/oracle/contracts.py)", **ORCHESTRATOR),
    bash("python -c 'print(open(\"src/x.py\").read())'", **ORCHESTRATOR),
    # R7 runtime never writes code
    edit(f"{ROOT}/src/inodefence/mutator/m1.py", "a", "b", agent_id="a2", agent_type="runtime"),
    # R8 verifier is read-only
    edit(f"{ROOT}/docs/WORKLOG.md", "a", "b", agent_id="a3", agent_type="verifier"),
    bash("git commit -am x", agent_id="a3", agent_type="verifier"),
    bash("sed -i s/a/b/ src/x.py", agent_id="a3", agent_type="verifier"),
    bash("echo x > src/x.py", agent_id="a3", agent_type="verifier"),
]


def _id(payload: dict) -> str:
    who = payload.get("agent_type", "main")
    detail = payload["tool_input"].get("command") or payload["tool_input"].get("file_path")
    return f"{who}:{payload['tool_name']}:{detail or payload['tool_input']}"[:90]


@pytest.mark.parametrize("payload", ALLOWED, ids=_id)
def test_guard_allows_normal_work(payload: dict) -> None:
    result = run_guard(payload)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("payload", BLOCKED, ids=_id)
def test_guard_blocks_with_reason(payload: dict) -> None:
    result = run_guard(payload)
    assert result.returncode == 2
    assert "BLOCKED" in result.stderr


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(repo), "GIT_CONFIG_NOSYSTEM": "1"},
    )


def _repo_on_branch(tmp_path: Path, branch: str) -> Path:
    """A throwaway git repo whose checked-out branch is ``branch`` (one empty commit)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", branch)
    _git(
        repo,
        "-c",
        "user.name=guard-test",
        "-c",
        "user.email=guard-test@example.invalid",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    return repo


@pytest.mark.parametrize(
    ("branch", "allowed"),
    [("jiwoong/p0-some-work", True), ("main", False)],
    ids=["work-branch:allowed", "main:blocked-R2"],
)
def test_guard_resolves_push_head_against_current_branch(
    tmp_path: Path, branch: str, allowed: bool
) -> None:
    """``git push origin HEAD`` pushes main only when HEAD *is* main.

    The verdict must follow the checked-out branch of the payload's ``cwd``, not the
    branch this test suite happens to run on (main CI checks out main; PR CI does not).
    """
    repo = _repo_on_branch(tmp_path, branch)
    result = run_guard({**bash("git push origin HEAD"), "cwd": str(repo)})
    if allowed:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode == 2
        assert "R2" in result.stderr
        assert "BLOCKED" in result.stderr


def test_guard_blocks_new_banned_doc_but_not_existing_one() -> None:
    existing = ROOT / "docs" / "audits" / "final-runtime-integration-audit-v1.md"
    assert existing.is_file()
    assert run_guard(write(str(existing))).returncode == 0


def test_guard_fails_closed_on_bad_input() -> None:
    result = subprocess.run(
        [sys.executable, str(GUARD)], input="not json", capture_output=True, text=True, check=False
    )
    assert result.returncode == 2


def test_settings_run_guard_for_every_tool_and_fail_closed() -> None:
    hooks = json.loads(SETTINGS.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert [entry["matcher"] for entry in hooks] == ["*"]
    command = hooks[0]["hooks"][0]["command"]
    assert ".claude/hooks/guard.py" in command
    assert command.rstrip().endswith("|| exit 2")
