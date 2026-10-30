"""Portable tests for the oras-go frame target (M4 self-discovery adapter): the `frame`
invocation, shared version identity and status classification. They do not run a container -- the
real extraction + frame emission lives in the native container closure.
"""

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from inodefence.execution.base import BackendError, ContainerOutcome, ExecutionBackend
from inodefence.model import ExecutionStatus
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import ExecutionSafety
from inodefence.targets.isolated import IsolatedTarget
from inodefence.targets.oras_go import WORKER
from inodefence.targets.oras_go_effect import OrasGoFrameTarget

_IMAGE = "sha256:" + "a" * 64
_WORKER_SHA = "b" * 64


def _target(
    image_id: str = _IMAGE,
    oras_go_version: str = "v2.6.1",
    go_version: str = "go1.25.14",
    worker_sha256: str = _WORKER_SHA,
    timeout_seconds: float = 10.0,
) -> OrasGoFrameTarget:
    return OrasGoFrameTarget(image_id, oras_go_version, go_version, worker_sha256, timeout_seconds)


def _identity_json(target: OrasGoFrameTarget) -> bytes:
    return json.dumps(
        {
            "oras_go_version": target.oras_go_version,
            "go_version": target.go_version,
            "worker_sha256": target.worker_sha256,
        }
    ).encode()


class _IdentityBackend(ExecutionBackend):
    """Minimal backend that answers only the identity probe (used by bind())."""

    def __init__(self, identity: bytes) -> None:
        self._identity = identity

    def validate_image(self, image_id: str) -> None:
        assert image_id == _IMAGE

    def policy(self, image_id):  # pragma: no cover - unused by bind
        raise AssertionError("not used")

    def capture_isolation(self, image_id):  # pragma: no cover - unused by bind
        raise AssertionError("not used")

    @contextmanager
    def prepare(self, request):
        backend = self

        class _Prepared:
            def execute(self) -> ContainerOutcome:
                return ContainerOutcome(0, backend._identity, b"", 0.0, False)

        yield _Prepared()


def test_provenance_uses_a_distinct_frame_target_id_and_exact_versions() -> None:
    provenance = _target().provenance
    # A distinct id so the frame run never reads as the generality `extract` differential.
    assert provenance.target_id == "oras-go-boundary-attempt-frame"
    assert provenance.target_version == "oras-go=v2.6.1;go=go1.25.14"
    assert provenance.execution_safety == ExecutionSafety.ISOLATION_REQUIRED


def test_command_runs_the_frame_subcommand() -> None:
    target = _target()
    assert target.command(Path("/s/archive/input.tar"), Path("/s/extract")) == (
        WORKER,
        "frame",
        "/s/archive/input.tar",
        "/s/extract",
    )
    assert target.identity_command == (WORKER, "identify")
    assert target.artifacts == (ArtifactDigest("oras-go-worker", _WORKER_SHA),)


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [
        (0, ExecutionStatus.SUCCESS),
        (2, ExecutionStatus.REJECTED),
        (1, ExecutionStatus.FAILED),
        (3, ExecutionStatus.FAILED),
        (None, ExecutionStatus.TIMED_OUT),
    ],
)
def test_classify_maps_exit_codes(exit_code: int | None, expected: ExecutionStatus) -> None:
    command = _target().command(Path("/s/archive/input.tar"), Path("/s/extract"))
    outcome = ContainerOutcome(exit_code, b"{}\n", b"", 0.1, False)
    assert _target().classify(outcome, command).status == expected


def test_bind_observes_identity_and_returns_isolated_target() -> None:
    expected = _target()
    isolated = OrasGoFrameTarget.bind(_IdentityBackend(_identity_json(expected)), _IMAGE)
    assert isinstance(isolated, IsolatedTarget)
    assert isolated.invocation == expected


def test_verify_identity_rejects_a_changed_worker_or_version() -> None:
    target = _target()
    drifted = json.dumps(
        {
            "oras_go_version": "v9.9.9",
            "go_version": "go1.25.14",
            "worker_sha256": _WORKER_SHA,
        }
    ).encode()
    with pytest.raises(BackendError):
        target.verify_identity(drifted)
