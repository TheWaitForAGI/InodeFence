"""Track A host-attempt accounting tests use only synthetic retained evidence."""

import argparse
import base64
import io
import json
import sys
import threading
from contextlib import contextmanager
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path, PurePosixPath

import pytest
from scripts import track_a_container_controller as controller_script
from scripts import track_a_container_host as host_script
from tests.evaluation import test_track_a_admission as admission_support

import inodefence.evaluation.track_a_exploratory as track_a
from inodefence.evaluation.controller_memory import start_controller_memory_observation
from inodefence.evaluation.encoding import decode
from inodefence.evaluation.failure import ArtifactReference
from inodefence.evaluation.policy_journal import run_journaled_timed_search_campaign
from inodefence.evaluation.policy_repeated import PolicyRepetitionController
from inodefence.evaluation.repeated import RunState
from inodefence.evaluation.storage import publish_bytes, write_record
from inodefence.evaluation.track_a_exploratory import (
    execute_track_a_slot,
    freeze_track_a_execution,
    read_track_a_execution,
)
from inodefence.evaluation.track_a_host_ledger import (
    HOST_ADMISSION_NAME,
    TrackACampaignObservationStatus,
    TrackAControllerTerminal,
    TrackAHostAttemptStatus,
    TrackAHostCleanupStatus,
    TrackAHostLedger,
    claim_track_a_controller_entry,
    read_track_a_host_attempt,
    read_track_a_host_attempt_started,
    read_track_a_host_ledger,
    validate_track_a_host_admission,
    validate_track_a_host_attempt_binding,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.execution.base import ContainerOutcome, ExecutionBackend
from inodefence.execution.docker_client import OUTPUT_LIMIT, BackendError, CommandResult
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.targets.isolated import IsolatedTarget


class _SyntheticSuccessfulInvocation:
    def __init__(self, provenance, isolation) -> None:
        self.image_id = isolation.policy.image_id
        self.provenance = provenance
        self.artifacts = isolation.artifacts
        self.identity_command = ("synthetic-identity",)

    def verify_identity(self, stdout: bytes):
        return self.artifacts

    def command(self, archive_path: Path, extraction_root: Path):
        return ("synthetic-extract", str(archive_path), str(extraction_root))

    def classify(self, outcome, command):
        return ExecutionResult(
            self.provenance.target_id,
            self.provenance.target_version,
            command,
            ExecutionStatus.SUCCESS,
            0,
            "",
            "",
            0,
            self.provenance.timeout_seconds,
        )


class _SyntheticSuccessfulBackend(ExecutionBackend):
    def __init__(self, isolation) -> None:
        self.isolation = isolation

    def validate_image(self, image_id):
        assert image_id == self.isolation.policy.image_id

    def policy(self, image_id):
        self.validate_image(image_id)
        return self.isolation.policy

    def capture_isolation(self, image_id):
        self.validate_image(image_id)
        return self.isolation

    @contextmanager
    def prepare(self, request):
        class Prepared:
            def execute(self):
                return ContainerOutcome(0, b"synthetic identity", b"", 0, False)

        yield Prepared()


class _SyntheticFailingBackend(_SyntheticSuccessfulBackend):
    @contextmanager
    def prepare(self, request):
        if request.command[0] != "synthetic-extract":
            with super().prepare(request) as prepared:
                yield prepared
            return

        class Prepared:
            def execute(self):
                raise RuntimeError("controlled synthetic target boundary failure")

        yield Prepared()


def _frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = admission_support._synthetic_admission(tmp_path, monkeypatch)
    admission = admission_support._validate(fixture)
    affected = next(
        run.evaluation_config.provenance
        for run in admission.repetition_plan.runs
        if run.arm_id.startswith("affected-")
    )
    fixed = next(
        run.evaluation_config.provenance
        for run in admission.repetition_plan.runs
        if run.arm_id == "fixed-b3"
    )
    frozen = freeze_track_a_execution(
        fixture.output_root,
        affected,
        fixed,
        admission=admission,
        protocol_config_path=fixture.protocol_path,
    )
    verified = validate_track_a_host_admission(
        fixture.output_root,
        expected_execution_sha256=frozen.execution_sha256,
        pilot_authorization_path=fixture.authorization_path,
        expected_pilot_authorization_sha256=fixture.authorization_sha256,
        trusted_approval_reference=fixture.approval_reference,
        protocol_config_path=fixture.protocol_path,
    )
    return fixture, frozen, verified


def _ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture, frozen, admission = _frozen(tmp_path, monkeypatch)
    ledger = TrackAHostLedger(admission, protocol_config_path=fixture.protocol_path)
    return fixture, frozen, admission, ledger


def _args(fixture, frozen) -> argparse.Namespace:
    authorization = fixture.authorization
    return argparse.Namespace(
        context=authorization.host_docker_context,
        controller=authorization.controller_id,
        controller_worktree=PurePosixPath("/workspaces/InodeFence-track-a-controller"),
        volume=authorization.runtime_volume_name,
        image=[item.image_id for item in authorization.targets],
        evidence=fixture.output_root,
        pilot_authorization=fixture.authorization_path,
        pilot_authorization_sha256=fixture.authorization_sha256,
        approval_reference=fixture.approval_reference,
        protocol_config=fixture.protocol_path,
        run_index=0,
        execution_sha256=frozen.execution_sha256,
        mode="run-cell",
    )


def _controller_argv(
    fixture,
    frozen,
    claimed,
    *,
    attempt_id: str | None = None,
    launch_sha256: str = "f" * 64,
) -> list[str]:
    return [
        "track-a-controller",
        "--controller",
        fixture.authorization.controller_id,
        "--volume",
        fixture.authorization.runtime_volume_name,
        "--owner",
        "00000000000040008000000000000001",
        *(
            argument
            for image in fixture.authorization.targets
            for argument in ("--image", image.image_id)
        ),
        "--evidence",
        str(fixture.output_root),
        "--host-ledger",
        str(fixture.track_a_host_root),
        "--host-started-sha256",
        claimed.started_sha256,
        "--host-launch-sha256",
        launch_sha256,
        "--attempt-id",
        claimed.started.attempt_id if attempt_id is None else attempt_id,
        "--run-index",
        "0",
        "--execution-sha256",
        frozen.execution_sha256,
        "--protocol-config",
        str(fixture.protocol_path),
        "run-cell",
    ]


_CONTROLLER_LAUNCH_SECRET = b"s" * 32


def _launch_input(secret: bytes = _CONTROLLER_LAUNCH_SECRET) -> io.StringIO:
    return io.StringIO(
        json.dumps(
            {
                "controller_launch_secret": base64.b64encode(secret).decode("ascii"),
            }
        )
        + "\n"
    )


def _authorize_and_enter(fixture, ledger, claimed):
    launch = ledger.authorize_controller_launch(
        claimed,
        controller_id=fixture.authorization.controller_id,
        launch_secret_sha256=sha256(_CONTROLLER_LAUNCH_SECRET).hexdigest(),
    )
    result = claim_track_a_controller_entry(
        fixture.track_a_host_root,
        claimed.started.run_index,
        expected_started_sha256=claimed.started_sha256,
        expected_launch_sha256=launch.launch_sha256,
        expected_attempt_id=claimed.started.attempt_id,
        expected_execution_sha256=claimed.started.execution_sha256,
        controller_id=fixture.authorization.controller_id,
        runtime_volume_name=fixture.authorization.runtime_volume_name,
        image_ids=tuple(item.image_id for item in fixture.authorization.targets),
        evidence_root=fixture.output_root,
        launch_secret=_CONTROLLER_LAUNCH_SECRET,
        protocol_config_path=fixture.protocol_path,
    )
    return launch, result


def _manifest_digest(attempt_directory: Path) -> str:
    return sha256((attempt_directory / "manifest.json").read_bytes()).hexdigest()


class _FakeControllerProcess:
    def __init__(
        self,
        stdout: bytes,
        *,
        stderr: object = b"",
        returncode: int = 0,
        stdin_callback=None,
    ) -> None:
        class CallbackInput(io.BytesIO):
            def __init__(self, callback) -> None:
                super().__init__()
                self.callback = callback
                self.called = False

            def flush(self) -> None:
                super().flush()
                if not self.called:
                    self.called = True
                    self.callback(self.getvalue())

        self.stdin = CallbackInput(stdin_callback or (lambda content: None))
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr) if isinstance(stderr, bytes) else stderr
        self.returncode = returncode
        self.finished = False
        self.killed = False

    def wait(self, timeout=None):
        self.finished = True
        return self.returncode

    def poll(self):
        return self.returncode if self.finished else None

    def kill(self):
        self.killed = True
        self.returncode = -9


