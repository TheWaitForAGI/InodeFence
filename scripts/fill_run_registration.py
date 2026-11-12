"""Fill the ``TBD-FREEZE`` values of a run registration into a copy outside the worktree.

The run registrations (``experiments/configs/run-exp0-eng-smoke-v1.md``,
``host-qualification-v1-run.md``, ``stop-path-smoke-<n>-v1.md``) leave values such as
``engine_sha`` and ``exposure_ledger_sha256`` as ``TBD-FREEZE`` until just before a run;
the parser refuses them while the token remains. ``run_exp0`` compares the checkout HEAD
with ``engine_sha``, so the filled file must not be a change to that checkout: this tool
writes the copy only outside the git worktree of the source.

It replaces ``<key> = TBD-FREEZE`` lines of the registration block for exactly the keys
given, refuses a given key that has no such line, refuses when any ``TBD-FREEZE`` is left
in the block, and never overwrites a different file. It prints both sha256 values.

    python -m scripts.fill_run_registration experiments/configs/host-qualification-v1-run.md \\
        --set engine_sha=<40 hex> --set exposure_ledger_sha256=<64 hex> \\
        --set execution_deadline=2026-11-20T12:00:00+09:00 \\
        --set host.HOST1.docker_engine=29.8.0 --set host.HOST2.docker_engine=29.9.3 \\
        --out <outside the worktree>/host-qual-filled.md
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

TOKEN = "TBD-FREEZE"
FENCE_OPEN = "```preregistration"
FENCE_CLOSE = "```"


class FillError(ValueError):
    """The copy cannot be written as asked."""


def worktree_root(path: Path) -> Path | None:
    """The git worktree containing ``path``, or None."""
    done = subprocess.run(
        ["git", "-C", str(path if path.is_dir() else path.parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(done.stdout.strip()).resolve() if done.returncode == 0 else None


def _block_bounds(text: str) -> tuple[int, int]:
    start = text.find(FENCE_OPEN)
    if start < 0:
        raise FillError(f"no {FENCE_OPEN} block")
    body = text.index("\n", start) + 1
    end = text.find("\n" + FENCE_CLOSE, body - 1)
    if end < 0:
        raise FillError("the registration block is not closed")
    return body, end + 1


def fill(text: str, values: Mapping[str, str]) -> str:
    body, end = _block_bounds(text)
    block = text[body:end]
    for key, value in values.items():
        if not value or TOKEN in value or "\n" in value:
            raise FillError(f"{key}: unusable value {value!r}")
        pattern = re.compile(rf"^{re.escape(key)} = {TOKEN}$", re.M)
        block, count = pattern.subn(f"{key} = {value}", block)
        if count != 1:
            raise FillError(f"{key} has no '{key} = {TOKEN}' line in the block")
    # Comment lines may mention the token (the templates say "Fill TBD-FREEZE ..."); the
    # parser ignores them, so only key lines count.
    left = [
        line for line in block.splitlines() if TOKEN in line and not line.lstrip().startswith("#")
    ]
    if left:
        raise FillError(f"{TOKEN} left in the block: {left}")
    return text[:body] + block + text[end:]


def write_copy(source: Path, out: Path, values: Mapping[str, str]) -> tuple[str, str]:
    root = worktree_root(source.resolve())
    resolved = out.resolve()
    if root is not None and (resolved == root or root in resolved.parents):
        raise FillError(f"{out} is inside the worktree {root}; write the copy outside it")
    original = source.read_bytes()
    filled = fill(original.decode("utf-8"), values).encode("utf-8")
    if out.exists() and out.read_bytes() != filled:
        raise FillError(f"{out} exists with different content; not overwritten")
    if not out.exists():
        out.write_bytes(filled)
    return hashlib.sha256(original).hexdigest(), hashlib.sha256(filled).hexdigest()


def _value(text: str) -> tuple[str, str]:
    key, separator, value = text.partition("=")
    if not separator or not key.strip():
        raise argparse.ArgumentTypeError("--set takes KEY=VALUE")
    return key.strip(), value.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("--set", dest="values", type=_value, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    values = dict(args.values)
    if len(values) != len(args.values):
        parser.error("each key at most once")
    try:
        source_sha, copy_sha = write_copy(args.source, args.out, values)
    except (FillError, OSError) as error:
        print(f"not filled: {error}", file=sys.stderr)
        return 2
    print(f"source {args.source} sha256={source_sha}")
    print(f"copy {args.out} sha256={copy_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
