"""``inodefence``: the user-facing command for extractor targets and their results.

One command, the same options for every target, so someone can use the tool without knowing the
repository layout or ``make``. Subcommands wrap the existing drivers; this module adds no run logic
and assembles no shell strings (argv goes straight to the driver), so user values are never
re-parsed as shell syntax.

- ``targets`` — list the extractors and what each supports (regression check, auto-prepare,
  exploration), with a reason when a feature is unsupported; ``--json`` for machines. Exploration
  support is read from each adapter's hook, so it updates on its own as a target's owner fills it.
- ``doctor`` — check the environment (Python, the repository, the user config and output folder,
  Docker CLI and daemon access, locally prepared images, the runtime directory) and say how to fix
  each problem. A check it cannot settle is printed as ``UNKNOWN``, never as ``OK``.
- ``verify`` — run the fixed-input regression check on a target (wraps the regression driver).
- ``explore`` — run a feedback-search exploration on a target's prepared image (wraps the
  exploration driver). More options (search / mutation policy, stop conditions, mirror, resume)
  are added here as the driver gains them; none is shown before it works. It prints live progress
  lines; ``--quiet`` / ``--verbose`` change that (:mod:`inodefence.drivers.progress`).
- ``summary`` — render a result file as a one-page summary.

``status`` (live progress of a running exploration) follows the driver's streaming output.

Finding the repository and the out-of-package drivers is concentrated in :mod:`inodefence.locate`;
only an editable install from a clone works today, and ``doctor`` and every command that needs the
drivers say why when the repository cannot be found. User settings (repository location, output
base folder) are read by :mod:`inodefence.user_config`; research settings are never read from there.

``--out`` is resolved against the caller's working directory before it reaches a driver (drivers
run with the repository as their working directory), and an output folder inside the repository
is refused here: results may hold real violating inputs and the repository is public.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from inodefence.app.doctor import looks_cloud_synced, relative_output_base
from inodefence.locate import (
    EXPLORE_DRIVER,
    REPLAY_DRIVER,
    VERIFY_DRIVER,
    RepositoryCodeMissing,
    repo_not_found_message,
    repo_root,
    run_driver,
    target_support,
)
from inodefence.user_config import (
    EXPLORE_OUT_NAME,
    VERIFY_OUT_NAME,
    UserConfig,
    UserConfigError,
    load_user_config,
)

PROG = "inodefence"
#: Same runtime default as :mod:`inodefence.runtime` (read from the environment only).
RUNTIME_ROOT_DEFAULT = "/var/lib/inodefence"
DOCKER_TIMEOUT_SECONDS = 30
#: Exit code for a refusal before anything runs (drivers' "nothing judged"); see README 종료 코드.
REFUSED = 3
#: ``explore --profile`` choices, the default first (``drivers.runtime.policy.PROFILES``; a test
#: keeps the two in step -- the drivers are not imported here).
RUNTIME_PROFILES = ("strict", "fast")


def cmd_targets(args: argparse.Namespace) -> int:
    root = repo_root()
    if root is None:
        print(repo_not_found_message(), file=sys.stderr)
        return 3
    try:
        support = target_support(root)
    except RepositoryCodeMissing as error:  # markers only: never run another tree instead
        print(error, file=sys.stderr)
        return 3
    except Exception as error:  # a broken or partial checkout: say so, do not pretend
        print(f"could not read the target registry from {root}: {error}", file=sys.stderr)
        return 3
    if args.json:
        import json

        print(json.dumps(support, indent=2, sort_keys=True))
        return 0
    from inodefence.app.targets import TABLE_HEADER, TABLE_NOTE, table_rows
    from inodefence.ui.console import Console

    Console(version=_package_version()).targets(
        table_rows(support), TABLE_HEADER, TABLE_NOTE, support
    )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from inodefence.app import doctor
    from inodefence.ui.console import Console

    report = doctor.run(
        args.user_config, args.user_config_error, details=getattr(args, "details", False)
    )
    Console(version=_package_version()).doctor(report)
    return report.exit_code


def _forward(driver: str, argv: list[str], command: str) -> int:
    root = repo_root()
    if root is None:
        print(repo_not_found_message(), file=sys.stderr)
        return REFUSED
    try:
        return run_driver(root, driver, argv, prog=f"inodefence {command}")
    except RepositoryCodeMissing as error:
        print(error, file=sys.stderr)
        return REFUSED


def _out_problem(out: Path) -> str | None:
    """Why ``out`` cannot be the output folder, or None (checked before anything runs)."""
    if out.exists() and not out.is_dir():
        return f"--out {out} exists and is not a folder"
    probe = out
    while not probe.exists():
        probe = probe.parent
    if not probe.is_dir():
        return f"--out {out} cannot be created: {probe} is not a folder"
    if not os.access(probe, os.W_OK | os.X_OK):
        where = "is not writable" if probe == out else f"cannot be created: {probe} is not writable"
        return f"--out {out} {where}"
    return None


def _resolve_out(args: argparse.Namespace, default_name: str) -> Path | None:
    """The absolute output folder, or None (printed why) when it must be refused.

    Relative paths are taken against the caller's working directory: the driver runs with the
    repository as its working directory, so forwarding a relative path would land inside the repo.
    """
    out = args.out
    if out is None:
        config: UserConfig | None = args.user_config
        if config is None:
            print(f"error: no --out given and {args.user_config_error}", file=sys.stderr)
            return None
        relative = relative_output_base(config)
        if relative:
            print(f"error: no --out given and {relative}", file=sys.stderr)
            return None
        out = config.default_out(default_name)
    out = Path(os.path.abspath(out.expanduser()))
    root = repo_root()
    if root is not None and out.resolve().is_relative_to(root.resolve()):
        print(
            f"error: --out {out} is inside the repository {root}. Results may hold real violating "
            "inputs and the repository is public; choose a folder outside it.",
            file=sys.stderr,
        )
        return None
    problem = _out_problem(out)
    if problem is not None:
        print(f"error: {problem}; choose another folder", file=sys.stderr)
        return None
    synced = looks_cloud_synced(out.resolve())
    if synced:
        print(
            f"warning: --out {out} looks like a cloud-synced folder ({synced!r}); results may hold "
            "real violating inputs. Prefer a local folder (name-based guess only).",
            file=sys.stderr,
        )
    return out


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
    # Resolved and checked on --dry-run too, so the plan shows (and refuses) where it would write.
    out = _resolve_out(args, VERIFY_OUT_NAME)
    if out is None:
        return REFUSED
    argv += ["--out", str(out)]
    started = time.time()
    code = _forward(VERIFY_DRIVER, argv + args.extra, "verify")
    if not args.dry_run:
        _verify_screen(out, started)
    return code


def _verify_screen(out: Path, started: float) -> None:
    """On an interactive terminal with Rich: a result screen per cell this run wrote, after the
    driver's own lines (which are unchanged). Elsewhere nothing is added, so the output and the
    exit code are the driver's, byte for byte."""
    from inodefence.ui.console import Console

    console = Console(version=_package_version())
    if not console.uses_rich:
        return
    from inodefence.app.runs import read_verify

    def written_now(summary: object) -> bool:
        path = getattr(summary, "result_path", None)
        try:
            return path is not None and path.stat().st_mtime >= started - 1
        except OSError:
            return False

    console.verify_results([s for s in read_verify(out) if written_now(s)], out)


