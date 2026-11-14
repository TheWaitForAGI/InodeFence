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

Versions without a committed recipe (any other exact ``X.Y.Z``, or ``latest`` resolved from the
Go module proxy before any cell exists) are prepared with ``AUTO_PREPARE=1`` by
``scripts.oras_go_registry_prepare`` into ``inodefence-oras-go-registry:<version>`` (never the
committed-recipe name): go.mod/go.sum generated in a disposable Go container against
``proxy.golang.org`` with ``GOSUMDB=sum.golang.org``, the unchanged Dockerfile and worker built,
then checked offline (``identify``, the probe below and the campaign's ``frame`` subcommand).
Those cells are labelled ``exploratory demo run`` and keep go.mod/go.sum under
``preparation/``. Which path a version takes depends only on whether a committed recipe pins it.

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
import sys
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from experiments.repro import oras_go_cwd_hardlink as ogh
from scripts import image_prepare as ip
from scripts import oras_go_registry_prepare as proxy
from scripts import regression_check as rc
from scripts.run_target import CaseRun, PrepareStep, RunCell, TargetAdapter, fixture_case

from inodefence.target_result import Preparation, ResultMode, TargetAxes

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


#: ``latest`` is the only symbolic version accepted; it becomes exact before any cell exists.
LATEST = "latest"
#: Images prepared from the Go module proxy never share a name with committed-recipe images.
PROXY_IMAGE = proxy.REGISTRY_REPOSITORY + ":{version}"
#: exact version -> (what was asked, UTC resolution time), filled by ``_resolve`` for ``describe``.
_RESOLVED: dict[str, tuple[str, str]] = {}


def _resolve(versions: list[str]) -> list[str]:
    """Resolve ``latest`` from the Go module proxy (not called by --dry-run)."""
    exact = []
    for version in versions:
        if version != LATEST:
            exact.append(version)
            continue
        try:
            resolved = proxy.resolve_latest()
        except proxy.RegistryPrepareError as error:
            raise ValueError(f"cannot resolve oras-go {LATEST}: {error}") from error
        _RESOLVED[resolved] = (LATEST, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        print(f"TARGET-RUN RESOLVE oras-go {LATEST} -> {resolved}", flush=True)
        exact.append(resolved)
    return exact


def _cells(versions: list[str], filters: list[str]) -> list[RunCell]:
    if filters:
        raise ValueError("oras-go has no extraction-filter axis; drop --extraction-filter")
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
                f"oras-go --version must be dotted numeric (e.g. 2.6.1) or latest: {version!r}"
            )
    pinned = pinned_versions()
    cells = []
    for v in versions:
        if v in pinned or proxy.EXACT.fullmatch(v) is None:
            # Unchanged verified path (a non-exact version can only reuse an existing image).
            cells.append(
                RunCell(
                    dirname=f"{TARGET}-{v}",
                    axes=TargetAxes(target_version=v),
                    image_ref=ogh.IMAGE.format(tag=v),
                )
            )
        else:
            cells.append(
                RunCell(
                    dirname=f"{TARGET}-{v}-exploratory",
                    axes=TargetAxes(target_version=v),
                    image_ref=PROXY_IMAGE.format(version=v),
                    exploratory=True,
                )
            )
    return cells


def _plan(cell: RunCell) -> list[dict[str, Any]]:
    if cell.axes.target_version == LATEST:
        return [{"note": f"{LATEST} is resolved from {proxy.PROXY} at run time"}]
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
    """``TargetAdapter.prepare``: committed recipe (verified) or Go module proxy (exploratory)."""
    version = cell.axes.target_version or ""
    if not cell.exploratory:
        return ip.recipe_step(cell, lambda: image_recipe(version))
    image = cell.image_ref or ""
    try:
        proxy.check_inputs(version, image)
    except proxy.RegistryPrepareError as error:
        return PrepareStep(image_ref=image, commands=None, reason=str(error))
    command = (sys.executable, "-m", "scripts.oras_go_registry_prepare")
    return PrepareStep(
        image_ref=image,
        commands=((*command, "--version", version, "--image", image),),
        reason=f"exploratory: go.mod/go.sum from {proxy.PROXY} (GOSUMDB={proxy.SUMDB}), "
        "checked, then the committed Dockerfile and worker",
    )


def _describe(cell: RunCell, cell_dir: Path) -> Preparation | None:
    """Proxy cells only: record what is inside the image and keep its go.mod/go.sum as evidence."""
    if not cell.exploratory:
        return None
    version, image = cell.axes.target_version or "", cell.image_ref or ""
    try:
        found = proxy.image_evidence(image)
        frame = proxy.frame_check(proxy.subprocess.run, image, version)
    except proxy.RegistryPrepareError as error:
        raise ValueError(str(error)) from error
    if found["installed_version"] != version:
        raise ValueError(f"{image} has oras-go {found['installed_version']!r}, requested {version}")
    if not frame["ok"]:
        raise ValueError(f"worker incompatible (frame): {frame['reason']}")
    evidence = cell_dir / "preparation"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "go.mod").write_bytes(found["gomod"])
    (evidence / "go.sum").write_bytes(found["gosum"])
    spec, resolved_at = _RESOLVED.get(version, (None, None))
    return Preparation(
        method="registry",
        requested_version=version,
        installed_version=found["installed_version"],
        lock_sha256=found["gosum_sha256"],
        worker_sha256=found["worker_sha256"],
        recipe=(
            f"{proxy.RECIPE}; {found['sumdb']}; base image {found['base_image']}; "
            f"toolchain required {found['toolchain_required']}, used {found['go_version']}"
        ),
        requested_spec=spec,
        resolved_at=resolved_at,
        new_dependencies=tuple(proxy.new_modules(found["gosum"], proxy.committed_modules())),
        producer_sha256=frame["worker_sha256"],
        producer_check=frame["reason"],
    )


