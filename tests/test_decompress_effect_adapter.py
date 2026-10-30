"""Portable tests for the decompress frame target (M4 self-discovery adapter): the `frame`
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
from inodefence.targets.decompress_effect import NODE, WORKER, DecompressFrameTarget
from inodefence.targets.isolated import IsolatedTarget

_IMAGE = "sha256:" + "a" * 64
_WORKER_SHA = "b" * 64


def _target(
    image_id: str = _IMAGE,
    decompress_module: str = "decompress",
    decompress_version: str = "4.2.1",
    node_version: str = "22.23.4",
    worker_sha256: str = _WORKER_SHA,
    timeout_seconds: float = 10.0,
) -> DecompressFrameTarget:
    return DecompressFrameTarget(
        image_id,
        decompress_module,
        decompress_version,
        node_version,
        worker_sha256,
        timeout_seconds,
    )


def _identity_json(target: DecompressFrameTarget) -> bytes:
    return json.dumps(
        {
            "decompress_module": target.decompress_module,
            "decompress_version": target.decompress_version,
            "node_version": target.node_version,
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
    assert provenance.target_id == "decompress-boundary-attempt-frame"
    assert provenance.target_version == "decompress=decompress@4.2.1;node=22.23.4"
    assert provenance.execution_safety == ExecutionSafety.ISOLATION_REQUIRED


def test_command_runs_the_frame_subcommand() -> None:
    target = _target()
    assert target.command(Path("/s/archive/input.tar"), Path("/s/extract")) == (
        NODE,
        WORKER,
        "frame",
        "/s/archive/input.tar",
        "/s/extract",
    )
    assert target.identity_command == (NODE, WORKER, "identify")
    assert target.artifacts == (ArtifactDigest("decompress-worker", _WORKER_SHA),)


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
    isolated = DecompressFrameTarget.bind(_IdentityBackend(_identity_json(expected)), _IMAGE)
    assert isinstance(isolated, IsolatedTarget)
    assert isolated.invocation == expected


def test_verify_identity_rejects_a_changed_worker_or_version() -> None:
    target = _target()
    drifted = json.dumps(
        {
            "decompress_module": "decompress",
            "decompress_version": "9.9.9",
            "node_version": "22.23.4",
            "worker_sha256": _WORKER_SHA,
        }
    ).encode()
    with pytest.raises(BackendError):
        target.verify_identity(drifted)
