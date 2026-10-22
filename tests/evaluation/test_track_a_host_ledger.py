"""Track A host-attempt accounting tests use only synthetic retained evidence."""

import argparse
import io
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
from inodefence.evaluation.encoding import decode
from inodefence.evaluation.failure import ArtifactReference
from inodefence.evaluation.policy_repeated import PolicyRepetitionController
from inodefence.evaluation.repeated import RunState
from inodefence.evaluation.storage import write_record
from inodefence.evaluation.track_a_exploratory import (
    execute_track_a_slot,
    freeze_track_a_execution,
    read_track_a_execution,
)
from inodefence.evaluation.track_a_host_ledger import (
    HOST_ADMISSION_NAME,
    TrackAControllerTerminal,
    TrackAHostAttemptStatus,
    TrackAHostCleanupStatus,
    TrackAHostLedger,
    read_track_a_host_attempt,
    read_track_a_host_attempt_started,
    read_track_a_host_ledger,
    validate_track_a_host_admission,
    validate_track_a_host_attempt_binding,
)
from inodefence.evaluation.verify import VerificationError
from inodefence.execution.base import ContainerOutcome, ExecutionBackend
from inodefence.execution.docker_client import OUTPUT_LIMIT, BackendError
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


def _manifest_digest(attempt_directory: Path) -> str:
    return sha256((attempt_directory / "manifest.json").read_bytes()).hexdigest()


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


def test_admission_host_claim_controller_claim_and_complete_terminal_roundtrip(
    tmp_path, monkeypatch
):
    fixture, frozen, _, ledger = _ledger(tmp_path, monkeypatch)
    claimed = ledger.claim(0, attempt_id="host-complete-attempt")
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
    assert verified.terminal.campaign_state == RunState.COMPLETED
    assert verified.terminal.target_executions == 200


def test_host_generated_attempt_id_reaches_campaign_claim_and_host_terminal(tmp_path, monkeypatch):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    observed: list[str] = []

    def controlled_controller(args, claimed, state):
        observed.append(claimed.started.attempt_id)
        controller = PolicyRepetitionController(
            args.evidence / "repetitions",
            expected_plan_sha256=claimed.started.plan_sha256,
        )
        controller.claim(args.run_index, attempt_id=claimed.started.attempt_id)
        state.controller_launched = True
        state.controller_returncode = 9
        state.controller_stderr = b"controlled nonzero exit\n"
        state.controller_stderr_capture_complete = True
        raise BackendError("controlled controller nonzero exit")

    monkeypatch.setattr(host_script, "_launch_controller", controlled_controller)
    with pytest.raises(BackendError, match="nonzero"):
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


@pytest.mark.parametrize(
    ("label", "launched", "returncode", "deadline", "cleanup", "cleanup_errors"),
    (
        ("spawn", False, None, False, TrackAHostCleanupStatus.NOT_NEEDED, ()),
        ("malformed", True, None, False, TrackAHostCleanupStatus.NOT_NEEDED, ()),
        ("nonzero", True, 7, False, TrackAHostCleanupStatus.NOT_NEEDED, ()),
        ("watchdog", True, None, True, TrackAHostCleanupStatus.NOT_NEEDED, ()),
        (
            "cleanup",
            True,
            0,
            False,
            TrackAHostCleanupStatus.FAILED,
            ("controlled cleanup failure",),
        ),
    ),
)
def test_post_started_failures_publish_terminal_pending_zero_target(
    tmp_path,
    monkeypatch,
    label,
    launched,
    returncode,
    deadline,
    cleanup,
    cleanup_errors,
):
    fixture, frozen, _ = _frozen(tmp_path, monkeypatch)
    stderr = (label + " controller stderr\n").encode()

    def controlled_failure(args, claimed, state):
        state.controller_launched = launched
        state.controller_returncode = returncode
        state.controller_stderr = stderr
        state.controller_stderr_capture_complete = launched
        state.deadline_expired = deadline
        state.cleanup_status = cleanup
        state.cleanup_errors = cleanup_errors
        raise BackendError(f"controlled {label} failure")

    monkeypatch.setattr(host_script, "_launch_controller", controlled_failure)
    with pytest.raises(BackendError, match=label):
        host_script._run_cell(_args(fixture, frozen))

    snapshot = read_track_a_host_ledger(
        fixture.track_a_host_root, protocol_config_path=fixture.protocol_path
    )
    verified = snapshot.attempts[0]

    assert verified.terminal.status == TrackAHostAttemptStatus.FAILED
    assert verified.terminal.campaign_state == RunState.PENDING
    assert verified.terminal.target_executions == 0
    assert verified.terminal.cleanup_status == cleanup
    assert verified.controller_stderr == stderr
    assert verified.manifest.controller_stderr.sha256 == sha256(stderr).hexdigest()


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


@pytest.mark.parametrize("artifact", ("started.json", "terminal.json", "manifest.json"))
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
    with pytest.raises(ValueError, match="launch inputs differ"):
        controller_script.main()
    assert calls == []

    monkeypatch.setattr(sys, "argv", [*common, "run-cell"])
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
    monkeypatch.setattr(sys, "stdin", io.StringIO())
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
