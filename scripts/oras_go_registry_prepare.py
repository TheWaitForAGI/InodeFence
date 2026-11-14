"""Exploratory oras-go image from the public Go module proxy (part of ``AUTO_PREPARE=1``).

For an oras-go version that has **no** committed ``tools/oras-go/<role>/go.mod`` + ``go.sum``
(a committed recipe always wins; it is the reproducibility baseline, not an allowlist), this builds
``--image`` the same way the committed versions are built, except that ``go.mod``/``go.sum`` are
generated now:

1. In a disposable container of the pinned Go build image (the ``FROM golang:...@sha256:`` of
   ``tools/oras-go/Dockerfile``; nothing mounted), with ``GOPROXY=https://proxy.golang.org`` (no
   ``direct`` fallback) and ``GOSUMDB=sum.golang.org``: the container first refuses to continue if
   anything in its Go environment would skip checksum verification (``GONOSUMDB``, ``GOPRIVATE``,
   ``GOINSECURE``, ``GOFLAGS``, ``GONOSUMCHECK``/``GONOVERIFY`` non-empty, or ``GOSUMDB=off``);
   then ``go list -m oras.land/oras-go/v2@v<v>`` (the version exists), ``go mod init`` + the
   committed ``worker/main.go`` + ``go get oras.land/oras-go/v2@v<v>`` + ``go mod tidy`` (every
   downloaded module is checked by the go command against the signed checksum database) + ``go mod
   verify``. As an independent record, every ``go.sum`` module is looked up on
   ``https://sum.golang.org/lookup/`` and its ``h1:`` hashes must equal the lines in ``go.sum``.
   ``go.mod``/``go.sum`` come back on stdout and are never written into the repository.
   If the version needs a newer Go than the base image has (``requires go >= X``), the generation
   is repeated with ``GOTOOLCHAIN=goX`` set to exactly that release (never ``auto`` or a range):
   the go command downloads ``golang.org/toolchain`` from the same proxy and checks it against the
   same checksum database. A required Go equal to or older than the base downloads nothing.
2. On the host: ``go.mod`` must require exactly ``oras.land/oras-go/v2 v<v>``; ``go.sum`` must have
   that module's hash. Modules absent from every committed ``go.sum`` are **recorded, not refused**.
3. ``tools/oras-go/Dockerfile`` (unchanged: pinned base digests, the committed worker source) is
   built from a temporary context outside the repository (``ROLE=registry``) into
   ``<image>-unverified``. When a newer toolchain is needed, the build uses a copy of the
   Dockerfile in the temporary context with one added line in the build stage
   (``ENV GOTOOLCHAIN=goX GOPROXY=... GOSUMDB=...``); the committed Dockerfile and both base
   digests are unchanged, and committed (verified) versions never download a toolchain. The
   generated ``go.mod``/``go.sum`` are attached as image labels, so a later run can save them as
   evidence. A compile failure is "worker incompatible" with the compiler's error lines.
4. With ``--network none``: the worker's ``identify`` must report ``v<v>`` and the Go release
   that built it (the base Go, or exactly the downloaded toolchain); the regression run's
   program (``oras_go_cwd_hardlink.run_probe``) must extract a benign one-file archive; and the
   exploration path's ``frame`` subcommand (what ``OrasGoFrameTarget`` runs for the effect
   campaign) must extract the same archive and print a usable boundary-attempt frame, and the
   identity must bind as an ``OrasGoFrameTarget``. Otherwise: "worker incompatible", fail-closed.
5. Only then is ``<image>`` tagged; the staging tag and the temporary context are removed.

Every failure (unknown version, proxy/network error, checksum mismatch, build failure, wrong
installed version, incompatible worker) exits non-zero with its reason and leaves ``<image>``
absent: no run, verdict or result file, and a rerun starts over. An existing ``<image>`` is never
rebuilt. This does **not** make a module safe; it only pins and checks what was downloaded in this
run. The extraction run itself is offline (``--network none``).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools" / "oras-go"
DOCKERFILE = TOOLS_DIR / "Dockerfile"
WORKER_SOURCE = TOOLS_DIR / "worker" / "main.go"
MODULE = "oras.land/oras-go/v2"
PROXY = "https://proxy.golang.org"
SUMDB = "sum.golang.org"
#: Build-arg role of the temporary context (never a committed role directory name).
ROLE = "registry"
#: Prepared images live only in this repository name, never the committed-recipe name.
REGISTRY_REPOSITORY = "inodefence-oras-go-registry"
LABEL_PREFIX = "org.inodefence.oras-go."
EXACT = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
IMAGE_REF = re.compile(r"[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
STAGING = "-unverified"
GO_TIMEOUT = 600
BUILD_TIMEOUT = 1800
LIMITS = (
    "The go command checks every downloaded module against the signed checksum database "
    "(sum.golang.org), which shows that this run's modules are the ones the database has "
    "recorded for these versions; it does not make the module safe. These runs are exploratory: "
    "they are reproducible from the saved go.mod/go.sum and their SHA-256, not from a committed "
    "recipe."
)
RECIPE = (
    "tools/oras-go/Dockerfile ROLE=registry; go.mod/go.sum generated at run time from "
    f"{PROXY} with GOSUMDB={SUMDB} (pinned golang image)"
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


class RegistryPrepareError(RuntimeError):
    """A step failed; the requested image must not exist afterwards."""


def go_image(dockerfile: Path = DOCKERFILE) -> str:
    """The pinned Go build image (``FROM golang:...@sha256:...``) of the existing Dockerfile."""
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        match = re.match(r"FROM\s+(golang:\S+@sha256:[0-9a-f]{64})\s", line)
        if match:
            return match.group(1)
    raise RegistryPrepareError(f"no pinned golang image in {dockerfile}")


_REQUIRE = re.compile(r"^\s*oras\.land/oras-go/v2\s+v([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.M)


def committed_versions(tools_dir: Path = TOOLS_DIR) -> set[str]:
    """oras-go versions pinned by a committed ``<role>/go.mod`` with its ``go.sum``."""
    found = set()
    for role in tools_dir.iterdir():
        gomod = role / "go.mod"
        if role.is_dir() and gomod.is_file() and (role / "go.sum").is_file():
            match = _REQUIRE.search(gomod.read_text(encoding="utf-8"))
            if match:
                found.add(match.group(1))
    return found


def check_inputs(version: str, image: str, tools_dir: Path = TOOLS_DIR) -> None:
    """Before any docker or go call: exact X.Y.Z, an uncommitted version, a registry-only name."""
    if EXACT.fullmatch(version) is None:
        raise RegistryPrepareError(f"oras-go version must be exact X.Y.Z: {version!r}")
    if IMAGE_REF.fullmatch(image) is None or image.endswith(STAGING):
        raise RegistryPrepareError(f"not a plain image reference: {image!r}")
    if image.partition(":")[0] != REGISTRY_REPOSITORY:
        raise RegistryPrepareError(
            f"proxy-prepared images are tagged only as {REGISTRY_REPOSITORY}:<tag>, not {image!r}"
        )
    if version in committed_versions(tools_dir):
        raise RegistryPrepareError(
            f"oras-go {version} has a committed go.mod/go.sum; it uses the verified recipe, "
            "never the proxy path"
        )


def committed_modules(tools_dir: Path = TOOLS_DIR) -> set[str]:
    """Every module path in the committed ``go.sum`` files (the expected dependency closure)."""
    names: set[str] = set()
    for gosum in sorted(tools_dir.glob("*/go.sum")):
        for line in gosum.read_text(encoding="utf-8").splitlines():
            if line.strip():
                names.add(line.split()[0])
    if MODULE not in names:
        raise RegistryPrepareError("no committed go.sum to compare dependencies with")
    return names


# ---- the disposable Go container ----

#: Environment the container must have before any module is downloaded. Checked inside the
#: container (``go env`` + plain env), so an image default cannot silently skip verification.
_ENV_GUARD = r"""
export GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org GOTOOLCHAIN="${TC:-local}"
case "$GOTOOLCHAIN" in
  local) ;;
  go1.[0-9]*.[0-9]*) echo "INODEFENCE-TOOLCHAIN downloading $GOTOOLCHAIN" >&2 ;;
  *) echo "INODEFENCE-ENV refusing GOTOOLCHAIN=$GOTOOLCHAIN" >&2; exit 7 ;;