@dataclass(frozen=True, slots=True)
class PreparedOrasGo:
    """An oras-go image that exists locally and passed its offline checks."""

    requested: str  # what the caller asked for (``latest`` or an exact version)
    version: str  # the exact oras-go version inside the image
    image_ref: str
    image_id: str
    exploratory: bool  # True: Go-proxy-prepared; False: committed go.mod/go.sum recipe


def ensure_image(spec: str, *, image_tag_suffix: str = "") -> PreparedOrasGo:
    """One call for other commands: resolve ``spec``, reuse or prepare its image, return its id.

    ``spec`` is ``latest`` or an exact version. A committed go.mod/go.sum selects the verified
    recipe; otherwise the image is prepared from the Go module proxy
    (``scripts.oras_go_registry_prepare``) with all of its offline checks (installed version, the
    regression probe, the campaign's ``frame`` worker). This is the path
    ``make target-run ... AUTO_PREPARE=1`` takes; it may use the network. Raises ``ValueError``
    with the reason when the version is refused or preparation fails (no image is tagged then).
    """
    from scripts.run_target import resolve_images, with_tag_suffix

    (version,) = _resolve([spec])
    (cell,) = _cells([version], [])
    if cell.image_ref is None:
        raise ValueError(f"oras-go {spec}: no image for this version")
    cell = with_tag_suffix(cell, image_tag_suffix)
    ready, errors = resolve_images(ADAPTER, [cell], auto_prepare=True)
    ref = cell.image_ref
    assert ref is not None
    if ref in errors:
        raise ValueError(errors[ref])
    return PreparedOrasGo(spec, version, ref, ready[ref], cell.exploratory)


def _explore_hook(prepared, options):  # type: ignore[no-untyped-def]
    """oras-go exploration (lazy import so the fixture-regression path has no extra deps)."""
    from scripts.oras_go_explore import explore

    return explore(prepared, options)


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
)
