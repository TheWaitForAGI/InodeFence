"""Explicit repeated policy schedule with journal-backed terminal accounting."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import ClassVar

from inodefence.model import ArchiveCase
from inodefence.runtime import SentinelSpec
from inodefence.targets.base import CampaignTarget

from .controller_memory import (
    ControllerMemoryObservation,
    ControllerMemoryObservationStart,
    finish_controller_memory_observation,
    start_controller_memory_observation,
)
from .encoding import json_bytes
from .failure import ArtifactReference, _text
from .policy_binding import PolicyEvaluationConfig
from .policy_journal import (
    PolicyJournalSnapshot,
    read_policy_journal,
    run_journaled_timed_search_campaign,
)
from .policy_timing import VerifiedTimedPolicyEvidence
from .repeated import RunState
from .storage import read_record, sync_directory, write_record
from .verify import VerificationError, _digest, _read_file


def _timestamp(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("record timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("record timestamp must be ISO-8601") from error
    if parsed.utcoffset() is None:
        raise ValueError("record timestamp requires a timezone")


def _label(value: str) -> None:
    _text(value)
    if any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for character in value
    ):
        raise ValueError("run and arm identifiers require stable filename-safe characters")


@dataclass(frozen=True, slots=True)
class PolicyScheduledRun:
    """One immutable schedule cell; repetition and arm identity stay explicit."""

    serialization_schema: ClassVar[int] = 1

    run_id: str
    arm_id: str
    evaluation_config: PolicyEvaluationConfig

    def __post_init__(self) -> None:
        _label(self.run_id)
        _label(self.arm_id)
        if type(self.evaluation_config) is not PolicyEvaluationConfig:
            raise ValueError("scheduled run requires a PolicyEvaluationConfig")


@dataclass(frozen=True, slots=True)
class PolicyRepetitionPlan:
    """Frozen ordered schedule; fairness remains a protocol-level decision."""

    serialization_schema: ClassVar[int] = 1

    experiment_id: str
    protocol_version: str
    runs: tuple[PolicyScheduledRun, ...]

    def __post_init__(self) -> None:
        _label(self.experiment_id)
        _label(self.protocol_version)
        if (
            not isinstance(self.runs, tuple)
            or not self.runs
            or not all(isinstance(run, PolicyScheduledRun) for run in self.runs)
            or len({run.run_id for run in self.runs}) != len(self.runs)
            or len({run.evaluation_config.config_id for run in self.runs}) != len(self.runs)
        ):
            raise ValueError("policy schedule requires unique run and configuration IDs")
        if any(
            run.evaluation_config.protocol_version != self.protocol_version for run in self.runs
        ):
            raise ValueError("scheduled configurations must use the declared protocol version")


@dataclass(frozen=True, slots=True)
class PolicyRunClaim:
    serialization_schema: ClassVar[int] = 1

    run_index: int
    run_id: str
    config_id: str
    plan_sha256: str
    attempt_id: str
    recorded_at: str

    def __post_init__(self) -> None:
        if type(self.run_index) is not int or self.run_index < 0:
            raise ValueError("nonnegative run index required")
        _label(self.run_id)
        _digest(self.config_id)
        _digest(self.plan_sha256)
        _text(self.attempt_id)
        _timestamp(self.recorded_at)


@dataclass(frozen=True, slots=True)
class PolicyRunTerminal:
    serialization_schema: ClassVar[int] = 1

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
            raise ValueError("policy terminal state must be completed/failed/invalid")
        _digest(self.claim_sha256)
        expected = (
            "evidence/completion.json"
            if self.state == RunState.COMPLETED
            else "evidence/failure.json"
        )
        if not isinstance(self.artifact, ArtifactReference) or self.artifact.name != expected:
            raise ValueError("policy terminal requires its journal terminal artifact")
        _timestamp(self.recorded_at)


@dataclass(frozen=True, slots=True)
class PolicyControllerMemory:
    """A terminal run bound to current-process lifetime peak RSS evidence."""

    serialization_schema: ClassVar[int] = 1

    run_index: int
    run_id: str
    config_id: str
    attempt_id: str
    plan_sha256: str
    state: RunState
    claim: ArtifactReference
    terminal: ArtifactReference
    evidence_terminal: ArtifactReference
    observation: ControllerMemoryObservation

    def __post_init__(self) -> None:
        if type(self.run_index) is not int or self.run_index < 0:
            raise ValueError("controller memory requires a nonnegative run index")
        _label(self.run_id)
        _digest(self.config_id)
        _text(self.attempt_id)
        _digest(self.plan_sha256)
        if not isinstance(self.state, RunState) or self.state not in {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.INVALID,
        }:
            raise ValueError("controller memory requires a terminal run state")
        if (
            not isinstance(self.claim, ArtifactReference)
            or self.claim.name != "claim.json"
            or not isinstance(self.terminal, ArtifactReference)
            or self.terminal.name != "terminal.json"
            or not isinstance(self.evidence_terminal, ArtifactReference)
            or self.evidence_terminal.name
            not in {"evidence/completion.json", "evidence/failure.json"}
            or not isinstance(self.observation, ControllerMemoryObservation)
        ):
            raise ValueError("invalid controller memory evidence binding")
        expected = (
            "evidence/completion.json"
            if self.state == RunState.COMPLETED
            else "evidence/failure.json"
        )
        if self.evidence_terminal.name != expected:
            raise ValueError("controller memory state/artifact mismatch")


@dataclass(frozen=True, slots=True)
class PolicyRunSlot:
    run_index: int
    run_id: str
    arm_id: str
    random_seed: int
    config_id: str
    result_directory: str
    state: RunState
    completed_steps: int
    claim: PolicyRunClaim | None
    terminal: PolicyRunTerminal | None
    diagnostics: tuple[str, ...] = ()
    controller_memory: PolicyControllerMemory | None = None
    controller_memory_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyRepetitionSnapshot:
    plan: PolicyRepetitionPlan
    plan_sha256: str
    slots: tuple[PolicyRunSlot, ...]


def _run_directory(index: int) -> str:
    return f"run-{index:08d}"


def _matches_journal(
    scheduled: PolicyScheduledRun,
    claim: PolicyRunClaim,
    plan_sha256: str,
    snapshot: PolicyJournalSnapshot,
) -> None:
    header = snapshot.header
    if (
        header.attempt_id != claim.attempt_id
        or header.experiment_id != plan_sha256
        or header.evaluation_config != scheduled.evaluation_config
    ):
        raise ValueError("policy journal differs from its schedule claim")


def _terminal_snapshot(
    scheduled: PolicyScheduledRun,
    claim: PolicyRunClaim,
    plan_sha256: str,
    directory: Path,
    terminal: PolicyRunTerminal,
) -> PolicyJournalSnapshot:
    journal = directory / "evidence"
    if terminal.state == RunState.COMPLETED:
        snapshot = read_policy_journal(journal, expected_completion_sha256=terminal.artifact.sha256)
        if not snapshot.complete or snapshot.infrastructure_invalid:
            raise ValueError("completed slot lacks completed policy evidence")
    else:
        snapshot = read_policy_journal(journal)
        if (
            not snapshot.infrastructure_invalid
            or snapshot.complete
            or snapshot.failure_sha256 != terminal.artifact.sha256
        ):
            raise ValueError("failed slot lacks matching infrastructure evidence")
    _matches_journal(scheduled, claim, plan_sha256, snapshot)
    return snapshot


def _matches_controller_memory(
    record: PolicyControllerMemory,
    *,
    index: int,
    scheduled: PolicyScheduledRun,
    claim: PolicyRunClaim,
    claim_digest: str,
    terminal: PolicyRunTerminal,
    terminal_digest: str,
    plan_sha256: str,
) -> None:
    if (
        record.run_index != index
        or record.run_id != scheduled.run_id
        or record.config_id != scheduled.evaluation_config.config_id
        or record.attempt_id != claim.attempt_id
        or record.plan_sha256 != plan_sha256
        or record.state != terminal.state
        or record.claim != ArtifactReference("claim.json", claim_digest)
        or record.terminal != ArtifactReference("terminal.json", terminal_digest)
        or record.evidence_terminal != terminal.artifact
    ):
        raise ValueError("controller memory record differs from terminal policy slot")


def read_policy_repetitions(
    root: Path,
    *,
    expected_plan_sha256: str | None = None,
    require_controller_memory: bool = False,
) -> PolicyRepetitionSnapshot:
    """Verify all scheduled slots; started/incomplete attempts are never retried."""
    try:
        if root.is_symlink() or not root.is_dir():
            raise ValueError("expected a policy repetition directory")
        plan_path = root / "plan.json"
        plan_sha = sha256(_read_file(plan_path)).hexdigest()
        if expected_plan_sha256 is not None and plan_sha != _digest(expected_plan_sha256):
            raise ValueError("policy repetition plan checksum mismatch")
        plan = read_record(plan_path, PolicyRepetitionPlan, expected_sha256=plan_sha)
        permitted = {"plan.json", *(_run_directory(index) for index in range(len(plan.runs)))}
        if any(
            path.name not in permitted and not path.name.startswith(".record-")
            for path in root.iterdir()
        ):
            raise ValueError("unexpected policy repetition artifact")

        slots: list[PolicyRunSlot] = []
        attempt_ids: set[str] = set()
        measured_processes: set[tuple[str, int, int]] = set()
        for index, scheduled in enumerate(plan.runs):
            directory = root / _run_directory(index)
            state = RunState.PENDING
            claim = None
            terminal = None
            completed_steps = 0
            diagnostics: tuple[str, ...] = ()
            controller_memory = None
            controller_memory_digest = None
            if directory.is_symlink():
                raise ValueError("policy run directory cannot be a symlink")
            if directory.exists():
                if not directory.is_dir():
                    raise ValueError("policy run slot must be a directory")
                allowed = {"claim.json", "terminal.json", "evidence", "controller-memory.json"}
                if any(path.name not in allowed for path in directory.iterdir()):
                    raise ValueError("unexpected policy run artifact")
                if not (directory / "claim.json").is_file():
                    if (directory / "controller-memory.json").exists():
                        raise ValueError("controller memory exists without a durable claim")
                    state = RunState.INVALID
                    diagnostics = ("reserved without durable claim; no automatic retry",)
                else:
                    claim_path = directory / "claim.json"
                    claim_digest = sha256(_read_file(claim_path)).hexdigest()
                    claim = read_record(claim_path, PolicyRunClaim, expected_sha256=claim_digest)
                    if (
                        claim.run_index != index
                        or claim.run_id != scheduled.run_id
                        or claim.config_id != scheduled.evaluation_config.config_id
                        or claim.plan_sha256 != plan_sha
                        or claim.attempt_id in attempt_ids
                    ):
                        raise ValueError("policy run claim differs from schedule")
                    attempt_ids.add(claim.attempt_id)
                    state = RunState.STARTED
                    journal_snapshot = None
                    if (directory / "evidence").exists():
                        journal_snapshot = read_policy_journal(directory / "evidence")
                        _matches_journal(scheduled, claim, plan_sha, journal_snapshot)
                        completed_steps = len(journal_snapshot.records)
                        diagnostics = (
                            ("complete journal lacks terminal acknowledgement",)
                            if journal_snapshot.complete
                            else ("infrastructure-invalid journal lacks terminal acknowledgement",)
                            if journal_snapshot.infrastructure_invalid
                            else ("interrupted journal prefix; no automatic retry",)
                        )
                    if (directory / "terminal.json").exists():
                        terminal_path = directory / "terminal.json"
                        terminal_digest = sha256(_read_file(terminal_path)).hexdigest()
                        terminal = read_record(
                            terminal_path,
                            PolicyRunTerminal,
                            expected_sha256=terminal_digest,
                        )
                        if terminal.claim_sha256 != claim_digest:
                            raise ValueError("policy terminal claim checksum mismatch")
                        journal_snapshot = _terminal_snapshot(
                            scheduled, claim, plan_sha, directory, terminal
                        )
                        completed_steps = len(journal_snapshot.records)
                        state = terminal.state
                        diagnostics = ()
                    memory_path = directory / "controller-memory.json"
                    if memory_path.exists():
                        if terminal is None:
                            raise ValueError("controller memory exists without a terminal slot")
                        controller_memory_digest = sha256(_read_file(memory_path)).hexdigest()
                        controller_memory = read_record(
                            memory_path,
                            PolicyControllerMemory,
                            expected_sha256=controller_memory_digest,
                        )
                        _matches_controller_memory(
                            controller_memory,
                            index=index,
                            scheduled=scheduled,
                            claim=claim,
                            claim_digest=claim_digest,
                            terminal=terminal,
                            terminal_digest=terminal_digest,
                            plan_sha256=plan_sha,
                        )
                        identity = controller_memory.observation.process_identity
                        if identity in measured_processes:
                            raise ValueError(
                                "controller process identity reused across measured policy runs"
                            )
                        measured_processes.add(identity)
                    if (
                        require_controller_memory
                        and terminal is not None
                        and controller_memory is None
                    ):
                        raise ValueError("terminal policy slot lacks required controller memory")
            slots.append(
                PolicyRunSlot(
                    index,
                    scheduled.run_id,
                    scheduled.arm_id,
                    scheduled.evaluation_config.campaign.random_seed,
                    scheduled.evaluation_config.config_id,
                    directory.name,
                    state,
                    completed_steps,
                    claim,
                    terminal,
                    diagnostics,
                    controller_memory,
                    controller_memory_digest,
                )
            )
        return PolicyRepetitionSnapshot(plan, plan_sha, tuple(slots))
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid policy repetition metadata: {error}") from error


class PolicyRepetitionController:
    """Single-writer exact schedule; a claimed slot is never automatically retried."""

    def __init__(self, root: Path, *, expected_plan_sha256: str | None = None):
        self.root = root
        self.expected_plan_sha256 = expected_plan_sha256
        self.snapshot()

    @classmethod
    def create(cls, root: Path, plan: PolicyRepetitionPlan) -> "PolicyRepetitionController":
        if type(plan) is not PolicyRepetitionPlan:
            raise ValueError("explicit PolicyRepetitionPlan required")
        root.mkdir(parents=True, exist_ok=False)
        digest = write_record(root / "plan.json", plan)
        sync_directory(root.parent)
        return cls(root, expected_plan_sha256=digest)

    def snapshot(self) -> PolicyRepetitionSnapshot:
        return read_policy_repetitions(self.root, expected_plan_sha256=self.expected_plan_sha256)

    def claim(self, index: int, *, attempt_id: str) -> Path:
        snapshot = self.snapshot()
        if type(index) is not int or not 0 <= index < len(snapshot.slots):
            raise ValueError("run index outside policy schedule")
        if snapshot.slots[index].state != RunState.PENDING:
            raise ValueError("policy run already reserved; duplicate execution prohibited")
        _text(attempt_id)
        if any(
            slot.claim is not None and slot.claim.attempt_id == attempt_id
            for slot in snapshot.slots
        ):
            raise ValueError("attempt identifier already reserved")
        scheduled = snapshot.plan.runs[index]
        claim = PolicyRunClaim(
            index,
            scheduled.run_id,
            scheduled.evaluation_config.config_id,
            snapshot.plan_sha256,
            attempt_id,
            datetime.now(UTC).isoformat(),
        )
        directory = self.root / snapshot.slots[index].result_directory
        directory.mkdir(exist_ok=False)
        sync_directory(self.root)
        write_record(directory / "claim.json", claim)
        return directory

    def _started(self, index: int) -> tuple[PolicyRepetitionSnapshot, PolicyRunClaim, Path]:
        snapshot = self.snapshot()
        if type(index) is not int or not 0 <= index < len(snapshot.slots):
            raise ValueError("run index outside policy schedule")
        slot = snapshot.slots[index]
        if slot.state != RunState.STARTED or slot.claim is None:
            raise ValueError("policy run requires one nonterminal durable claim")
        return snapshot, slot.claim, self.root / slot.result_directory

    def complete(self, index: int) -> str:
        snapshot, claim, directory = self._started(index)
        scheduled = snapshot.plan.runs[index]
        journal = read_policy_journal(directory / "evidence")
        _matches_journal(scheduled, claim, snapshot.plan_sha256, journal)
        if (
            not journal.complete
            or journal.infrastructure_invalid
            or journal.completion_sha256 is None
        ):
            raise ValueError("policy run has no complete journal")
        return self._terminal(
            directory,
            RunState.COMPLETED,
            ArtifactReference("evidence/completion.json", journal.completion_sha256),
        )

    def acknowledge_failure(self, index: int, *, state: RunState = RunState.FAILED) -> str:
        snapshot, claim, directory = self._started(index)
        if not isinstance(state, RunState) or state not in {RunState.FAILED, RunState.INVALID}:
            raise ValueError("policy infrastructure attempt must remain failed/invalid")
        scheduled = snapshot.plan.runs[index]
        journal = read_policy_journal(directory / "evidence")
        _matches_journal(scheduled, claim, snapshot.plan_sha256, journal)
        if not journal.infrastructure_invalid or journal.complete or journal.failure_sha256 is None:
            raise ValueError("policy run has no infrastructure failure journal")
        return self._terminal(
            directory,
            state,
            ArtifactReference("evidence/failure.json", journal.failure_sha256),
        )

    def execute(
        self,
        index: int,
        initial_cases: Sequence[ArchiveCase],
        target: CampaignTarget,
        *,
        attempt_id: str,
        sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    ) -> VerifiedTimedPolicyEvidence:
        """Claim and execute exactly once; ordinary failure is terminally counted."""
        snapshot = self.snapshot()
        if type(index) is not int or not 0 <= index < len(snapshot.slots):
            raise ValueError("run index outside policy schedule")
        scheduled = snapshot.plan.runs[index]
        cases = tuple(initial_cases)
        if (
            not cases
            or not all(isinstance(case, ArchiveCase) for case in cases)
            or tuple(case.case_id for case in cases) != scheduled.evaluation_config.initial_case_ids
        ):
            raise ValueError("initial cases differ from scheduled policy configuration")
        directory = self.claim(index, attempt_id=attempt_id)
        try:
            verified = run_journaled_timed_search_campaign(
                cases,
                target,
                scheduled.evaluation_config,
                directory / "evidence",
                attempt_id=attempt_id,
                experiment_id=snapshot.plan_sha256,
                sentinels=sentinels,
            )
        except Exception as error:
            try:
                self.acknowledge_failure(index)
            except Exception as terminal_error:
                error.add_note(
                    "policy repetition failure acknowledgement also failed: "
                    f"{type(terminal_error).__module__}.{type(terminal_error).__qualname__}: "
                    f"{terminal_error}"
                )
            raise
        self.complete(index)
        return verified

    def _publish_controller_memory(
        self,
        index: int,
        started: ControllerMemoryObservationStart,
    ) -> str:
        snapshot = self.snapshot()
        if type(index) is not int or not 0 <= index < len(snapshot.slots):
            raise ValueError("run index outside policy schedule")
        slot = snapshot.slots[index]
        if slot.claim is None or slot.terminal is None:
            raise ValueError("controller memory requires a terminal policy slot")
        if slot.controller_memory is not None:
            raise ValueError("controller memory is already published")
        directory = self.root / slot.result_directory
        claim_digest = sha256(_read_file(directory / "claim.json")).hexdigest()
        terminal_digest = sha256(_read_file(directory / "terminal.json")).hexdigest()
        observation = finish_controller_memory_observation(started)
        record = PolicyControllerMemory(
            index,
            slot.run_id,
            slot.config_id,
            slot.claim.attempt_id,
            snapshot.plan_sha256,
            slot.terminal.state,
            ArtifactReference("claim.json", claim_digest),
            ArtifactReference("terminal.json", terminal_digest),
            slot.terminal.artifact,
            observation,
        )
        return write_record(directory / "controller-memory.json", record)

    def execute_measured(
        self,
        index: int,
        initial_cases: Sequence[ArchiveCase],
        target: CampaignTarget,
        *,
        attempt_id: str,
        sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    ) -> VerifiedTimedPolicyEvidence:
        """Execute one run and bind Linux process-lifetime HWM to its terminal.

        One OS process may publish at most one measured slot. A pilot launcher must
        therefore start a fresh dedicated controller process for every campaign.
        The value is not a campaign-attributable delta and excludes target containers.
        """
        started = start_controller_memory_observation()
        snapshot = self.snapshot()
        if any(
            slot.controller_memory is not None
            and slot.controller_memory.observation.process_identity
            == started.sample.process_identity
            for slot in snapshot.slots
        ):
            raise ValueError("controller process already published a measured policy run")
        try:
            verified = self.execute(
                index,
                initial_cases,
                target,
                attempt_id=attempt_id,
                sentinels=sentinels,
            )
        except BaseException as error:
            try:
                slot = self.snapshot().slots[index]
                if slot.terminal is not None:
                    self._publish_controller_memory(index, started)
            except Exception as memory_error:
                error.add_note(
                    "controller memory publication also failed: "
                    f"{type(memory_error).__module__}.{type(memory_error).__qualname__}: "
                    f"{memory_error}"
                )
            raise
        self._publish_controller_memory(index, started)
        return verified

    def _terminal(self, directory: Path, state: RunState, artifact: ArtifactReference) -> str:
        terminal = PolicyRunTerminal(
            state,
            sha256(_read_file(directory / "claim.json")).hexdigest(),
            artifact,
            datetime.now(UTC).isoformat(),
        )
        return write_record(directory / "terminal.json", terminal)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--require-controller-memory", action="store_true")
    args = parser.parse_args()
    try:
        snapshot = read_policy_repetitions(
            args.root,
            expected_plan_sha256=args.plan_sha256,
            require_controller_memory=args.require_controller_memory,
        )
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    counts = {state.value: 0 for state in RunState}
    for slot in snapshot.slots:
        counts[slot.state.value] += 1
    print(
        json_bytes(
            {
                "classification": "verified-policy-repetition-v1",
                "plan_sha256": snapshot.plan_sha256,
                "experiment_id": snapshot.plan.experiment_id,
                "protocol_version": snapshot.plan.protocol_version,
                "states": counts,
                "slots": [
                    {
                        "run_index": slot.run_index,
                        "run_id": slot.run_id,
                        "arm_id": slot.arm_id,
                        "random_seed": slot.random_seed,
                        "config_id": slot.config_id,
                        "state": slot.state.value,
                        "completed_steps": slot.completed_steps,
                        "controller_memory_sha256": slot.controller_memory_sha256,
                        "controller_process_lifetime_peak_bytes": None
                        if slot.controller_memory is None
                        else slot.controller_memory.observation.lifetime_peak_resident_bytes,
                        "diagnostics": list(slot.diagnostics),
                    }
                    for slot in snapshot.slots
                ],
            }
        ).decode("ascii")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
