"""oras-go target for ``scripts.run_target`` (``make target-run TARGET=oras-go``).

    make target-run TARGET=oras-go TARGET_VERSIONS="2.6.1 2.6.2"

``--version`` is the oras-go release and fills ``axes.target_version``; oras-go has no
extraction-filter axis and no separate runtime axis (the Go worker is statically linked).

Execution reuses the existing controlled repro unchanged:
``experiments.repro.oras_go_cwd_hardlink.run_probe`` runs the worker's ``probe`` in a disposable
``inodefence-oras-go:<version>`` container (``--network none``, ``--read-only``, tmpfs ``/work``
and ``/tmp`` only, ``--cap-drop ALL``, non-root, nothing mounted). The probe builds the sandbox
inside the container: ``/work/extract`` plus an external file ``/work/outside/sentinel.txt``
beside it, with the working directory at ``/work``. It prints the same JSON keys as the node-tar
and Python programs, so ``run_target.fixture_case`` judges C1/C2 unchanged; C0 is not observed.

Images are built in a separate step that needs the network (``go mod download``); the
extraction run never does. A missing image is a run error, never a result::

    docker build -f tools/oras-go/Dockerfile --build-arg ROLE=affected -t inodefence-oras-go:2.6.1 .
    docker build -f tools/oras-go/Dockerfile --build-arg ROLE=fixed    -t inodefence-oras-go:2.6.2 .

Fixtures (mode ``fixture-regression``):

- the ``make regression`` fixtures (``regression_check.build_fixtures``), relocated to the probe
  layout: every member goes under oras-go's directory-artifact title ``d/``, path components
  ``ext`` / ``reference.bin`` become ``outside`` / ``sentinel.txt``, and symlink targets gain one
  ``../`` for the extra ``d/`` level. Entry types, order and contents are unchanged;
- the repro's own controlled fixture (``oras_go_cwd_hardlink.FIXTURE``, a hard link whose target
  has no ``..``), verbatim.

These are hand-built controlled inputs, not fuzzer findings. The external file's name appears only
in the inputs and the probe layout; the verdict is "does an extracted object share the external
file's inode / did the external file change", with no path, release id or CVE id in it.
"""

from __future__ import annotations

import base64
import io
import re
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from experiments.repro import oras_go_cwd_hardlink as ogh
from scripts import image_prepare as ip
from scripts import regression_check as rc
from scripts.run_target import CaseRun, PrepareStep, RunCell, TargetAdapter, fixture_case

from inodefence.target_result import ResultMode, TargetAxes

TARGET = "oras-go"
ARTIFACT_DIR = "d"  # oras-go unpacks a directory artifact under its title (worker artifactDir)
# The make-regression layout (extract/ + ext/reference.bin) -> the probe layout
# (extract/ + outside/sentinel.txt). Geometry only; never a verdict condition.
_COMPONENTS = {"ext": "outside", "reference.bin": "sentinel.txt"}


def _map_components(path: str) -> str:
    return "/".join(_COMPONENTS.get(part, part) for part in path.split("/"))


def relocate(tar_bytes: bytes) -> bytes:
    """Rewrite one fixture TAR for the probe layout; types, order and contents are kept."""
    out = io.BytesIO()
    with (
        tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as src,
        tarfile.open(fileobj=out, mode="w", format=tarfile.USTAR_FORMAT) as dst,
    ):
        for member in src.getmembers():
            stream = src.extractfile(member) if member.isreg() else None
            data = stream.read() if stream is not None else None
            info = tarfile.TarInfo(f"{ARTIFACT_DIR}/{_map_components(member.name)}")
            info.type, info.mode, info.size = member.type, member.mode, member.size
            info.uid = info.gid = info.mtime = 0
            if member.issym():
                info.linkname = "../" + _map_components(member.linkname)
            elif member.islnk():
                info.linkname = _map_components(member.linkname)
            dst.addfile(info, io.BytesIO(data) if data is not None else None)
    return out.getvalue()


