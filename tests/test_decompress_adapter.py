"""Portable tests for the decompress target descriptor (M4.2): invocation, version identity and
status classification. They do not run a container and do not claim real containment -- the real
extraction lives in the capability probe and the controller-run container closure.
"""

import json
from pathlib import Path

import pytest

from inodefence.execution.base import BackendError, ContainerOutcome
from inodefence.model import ExecutionStatus
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import ExecutionSafety
from inodefence.targets.decompress_js import NODE, WORKER, DecompressJsTarget

_IMAGE = "sha256:" + "a" * 64
_WORKER_SHA = "b" * 64


def _target(
    image_id: str = _IMAGE,
    decompress_module: str = "decompress",
    decompress_version: str = "4.2.1",
    node_version: str = "22.23.4",
    worker_sha256: str = _WORKER_SHA,
    timeout_seconds: float = 10.0,
) -> DecompressJsTarget:
    return DecompressJsTarget(
        image_id,
        decompress_module,
        decompress_version,
        node_version,
        worker_sha256,
        timeout_seconds,
    )


def _identity_json(target: DecompressJsTarget) -> bytes:
    return json.dumps(
        {
            "decompress_module": target.decompress_module,
            "decompress_version": target.decompress_version,
            "node_version": target.node_version,
            "worker_sha256": target.worker_sha256,
        }
    ).encode()


def test_provenance_declares_isolation_required_and_exact_versions() -> None:
    provenance = _target().provenance
    assert provenance.target_id == "decompress"
    assert provenance.target_version == "decompress=decompress@4.2.1;node=22.23.4"
    assert provenance.timeout_seconds == 10.0
    # Third-party target: the descriptor must require OS containment, never TRUSTED_REFERENCE.
    assert provenance.execution_safety == ExecutionSafety.ISOLATION_REQUIRED


def test_fork_module_is_recorded_in_provenance() -> None:
    provenance = _target(
        decompress_module="@xhmikosr/decompress", decompress_version="11.1.4"
    ).provenance
    assert provenance.target_version == "decompress=@xhmikosr/decompress@11.1.4;node=22.23.4"


def test_command_and_identity_command_shape() -> None:
    target = _target()
    assert target.command(Path("/s/archive/input.tar"), Path("/s/extract")) == (
        NODE,
        WORKER,
        "extract",
        "/s/archive/input.tar",
        "/s/extract",
    )
    assert target.identity_command == (NODE, WORKER, "identify")
    assert target.artifacts == (ArtifactDigest("decompress-worker", _WORKER_SHA),)


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [
        (0, ExecutionStatus.SUCCESS),
        (2, ExecutionStatus.REJECTED),  # extraction refused/failed (e.g. fixed release)
        (1, ExecutionStatus.FAILED),
        (3, ExecutionStatus.FAILED),  # harness/IO failure in the worker
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
    assert result.target_id == "decompress"
    assert result.stdout == "out"
    assert result.stderr == "err"
    assert result.duration_seconds == 0.25
    assert result.timeout_seconds == 10.0


def test_verify_identity_accepts_matching_metadata_and_rejects_drift() -> None:
    target = _target()
    assert target.verify_identity(_identity_json(target)) == target.artifacts

    drifted = _identity_json(_target(decompress_version="4.2.0"))
    with pytest.raises(BackendError, match="identity changed"):
        target.verify_identity(drifted)

    with pytest.raises(BackendError, match="invalid identity metadata"):
        target.verify_identity(b"not json")


@pytest.mark.parametrize(
    "override",
    [
        {"image_id": "4.2.1"},  # not an immutable sha256 image id
        {"image_id": "sha256:" + "a" * 63},
        {"decompress_version": "latest"},  # not semver
        {"node_version": "v22"},  # not semver
        {"decompress_module": "Bad Name"},  # not an npm package name
        {"worker_sha256": "nothex"},
    ],
)
def test_construction_rejects_malformed_identity(override: dict[str, str]) -> None:
    fields = {
        "image_id": _IMAGE,
        "decompress_module": "decompress",
        "decompress_version": "4.2.1",
        "node_version": "22.23.4",
        "worker_sha256": _WORKER_SHA,
        **override,
    }
    with pytest.raises(ValueError):
        DecompressJsTarget(
            fields["image_id"],
            fields["decompress_module"],
            fields["decompress_version"],
            fields["node_version"],
            fields["worker_sha256"],
        )


def test_timeout_bounds_are_enforced() -> None:
    with pytest.raises(ValueError):
        _target(timeout_seconds=0)
    with pytest.raises(ValueError):
        _target(timeout_seconds=121)