class _ReadySelector:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def register(self, *args):
        return None

    def select(self, timeout=None):
        return ((object(), object()),)


class _TimeoutSelector(_ReadySelector):
    def select(self, timeout=None):
        return ()


class _FailingStderr:
    def read(self, size=-1):
        raise OSError("controlled stderr drain failure")


class _FakeDockerCLI:
    def __init__(self, controller_id: str) -> None:
        self.controller_id = controller_id
        self.requests: list[tuple[str, ...]] = []

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        self.requests.append(args)
        if args[:2] == ("container", "inspect"):
            return CommandResult(0, json.dumps([{"Id": self.controller_id}]).encode(), b"")
        return CommandResult(0, b"", b"")


def _terminal_line(terminal: TrackAControllerTerminal) -> bytes:
    return (json.dumps({"terminal": asdict(terminal)}) + "\n").encode()


def _mismatched_terminal() -> TrackAControllerTerminal:
    return TrackAControllerTerminal(
        "different-attempt",
        0,
        "different-run",
        "a" * 64,
        "b" * 64,
        RunState.COMPLETED,
        1,
        ArtifactReference("repetitions/different/claim.json", "c" * 64),
        ArtifactReference("repetitions/different/terminal.json", "d" * 64),
        "e" * 64,
    )


def _install_launch_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    fixture,
    *,
    stdout: object = b"",
    stderr: object = b"",
    returncode: int = 0,
    spawn_error: BaseException | None = None,
    timeout: bool = False,
    claim_campaign: bool = False,
    cleanup_error: bool = False,
    on_spawn=None,
):
    client = _FakeDockerCLI(fixture.authorization.controller_id)
    processes: list[_FakeControllerProcess] = []
    observed_attempt_ids: list[str] = []

    def popen(command, **kwargs):
        if spawn_error is not None:
            raise spawn_error
        attempt_id = command[command.index("--attempt-id") + 1]
        observed_attempt_ids.append(attempt_id)
        process_stdout = stdout(command) if callable(stdout) else stdout
        assert isinstance(process_stdout, bytes)

        def enter_controller(content: bytes) -> None:
            frame = json.loads(content.decode("ascii").splitlines()[0])
            secret = base64.b64decode(frame["controller_launch_secret"], validate=True)
            started, _, _ = claim_track_a_controller_entry(
                fixture.track_a_host_root,
                0,
                expected_started_sha256=command[command.index("--host-started-sha256") + 1],
                expected_launch_sha256=command[command.index("--host-launch-sha256") + 1],
                expected_attempt_id=attempt_id,
                expected_execution_sha256=command[command.index("--execution-sha256") + 1],
                controller_id=fixture.authorization.controller_id,
                runtime_volume_name=fixture.authorization.runtime_volume_name,
                image_ids=tuple(item.image_id for item in fixture.authorization.targets),
                evidence_root=fixture.output_root,
                launch_secret=secret,
                protocol_config_path=fixture.protocol_path,
            )
            if claim_campaign:
                controller = PolicyRepetitionController(fixture.output_root / "repetitions")
                controller.claim(0, attempt_id=attempt_id)
            if on_spawn is not None:
                on_spawn(command, started)

        process = _FakeControllerProcess(
            process_stdout,
            stderr=stderr,
            returncode=returncode,
            stdin_callback=enter_controller,
        )
        processes.append(process)
        return process

    def cleanup(*args):
        if cleanup_error:
            raise BackendError("controlled cleanup failure")

    monkeypatch.setattr(host_script.shutil, "which", lambda executable: "/usr/bin/docker")
    monkeypatch.setattr(host_script, "token_bytes", lambda size: _CONTROLLER_LAUNCH_SECRET)
    monkeypatch.setattr(host_script, "DockerCLI", lambda executable, context: client)
    monkeypatch.setattr(host_script.subprocess, "Popen", popen)
    monkeypatch.setattr(
        host_script.selectors,
        "DefaultSelector",
        _TimeoutSelector if timeout else _ReadySelector,
    )
    monkeypatch.setattr(host_script, "remove_owned", cleanup)
    return client, processes, observed_attempt_ids


def _transient_execution_read_failure(monkeypatch: pytest.MonkeyPatch, fixture):
    original_read = track_a._read_file
    execution_path = fixture.output_root / "execution.json"
    armed = False
    failed = False

    def arm():
        nonlocal armed
        armed = True

    def read(path):
        nonlocal failed
        if armed and not failed and path == execution_path:
            failed = True
            raise OSError("controlled campaign evidence read failure")
        return original_read(path)

    monkeypatch.setattr(track_a, "_read_file", read)
    return arm


def _finish_pending(
    ledger: TrackAHostLedger,
    frozen,
    claimed,
    *,
    error: BaseException,
    launched: bool = False,
    returncode: int | None = None,
    deadline: bool = False,
    cleanup: TrackAHostCleanupStatus = TrackAHostCleanupStatus.NOT_NEEDED,
    cleanup_errors: tuple[str, ...] = (),
    stderr: bytes = b"",
    capture_complete: bool = False,
    truncated: bool = False,
):
    return ledger.finish(
        claimed,
        frozen,
        campaign_observation_error=None,
        controller_stderr=stderr,
        controller_stderr_truncated=truncated,
        controller_stderr_capture_complete=capture_complete,
        controller_launched=launched,
        controller_returncode=returncode,
        controller_terminal=None,
        deadline_expired=deadline,
        cleanup_status=cleanup,
        cleanup_errors=cleanup_errors,
        error=error,
    )


def test_admission_started_preclaim_terminal_roundtrip_is_consumed(tmp_path, monkeypatch):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="host-attempt-000")
    verified = _finish_pending(
        ledger,
        frozen,
        claimed,
        error=BackendError("controlled spawn failure"),
    )

    assert verified.started.attempt_id == "host-attempt-000"
    assert verified.terminal.status == TrackAHostAttemptStatus.FAILED
    assert verified.terminal.campaign_state == RunState.PENDING
    assert verified.terminal.campaign_claim is None
    assert verified.terminal.target_executions == 0
    assert verified.terminal.cleanup_status == TrackAHostCleanupStatus.NOT_NEEDED
    assert {path.name for path in claimed.directory.iterdir()} == {
        "started.json",
        "controller-stderr.bin",
        "terminal.json",
        "manifest.json",
    }
    snapshot = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    )
    assert snapshot.attempts == (verified,)
    missing_cleanup = asdict(verified.terminal)
    del missing_cleanup["cleanup_status"]
    with pytest.raises(ValueError, match="exact fields"):
        decode(type(verified.terminal), missing_cleanup)


