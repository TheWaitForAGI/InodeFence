"""One command per target: run it on fixed axes, judge C0/C1/C2, save the result and the inputs.

    make target-run TARGET=node-tar TARGET_VERSIONS="7.5.2 7.5.3"
    make target-run TARGET=python-tarfile TARGET_VERSIONS=3.12.16 TARGET_FILTERS=data
    python -m inodefence.drivers.run_target --target node-tar --version 7.5.2 --out DIR

A run is a list of cells. A cell is one fixed point on the target's axes
(``inodefence.target_result.TargetAxes``: ``target_version`` / ``runtime_version`` /
``extraction_filter``). ``--version`` is the target's version axis (node-tar: the package
version -> ``target_version``; python-tarfile: the exact interpreter ``X.Y.Z`` ->
``runtime_version``); ``--extraction-filter`` is the filter axis for targets that have one.
One invocation varies at most one axis: several ``--version`` together with several
``--extraction-filter`` is refused, so a configuration comparison and a version comparison never
mix in one run. For each cell this writes, under ``DIR/<cell dirname>/``:

- ``result.json``: the common ``inodefence-target-result-v1`` record
  (``inodefence.target_result``; label ``demo run``),
- ``inputs/<case>.tar``: every TAR that was extracted, named in ``repro_inputs`` with its SHA-256,
- ``raw/<case>.json``: the target's raw observation for that case, unchanged.

A cell directory that already has a ``result.json`` is refused; nothing is overwritten.

Benign-input control: the regression fixtures are all attack-shaped, so a target that declines
every one of them is ``PASS`` -- and so would be an image that cannot extract anything. Each cell
therefore first extracts ONE benign archive through the target's own run program, on the cell's
image, in this invocation (``TargetAdapter.benign``), prints ``TARGET-RUN BENIGN-CONTROL ok|FAILED``
and records it as ``benign_control`` in ``result.json`` (its archive and raw observation go to
``benign/``). A control that did not extract makes a cell that would be ``PASS`` an ``ERROR``
(exit 2); an observed violation stays ``FAIL``. The control archive is built here for this command
only; it is not a regression fixture (``make regression`` and ``regression_check.build_fixtures``
are unchanged) and not a search seed.

Targets are registered in ``TARGETS`` as ``"module:ATTRIBUTE"`` and loaded on use. Each entry is
a target-specific ``TargetAdapter`` in its own module (``scripts/run_<target>_target.py``), never
in this file or the common format module. All registered targets run in mode
``fixture-regression``: the same hand-built hard-link and symlink-write fixtures that
``make regression`` runs, each extracted in a disposable container (the host is never the
extraction target) that observes the post-extraction state of an external reference file beside
``extract/``. That observes C1 (inode identity shared) and C2 (reference changed) but not C0, so
C0 is ``null`` ("not observed", never "no violation"). Versions and filters are plain inputs; no
release id or CVE id is a decision condition.

Images (target-independent flow; ``AUTO_PREPARE`` / ``--auto-prepare``):

1. validate target, versions and axes (``adapter.cells``; unsupported values are refused with the
   adapter's reason);
2. check docker, then each distinct cell image (``RunCell.image_ref``): present -> reuse;
3. missing and no ``--auto-prepare`` (the default) -> one line per missing image, exit 3, nothing
   runs; missing and ``--auto-prepare`` -> ``adapter.prepare(cell)`` gives a ``PrepareStep``,
   run once per image; an unsupported step or a failed command is an explicit error and that
   image's cells get no verdict (exit 3);
4. run each cell; the image id is read before and after the run and must match the id that was
   reused or prepared (else no verdict, exit 3); that id goes into ``provenance.image_id``.

``--image-tag-suffix S`` (``IMAGE_TAG_SUFFIX``) appends ``S`` to every cell image tag, so a
missing-image -> prepare -> run path can be shown without touching any existing tag; the suffixed
tag is what ``provenance.image_ref`` records. Nothing here removes or retags an existing image.
``--dry-run`` prints, per cell, whether its image would be reused or prepared (read-only image
lookups only); it pulls, builds, runs and writes nothing.

Exit codes: 0 PASS, 1 FAIL, 2 ERROR (worst verdict over cells; a failed benign-input control is
ERROR: it is an observation failure after the run started), 3 nothing judged for some or all
cells (refused input or existing result, setup, preparation or image problem).
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, NoReturn

from inodefence.case_replay import ReplayHook
from inodefence.drivers import regression_check as rc
from inodefence.drivers.repo import code_checkout, require_repository_or_exit
from inodefence.drivers.runtime import health
from inodefence.drivers.runtime.session import RuntimeSession
from inodefence.target_result import (
    RUN_ERROR,
    BenignControl,
    CaseVerdict,
    Preparation,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)
from inodefence.target_result_summary import write_cell_summaries

REPO_ROOT = code_checkout()
RESULT_NAME = "result.json"


@dataclass(frozen=True, slots=True)
class CaseRun:
    """One executed case: its input bytes, the target's raw observation, and the verdict."""

    verdict: CaseVerdict
    tar: bytes
    raw: dict[str, Any]


