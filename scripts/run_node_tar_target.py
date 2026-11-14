"""node-tar target for ``scripts.run_target`` (``make target-run TARGET=node-tar``).

    make target-run TARGET=node-tar TARGET_VERSIONS="7.5.2 7.5.3"

``--version`` is the node-tar package version and fills ``axes.target_version``; node-tar has no
extraction-filter or runtime axis. Mode is ``fixture-regression`` with the ``make regression``
fixtures (``regression_check.build_fixtures``), each extracted by
``experiments.repro.cross_release_identity.run_one`` in a disposable container of the cell's
image (``cell.image_ref``; by default ``inodefence-node-tar-effect:<version>``). That path
observes C1 and C2, not C0 (``null``). The version is a plain input; no release id or CVE id is a
decision condition.

Image preparation (``ADAPTER.prepare``) is not implemented here yet: a missing image is reported
with that reason and the run stops before any case.

(Moved out of ``scripts/run_target.py`` so the common command holds no target-specific code.)
"""

from __future__ import annotations

import base64

from experiments.repro import cross_release_identity as cri
from scripts import regression_check as rc
from scripts.run_target import CaseRun, RunCell, TargetAdapter, fixture_case, fixture_plan

from inodefence.target_result import ResultMode, TargetAxes

TARGET = "node-tar"


def _cells(versions: list[str], filters: list[str]) -> list[RunCell]:
    if filters:
        raise ValueError("node-tar has no extraction-filter axis; drop --extraction-filter")
    for version in versions:
        if rc._VERSION_RE.fullmatch(version) is None:
            raise ValueError(f"node-tar --version must be dotted numeric, e.g. 7.5.2: {version!r}")
    return [
        RunCell(
            dirname=f"{TARGET}-{v}",
            axes=TargetAxes(target_version=v),
            image_ref=cri.IMAGE.format(release=v),
        )
        for v in versions
    ]


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
)
