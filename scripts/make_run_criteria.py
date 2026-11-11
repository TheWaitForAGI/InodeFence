"""Write the host-qualification criteria file for one execution SHA (D047; #347).

The file is what ``run_exp0 --expected-images`` and ``qualify_host --criteria`` both read:
three expected image ids, the Docker Engine of each host, the sha256 of every shared
execution-path file (``launcher_guards.SHARED_PATH_FILES``), the execution SHA, and the
thresholds fixed in ``experiments/configs/host-qualification-v1.md`` section 5.

Run it in the clean detached worktree of the execution SHA, on the host whose values it
records. It only reads: ``git rev-parse``/``git status``, ``docker version`` and
``docker image inspect`` (no pull, no build). It refuses a tree that is not clean or not at
the given SHA, thresholds that differ from the design file, and an existing output file
with different content (an equal file is left as it is). The file it writes passes
``qualify_host``'s own criteria checks.

    python -m scripts.make_run_criteria --execution-sha <40 hex> --host HOST1 \\
        [--engine HOST2=29.9.3] [--context <ctx>] --out <outside the worktree>/criteria.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from scripts import launcher_guards as guards
from scripts import qualify_host

DESIGN_FILE = Path("experiments/configs/host-qualification-v1.md")
#: Section 5 of the design file (Q7, Q9, Q10, cells). The file must still say so.
THRESHOLDS: Mapping[str, Any] = {
    "max_first_attempt_abort_ratio": "0.30",
    "max_unstable_steps_per_1000": "1",
    "max_cell_seconds": 7200,
    "expected_cells": 12,
}
DESIGN_PHRASES = ("≤ 0.30", "1,000개당 1건", "7200 s", "12셀")
TARGET_IMAGE = "inodefence-node-tar-effect:7.5.2"
LOCAL_IMAGES = qualify_host.LOCAL_IMAGE_NAMES
HOSTS = ("HOST1", "HOST2")

Docker = Callable[..., str]


class CriteriaError(RuntimeError):
    """The criteria file cannot be written as asked."""


def tree_state(tree: Path) -> tuple[str, bool]:
    """(HEAD, clean) of ``tree``; a tree that is not a git checkout is refused."""

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(tree), *args], capture_output=True, text=True, check=False
        )
        if done.returncode != 0:
            raise CriteriaError(f"git {' '.join(args)} failed in {tree}: {done.stderr.strip()}")
        return done.stdout.strip()

    return git("rev-parse", "HEAD"), git("status", "--porcelain") == ""


def check_design(tree: Path) -> None:
    text = (tree / DESIGN_FILE).read_text(encoding="utf-8")
    missing = [phrase for phrase in DESIGN_PHRASES if phrase not in text]
    if missing:
        raise CriteriaError(f"{DESIGN_FILE} no longer states {missing}: thresholds not confirmed")


def build_criteria(
    *,
    tree: Path,
    execution_sha: str,
    host: str,
    other_engines: Mapping[str, str],
    docker: Docker,
    target_image: str = TARGET_IMAGE,
    thresholds: Mapping[str, Any] | None = None,
    state: Callable[[Path], tuple[str, bool]] = tree_state,
) -> dict[str, Any]:
    if host not in HOSTS or any(name not in HOSTS or name == host for name in other_engines):
        raise CriteriaError(f"hosts must be {HOSTS}, this host once")
    head, clean = state(tree)
    if head != execution_sha:
        raise CriteriaError(f"tree HEAD {head} != --execution-sha {execution_sha}")
    if not clean:
        raise CriteriaError("the tree is not clean")
    check_design(tree)
    if thresholds is not None and dict(thresholds) != dict(THRESHOLDS):
        raise CriteriaError(f"thresholds {dict(thresholds)} differ from the design {THRESHOLDS}")
    shared = guards.shared_path_sha256(tree)
    missing = guards.missing_shared_paths(shared)
    if missing:
        raise CriteriaError(f"shared execution path files missing: {missing}")
    images = {
        name: docker("image", "inspect", name, "--format", "{{.Id}}")
        for name in (target_image, *LOCAL_IMAGES)
    }
    engines = {host: docker("version", "--format", "{{.Server.Version}}"), **other_engines}
    criteria = {
        "schema": qualify_host.CRITERIA_SCHEMA,
        **THRESHOLDS,
        "expected_image_ids": images,
        "expected_docker_engine": dict(sorted(engines.items())),
        "expected_shared_path_sha256": shared,
        "expected_execution_sha": execution_sha,
    }
    problems = qualify_host.criteria_problems(criteria)
    if problems or set(criteria) != qualify_host.CRITERIA_KEYS:
        raise CriteriaError(f"criteria would be refused by qualify_host: {problems}")
    return criteria


def write_once(path: Path, criteria: Mapping[str, Any]) -> str:
    """Write ``criteria`` to ``path`` unless a different file is there; return its sha256."""
    data = (json.dumps(criteria, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path.exists():
        if path.read_bytes() != data:
            raise CriteriaError(f"{path} exists with different content; not overwritten")
    else:
        path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    qualify_host.load_criteria(path, digest)  # the same checks the judgment runs
    return digest


def _engine(value: str) -> tuple[str, str]:
    host, separator, version = value.partition("=")
    if not separator or not version:
        raise argparse.ArgumentTypeError("--engine takes HOSTn=<version>")
    return host, version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--tree", type=Path, default=Path.cwd(), help="the execution SHA's tree")
    parser.add_argument("--execution-sha", required=True)
    parser.add_argument("--host", required=True, choices=HOSTS, help="the host this runs on")
    parser.add_argument("--engine", type=_engine, action="append", default=[])
    parser.add_argument("--context", default=None)
    parser.add_argument("--target-image", default=TARGET_IMAGE)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    prefix = ("--context", args.context) if args.context else ()

    def docker(*call: str) -> str:
        return guards.docker_cli(*prefix, *call)

    try:
        criteria = build_criteria(
            tree=args.tree.resolve(),
            execution_sha=args.execution_sha,
            host=args.host,
            other_engines=dict(args.engine),
            docker=docker,
            target_image=args.target_image,
        )
        digest = write_once(args.out, criteria)
    except (CriteriaError, RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"criteria not written: {error}", file=sys.stderr)
        return 2
    print(f"criteria: {args.out} sha256={digest}")
    print(f"shared files: {len(criteria['expected_shared_path_sha256'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