#: Where a cell keeps its benign-control archive and raw observation (beside ``inputs/``).
BENIGN_TAR_PATH = "benign/benign-control.tar"
BENIGN_RAW_PATH = "benign/benign-control.json"


@dataclass(frozen=True, slots=True)
class BenignRun:
    """The benign-input control of one cell: the record, the archive and the raw observation."""

    control: BenignControl
    tar: bytes
    raw: dict[str, Any]


#: The benign control's one regular file (three bytes; nothing an extractor could object to).
BENIGN_NAME = "ok.txt"
BENIGN_CONTENT = b"ok\n"


def benign_archive(name: str = BENIGN_NAME) -> bytes:
    """The benign control archive: ONE regular file ``name``, deterministic bytes (ustar, mtime 0).

    Built for ``verify`` only -- never added to the regression fixtures or the search seeds.
    """
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:", format=tarfile.USTAR_FORMAT) as archive:
        info = tarfile.TarInfo(name)
        info.size, info.mode = len(BENIGN_CONTENT), 0o644
        archive.addfile(info, io.BytesIO(BENIGN_CONTENT))
    return out.getvalue()


def benign_from_raw(tar: bytes, raw: object, expected_path: str) -> BenignRun:
    """Judge a benign-control run from the run program's raw observation (all four targets' run
    programs report the same two fields): the extractor declined nothing and ``expected_path`` is
    in the extracted tree. Anything else -- a run error, a refusal, a missing file -- is "not
    extracted", with the reason in ``detail``."""
    record = raw if isinstance(raw, dict) else {"_run_error": True, "_reason": repr(raw)[:200]}
    tree = record.get("extract_tree")
    declined = record.get("declined")
    if record.get("_run_error"):
        why = record.get("_reason") or record.get("_stderr") or f"exit {record.get('_rc')}"
        extracted, detail = False, f"the run program gave no observation ({str(why)[:200]})"
    elif declined is not None:
        message = declined.get("message") if isinstance(declined, dict) else declined
        extracted, detail = (
            False,
            f"the extractor declined the benign archive ({str(message)[:200]})",
        )
    elif not isinstance(tree, dict) or expected_path not in tree:
        extracted, detail = False, f"{expected_path} was not extracted"
    else:
        extracted, detail = True, f"{expected_path} extracted, nothing declined"
    control = BenignControl(
        extracted=extracted,
        expected_path=expected_path,
        tar_path=BENIGN_TAR_PATH,
        tar_sha256=sha256(tar).hexdigest(),
        detail=detail,
    )
    return BenignRun(control, tar, record)


@dataclass(frozen=True, slots=True)
class RunCell:
    """One fixed point on the target's axes: where its result goes and which image runs it."""

    dirname: str
    axes: TargetAxes
    image_ref: str | None
    #: The image comes from the public registry, not a committed recipe: the run is labelled
    #: "exploratory demo run" and is never mixed with committed-recipe cells in one run.
    exploratory: bool = False


@dataclass(frozen=True, slots=True)
class PrepareStep:
    """How a target would make one missing cell image exist (pull and/or build).

    ``commands`` run in order from the repository root; ``None`` means automatic preparation is
    not supported for this cell, and ``reason`` says why (printed to the user unchanged). When
    supported, ``reason`` is a short description (e.g. "build from tools/x/Dockerfile"). The
    commands must create exactly ``image_ref`` and must not retag, overwrite or remove any other
    existing tag; they may use the network (the extraction run never does).
    """

    image_ref: str
    commands: tuple[tuple[str, ...], ...] | None
    reason: str


def prepare_unsupported(cell: RunCell) -> PrepareStep:
    """Default ``TargetAdapter.prepare``: no automatic preparation for this target yet."""
    return PrepareStep(
        image_ref=cell.image_ref or "",
        commands=None,
        reason="automatic image preparation is not implemented for this target yet",
    )


@dataclass(frozen=True, slots=True)
class TargetOption:
    """A target-specific explore/run option an adapter declares (node-tar / oras-go declare
    none; python-tarfile declares its extraction filter, decompress its package, etc.). The
    common driver reads these to accept, validate and forward values without any target-specific
    code; the declared options become the ``filters`` list passed to ``cells`` in order."""

    name: str
    description: str
    required: bool = False
    choices: tuple[str, ...] | None = None  # allowed values, or None for free-form
    single: bool = True  # exploration takes one value; target-run may take several


@dataclass(frozen=True, slots=True)
class PreparedTargetImage:
    """A prepared, version-verified extractor image handed to a target's explore hook."""

    target: str
    requested: str  # the spec asked for ("latest" or an exact version)
    version: str  # the exact version inside the image
    image_ref: str
    image_id: str
    exploratory: bool  # True: registry-prepared (no committed recipe)