def build_fixtures() -> tuple[rc.RegressionFixture, ...]:
    shared = tuple(
        rc.RegressionFixture(f.name, f.kind, relocate(f.tar)) for f in rc.build_fixtures()
    )
    repro = rc.RegressionFixture(
        "cwd_relative_hardlink", "repro-hardlink", ogh.build_tar(ogh.FIXTURE)
    )
    return (*shared, repro)


def _cells(versions: list[str], filters: list[str]) -> list[RunCell]:
    if filters:
        raise ValueError("oras-go has no extraction-filter axis; drop --extraction-filter")
    for version in versions:
        if rc._VERSION_RE.fullmatch(version) is None:
            raise ValueError(f"oras-go --version must be dotted numeric, e.g. 2.6.1: {version!r}")
    return [
        RunCell(
            dirname=f"{TARGET}-{v}",
            axes=TargetAxes(target_version=v),
            image_ref=ogh.IMAGE.format(tag=v),
        )
        for v in versions
    ]


def _plan(cell: RunCell) -> list[dict[str, Any]]:
    return [{"fixture": f.name, "kind": f.kind, "tar_bytes": len(f.tar)} for f in build_fixtures()]


def _run(cell: RunCell) -> list[CaseRun]:
    version = cell.axes.target_version
    assert version is not None
    sentinel_b64 = base64.b64encode(ogh.SENTINEL_CONTENT).decode()
    runs = []
    for fixture in build_fixtures():
        tar_b64 = base64.b64encode(fixture.tar).decode()
        try:
            raw = ogh.run_probe(version, tar_b64, sentinel_b64, image=cell.image_ref)
        except (OSError, subprocess.SubprocessError) as error:  # docker missing / timeout
            raw = {"_run_error": True, "_reason": f"{type(error).__name__}: {error}"[:400]}
        runs.append(fixture_case(fixture, raw))
    return runs


# ---- image preparation (build from the committed per-role go.mod/go.sum) ----

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools" / "oras-go"
_ORAS_REQUIRE = re.compile(r"^\s*oras\.land/oras-go/v2\s+v([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.M)


def pinned_versions(tools_dir: Path = TOOLS_DIR) -> dict[str, str]:
    """oras-go version -> recipe role, from each committed ``<role>/go.mod`` with its ``go.sum``."""
    pinned: dict[str, str] = {}
    for role in sorted(p for p in tools_dir.iterdir() if p.is_dir()):
        gomod = role / "go.mod"
        if gomod.is_file() and (role / "go.sum").is_file():
            found = _ORAS_REQUIRE.search(gomod.read_text(encoding="utf-8"))
            if found:
                pinned[found.group(1)] = role.name
    return pinned


def image_recipe(version: str, tools_dir: Path = TOOLS_DIR) -> ip.Recipe:
    """Build ``tools/oras-go/Dockerfile`` with the role whose committed go.mod pins ``version``.

    After the build the worker's offline ``identify`` must report ``v<version>``. Versions without
    a committed go.mod/go.sum are refused; nothing is resolved from the network by version name.
    """
    ip.exact_version(version, "oras-go version")
    pinned = pinned_versions(tools_dir)
    if version not in pinned:
        raise ip.UnsupportedVersionError(
            f"oras-go {version}: no committed go.mod/go.sum pins it "
            f"(buildable: {', '.join(sorted(pinned)) or 'none'})"
        )
    return ip.Recipe(
        description=f"build tools/oras-go/Dockerfile ROLE={pinned[version]} (committed go.sum)",
        expected=f"v{version}",
        build=("-f", "tools/oras-go/Dockerfile", "--build-arg", f"ROLE={pinned[version]}"),
        check=(ip.IMAGE_SLOT, "identify"),
        json_key="oras_go_version",
    )


def _prepare(cell: RunCell) -> PrepareStep:
    """``TargetAdapter.prepare``: build ``cell.image_ref`` from the committed recipe; verify it."""
    version = cell.axes.target_version or ""
    return ip.recipe_step(cell, lambda: image_recipe(version))


ADAPTER = TargetAdapter(
    mode=ResultMode.FIXTURE_REGRESSION,
    observed_contracts=("C1", "C2"),
    cells=_cells,
    plan=_plan,
    run=_run,
    prepare=_prepare,
)