def test_completed_campaign_requires_complete_cleanup_for_terminal_roundtrip(tmp_path, monkeypatch):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="host-complete-attempt")
    _authorize_and_enter(fixture, ledger, claimed)
    scheduled = frozen.repetitions.plan.runs[0]
    provenance = scheduled.evaluation_config.provenance
    assert provenance.isolation is not None
    target = IsolatedTarget(
        _SyntheticSuccessfulInvocation(provenance.target, provenance.isolation),
        _SyntheticSuccessfulBackend(provenance.isolation),
    )
    monkeypatch.setattr(track_a, "capture_source", lambda repository: provenance.source)
    monkeypatch.setattr(track_a, "capture_environment", lambda: provenance.environment)

    execute_track_a_slot(
        fixture.output_root,
        0,
        target,
        host_attempt=claimed.started,
        expected_execution_sha256=frozen.execution_sha256,
        repository=tmp_path,
        protocol_config_path=fixture.protocol_path,
    )
    execution = read_track_a_execution(
        fixture.output_root,
        expected_execution_sha256=frozen.execution_sha256,
        protocol_config_path=fixture.protocol_path,
    )
    slot = execution.repetitions.slots[0]
    assert slot.claim is not None
    assert slot.terminal is not None
    assert slot.controller_memory_sha256 is not None
    campaign_root = fixture.output_root / "repetitions" / slot.result_directory
    controller_terminal = TrackAControllerTerminal(
        claimed.started.attempt_id,
        slot.run_index,
        slot.run_id,
        execution.execution_sha256,
        execution.repetitions.plan_sha256,
        slot.state,
        slot.completed_steps,
        ArtifactReference(
            f"repetitions/{slot.result_directory}/claim.json",
            sha256((campaign_root / "claim.json").read_bytes()).hexdigest(),
        ),
        ArtifactReference(
            f"repetitions/{slot.result_directory}/terminal.json",
            sha256((campaign_root / "terminal.json").read_bytes()).hexdigest(),
        ),
        slot.controller_memory_sha256,
    )
    verified = ledger.finish(
        claimed,
        execution,
        campaign_observation_error=None,
        controller_stderr=b"synthetic controller completed\n",
        controller_stderr_truncated=False,
        controller_stderr_capture_complete=True,
        controller_launched=True,
        controller_returncode=0,
        controller_terminal=controller_terminal,
        deadline_expired=False,
        cleanup_status=TrackAHostCleanupStatus.COMPLETE,
        cleanup_errors=(),
        error=None,
    )

    assert slot.claim.attempt_id == claimed.started.attempt_id
    assert verified.terminal.status == TrackAHostAttemptStatus.COMPLETE
    assert verified.terminal.campaign_observation_status == TrackACampaignObservationStatus.VERIFIED
    assert verified.terminal.campaign_state == RunState.COMPLETED
    assert verified.terminal.target_executions == 200
    with pytest.raises(ValueError, match="requires verified completion and cleanup"):
        replace(verified.terminal, cleanup_status=TrackAHostCleanupStatus.NOT_NEEDED)
    with pytest.raises(ValueError, match="requires verified completion and cleanup"):
        replace(
            verified.terminal,
            cleanup_status=TrackAHostCleanupStatus.FAILED,
            cleanup_errors=("controlled cleanup failure",),
        )


def test_host_generated_attempt_id_reaches_campaign_claim_and_host_terminal(tmp_path, monkeypatch):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    commands: list[tuple[str, ...]] = []
    _, _, observed = _install_launch_boundaries(
        monkeypatch,
        fixture,
        returncode=9,
        stderr=b"controlled nonzero exit\n",
        claim_campaign=True,
        on_spawn=lambda command, started: commands.append(command),
    )
    with pytest.raises(BackendError, match="status 9"):
        host_script._run_cell(_args(fixture, frozen))

    snapshot = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    )
    attempt = snapshot.attempts[0]
    claim = attempt.execution.repetitions.slots[0].claim
    assert claim is not None
    assert observed == [attempt.started.attempt_id]
    assert claim.attempt_id == attempt.started.attempt_id
    assert attempt.terminal.campaign_state == RunState.STARTED
    assert attempt.terminal.target_executions == 0
    command_bytes = "\0".join(commands[0]).encode("utf-8")
    assert _CONTROLLER_LAUNCH_SECRET not in command_bytes
    assert base64.b64encode(_CONTROLLER_LAUNCH_SECRET) not in command_bytes


@pytest.mark.parametrize(
    "change",
    (
        lambda value: replace(value, run_index=1),
        lambda value: replace(value, run_id="different-run"),
        lambda value: replace(value, config_id="f" * 64),
        lambda value: replace(value, execution_sha256="e" * 64),
        lambda value: replace(value, plan_sha256="d" * 64),
        lambda value: replace(value, output_root="/var/lib/inodefence/different"),
    ),
)
def test_attempt_binding_rejects_schedule_execution_and_plan_mismatch(
    tmp_path, monkeypatch, change
):
    _, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="binding-attempt")

    with pytest.raises(ValueError, match="host attempt differs"):
        validate_track_a_host_attempt_binding(frozen, 0, change(claimed.started))


def test_started_reader_rejects_changed_admission_reference(tmp_path, monkeypatch):
    fixture, _, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="binding-attempt")
    started_path = claimed.directory / "started.json"
    started_path.unlink()
    changed = replace(
        claimed.started,
        host_admission=ArtifactReference(HOST_ADMISSION_NAME, "f" * 64),
    )
    changed_sha256 = write_record(started_path, changed)

    with pytest.raises(VerificationError, match="attempt and admission"):
        read_track_a_host_attempt_started(
            fixture.track_a_host_root,
            0,
            expected_started_sha256=changed_sha256,
            protocol_config_path=fixture.protocol_path,
        )


def test_existing_attempt_directory_is_never_overwritten(tmp_path, monkeypatch):
    _, _, _, ledger = _ledger(tmp_path, monkeypatch)
    scheduled = ledger.admission.execution.repetitions.plan.runs[0]
    directory = ledger.root / "attempts" / f"00-{scheduled.run_id}"
    directory.mkdir()
    marker = directory / "preserve"
    marker.write_bytes(b"existing evidence")

    with pytest.raises(VerificationError):
        ledger.claim(0, attempt_id="new-attempt")

    assert marker.read_bytes() == b"existing evidence"
    assert not (directory / "started.json").exists()


def test_failed_host_attempt_rejects_retry_and_duplicate_attempt_id(tmp_path, monkeypatch):
    _, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="consumed-attempt")
    _finish_pending(ledger, frozen, claimed, error=BackendError("controlled failure"))

    with pytest.raises(ValueError, match="identifier already consumed"):
        ledger.claim(0, attempt_id="consumed-attempt")
    with pytest.raises(ValueError, match="already has an attempt"):
        ledger.claim(0, attempt_id="different-attempt")