# The ceiling an exploration's un-judged ratio is held to: above it the verdict is ERROR, not a
# quiet PASS (an un-judged step is one the oracle never evaluated -- a run error or a missing
# observation, not a rejection/crash/timeout the oracle judged). 0.2 is a generous default: a
# healthy run is ~0 un-judged, so this tolerates occasional infra flakiness while still catching a
# systemic observation failure that would otherwise read as PASS. Tighten it with
# ``--max-unjudged-ratio`` for a stricter run; the chosen value is recorded in the result so the
# verdict is reproducible from the file alone.
DEFAULT_MAX_UNJUDGED_RATIO = 0.2

#: ``--mutation-policy`` values exploration accepts (exploratory, opt-in): only the v2 grammar
#: policy ``MutationPolicy.V2_FREEZE3_FIXED_BASELINE`` (escape depth 0..3; a test pins the value
#: to the enum). Without the option a run uses each target's own default, unchanged. The v2.1
#: seed-corpus variant is not offered (its empty seed is refused by node-tar and its python-tarfile
#: record is not valid, #533).
EXPLORE_MUTATION_POLICIES = ("uniform-b-grammar-v2-freeze-3-fixed-baseline-v1",)
#: The targets whose exploration can run a ``--mutation-policy`` value; the explore driver refuses
#: the option for any other target before anything is prepared or run (exit 3).
MUTATION_POLICY_TARGETS = ("node-tar",)
#: D065: the targets whose ``--profile fast`` keeps the shared-image rebuild skip only. The D064
#: identity-probe interval is not applied there (no FAST acceptance was measured for them), so
#: their image identity is probed before every case, as STRICT does.
FAST_PER_CASE_IDENTITY_TARGETS = ("decompress", "oras-go")
#: The launcher environment variable that selects the mutation policy. An explore driver never
#: passes the caller's own value through: it sets it from ``ExploreOptions.mutation_policy`` (or
#: its target's default) and otherwise removes it, so a run without the option is the default run
#: whatever the caller's environment holds.
MUTATION_POLICY_ENV = "DEMO_MUTATION_POLICY"


#: The launcher environment variable that selects the search policy. Exploration runs each
#: target's fixed search policy; no explore driver passes the caller's own value through.
SEARCH_POLICY_ENV = "DEMO_POLICY"


def _drop_inherited(env: dict[str, str], name: str, instead: str) -> None:
    """Remove the caller's ``name`` from a launcher env, saying so in one stderr line.

    A run that used to choose a setting through this variable must not silently fall back to the
    default: the warning names the variable and what to do instead. stdout, the result and the
    exit code are unchanged.
    """
    inherited = env.pop(name, None)
    if inherited is not None:
        print(
            f"TARGET-EXPLORE WARNING: environment variable {name}={inherited} is ignored; "
            f"{instead}",
            file=sys.stderr,
        )


def drop_inherited_mutation_policy(env: dict[str, str]) -> None:
    """The caller's ``DEMO_MUTATION_POLICY`` never reaches a launcher (``--mutation-policy``)."""
    _drop_inherited(env, MUTATION_POLICY_ENV, "use --mutation-policy (node-tar exploration only)")


def drop_inherited_search_policy(env: dict[str, str]) -> None:
    """The caller's ``DEMO_POLICY`` never reaches a launcher (exploration's search policy is
    fixed per target; there is no option to change it)."""
    _drop_inherited(env, SEARCH_POLICY_ENV, "exploration runs the target's fixed search policy")


@dataclass(frozen=True, slots=True)
class ExploreOptions:
    """Target-agnostic exploration options. Later PRs extend this (search / mutation policy, stop
    conditions, output sinks, mirror, poll interval); a hook reads the fields it supports and
    records the chosen values in the result provenance, and ignores ones it has no use for."""

    budget: int
    seed: int
    out: Path
    image_tag_suffix: str = ""
    #: target-specific option values, by declared option name (see ``TargetAdapter.options``).
    target_options: dict[str, str] = field(default_factory=dict)
    #: ERROR ceiling for the un-judged ratio (see ``DEFAULT_MAX_UNJUDGED_RATIO``).
    max_unjudged_ratio: float = DEFAULT_MAX_UNJUDGED_RATIO
    #: The runtime session the hook passes to ``run_launcher`` (``None``: a plain, unrecorded
    #: launch, as before). The explore driver always passes one (STRICT by default).
    runtime: RuntimeSession | None = None
    #: ``--mutation-policy`` (one of ``EXPLORE_MUTATION_POLICIES``), or ``None``: the target's own
    #: default. Only targets in ``MUTATION_POLICY_TARGETS`` get a value (the driver refuses it for
    #: the others); a hook that runs it records it in the result's campaign block.
    mutation_policy: str | None = None


def requested_identity_check_every(options: ExploreOptions) -> int | None:
    """The identity probe interval this exploration's runtime session asked for (FAST), or
    ``None``: a probe before every case (STRICT, or no session)."""
    runtime = getattr(options, "runtime", None)
    return runtime.policy.identity_check_every if runtime is not None else None