def cmd_tui(args: argparse.Namespace) -> int:
    """The read-only terminal dashboard (optional ``tui`` extra). 3 when it cannot start."""
    if args.refresh <= 0:
        print("error: --refresh must be > 0", file=sys.stderr)
        return 3
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "error: inodefence tui needs an interactive terminal (stdin and stdout)",
            file=sys.stderr,
        )
        return 3
    from inodefence.ui.tui import TuiUnavailable, run

    try:
        return run(extra=args.folders, refresh=args.refresh)
    except TuiUnavailable as error:
        print(f"error: {error}", file=sys.stderr)
        return 3


def cmd_dashboard(args: argparse.Namespace) -> int:
    """The local read-only web dashboard (optional ``web`` extra). 0 when stopped (Ctrl-C),
    3 when it did not start (no FastAPI/uvicorn, or the server could not start)."""
    from inodefence.ui.web import WebUnavailable, run

    try:
        return run(extra=args.folders, repo_root=repo_root(), host=args.host, port=args.port)
    except WebUnavailable as error:
        print(f"error: {error}", file=sys.stderr)
        return 3
    except SystemExit as stop:  # uvicorn exits when it cannot start (e.g. the port is taken)
        if stop.code in (0, None):
            return 0
        print(
            f"error: the dashboard did not start on {args.host}:{args.port} "
            "(is the port already in use? try --port)",
            file=sys.stderr,
        )
        return 3


