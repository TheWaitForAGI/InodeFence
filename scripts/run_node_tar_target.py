"""node-tar target for ``scripts.run_target`` (``make target-run TARGET=node-tar``).

    make target-run TARGET=node-tar TARGET_VERSIONS="7.5.2 7.5.3"

``--version`` is the node-tar package version and fills ``axes.target_version``; node-tar has no
extraction-filter or runtime axis. Mode is ``fixture-regression`` with the ``make regression``
fixtures (``regression_check.build_fixtures``), each extracted by
``experiments.repro.cross_release_identity.run_one`` in a disposable container of the cell's
image (``cell.image_ref``; by default ``inodefence-node-tar-effect:<version>``). That path
observes C1 and C2, not C0 (``null``). The version is a plain input; no release id or CVE id is a
decision condition.

Image preparation (``ADAPTER.prepare``) is ``scripts.node_tar_image.prepare``: versions with a
committed lock in ``tools/node-tar/versions/<v>/`` are built and checked offline; others are
refused.

(Moved out of ``scripts/run_target.py`` so the common command holds no target-specific code.)
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from experiments.repro import cross_release_identity as cri
from scripts import node_tar_image
from scripts import node_tar_registry_prepare as registry
from scripts import regression_check as rc
from scripts.run_target import (
    CaseRun,
    PrepareStep,
    RunCell,
    TargetAdapter,
    fixture_case,
    fixture_plan,
)

from inodefence.target_result import Preparation, ResultMode, TargetAxes

TARGET = "node-tar"
#: Images built from a registry-generated lock never share a name with committed-recipe images.
REGISTRY_IMAGE = "inodefence-node-tar-registry:{version}"


def _committed(version: str) -> bool:
    return (node_tar_image.VERSIONS_DIR / version / "package-lock.json").is_file()


#: ``latest`` is the only symbolic version accepted; it becomes exact before any cell exists.
LATEST = "latest"
#: exact version -> (what was asked, UTC resolution time), filled by ``_resolve`` for ``describe``.
_RESOLVED: dict[str, tuple[str, str]] = {}


def _resolve(versions: list[str]) -> list[str]:
    """Resolve ``latest`` from the registry's dist-tag (not called by --dry-run)."""
    exact = []
    for version in versions:
        if version != LATEST:
            exact.append(version)
            continue
        try:
            resolved = registry.resolve_latest()
        except registry.RegistryPrepareError as error:
            raise ValueError(f"cannot resolve node-tar {LATEST}: {error}") from error
        _RESOLVED[resolved] = (LATEST, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        print(f"TARGET-RUN RESOLVE node-tar {LATEST} -> {resolved}", flush=True)
        exact.append(resolved)
    return exact


def _cells(versions: list[str], filters: list[str]) -> list[RunCell]:
    if filters:
        raise ValueError("node-tar has no extraction-filter axis; drop --extraction-filter")
    if LATEST in versions:  # only reached by --dry-run (a real run resolves first)
        return [
            RunCell(
                dirname=f"{TARGET}-{LATEST} (resolved at run time)",
                axes=TargetAxes(target_version=LATEST),
                image_ref=None,
                exploratory=True,
            )
        ]
    for version in versions:
        if rc._VERSION_RE.fullmatch(version) is None:
            raise ValueError(
                f"node-tar --version must be dotted numeric (e.g. 7.5.2) or latest: {version!r}"
            )
    cells = []
    for v in versions:
        if _committed(v) or registry.EXACT.fullmatch(v) is None:
            # Unchanged verified path (a non-exact version can only reuse an existing image).
            cells.append(
                RunCell(
                    dirname=f"{TARGET}-{v}",
                    axes=TargetAxes(target_version=v),
                    image_ref=cri.IMAGE.format(release=v),
                )
            )
        else:
            cells.append(
                RunCell(
                    dirname=f"{TARGET}-{v}-exploratory",
                    axes=TargetAxes(target_version=v),
                    image_ref=REGISTRY_IMAGE.format(version=v),
                    exploratory=True,
                )
            )
    return cells


def _prepare(cell: RunCell) -> PrepareStep:
    if not cell.exploratory:
        return node_tar_image.prepare(cell)
    version, image = cell.axes.target_version or "", cell.image_ref or ""
    try:
        registry.check_inputs(version, image)
    except registry.RegistryPrepareError as error:
        return PrepareStep(image_ref=image, commands=None, reason=str(error))
    command = (sys.executable, "-m", "scripts.node_tar_registry_prepare")
    return PrepareStep(
        image_ref=image,
        commands=((*command, "--version", version, "--image", image),),
        reason=f"exploratory: lock from {registry.REGISTRY}, checked, then the committed recipe",
    )


def _describe(cell: RunCell, cell_dir: Path) -> Preparation | None:
    """Registry cells only: record what is inside the image and keep its lock as evidence."""
    if not cell.exploratory:
        return None
    version, image = cell.axes.target_version or "", cell.image_ref or ""
    try:
        found = registry.image_evidence(image)
    except registry.RegistryPrepareError as error:
        raise ValueError(str(error)) from error
    if found["installed_version"] != version:
        raise ValueError(f"{image} has tar {found['installed_version']!r}, requested {version}")
    evidence = cell_dir / "preparation"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "package-lock.json").write_bytes(found["lock"])
    findings = registry.lock_findings(json.loads(found["lock"]), registry.allowed_packages())
    producer = registry.producer_check(registry.subprocess.run, image, version)
    if not producer["ok"]:
        raise ValueError(f"worker incompatible (effect-producer): {producer['reason']}")
    spec, resolved_at = _RESOLVED.get(version, (None, None))
    return Preparation(
        method="registry",
        requested_version=version,
        installed_version=found["installed_version"],
        lock_sha256=found["lock_sha256"],
        worker_sha256=found["worker_sha256"],
        recipe=registry.RECIPE.format(version=version),
        requested_spec=spec,
        resolved_at=resolved_at,
        new_dependencies=tuple(findings["new_dependencies"]),
        install_scripts_disabled=tuple(findings["install_scripts_disabled"]),
        producer_sha256=producer["producer_sha256"],
        producer_check=producer["reason"],
    )