@dataclass(frozen=True, slots=True)
class ExploreOutcome:
    """What a target's explore hook reports back: where it wrote the common campaign result."""

    result_path: Path
    verdict: str  # PASS / FAIL / ERROR
    runs: int
    violations: int


#: A target's exploration hook: open a campaign on an already-prepared image and write the common
#: ``inodefence-target-result-v1`` campaign result. Everything target-specific (controller mode,
#: run program, target-specific observation) lives behind this hook; the driver that prepares the
#: image, the result format, the options, the output and the stop conditions are target-agnostic.
ExploreHook = Callable[[PreparedTargetImage, ExploreOptions], ExploreOutcome]


@dataclass(frozen=True, slots=True)
class TargetAdapter:
    """What a target supplies.

    - ``cells(versions, filters)``: validate the axis values and return the cells, each with the
      image it needs (``RunCell.image_ref``); ``ValueError(reason)`` refuses unsupported values.
    - ``plan(cell)``: what a run of the cell would execute (dry-run only).
    - ``run(cell)``: execute the cell's cases in ``cell.image_ref`` (never an image name rebuilt
      from the version, so a tag override reaches the run).
    - ``prepare(cell)``: the ``PrepareStep`` that would create ``cell.image_ref`` when it is
      missing; default ``prepare_unsupported``.
    """

    mode: ResultMode
    observed_contracts: tuple[str, ...]
    cells: Callable[[list[str], list[str]], list[RunCell]]
    plan: Callable[[RunCell], list[dict[str, Any]]]
    run: Callable[[RunCell], list[CaseRun]]
    prepare: Callable[[RunCell], PrepareStep] = prepare_unsupported
    #: Optional: after a run, record how the cell image was obtained (read from the image itself)
    #: and save any evidence under the given cell directory. ``None`` adds no ``preparation``.
    describe: Callable[[RunCell, Path], Preparation | None] | None = None
    #: Optional: turn symbolic versions (e.g. ``latest``) into exact ones before ``cells``; may use
    #: the network, so it is skipped by --dry-run (``ValueError(reason)`` refuses).
    resolve: Callable[[list[str]], list[str]] | None = None
    #: Optional: open an exploration campaign on a prepared image (``PreparedTargetImage``) and
    #: write the common campaign result. ``None`` (default) means this target does not support
    #: exploration yet; the driver then reports that and stops.
    explore: ExploreHook | None = None
    #: Optional: the smallest ``--budget`` the explore hook accepts (its seed count), read from the
    #: hook's own module (lazy, so no rule is duplicated). The driver checks it before preparing
    #: anything and on ``--dry-run``; ``None`` means the hook has no such floor.
    explore_min_budget: Callable[[], int] | None = None
    #: Target-specific options this target declares (default none). The common driver accepts
    #: them as ``--<name>``, validates against the declaration, and passes them to ``cells`` as
    #: the ``filters`` list in declaration order.
    options: tuple[TargetOption, ...] = ()
    #: Optional: before a present image is reused, confirm it really is the version it is tagged
    #: for. ``(cell, image_id) -> None`` reuses it; a one-line reason refuses the reuse (no
    #: verdict, like a failed prepare). ``None`` (default) reuses any present image by tag name,
    #: unchanged. ``inodefence.drivers.image_prepare.recipe_verify_existing`` builds one from a
    #: recipe.
    verify_existing: Callable[[RunCell, str], str | None] | None = None
    #: Optional: re-run one recorded violation case on its exact image through the same isolation
    #: path as exploration (``inodefence replay``; see ``inodefence.case_replay.ReplayHook``).
    #: ``None`` (default) means this target does not support replay yet.
    replay: ReplayHook | None = None
    #: Optional: before a replay runs anything (and on ``--dry-run``), check that the request is
    #: one this target can re-run under the exploration's own conditions -- its options and input
    #: constraints, read from ``request.run_settings``. ``CaseReplayError(reason)`` refuses the
    #: replay (exit 2, nothing runs); ``None`` (default) means the hook has no such check.
    replay_check: Callable[[Any], None] | None = None
    #: Optional: the benign-input control of a cell -- extract ONE benign archive through the same
    #: run program and image ``run`` uses and report whether it was extracted (see the module
    #: docstring). ``None`` (default): the cell records no control, as before.
    benign: Callable[[RunCell], BenignRun] | None = None


def fixture_case(fixture: rc.RegressionFixture, raw: dict[str, Any]) -> CaseRun:
    """Judge one regression fixture from a raw observation (shared by fixture-regression targets).

    An unobservable C1/C2 is a failed observation, never a nonviolation.
    """
    row = rc.evaluate_fixture(fixture, raw)
    c1, c2 = row["c1_identity_shared"], row["c2_reference_changed"]
    errored = row["outcome"] == "run_error" or c1 is None or c2 is None
    verdict = CaseVerdict(
        case_id=fixture.name,
        outcome=RUN_ERROR if errored else str(row["outcome"]),
        c0=None,
        c1=None if errored else c1,
        c2=None if errored else c2,
    )
    return CaseRun(verdict, fixture.tar, raw)


