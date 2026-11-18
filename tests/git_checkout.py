"""Test helpers for code that reads git metadata, so the suite also runs from a ``git archive``
copy (a tarball, no ``.git``).

* :func:`head_or_none`: the checkout's HEAD, or ``None`` outside a git checkout -- what the product
  code records then (it writes no revision rather than a guess).
* :func:`require_git_checkout`: for a test whose subject is git itself (worktree, ignore rules).
  Outside a git checkout it skips with the reason, except under CI (``CI`` set, as GitHub Actions
  does), where a missing checkout is a failure: CI must run these tests, never skip them.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def head_or_none() -> str | None:
    """HEAD of the repository the tests run from, or ``None`` when it is not a git checkout."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False
        )
    except OSError:  # no git executable
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def require_git_checkout(reason: str) -> None:
    """Skip (outside CI) or fail (under CI) when the tests do not run from a git checkout."""
    if head_or_none() is not None:
        return
    message = f"needs a git checkout: {reason}"
    if os.environ.get("CI"):
        pytest.fail(f"CI must run this test from a git checkout ({message})")
    pytest.skip(message)