def cmd_compare(args: argparse.Namespace) -> int:
    from inodefence.app.runs import compare_results, read_result
    from inodefence.ui.console import Console

    a, b = read_result(args.a), read_result(args.b)
    Console(version=_package_version()).compare(a, b, compare_results(a, b))
    return 0 if a.has_values and b.has_values else 2


def cmd_explore(args: argparse.Namespace) -> int:
    if not args.auto_prepare and not args.dry_run:
        print(
            "error: explore needs --auto-prepare. It reuses the target image when it is already "
            "prepared, and otherwise builds it with Docker (may download packages). Add "
            "--auto-prepare to allow that, or --dry-run to see the plan without running anything.",
            file=sys.stderr,
        )
        return REFUSED
    out = _resolve_out(args, EXPLORE_OUT_NAME)
    if out is None:
        return REFUSED
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
        str(out),
    ]
    if args.max_unjudged_ratio is not None:
        argv += ["--max-unjudged-ratio", str(args.max_unjudged_ratio)]
    if args.auto_prepare:
        argv.append("--auto-prepare")
    if args.image_tag_suffix:
        argv += ["--image-tag-suffix", args.image_tag_suffix]
    if args.dry_run:
        argv.append("--dry-run")
    # Terminal output (drivers.progress): progress lines by default, --quiet none, --verbose the
    # launcher's raw output as before. Exit codes and the result lines are the same in all three.
    argv += ["--output", "quiet" if args.quiet else "stream" if args.verbose else "progress"]
    if args.profile != RUNTIME_PROFILES[0]:  # the default (strict) forwards nothing
        argv += ["--profile", args.profile]
    return _forward(EXPLORE_DRIVER, argv + args.extra, "explore")


def cmd_replay(args: argparse.Namespace) -> int:
    # The driver runs with the repository as its working directory, while the recorded command
    # (``inodefence replay violations/run-NNNNNN``) is run from the live folder: resolve here.
    argv = [str(args.case_dir.expanduser().resolve()), "--rounds", str(args.rounds)]
    if args.case:
        argv += ["--case", args.case]
    if args.dry_run:
        argv.append("--dry-run")
    started = time.time()
    code = _forward(REPLAY_DRIVER, argv, "replay")
    if not args.dry_run:
        _replay_screen(args.case_dir.expanduser().resolve(), started)
    return code


def _replay_screen(case_dir: Path, started: float) -> None:
    """On an interactive Rich terminal: the replay record(s) this run wrote, after the driver's
    unchanged lines (``<case>.replay-<UTC>/replay.json`` beside the case folder, or inside a
    result folder for ``--case``). Elsewhere nothing is added."""
    from inodefence.ui.console import Console

    console = Console(version=_package_version())
    if not console.uses_rich:
        return
    from inodefence.app.runs import read_replay

    found = {
        *case_dir.parent.glob(f"{case_dir.name}.replay-*/replay.json"),
        *case_dir.glob("**/*.replay-*/replay.json"),
    }

    def written_now(path: Path) -> bool:
        try:
            return path.stat().st_mtime >= started - 1
        except OSError:
            return False

    console.replay_results([read_replay(p) for p in sorted(found) if written_now(p)])


