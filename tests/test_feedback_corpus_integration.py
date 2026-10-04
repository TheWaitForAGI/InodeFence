"""Caller-level composition using real run_case observation in disposable runtime."""

import random
import stat
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from inodefence.feedback import (
    ChangeFingerprint,
    Corpus,
    CorpusStats,
    ViolationFingerprint,
    state_signature,
)
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ChangeField,
    ContractId,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    RunResult,
    StateSnapshot,
)
from inodefence.mutator import mutate
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.pipeline import run_case
from inodefence.targets import PythonTarfileTarget


@dataclass(frozen=True, slots=True)
class ControlledTarget:
    """Simulate target effects only inside run(), never during harness setup."""

    harness_effect: bool = False
    harness_metadata_effect: bool = False
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    duration_seconds: float = 0.0

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        if self.harness_effect:
            (archive_path.parent / "escaped.txt").write_bytes(b"controlled target effect")
        if self.harness_metadata_effect:
            # Toggle a group bit so the caller's initial umask cannot make this a no-op.
            for path in (archive_path, archive_path.parent, extraction_root.parent):
                path.chmod(stat.S_IMODE(path.lstat().st_mode) ^ 0o040)
        exit_code = {
            ExecutionStatus.SUCCESS: 0,
            ExecutionStatus.FAILED: 1,
            ExecutionStatus.REJECTED: 2,
            ExecutionStatus.TIMED_OUT: None,
        }[self.status]
        return ExecutionResult(
            "controlled",
            "test",
            (),
            self.status,
            exit_code,
            "",
            "",
            self.duration_seconds,
        )


def _case(name: str) -> ArchiveCase:
    return ArchiveCase((ArchiveEntry(name, EntryType.REGULAR, content=name.encode()),))


def test_same_signature_new_c0_harness_violation_remains_interesting() -> None:
    first = run_case(_case("a"), ControlledTarget())
    equivalent = run_case(_case("b"), ControlledTarget())
    escaped = run_case(_case("c"), ControlledTarget(harness_effect=True))
    results = (first, equivalent, escaped)
    assert len({result.case.case_id for result in results}) == 3
    assert len({result.archive_sha256 for result in results}) == 3
    assert first.signature == equivalent.signature == escaped.signature
    assert first.signature.schema_version == 3
    for result in results:
        for snapshot in (result.before, result.after):
            artifact = snapshot.get("archive/input.tar")
            assert artifact is not None and artifact.content_digest == result.archive_sha256
        assert not Path(result.after.sandbox_root).exists()
    assert all(
        not verdict.violated for result in (first, equivalent) for verdict in result.violations
    )
    c0, c1, c2 = escaped.violations
    assert c0.violated and not c1.violated and not c2.violated
    assert escaped.before.get("archive/escaped.txt") is None
    assert escaped.after.get("archive/escaped.txt") is not None
    expected = ViolationFingerprint(
        ContractId.C0,
        (ChangeFingerprint("archive/escaped.txt", (ChangeField.EXISTENCE,)),),
    )

    corpus = Corpus()
    admitted = corpus.consider(first)
    assert admitted.state_novel and admitted.retained and not admitted.new_violation_fingerprints
    discarded = corpus.consider(equivalent)
    assert not discarded.state_novel and discarded.new_violation_fingerprints == ()
    assert not discarded.interesting and not discarded.retained and not discarded.already_retained
    decision = corpus.consider(escaped)
    assert not decision.state_novel and decision.new_violation_fingerprints == (expected,)
    assert decision.interesting and decision.retained and not decision.already_retained
    assert tuple(entry.case for entry in corpus.entries) == (first.case, escaped.case)
    assert corpus.entries[1].admission_signature == first.signature
    assert corpus.entries[1].admission_violation_fingerprints == (expected,)
    assert corpus.stats == CorpusStats(3, 2, 2, 1, 1)


@pytest.mark.parametrize("status", tuple(ExecutionStatus))
@pytest.mark.parametrize("duration", (0.0, 123.5))
def test_input_harness_metadata_and_process_evidence_do_not_create_novelty(
    status: ExecutionStatus,
    duration: float,
) -> None:
    first = run_case(_case("a"), ControlledTarget())
    second = run_case(
        _case("b"),
        ControlledTarget(
            harness_metadata_effect=True,
            status=status,
            duration_seconds=duration,
        ),
    )
    assert first.case.case_id != second.case.case_id
    assert first.archive_sha256 != second.archive_sha256
    first_artifact, second_artifact = (
        first.after.get("archive/input.tar"),
        second.after.get("archive/input.tar"),
    )
    assert first_artifact is not None and second_artifact is not None
    assert first_artifact.content_digest != second_artifact.content_digest
    assert first_artifact.mode != second_artifact.mode
    for path in (".", "archive"):
        original, modified = first.after.get(path), second.after.get(path)
        assert original is not None and modified is not None and original.mode != modified.mode
    assert second.execution.status == status and second.execution.duration_seconds == duration
    assert first.signature == second.signature
    assert all(not verdict.violated for verdict in second.violations)
    corpus = Corpus()
    assert corpus.consider(first).retained
    decision = corpus.consider(second)
    assert not decision.state_novel and not decision.new_violation_fingerprints
    assert not decision.interesting and not decision.retained and not decision.already_retained
    assert corpus.stats == CorpusStats(2, 1, 1, 1, 0)


def test_corpus_does_not_use_raw_inode_device_or_timestamp_allocation() -> None:
    first = run_case(_case("a"), PythonTarfileTarget())

    def relabel(snapshot: StateSnapshot) -> StateSnapshot:
        return replace(
            snapshot,
            objects=tuple(
                replace(
                    obj,
                    st_dev=obj.st_dev + 91,
                    st_ino=obj.st_ino + 9000,
                    mtime_ns=obj.mtime_ns + 1234,
                    ctime_ns=obj.ctime_ns + 5678,
                )
                for obj in snapshot.objects
            ),
        )

    # Relabel actual raw evidence on both sides, preserving all relations and change labels.
    before, after = relabel(first.before), relabel(first.after)
    second = replace(
        first,
        case=_case("b"),
        before=before,
        after=after,
        changes=compare_states(before, after),
        signature=state_signature(before, after),
        violations=evaluate_contracts(before, after),
    )
    assert first.before != second.before and first.after != second.after
    assert first.signature == second.signature
    assert all(not verdict.violated for verdict in second.violations)
    corpus = Corpus()
    corpus.consider(first)
    assert not corpus.consider(second).interesting
    assert corpus.stats == CorpusStats(2, 1, 1, 1, 0)


def test_caller_can_select_mutate_and_execute_one_child_without_coupling() -> None:
    case = _case("a")
    corpus = Corpus()
    assert corpus.consider(run_case(case, PythonTarfileTarget())).retained
    rng, reference = random.Random(19), random.Random(19)
    parent = corpus.select_case(rng)
    assert parent == corpus.select_case(reference) == case
    child = mutate(parent, rng)
    assert child == mutate(parent, reference)
    assert child != parent and parent == case
    result: RunResult = run_case(child, PythonTarfileTarget())
    decision = corpus.consider(result)
    assert result.case == child and decision.case_id == child.case_id
    assert rng.getstate() == reference.getstate()
    assert corpus.stats.observations == 2