def _plan(cell: RunCell) -> list[dict[str, object]]:
    if cell.axes.target_version == LATEST:
        return [{"note": f"{LATEST} is resolved from {registry.REGISTRY} at run time"}]
    return fixture_plan()


def _run(cell: RunCell) -> list[CaseRun]:
    version = cell.axes.target_version
    assert version is not None and cell.image_ref is not None
    runs = []
    for fixture in rc.build_fixtures():
        tar_b64 = base64.b64encode(fixture.tar).decode()
        # Registry-prepared images run offline; committed-recipe runs keep the historical command.
        if cell.exploratory:
            raw = cri.run_one(version, tar_b64, image=cell.image_ref, network_none=True)
        else:
            raw = cri.run_one(version, tar_b64, image=cell.image_ref)
        runs.append(fixture_case(fixture, raw))
    return runs


@dataclass(frozen=True, slots=True)
class PreparedNodeTar:
    """A node-tar image that exists locally and passed its offline checks."""

    requested: str  # what the caller asked for (``latest`` or an exact version)
    version: str  # the exact version inside the image
    image_ref: str
    image_id: str
    exploratory: bool  # True: registry-prepared (no committed lock); False: committed recipe


def ensure_image(spec: str, *, image_tag_suffix: str = "") -> PreparedNodeTar:
    """One call for other commands: resolve ``spec``, reuse or prepare its image, return its id.

    ``spec`` is ``latest`` or an exact/dotted version. A committed lock selects the verified recipe;
    otherwise the image is prepared from the registry (``scripts.node_tar_registry_prepare``) with
    all of its offline checks (installed version, harness, effect producer). This is the same path
    ``make target-run ... AUTO_PREPARE=1`` takes; it may use the network. Raises ``ValueError`` with
    the reason when the version is refused or preparation fails (no image is tagged then).
    """
    from scripts.run_target import resolve_images, with_tag_suffix

    (version,) = _resolve([spec])
    (cell,) = _cells([version], [])
    if cell.image_ref is None:
        raise ValueError(f"node-tar {spec}: no image for this version")
    cell = with_tag_suffix(cell, image_tag_suffix)
    ready, errors = resolve_images(ADAPTER, [cell], auto_prepare=True)
    ref = cell.image_ref
    assert ref is not None
    if ref in errors:
        raise ValueError(errors[ref])
    return PreparedNodeTar(spec, version, ref, ready[ref], cell.exploratory)


def _explore_hook(prepared, options):  # type: ignore[no-untyped-def]
    """node-tar exploration (lazy import so the fixture-regression path has no extra deps)."""
    from scripts.node_tar_explore import explore

    return explore(prepared, options)


def _verify_existing(cell: RunCell, image_id: str) -> str | None:
    """Before the explore path reuses a prepared registry image, confirm its effect producer runs.

    Checking only that the image's ``tar`` version string matches is not enough: a same-version
    image whose committed effect producer is missing or incompatible would run but fail at every
    step, a silent all-unjudged campaign. So re-run the producer offline against the image -- it
    must identify the installed ``tar`` and extract a benign archive with a usable frame and no
    failures (the same check preparation runs, at #409). Only the exploratory (registry) reuse path
    is guarded; committed-recipe reuse (fixture regression) is unchanged.
    """
    if cell.image_ref is None or not cell.exploratory:
        return None
    result = registry.producer_check(subprocess.run, cell.image_ref, cell.axes.target_version or "")
    return None if result["ok"] else result["reason"]


ADAPTER = TargetAdapter(
    mode=ResultMode.FIXTURE_REGRESSION,
    observed_contracts=("C1", "C2"),
    cells=_cells,
    plan=_plan,
    run=_run,
    prepare=_prepare,
    describe=_describe,
    resolve=_resolve,
    explore=_explore_hook,
    verify_existing=_verify_existing,
)