def fixture_plan() -> list[dict[str, Any]]:
    return [
        {"fixture": f.name, "kind": f.kind, "tar_bytes": len(f.tar)} for f in rc.build_fixtures()
    ]


# Adding a target: write a module with a TargetAdapter, then add one line here.
TARGETS: dict[str, str] = {
    "node-tar": "inodefence.drivers.node_tar.adapter:ADAPTER",
    "python-tarfile": "inodefence.drivers.python_tarfile.adapter:ADAPTER",
    "oras-go": "inodefence.drivers.oras_go.adapter:ADAPTER",
    "decompress": "inodefence.drivers.decompress.adapter:ADAPTER",
}


def load_adapter(target: str) -> TargetAdapter:
    module_name, _, attribute = TARGETS[target].partition(":")
    return getattr(importlib.import_module(module_name), attribute)


# ---- target-independent command ----


def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()


#: Paths whose untracked files make the engine dirty (the code a run executes).
ENGINE_SOURCE_PATHS = ("src", "scripts", "tools")


def auto_prepare_hint() -> str:
    """How to ask for preparation: the CLI flag via ``inodefence``, else the make variable too."""
    if os.environ.get("INODEFENCE_PROG"):
        return "--auto-prepare"
    return "AUTO_PREPARE=1 (--auto-prepare)"


def engine_provenance(image_ref: str | None) -> Provenance:
    """The engine revision that ran (HEAD + dirty flag) and the image's local id, when known."""
    sha = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no")
    # Untracked files count only under the engine's source paths: a new, uncommitted module there
    # changes what ran, so the clone is not clean. (Untracked files elsewhere -- notes, outputs --
    # do not.) The record format is unchanged: still one bool.
    untracked = _git("status", "--porcelain", "--untracked-files=all", "--", *ENGINE_SOURCE_PATHS)
    image_id = None
    if image_ref is not None:
        try:
            done = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            image_id = done.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            image_id = None
    return Provenance(
        engine_sha=sha or None,
        engine_dirty=status is None or bool(status) or untracked is None or bool(untracked),
        image_ref=image_ref,
        image_id=image_id,
    )


# ---- images: lookup, preparation, tag override (target-independent) ----

SETUP_ERROR = 3  # nothing judged for the affected cells: refused input, setup, preparation, image
_TAG_SUFFIX_RE = re.compile(r"[A-Za-z0-9_.-]{1,40}")


#: The command the "docker not found" advice names; another driver substitutes its own
#: (:func:`docker_advice_for`), so verify's wording stays byte for byte.
DOCKER_ADVICE_COMMAND = "target-run"


def docker_advice_for(problem: str | None, command: str) -> str | None:
    """``problem`` (from :func:`docker_problem`) with its advice naming ``command`` instead."""
    if problem is None:
        return None
    return problem.replace(
        f"run {DOCKER_ADVICE_COMMAND} on that host", f"run {command} on that host"
    )


def docker_problem() -> str | None:
    """Why docker cannot run containers here, with the fix, or None if it can.

    An unanswered ``docker info`` (time limit) is named as such, apart from "not reachable": the
    daemon may be alive but stalled (the holdout stops of 2026-11-14..16), and nothing is started.
    """
    if shutil.which("docker") is None:
        return (
            "docker not found on PATH; install Docker (Linux: Docker Engine; Windows: Docker "
            f"Desktop with WSL integration) and run {DOCKER_ADVICE_COMMAND} on that host "
            "(the Dev Container has no docker)"
        )
    try:
        done = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return (
            "docker daemon did not answer `docker info` within 30s (stalled?); nothing was "
            "started. Check Docker (Docker Desktop) and retry"
        )
    except (OSError, subprocess.SubprocessError) as error:
        return f"docker daemon not reachable ({type(error).__name__}); start Docker and retry"
    if done.returncode != 0:
        return (
            "docker daemon not reachable; start Docker (Docker Desktop, or "
            "`sudo service docker start`) and make sure your user may use it, then retry"
        )
    return None


class ImageStateUnknown(ValueError):
    """Docker gave no usable answer to "is this image here?" (timeout, no daemon, odd output).

    A ``ValueError`` so every driver's existing setup path (exit 3) reports it; it is never read
    as "absent", so an image is never prepared (built) because Docker was silent.
    """


def image_id(image_ref: str) -> str | None:
    """The local image id for ``image_ref`` (read-only lookup), or None if Docker says it is absent.

    Raises :class:`ImageStateUnknown` when the question had no usable answer: before, a timeout or
    a stopped daemon returned None too, and an ``--auto-prepare`` run then tried to build the image
    and failed with a misleading "preparing ... failed".
    """
    lookup = health.lookup_image(image_ref, timeout=30)
    if lookup.state is health.ImageState.UNKNOWN:
        raise ImageStateUnknown(
            f"could not tell whether image {image_ref} is on this host: {lookup.detail}. "
            "Nothing was prepared or run"
        )
    return lookup.image_id


