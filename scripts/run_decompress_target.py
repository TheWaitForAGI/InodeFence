"""decompress target adapter for ``scripts/run_target.py`` (fixture-regression, demo run).

Target: the npm ``decompress`` family. The original package (``decompress``, kevva/decompress) is
unmaintained: its last release is 4.2.1 and it has no in-package fix for its hard-link handling.
The 2026 fix exists only in the maintained fork ``@xhmikosr/decompress`` (11.1.4 is the pinned
patched release). Because the two are different packages, a version alone is ambiguous, so
``--version`` is ``<package>@<X.Y.Z>`` and lands unchanged in ``axes.target_version``:

    --version decompress@4.2.1              (original, unmaintained)
    --version @xhmikosr/decompress@11.1.4   (maintained fork)

There is no runtime or extraction-filter axis (``runtime_version`` / ``extraction_filter`` are
``null``). Mode is ``fixture-regression`` with the same five fixtures every registered target runs
(``scripts.regression_check.build_fixtures``) in the same ``/work/extract`` + external
``/work/ext/reference.bin`` layout, judged by the same ``regression_check.c1_from_raw`` /
``c2_from_raw`` through ``run_target.fixture_case``. C0 is not observed (``null``). No package
name, version, CVE id or reference-file name is a decision condition.

Execution reuses the existing decompress path (``experiments.repro.decompress_hardlink``):

- Install and run are separate steps. The pinned images ``inodefence-decompress:<X.Y.Z>`` are built
  beforehand from ``tools/decompress/Dockerfile`` (``npm ci`` from a committed, checksum-verified
  ``package-lock.json``; the only step that uses the network), by hand or with ``AUTO_PREPARE=1``
  (``scripts.decompress_image.prepare``). The run step never builds or pulls (``--pull never``).
- Each fixture is extracted in a fresh container with the same flags as
  ``decompress_hardlink.run_probe``: ``--rm --network none --read-only``, tmpfs ``/work`` and
  ``/tmp`` only, ``--cap-drop ALL``, the image's non-root user, no mounts; inputs arrive in
  environment variables. The sandbox and the reference file are created inside the container.
- The in-container program (``JS_PROGRAM``) loads whichever decompress package the image pinned,
  as the image's own worker does, and reports the installed package name and version. A
  mismatch with the requested ``<package>@<version>`` is a run error, not a result.

Harness setting, fixed for every version: decompress passes a hard-link target to ``fs.link``,
which resolves a relative target against the process working directory. The fixtures write link
targets relative to the extraction directory (the geometry node-tar and Python tarfile read), so
the program runs with the working directory set to the extraction directory (a caller extracting
into its current directory). The existing M4 probe used the sandbox root as working directory with
its own fixture; both are caller choices, not per-version tuning.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from experiments.repro import decompress_hardlink as dh
from scripts import decompress_image
from scripts import decompress_registry_prepare as registry
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

TARGET = "decompress"
REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools" / "decompress"
SPEC_RE = re.compile(
    r"(?P<package>(?:@[a-z0-9][a-z0-9._-]*/)?decompress)@(?P<version>[0-9]+\.[0-9]+\.[0-9]+)"
)
REFERENCE_CONTENT = b"inodefence external reference\n"
TIMEOUT_SECONDS = 90

Runner = Callable[..., subprocess.CompletedProcess[str]]

JS_PROGRAM = r"""
'use strict'
const fs = require('node:fs'), path = require('node:path')
function st(p) {
  try {
    const s = fs.lstatSync(p)
    return { dev: String(s.dev), ino: String(s.ino), nlink: s.nlink, size: s.size,
      type: s.isSymbolicLink() ? 'sym' : s.isDirectory() ? 'dir' : s.isFile() ? 'reg' : 'other' }
  } catch (e) { return { error: e.code || String(e) } }
}
function walk(dir, base) {
  const out = {}
  let names
  try { names = fs.readdirSync(dir).sort() } catch (e) { return out }
  for (const n of names) {
    const full = path.join(dir, n), rel = base ? base + '/' + n : n
    const s = st(full)
    out[rel] = s
    if (s.type === 'dir') Object.assign(out, walk(full, rel))
  }
  return out
}
;(async () => {
  const pkg = JSON.parse(fs.readFileSync('/target/package.json', 'utf8'))
  const name = Object.keys(pkg.dependencies || {})
    .find(d => d === 'decompress' || d.endsWith('/decompress'))
  const installed = JSON.parse(fs.readFileSync(
    path.join('/target/node_modules', ...name.split('/'), 'package.json'), 'utf8')).version
  const mod = await import(name)
  const decompress = mod.default ?? mod
  const extract = '/work/extract', ref = '/work/ext/reference.bin'
  fs.mkdirSync(extract, { recursive: true })
  fs.mkdirSync(path.dirname(ref), { recursive: true })
  fs.writeFileSync(ref, Buffer.from(process.env.REF_B64, 'base64'))
  fs.chmodSync(ref, 0o600)
  const before = st(ref)
  process.chdir(extract)
  let declined = null
  try { await decompress(Buffer.from(process.env.TAR_B64, 'base64'), extract) }
  catch (e) { declined = { message: String((e && e.message) || e).slice(0, 200) } }
  const after = st(ref)
  const tree = walk(extract, '')
  const shared = []
  if (after.ino) for (const k in tree) {
    const o = tree[k]
    if (o.dev === after.dev && o.ino === after.ino) shared.push('extract/' + k)
  }
  process.stdout.write(JSON.stringify({
    package: name, package_version: installed, node_version: process.versions.node,
    declined, reference_before: before, reference_after: after,
    nlink_before: before.nlink, nlink_after: after.nlink,
    shared_identity: shared, extract_tree: tree,
  }) + '\n')
})().catch(e => {
  process.stderr.write('FATAL ' + String((e && e.message) || e) + '\n')
  process.exit(3)
})
"""


def parse_spec(spec: str) -> tuple[str, str]:
    """``<package>@<X.Y.Z>`` -> (package, version); ``ValueError`` otherwise."""
    match = SPEC_RE.fullmatch(spec)
    if match is None:
        raise ValueError(
            f"decompress --version is <package>@<X.Y.Z> or <package>@latest, e.g. "
            f"decompress@4.2.1 or @xhmikosr/decompress@latest: {spec!r}"
        )
    return match["package"], match["version"]


def pinned_recipe(package: str, version: str, tools_dir: Path = TOOLS_DIR) -> str | None:
    """The ``tools/decompress/<dir>`` whose package.json pins exactly this package and version."""
    for manifest in sorted(tools_dir.glob("*/package.json")):
        deps = json.loads(manifest.read_text(encoding="utf-8")).get("dependencies", {})
        if deps.get(package) == version:
            return manifest.parent.name
    return None


def image_ref(version: str) -> str:
    return dh.IMAGE.format(tag=version)


def dirname(package: str, version: str) -> str:
    slug = package.lstrip("@").replace("/", "-")
    return f"{TARGET}-{version}" if slug == TARGET else f"{TARGET}-{slug}-{version}"


def docker_command(version: str, tar_b64: str, image: str | None = None) -> list[str]:
    """Same isolation as ``decompress_hardlink.run_probe``; only the program differs.

    ``--pull never`` keeps the run step off the network for images too: a missing pinned image is a
    run error, never a registry pull.
    """
    return [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/work:rw,size=16m,mode=1777",
        "--tmpfs",
        "/tmp:rw,size=16m,mode=1777",
        "--cap-drop",
        "ALL",
        "-e",
        f"TAR_B64={tar_b64}",
        "-e",
        f"REF_B64={base64.b64encode(REFERENCE_CONTENT).decode()}",
        "--entrypoint",
        "/usr/local/bin/node",
        image or image_ref(version),
        "-e",
        JS_PROGRAM,
    ]


def parse_output(stdout: str, package: str, version: str) -> dict[str, Any] | None:
    """Last JSON line, or None. A different installed package or version is a run error."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        if (raw.get("package"), raw.get("package_version")) != (package, version):
            ran = f"{raw.get('package')}@{raw.get('package_version')}"
            return {"_run_error": True, "_reason": f"package mismatch: ran {ran}", "observed": raw}
        return raw
    return None


