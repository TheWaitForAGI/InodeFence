"""Docker-free checks of the Rust `tar` crate image recipe and worker source (Tier-B, D039).

The worker cannot be compiled in the portable suite, so these pin the contract the Python adapters
rely on: the worker's subcommands/exit codes and `identify` keys match the adapter, the crate runs
through the standard `Archive::unpack` path with default settings, every role pins one exact crate
release with a lock-enforced build, base images are digest-pinned, and no advisory identifier
leaks into generic oracle/feedback code (D005).
"""

import re
from pathlib import Path

import pytest

from inodefence.targets.rust_tar import IDENTITY_KEYS, WORKER

_ROOT = Path(__file__).resolve().parents[1]
_RECIPE = _ROOT / "tools" / "rust-tar"
_WORKER_SOURCE = (_RECIPE / "worker" / "src" / "main.rs").read_text(encoding="utf-8")
_DOCKERFILE = (_RECIPE / "Dockerfile").read_text(encoding="utf-8")
_PINS = {"affected": "0.4.35", "fixed": "0.4.36"}


def test_worker_speaks_the_oras_go_protocol() -> None:
    for subcommand in ("identify", "extract", "frame", "probe"):
        assert f'"{subcommand}" =>' in _WORKER_SOURCE
    # 2 = crate refused/failed (REJECTED), 3 = harness/IO failure, as in the oras-go worker.
    assert "process::exit(2)" in _WORKER_SOURCE
    assert "die(3," in _WORKER_SOURCE
    assert 'const FRAME_FORMAT: &str = "inodefence-boundary-attempt-v1";' in _WORKER_SOURCE
    for key in IDENTITY_KEYS:
        assert f'("{key}",' in _WORKER_SOURCE
    assert WORKER == "/target/rust-tar-worker"
    assert 'ENTRYPOINT ["/target/rust-tar-worker"]' in _DOCKERFILE


def test_worker_uses_the_standard_unpack_path_with_default_settings() -> None:
    assert "tar::Archive::new(" in _WORKER_SOURCE
    assert "archive.unpack(dest)" in _WORKER_SOURCE
    # Any Archive/Entry setter would replace the library's own behaviour with custom hardening.
    assert re.search(r"\.set_[a-z_]+\(", _WORKER_SOURCE) is None
    assert "unpack_in(" not in _WORKER_SOURCE


@pytest.mark.parametrize(("role", "version"), sorted(_PINS.items()))
def test_each_role_pins_one_exact_crate_release(role: str, version: str) -> None:
    manifest = (_RECIPE / role / "Cargo.toml").read_text(encoding="utf-8")
    assert re.findall(r'^tar = "=([^"]+)"$', manifest, flags=re.MULTILINE) == [version]
    assert 'build = "../worker/build.rs"' in manifest
    assert 'path = "../worker/src/main.rs"' in manifest
    # Only the comment header and the pin differ between roles.
    other = "fixed" if role == "affected" else "affected"
    other_manifest = (_RECIPE / other / "Cargo.toml").read_text(encoding="utf-8")
    differing = [
        line
        for line, other_line in zip(manifest.splitlines(), other_manifest.splitlines(), strict=True)
        if line != other_line
    ]
    assert len(differing) == 2


def test_dockerfile_is_digest_pinned_lock_enforced_and_non_root() -> None:
    froms = re.findall(r"^FROM (\S+)", _DOCKERFILE, flags=re.MULTILINE)
    assert len(froms) == 2
    assert all(re.search(r"@sha256:[0-9a-f]{64}$", image) for image in froms)
    assert froms[-1].startswith("gcr.io/distroless/cc-debian12:nonroot@")
    # The role's Cargo.lock is copied by name (a missing lock fails the build) and enforced.
    assert "tools/rust-tar/${ROLE}/Cargo.lock" in _DOCKERFILE
    assert "cargo build --locked --release" in _DOCKERFILE
    assert "test -s Cargo.lock" in _DOCKERFILE
    build_script = (_RECIPE / "worker" / "build.rs").read_text(encoding="utf-8")
    assert 'join("Cargo.lock")' in build_script and "panic!(" in build_script


def test_no_advisory_identifier_in_generic_oracle_or_feedback_code() -> None:
    generic = [
        *(_ROOT / "src" / "inodefence" / "oracle").rglob("*.py"),
        *(_ROOT / "src" / "inodefence" / "feedback").rglob("*.py"),
        *(_ROOT / "src" / "inodefence" / "targets").glob("rust_tar*.py"),
    ]
    assert generic
    for path in generic:
        text = path.read_text(encoding="utf-8")
        assert "RUSTSEC" not in text and "CVE-2021-38511" not in text, path
