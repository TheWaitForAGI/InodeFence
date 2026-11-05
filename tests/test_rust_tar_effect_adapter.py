"""Portable tests for the Rust `tar` crate frame target (Tier-B, D039): the `frame` invocation,
shared version identity, status classification, and that the worker's frame format is the one the
existing oras-go frame pipeline and the sanctioned normalizer already consume. No container runs.
"""

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from inodefence.effect_pipeline_oras_go import _parse_frame
from inodefence.execution.base import BackendError, ContainerOutcome, ExecutionBackend
from inodefence.feedback.boundary_attempt_frame import FRAME_FORMAT, frame_boundary_attempt_keys
from inodefence.model import EffectFeedbackKeyKind, ExecutionStatus
from inodefence.model.isolation import ArtifactDigest
from inodefence.model.provenance import ExecutionSafety
from inodefence.targets.isolated import IsolatedTarget
from inodefence.targets.rust_tar import IDENTITY_KEYS, WORKER
from inodefence.targets.rust_tar_effect import RustTarFrameTarget

_IMAGE = "sha256:" + "a" * 64
_LOCK_SHA = "c" * 64
_WORKER_SHA = "b" * 64


def _target(tar_crate_version: str = "0.4.35") -> RustTarFrameTarget:
    return RustTarFrameTarget(_IMAGE, tar_crate_version, "1.99.1", _LOCK_SHA, _WORKER_SHA, 10.0)


def _identity_json(target: RustTarFrameTarget) -> bytes:
    return json.dumps({key: getattr(target, key) for key in IDENTITY_KEYS}).encode()


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
    # A distinct id so a frame run never reads as the `extract` adapter.
    assert provenance.target_id == "rust-tar-boundary-attempt-frame"
    assert provenance.target_version == "tar=0.4.35;rustc=1.99.1"
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
    assert target.artifacts == (
        ArtifactDigest("rust-tar-cargo-lock", _LOCK_SHA),
        ArtifactDigest("rust-tar-worker", _WORKER_SHA),
    )


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
    result = _target().classify(outcome, command)
    assert result.status == expected
    assert result.target_id == "rust-tar-boundary-attempt-frame"


def test_bind_observes_identity_and_returns_isolated_target() -> None:
    expected = _target()
    isolated = RustTarFrameTarget.bind(_IdentityBackend(_identity_json(expected)), _IMAGE)
    assert isinstance(isolated, IsolatedTarget)
    assert isolated.invocation == expected


def test_bind_rejects_incomplete_metadata() -> None:
    incomplete = json.loads(_identity_json(_target()))
    del incomplete["tar_crate_version"]
    with pytest.raises(BackendError, match="incomplete metadata"):
        RustTarFrameTarget.bind(_IdentityBackend(json.dumps(incomplete).encode()), _IMAGE)


def test_verify_identity_rejects_a_changed_crate_version() -> None:
    with pytest.raises(BackendError):
        _target().verify_identity(_identity_json(_target("0.4.36")))


def _worker_frame() -> str:
    """A frame in the exact key layout `tools/rust-tar/worker/src/main.rs` prints (run_frame)."""
    attempt = (
        '{"aliases_external_object":false,"created_path":"extract/up","created_region":'
        '"extraction","operation":"symlink","outcome":"created","target_raw":"..",'
        '"target_region":"harness","target_resolved_absolute":"."}'
    )
    return (
        '{"attempts":[' + attempt + '],"extraction_root_absolute":"/s/extract",'
        '"extractor":"tar@0.4.35","format":"' + FRAME_FORMAT + '","schema_version":1}\n'
    )


def test_worker_frame_layout_is_consumed_by_the_existing_frame_pipeline() -> None:
    frame, error = _parse_frame("unpack error on stderr goes elsewhere\n" + _worker_frame())
    assert error is None
    assert frame is not None and frame["extractor"] == "tar@0.4.35"
    kinds = {key.kind for key in frame_boundary_attempt_keys(frame)}
    # A `..` symlink resolving to the harness region is a lexical boundary-escape attempt.
    assert kinds == {EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT}