def test_terminalled_preclaim_attempt_rejects_controller_replay_before_backend(
    tmp_path, monkeypatch
):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="terminalled-attempt")
    _finish_pending(ledger, frozen, claimed, error=BackendError("controlled preclaim failure"))
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("called")
        raise AssertionError("terminalled attempt crossed the backend boundary")

    monkeypatch.setattr(
        controller_script, "AFFECTED_IMAGE_ID", fixture.authorization.targets[0].image_id
    )
    monkeypatch.setattr(
        controller_script, "FIXED_IMAGE_ID", fixture.authorization.targets[1].image_id
    )
    monkeypatch.setattr(controller_script, "ContainerExecutionBackend", forbidden)
    monkeypatch.setattr(IsolatedTarget, "run", forbidden)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", _launch_input())
    monkeypatch.setattr(sys, "argv", _controller_argv(fixture, frozen, claimed))

    with pytest.raises(VerificationError, match="already terminal or partially terminal"):
        controller_script.main()

    assert calls == []
    execution = read_track_a_execution(
        fixture.output_root,
        expected_execution_sha256=frozen.execution_sha256,
        protocol_config_path=fixture.protocol_path,
    )
    assert execution.repetitions.slots[0].state == RunState.PENDING
    assert execution.repetitions.slots[0].completed_steps == 0


@pytest.mark.parametrize("artifact", ("controller-stderr.bin", "terminal.json", "manifest.json"))
def test_partial_terminal_attempt_rejects_controller_before_backend(
    tmp_path, monkeypatch, artifact
):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="partial-terminal-attempt")
    publish_bytes(claimed.directory / artifact, b"partial terminal publication\n")
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("called")
        raise AssertionError("partial terminal attempt crossed the backend boundary")

    monkeypatch.setattr(
        controller_script, "AFFECTED_IMAGE_ID", fixture.authorization.targets[0].image_id
    )
    monkeypatch.setattr(
        controller_script, "FIXED_IMAGE_ID", fixture.authorization.targets[1].image_id
    )
    monkeypatch.setattr(controller_script, "ContainerExecutionBackend", forbidden)
    monkeypatch.setattr(IsolatedTarget, "run", forbidden)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", _launch_input())
    monkeypatch.setattr(sys, "argv", _controller_argv(fixture, frozen, claimed))

    with pytest.raises(VerificationError, match="already terminal or partially terminal"):
        controller_script.main()

    assert calls == []
    assert not list(fixture.output_root.rglob("claim.json"))


def test_start_only_attempt_cannot_enter_controller_without_live_host_launch(tmp_path, monkeypatch):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="start-only-attempt")
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("backend")
        raise AssertionError("start-only attempt crossed the backend boundary")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        controller_script, "AFFECTED_IMAGE_ID", fixture.authorization.targets[0].image_id
    )
    monkeypatch.setattr(
        controller_script, "FIXED_IMAGE_ID", fixture.authorization.targets[1].image_id
    )
    monkeypatch.setattr(controller_script, "ContainerExecutionBackend", forbidden)
    monkeypatch.setattr(sys, "stdin", _launch_input())
    monkeypatch.setattr(sys, "argv", _controller_argv(fixture, frozen, claimed))

    with pytest.raises(VerificationError, match="controller launch"):
        controller_script.main()

    assert calls == []
    assert {path.name for path in claimed.directory.iterdir()} == {"started.json"}
    assert not list(fixture.output_root.rglob("claim.json"))


def test_controller_entry_is_atomic_across_concurrent_claims(tmp_path, monkeypatch):
    fixture, _, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="concurrent-entry-attempt")
    launch = ledger.authorize_controller_launch(
        claimed,
        controller_id=fixture.authorization.controller_id,
        launch_secret_sha256=sha256(_CONTROLLER_LAUNCH_SECRET).hexdigest(),
    )
    barrier = threading.Barrier(3)
    successes = []
    failures: list[BaseException] = []
    backend_calls: list[str] = []

    def enter() -> None:
        barrier.wait()
        try:
            successes.append(
                claim_track_a_controller_entry(
                    fixture.track_a_host_root,
                    0,
                    expected_started_sha256=claimed.started_sha256,
                    expected_launch_sha256=launch.launch_sha256,
                    expected_attempt_id=claimed.started.attempt_id,
                    expected_execution_sha256=claimed.started.execution_sha256,
                    controller_id=fixture.authorization.controller_id,
                    runtime_volume_name=fixture.authorization.runtime_volume_name,
                    image_ids=tuple(item.image_id for item in fixture.authorization.targets),
                    evidence_root=fixture.output_root,
                    launch_secret=_CONTROLLER_LAUNCH_SECRET,
                    protocol_config_path=fixture.protocol_path,
                )
            )
            backend_calls.append("backend")
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=enter), threading.Thread(target=enter)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], VerificationError)
    assert backend_calls == ["backend"]
    assert {path.name for path in claimed.directory.iterdir()} == {
        "started.json",
        "controller-launch.json",
        "controller-entry.json",
    }


def test_first_controller_entry_consumes_launch_and_replay_stops_before_backend(
    tmp_path, monkeypatch
):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="one-shot-controller-attempt")
    launch = ledger.authorize_controller_launch(
        claimed,
        controller_id=fixture.authorization.controller_id,
        launch_secret_sha256=sha256(_CONTROLLER_LAUNCH_SECRET).hexdigest(),
    )
    backend_calls: list[str] = []

    def controlled_backend(*args, **kwargs):
        backend_calls.append("backend")
        raise BackendError("controlled backend boundary")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        controller_script, "AFFECTED_IMAGE_ID", fixture.authorization.targets[0].image_id
    )
    monkeypatch.setattr(
        controller_script, "FIXED_IMAGE_ID", fixture.authorization.targets[1].image_id
    )
    monkeypatch.setattr(controller_script, "ContainerExecutionBackend", controlled_backend)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    arguments = _controller_argv(
        fixture,
        frozen,
        claimed,
        launch_sha256=launch.launch_sha256,
    )

    monkeypatch.setattr(sys, "stdin", _launch_input())
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(BackendError, match="controlled backend"):
        controller_script.main()

    assert backend_calls == ["backend"]
    assert (claimed.directory / "controller-entry.json").is_file()
    retained = b"".join(path.read_bytes() for path in claimed.directory.iterdir())
    assert _CONTROLLER_LAUNCH_SECRET not in retained
    assert base64.b64encode(_CONTROLLER_LAUNCH_SECRET) not in retained

    monkeypatch.setattr(sys, "stdin", _launch_input())
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(VerificationError, match="already consumed"):
        controller_script.main()

    assert backend_calls == ["backend"]
    assert not list(fixture.output_root.rglob("claim.json"))


@pytest.mark.parametrize(
    "live_input",
    (
        io.StringIO(""),
        io.StringIO("{malformed}\n"),
        _launch_input(b"w" * 32),
    ),
)
def test_launch_only_attempt_rejects_missing_or_wrong_live_secret_before_backend(
    tmp_path, monkeypatch, live_input
):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="launch-only-attempt")
    launch = ledger.authorize_controller_launch(
        claimed,
        controller_id=fixture.authorization.controller_id,
        launch_secret_sha256=sha256(_CONTROLLER_LAUNCH_SECRET).hexdigest(),
    )
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("backend")
        raise AssertionError("invalid live launch crossed the backend boundary")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        controller_script, "AFFECTED_IMAGE_ID", fixture.authorization.targets[0].image_id
    )
    monkeypatch.setattr(
        controller_script, "FIXED_IMAGE_ID", fixture.authorization.targets[1].image_id
    )
    monkeypatch.setattr(controller_script, "ContainerExecutionBackend", forbidden)
    monkeypatch.setattr(sys, "stdin", live_input)
    monkeypatch.setattr(
        sys,
        "argv",
        _controller_argv(
            fixture,
            frozen,
            claimed,
            launch_sha256=launch.launch_sha256,
        ),
    )

    with pytest.raises((ValueError, VerificationError), match="launch handshake"):
        controller_script.main()

    assert calls == []
    assert {path.name for path in claimed.directory.iterdir()} == {
        "started.json",
        "controller-launch.json",
    }
    assert not list(fixture.output_root.rglob("claim.json"))