def with_tag_suffix(cell: RunCell, suffix: str) -> RunCell:
    """The same cell run on ``<image_ref><suffix>`` (development tag override)."""
    if cell.image_ref is None or not suffix:
        return cell
    return dataclasses.replace(cell, image_ref=cell.image_ref + suffix)


class PrepareError(Exception):
    """An image could not be prepared; its cells get no verdict."""


def prepare_image(step: PrepareStep) -> str:
    """Run ``step``'s commands and return the prepared image's id (``PrepareError`` if not)."""
    if step.commands is None:
        raise PrepareError(f"cannot prepare {step.image_ref}: {step.reason}")
    for command in step.commands:
        print(f"TARGET-RUN PREPARE {step.image_ref}: {shlex.join(command)}", flush=True)
        try:
            done = subprocess.run(list(command), cwd=REPO_ROOT)
        except OSError as error:
            raise PrepareError(f"preparing {step.image_ref} failed: {error}") from error
        if done.returncode != 0:
            raise PrepareError(
                f"preparing {step.image_ref} failed (exit {done.returncode}): {shlex.join(command)}"
            )
    try:
        prepared = image_id(step.image_ref)
    except ImageStateUnknown as error:
        raise PrepareError(f"preparing {step.image_ref} finished but {error}") from error
    if prepared is None:
        raise PrepareError(f"preparing {step.image_ref} finished but the image is not present")
    return prepared


def resolve_images(
    adapter: TargetAdapter, cells: list[RunCell], *, auto_prepare: bool
) -> tuple[dict[str, str], dict[str, str]]:
    """Each distinct cell image -> its id (reused or prepared once), and image -> error."""
    ready: dict[str, str] = {}
    errors: dict[str, str] = {}
    for cell in cells:
        ref = cell.image_ref
        if ref is None or ref in ready or ref in errors:
            continue
        try:
            present = image_id(ref)
        except ImageStateUnknown as error:
            errors[ref] = str(error)  # not "missing": never prepare because Docker was silent
            continue
        if present is not None:
            reason = (
                adapter.verify_existing(cell, present)
                if adapter.verify_existing is not None
                else None
            )
            if reason is None:
                print(f"TARGET-RUN IMAGE reuse {ref} {present}")
                ready[ref] = present
                continue
            errors[ref] = f"present image {ref} refused: {reason}"
            continue
        step = adapter.prepare(cell)
        if not auto_prepare:
            hint = (
                f"rerun with {auto_prepare_hint()} to prepare it"
                if step.commands is not None
                else f"automatic preparation unavailable: {step.reason}"
            )
            errors[ref] = f"missing image {ref}; {hint}"
            continue
        try:
            ready[ref] = prepare_image(step)
            print(f"TARGET-RUN IMAGE prepared {ref} {ready[ref]}")
        except PrepareError as error:
            errors[ref] = str(error)
    return ready, errors


def image_status(adapter: TargetAdapter, cell: RunCell, docker_ok: bool) -> dict[str, Any]:
    """Dry-run view of a cell image: reuse, prepare (with commands) or why it cannot run."""
    if cell.image_ref is None:
        return {"action": "none"}
    if not docker_ok:
        return {"action": "unknown", "reason": "docker unavailable; image presence not checked"}
    try:
        present = image_id(cell.image_ref)
    except ImageStateUnknown as error:
        return {"action": "unknown", "reason": str(error)}
    if present is not None:
        return {"action": "reuse", "image_id": present}
    step = adapter.prepare(cell)
    if step.commands is None:
        return {"action": "missing-unsupported", "reason": step.reason}
    return {
        "action": f"prepare (needs {auto_prepare_hint()})",
        "reason": step.reason,
        "commands": [shlex.join(c) for c in step.commands],
    }


def build_result(
    target: str,
    adapter: TargetAdapter,
    cell: RunCell,
    runs: list[CaseRun],
    provenance: Provenance,
    preparation: Preparation | None = None,
    benign: BenignRun | None = None,
) -> TargetResult:
    return TargetResult(
        target=target,
        axes=cell.axes,
        mode=adapter.mode,
        observed_contracts=adapter.observed_contracts,
        cases=tuple(run.verdict for run in runs),
        repro_inputs=tuple(
            repro_input(run.verdict.case_id, f"inputs/{run.verdict.case_id}.tar", run.tar)
            for run in runs
        ),
        provenance=provenance,
        preparation=preparation,
        benign_control=None if benign is None else benign.control,
    )


