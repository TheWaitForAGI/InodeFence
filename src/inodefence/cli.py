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
  are added here as the driver gains them; none is shown before it works.
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
import shutil
import subprocess
import sys
from pathlib import Path

from inodefence.locate import (
    EXPLORE_DRIVER,
    REPLAY_DRIVER,
    REPO_NOT_FOUND,
    VERIFY_DRIVER,
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


def _check(label: str, status: str, detail: str) -> str:
    """Print one doctor line. ``status``: OK, FAIL, WARN (not needed for every command), UNKNOWN."""
    print(f"[{status}] {label}: {detail}")
    return status


def _docker_server() -> tuple[str, str]:
    """Ask the daemon for its version the way the drivers do (``docker info``, default context).

    Returns (status, detail): OK with the server version, FAIL with the reason and fix, or UNKNOWN
    when the question could not be answered (timeout), which is not reported as a pass.
    """
    try:
        done = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return "UNKNOWN", f"`docker info` did not answer in {DOCKER_TIMEOUT_SECONDS}s"
    except OSError as error:
        return "FAIL", f"could not run docker ({error})"
    if done.returncode == 0 and done.stdout.strip():
        return "OK", f"server {done.stdout.strip()}"
    message = (done.stderr or done.stdout).strip().splitlines()
    first = message[0] if message else f"exit {done.returncode}"
    if "permission denied" in first.lower():
        return "FAIL", (
            f"{first}; your user may not use the Docker daemon (Linux: add it to the docker group "
            "and log in again)"
        )
    return "FAIL", f"{first}; start Docker (Docker Desktop, or `sudo service docker start`)"


def _local_images() -> list[str] | None:
    """Locally present ``inodefence-*`` images (read-only lookup), or None if docker cannot say."""
    try:
        done = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return sorted(
        {line for line in done.stdout.split() if line.split("/")[-1].startswith("inodefence-")}
    )


#: Folder names of common sync clients; a name match is a guess, reported as WARN, never as OK/FAIL.
_SYNCED_FOLDER_NAMES = (
    "google drive",
    "googledrive",
    "my drive",
    "내 드라이브",
    "onedrive",
    "dropbox",
)


#: Whole folder names that are typical sync mount points (e.g. ``~/Drive``), matched exactly.
_SYNCED_MOUNT_NAMES = ("drive", "gdrive")


def _looks_cloud_synced(path: Path) -> str | None:
    for part in path.parts:
        lowered = part.lower()
        if lowered in _SYNCED_MOUNT_NAMES:
            return part
        for name in _SYNCED_FOLDER_NAMES:
            if name in lowered:
                return part
    return None


def _output_base_check(config: UserConfig, root: Path | None) -> str:
    base = config.output_base
    path = Path(base.value)
    label = f"output folder base ({base.source})"
    if not path.is_absolute():
        return _check(label, "FAIL", f"{path} is not absolute; set INODEFENCE_OUTPUT_DIR to one")
    if root is not None and path.resolve().is_relative_to(root.resolve()):
        return _check(
            label, "FAIL", f"{path} is inside the repository {root}; outputs must be outside it"
        )
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not os.access(existing, os.W_OK):
        return _check(label, "FAIL", f"{path}: {existing} is not writable by you")
    synced = _looks_cloud_synced(path.resolve())
    if synced:
        return _check(
            label,
            "WARN",
            f"{path} looks like a cloud-synced folder ({synced!r} in the path); violating inputs "
            "should not be uploaded. Set INODEFENCE_OUTPUT_DIR to a local folder. "
            "(name-based guess only; a synced folder with another name is not detected)",
        )
    return _check(
        label,
        "OK",
        f"{path} (default --out: {config.default_out(VERIFY_OUT_NAME)}, "
        f"{config.default_out(EXPLORE_OUT_NAME)})",
    )


def _docker_checks() -> list[str]:
    docker = shutil.which("docker")
    statuses = [
        _check(
            "Docker CLI",
            "OK" if docker else "FAIL",
            f"{docker}" if docker else "docker not on PATH; targets run in Docker on the host",
        )
    ]
    if not docker:
        statuses.append(_check("Docker daemon access", "UNKNOWN", "no docker CLI to ask"))
        return statuses
    status, detail = _docker_server()
    statuses.append(_check("Docker daemon access", status, detail))
    images = _local_images() if status == "OK" else None
    if images is None:
        statuses.append(
            _check("prepared images", "UNKNOWN", "could not list images (daemon not usable)")
        )
        return statuses
    listed = ", ".join(images) if images else "none yet"
    statuses.append(
        _check(
            "prepared images",
            "UNKNOWN",
            f"inodefence-* images present: {listed}. Whether a given target/version is ready is "
            "not checked here; `inodefence verify --target T --version V --dry-run` shows it "
            "(read-only), and --auto-prepare builds a missing one",
        )
    )
    return statuses


def cmd_doctor(args: argparse.Namespace) -> int:
    statuses: list[str] = []
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info[:2] == (3, 12)
    statuses.append(
        _check(
            "Python 3.12",
            "OK" if py_ok else "FAIL",
            version if py_ok else f"found {version}; InodeFence needs 3.12",
        )
    )

    config: UserConfig | None = args.user_config
    if config is None:
        statuses.append(_check("user config", "FAIL", str(args.user_config_error)))
    else:
        detail = (
            str(config.config_path)
            if config.config_found
            else f"{config.config_path} not present (optional; defaults apply)"
        )
        statuses.append(_check("user config", "OK", detail))

    root = repo_root()
    statuses.append(
        _check(
            "repository (needed by targets / verify / explore / replay)",
            "OK" if root is not None else "FAIL",
            f"{root}" if root is not None else REPO_NOT_FOUND,
        )
    )
    if config is not None:
        statuses.append(_output_base_check(config, root))

    statuses += _docker_checks()

    runtime = Path(os.environ.get("INODEFENCE_RUNTIME_ROOT", RUNTIME_ROOT_DEFAULT))
    runtime_ok = runtime.is_dir()
    statuses.append(
        _check(
            "runtime directory (development only: make check / tests; not used by "
            "verify / explore)",
            "OK" if runtime_ok else "WARN",
            f"{runtime}"
            if runtime_ok
            else f"{runtime} missing; for development create it with: "
            f'sudo mkdir -p {runtime} && sudo chown "$(id -u):$(id -g)" {runtime}',
        )
    )

    failed = "FAIL" in statuses
    unknown = statuses.count("UNKNOWN")
    if failed:
        print("\nsome checks failed (see FAIL lines above)")
    else:
        print(
            "\nno check failed"
            + (f"; {unknown} UNKNOWN (not verified, see above)" if unknown else "")
        )
    return 1 if failed else 0


def _forward(driver: str, argv: list[str], command: str) -> int:
    root = repo_root()
    if root is None:
        print(REPO_NOT_FOUND, file=sys.stderr)
        return REFUSED
    return run_driver(root, driver, argv, prog=f"inodefence {command}")


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
    synced = _looks_cloud_synced(out.resolve())
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
    return _forward(VERIFY_DRIVER, argv + args.extra, "verify")


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
    return _forward(EXPLORE_DRIVER, argv + args.extra, "explore")


def cmd_replay(args: argparse.Namespace) -> int:
    # The driver runs with the repository as its working directory, while the recorded command
    # (``inodefence replay violations/run-NNNNNN``) is run from the live folder: resolve here.
    argv = [str(args.case_dir.expanduser().resolve()), "--rounds", str(args.rounds)]
    if args.dry_run:
        argv.append("--dry-run")
    return _forward(REPLAY_DRIVER, argv, "replay")


def cmd_status(args: argparse.Namespace) -> int:
    from inodefence.live_exploration import live_dirs_status
    from inodefence.target_result import TargetResultError, load_target_result

    folder = args.folder
    # `explore --out X` writes under X/target-explore/; accept X itself as well.
    nested = folder / "target-explore"
    if (
        not (folder / "result.json").is_file()
        and not (folder / "live").is_dir()
        and nested.is_dir()
    ):
        folder = nested
    # A running (or finished) exploration's live folder: progress snapshot + violation cases.
    live = live_dirs_status(folder)
    for block in live:
        print(block)
    results = (
        [folder / "result.json"]
        if (folder / "result.json").is_file()
        else sorted(folder.glob("*/result.json"))
    )
    if not results:
        if live:
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
            continue
        line = f"{result_path.parent.name}: {result.verdict.value} target={result.target}"
        if result.axes.target_version:
            line += f" version={result.axes.target_version}"
        line += f" runs={result.executed} violations={len(result.violating_cases)}"
        campaign = result.campaign
        if campaign is not None:
            if campaign.runs_to_first_violation is not None:
                line += f" first-violation={campaign.runs_to_first_violation}"
            if getattr(campaign, "stopped_early", False):  # set once the large-campaign fields land
                line += " (stopped early)"
        print(line)
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

    For ``verify`` / ``explore`` the exit code carries the verdict (0 PASS, 1 FAIL, 2 ERROR), so a
    usage error must not exit 2 and be read as an ERROR verdict; it is a refusal like the drivers'.
    """

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(REFUSED, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG, description="run extractor targets and read their results"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_package_version()}")
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
    verify.add_argument(
        "--auto-prepare",
        action="store_true",
        help="build a missing target image with Docker (else a missing image stops the run)",
    )
    verify.add_argument("--image-tag-suffix", default="")
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

    explore = sub.add_parser("explore", help="run a feedback-search exploration on a target")
    explore.add_argument("--target", default="node-tar")
    explore.add_argument("--version", required=True, help="latest or an exact version")
    explore.add_argument("--budget", type=_positive_int, default=20)
    explore.add_argument("--seed", type=int, default=123)
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
    explore.add_argument("--image-tag-suffix", default="")
    explore.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output folder outside the repository, relative to the current directory "
        f"(default: <output base>/{EXPLORE_OUT_NAME}; see `doctor`)",
    )
    explore.add_argument("--dry-run", action="store_true", help="print the plan; run nothing")
    explore.__class__ = _RefusalParser
    explore.set_defaults(func=cmd_explore)

    replay = sub.add_parser(
        "replay",
        help="re-run one violation case N times on the same image and record the reproduction rate",
    )
    replay.add_argument("case_dir", type=Path, help="a live/violations/run-NNNNNN folder")
    replay.add_argument(
        "--rounds", type=_positive_int, default=3, help="how many re-runs (default 3)"
    )
    replay.add_argument(
        "--dry-run", action="store_true", help="check input, image and support; run nothing"
    )
    replay.set_defaults(func=cmd_replay)

    status = sub.add_parser(
        "status",
        help="show a run's live progress and violation cases while it runs, and its result after",
    )
    status.add_argument(
        "folder", type=Path, help="an exploration output folder (live/ and/or result.json)"
    )
    status.set_defaults(func=cmd_status)

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
