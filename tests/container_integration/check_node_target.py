"""Mandatory actual contained Node fixtures; no generated-input campaign."""

import json
from pathlib import Path

import pytest

from inodefence.generator import minimal_seed_corpus
from inodefence.model import ExecutionStatus
from inodefence.pipeline import run_case
from inodefence.runtime import RuntimeSandbox
from inodefence.targets.node_tar import NodeTarTarget


@pytest.mark.parametrize("index", range(4))
def test_benign_baseline_extraction_has_no_harness_bookkeeping(
    index: int, container_backend, container_image
) -> None:
    target = NodeTarTarget.bind(container_backend, container_image)
    result = run_case(minimal_seed_corpus()[index], target)
    assert result.execution.status == ExecutionStatus.SUCCESS
    assert result.execution.target_version == target.provenance.target_version
    assert result.execution.timeout_seconds == target.provenance.timeout_seconds
    assert result.execution.duration_seconds >= 0
    assert result.execution.stdout == result.execution.stderr == ""
    assert not any(verdict.violated for verdict in result.violations)
    assert all(change.path.startswith("extract") for change in result.changes)
    if index == 2:
        first, second = result.after.get("extract/a.txt"), result.after.get("extract/b.txt")
        assert first is not None and second is not None
        assert first.identity == second.identity
    if index == 3:
        link = result.after.get("extract/b.txt")
        assert link is not None and link.symlink_target == "a.txt"
    assert not Path(result.after.sandbox_root).exists()


def test_nonarchive_input_returns_error_diagnostics(
    sandbox: RuntimeSandbox, container_backend, container_image
) -> None:
    sandbox.archive_path.write_bytes(b"ordinary invalid format")
    result = NodeTarTarget.bind(container_backend, container_image).run(
        sandbox.archive_path, sandbox.extraction_root
    )
    assert result.status == ExecutionStatus.REJECTED
    diagnostic = json.loads(result.stderr)
    assert diagnostic["code"] == "TAR_BAD_ARCHIVE"
    assert result.stdout == ""


def test_real_timeout_of_ordinary_fixture_preserves_after_state_and_cleanup(
    container_backend, container_image
):
    result = run_case(
        minimal_seed_corpus()[0],
        NodeTarTarget.bind(container_backend, container_image, timeout_seconds=1e-9),
    )
    assert result.execution.status == ExecutionStatus.TIMED_OUT
    assert result.execution.duration_seconds > 0
    assert not Path(result.after.sandbox_root).exists()


def test_worker_identity_guard_precedes_extraction(sandbox, container_backend, container_image):
    from dataclasses import replace

    from inodefence.targets.isolated import IsolatedTarget

    bound = NodeTarTarget.bind(container_backend, container_image)
    assert isinstance(bound.invocation, NodeTarTarget)
    target = IsolatedTarget(replace(bound.invocation, node_version="99.0.0"), container_backend)
    with pytest.raises(RuntimeError, match="identity changed"):
        target.run(sandbox.archive_path, sandbox.extraction_root)
    assert tuple(sandbox.extraction_root.iterdir()) == ()


def test_after_observation_failure_removes_real_container_and_runtime(
    container_backend, container_image, monkeypatch
):
    from contextlib import contextmanager

    from inodefence.model import SnapshotPhase
    from inodefence.observer import ObservationError, capture_state

    target = NodeTarTarget.bind(container_backend, container_image)
    identities = []
    original_prepare = type(container_backend).prepare

    @contextmanager
    def tracked_prepare(backend, request):
        with original_prepare(backend, request) as prepared:
            identities.append(prepared.identity)
            yield prepared

    monkeypatch.setattr(type(container_backend), "prepare", tracked_prepare)
    roots = []

    def capture(root, phase, protected):
        roots.append(root)
        if phase == SnapshotPhase.AFTER:
            raise ObservationError("controlled AFTER failure")
        return capture_state(root, phase, protected)

    monkeypatch.setattr("inodefence.pipeline.capture_state", capture)
    with pytest.raises(ObservationError, match="AFTER failure"):
        run_case(minimal_seed_corpus()[0], target)
    assert len(roots) == 2 and all(not root.exists() for root in roots)
    assert len(identities) == 1
    assert container_backend.client.run(("container", "inspect", identities[0]), 10).returncode != 0