esac
go version >&2 || exit 9
bad="$(go env GONOSUMDB GOPRIVATE GOINSECURE GOFLAGS | tr -d '\n')${GONOSUMCHECK:-}${GONOVERIFY:-}"
if [ -n "$bad" ] || [ "$(go env GOSUMDB)" != "sum.golang.org" ]; then
  echo "INODEFENCE-ENV checksum verification would be skipped: $bad $(go env GOSUMDB)" >&2
  exit 7
fi
if [ "$(go env GOPROXY)" != "https://proxy.golang.org" ]; then
  echo "INODEFENCE-ENV unexpected GOPROXY $(go env GOPROXY)" >&2
  exit 7
fi
"""

_RESOLVE_SCRIPT = _ENV_GUARD + 'go list -m -f "{{.Version}}" oras.land/oras-go/v2@latest\n'

_GENERATE_SCRIPT = (
    _ENV_GUARD
    + r"""
set -e
go list -m -f '{{.Version}}' "oras.land/oras-go/v2@v$V" >/dev/null
mkdir -p /tmp/w && cd /tmp/w
printf '%s' "$MAIN_B64" | base64 -d > main.go
go mod init worker >/dev/null 2>&1
go get "oras.land/oras-go/v2@v$V" >&2
go mod tidy >&2
go mod verify >&2
printf 'GOMOD %s\n' "$(base64 -w0 go.mod)"
printf 'GOSUM %s\n' "$(base64 -w0 go.sum)"
printf 'GOVERSION %s\n' "$(go env GOVERSION)"
printf 'BASEGO %s\n' "$(GOTOOLCHAIN=local go env GOVERSION)"
awk '{v=$2; sub("/go.mod$", "", v); print $1 "@" v}' go.sum | sort -u | while read -r m; do
  e="$(printf '%s' "$m" | sed 's/[A-Z]/!\L&/g')"
  body="$(curl -fsS --max-time 60 "https://sum.golang.org/lookup/$e")" || {
    echo "INODEFENCE-LOOKUP failed for $m" >&2; exit 8; }
  printf 'LOOKUP %s %s\n' "$m" "$(printf '%s' "$body" | base64 -w0)"
