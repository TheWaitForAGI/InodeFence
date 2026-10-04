"""Verify originals, execute only fixed benign fixtures, preserve new evidence."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from inodefence.evaluation.failure import (
    FailureContext,
    FailurePhase,
    FailureRecord,
    failure_record,
    read_failure,
    write_failure,
)
from inodefence.evaluation.storage import read_record, write_record
from inodefence.evaluation.verify import (
    VerificationError,
    _digest,
    _read_file,
    verify_binding,
    verify_campaign,
    verify_run,
)
from inodefence.model import RunResult
from inodefence.model.provenance import ExecutionProvenance, ExecutionSafety
from inodefence.pipeline import run_case
from inodefence.provenance import freeze_provenance, sentinel_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.isolated import IsolatedTarget
from inodefence.targets.python_tarfile import PythonTarfileTarget

from .benign import benign_replay_cases


@dataclass(frozen=True, slots=True)
class ReplayHeader:
    profile: str
    original_manifest_sha256: str
    original_steps_sha256: str
    step_indices: tuple[int, ...]
    provenance: ExecutionProvenance

    def __post_init__(self) -> None:
        if self.profile != "benign-fixtures-v1" or not isinstance(
            self.provenance, ExecutionProvenance
        ):
            raise ValueError("unsupported replay profile/provenance")
        _digest(self.original_manifest_sha256)
        _digest(self.original_steps_sha256)
        if (
            not isinstance(self.step_indices, tuple)
            or not self.step_indices
            or not all(type(index) is int and index >= 0 for index in self.step_indices)
            or len(set(self.step_indices)) != len(self.step_indices)
        ):
            raise ValueError("replay requires explicit unique original step indices")


@dataclass(frozen=True, slots=True)
class ReplayStep:
    original_step_index: int
    original_case_id: str
    original_archive_sha256: str
    result: RunResult

    def __post_init__(self) -> None:
        if (
            type(self.original_step_index) is not int
            or self.original_step_index < 0
            or not isinstance(self.result, RunResult)
        ):
            raise ValueError("replay step requires original index and raw result")
        _digest(self.original_case_id)
        _digest(self.original_archive_sha256)
        verify_run(self.result)
        if (
            self.result.case.case_id != self.original_case_id
            or self.result.archive_sha256 != self.original_archive_sha256
        ):
            raise ValueError("replay logical case/TAR differs from original")
        if self.result.case not in benign_replay_cases():
            raise ValueError("case is outside the fixed benign replay profile")


@dataclass(frozen=True, slots=True)
class ReplayCompletion:
    artifacts: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class ReplayEvidence:
    header: ReplayHeader
    steps: tuple[ReplayStep, ...]
    complete: bool
    failure: FailureRecord | None


def _capture(target: PythonTarfileTarget | IsolatedTarget, sentinels: tuple[SentinelSpec, ...]):
    if type(target) is PythonTarfileTarget:
        isolation = None
    elif (
        type(target) is IsolatedTarget
        and target.provenance.execution_safety == ExecutionSafety.ISOLATION_REQUIRED
    ):
        isolation = target.capture_isolation()
    else:
        raise ValueError("benign replay requires exact reference or enforced IsolatedTarget")
    return freeze_provenance(target.provenance, sentinels, isolation=isolation)


def replay_benign(
    original_directory: Path,
    destination: Path,
    target: PythonTarfileTarget | IsolatedTarget,
    *,
    step_indices: tuple[int, ...] | None = None,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    expected_manifest_sha256: str | None = None,
) -> ReplayEvidence:
    """No arbitrary attack-case execution or search replay. Original files stay intact."""
    original = verify_campaign(
        original_directory, expected_manifest_sha256=expected_manifest_sha256
    )
    indices = tuple(range(len(original.result.steps))) if step_indices is None else step_indices
    # Validate the entire selection before target capture or any runtime creation.
    ReplayHeader(
        "benign-fixtures-v1",
        original.manifest_sha256,
        original.steps_sha256,
        indices,
        original.result.provenance,
    )
    if any(index >= len(original.result.steps) for index in indices):
        raise ValueError("original replay index exceeds the verified export")
    if any(
        original.result.steps[index].result.case not in benign_replay_cases() for index in indices
    ):
        raise ValueError("selection includes a case outside the fixed benign replay profile")
    if sentinel_provenance(sentinels) != original.result.provenance.sentinels:
        raise ValueError("supply sentinel bytes/modes matching the original configuration")
    source_path, output_path = original_directory.resolve(), destination.resolve()
    if output_path.is_relative_to(source_path) or source_path.is_relative_to(output_path):
        raise ValueError("replay destination must be independent of original evidence")
    frozen = _capture(target, sentinels)
    header = ReplayHeader(
        "benign-fixtures-v1", original.manifest_sha256, original.steps_sha256, indices, frozen
    )
    destination.mkdir(parents=True, exist_ok=False)
    artifacts = [("header.json", write_record(destination / "header.json", header))]
    roots = {step.result.before.sandbox_root for step in original.result.steps}
    completed, available = [], None
    phase = FailurePhase.UNKNOWN
    try:
        for ordinal, index in enumerate(indices):
            available = None
            phase = FailurePhase.UNKNOWN
            current = _capture(target, sentinels)
            if current.target != frozen.target or current.isolation != frozen.isolation:
                raise ValueError("replay target/isolation configuration changed")
            old = original.result.steps[index].result
            available = run_case(old.case, target, sentinels=sentinels)
            phase = FailurePhase.DERIVATION
            verify_binding(available, frozen)
            if available.before.sandbox_root in roots:
                raise ValueError("replay did not use a fresh runtime")
            roots.add(available.before.sandbox_root)
            record = ReplayStep(index, old.case.case_id, old.archive_sha256, available)
            phase = FailurePhase.PUBLICATION
            name = f"step-{ordinal:08d}.json"
            artifacts.append((name, write_record(destination / name, record)))
            completed.append(record)
        write_record(destination / "completion.json", ReplayCompletion(tuple(artifacts)))
    except Exception as error:
        context = FailureContext(
            destination.name,
            original.manifest_sha256,
            frozen.source,
            frozen.target,
            len(completed),
            phase,
            last_fully_completed_step=len(completed) - 1 if completed else None,
            stdout=available.execution.stdout if available else None,
            stderr=available.execution.stderr if available else None,
            before=available.before if available else None,
            after=available.after if available else None,
        )
        write_failure(destination / "failure.json", failure_record(error, context))
        raise
    return verify_replay(original_directory, destination)


def verify_replay(original_directory: Path, directory: Path) -> ReplayEvidence:
    """Reverify original and every replay record; a prefix is explicitly incomplete."""
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("expected replay evidence directory")
        header = read_record(directory / "header.json", ReplayHeader)
        original = verify_campaign(
            original_directory, expected_manifest_sha256=header.original_manifest_sha256
        )
        if original.steps_sha256 != header.original_steps_sha256 or any(
            index >= len(original.result.steps) for index in header.step_indices
        ):
            raise ValueError("original replay binding mismatch")
        if header.provenance.sentinels != original.result.provenance.sentinels or any(
            original.result.steps[index].result.case not in benign_replay_cases()
            for index in header.step_indices
        ):
            raise ValueError("replay selection/sentinel profile differs from original")
        names = {path.name for path in directory.iterdir()}
        records = sorted(name for name in names if name.startswith("step-"))
        if records != [f"step-{index:08d}.json" for index in range(len(records))] or len(
            records
        ) > len(header.step_indices):
            raise ValueError("replay record gap/count mismatch")
        if any(
            name not in {"header.json", "completion.json", "failure.json", *records}
            and not name.startswith(".record-")
            for name in names
        ):
            raise ValueError("unexpected replay artifact")
        roots = {step.result.before.sandbox_root for step in original.result.steps}
        artifacts = [("header.json", sha256(_read_file(directory / "header.json")).hexdigest())]
        steps = []
        for ordinal, name in enumerate(records):
            step = read_record(directory / name, ReplayStep)
            old = original.result.steps[header.step_indices[ordinal]].result
            if (
                step.original_step_index != header.step_indices[ordinal]
                or step.result.case != old.case
                or step.original_archive_sha256 != old.archive_sha256
            ):
                raise ValueError("replayed case/TAR differs from original record")
            verify_binding(step.result, header.provenance)
            if step.result.before.sandbox_root in roots:
                raise ValueError("replay runtime was reused")
            roots.add(step.result.before.sandbox_root)
            artifacts.append((name, sha256(_read_file(directory / name)).hexdigest()))
            steps.append(step)
        failure = read_failure(directory / "failure.json") if "failure.json" in names else None
        if failure is not None and (
            failure.context.experiment_id != header.original_manifest_sha256
            or failure.context.source != header.provenance.source
            or failure.context.target != header.provenance.target
            or failure.context.step_index != len(steps)
            or failure.context.last_fully_completed_step != (len(steps) - 1 if steps else None)
        ):
            raise ValueError("failure ledger differs from replay attempt/prefix")
        complete = "completion.json" in names
        if complete:
            marker = read_record(directory / "completion.json", ReplayCompletion)
            if (
                marker.artifacts != tuple(artifacts)
                or len(steps) != len(header.step_indices)
                or failure is not None
            ):
                raise ValueError("replay completion differs from full evidence")
        return ReplayEvidence(header, tuple(steps), complete, failure)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid replay evidence: {error}") from error
