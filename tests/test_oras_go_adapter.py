"""Portable tests for the oras-go target descriptor (M4.1): invocation, version identity and
status classification. They do not run a container and do not claim real containment -- the
real extraction lives in the capability probe and the controller-run container closure.
"""

import json
from pathlib import Path

import pytest

from inodefence.execution.base import BackendError, ContainerOutcome
from inodefence.model import ExecutionStatus
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import ExecutionSafety
from inodefence.targets.oras_go import WORKER, OrasGoTarget

_IMAGE = "sha256:" + "a" * 64
_WORKER_SHA = "b" * 64


def _target(
    image_id: str = _IMAGE,
    oras_go_version: str = "v2.6.1",
    go_version: str = "go1.25.14",
    worker_sha256: str = _WORKER_SHA,
    timeout_seconds: float = 10.0,
) -> OrasGoTarget:
    return OrasGoTarget(image_id, oras_go_version, go_version, worker_sha256, timeout_seconds)


def _identity_json(target: OrasGoTarget) -> bytes:
    return json.dumps(
        {
            "oras_go_version": target.oras_go_version,
            "go_version": target.go_version,
            "worker_sha256": target.worker_sha256,
        }
    ).encode()


def test_provenance_declares_isolation_required_and_exact_versions() -> None:
    provenance = _target().provenance
    assert provenance.target_id == "oras-go"
    assert provenance.target_version == "oras-go=v2.6.1;go=go1.25.14"
    assert provenance.timeout_seconds == 10.0
    # Third-party target: the descriptor must require OS containment, never TRUSTED_REFERENCE.
    assert provenance.execution_safety == ExecutionSafety.ISOLATION_REQUIRED


def test_command_and_identity_command_shape() -> None:
    target = _target()
    assert target.command(Path("/s/archive/input.tar"), Path("/s/extract")) == (
        WORKER,
        "extract",
        "/s/archive/input.tar",
        "/s/extract",
    )
    assert target.identity_command == (WORKER, "identify")
    assert target.artifacts == (ArtifactDigest("oras-go-worker", _WORKER_SHA),)


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
    assert result.target_id == "oras-go"
    assert result.stdout == "out"
    assert result.stderr == "err"
    assert result.duration_seconds == 0.25
    assert result.timeout_seconds == 10.0


def test_verify_identity_accepts_matching_metadata_and_rejects_drift() -> None:
    target = _target()
    assert target.verify_identity(_identity_json(target)) == target.artifacts

    drifted = _identity_json(_target(oras_go_version="v2.6.2"))
    with pytest.raises(BackendError, match="identity changed"):
        target.verify_identity(drifted)

    with pytest.raises(BackendError, match="invalid identity metadata"):
        target.verify_identity(b"not json")


@pytest.mark.parametrize(
    "override",
    [
        {"image_id": "2.6.1"},  # not an immutable sha256 image id
        {"image_id": "sha256:" + "a" * 63},
        {"oras_go_version": "2.6.1"},  # missing leading v
        {"oras_go_version": "latest"},
        {"go_version": "1.25.14"},  # missing go prefix
        {"worker_sha256": "nothex"},
    ],
)
def test_construction_rejects_malformed_identity(override: dict[str, str]) -> None:
    fields = {
        "image_id": _IMAGE,
        "oras_go_version": "v2.6.1",
        "go_version": "go1.25.14",
        "worker_sha256": _WORKER_SHA,
        **override,
    }
    with pytest.raises(ValueError):
        OrasGoTarget(
            fields["image_id"],
            fields["oras_go_version"],
            fields["go_version"],
            fields["worker_sha256"],
        )


def test_timeout_bounds_are_enforced() -> None:
    with pytest.raises(ValueError):
        _target(timeout_seconds=0)
    with pytest.raises(ValueError):
        _target(timeout_seconds=121)