@pytest.mark.parametrize("artifact", ("controller-launch.json", "controller-entry.json"))
def test_partial_controller_prefix_rejects_entry_before_backend(tmp_path, monkeypatch, artifact):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="partial-controller-prefix-attempt")
    if artifact == "controller-entry.json":
        launch = ledger.authorize_controller_launch(
            claimed,
            controller_id=fixture.authorization.controller_id,
            launch_secret_sha256=sha256(_CONTROLLER_LAUNCH_SECRET).hexdigest(),
        )
        launch_sha256 = launch.launch_sha256
        publish_bytes(claimed.directory / artifact, b"partial controller entry\n")
    else:
        partial_launch = b"partial controller launch\n"
        publish_bytes(claimed.directory / artifact, partial_launch)
        launch_sha256 = sha256(partial_launch).hexdigest()
    backend_calls: list[str] = []

    def forbidden(*args, **kwargs):
        backend_calls.append("backend")
        raise AssertionError("partial controller prefix crossed the backend boundary")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        controller_script, "AFFECTED_IMAGE_ID", fixture.authorization.targets[0].image_id
    )
    monkeypatch.setattr(
        controller_script, "FIXED_IMAGE_ID", fixture.authorization.targets[1].image_id
    )
    monkeypatch.setattr(controller_script, "ContainerExecutionBackend", forbidden)
    monkeypatch.setattr(sys, "stdin", _launch_input())
    monkeypatch.setattr(
        sys,
        "argv",
        _controller_argv(fixture, frozen, claimed, launch_sha256=launch_sha256),
    )

    with pytest.raises(VerificationError):
        controller_script.main()

    assert backend_calls == []
    assert not list(fixture.output_root.rglob("claim.json"))


@pytest.mark.parametrize(
    "change",
    (
        lambda value: replace(value, attempt_id="different-attempt"),
        lambda value: replace(value, run_index=1),
        lambda value: replace(value, run_id="different-run"),
        lambda value: replace(value, config_id="c" * 64),
        lambda value: replace(value, execution_sha256="e" * 64),
        lambda value: replace(value, plan_sha256="d" * 64),
        lambda value: replace(
            value,
            host_admission=ArtifactReference(HOST_ADMISSION_NAME, "a" * 64),
        ),
        lambda value: replace(
            value,
            started=ArtifactReference("started.json", "b" * 64),
        ),
        lambda value: replace(value, controller_id="different-controller"),
    ),
)
def test_controller_launch_binding_mismatch_is_rejected_before_entry(tmp_path, monkeypatch, change):
    fixture, _, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="launch-binding-attempt")
    launch = ledger.authorize_controller_launch(
        claimed,
        controller_id=fixture.authorization.controller_id,
        launch_secret_sha256=sha256(_CONTROLLER_LAUNCH_SECRET).hexdigest(),
    )
    launch_path = claimed.directory / "controller-launch.json"
    launch_path.unlink()
    changed_sha256 = write_record(launch_path, change(launch.launch))

    with pytest.raises(VerificationError):
        claim_track_a_controller_entry(
            fixture.track_a_host_root,
            0,
            expected_started_sha256=claimed.started_sha256,
            expected_launch_sha256=changed_sha256,
            expected_attempt_id=claimed.started.attempt_id,
            expected_execution_sha256=claimed.started.execution_sha256,
            controller_id=fixture.authorization.controller_id,
            runtime_volume_name=fixture.authorization.runtime_volume_name,
            image_ids=tuple(item.image_id for item in fixture.authorization.targets),
            evidence_root=fixture.output_root,
            launch_secret=_CONTROLLER_LAUNCH_SECRET,
            protocol_config_path=fixture.protocol_path,
        )

    assert not (claimed.directory / "controller-entry.json").exists()
    assert not list(fixture.output_root.rglob("claim.json"))


def test_duplicate_controller_launch_is_no_overwrite(tmp_path, monkeypatch):
    fixture, _, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="duplicate-launch-attempt")
    first = ledger.authorize_controller_launch(
        claimed,
        controller_id=fixture.authorization.controller_id,
        launch_secret_sha256=sha256(_CONTROLLER_LAUNCH_SECRET).hexdigest(),
    )
    before = (claimed.directory / "controller-launch.json").read_bytes()

    with pytest.raises(ValueError, match="already consumed"):
        ledger.authorize_controller_launch(
            claimed,
            controller_id=fixture.authorization.controller_id,
            launch_secret_sha256=sha256(b"x" * 32).hexdigest(),
        )

    assert (claimed.directory / "controller-launch.json").read_bytes() == before
    assert first.launch.launch_secret_sha256 == sha256(_CONTROLLER_LAUNCH_SECRET).hexdigest()


@pytest.mark.parametrize(
    "case",
    ("spawn", "malformed", "oversized", "unterminated", "nonzero", "watchdog", "cleanup"),
)
def test_real_launch_orchestration_failures_publish_terminal_pending_zero_target(
    tmp_path, monkeypatch, case
):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    stderr = (case + " controller stderr\n").encode()
    options = {}
    expected_error = {
        "spawn": "controlled spawn failure",
        "malformed": "malformed trusted",
        "oversized": "oversized or unterminated",
        "unterminated": "oversized or unterminated",
        "nonzero": "status 7",
        "watchdog": "watchdog",
        "cleanup": "terminal summary",
    }[case]
    if case == "spawn":
        options["spawn_error"] = OSError("controlled spawn failure")
    elif case == "malformed":
        options["stdout"] = b"{malformed}\n"
    elif case == "oversized":
        options["stdout"] = b"x" * (host_script.BROKER_LINE_LIMIT + 1) + b"\n"
    elif case == "unterminated":
        options["stdout"] = b"{}"
    elif case == "nonzero":
        options["returncode"] = 7
    elif case == "watchdog":
        options["timeout"] = True
    else:

        def create_request(command):
            owner = command[command.index("--owner") + 1]
            return (
                json.dumps(
                    {
                        "args": [
                            "container",
                            "create",
                            "--label",
                            f"{host_script.OWNER_LABEL}={owner}",
                            "--name",
                            "synthetic-target",
                            "synthetic-image",
                        ],
                        "timeout": 1,
                    }
                )
                + "\n"
            ).encode()

        options["stdout"] = create_request
        options["cleanup_error"] = True
    _, processes, _ = _install_launch_boundaries(monkeypatch, fixture, stderr=stderr, **options)
    with pytest.raises((BackendError, OSError, TimeoutError), match=expected_error):
        host_script._run_cell(_args(fixture, frozen))

    snapshot = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    )
    verified = snapshot.attempts[0]

    assert verified.terminal.status == TrackAHostAttemptStatus.FAILED
    assert verified.terminal.campaign_state == RunState.PENDING
    assert verified.terminal.target_executions == 0
    expected_stderr = b"" if case == "spawn" else stderr[:OUTPUT_LIMIT]
    assert verified.controller_stderr == expected_stderr
    assert verified.manifest.controller_stderr.sha256 == sha256(expected_stderr).hexdigest()
    assert verified.terminal.deadline_expired is (case == "watchdog")
    assert verified.controller_launch is not None
    assert verified.terminal.controller_launch == verified.manifest.controller_launch
    if case == "spawn":
        assert verified.controller_entry is None
        assert verified.terminal.controller_entry is None
    else:
        assert verified.controller_entry is not None
        assert verified.terminal.controller_entry == verified.manifest.controller_entry
        assert verified.controller_entry.attempt_id == verified.started.attempt_id
    if case == "watchdog":
        assert processes[0].killed is True
        assert verified.terminal.controller_returncode == -9
    assert verified.terminal.cleanup_status == (
        TrackAHostCleanupStatus.FAILED if case == "cleanup" else TrackAHostCleanupStatus.NOT_NEEDED
    )
    attempt_directory = next((fixture.track_a_host_root / "attempts").iterdir())
    retained = b"".join(path.read_bytes() for path in attempt_directory.iterdir())
    assert _CONTROLLER_LAUNCH_SECRET not in retained
    assert base64.b64encode(_CONTROLLER_LAUNCH_SECRET) not in retained


