"""``inodefence``: the user-facing command for extractor targets and their results.

One command, the same options for every target, so someone can use the tool without knowing the
repository layout or ``make``. Subcommands wrap the existing drivers; this module adds no run logic
and assembles no shell strings (argv goes straight to the driver), so user values are never
re-parsed as shell syntax.

- ``targets`` — list the extractors and what each supports (regression check, auto-prepare,
  exploration), with a reason when a feature is unsupported; ``--json`` for machines. Exploration
  support is read from each adapter's hook, so it updates on its own as a target's owner fills it.
- ``doctor`` — check the environment (Python, the repository, Docker, the runtime directory) and
  say how to fix each problem.
- ``verify`` — run the fixed-input regression check on a target (wraps the regression driver).
- ``explore`` — run a feedback-search exploration on a target's prepared image (wraps the
  exploration driver). More options (search / mutation policy, stop conditions, mirror, resume)
  are added here as the driver gains them; none is shown before it works.
- ``summary`` — render a result file as a one-page summary.

``status`` (live progress of a running exploration) follows the driver's streaming output.

Finding the repository and the out-of-package drivers is concentrated in :mod:`inodefence.locate`;
only an editable install from a clone works today, and ``doctor`` and every command that needs the
drivers say why when the repository cannot be found.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from inodefence.locate import (
    EXPLORE_DRIVER,
    REPO_NOT_FOUND,
    VERIFY_DRIVER,
    repo_root,
    run_driver,
    target_support,
)

PROG = "inodefence"
DEFAULT_VERIFY_OUT = Path.home() / "inodefence-target-run"
DEFAULT_EXPLORE_OUT = Path.home() / "inodefence-explore"


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
        import json

        print(json.dumps(support, indent=2, sort_keys=True))
        return 0
    header = f"{'target':16} {'regression':11} {'auto-prepare':13} {'explore':8} target options"
    print(header)
    print("-" * len(header))
    for name, feats in support.items():
        explore = "yes" if feats["explore"] else f"no ({feats['explore_reason']})"
        opts = feats.get("options") or []
        names = ", ".join(f"--{o['name']}" + ("" if o["required"] else "?") for o in opts) or "—"
        print(f"{name:16} {'yes':11} {'yes':13} {explore:8} {names}")
    print("\ntarget options: a trailing '?' marks optional. Pass them to `verify` / `explore`.")
    return 0


def _check(label: str, ok: bool, detail: str) -> bool:
    print(f"[{'OK' if ok else 'FAIL'}] {label}: {detail}")
    return ok


def cmd_doctor(args: argparse.Namespace) -> int:
    import os

    ok = True
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok &= _check(
        "Python 3.12",
        sys.version_info[:2] == (3, 12),
        version if sys.version_info[:2] == (3, 12) else f"found {version}; InodeFence needs 3.12",
    )
    root = repo_root()
    ok &= _check("repository", root is not None, f"{root}" if root is not None else REPO_NOT_FOUND)
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


def _forward(driver: str, argv: list[str]) -> int:
    root = repo_root()
    if root is None:
        print(REPO_NOT_FOUND, file=sys.stderr)
        return 3
    return run_driver(root, driver, argv)


def cmd_verify(args: argparse.Namespace) -> int:
    argv = ["--target", args.target]
    for version in args.version:
        argv += ["--version", version]
    for extraction_filter in args.extraction_filter:
        argv += ["--extraction-filter", extraction_filter]
    if args.auto_prepare:
        argv.append("--auto-prepare")
    if args.image_tag_suffix:
        argv += ["--image-tag-suffix", args.image_tag_suffix]
    if args.dry_run:
        argv.append("--dry-run")
    else:
        argv += ["--out", str(args.out)]
    return _forward(VERIFY_DRIVER, argv + args.extra)


def cmd_explore(args: argparse.Namespace) -> int:
    argv = [
        "--target",
        args.target,
        "--version",
        args.version,
        "--budget",
        str(args.budget),
        "--seed",
        str(args.seed),
        "--out",
        str(args.out),
    ]
    if args.auto_prepare:
        argv.append("--auto-prepare")
    if args.image_tag_suffix:
        argv += ["--image-tag-suffix", args.image_tag_suffix]
    if args.dry_run:
        argv.append("--dry-run")
    return _forward(EXPLORE_DRIVER, argv + args.extra)


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

    verify = sub.add_parser("verify", help="run the fixed-input regression check on a target")
    verify.add_argument("--target", default="node-tar")
    verify.add_argument("--version", action="append", default=[], help="repeatable")
    verify.add_argument("--extraction-filter", action="append", default=[], help="repeatable")
    verify.add_argument("--auto-prepare", action="store_true")
    verify.add_argument("--image-tag-suffix", default="")
    verify.add_argument("--out", type=Path, default=DEFAULT_VERIFY_OUT)
    verify.add_argument("--dry-run", action="store_true", help="print the plan; run nothing")
    verify.set_defaults(func=cmd_verify)

    explore = sub.add_parser("explore", help="run a feedback-search exploration on a target")
    explore.add_argument("--target", default="node-tar")
    explore.add_argument("--version", required=True, help="latest or an exact version")
    explore.add_argument("--budget", type=int, default=20)
    explore.add_argument("--seed", type=int, default=123)
    explore.add_argument("--auto-prepare", action="store_true")
    explore.add_argument("--image-tag-suffix", default="")
    explore.add_argument("--out", type=Path, default=DEFAULT_EXPLORE_OUT)
    explore.add_argument("--dry-run", action="store_true", help="print the plan; run nothing")
    explore.set_defaults(func=cmd_explore)

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


#: Subcommands that forward unknown flags to a driver (target options the adapter declares).
_FORWARDING = {"verify", "explore"}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    if extra and args.command not in _FORWARDING:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    args.extra = extra
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
