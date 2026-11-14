"""``inodefence``: the user-facing command for extractor targets and their results.

One command, the same options for every target, so someone can use the tool without knowing the
repository layout or ``make``. Subcommands wrap the existing drivers; this module adds no run logic.

Built now (no per-target exploration hook needed):

- ``targets`` — list the extractors and what each supports (regression check, auto-prepare,
  exploration), with a reason when a feature is unsupported; ``--json`` for machines.
- ``doctor`` — check the environment (Python, Docker, the runtime directory, and whether the
  repository can be located) and say how to fix each problem.
- ``summary`` — render a result file as a one-page summary (wraps
  :mod:`inodefence.target_result_summary`).

``verify`` (regression check), ``explore`` and ``status`` (live progress of a running exploration)
follow once the shared options and the adapter exploration hooks are in place.

Distribution (today): only ``src/inodefence/`` is packaged; the drivers (``scripts/``) and the
per-target build assets (``tools/``) live outside it, so only an *editable* install from a clone
works. :func:`repo_root` finds the repository explicitly — ``INODEFENCE_HOME`` if set, otherwise the
editable-install location — and never guesses; ``doctor`` and every command that needs the drivers
report why when it cannot be found.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

PROG = "inodefence"

#: What ``repo_root`` must see to accept a directory as the InodeFence repository.
_REPO_MARKERS = (Path("scripts") / "run_target.py", Path("tools"))
REPO_NOT_FOUND = (
    "InodeFence repository not found. Install from a clone with `pip install -e .`, or set "
    "INODEFENCE_HOME to the repository root (it must contain scripts/run_target.py and tools/)."
)


def _is_repo(root: Path) -> bool:
    return (root / _REPO_MARKERS[0]).is_file() and (root / _REPO_MARKERS[1]).is_dir()


def repo_root() -> Path | None:
    """Locate the repository explicitly, or ``None``; never a guess.

    ``INODEFENCE_HOME`` wins when set. Otherwise, in an editable install this file is
    ``<repo>/src/inodefence/cli.py``, so its grandparent's parent is the repository root; a wheel
    install has no such layout and returns ``None`` (the drivers and build assets are not bundled).
    """
    env = os.environ.get("INODEFENCE_HOME")
    if env:
        root = Path(env).expanduser()
        return root if _is_repo(root) else None
    candidate = Path(__file__).resolve().parents[2]
    return candidate if _is_repo(candidate) else None


def target_support(root: Path) -> dict[str, dict[str, Any]]:
    """Read the regression and exploration target registries from the drivers (single source)."""
    for path in (str(root), str(root / "src")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from scripts.run_target import TARGETS as REGRESSION_TARGETS
    from scripts.run_target_explore import TARGETS as EXPLORE_TARGETS

    support: dict[str, dict[str, Any]] = {}
    for name in sorted(REGRESSION_TARGETS):
        explores = name in EXPLORE_TARGETS
        support[name] = {
            "regression": True,
            "auto_prepare": True,
            "explore": explores,
            "explore_reason": None if explores else "no exploration hook for this target yet",
        }
    return support


def cmd_targets(args: argparse.Namespace) -> int:
    root = repo_root()
    if root is None:
        print(REPO_NOT_FOUND, file=sys.stderr)
        return 3
    try:
        support = target_support(root)
    except Exception as error:  # a broken or partial checkout: say so, do not pretend
        print(f"could not read the target registry from {root}: {error}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(support, indent=2, sort_keys=True))
        return 0
    header = f"{'target':16} {'regression':11} {'auto-prepare':13} explore"
    print(header)
    print("-" * len(header))
    for name, feats in support.items():
        explore = "yes" if feats["explore"] else f"no ({feats['explore_reason']})"
        print(f"{name:16} {'yes':11} {'yes':13} {explore}")
    return 0


def _check(label: str, ok: bool, detail: str) -> bool:
    print(f"[{'OK' if ok else 'FAIL'}] {label}: {detail}")
    return ok


def cmd_doctor(args: argparse.Namespace) -> int:
    ok = True
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok &= _check(
        "Python 3.12",
        sys.version_info[:2] == (3, 12),
        version if sys.version_info[:2] == (3, 12) else f"found {version}; InodeFence needs 3.12",
    )
    root = repo_root()
    ok &= _check(
        "repository",
        root is not None,
        f"{root}" if root is not None else REPO_NOT_FOUND,
    )
    docker = shutil.which("docker")
    ok &= _check(
        "Docker",
        docker is not None,
        f"{docker}" if docker else "docker not on PATH; targets run in Docker on the host",
    )
    runtime = Path(os.environ.get("INODEFENCE_RUNTIME_ROOT", "/var/lib/inodefence"))
    runtime_ok = runtime.is_dir()
    ok &= _check(
        "runtime directory (for make check / tests)",
        runtime_ok,
        f"{runtime}"
        if runtime_ok
        else f"{runtime} missing; create it with: "
        f'sudo mkdir -p {runtime} && sudo chown "$(id -u):$(id -g)" {runtime}',
    )
    print("\nall checks passed" if ok else "\nsome checks failed (see FAIL lines above)")
    return 0 if ok else 1


def cmd_summary(args: argparse.Namespace) -> int:
    from inodefence.target_result import TargetResultError
    from inodefence.target_result_summary import summarize_file

    try:
        text = summarize_file(args.result, verify_inputs=not args.no_verify_inputs)
    except (TargetResultError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG, description="run extractor targets and read their results"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    targets = sub.add_parser("targets", help="list the extractors and what each supports")
    targets.add_argument("--json", action="store_true", help="machine-readable output")
    targets.set_defaults(func=cmd_targets)

    doctor = sub.add_parser("doctor", help="check the environment and say how to fix problems")
    doctor.set_defaults(func=cmd_doctor)

    summary = sub.add_parser("summary", help="render a result file as a one-page summary")
    summary.add_argument("result", type=Path, help="a result.json")
    summary.add_argument("-o", "--output", type=Path, help="write to this file (else stdout)")
    summary.add_argument(
        "--no-verify-inputs",
        action="store_true",
        help="skip re-hashing the saved input TARs (the summary records that it was skipped)",
    )
    summary.set_defaults(func=cmd_summary)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
