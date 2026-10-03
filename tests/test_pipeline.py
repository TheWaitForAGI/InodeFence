import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.generate_tar_fixtures import CASE_NAMES, CONTENT, baseline_case

from inodefence import pipeline as pipeline_module
from inodefence.feedback import state_signature
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    ObjectType,
    SnapshotPhase,
    StateSnapshot,
    canonical_json,
)
from inodefence.observer import ObservationError, capture_state
from inodefence.pipeline import run_case
from inodefence.runtime import RuntimeSandbox, SentinelSpec, disposable_sandbox, runtime_root
from inodefence.targets import PythonTarfileTarget
from inodefence.targets.python_tarfile import _text


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_real_reference_pipeline_baselines_and_self_contained_evidence(case_name: str) -> None:
    case = baseline_case(case_name)
    result = run_case(case, PythonTarfileTarget())
    assert result.execution.succeeded and result.execution.exit_code == 0
    assert result.execution.target_id == "python-tarfile-data"
    assert result.execution.target_version.startswith("3.12.")
    assert not any(contract.violated for contract in result.violations)
    assert result.case == case
    assert result.before.get("extract/a.txt") is None
    path = "extract/dir/a.txt" if case_name == "directory" else "extract/a.txt"
    first = result.after.get(path)
    assert first is not None and first.content_digest == hashlib.sha256(CONTENT).hexdigest()
    assert first.size == 16
    if case_name == "hardlink":
        second = result.after.get("extract/b.txt")
        assert second is not None and second.identity == first.identity
        assert ("extract/a.txt", "extract/b.txt") in result.signature.identity_groups
    if case_name == "symlink":
        second = result.after.get("extract/b.txt")
        assert second is not None and second.object_type == ObjectType.SYMLINK
        assert second.identity != first.identity and second.symlink_target == "a.txt"
    assert not Path(result.after.sandbox_root).exists()
    encoded = json.loads(canonical_json(result))
    assert encoded["schema_version"] == 1
    assert encoded["value"]["execution"]["status"] == "success"
    assert encoded["value"]["violations"][0]["contract_id"] == "C0"
    assert len(result.archive_sha256) == 64


def test_pipeline_signature_equal_across_real_runs_with_different_inodes() -> None:
    # Keep both allocations alive so inode reuse cannot make this a vacuous test.
    case = baseline_case("hardlink")
    with disposable_sandbox() as first, disposable_sandbox() as second:
        from inodefence.builder import build_tar

        signatures = []
        identities = []
        for sandbox in (first, second):
            sandbox.archive_path.write_bytes(build_tar(case))
            before = capture_state(sandbox.root, SnapshotPhase.BEFORE, sandbox.protected_paths)
            assert (
                PythonTarfileTarget().run(sandbox.archive_path, sandbox.extraction_root).succeeded
            )
            after = capture_state(sandbox.root, SnapshotPhase.AFTER, sandbox.protected_paths)
            obj = after.get("extract/a.txt")
            assert obj is not None
            identities.append(obj.identity)
            signatures.append(state_signature(before, after))
        assert identities[0] != identities[1]
        assert signatures[0] == signatures[1]
        assert canonical_json(signatures[0]) == canonical_json(signatures[1])


def test_reference_rejection_is_not_a_violation_and_partial_extraction_is_observed() -> None:
    case = ArchiveCase(
        (
            ArchiveEntry("first.txt", EntryType.REGULAR, content=b"before rejection"),
            ArchiveEntry("../outside/rejected.txt", EntryType.REGULAR, content=b"must be rejected"),
        )
    )
    result = run_case(case, PythonTarfileTarget())
    assert result.execution.status == ExecutionStatus.REJECTED
    assert result.execution.exit_code == 2 and "OutsideDestinationError" in result.execution.stderr
    assert result.after.get("extract/first.txt") is not None
    assert result.after.get("outside/rejected.txt") is None
    assert not any(contract.violated for contract in result.violations)
    assert not Path(result.after.sandbox_root).exists()