def cmd_status(args: argparse.Namespace) -> int:
    from inodefence.live_exploration import live_dirs_status
    from inodefence.target_result import (
        TargetResultError,
        load_target_result,
        no_extraction_warning,
    )

    folder = args.folder
    # `explore --out X` writes under X/target-explore/; accept X itself as well.
    nested = folder / "target-explore"
    if (
        not (folder / "result.json").is_file()
        and not (folder / "live").is_dir()
        and nested.is_dir()
    ):
        folder = nested
    from inodefence.ui.console import Console

    console = None if args.plain else Console(version=_package_version())
    rich = console is not None and console.uses_rich
    rows: list[dict[str, object]] = []  # the Rich screen's rows (the same values as the lines)
    # A running (or finished) exploration's live folder: progress snapshot + violation cases.
    live = live_dirs_status(folder)
    if not rich:
        for block in live:
            print(block)
    results = (
        [folder / "result.json"]
        if (folder / "result.json").is_file()
        else sorted(folder.glob("*/result.json"))
    )
    if not results:
        if live:
            if rich and console is not None:
                console.status(folder, live, rows)
            return 0  # still running (or stopped before writing result.json): live view only
        print(
            f"no result.json and no live progress under {folder}. A running exploration writes "
            "live/progress.json and live/violations/; a finished run writes result.json.",
            file=sys.stderr,
        )
        return 2
    unreadable = 0
    for result_path in results:
        try:
            result = load_target_result(result_path, verify_inputs=False)
        except (TargetResultError, OSError, ValueError) as error:
            print(f"{result_path}: unreadable ({error})", file=sys.stderr)
            unreadable += 1
            rows.append({"cell": result_path.parent.name, "verdict": "ERROR", "error": str(error)})
            continue
        line = f"{result_path.parent.name}: {result.verdict.value} target={result.target}"
        if result.axes.target_version:
            line += f" version={result.axes.target_version}"
        line += f" runs={result.executed} violations={len(result.violating_cases)}"
        campaign = result.campaign
        if campaign is not None:
            if campaign.runs_to_first_violation is not None:
                line += f" first-violation={campaign.runs_to_first_violation}"
            if campaign.stopped_early:
                line += " (stopped early)"
        # Same wording as summary.md, the explore output line and the live view (one function);
        # for exploration results only, as in the summary. Verdict and exit code are unchanged.
        warning = no_extraction_warning(result.termination_counts) if campaign else None
        if rich:
            rows.append(
                {
                    "cell": result_path.parent.name,
                    "verdict": result.verdict.value,
                    "target": result.target,
                    "version": result.axes.target_version,
                    "runs": result.executed,
                    "violations": len(result.violating_cases),
                    "first": campaign.runs_to_first_violation if campaign else None,
                    "stopped_early": bool(campaign and campaign.stopped_early),
                    "warning": warning,
                    "path": str(result_path),
                }
            )
            continue
        print(line)
        if warning:
            print(f"  ** {warning} **")
    if rich and console is not None:
        console.status(folder, live, rows)
    return 2 if unreadable else 0  # a result that could not be read is not a clean status


