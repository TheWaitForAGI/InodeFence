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
import sys
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


def _cells(versions: list[str], filters: list[str]) -> list[RunCell]:
    if filters:
        raise ValueError("node-tar has no extraction-filter axis; drop --extraction-filter")
    for version in versions:
        if rc._VERSION_RE.fullmatch(version) is None:
            raise ValueError(f"node-tar --version must be dotted numeric, e.g. 7.5.2: {version!r}")
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
                    dirname=f"{TARGET}-{v}",
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
    return Preparation(
        method="registry",
        requested_version=version,
        installed_version=found["installed_version"],
        lock_sha256=found["lock_sha256"],
        worker_sha256=found["worker_sha256"],
        recipe=registry.RECIPE.format(version=version),
    )


def _run(cell: RunCell) -> list[CaseRun]:
    version = cell.axes.target_version
    assert version is not None and cell.image_ref is not None
    runs = []
    for fixture in rc.build_fixtures():
        tar_b64 = base64.b64encode(fixture.tar).decode()
        raw = cri.run_one(version, tar_b64, image=cell.image_ref)
        runs.append(fixture_case(fixture, raw))
    return runs


ADAPTER = TargetAdapter(
    mode=ResultMode.FIXTURE_REGRESSION,
    observed_contracts=("C1", "C2"),
    cells=_cells,
    plan=lambda cell: fixture_plan(),
    run=_run,
    prepare=_prepare,
    describe=_describe,
)