def test_real_launch_bounded_stderr_prefix_truncation_and_checksum(tmp_path, monkeypatch):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    stderr = b"s" * (OUTPUT_LIMIT + 8192)
    _install_launch_boundaries(
        monkeypatch,
        fixture,
        stdout=b"{malformed}\n",
        stderr=stderr,
    )

    with pytest.raises(BackendError, match="malformed trusted"):
        host_script._run_cell(_args(fixture, frozen))

    attempt = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    ).attempts[0]
    assert attempt.controller_stderr == stderr[:OUTPUT_LIMIT]
    assert attempt.terminal.controller_stderr_size == OUTPUT_LIMIT
    assert attempt.terminal.controller_stderr_truncated is True
    assert attempt.terminal.controller_stderr_capture_complete is True
    assert attempt.manifest.controller_stderr.sha256 == sha256(stderr[:OUTPUT_LIMIT]).hexdigest()


def test_real_launch_primary_stderr_and_cleanup_failures_all_reach_terminal(tmp_path, monkeypatch):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)

    def create_then_malformed(command):
        owner = command[command.index("--owner") + 1]
        request = {
            "args": [
                "container",
                "create",
                "--label",
                f"{host_script.OWNER_LABEL}={owner}",
                "--name",
                "synthetic-target",
                "synthetic-image",
            ],
            "timeout": 1,
        }
        return (json.dumps(request) + "\n{malformed}\n").encode()

    _install_launch_boundaries(
        monkeypatch,
        fixture,
        stdout=create_then_malformed,
        stderr=_FailingStderr(),
        cleanup_error=True,
    )
    with pytest.raises(BackendError, match="malformed trusted") as raised:
        host_script._run_cell(_args(fixture, frozen))

    attempt = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    ).attempts[0]
    assert attempt.terminal.status == TrackAHostAttemptStatus.FAILED
    assert attempt.terminal.controller_stderr_capture_complete is False
    assert attempt.terminal.cleanup_status == TrackAHostCleanupStatus.FAILED
    assert attempt.terminal.exception is not None
    assert "stderr capture also failed" in attempt.terminal.exception
    assert "post-controller handling also failed" in attempt.terminal.exception
    assert "controlled cleanup failure" in attempt.terminal.exception
    assert len(raised.value.__notes__) == 2


def test_real_launch_cleanup_complete_after_owned_container_request(tmp_path, monkeypatch):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)

    def create_request(command):
        owner = command[command.index("--owner") + 1]
        return (
            json.dumps(
                {
                    "args": [
                        "container",
                        "create",
                        "--label",
                        f"{host_script.OWNER_LABEL}={owner}",
                        "--name",
                        "synthetic-target",
                        "synthetic-image",
                    ],
                    "timeout": 1,
                }
            )
            + "\n"
        ).encode()

    _install_launch_boundaries(monkeypatch, fixture, stdout=create_request)
    with pytest.raises(BackendError, match="terminal summary"):
        host_script._run_cell(_args(fixture, frozen))

    attempt = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    ).attempts[0]
    assert attempt.terminal.cleanup_status == TrackAHostCleanupStatus.COMPLETE
    assert attempt.terminal.status == TrackAHostAttemptStatus.FAILED


def test_claimed_campaign_reread_failure_records_unknown_not_stale_pending(tmp_path, monkeypatch):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    arm_reread_failure = _transient_execution_read_failure(monkeypatch, fixture)
    _install_launch_boundaries(
        monkeypatch,
        fixture,
        returncode=7,
        claim_campaign=True,
        on_spawn=lambda command, started: arm_reread_failure(),
    )
    with pytest.raises(BackendError, match="status 7") as raised:
        host_script._run_cell(_args(fixture, frozen))

    snapshot = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    )
    terminal = snapshot.attempts[0].terminal
    assert terminal.campaign_observation_status == TrackACampaignObservationStatus.FAILED
    assert terminal.campaign_observation_error is not None
    assert "controlled campaign evidence read failure" in terminal.campaign_observation_error
    assert terminal.campaign_state is None
    assert terminal.campaign_claim is None
    assert terminal.campaign_terminal is None
    assert terminal.target_executions is None
    assert terminal.exception is not None
    assert "campaign prefix reread also failed" in terminal.exception
    assert any("campaign prefix reread also failed" in note for note in raised.value.__notes__)


def test_terminal_campaign_reread_failure_records_unknown_and_preserves_campaign_prefix(
    tmp_path, monkeypatch
):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    scheduled = frozen.repetitions.plan.runs[0]
    provenance = scheduled.evaluation_config.provenance
    assert provenance.isolation is not None
    monkeypatch.setattr(track_a, "capture_source", lambda repository: provenance.source)
    monkeypatch.setattr(track_a, "capture_environment", lambda: provenance.environment)
    arm_reread_failure = _transient_execution_read_failure(monkeypatch, fixture)

    def fail_campaign(command, started):
        target = IsolatedTarget(
            _SyntheticSuccessfulInvocation(provenance.target, provenance.isolation),
            _SyntheticFailingBackend(provenance.isolation),
        )
        with pytest.raises(RuntimeError, match="synthetic target boundary failure"):
            execute_track_a_slot(
                fixture.output_root,
                0,
                target,
                host_attempt=started,
                expected_execution_sha256=frozen.execution_sha256,
                repository=tmp_path,
                protocol_config_path=fixture.protocol_path,
            )
        arm_reread_failure()

    _install_launch_boundaries(
        monkeypatch,
        fixture,
        returncode=7,
        on_spawn=fail_campaign,
    )
    with pytest.raises(BackendError, match="status 7"):
        host_script._run_cell(_args(fixture, frozen))

    snapshot = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    )
    attempt = snapshot.attempts[0]
    assert attempt.execution.repetitions.slots[0].state == RunState.FAILED
    assert attempt.terminal.campaign_observation_status == TrackACampaignObservationStatus.FAILED
    assert attempt.terminal.campaign_state is None
    assert attempt.terminal.target_executions is None
    assert attempt.terminal.campaign_observation_error is not None
    assert "controlled campaign evidence read failure" in (
        attempt.terminal.campaign_observation_error
    )