done
"""
)


def _go(runner: Runner, image: str, script: str, env: dict[str, str]) -> str:
    """Run ``script`` in a disposable container of the pinned Go image (proxy access)."""
    command = ["docker", "run", "--rm"]
    for key, value in env.items():
        command += ["-e", f"{key}={value}"]
    command += ["--entrypoint", "sh", image, "-c", script]
    try:
        done = runner(command, capture_output=True, text=True, timeout=GO_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise RegistryPrepareError(f"go container failed: {type(error).__name__}") from error
    if done.returncode != 0:
        raise RegistryPrepareError(go_failure(done.stderr or "", done.returncode))
    return done.stdout or ""


_NETWORK_MARKS = (
    "no such host",
    "dial tcp",
    "i/o timeout",
    "connection refused",
    "connection reset",
    "network is unreachable",
    "TLS handshake timeout",
    "Temporary failure in name resolution",
)
_NOT_FOUND_MARKS = (
    "unknown revision",
    "invalid version",
    "404 Not Found",
    "410 Gone",
    "no matching",
)
_CHECKSUM_MARKS = ("SECURITY ERROR", "checksum mismatch", "verifying module", "has been modified")


def go_failure(stderr: str, returncode: int = 1) -> str:
    """A precise reason from the go command's error output (the order matters: checksum first)."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]

    def first(marks: tuple[str, ...]) -> str:
        return next((line for line in lines if any(m in line for m in marks)), "")[:300]

    if returncode == 7 or any("INODEFENCE-ENV" in line for line in lines):
        return f"refused: {first(('INODEFENCE-ENV',)) or 'Go environment check failed'}"
    if any(m in stderr for m in _CHECKSUM_MARKS):
        return f"checksum mismatch against {SUMDB}: {first(_CHECKSUM_MARKS)}"
    if any(m in stderr for m in _NETWORK_MARKS):
        return f"module proxy unreachable ({first(_NETWORK_MARKS)}); nothing was prepared"
    if returncode == 9:
        return f"toolchain download failed: {(lines[-1] if lines else 'no output')[:300]}"
    if any(m in stderr for m in _NOT_FOUND_MARKS):
        return f"version not found on {PROXY}: {first(_NOT_FOUND_MARKS)}"
    if returncode == 8 or any("INODEFENCE-LOOKUP" in line for line in lines):
        return f"{SUMDB} lookup failed: {first(('INODEFENCE-LOOKUP',))}"
    if any("requires go >=" in line for line in lines):
        return f"toolchain too old for this version: {first(('requires go >=',))}"
    return f"go step failed: {(lines[-1] if lines else 'no output')[:300]}"


