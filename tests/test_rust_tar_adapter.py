"""Portable tests for the Rust `tar` crate target descriptor (Tier-B, D039): invocation, version
identity, status classification and package registration. They do not run a container and do not
claim real containment -- the real extraction lives in the post-EXP-0 fixture probe.
"""

import json
from pathlib import Path

import pytest

import inodefence.targets as targets
from inodefence.execution.base import BackendError, ContainerOutcome
from inodefence.model import ExecutionStatus
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import ExecutionSafety
from inodefence.targets.rust_tar import IDENTITY_KEYS, WORKER, RustTarTarget

_IMAGE = "sha256:" + "a" * 64
_LOCK_SHA = "c" * 64
_WORKER_SHA = "b" * 64


def _target(
    image_id: str = _IMAGE,
    tar_crate_version: str = "0.4.35",
    rustc_version: str = "1.99.1",
    cargo_lock_sha256: str = _LOCK_SHA,
    worker_sha256: str = _WORKER_SHA,
    timeout_seconds: float = 10.0,
) -> RustTarTarget:
    return RustTarTarget(
        image_id,
        tar_crate_version,
        rustc_version,
        cargo_lock_sha256,
        worker_sha256,
        timeout_seconds,
    )


def _identity_json(target: RustTarTarget) -> bytes:
    return json.dumps({key: getattr(target, key) for key in IDENTITY_KEYS}).encode()


def test_package_exports_the_rust_tar_adapters() -> None:
    assert targets.RustTarTarget is RustTarTarget
    assert "RustTarTarget" in targets.__all__
    assert "RustTarFrameTarget" in targets.__all__


def test_provenance_declares_isolation_required_and_exact_versions() -> None:
    provenance = _target().provenance
    assert provenance.target_id == "rust-tar"
    assert provenance.target_version == "tar=0.4.35;rustc=1.99.1"
    assert provenance.timeout_seconds == 10.0
    # Third-party target: the descriptor must require OS containment, never TRUSTED_REFERENCE.
    assert provenance.execution_safety == ExecutionSafety.ISOLATION_REQUIRED


def test_command_identity_command_and_artifacts() -> None:
    target = _target()
    assert target.command(Path("/s/archive/input.tar"), Path("/s/extract")) == (
        WORKER,
        "extract",
        "/s/archive/input.tar",
        "/s/extract",
    )
    assert target.identity_command == (WORKER, "identify")
    # Container target: the preregistration binding is the image id (targets.<id>.image_digest),
    # as for node-tar/oras-go/decompress; lock_digest is reserved for in-process targets.
    assert target.image_digest == _IMAGE
    # The Cargo.lock digest is build-recipe provenance (like node-tar's recipe_sha256), carried
    # as an identity artifact next to the worker digest -- not the registration digest.
    assert target.artifacts == (
        ArtifactDigest("rust-tar-cargo-lock", _LOCK_SHA),
        ArtifactDigest("rust-tar-worker", _WORKER_SHA),
    )


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [
        (0, ExecutionStatus.SUCCESS),
        (2, ExecutionStatus.REJECTED),  # the crate refused/failed the extraction
        (1, ExecutionStatus.FAILED),
        (3, ExecutionStatus.FAILED),  # harness/IO failure in the worker
        (101, ExecutionStatus.FAILED),  # a Rust panic exits 101: never read as a crate refusal
        (None, ExecutionStatus.TIMED_OUT),
    ],
)
def test_classify_maps_exit_codes(exit_code: int | None, expected: ExecutionStatus) -> None:
    target = _target()
    command = target.command(Path("/s/archive/input.tar"), Path("/s/extract"))
    outcome = ContainerOutcome(exit_code, b"out", b"err", 0.25, False)
    result = target.classify(outcome, command)
    assert result.status == expected
    assert result.exit_code == exit_code
    assert result.target_id == "rust-tar"
    assert result.target_version == "tar=0.4.35;rustc=1.99.1"
    assert result.stdout == "out"
    assert result.stderr == "err"
    assert result.duration_seconds == 0.25
    assert result.timeout_seconds == 10.0


def test_verify_identity_accepts_matching_metadata_and_rejects_drift() -> None:
    target = _target()
    assert target.verify_identity(_identity_json(target)) == target.artifacts

    for drift in (
        {"tar_crate_version": "0.4.36"},
        {"rustc_version": "1.99.0"},
        {"cargo_lock_sha256": "d" * 64},
        {"worker_sha256": "e" * 64},
    ):
        drifted = json.loads(_identity_json(target))
        drifted.update(drift)
        with pytest.raises(BackendError, match="identity changed"):
            target.verify_identity(json.dumps(drifted).encode())

    with pytest.raises(BackendError, match="invalid identity metadata"):
        target.verify_identity(b"not json")
    with pytest.raises(BackendError, match="invalid identity metadata"):
        target.verify_identity(b"[]")
    missing = json.loads(_identity_json(target))
    del missing["cargo_lock_sha256"]
    with pytest.raises(BackendError, match="invalid identity metadata"):
        target.verify_identity(json.dumps(missing).encode())


@pytest.mark.parametrize(
    "override",
    [
        {"image_id": "0.4.35"},  # not an immutable sha256 image id
        {"image_id": "sha256:" + "a" * 63},
        {"tar_crate_version": "v0.4.35"},  # crates.io versions carry no leading v
        {"tar_crate_version": ""},  # identify found no `tar` package in the lock
        {"tar_crate_version": "latest"},
        {"rustc_version": "rustc 1.99.1"},
        {"cargo_lock_sha256": "C" * 64},  # uppercase hex
        {"worker_sha256": "nothex"},
    ],
)
def test_construction_rejects_malformed_identity(override: dict[str, str]) -> None:
    fields = {
        "image_id": _IMAGE,
        "tar_crate_version": "0.4.35",
        "rustc_version": "1.99.1",
        "cargo_lock_sha256": _LOCK_SHA,
        "worker_sha256": _WORKER_SHA,
        **override,
    }
    with pytest.raises(ValueError):
        RustTarTarget(
            fields["image_id"],
            fields["tar_crate_version"],
            fields["rustc_version"],
            fields["cargo_lock_sha256"],
            fields["worker_sha256"],
        )


def test_timeout_bounds_are_enforced() -> None:
    with pytest.raises(ValueError):
        _target(timeout_seconds=0)
    with pytest.raises(ValueError):
        _target(timeout_seconds=121)