@pytest.mark.parametrize("campaign_state", (RunState.FAILED, RunState.INVALID))
def test_real_launch_preserves_claimed_failed_or_invalid_campaign_prefix(
    tmp_path, monkeypatch, campaign_state
):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    scheduled = frozen.repetitions.plan.runs[0]
    provenance = scheduled.evaluation_config.provenance
    assert provenance.isolation is not None

    def terminal_campaign(command, started):
        attempt_id = command[command.index("--attempt-id") + 1]
        memory_start = start_controller_memory_observation()
        controller = PolicyRepetitionController(
            fixture.output_root / "repetitions",
            expected_plan_sha256=frozen.repetitions.plan_sha256,
        )
        directory = controller.claim(0, attempt_id=attempt_id)
        target = IsolatedTarget(
            _SyntheticSuccessfulInvocation(provenance.target, provenance.isolation),
            _SyntheticFailingBackend(provenance.isolation),
        )
        with pytest.raises(RuntimeError, match="synthetic target boundary failure"):
            run_journaled_timed_search_campaign(
                minimal_seed_corpus(),
                target,
                scheduled.evaluation_config,
                directory / "evidence",
                attempt_id=attempt_id,
                experiment_id=frozen.repetitions.plan_sha256,
            )
        controller.acknowledge_failure(0, state=campaign_state)
        controller._publish_controller_memory(0, memory_start)

    _install_launch_boundaries(
        monkeypatch,
        fixture,
        returncode=7,
        on_spawn=terminal_campaign,
    )
    with pytest.raises(BackendError, match="status 7"):
        host_script._run_cell(_args(fixture, frozen))

    attempt = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    ).attempts[0]
    slot = attempt.execution.repetitions.slots[0]
    assert slot.claim is not None
    assert slot.claim.attempt_id == attempt.started.attempt_id
    assert slot.state == campaign_state
    assert attempt.terminal.campaign_state == campaign_state
    assert attempt.terminal.campaign_claim is not None
    assert attempt.terminal.campaign_terminal is not None
    assert attempt.terminal.target_executions == 0
    assert attempt.terminal.status == TrackAHostAttemptStatus.FAILED


@pytest.mark.parametrize("duplicate", (False, True))
def test_controller_terminal_mismatch_or_duplicate_is_terminal_failure(
    tmp_path, monkeypatch, duplicate
):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    line = _terminal_line(_mismatched_terminal())
    _install_launch_boundaries(
        monkeypatch,
        fixture,
        stdout=line + line if duplicate else line,
    )

    expected = "duplicate" if duplicate else "did not complete"
    with pytest.raises(BackendError, match=expected):
        host_script._run_cell(_args(fixture, frozen))

    snapshot = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    )
    terminal = snapshot.attempts[0].terminal
    assert terminal.status == TrackAHostAttemptStatus.FAILED
    assert terminal.controller_terminal is None
    assert terminal.campaign_state == RunState.PENDING
    if not duplicate:
        assert terminal.exception is not None
        assert "controller terminal differs from the campaign claim" in terminal.exception


def test_controller_terminal_and_campaign_reread_failures_are_both_retained(tmp_path, monkeypatch):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    arm_reread_failure = _transient_execution_read_failure(monkeypatch, fixture)
    _install_launch_boundaries(
        monkeypatch,
        fixture,
        stdout=_terminal_line(_mismatched_terminal()),
        on_spawn=lambda command, started: arm_reread_failure(),
    )
    with pytest.raises(VerificationError, match="controlled campaign evidence read failure"):
        host_script._run_cell(_args(fixture, frozen))

    terminal = (
        read_track_a_host_ledger(
            fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
        )
        .attempts[0]
        .terminal
    )
    assert terminal.campaign_observation_status == TrackACampaignObservationStatus.FAILED
    assert terminal.controller_terminal is None
    assert terminal.exception is not None
    assert "controlled campaign evidence read failure" in terminal.exception
    assert "controller terminal cannot be verified" in terminal.exception


def test_bounded_stderr_capture_retains_prefix_and_truncation():
    capture = host_script._BoundedControllerStderr(limit=1024)
    thread = threading.Thread(target=capture.drain, args=(io.BytesIO(b"e" * 4096),))
    thread.start()

    content, truncated = capture.finish(thread)

    assert content == b"e" * 1024
    assert truncated is True
    assert len(content) <= OUTPUT_LIMIT


def test_bounded_stderr_capture_failure_is_not_complete():
    capture = host_script._BoundedControllerStderr(limit=1024)
    capture.error = OSError("controlled stderr failure")
    thread = threading.Thread(target=lambda: None)
    thread.start()

    with pytest.raises(BackendError, match="could not be drained"):
        capture.finish(thread)


@pytest.mark.parametrize("value", ({}, {"terminal": "unexpected"}, []))
def test_malformed_controller_terminal_output_is_rejected(value):
    with pytest.raises(BackendError, match="malformed"):
        host_script._controller_terminal(value)


@pytest.mark.parametrize("artifact", ("terminal.json", "manifest.json", "controller-stderr.bin"))
def test_reader_rejects_missing_terminal_manifest_or_stderr(tmp_path, monkeypatch, artifact):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="incomplete-attempt")
    verified = _finish_pending(
        ledger,
        frozen,
        claimed,
        error=BackendError("controlled failure"),
        stderr=b"bounded\n",
    )
    (claimed.directory / artifact).unlink()

    with pytest.raises(VerificationError):
        read_track_a_host_attempt(
            fixture.track_a_host_root,
            0,
            expected_manifest_sha256=verified.manifest_sha256,
            protocol_config_path=fixture.protocol_path,
        )


@pytest.mark.parametrize(
    "artifact", ("started.json", "controller-stderr.bin", "terminal.json", "manifest.json")
)
def test_reader_rejects_tampered_attempt_records(tmp_path, monkeypatch, artifact):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="tampered-attempt")
    verified = _finish_pending(
        ledger,
        frozen,
        claimed,
        error=BackendError("controlled failure"),
    )
    path = claimed.directory / artifact
    path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(VerificationError):
        read_track_a_host_attempt(
            fixture.track_a_host_root,
            0,
            expected_manifest_sha256=verified.manifest_sha256,
            protocol_config_path=fixture.protocol_path,
        )


@pytest.mark.parametrize("artifact", ("controller-launch.json", "controller-entry.json"))
@pytest.mark.parametrize("change", ("missing", "tampered"))
def test_reader_rejects_missing_or_tampered_controller_launch_evidence(
    tmp_path, monkeypatch, artifact, change
):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    _install_launch_boundaries(monkeypatch, fixture, returncode=7)
    with pytest.raises(BackendError, match="status 7"):
        host_script._run_cell(_args(fixture, frozen))

    attempt_directory = next((fixture.track_a_host_root / "attempts").iterdir())
    manifest_sha256 = _manifest_digest(attempt_directory)
    path = attempt_directory / artifact
    if change == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(VerificationError):
        read_track_a_host_attempt(
            fixture.track_a_host_root,
            0,
            expected_manifest_sha256=manifest_sha256,
            protocol_config_path=fixture.protocol_path,
        )