def resolve_latest(runner: Runner = subprocess.run, image: str | None = None) -> str:
    """The proxy's current latest release of ``oras.land/oras-go/v2`` as an exact X.Y.Z."""
    out = _go(runner, image or go_image(), _RESOLVE_SCRIPT, {})
    seen = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if not seen.startswith("v") or EXACT.fullmatch(seen[1:]) is None:
        raise RegistryPrepareError(f"proxy latest for {MODULE} is not an exact release: {seen!r}")
    return seen[1:]


def parse_generated(stdout: str) -> dict[str, Any]:
    """go.mod/go.sum bytes, Go version and the per-module sumdb lookup bodies from the container."""
    found: dict[str, Any] = {"lookups": {}}
    for line in stdout.splitlines():
        key, _, rest = line.partition(" ")
        if key in ("GOMOD", "GOSUM"):
            found[key.lower()] = base64.b64decode(rest)
        elif key == "GOVERSION":
            found["go_version"] = rest.strip()
        elif key == "BASEGO":
            found["base_go"] = rest.strip()
        elif key == "LOOKUP":
            module, _, body = rest.partition(" ")
            found["lookups"][module] = base64.b64decode(body).decode("utf-8", "replace")
    if "gomod" not in found or "gosum" not in found:
        raise RegistryPrepareError("go step produced no go.mod/go.sum")
    return found


def gosum_entries(gosum: bytes) -> dict[str, str]:
    """``"<module> <version>[/go.mod]"`` -> ``h1:`` hash, from go.sum (or a sumdb lookup body)."""
    entries = {}
    for line in gosum.decode("utf-8").splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].startswith("h1:"):
            entries[f"{parts[0]} {parts[1]}"] = parts[2]
    return entries


def check_generated(found: dict[str, Any], version: str) -> None:
    """Fail unless go.mod pins exactly ``v<version>`` and every go.sum line matches its lookup."""
    match = _REQUIRE.search(found["gomod"].decode("utf-8"))
    if match is None or match.group(1) != version:
        pinned = match.group(1) if match else None
        raise RegistryPrepareError(f"generated go.mod pins oras-go {pinned!r}, expected {version}")
    entries = gosum_entries(found["gosum"])
    if f"{MODULE} v{version}" not in entries:
        raise RegistryPrepareError(f"generated go.sum has no hash for {MODULE} v{version}")
    for key, digest in entries.items():
        module, version_part = key.split(" ")
        spec = f"{module}@{version_part.removesuffix('/go.mod')}"
        body = found["lookups"].get(spec)
        if body is None:
            raise RegistryPrepareError(f"no {SUMDB} lookup recorded for {spec}")
        if gosum_entries(body.encode()).get(key) != digest:
            raise RegistryPrepareError(
                f"checksum mismatch against {SUMDB}: {key} go.sum {digest} differs from the lookup"
            )


def new_modules(gosum: bytes, allowed: set[str]) -> list[dict[str, str]]:
    """Recorded, not refused: modules in no committed go.sum (module path, version, ``h1:``)."""
    out: dict[str, dict[str, str]] = {}
    for key, digest in gosum_entries(gosum).items():
        module, version = key.split(" ")
        if module in allowed:
            continue
        if version.endswith("/go.mod"):
            out.setdefault(module, {"name": module, "version": version[:-7], "integrity": digest})
        else:
            out[module] = {"name": module, "version": version, "integrity": digest}
    return [out[name] for name in sorted(out)]