def cmd_summary(args: argparse.Namespace) -> int:
    from inodefence.target_result import TargetResultError
    from inodefence.target_result_summary import summarize_file

    try:
        text = summarize_file(args.result, verify_inputs=not args.no_verify_inputs)
    except (TargetResultError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.output is None:
        if not args.plain:
            from inodefence.ui.console import Console

            console = Console(version=_package_version())
            if console.uses_rich:
                console.markdown(text)  # the same Markdown, drawn; pipes and -o get the text
                return 0
        sys.stdout.write(text)
    else:
        try:
            args.output.write_text(text, encoding="utf-8")
        except OSError as error:
            print(f"error: cannot write {args.output}: {error}", file=sys.stderr)
            return 2
    return 0


def _package_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("inodefence")
    except PackageNotFoundError:
        return "unknown (not installed)"


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


class _RefusalParser(argparse.ArgumentParser):
    """A subcommand parser whose usage errors exit 3, not argparse's 2.

    For ``verify`` / ``explore`` (and ``replay``) the exit code carries the result, so a
    usage error must not exit 2 and be read as an ERROR verdict; it is a refusal like the drivers'.
    """

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(REFUSED, f"{self.prog}: error: {message}\n")


#: Exit codes shown under ``--help`` (help text only; the codes are the drivers', unchanged).
_RUN_EXIT_CODES = (
    "exit codes: 0 PASS, 1 FAIL (a violation was judged), 2 ERROR (no verdict, e.g. the run\n"
    "stopped after its controller started; no result is published), 3 refused before anything\n"
    "ran (bad option, no repository, missing image without --auto-prepare, existing result)."
)
_REPLAY_EXIT_CODES = (
    "exit codes: 0 every round ran, 1 not every round ran (finished rounds are kept),\n"
    "2 cannot replay, 3 stopped before running (image absent, Docker did not answer,\n"
    "run name taken), 4 unsupported."
)
_TARGET_HELP = "extractor to run (default: node-tar; `inodefence targets` lists them)"
_SUFFIX_HELP = "suffix for the target image tag, to keep a separate prepared image (default: none)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG, description="run extractor targets and read their results"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_package_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    targets = sub.add_parser("targets", help="list the extractors and what each supports")
    targets.add_argument("--json", action="store_true", help="machine-readable output")
    targets.set_defaults(func=cmd_targets)

    doctor = sub.add_parser(
        "doctor",
        help="check the environment and say how to fix problems",
        epilog="exit codes: 0 no check failed (UNKNOWN lines are not failures), 1 a check failed.",
    )
    doctor.add_argument(
        "--details",
        action="store_true",
        help="also list every image and leftover by name, with how to remove a leftover",
    )
    doctor.set_defaults(func=cmd_doctor)

    verify = sub.add_parser(
        "verify",
        help="run the fixed-input regression check on a target",
        epilog=_RUN_EXIT_CODES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    verify.add_argument("--target", default="node-tar", help=_TARGET_HELP)
    verify.add_argument(
        "--version", action="append", default=[], help="target version (required; repeatable)"
    )
    verify.add_argument(
        "--extraction-filter",
        action="append",
        default=[],
        help="python-tarfile only (repeatable); see `inodefence targets`",
    )
    verify.add_argument(
        "--auto-prepare",
        action="store_true",
        help="build a missing target image with Docker (else a missing image stops the run)",
    )
    verify.add_argument("--image-tag-suffix", default="", help=_SUFFIX_HELP)
    verify.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output folder outside the repository, relative to the current directory "
        f"(default: <output base>/{VERIFY_OUT_NAME}; see `doctor`)",
    )
    verify.add_argument("--dry-run", action="store_true", help="print the plan; run nothing")
    verify.__class__ = _RefusalParser  # usage errors exit 3 (see _RefusalParser)
    verify.set_defaults(func=cmd_verify)

    explore = sub.add_parser(
        "explore",
        help="run a feedback-search exploration on a target",
        epilog=_RUN_EXIT_CODES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    explore.add_argument("--target", default="node-tar", help=_TARGET_HELP)
    explore.add_argument("--version", required=True, help="latest or an exact version (required)")
    explore.add_argument(
        "--budget", type=_positive_int, default=20, help="number of runs (default: 20)"
    )
    explore.add_argument("--seed", type=int, default=123, help="search seed (default: 123)")
    explore.add_argument(
        "--max-unjudged-ratio",
        type=float,
        default=None,
        help="ERROR ceiling for the un-judged ratio (default: the driver's)",
    )
    explore.add_argument(
        "--auto-prepare",
        action="store_true",
        help="required for a real run: reuse the prepared image or build it with Docker",
    )
    explore.add_argument("--image-tag-suffix", default="", help=_SUFFIX_HELP)
    explore.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output folder outside the repository, relative to the current directory "
        f"(default: <output base>/{EXPLORE_OUT_NAME}; see `doctor`)",
    )
    explore.add_argument("--dry-run", action="store_true", help="print the plan; run nothing")
    noise = explore.add_mutually_exclusive_group()
    noise.add_argument(
        "--quiet",
        action="store_true",
        help="no progress lines (the result lines and errors still print)",
    )
    noise.add_argument(
        "--verbose",
        action="store_true",
        help="show the launcher's raw output instead of progress lines",
    )
    explore.add_argument(
        "--profile",
        choices=RUNTIME_PROFILES,
        default=RUNTIME_PROFILES[0],
        help="runtime profile (default: strict, the verified execution). fast skips the per-run "
        "rebuild of the shared controller/helper images when they are verified to be this "
        "checkout's (measured: about 1.5 s less setup per run; nothing per case changes). The "
        "same inputs are run and judged; `replay` always runs strict",
    )
    explore.__class__ = _RefusalParser
    explore.set_defaults(func=cmd_explore)

    replay = sub.add_parser(
        "replay",
        help="re-run one explored case N times on the same image and record the reproduction rate",
        epilog=_REPLAY_EXIT_CODES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    replay.add_argument(
        "case_dir",
        type=Path,
        help="a live/violations/run-NNNNNN folder, or an exploration result folder (with --case)",
    )
    replay.add_argument(
        "--case", help="with a result folder: the saved input to replay (e.g. step-7)"
    )
    replay.add_argument(
        "--rounds", type=_positive_int, default=3, help="how many re-runs (default 3)"
    )
    replay.add_argument(
        "--dry-run", action="store_true", help="check input, image and support; run nothing"
    )
    replay.__class__ = _RefusalParser
    replay.set_defaults(func=cmd_replay)

    status = sub.add_parser(
        "status",
        help="show a run's live progress and violation cases while it runs, and its result after",
        epilog="exit codes: 0 shown, 2 nothing to show, an unreadable result, or a usage error.",
    )
    status.add_argument(
        "folder", type=Path, help="an exploration output folder (live/ and/or result.json)"
    )
    status.add_argument(
        "--plain",
        action="store_true",
        help="the plain lines even on an interactive terminal (pipes always get them)",
    )
    status.set_defaults(func=cmd_status)

    summary = sub.add_parser(
        "summary",
        help="render a result file as a one-page summary",
        epilog="exit codes: 0 written, 2 unreadable result, output not written, or a usage error.",
    )
    summary.add_argument("result", type=Path, help="a result.json")
    summary.add_argument("-o", "--output", type=Path, help="write to this file (else stdout)")
    summary.add_argument(
        "--plain",
        action="store_true",
        help="print the Markdown text even on an interactive terminal (pipes and -o always do)",
    )
    summary.add_argument(
        "--no-verify-inputs",
        action="store_true",
        help="skip re-hashing the saved input TARs (the summary records that it was skipped)",
    )
    summary.set_defaults(func=cmd_summary)

    compare = sub.add_parser(
        "compare",
        help="compare two results case by case: same input (SHA-256) and each verdict",
        epilog="exit codes: 0 shown, 2 a result could not be read, or a usage error.",
    )
    compare.add_argument("a", type=Path, help="a result.json (shown as A)")
    compare.add_argument("b", type=Path, help="another result.json (shown as B)")
    compare.set_defaults(func=cmd_compare)

    tui = sub.add_parser(
        "tui",
        help="read-only full-screen dashboard of the runs on this host (optional 'tui' extra)",
        epilog="exit codes: 0 quit, 3 not started (no Textual, not an interactive terminal, "
        "bad --refresh). Reads the default explore/verify output folders plus FOLDER ...; "
        "starts, stops, deletes and writes nothing.",
    )
    tui.add_argument("folders", nargs="*", type=Path, metavar="FOLDER", help="extra folders")
    tui.add_argument(
        "--refresh", type=float, default=1.0, help="seconds between re-reads (default 1)"
    )
    tui.set_defaults(func=cmd_tui)

    dashboard = sub.add_parser(
        "dashboard",
        help="local read-only web dashboard of the runs on this host (optional 'web' extra)",
        epilog="exit codes: 0 stopped (Ctrl-C), 3 not started (no FastAPI/uvicorn, or the "
        "server could not start). Serves 127.0.0.1 by default; reads the default output "
        "folders plus FOLDER ...; starts, stops, deletes and writes nothing.",
    )
    dashboard.add_argument("folders", nargs="*", type=Path, metavar="FOLDER", help="extra folders")
    dashboard.add_argument("--host", default="127.0.0.1", help="address (default 127.0.0.1)")
    dashboard.add_argument("--port", type=int, default=8765, help="port (default 8765)")
    dashboard.set_defaults(func=cmd_dashboard)

    return parser


#: Subcommands that forward unknown flags to a driver (target options the adapter declares).
_FORWARDING = {"verify", "explore"}
#: Subcommands that run a target driver; a refusal before the driver runs exits 3 like the driver.
_TARGET_COMMANDS = {"targets", "verify", "explore", "replay"}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    if extra and args.command not in _FORWARDING:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    args.extra = extra
    # A broken user config stops every command except `doctor`, which reports it as a FAIL line.
    # Target commands use the drivers' "nothing judged" code 3 (2 means an ERROR verdict there).
    try:
        args.user_config, args.user_config_error = load_user_config(), None
    except UserConfigError as error:
        args.user_config, args.user_config_error = None, str(error)
        if args.command != "doctor":
            print(f"error: user config: {error}", file=sys.stderr)
            return 3 if args.command in _TARGET_COMMANDS else 2
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