def test_reader_does_not_modify_host_track_a_or_n05_evidence(tmp_path, monkeypatch):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="readonly-attempt")
    verified = _finish_pending(
        ledger,
        frozen,
        claimed,
        error=BackendError("controlled failure"),
    )
    before = {
        "host": admission_support._tree_bytes(fixture.track_a_host_root),
        "track_a": admission_support._tree_bytes(fixture.output_root),
        "n05_host": admission_support._tree_bytes(fixture.host_root),
        "n05_linux": admission_support._tree_bytes(fixture.linux_root),
    }

    read_track_a_host_attempt(
        fixture.track_a_host_root,
        0,
        expected_manifest_sha256=verified.manifest_sha256,
        protocol_config_path=fixture.protocol_path,
    )

    assert admission_support._tree_bytes(fixture.track_a_host_root) == before["host"]
    assert admission_support._tree_bytes(fixture.output_root) == before["track_a"]
    assert admission_support._tree_bytes(fixture.host_root) == before["n05_host"]
    assert admission_support._tree_bytes(fixture.linux_root) == before["n05_linux"]


def test_admission_failure_precedes_started_controller_docker_and_target(tmp_path, monkeypatch):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    args = _args(fixture, frozen)
    args.pilot_authorization_sha256 = "f" * 64
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("called")
        raise AssertionError("failed admission crossed an execution boundary")

    monkeypatch.setattr(host_script, "_launch_controller", forbidden)
    monkeypatch.setattr(host_script.shutil, "which", forbidden)
    monkeypatch.setattr(IsolatedTarget, "run", forbidden)

    with pytest.raises(VerificationError):
        host_script._run_cell(args)

    assert calls == []
    assert not fixture.track_a_host_root.exists()
    assert not list(fixture.output_root.rglob("claim.json"))


def test_pre_started_cell_collision_calls_no_controller_campaign_or_target(tmp_path, monkeypatch):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    scheduled = frozen.repetitions.plan.runs[0]
    directory = ledger.root / "attempts" / f"00-{scheduled.run_id}"
    directory.mkdir()
    marker = directory / "preserve"
    marker.write_bytes(b"preexisting host evidence")
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("called")
        raise AssertionError("pre-start failure crossed an execution boundary")

    monkeypatch.setattr(host_script, "_launch_controller", forbidden)
    monkeypatch.setattr(PolicyRepetitionController, "claim", forbidden)
    monkeypatch.setattr(IsolatedTarget, "run", forbidden)

    with pytest.raises(VerificationError):
        host_script._run_cell(_args(fixture, frozen))

    assert calls == []
    assert marker.read_bytes() == b"preexisting host evidence"
    assert not (directory / "started.json").exists()
    assert not list(fixture.output_root.rglob("claim.json"))


def test_controller_rejects_changed_or_missing_host_attempt_id_before_target(tmp_path, monkeypatch):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    monkeypatch.setattr(
        controller_script, "AFFECTED_IMAGE_ID", fixture.authorization.targets[0].image_id
    )
    monkeypatch.setattr(
        controller_script, "FIXED_IMAGE_ID", fixture.authorization.targets[1].image_id
    )
    claimed = ledger.claim(0, attempt_id="host-owned-attempt")
    launch = ledger.authorize_controller_launch(
        claimed,
        controller_id=fixture.authorization.controller_id,
        launch_secret_sha256=sha256(_CONTROLLER_LAUNCH_SECRET).hexdigest(),
    )
    monkeypatch.chdir(tmp_path)
    common = [
        "track-a-controller",
        "--controller",
        fixture.authorization.controller_id,
        "--volume",
        fixture.authorization.runtime_volume_name,
        "--owner",
        "00000000000040008000000000000001",
        *(
            argument
            for image in fixture.authorization.targets
            for argument in ("--image", image.image_id)
        ),
        "--evidence",
        str(fixture.output_root),
        "--host-ledger",
        str(fixture.track_a_host_root),
        "--host-started-sha256",
        claimed.started_sha256,
        "--host-launch-sha256",
        launch.launch_sha256,
        "--run-index",
        "0",
        "--execution-sha256",
        frozen.execution_sha256,
        "--protocol-config",
        str(fixture.protocol_path),
    ]
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("called")
        raise AssertionError("attempt mismatch reached target binding")

    monkeypatch.setattr(IsolatedTarget, "__post_init__", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [*common, "--attempt-id", "changed-attempt", "run-cell"],
    )
    monkeypatch.setattr(sys, "stdin", _launch_input())
    with pytest.raises(ValueError, match="differs from the host-published"):
        controller_script.main()
    assert calls == []

    changed_launch = list(common)
    changed_launch[changed_launch.index("--volume") + 1] = "different-volume"
    monkeypatch.setattr(
        sys,
        "argv",
        [*changed_launch, "--attempt-id", claimed.started.attempt_id, "run-cell"],
    )
    monkeypatch.setattr(sys, "stdin", _launch_input())
    with pytest.raises(ValueError, match="launch inputs differ"):
        controller_script.main()
    assert calls == []

    monkeypatch.setattr(sys, "argv", [*common, "run-cell"])
    monkeypatch.setattr(sys, "stdin", _launch_input())
    with pytest.raises(SystemExit):
        controller_script.main()
    assert calls == []

    broker_output = io.StringIO()
    diagnostic_output = io.StringIO()
    observed_writers = []

    def controlled_backend(client, *args, **kwargs):
        observed_writers.append(client.writer)
        raise BackendError("controlled backend boundary")

    monkeypatch.setattr(controller_script, "ContainerExecutionBackend", controlled_backend)
    monkeypatch.setattr(sys, "stdin", _launch_input())
    monkeypatch.setattr(sys, "stdout", broker_output)
    monkeypatch.setattr(sys, "stderr", diagnostic_output)
    monkeypatch.setattr(
        sys,
        "argv",
        [*common, "--attempt-id", claimed.started.attempt_id, "run-cell"],
    )
    with pytest.raises(BackendError, match="controlled backend"):
        controller_script.main()
    assert observed_writers == [broker_output]


def test_legacy_digest_only_prepare_and_admissionless_run_cell_remain_rejected(
    tmp_path, monkeypatch
):
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("called")
        raise AssertionError("legacy path launched a controller")

    monkeypatch.setattr(host_script.subprocess, "Popen", forbidden)
    base = [
        "track-a-host",
        "--context",
        "synthetic",
        "--controller",
        "a" * 64,
        "--controller-worktree",
        "/workspaces/InodeFence-track-a-controller",
        "--volume",
        "synthetic-volume",
        "--image",
        host_script.AFFECTED_IMAGE_ID,
        "--image",
        host_script.FIXED_IMAGE_ID,
        "--evidence",
        str(tmp_path / "output"),
    ]
    for arguments in (
        [
            *base,
            "--preflight-manifest-sha256",
            "b" * 64,
            "--resource-authorization-sha256",
            "c" * 64,
            "prepare",
        ],
        [*base, "--run-index", "0", "--execution-sha256", "d" * 64, "run-cell"],
    ):
        monkeypatch.setattr(sys, "argv", arguments)
        with pytest.raises(SystemExit):
            host_script.main()

    assert calls == []


def test_started_and_manifest_bind_exact_execution_plan_run_and_admission(tmp_path, monkeypatch):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="cross-reference-attempt")
    verified = _finish_pending(
        ledger,
        frozen,
        claimed,
        error=BackendError("controlled failure"),
    )
    scheduled = frozen.repetitions.plan.runs[0]

    assert verified.started.run_index == 0
    assert verified.started.run_id == scheduled.run_id
    assert verified.started.config_id == scheduled.evaluation_config.config_id
    assert verified.started.execution_sha256 == frozen.execution_sha256
    assert verified.started.plan_sha256 == frozen.repetitions.plan_sha256
    assert verified.started.host_admission == ArtifactReference(
        HOST_ADMISSION_NAME, verified.admission_sha256
    )
    assert verified.manifest_sha256 == _manifest_digest(claimed.directory)