#: An exact Go release toolchain name; the only ``GOTOOLCHAIN`` value ever set besides ``local``.
TOOLCHAIN = re.compile(r"go1\.[0-9]+\.[0-9]+")
_REQUIRES = re.compile(r"requires go >= ([0-9][0-9.]*) \(running go ([0-9][0-9.]*)")


def _release(name: str) -> tuple[int, ...]:
    """``go1.26.0`` / ``1.26.0`` -> ``(1, 26, 0)``; anything else is refused."""
    name = name if name.startswith("go") else f"go{name}"
    if TOOLCHAIN.fullmatch(name) is None:
        raise RegistryPrepareError(f"not an exact Go release: {name!r}")
    return tuple(int(part) for part in name[2:].split("."))


def required_toolchain(gomod: bytes, base_go: str) -> str | None:
    """The exact toolchain go.mod needs when it is newer than the base image's Go, else None.

    The need is the larger of the ``go`` and ``toolchain`` directives; it must be an exact release
    (``go1.N.M``). Equal to or older than the base -> nothing is downloaded.
    """
    text = gomod.decode("utf-8")
    go = re.search(r"^go\s+(\S+)\s*$", text, re.M)
    if go is None:
        raise RegistryPrepareError("generated go.mod has no go directive")
    needs = [go.group(1)]
    pinned = re.search(r"^toolchain\s+(\S+)\s*$", text, re.M)
    if pinned is not None:
        needs.append(pinned.group(1))
    need = max(needs, key=_release)
    if _release(need) <= _release(base_go):
        return None
    return f"go{_release(need)[0]}.{_release(need)[1]}.{_release(need)[2]}"


def generate(
    runner: Runner, image: str, version: str, log: Callable[[str], None] = print
) -> dict[str, Any]:
    """go.mod/go.sum for ``v<version>``; a newer required Go is fetched only as an exact release.

    First with the base image's own Go (``GOTOOLCHAIN=local``). If the module requires a newer
    Go, that exact release is downloaded by the go command itself (``golang.org/toolchain`` from
    the proxy, checked against the checksum database) and the generation is repeated with it.
    """
    env = {"V": version, "MAIN_B64": base64.b64encode(WORKER_SOURCE.read_bytes()).decode()}
    try:
        out = _go(runner, image, _GENERATE_SCRIPT, env)
    except RegistryPrepareError as error:
        match = _REQUIRES.search(str(error))
        if match is None:
            raise
        required, running = match.group(1), match.group(2)
        if _release(required) <= _release(running):
            raise
        toolchain = "go" + ".".join(str(part) for part in _release(required))
        log(
            f"PROXY-PREPARE {MODULE}@v{version} requires go >= {required}; base image has "
            f"go{running}; toolchain {toolchain} via golang.org/toolchain ({PROXY}, {SUMDB})"
        )
        out = _go(runner, image, _GENERATE_SCRIPT, {**env, "TC": toolchain})
    found = parse_generated(out)
    check_generated(found, version)
    base_go = str(found.get("base_go", ""))
    _release(base_go)
    found["toolchain"] = required_toolchain(found["gomod"], base_go)
    if found["toolchain"] is not None and found.get("go_version") != found["toolchain"]:
        raise RegistryPrepareError(
            f"go.mod needs {found['toolchain']} but generation ran {found.get('go_version')!r}"
        )
    return found


def dockerfile_with_toolchain(toolchain: str, dockerfile: Path = DOCKERFILE) -> str:
    """The committed Dockerfile plus one ``ENV`` line in the build stage (temporary copy only)."""
    if TOOLCHAIN.fullmatch(toolchain) is None:
        raise RegistryPrepareError(f"not an exact Go release: {toolchain!r}")
    lines = dockerfile.read_text(encoding="utf-8").splitlines(keepends=True)
    stages = [
        i for i, line in enumerate(lines) if re.match(r"FROM\s+golang:\S+\s+AS\s+build", line)
    ]
    if len(stages) != 1:
        raise RegistryPrepareError(f"expected one golang build stage in {dockerfile}")
    env = f"ENV GOTOOLCHAIN={toolchain} GOPROXY={PROXY} GOSUMDB={SUMDB}\n"
    lines.insert(stages[0] + 1, env)
    return "".join(lines)


