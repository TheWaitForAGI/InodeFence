"""``inodefence doctor``'s checks as data: one :class:`Item` per check, nothing printed.

The checks, their verdicts (OK / WARN / FAIL / UNKNOWN / INFO) and their wording are the ones the
command has always made; this module only returns them instead of printing them, so the console,
the TUI and the web dashboard show the same items (:mod:`inodefence.ui.console` draws them).
Everything here is read-only: nothing is created, changed or removed. Standard library only.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from inodefence.locate import (
    RepositoryCodeMissing,
    check_repository_code,
    repo_not_found_message,
    repo_root,
)
from inodefence.user_config import EXPLORE_OUT_NAME, VERIFY_OUT_NAME, UserConfig

if TYPE_CHECKING:  # the health module is loaded lazily
    from inodefence.drivers.runtime.health import Residue

#: Same runtime default as :mod:`inodefence.runtime` (read from the environment only).
RUNTIME_ROOT_DEFAULT = "/var/lib/inodefence"
DOCKER_TIMEOUT_SECONDS = 30
STATUSES = ("OK", "WARN", "FAIL", "UNKNOWN", "INFO")


@dataclass(frozen=True)
class Item:
    """One doctor check.

    ``value`` is the main line. ``parts`` are short pieces shown together (the image groups),
    ``more`` further lines, ``hints`` what to do next (each drawn after an arrow). ``counted``:
    whether the item can change the exit code (the running-code line never does).
    """

    label: str
    status: str
    value: str
    more: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()
    parts: tuple[str, ...] = ()
    counted: bool = True

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown doctor status {self.status!r}")
        for name in ("more", "hints", "parts"):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class Report:
    """All items, in the order doctor shows them, and the verdict they give."""

    items: tuple[Item, ...]

    @property
    def failed(self) -> bool:
        return any(item.status == "FAIL" and item.counted for item in self.items)

    @property
    def unknown(self) -> int:
        return sum(1 for item in self.items if item.status == "UNKNOWN" and item.counted)

    @property
    def exit_code(self) -> int:
        """0 no check failed (UNKNOWN is not a failure), 1 a check failed (unchanged)."""
        return 1 if self.failed else 0

    @property
    def summary(self) -> str:
        if self.failed:
            return "some checks failed (see FAIL lines above)"
        return "no check failed" + (
            f"; {self.unknown} UNKNOWN (not verified, see above)" if self.unknown else ""
        )


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


def looks_cloud_synced(path: Path) -> str | None:
    for part in path.parts:
        lowered = part.lower()
        if lowered in _SYNCED_MOUNT_NAMES:
            return part
        for name in _SYNCED_FOLDER_NAMES:
            if name in lowered:
                return part
    return None


def relative_output_base(config: UserConfig) -> str | None:
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


def _split_fix(detail: str) -> tuple[str, tuple[str, ...]]:
    """``problem; fix`` (one wording shared with the commands) -> the problem and a → hint."""
    problem, sep, fix = detail.rpartition("; ")
    return (problem, (fix,)) if sep else (detail, ())


def _output_base_check(config: UserConfig, root: Path | None) -> Item:
    base = config.output_base
    path = Path(base.value)
    label = "output folder"
    relative = relative_output_base(config)
    if relative:
        problem, hints = _split_fix(relative)
        return Item(label, "FAIL", problem, hints=hints)
    where = f"{path} ({base.source})"
    if root is not None and path.resolve().is_relative_to(root.resolve()):
        return Item(
            label,
            "FAIL",
            f"{where} is inside the repository {root}",
            hints=(
                "outputs must be outside it: set INODEFENCE_OUTPUT_DIR to a folder outside "
                "the repository",
            ),
        )
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    move = ("set INODEFENCE_OUTPUT_DIR to a folder you can write to",)
    if not existing.is_dir():
        return Item(label, "FAIL", f"{where}: {existing} exists and is not a folder", hints=move)
    if not os.access(existing, os.W_OK):
        return Item(label, "FAIL", f"{where}: {existing} is not writable by you", hints=move)
    synced = looks_cloud_synced(path.resolve())
    if synced:
        return Item(
            label,
            "WARN",
            f"{where} looks like a cloud-synced folder ({synced!r} in the path); violating inputs "
            "should not be uploaded",
            more=("(name-based guess only; a synced folder with another name is not detected)",),
            hints=("set INODEFENCE_OUTPUT_DIR to a local folder",),
        )
    return Item(
        label,
        "OK",
        where,
        more=(
            f"default --out: {config.default_out(VERIFY_OUT_NAME)}, "
            f"{config.default_out(EXPLORE_OUT_NAME)}",
        ),
    )


def _docker_checks(details: bool) -> list[Item]:
    docker = shutil.which("docker")
    items = [
        Item("Docker CLI", "OK", f"{docker}")
        if docker
        else Item(
            "Docker CLI",
            "FAIL",
            "docker not on PATH",
            hints=(
                "install Docker (Docker Desktop, or Docker Engine on Linux); targets run in "
                "Docker on the host",
            ),
        )
    ]
    if not docker:
        items.append(Item("Docker daemon access", "UNKNOWN", "no docker CLI to ask"))
        return items
    status, detail = _docker_server()
    problem, hints = _split_fix(detail) if status == "FAIL" else (detail, ())
    items.append(Item("Docker daemon access", status, problem, hints=hints))
    images = _local_images() if status == "OK" else None
    if images is None:
        items.append(
            Item("prepared images", "UNKNOWN", "could not list images (daemon not usable)")
        )
        return items
    readiness = (
        "which target/version each one serves is not checked here; "
        "`inodefence verify --target T --version V --dry-run` shows reuse/prepare per version "
        "(read-only), and --auto-prepare builds a missing one"
    )
    if images:
        groups = tuple(f"{name} {count}" for name, count in _image_groups(images).items())
        if details:
            items.append(
                Item(
                    "prepared images",
                    "OK",
                    f"{len(images)} inodefence-* image(s) present",
                    parts=groups,
                    more=tuple(images),
                    hints=(readiness,),
                )
            )
        else:
            items.append(
                Item(
                    "prepared images",
                    "OK",
                    f"{len(images)} inodefence-* image(s) present",
                    parts=groups,
                    hints=("full list: inodefence doctor --details",),
                )
            )
    else:
        # Not a failure: images are built on first use with --auto-prepare.
        items.append(Item("prepared images", "INFO", "none yet", hints=(readiness,)))
    return items


#: Image groups by target, read from the repository name (``inodefence-<target>`` or
#: ``inodefence-<target>-…``). Any other name counts as "other".
_IMAGE_TARGETS = ("python-tarfile", "node-tar", "decompress", "oras-go")


def _image_target(image: str) -> str:
    """The target an image (``repo:tag``) is counted under, from its repository name only.

    The name must be ``inodefence-<target>`` or begin ``inodefence-<target>-``: a target name
    elsewhere in it (``inodefence-helper-node-tar``) or a longer word (``inodefence-node-tarball``)
    is "other".
    """
    name = image.split(":", 1)[0].split("/")[-1].removeprefix("inodefence-")
    return next((t for t in _IMAGE_TARGETS if name == t or name.startswith(f"{t}-")), "other")


#: Display order of the groups.
IMAGE_GROUP_ORDER = ("node-tar", "decompress", "oras-go", "python-tarfile", "other")


def _image_groups(images: Sequence[str]) -> dict[str, int]:
    """How many of ``images`` (``repo:tag``) belong to each target, in a fixed order; read from
    the name only (what each image serves is not checked here)."""
    counts: Counter[str] = Counter(_image_target(image) for image in images)
    return {name: counts[name] for name in IMAGE_GROUP_ORDER if counts[name]}


@dataclass(frozen=True)
class PreparedImages:
    """The local ``inodefence-*`` images, grouped by target from their names (read-only).

    ``by_target`` maps a group (a target name or "other") to its ``repo:tag`` names, in
    :data:`IMAGE_GROUP_ORDER`; a group with no image is absent. Which version or option each
    image serves is not checked (as in doctor).
    """

    by_target: dict[str, tuple[str, ...]]

    @property
    def counts(self) -> dict[str, int]:
        return {name: len(images) for name, images in self.by_target.items()}

    @property
    def total(self) -> int:
        return sum(len(images) for images in self.by_target.values())


def prepared_images() -> PreparedImages | None:
    """The local images by target, or ``None`` when Docker could not list them (unknown -- not
    zero). Asks ``docker images`` once; changes nothing."""
    images = _local_images()
    if images is None:
        return None
    grouped: dict[str, list[str]] = {}
    for image in images:
        grouped.setdefault(_image_target(image), []).append(image)
    return PreparedImages(
        {name: tuple(grouped[name]) for name in IMAGE_GROUP_ORDER if name in grouped}
    )


def image_groups() -> dict[str, int] | None:
    """Per-target image counts (``prepared_images().counts``), or ``None`` when unknown."""
    images = prepared_images()
    return None if images is None else images.counts


def _find_residue():
    """Leftover InodeFence containers / volumes (read-only listing; see drivers.runtime.health)."""
    from inodefence.drivers.runtime import health  # stdlib-only leaf, loaded only by doctor

    return health.find_residue()


def _host_checks(config: UserConfig | None, daemon_ok: bool, details: bool) -> list[Item]:
    """Doctor lines added in 0.3 (PR 3): leftovers, free disk, memory. Nothing is changed.

    A leftover is WARN (reported with the commands a person may run; never removed); a listing
    Docker did not answer is UNKNOWN. Memory is always UNKNOWN: the Docker Desktop backend's
    memory (Windows commit limit) is not visible from inside WSL/Linux.
    """
    from inodefence.drivers.runtime import health

    items: list[Item] = []
    label = "leftover from old runs"
    if not daemon_ok:
        items.append(Item(label, "UNKNOWN", "not asked (daemon not usable)"))
    else:
        residue = _find_residue()
        if residue.clean:
            items.append(
                Item(label, "OK", "no container or volume labelled or named as InodeFence's")
            )
        else:
            status = "WARN" if residue.containers or residue.volumes else "UNKNOWN"
            items.append(_residue_check(label, status, residue, details))
    if config is not None and relative_output_base(config):
        items.append(Item("free disk", "UNKNOWN", "not checked (see output folder)"))
    elif config is not None:
        disk = health.disk_free(Path(config.output_base.value))
        status = "UNKNOWN" if disk.free_bytes is None else "WARN" if disk.low else "OK"
        hints = (
            ("free some space there, or set INODEFENCE_OUTPUT_DIR to a disk with room",)
            if status == "WARN"
            else ()
        )
        items.append(Item("free disk", status, disk.detail, hints=hints))
    memory = health.memory_status()
    if memory.state == "UNKNOWN" and not details:
        items.append(
            Item(
                "Docker memory",
                "UNKNOWN",
                "not checked on this host",
                hints=("why: inodefence doctor --details",),
            )
        )
    else:
        items.append(Item("Docker memory", memory.state, memory.detail))
    return items


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def _residue_check(label: str, status: str, residue: Residue, details: bool) -> Item:
    """The leftover line: counts by default; names and the removal guidance with ``--details``.

    The guidance and the unknown-listing sentences are :meth:`Residue.lines`' own wording.
    """
    found = [
        _plural(len(names), noun)
        for names, noun in ((residue.containers, "container"), (residue.volumes, "volume"))
        if names
    ]
    detail = (", ".join(found) + " (nothing was removed)") if found else "listing incomplete"
    lines = residue.lines()
    unknown = [line for line in lines if line.startswith("could not list")]
    if not details:
        hints = ("names and how to remove: inodefence doctor --details",) if found else ()
        return Item(label, status, detail, more=tuple(unknown), hints=hints)
    names = [f"container {name}" for name in residue.containers]
    names += [f"volume {name}" for name in residue.volumes]
    guidance = [line for line in lines if line.startswith("nothing was removed")]
    return Item(label, status, detail, more=(*names, *unknown), hints=tuple(guidance))


def _runtime_check(details: bool = False) -> Item:
    """Same rule as :func:`inodefence.runtime.open_runtime_directory` (meaning unchanged)."""
    from inodefence.runtime import RUNTIME_BASE

    runtime = Path(os.environ.get("INODEFENCE_RUNTIME_ROOT", RUNTIME_ROOT_DEFAULT))
    label = "runtime dir (dev only)"
    about = (
        ("development only: make check / tests; not used by verify / explore",) if details else ()
    )
    if (
        not runtime.is_absolute()
        or ".." in runtime.parts
        or not runtime.is_relative_to(RUNTIME_BASE)
    ):
        return Item(
            label,
            "FAIL",
            f"INODEFENCE_RUNTIME_ROOT={runtime} is not allowed: it must be an absolute path within "
            f"{RUNTIME_BASE}",
            more=about,
            hints=(f"unset INODEFENCE_RUNTIME_ROOT to use {RUNTIME_BASE}",),
        )
    if runtime.is_symlink():
        return Item(
            label,
            "FAIL",
            f"{runtime} is a symlink; the runtime root must not be one",
            more=about,
            hints=(f"set INODEFENCE_RUNTIME_ROOT to a real folder within {RUNTIME_BASE}",),
        )
    if runtime.is_dir():
        return Item(label, "OK", str(runtime), more=about)
    return Item(
        label,
        "WARN",
        f"{runtime} missing",
        more=about,
        hints=(
            "for development create it with: "
            f'sudo mkdir -p {runtime} && sudo chown "$(id -u):$(id -g)" {runtime}',
        ),
    )


def _repository_code_problem(root: Path) -> str | None:
    """The refusal every target command would print for ``root`` (marker-only / old clone)."""
    try:
        check_repository_code(root)
    except RepositoryCodeMissing as error:
        return str(error)
    return None


def _repository_check(config: UserConfig | None, details: bool = False) -> tuple[Item, Path | None]:
    """The repository line: the clone in use, where that choice came from, and why it is refused.

    Same resolution as every target command (:func:`inodefence.locate.repo_root`); this only adds
    the source (``INODEFENCE_HOME`` from the environment or the config file, else this install's
    checkout) and the check the commands make before running a driver.
    """
    label = "repository"
    about = ("needed by targets / verify / explore / replay",) if details else ()
    setting = config.get("INODEFENCE_HOME") if config is not None else None
    env_home = os.environ.get("INODEFENCE_HOME")
    if env_home:
        home, source = env_home, "INODEFENCE_HOME from the environment"
    elif setting is not None:
        home, source = setting.value, f"INODEFENCE_HOME from {setting.source}"
    else:
        home, source = None, "the checkout this inodefence is installed from"
    root = repo_root()
    fix = (
        "set INODEFENCE_HOME to an InodeFence clone, or update that clone (`git pull`); "
        "then run doctor again",
    )
    if root is None:
        return Item(label, "FAIL", repo_not_found_message(), more=about, hints=fix), None
    problem = _repository_code_problem(root)
    if problem:
        return Item(label, "FAIL", f"{root} ({source}): {problem}", more=about, hints=fix), None
    notes = []
    if setting is not None and setting.overridden is not None:
        notes.append(
            f"the config file's INODEFENCE_HOME={setting.overridden} is overridden by the "
            "environment"
        )
    if home is not None and root.resolve() != _running_code().parents[1].resolve():
        notes.append("target commands run this clone's code, not the code doctor runs from")
    status = "OK"
    hints: tuple[str, ...] = ()
    if home is not None and not Path(home).expanduser().is_absolute():
        status = "WARN"
        notes.append(
            f"INODEFENCE_HOME={home} is relative, so the clone it names depends on the working "
            "directory"
        )
        hints = ("set INODEFENCE_HOME to an absolute path",)
    return Item(label, status, f"{root} ({source})", more=(*notes, *about), hints=hints), root


def _running_code() -> Path:
    """The folder of the ``inodefence`` package this process runs (``.../inodefence``)."""
    import inodefence

    return Path(inodefence.__file__).resolve().parent


def _running_code_check(details: bool = False) -> Item:
    """Read-only: where the running ``inodefence`` code comes from (doctor; never changes rc).

    WARN only when ``PYTHONPATH`` is set and the package was loaded from under one of its entries:
    then the code running is that path's, not the installed one. Nothing is ignored or blocked.
    """
    code = _running_code()
    label = "inodefence code"
    about = ("the code running doctor / status / summary",) if details else ()
    for entry in filter(None, os.environ.get("PYTHONPATH", "").split(os.pathsep)):
        base = Path(entry).expanduser().resolve()
        if code.is_relative_to(base):
            return Item(
                label,
                "WARN",
                f"{code} is loaded from PYTHONPATH entry {entry}, not from the installed package",
                more=about,
                hints=("unset PYTHONPATH if that is not intended",),
            )
    return Item(label, "INFO", str(code), more=about)


def run(config: UserConfig | None, config_error: str | None, *, details: bool = False) -> Report:
    """Every check, in doctor's order. ``details`` adds the long lists and background lines;
    it never changes a verdict."""
    items: list[Item] = []
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info[:2] == (3, 12):
        items.append(Item("Python 3.12", "OK", version))
    else:
        items.append(
            Item(
                "Python 3.12",
                "FAIL",
                f"found {version}; InodeFence needs 3.12",
                hints=("install inodefence into a Python 3.12 environment",),
            )
        )
    if config is None:
        items.append(
            Item(
                "user config",
                "FAIL",
                str(config_error),
                hints=("fix the file and line named above (other commands refuse until then)",),
            )
        )
    else:
        detail = (
            str(config.config_path)
            if config.config_found
            else f"{config.config_path} not present (optional; defaults apply)"
        )
        items.append(Item("user config", "OK", detail))
    repository, root = _repository_check(config, details)
    items.append(repository)
    if config is not None:
        items.append(_output_base_check(config, root))
    docker = _docker_checks(details)
    items += docker
    daemon_ok = len(docker) > 1 and docker[1].status == "OK"
    items += _host_checks(config, daemon_ok, details)
    # INFO/WARN only: never changes the exit code.
    items.append(dataclasses.replace(_running_code_check(details), counted=False))
    items.append(_runtime_check(details))
    return Report(tuple(items))
