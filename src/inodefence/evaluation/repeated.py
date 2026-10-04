"""Independent-run scheduling metadata; no automatic execution or search resume."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from inodefence.campaign import CampaignConfig
from inodefence.experiment_config import ExperimentConfig
from inodefence.model.provenance import ExecutionProvenance
from inodefence.provenance import sentinel_provenance

from .failure import ArtifactReference, FailureRecord, _text, read_failure, write_failure
from .storage import read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file, verify_campaign


def _timestamp(value: str) -> None:
    if datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError("record timestamp requires timezone")


class RunState(StrEnum):
    PENDING = "pending"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class RepetitionPlan:
    experiment_config_json: str
    seeds: tuple[int, ...]
    provenance: ExecutionProvenance

    def __post_init__(self) -> None:
        config = ExperimentConfig.from_json(self.experiment_config_json)
        if config.to_json() != self.experiment_config_json:
            raise ValueError("canonical explicit experiment config required")
        if (
            not isinstance(self.seeds, tuple)
            or not self.seeds
            or not all(type(seed) is int and seed >= 0 for seed in self.seeds)
            or len(set(self.seeds)) != len(self.seeds)
            or config.campaign.random_seed != self.seeds[0]
        ):
            raise ValueError("unique seeds required; first seed must match base config")
        if not isinstance(self.provenance, ExecutionProvenance) or (
            config.target != self.provenance.target
            or sentinel_provenance(config.sentinels) != self.provenance.sentinels
            or config.isolation
            != (self.provenance.isolation.policy if self.provenance.isolation else None)
        ):
            raise ValueError("plan config/provenance mismatch")

    def config_for(self, index: int) -> ExperimentConfig:
        if type(index) is not int or not 0 <= index < len(self.seeds):
            raise ValueError("run index outside explicit plan")
        base = ExperimentConfig.from_json(self.experiment_config_json)
        return replace(
            base, campaign=CampaignConfig(self.seeds[index], base.campaign.execution_budget)
        )


@dataclass(frozen=True, slots=True)
class RunClaim:
    run_index: int
    config_id: str
    plan_sha256: str
    attempt_id: str
    recorded_at: str

    def __post_init__(self) -> None:
        if type(self.run_index) is not int or self.run_index < 0:
            raise ValueError("nonnegative run index required")
        _digest(self.config_id)
        _digest(self.plan_sha256)
        _text(self.attempt_id)
        _timestamp(self.recorded_at)


@dataclass(frozen=True, slots=True)
class RunTerminal:
    state: RunState
    claim_sha256: str
    artifact: ArtifactReference
    recorded_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.state, RunState) or self.state not in {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.INVALID,
        }:
            raise ValueError("terminal state must be completed/failed/invalid")
        _digest(self.claim_sha256)
        if not isinstance(self.artifact, ArtifactReference) or self.artifact.name != (
            "evidence/manifest.json" if self.state == RunState.COMPLETED else "failure.json"
        ):
            raise ValueError("terminal requires appropriate bound artifact")
        _timestamp(self.recorded_at)


@dataclass(frozen=True, slots=True)
class RunSlot:
    run_index: int
    random_seed: int
    config_id: str
    result_directory: str
    state: RunState
    claim: RunClaim | None
    terminal: RunTerminal | None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RepetitionSnapshot:
    plan: RepetitionPlan
    plan_sha256: str
    slots: tuple[RunSlot, ...]


def _completed(plan: RepetitionPlan, index: int, directory: Path, digest: str | None):
    if (directory / "failure.json").exists() or (directory / "failure.json").is_symlink():
        raise ValueError("infrastructure failure artifact cannot be acknowledged as completed")
    verified = verify_campaign(directory / "evidence", expected_manifest_sha256=digest)
    config = plan.config_for(index)
    result = verified.result
    if (
        verified.experiment_config_bytes != config.to_json().encode("ascii") + b"\n"
        or result.experiment_config_id != config.config_id
        or result.config != config.campaign
        or result.initial_case_ids != config.initial_case_ids
        or result.provenance != plan.provenance
    ):
        raise ValueError("completed campaign differs from explicit repetition plan")
    return verified


def _failure(plan: RepetitionPlan, plan_sha: str, claim: RunClaim, failure: FailureRecord):
    if not isinstance(failure, FailureRecord):
        raise ValueError("infrastructure FailureRecord required")
    context, config = failure.context, plan.config_for(claim.run_index)
    if (
        context.attempt_id != claim.attempt_id
        or context.experiment_id != plan_sha
        or context.config_id != config.config_id
        or context.source != plan.provenance.source
        or context.target != plan.provenance.target
        or (
            context.step_index is not None and context.step_index > config.campaign.execution_budget
        )
        or (
            context.last_fully_completed_step is not None
            and context.last_fully_completed_step >= config.campaign.execution_budget
        )
    ):
        raise ValueError("failure ledger differs from explicit run claim/plan")


def read_repetitions(root: Path, *, expected_plan_sha256: str | None = None) -> RepetitionSnapshot:
    """Read scheduling facts; never retry claimed runs or silently exclude corruption."""
    try:
        if root.is_symlink() or not root.is_dir():
            raise ValueError("expected repetition directory")
        plan = read_record(root / "plan.json", RepetitionPlan, expected_sha256=expected_plan_sha256)
        plan_sha = sha256(_read_file(root / "plan.json")).hexdigest()
        permitted = {"plan.json", *(f"run-{index:08d}" for index in range(len(plan.seeds)))}
        if any(
            path.name not in permitted and not path.name.startswith(".record-")
            for path in root.iterdir()
        ):
            raise ValueError("unexpected repetition artifact")
        slots, attempts = [], set()
        for index, seed in enumerate(plan.seeds):
            config = plan.config_for(index)
            directory = root / f"run-{index:08d}"
            state, claim, terminal, diagnostics = RunState.PENDING, None, None, ()
            if directory.is_symlink():
                raise ValueError("run directory cannot be symlink")
            if directory.exists():
                if not directory.is_dir():
                    raise ValueError("run slot must be directory")
                if any((directory / name).is_symlink() for name in ("claim.json", "terminal.json")):
                    raise ValueError("run markers cannot be symlinks")
                if not (directory / "claim.json").exists():
                    state, diagnostics = (
                        RunState.INVALID,
                        ("reserved without durable claim; no automatic retry",),
                    )
                else:
                    claim = read_record(directory / "claim.json", RunClaim)
                    if (
                        claim.run_index != index
                        or claim.config_id != config.config_id
                        or claim.plan_sha256 != plan_sha
                        or claim.attempt_id in attempts
                    ):
                        raise ValueError("run claim index/config/plan/attempt mismatch")
                    attempts.add(claim.attempt_id)
                    state = RunState.STARTED
                    if (directory / "terminal.json").exists():
                        terminal = read_record(directory / "terminal.json", RunTerminal)
                        if (
                            terminal.claim_sha256
                            != sha256(_read_file(directory / "claim.json")).hexdigest()
                        ):
                            raise ValueError("terminal claim checksum mismatch")
                        state = terminal.state
                        if state == RunState.COMPLETED:
                            _completed(plan, index, directory, terminal.artifact.sha256)
                        else:
                            failure = read_failure(
                                directory / terminal.artifact.name,
                                expected_sha256=terminal.artifact.sha256,
                            )
                            _failure(plan, plan_sha, claim, failure)
            slots.append(
                RunSlot(
                    index,
                    seed,
                    config.config_id,
                    directory.name,
                    state,
                    claim,
                    terminal,
                    diagnostics,
                )
            )
        return RepetitionSnapshot(plan, plan_sha, tuple(slots))
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        raise VerificationError(f"invalid repetition metadata: {error}") from error


class RepetitionController:
    """Single writer with explicit caller-owned executions, no campaign runner."""

    def __init__(self, root: Path, *, expected_plan_sha256: str | None = None):
        self.root, self.expected_plan_sha256 = root, expected_plan_sha256
        self.snapshot()

    @classmethod
    def create(cls, root: Path, plan: RepetitionPlan) -> "RepetitionController":
        if not isinstance(plan, RepetitionPlan):
            raise ValueError("explicit repetition plan required")
        root.mkdir(parents=True, exist_ok=False)
        digest = write_record(root / "plan.json", plan)
        sync_directory(root.parent)
        return cls(root, expected_plan_sha256=digest)

    def snapshot(self) -> RepetitionSnapshot:
        return read_repetitions(self.root, expected_plan_sha256=self.expected_plan_sha256)

    def _started(self, index: int):
        snapshot = self.snapshot()
        snapshot.plan.config_for(index)
        slot = snapshot.slots[index]
        if slot.state != RunState.STARTED or slot.claim is None:
            raise ValueError("run requires one nonterminal durable claim")
        return snapshot, slot.claim, self.root / slot.result_directory

    def claim(self, index: int, *, attempt_id: str) -> Path:
        snapshot = self.snapshot()
        config = snapshot.plan.config_for(index)
        if snapshot.slots[index].state != RunState.PENDING:
            raise ValueError("run already reserved; duplicate execution prohibited")
        if any(
            slot.claim is not None and slot.claim.attempt_id == attempt_id
            for slot in snapshot.slots
        ):
            raise ValueError("attempt identifier already reserved")
        claim = RunClaim(
            index, config.config_id, snapshot.plan_sha256, attempt_id, datetime.now(UTC).isoformat()
        )
        directory = self.root / snapshot.slots[index].result_directory
        directory.mkdir(exist_ok=False)
        sync_directory(self.root)
        write_record(directory / "claim.json", claim)
        return directory

    def complete(self, index: int) -> str:
        snapshot, _, directory = self._started(index)
        verified = _completed(snapshot.plan, index, directory, None)
        return self._terminal(
            directory,
            RunState.COMPLETED,
            ArtifactReference("evidence/manifest.json", verified.manifest_sha256),
        )

    def record_failure(
        self, index: int, failure: FailureRecord, *, state: RunState = RunState.FAILED
    ) -> str:
        snapshot, claim, directory = self._started(index)
        if not isinstance(state, RunState) or state not in {RunState.FAILED, RunState.INVALID}:
            raise ValueError("infrastructure attempt must remain failed/invalid")
        _failure(snapshot.plan, snapshot.plan_sha256, claim, failure)
        digest = write_failure(directory / "failure.json", failure)
        return self._terminal(directory, state, ArtifactReference("failure.json", digest))

    def _terminal(self, directory: Path, state: RunState, artifact: ArtifactReference) -> str:
        record = RunTerminal(
            state,
            sha256(_read_file(directory / "claim.json")).hexdigest(),
            artifact,
            datetime.now(UTC).isoformat(),
        )
        return write_record(directory / "terminal.json", record)