def write_result(
    out_dir: Path, result: TargetResult, runs: list[CaseRun], benign: BenignRun | None = None
) -> Path:
    """Write inputs, raw observations, then result.json last (its presence means complete)."""
    result_path = out_dir / RESULT_NAME
    if result_path.exists():
        raise FileExistsError(f"refusing to overwrite {result_path}")
    if benign is not None:
        (out_dir / BENIGN_TAR_PATH).parent.mkdir(parents=True, exist_ok=True)
        (out_dir / BENIGN_TAR_PATH).write_bytes(benign.tar)
        (out_dir / BENIGN_RAW_PATH).write_text(
            json.dumps(benign.raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    (out_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    for run, item in zip(runs, result.repro_inputs, strict=True):
        (out_dir / item.tar_path).write_bytes(run.tar)
        raw_path = out_dir / "raw" / f"{run.verdict.case_id}.json"
        raw_path.write_text(json.dumps(run.raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result_path.write_text(result.dumps(), encoding="utf-8")
    return result_path


def summary_line(result: TargetResult) -> str:
    axes = result.axes
    axis = ",".join(
        f"{name}={value}"
        for name, value in (
            ("version", axes.target_version),
            ("runtime", axes.runtime_version),
            ("filter", axes.extraction_filter),
        )
        if value is not None
    )
    control = result.benign_control
    benign = "" if control is None else f" benign={'ok' if control.extracted else 'FAILED'}"
    return (
        f"TARGET-RUN {result.verdict.value} target={result.target} {axis} "
        f"image={result.provenance.image_ref} "
        f"mode={result.mode.value} violating={len(result.violating_cases)}/{result.executed} "
        f"errored={result.errored}{benign} ({result.label})"
    )


def benign_line(cell: RunCell, benign: BenignRun) -> str:
    """The one terminal line of a cell's benign-input control."""
    control = benign.control
    if control.extracted:
        return (
            f"TARGET-RUN BENIGN-CONTROL ok {cell.dirname}: {control.detail} on {cell.image_ref} "
            f"(tar sha256 {control.tar_sha256[:12]})"
        )
    return (
        f"TARGET-RUN BENIGN-CONTROL FAILED {cell.dirname}: {control.detail}. {cell.image_ref} "
        "does not extract a benign archive, so declined attack inputs prove nothing: the cell "
        "cannot be PASS (ERROR). Remove the image and prepare it again (--auto-prepare), then rerun"
    )


class RefusalParser(argparse.ArgumentParser):
    """Refusals exit 3, never argparse's 2, which is the ERROR verdict code of these commands.

    Shared by the regression and exploration drivers. ``prog`` defaults to the user-facing command
    from ``INODEFENCE_PROG`` (set by ``inodefence``), else argparse's own (the file name).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("prog") is None and os.environ.get("INODEFENCE_PROG"):
            kwargs["prog"] = os.environ["INODEFENCE_PROG"]
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(SETUP_ERROR, f"{self.prog}: error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = RefusalParser(description="run one target on fixed axes (demo run)")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument(
        "--version",
        required=True,
        action="append",
        help="the target's version axis (node-tar package / python-tarfile runtime); repeatable",
    )
    parser.add_argument(
        "--extraction-filter",
        action="append",
        default=[],
        help="extraction-filter axis, for targets that have one; repeatable",
    )
    parser.add_argument("--out", type=Path, help="output directory (required unless --dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    parser.add_argument(
        "--auto-prepare",
        action="store_true",
        help="prepare (pull/build) missing cell images with the target's recipe before running",
    )
    parser.add_argument(
        "--image-tag-suffix",
        default="",
        help="append this to every cell image tag (development; existing tags are untouched)",
    )
    args = parser.parse_args(argv)
    require_repository_or_exit(parser, 3)
    if args.image_tag_suffix and _TAG_SUFFIX_RE.fullmatch(args.image_tag_suffix) is None:
        parser.error("--image-tag-suffix must be 1-40 characters of [A-Za-z0-9_.-]")
    versions, filters = args.version, args.extraction_filter
    if len(set(versions)) != len(versions) or len(set(filters)) != len(filters):
        parser.error("each --version / --extraction-filter may be given once")
    if len(versions) > 1 and len(filters) > 1:
        parser.error(
            "vary one axis per run: several --version with one --extraction-filter, "
            "or one --version with several --extraction-filter"
        )
    adapter = load_adapter(args.target)
    try:
        if adapter.resolve is not None and not args.dry_run:
            versions = adapter.resolve(versions)
            if len(set(versions)) != len(versions):
                parser.error(f"versions resolve to duplicates: {versions}")
        cells = adapter.cells(versions, filters)
    except ValueError as error:
        parser.error(str(error))
    cells = [with_tag_suffix(cell, args.image_tag_suffix) for cell in cells]
    exploratory = [c.dirname for c in cells if c.exploratory]
    if exploratory and len(exploratory) != len(cells):
        parser.error(
            "run committed-recipe versions and registry-prepared (exploratory) versions "
            "separately, so their results are never mixed in one run"
        )

    if args.dry_run:
        docker_ok = docker_problem() is None
        plan = {
            "target": args.target,
            "mode": adapter.mode.value,
            "observed_contracts": list(adapter.observed_contracts),
            "cells": {
                cell.dirname: {
                    "axes": {
                        "target_version": cell.axes.target_version,
                        "runtime_version": cell.axes.runtime_version,
                        "extraction_filter": cell.axes.extraction_filter,
                    },
                    "image": cell.image_ref,
                    "exploratory": cell.exploratory,
                    "image_plan": image_status(adapter, cell, docker_ok),
                    "benign_control": adapter.benign is not None,
                    "would_run": adapter.plan(cell),
                }
                for cell in cells
            },
            "auto_prepare": args.auto_prepare,
            "out": None if args.out is None else str(args.out),
            "note": "dry-run: nothing pulled, built, run or written",
        }
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if args.out is None:
        parser.error("--out is required unless --dry-run")

    for cell in cells:
        if (args.out / cell.dirname / RESULT_NAME).exists():
            parser.error(
                f"{args.out / cell.dirname / RESULT_NAME} already exists; choose another --out"
            )

    problem = docker_problem()
    if problem is not None:
        print(f"TARGET-RUN SETUP: {problem}", file=sys.stderr)
        return SETUP_ERROR
    ready, image_errors = resolve_images(adapter, cells, auto_prepare=args.auto_prepare)
    if image_errors and not args.auto_prepare:
        for message in image_errors.values():
            print(f"TARGET-RUN SETUP: {message}", file=sys.stderr)
        return SETUP_ERROR

    worst = 0
    written: list[tuple[RunCell, TargetResult, Path]] = []
    for cell in cells:
        ref = cell.image_ref
        if ref is not None and ref in image_errors:
            print(f"TARGET-RUN PREPARE-ERROR {cell.dirname}: {image_errors[ref]}", file=sys.stderr)
            worst = max(worst, SETUP_ERROR)
            continue
        expected = ready.get(ref) if ref is not None else None
        try:
            before = image_id(ref) if ref is not None else None
        except ImageStateUnknown as error:
            print(f"TARGET-RUN IMAGE-UNKNOWN {cell.dirname}: {error}", file=sys.stderr)
            worst = max(worst, SETUP_ERROR)
            continue
        if ref is not None and before != expected:
            message = f"image {ref} changed before the run (expected {expected})"
            print(f"TARGET-RUN IMAGE-MISMATCH {cell.dirname}: {message}", file=sys.stderr)
            worst = max(worst, SETUP_ERROR)
            continue
        # The benign-input control comes first: same image, same run program, this invocation.
        benign = adapter.benign(cell) if adapter.benign is not None else None
        if benign is not None:
            print(
                benign_line(cell, benign),
                file=sys.stdout if benign.control.extracted else sys.stderr,
                flush=True,
            )
        runs = adapter.run(cell)
        try:
            after = image_id(ref) if ref is not None else None
        except ImageStateUnknown as error:
            print(
                f"TARGET-RUN IMAGE-UNKNOWN {cell.dirname}: after the run, {error}; no verdict",
                file=sys.stderr,
            )
            worst = max(worst, SETUP_ERROR)
            continue
        if after != expected:
            message = f"image {ref} is {after} after the run, expected {expected}; no verdict"
            print(f"TARGET-RUN IMAGE-MISMATCH {cell.dirname}: {message}", file=sys.stderr)
            worst = max(worst, SETUP_ERROR)
            continue
        provenance = dataclasses.replace(engine_provenance(ref), image_ref=ref, image_id=expected)
        try:
            preparation = (
                adapter.describe(cell, args.out / cell.dirname) if adapter.describe else None
            )
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print(f"TARGET-RUN PREPARE-ERROR {cell.dirname}: {error}; no verdict", file=sys.stderr)
            worst = max(worst, SETUP_ERROR)
            continue
        result = build_result(args.target, adapter, cell, runs, provenance, preparation, benign)
        path = write_result(args.out / cell.dirname, result, runs, benign)
        written.append((cell, result, path))
        print(f"{summary_line(result)} -> {path}")
        worst = max(worst, {"PASS": 0, "FAIL": 1, "ERROR": 2}[result.verdict.value])
    # summary.md hook (IF-MAC-C): one call here, from `written` (cell, result, result.json path),
    # writes args.out / "summary.md". Only cells with a verdict are in `written`.
    # One call per cell, so a failure names its cell and does not stop the other summaries.
    # The verdict files stay as written; only the human-readable page is missing.
    summary_failed = False
    for _, _, path in written:
        try:
            write_cell_summaries([path])
        except Exception as error:  # noqa: BLE001 - must surface, never mask the exit code
            summary_failed = True
            message = f"summary.md not written ({type(error).__name__}: {error})"
            print(f"TARGET-RUN SUMMARY-ERROR {path}: {message}", file=sys.stderr)
    if summary_failed:
        return SETUP_ERROR
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
