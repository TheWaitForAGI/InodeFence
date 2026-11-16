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
import shutil
import subprocess
import sys
from pathlib import Path

from inodefence.locate import (
    EXPLORE_DRIVER,
    REPLAY_DRIVER,
    VERIFY_DRIVER,
    RepositoryCodeMissing,
    check_repository_code,
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


def _relative_output_base(config: UserConfig) -> str | None:
    """Why the configured output base cannot be used, or None (one wording: doctor and commands).

    A relative ``INODEFENCE_OUTPUT_DIR`` would move the default ``--out`` with the working
    directory, so it is refused rather than resolved (an explicit ``--out`` may be relative).
    """
    base = config.output_base
    if Path(base.value).is_absolute():
        return None
    return (
        f"INODEFENCE_OUTPUT_DIR={base.value} ({base.source}) is not absolute; set it to an "
        "absolute path (a relative one would move with the working directory)"
    )


def _output_base_check(config: UserConfig, root: Path | None) -> str:
    base = config.output_base
    path = Path(base.value)
    label = f"output folder base ({base.source})"
    relative = _relative_output_base(config)
    if relative:
        return _check(label, "FAIL", relative)
    if root is not None and path.resolve().is_relative_to(root.resolve()):
        return _check(
            label, "FAIL", f"{path} is inside the repository {root}; outputs must be outside it"
        )
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.is_dir():
        return _check(label, "FAIL", f"{path}: {existing} exists and is not a folder")
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
    readiness = (
        "which target/version each one serves is not checked here; "
        "`inodefence verify --target T --version V --dry-run` shows reuse/prepare per version "
        "(read-only), and --auto-prepare builds a missing one"
    )
    if images:
        statuses.append(
            _check(
                "prepared images",
                "OK",
                f"{len(images)} inodefence-* image(s) present: {', '.join(images)}; {readiness}",
            )
        )
    else:
        # Not a failure: images are built on first use with --auto-prepare.
        statuses.append(_check("prepared images", "INFO", f"none yet; {readiness}"))
    return statuses


def _find_residue():
    """Leftover InodeFence containers / volumes (read-only listing; see drivers.runtime.health)."""
    from inodefence.drivers.runtime import health  # stdlib-only leaf, loaded only by doctor

    return health.find_residue()


def _host_checks(config: UserConfig | None, daemon_ok: bool) -> list[str]:
    """Doctor lines added in 0.3 (PR 3): leftovers, free disk, memory. Nothing is changed.

    A leftover is WARN (reported with the commands a person may run; never removed); a listing
    Docker did not answer is UNKNOWN. Memory is always UNKNOWN: the Docker Desktop backend's
    memory (Windows commit limit) is not visible from inside WSL/Linux.
    """
    from inodefence.drivers.runtime import health

    statuses = []
    label = "leftover containers / volumes (read-only; nothing is removed)"
    if not daemon_ok:
        statuses.append(_check(label, "UNKNOWN", "not asked (daemon not usable)"))
    else:
        residue = _find_residue()
        if residue.clean:
            statuses.append(_check(label, "OK", "none labelled or named as InodeFence's"))
        else:
            status = "WARN" if residue.containers or residue.volumes else "UNKNOWN"
            statuses.append(_check(label, status, "; ".join(residue.lines())))
    if config is not None and _relative_output_base(config):
        statuses.append(
            _check("free disk at the output folder base", "UNKNOWN", "not checked (see above)")
        )
    elif config is not None:
        disk = health.disk_free(Path(config.output_base.value))
        status = "UNKNOWN" if disk.free_bytes is None else "WARN" if disk.low else "OK"
        statuses.append(_check("free disk at the output folder base", status, disk.detail))
    memory = health.memory_status()
    statuses.append(_check("memory headroom for Docker", memory.state, memory.detail))
    return statuses


def _runtime_check() -> str:
    """Same rule as :func:`inodefence.runtime.open_runtime_directory` (meaning unchanged)."""
    from inodefence.runtime import RUNTIME_BASE

    runtime = Path(os.environ.get("INODEFENCE_RUNTIME_ROOT", RUNTIME_ROOT_DEFAULT))
    label = "runtime directory (development only: make check / tests; not used by verify / explore)"
    if (
        not runtime.is_absolute()
        or ".." in runtime.parts
        or not runtime.is_relative_to(RUNTIME_BASE)
    ):
        return _check(
            label,
            "FAIL",
            f"INODEFENCE_RUNTIME_ROOT={runtime} is not allowed: it must be an absolute path within "
            f"{RUNTIME_BASE} (unset it to use {RUNTIME_BASE})",
        )
    if runtime.is_symlink():
        return _check(label, "FAIL", f"{runtime} is a symlink; the runtime root must not be one")
    if runtime.is_dir():
        return _check(label, "OK", str(runtime))
    return _check(
        label,
        "WARN",
        f"{runtime} missing; for development create it with: "
        f'sudo mkdir -p {runtime} && sudo chown "$(id -u):$(id -g)" {runtime}',
    )


def _repository_code_problem(root: Path) -> str | None:
    """The refusal every target command would print for ``root`` (marker-only / old clone)."""
    try:
        check_repository_code(root)
    except RepositoryCodeMissing as error:
        return str(error)
    return None


def _repository_check(config: UserConfig | None) -> tuple[str, Path | None]:
    """The repository line: the clone in use, where that choice came from, and why it is refused.

    Same resolution as every target command (:func:`inodefence.locate.repo_root`); this only adds
    the source (``INODEFENCE_HOME`` from the environment or the config file, else this install's
    checkout) and the check the commands make before running a driver.
    """
    label = "repository (needed by targets / verify / explore / replay)"
    setting = config.get("INODEFENCE_HOME") if config is not None else None
    env_home = os.environ.get("INODEFENCE_HOME")
    if env_home:
        home, source = env_home, "INODEFENCE_HOME from the environment"
    elif setting is not None:
        home, source = setting.value, f"INODEFENCE_HOME from {setting.source}"
    else:
        home, source = None, "the checkout this inodefence is installed from"
    root = repo_root()
    if root is None:
        return _check(label, "FAIL", repo_not_found_message()), None
    problem = _repository_code_problem(root)
    if problem:
        return _check(label, "FAIL", f"{root} ({source}): {problem}"), None
    notes = []
    if setting is not None and setting.overridden is not None:
        notes.append(
            f"the config file's INODEFENCE_HOME={setting.overridden} is overridden by the "
            "environment"
        )
    if home is not None and root.resolve() != _running_code().parents[1].resolve():
        notes.append("target commands run this clone's code, not the code doctor runs from")
    status = "OK"
    if home is not None and not Path(home).expanduser().is_absolute():
        status = "WARN"
        notes.append(
            f"INODEFENCE_HOME={home} is relative, so the clone it names depends on the working "
            "directory; set an absolute path"
        )
    return _check(label, status, "; ".join([f"{root} ({source})", *notes])), root


def _running_code() -> Path:
    """The folder of the ``inodefence`` package this process runs (``.../inodefence``)."""
    import inodefence

    return Path(inodefence.__file__).resolve().parent


def _running_code_check() -> str:
    """Read-only: where the running ``inodefence`` code comes from (doctor; never changes rc).

    WARN only when ``PYTHONPATH`` is set and the package was loaded from under one of its entries:
    then the code running is that path's, not the installed one. Nothing is ignored or blocked.
    """
    code = _running_code()
    label = "inodefence code running doctor / status / summary"
    for entry in filter(None, os.environ.get("PYTHONPATH", "").split(os.pathsep)):
        base = Path(entry).expanduser().resolve()
        if code.is_relative_to(base):
            return _check(
                label,
                "WARN",
                f"{code} is loaded from PYTHONPATH entry {entry}, not from the installed package; "
                "unset PYTHONPATH if that is not intended",
            )
    return _check(label, "INFO", str(code))


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

    status, root = _repository_check(config)
    statuses.append(status)
    if config is not None:
        statuses.append(_output_base_check(config, root))

    docker = _docker_checks()
    statuses += docker
    statuses += _host_checks(config, daemon_ok=len(docker) > 1 and docker[1] == "OK")

    _running_code_check()  # INFO/WARN only: not counted (never changes the exit code)
    statuses.append(_runtime_check())

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
        relative = _relative_output_base(config)
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
    # Terminal output (drivers.progress): progress lines by default, --quiet none, --verbose the
    # launcher's raw output as before. Exit codes and the result lines are the same in all three.
    argv += ["--output", "quiet" if args.quiet else "stream" if args.verbose else "progress"]
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
        # Same wording as summary.md, the explore output line and the live view (one function);
        # for exploration results only, as in the summary. Verdict and exit code are unchanged.
        warning = no_extraction_warning(result.termination_counts) if campaign else None
        if warning:
            print(f"  ** {warning} **")
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
    explore.__class__ = _RefusalParser
    explore.set_defaults(func=cmd_explore)

    replay = sub.add_parser(
        "replay",
        help="re-run one violation case N times on the same image and record the reproduction rate",
        epilog=_REPLAY_EXIT_CODES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    replay.add_argument("case_dir", type=Path, help="a live/violations/run-NNNNNN folder")
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
    status.set_defaults(func=cmd_status)

    summary = sub.add_parser(
        "summary",
        help="render a result file as a one-page summary",
        epilog="exit codes: 0 written, 2 unreadable result, output not written, or a usage error.",
    )
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