def build_context(gomod: bytes, gosum: bytes, root: Path) -> Path:
    """A temporary build context outside the repository with the Dockerfile's expected layout."""
    role = root / "tools" / "oras-go" / ROLE
    role.mkdir(parents=True)
    (role / "go.mod").write_bytes(gomod)
    (role / "go.sum").write_bytes(gosum)
    worker = root / "tools" / "oras-go" / "worker"
    worker.mkdir(parents=True)
    shutil.copyfile(WORKER_SOURCE, worker / "main.go")
    return root


_COMPILE_ERROR = re.compile(r"(?:\./)?main\.go:\d+:\d+: .+")


def build_failure(stderr: str) -> str:
    """``worker incompatible`` plus the compiler lines if main.go did not compile, else the tail."""
    errors = [m.group(0).strip() for m in _COMPILE_ERROR.finditer(stderr)]
    if errors:
        unique = list(dict.fromkeys(errors))[:5]
        return "worker incompatible (compile error): " + "; ".join(unique)
    reason = go_failure(stderr)
    if not reason.startswith("go step failed"):
        return f"build failed: {reason}"
    return f"build failed: {stderr.strip()[-300:]}"


def _docker(runner: Runner, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RegistryPrepareError(f"docker {args[0]} failed: {type(error).__name__}") from error


def identify(runner: Runner, image: str) -> dict[str, str]:
    """The worker's offline ``identify`` JSON (oras-go version, Go version, worker SHA-256)."""
    done = _docker(runner, ["run", "--rm", "--network", "none", image, "identify"], 120)
    try:
        data = json.loads((done.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        data = None
    if done.returncode != 0 or not isinstance(data, dict):
        raise RegistryPrepareError(f"identify failed in {image}: {(done.stderr or '')[-200:]}")
    return {
        key: str(data.get(key, "")) for key in ("oras_go_version", "go_version", "worker_sha256")
    }


BENIGN = [{"name": "d/ok.txt", "type": "reg", "content": b"ok\n"}]


def probe_check(image: str, probe: Callable[..., dict[str, Any]] | None = None) -> None:
    """Offline: the regression run's own program must extract a benign one-file archive."""
    from experiments.repro import oras_go_cwd_hardlink as ogh

    run = probe or ogh.run_probe
    tar = base64.b64encode(ogh.build_tar(BENIGN)).decode()
    raw = run("check", tar, base64.b64encode(ogh.SENTINEL_CONTENT).decode(), image=image)
    ok = (
        isinstance(raw, dict)
        and not raw.get("_run_error")
        and raw.get("declined") is None
        and "d/ok.txt" in (raw.get("extract_tree") or {})
        and not raw.get("shared_identity")
    )
    if not ok:
        raise RegistryPrepareError(f"worker incompatible (probe): {str(raw)[:300]}")


def _frame_input() -> bytes:
    """The sandbox for the ``frame`` check: /work/archive/input.tar and an empty /work/extract."""
    from experiments.repro import oras_go_cwd_hardlink as ogh

    archive = ogh.build_tar(BENIGN)
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in ("work", "work/archive", "work/extract"):
            info = tarfile.TarInfo(name)
            info.type, info.mode = tarfile.DIRTYPE, 0o777
            tar.addfile(info)
        info = tarfile.TarInfo("work/archive/input.tar")
        info.size, info.mode = len(archive), 0o644
        tar.addfile(info, io.BytesIO(archive))
    return out.getvalue()


def frame_check(runner: Runner, image: str, version: str) -> dict[str, Any]:
    """Offline: the campaign's ``frame`` subcommand on a benign archive, and its identity binding.

    The sandbox is copied into a created (not started) container with ``docker cp``; nothing is
    mounted. Returns ``ok``, the reason, and the worker SHA-256 the campaign target would bind.
    """
    from inodefence.effect_pipeline_oras_go import _parse_frame
    from inodefence.targets.oras_go_effect import OrasGoFrameTarget

    ident = identify(runner, image)
    inspect = _docker(runner, ["image", "inspect", "--format", "{{.Id}}", image], 60)
    image_id = (inspect.stdout or "").strip()
    try:
        OrasGoFrameTarget(
            image_id, ident["oras_go_version"], ident["go_version"], ident["worker_sha256"]
        )
    except ValueError as error:
        return {"ok": False, "reason": f"campaign target would not bind: {error}"}
    create = _docker(
        runner,
        [
            "create",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            image,
            "frame",
            "/work/archive/input.tar",
            "/work/extract",
        ],
        60,
    )
    container = (create.stdout or "").strip()
    if create.returncode != 0 or not container:
        return {
            "ok": False,
            "reason": f"frame container not created: {(create.stderr or '')[-200:]}",
        }
    try:
        copy = runner(
            ["docker", "cp", "-", f"{container}:/"],
            input=_frame_input(),
            capture_output=True,
            timeout=60,
            check=False,
        )
        if copy.returncode != 0:
            return {"ok": False, "reason": "frame sandbox could not be copied in"}
        done = _docker(runner, ["start", "-a", container], 120)
    finally:
        _docker(runner, ["rm", "-f", container], 60)
    frame, error = _parse_frame(done.stdout or "")
    attempts = (frame or {}).get("attempts") or []
    expected = {
        "created_path": "extract/d/ok.txt",
        "operation": "regular",
        "aliases_external_object": False,
    }
    if done.returncode != 0:
        reason = f"frame run failed (exit {done.returncode}): {(done.stderr or '').strip()[-200:]}"
    elif frame is None:
        reason = f"frame unusable: {error}"
    elif frame.get("extractor") != f"{MODULE}@v{version}":
        reason = f"frame names extractor {frame.get('extractor')!r}, expected {MODULE}@v{version}"
    elif not any(all(a.get(k) == v for k, v in expected.items()) for a in attempts):
        reason = f"frame did not report the benign file: {attempts}"
    else:
        reason = f"frame worker extracted a benign archive ({len(attempts)} attempt)"
    return {
        "ok": reason.startswith("frame worker extracted"),
        "reason": reason,
        "worker_sha256": ident["worker_sha256"],
    }


def exists(runner: Runner, image: str) -> bool:
    return _docker(runner, ["image", "inspect", image], 60).returncode == 0


def prepare(
    version: str,
    image: str,
    *,
    runner: Runner = subprocess.run,
    probe: Callable[..., dict[str, Any]] | None = None,
    log: Callable[[str], None] = print,
) -> str:
    """Run steps 1-5; return go.sum's SHA-256. Raises ``RegistryPrepareError`` on any failure."""
    check_inputs(version, image)
    if exists(runner, image):
        log(f"PROXY-PREPARE reuse {image} (already present; not rebuilt)")
        return ""
    allowed = committed_modules()
    base_image = go_image()
    found = generate(runner, base_image, version, log)
    toolchain = found["toolchain"]
    if toolchain is not None:
        log(
            f"PROXY-PREPARE toolchain {toolchain} downloaded (툴체인 {toolchain} 내려받음) "
            f"via golang.org/toolchain, verified by {SUMDB}; base image {base_image} "
            f"({found['base_go']}) unchanged"
        )
    gosum_sha = hashlib.sha256(found["gosum"]).hexdigest()
    modules = sorted(found["lookups"])
    log(
        f"PROXY-PREPARE {MODULE}@v{version} go.mod/go.sum made with {found.get('go_version')}; "
        f"go.sum sha256={gosum_sha}; checksum database {SUMDB} verified by the go command and "
        f"lookup matched for {len(modules)} modules: {', '.join(modules)}"
    )
    for dep in new_modules(found["gosum"], allowed):
        log(
            "PROXY-PREPARE new module (recorded, not in committed go.sum): "
            f"{dep['name']}@{dep['version']} {dep['integrity']}"
        )
    staging = f"{image}{STAGING}"
    labels = {
        "gomod": base64.b64encode(found["gomod"]).decode(),
        "gosum": base64.b64encode(found["gosum"]).decode(),
        "requested": version,
        "sumdb": f"{SUMDB}: go command verified; lookup matched {len(modules)} modules",
        "base_image": base_image,
        "base_go": str(found["base_go"]),
        "toolchain_required": toolchain or "none",
        "toolchain_used": str(found.get("go_version", "")),
    }
    with tempfile.TemporaryDirectory(prefix="inodefence-oras-go-proxy-") as tmp:
        context = build_context(found["gomod"], found["gosum"], Path(tmp))
        dockerfile = DOCKERFILE
        if toolchain is not None:
            dockerfile = Path(tmp) / "Dockerfile.toolchain"
            dockerfile.write_text(dockerfile_with_toolchain(toolchain), encoding="utf-8")
        build = ["build", "-q", "-f", str(dockerfile), "--build-arg", f"ROLE={ROLE}"]
        for key, value in labels.items():
            build += ["--label", f"{LABEL_PREFIX}{key}={value}"]
        build += ["-t", staging, str(context)]
        done = _docker(runner, build, BUILD_TIMEOUT)
        if done.returncode != 0:
            raise RegistryPrepareError(build_failure(done.stderr or ""))
    try:
        ident = identify(runner, staging)
        seen = ident["oras_go_version"]
        if seen != f"v{version}":
            raise RegistryPrepareError(f"{staging} reports oras-go {seen!r}, expected v{version}")
        expected_go = toolchain or found["base_go"]
        if ident["go_version"] != expected_go:
            raise RegistryPrepareError(
                f"{staging} was built with {ident['go_version']!r}, expected {expected_go}"
            )
        probe_check(staging, probe)
        frame = frame_check(runner, staging, version)
        if not frame["ok"]:
            raise RegistryPrepareError(f"worker incompatible (frame): {frame['reason']}")
        log(f"PROXY-PREPARE {frame['reason']}; worker sha256={frame['worker_sha256']}")
        if _docker(runner, ["tag", staging, image], 60).returncode != 0:
            raise RegistryPrepareError(f"tag {staging} -> {image} failed")
        log(f"PROXY-PREPARE verified oras-go {seen} offline; tagged {image}")
    finally:
        _docker(runner, ["rmi", "--no-prune", staging], 60)
    return gosum_sha


def image_evidence(image: str, runner: Runner | None = None) -> dict[str, Any]:
    """Offline: the oras-go version and worker hash in ``image``, and its go.mod/go.sum labels."""
    runner = runner or subprocess.run
    done = _docker(runner, ["image", "inspect", "--format", "{{json .Config.Labels}}", image], 60)
    try:
        labels = json.loads((done.stdout or "").strip() or "null") or {}
        gomod = base64.b64decode(labels[f"{LABEL_PREFIX}gomod"])
        gosum = base64.b64decode(labels[f"{LABEL_PREFIX}gosum"])
    except (ValueError, KeyError, TypeError) as error:
        raise RegistryPrepareError(f"{image} carries no go.mod/go.sum labels") from error
    ident = identify(runner, image)
    return {
        "installed_version": ident["oras_go_version"].removeprefix("v"),
        "go_version": ident["go_version"],
        "worker_sha256": ident["worker_sha256"],
        "gomod": gomod,
        "gosum": gosum,
        "gosum_sha256": hashlib.sha256(gosum).hexdigest(),
        "sumdb": str(labels.get(f"{LABEL_PREFIX}sumdb", "")),
        "base_image": str(labels.get(f"{LABEL_PREFIX}base_image", "")),
        "toolchain_required": str(labels.get(f"{LABEL_PREFIX}toolchain_required", "")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="exploratory oras-go image from the Go proxy")
    parser.add_argument("--version", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args(argv)
    try:
        prepare(args.version, args.image)
    except RegistryPrepareError as error:
        print(f"PROXY-PREPARE FAIL: {error}; {args.image} not created", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