def run_one(
    package: str,
    version: str,
    tar_b64: str,
    *,
    image: str | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Extract one TAR in a fresh container; a failed or unverifiable run is ``_run_error``."""
    try:
        done = runner(
            docker_command(version, tar_b64, image),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"_run_error": True, "_reason": f"{type(error).__name__}: {error}"[:400]}
    raw = parse_output(done.stdout or "", package, version)
    if raw is None:
        return {"_run_error": True, "_rc": done.returncode, "_stderr": (done.stderr or "")[-400:]}
    return raw


# ---- adapter ----


# ---- registry preparation (exploratory): versions without a committed recipe, and @latest ----

#: Registry-prepared images never share a name with committed-recipe images.
REGISTRY_IMAGE = registry.REGISTRY_REPOSITORY + ":{slug}-{version}"
#: exact spec -> (what was asked, UTC resolution time), filled by ``_resolve`` for ``_describe``.
_RESOLVED: dict[str, tuple[str, str]] = {}


def _slug(package: str) -> str:
    return package.lstrip("@").replace("/", "-")


def _resolve(versions: list[str]) -> list[str]:
    """Resolve ``<package>@latest`` per package from the registry (not called by --dry-run)."""
    exact = []
    for spec in versions:
        if not spec.endswith("@" + registry.LATEST):
            exact.append(spec)
            continue
        try:
            package, _ = registry.split_spec(spec)
            resolved = f"{package}@{registry.resolve_latest(package)}"
        except registry.RegistryPrepareError as error:
            raise ValueError(f"cannot resolve {spec}: {error}") from error
        _RESOLVED[resolved] = (spec, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        print(f"TARGET-RUN RESOLVE {TARGET} {spec} -> {resolved}", flush=True)
        exact.append(resolved)
    return exact


def _cells(versions: list[str], filters: list[str]) -> list[RunCell]:
    if filters:
        raise ValueError("decompress has no extraction-filter axis; drop --extraction-filter")
    cells = []
    for spec in versions:
        if spec.endswith("@" + registry.LATEST):  # only reached by --dry-run
            try:
                registry.split_spec(spec)
            except registry.RegistryPrepareError as error:
                raise ValueError(str(error)) from error
            cells.append(
                RunCell(
                    f"{TARGET}-{_slug(spec)} (resolved at run time)",
                    TargetAxes(target_version=spec),
                    None,
                    exploratory=True,
                )
            )
            continue
        package, version = parse_spec(spec)
        if pinned_recipe(package, version) is not None:
            cells.append(
                RunCell(
                    dirname(package, version), TargetAxes(target_version=spec), image_ref(version)
                )
            )
        elif package in registry.PACKAGES:
            cells.append(
                RunCell(
                    dirname(package, version) + "-exploratory",
                    TargetAxes(target_version=spec),
                    REGISTRY_IMAGE.format(slug=_slug(package), version=version),
                    exploratory=True,
                )
            )
        else:
            raise ValueError(
                f"{package} is not this target; the packages are {', '.join(registry.PACKAGES)}"
            )
    return cells


def _prepare(cell: RunCell) -> PrepareStep:
    if not cell.exploratory:
        return decompress_image.prepare(cell)
    spec, image = cell.axes.target_version or "", cell.image_ref or ""
    try:
        package, version = registry.split_spec(spec)
        registry.check_inputs(package, version, image)
    except registry.RegistryPrepareError as error:
        return PrepareStep(image_ref=image, commands=None, reason=str(error))
    command = (sys.executable, "-m", "scripts.decompress_registry_prepare")
    return PrepareStep(
        image_ref=image,
        commands=((*command, "--spec", spec, "--image", image),),
        reason=f"exploratory: lock from {registry.REGISTRY}, checked, then the committed recipe",
    )


def _describe(cell: RunCell, cell_dir: Path) -> Preparation | None:
    """Registry cells only: record what is inside the image and keep its lock as evidence."""
    if not cell.exploratory:
        return None
    spec, image = cell.axes.target_version or "", cell.image_ref or ""
    package, version = parse_spec(spec)
    try:
        found = registry.image_evidence(image)
    except registry.RegistryPrepareError as error:
        raise ValueError(str(error)) from error
    installed = f"{found['package']}@{found['installed_version']}"
    if installed != spec:
        raise ValueError(f"{image} has {installed} installed, requested {spec}")
    worker = registry.worker_check(registry.subprocess.run, image, package, version)
    if not worker["ok"]:
        raise ValueError(f"worker incompatible (decompress worker): {worker['reason']}")
    findings = registry.npm.lock_findings(json.loads(found["lock"]), registry.allowed_packages())
    evidence = cell_dir / "preparation"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "package-lock.json").write_bytes(found["lock"])
    asked, resolved_at = _RESOLVED.get(spec, (None, None))
    return Preparation(
        method="registry",
        requested_version=spec,
        installed_version=installed,
        lock_sha256=found["lock_sha256"],
        worker_sha256=found["worker_sha256"],
        recipe=registry.RECIPE.format(spec=spec),
        requested_spec=asked,
        resolved_at=resolved_at,
        new_dependencies=tuple(findings["new_dependencies"]),
        install_scripts_disabled=tuple(findings["install_scripts_disabled"]),
        producer_check=worker["reason"],
    )


def _plan(cell: RunCell) -> list[dict[str, Any]]:
    assert cell.axes.target_version is not None
    if cell.image_ref is None:
        return [{"note": f"{cell.axes.target_version} is resolved from the registry at run time"}]
    if cell.exploratory:
        return [{"install_step": f"registry prepare ({registry.REGISTRY})"}, *fixture_plan()]
    package, version = parse_spec(cell.axes.target_version)
    recipe = pinned_recipe(package, version)
    build = (
        f"docker build -f tools/decompress/Dockerfile --build-arg ROLE={recipe} "
        f"-t {image_ref(version)} ."
    )
    return [{"install_step": build}, *fixture_plan()]


def _run(cell: RunCell) -> list[CaseRun]:
    assert cell.axes.target_version is not None
    package, version = parse_spec(cell.axes.target_version)
    runs = []
    assert cell.image_ref is not None
    for fixture in rc.build_fixtures():
        tar_b64 = base64.b64encode(fixture.tar).decode()
        raw = run_one(package, version, tar_b64, image=cell.image_ref)
        runs.append(fixture_case(fixture, raw))
    return runs


# ---- one call for exploration: resolve, reuse-or-prepare, then check the exploration worker ----


@dataclass(frozen=True, slots=True)
class PreparedDecompress:
    """A decompress image that exists locally and whose exploration worker passed its check."""

    requested: str  # what the caller asked for (``<package>@latest`` or an exact spec)
    spec: str  # the exact ``<package>@<version>`` inside the image
    image_ref: str
    image_id: str
    exploratory: bool  # True: registry-prepared; False: committed recipe
    worker_check: str  # the offline identify+frame result


def verify_existing(cell: RunCell, image_ref: str) -> str | None:
    """Check a cell image before it is (re)used for exploration; ``None`` or the refusal reason.

    Existing images are otherwise reused unchecked, and an image built before the worker had
    ``frame`` binds fine (``identify`` exists) but then fails every step, which a campaign would
    report as a clean negative. This runs the same offline identify+frame check as registry
    preparation, for committed-recipe and registry images alike.
    """
    package, version = parse_spec(cell.axes.target_version or "")
    check = registry.worker_check(registry.subprocess.run, image_ref, package, version)
    if check["ok"]:
        return None
    return f"worker incompatible (decompress worker) in {image_ref}: {check['reason']}; rebuild it"


def ensure_image(spec: str, *, image_tag_suffix: str = "") -> PreparedDecompress:
    """Resolve ``spec``, reuse or prepare its image, and refuse it unless the worker check passes.

    Same path as ``make target-run TARGET=decompress ... AUTO_PREPARE=1``; may use the network.
    Raises ``ValueError`` with the reason (no image is tagged by a failed preparation).
    """
    from scripts.run_target import resolve_images, with_tag_suffix

    (exact,) = _resolve([spec])
    (cell,) = _cells([exact], [])
    cell = with_tag_suffix(cell, image_tag_suffix)
    ref = cell.image_ref
    if ref is None:
        raise ValueError(f"decompress {spec}: no image for this version")
    ready, errors = resolve_images(ADAPTER, [cell], auto_prepare=True)
    if ref in errors:
        raise ValueError(errors[ref])
    package, version = parse_spec(exact)
    check = registry.worker_check(registry.subprocess.run, ref, package, version)
    if not check["ok"]:
        raise ValueError(
            f"worker incompatible (decompress worker) in {ref}: {check['reason']}; rebuild it"
        )
    return PreparedDecompress(spec, exact, ref, ready[ref], cell.exploratory, check["reason"])


ADAPTER = TargetAdapter(
    mode=ResultMode.FIXTURE_REGRESSION,
    observed_contracts=("C1", "C2"),
    cells=_cells,
    plan=_plan,
    run=_run,
    prepare=_prepare,
    describe=_describe,
    resolve=_resolve,
    explore=lambda prepared, options: _explore(prepared, options),
    # Reuse check (#435): the exploration worker's offline identify+frame check, which also
    # compares the identified package and version; a version-only check would pass an image
    # whose worker predates ``frame``.
    verify_existing=lambda cell, image: verify_existing(cell, image),
)


def _explore(prepared: Any, options: Any) -> Any:
    from scripts.decompress_explore import explore

    return explore(prepared, options)