def test_reference_parser_failure_has_execution_evidence(sandbox: RuntimeSandbox) -> None:
    sandbox.archive_path.write_bytes(b"not a tar archive")
    result = PythonTarfileTarget().run(sandbox.archive_path, sandbox.extraction_root)
    assert result.status == ExecutionStatus.FAILED and result.exit_code == 3
    assert "ReadError" in result.stderr
    assert list(sandbox.extraction_root.iterdir()) == []


def test_real_worker_timeout_stops_worker_and_still_observes_after_state() -> None:
    result = run_case(baseline_case("regular-file"), PythonTarfileTarget(timeout_seconds=1e-9))
    assert result.execution.status == ExecutionStatus.TIMED_OUT
    assert result.execution.exit_code is None
    assert not any(contract.violated for contract in result.violations)
    assert result.after.get("outside/sentinel.txt") is not None
    assert not Path(result.after.sandbox_root).exists()


def test_multiple_sentinels_and_empty_case() -> None:
    result = run_case(
        ArchiveCase(()),
        PythonTarfileTarget(),
        sentinels=(
            SentinelSpec("second", b"two"),
            SentinelSpec("nested/first", b"one", 0o640),
        ),
    )
    assert result.execution.succeeded
    assert result.before.protected_paths == ("outside/nested/first", "outside/second")
    assert not any(contract.violated for contract in result.violations)


def test_unexpected_adapter_failure_cleans_up() -> None:
    paths: list[Path] = []

    class RaisingAdapter:
        def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
            paths.append(extraction_root.parent)
            assert archive_path.is_file()
            raise RuntimeError("controlled harness failure")

    with pytest.raises(RuntimeError, match="controlled harness failure"):
        run_case(baseline_case("regular-file"), RaisingAdapter())
    assert len(paths) == 1 and not paths[0].exists()


def test_builder_failure_has_no_runtime_side_effect() -> None:
    original = set(runtime_root().iterdir())
    with pytest.raises(ValueError, match="USTAR"):
        run_case(
            ArchiveCase((ArchiveEntry("a" * 101, EntryType.REGULAR, content=b""),)),
            PythonTarfileTarget(),
        )
    assert set(runtime_root().iterdir()) == original


def test_observer_failure_after_real_execution_cleans_up_without_a_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots: list[Path] = []
    phases: list[SnapshotPhase] = []

    def capture_or_raise(
        root: Path, phase: SnapshotPhase, protected: tuple[str, ...]
    ) -> StateSnapshot:
        roots.append(root)
        phases.append(phase)
        if phase == SnapshotPhase.AFTER:
            raise ObservationError("controlled post-state failure")
        return capture_state(root, phase, protected)

    monkeypatch.setattr(pipeline_module, "capture_state", capture_or_raise)
    with pytest.raises(ObservationError, match="controlled post-state failure"):
        run_case(baseline_case("regular-file"), PythonTarfileTarget())
    assert phases == [SnapshotPhase.BEFORE, SnapshotPhase.AFTER]
    assert all(not root.exists() for root in roots)


def test_canonical_case_and_signature_stable_across_interpreter_hash_seeds() -> None:
    code = """
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, canonical_json
from inodefence.pipeline import run_case
from inodefence.targets import PythonTarfileTarget
case = ArchiveCase((ArchiveEntry('a', EntryType.REGULAR, content=b'content'),
                    ArchiveEntry('b', EntryType.HARDLINK, link_target='a')))
result = run_case(case, PythonTarfileTarget())
assert result.execution.succeeded
print(case.case_id)
print(canonical_json(case))
print(canonical_json(result.signature))
"""
    outputs = []
    for seed in ("1", "9876"):
        completed = subprocess.run(
            [sys.executable, "-c", code],
            env=os.environ | {"PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(completed.stdout)
    assert outputs[0] == outputs[1]


def test_execution_output_preserves_undecodable_bytes_in_json_evidence() -> None:
    output = b"diagnostic\xff\0\n"
    result = ExecutionResult(
        "target", "version", (), ExecutionStatus.FAILED, 1, _text(output), _text(output)
    )
    value = json.loads(canonical_json(result))["value"]
    assert value["stdout"].encode("utf-8", "surrogateescape") == output
    assert value["stderr"].encode("utf-8", "surrogateescape") == output
