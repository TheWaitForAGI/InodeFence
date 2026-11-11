"""Docker infrastructure stalls re-execute a case instead of aborting or faking a timeout.

Deterministic fault injection without Docker: a scripted fake daemon drives the real
``ContainerExecutionBackend`` code path, and a virtual clock stands in for every wait
(a timed-out call advances it by its timeout; nothing sleeps). The stall shapes follow the
HOST1 benchmark of 2026-11-07/08: Class S (one container's start never completes and holds
its lock), Class G (every call stalls for about a minute) and the 0.107 s target whose
attach timed out.
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import scripts.run_effect_demo as run_effect_demo
from scripts.container_controller import apply_aborted_infra_reexecutions

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_demo import EffectStepReporter, render_effect_step_line
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.abort_classification import (
    MAX_INFRA_RETRIES,
    MAX_INFRA_RETRIES_PER_CAMPAIGN,
    STALL_ABSENCE_CONFIRM_SECONDS,
    InvalidReason,
    classify_abort_reason,
)
from inodefence.execution.base import (
    BackendError,
    ContainerOutcome,
    ContainerRequest,
    OutputLimitError,
)
from inodefence.execution.container import OWNER_LABEL, ContainerExecutionBackend
from inodefence.execution.docker_client import CommandResult
from inodefence.execution.stall_recovery import (
    STDERR_PREFIX,
    ObservedDockerClient,
    StallRecovery,
    TimeoutVerdict,
    classify_target_timeout,
    confirm_absent,
    daemon_runtime_seconds,
)
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ExecutionStatus
from inodefence.mutator import MutationPolicy
from inodefence.runtime import RUNTIME_BASE, disposable_sandbox
from inodefence.targets.isolated import identify_image

IMAGE = "sha256:" + "a" * 64
CONTROLLER = "b" * 64
OWNER = "c" * 32
REALTIME_BASE = 1_794_000_000.0
TIMEOUT = 10


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def realtime(self) -> float:
        return REALTIME_BASE + self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def rfc3339(clock_time: float) -> str:
    epoch = REALTIME_BASE + clock_time
    whole = int(epoch)
    nanos = round((epoch - whole) * 1e9)
    moment = datetime.fromtimestamp(whole, UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + f".{nanos:09d}Z"


NEVER = "0001-01-01T00:00:00Z"


class StallDaemon:
    """Scripted daemon. ``plans`` gives each created container's start behavior, in order.

    Plans: ``normal`` (runs 0.1 s, exit 0); ``hang:<s>`` (Class S: start never completes,
    every call on the container times out for <s> seconds after the start deadline);
    ``created`` (start times out, container stays created, inspect works); ``attach_late``
    (target exits after 0.107 s, attach times out); ``genuine`` (target runs until killed);
    ``late:<s>`` (start overhead <s>, then runs until killed); ``global:<s>`` (normal start,
    then every daemon call times out for <s> seconds, Class G); ``foreign`` (owned by
    another invocation).
    """

    def __init__(self, clock: Clock, plans: list[str] | None = None) -> None:
        self.clock = clock
        self.plans = list(plans or [])
        self.log: list[tuple[tuple[str, ...], CommandResult]] = []
        self.containers: dict[str, dict[str, Any]] = {}
        self.names: dict[str, str] = {}
        self.global_until = -1.0
        self.created = 0

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        self.clock.advance(0.001)
        result = self._run(args, timeout)
        self.log.append((args, result))
        return result

    def _timeout(self, timeout: float) -> CommandResult:
        self.clock.advance(timeout)
        return CommandResult(-9, b"", b"", True)

    def _resolve(self, token: str) -> dict[str, Any] | None:
        identity = self.names.get(token, token)
        return self.containers.get(identity)

    def _run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        if args[0] == "version":
            return CommandResult(
                0, b'{"Os":"linux","Version":"test","ApiVersion":"1.54","Arch":"arm64"}', b""
            )
        if self.clock.now < self.global_until:
            return self._timeout(timeout)
        if args[:2] == ("image", "inspect"):
            info = {"Id": IMAGE, "Os": "linux", "Architecture": "arm64", "Config": {"Env": []}}
            return CommandResult(0, json.dumps([info]).encode(), b"")
        if args[:2] == ("container", "create"):
            return self._create(args)
        token = args[-1]
        if args[:2] == ("container", "inspect") and token == CONTROLLER:
            info = {
                "Mounts": [
                    {
                        "Type": "volume",
                        "Name": "inodefence-runtime",
                        "Destination": str(RUNTIME_BASE),
                        "RW": True,
                    }
                ],
                "Config": {"Hostname": CONTROLLER[:12]},
            }
            return CommandResult(0, json.dumps([info]).encode(), b"")
        container = self._resolve(token)
        if container is None:
            return CommandResult(1, b"", f"Error: No such object: {token}\n".encode())
        if self.clock.now < container["locked_until"]:
            return self._timeout(timeout)
        if args[:2] == ("container", "inspect"):
            info = dict(container["info"])
            info["State"] = {
                "Status": container["status"],
                "Running": container["status"] == "running",
                "Pid": 42 if container["status"] == "running" else 0,
                "StartedAt": NEVER
                if container["started_at"] is None
                else rfc3339(container["started_at"]),
                "FinishedAt": NEVER
                if container["finished_at"] is None
                else rfc3339(container["finished_at"]),
            }
            return CommandResult(0, json.dumps([info]).encode(), b"")
        if args[:2] == ("container", "start"):
            return self._start(container, timeout)
        if args[:2] == ("container", "kill"):
            if container["status"] != "running":
                return CommandResult(1, b"", b"Error: container is not running\n")
            container["status"] = "exited"
            container["finished_at"] = self.clock.now
            return CommandResult(0, b"", b"")
        if args[:2] == ("container", "wait"):
            return CommandResult(0, b"0\n", b"")
        if args[:2] == ("container", "rm"):
            del self.containers[container["id"]]
            del self.names[container["name"]]
            return CommandResult(0, b"", b"")
        raise AssertionError(f"unexpected call {args}")

    def _create(self, args: tuple[str, ...]) -> CommandResult:
        self.created += 1
        identity = f"{self.created:064x}"
        name = args[args.index("--name") + 1]
        root = args[args.index("--workdir") + 1].removesuffix("/extract")
        plan = self.plans.pop(0) if self.plans else "normal"
        owner = "f" * 32 if plan == "foreign" else OWNER
        info = {
            "Id": identity,
            "Image": IMAGE,
            "Config": {
                "Labels": {OWNER_LABEL: owner},
                "User": "1000:1000",
                "Entrypoint": [args[args.index("--entrypoint") + 1]],
                "Cmd": list(args[args.index(IMAGE) + 1 :]) or None,
                "WorkingDir": root + "/extract",
                "Env": [args[index + 1] for index, arg in enumerate(args) if arg == "--env"],
            },
            "HostConfig": {
                "NetworkMode": "none",
                "ReadonlyRootfs": True,
                "Privileged": False,
                "PidMode": "",
                "IpcMode": "private",
                "CgroupnsMode": "private",
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges=true"],
                "PidsLimit": 64,
                "Memory": 512 * 1024 * 1024,
                "MemorySwap": 512 * 1024 * 1024,
                "LogConfig": {"Type": "none"},
                "ShmSize": 16 * 1024 * 1024,
                "Ulimits": [
                    {"Name": "nofile", "Hard": 1024, "Soft": 1024},
                    {"Name": "fsize", "Hard": 64 * 1024 * 1024, "Soft": 64 * 1024 * 1024},
                ],
                "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=33554432,mode=1777"},
                "Mounts": [
                    {
                        "Type": "volume",
                        "Source": "inodefence-runtime",
                        "Target": root,
                        "VolumeOptions": {
                            "NoCopy": True,
                            "Subpath": Path(root).relative_to(RUNTIME_BASE).as_posix(),
                        },
                    }
                ],
            },
            "Mounts": [{"Destination": root}],
        }
        self.containers[identity] = {
            "id": identity,
            "name": name,
            "root": root,
            "plan": plan,
            "info": info,
            "status": "created",
            "started_at": None,
            "finished_at": None,
            "locked_until": -1.0,
        }
        self.names[name] = identity
        return CommandResult(0, identity.encode(), b"")

    def _start(self, container: dict[str, Any], timeout: float) -> CommandResult:
        plan, _, argument = container["plan"].partition(":")
        if plan in ("normal", "foreign", "global"):
            container["started_at"] = self.clock.now + 0.02
            container["finished_at"] = container["started_at"] + 0.1
            container["status"] = "exited"
            self.clock.advance(0.2)
            if plan == "global":
                self.global_until = self.clock.now + float(argument)
            return CommandResult(0, b"out", b"err")
        if plan == "hang":
            result = self._timeout(timeout)
            container["locked_until"] = self.clock.now + float(argument)
            return result
        if plan == "created":
            return self._timeout(timeout)
        if plan == "attach_late":
            container["started_at"] = self.clock.now + 0.02
            container["finished_at"] = container["started_at"] + 0.107
            container["status"] = "exited"
            return self._timeout(timeout)
        if plan in ("genuine", "late"):
            container["started_at"] = self.clock.now + (float(argument) if argument else 0.02)
            container["status"] = "running"
            return self._timeout(timeout)
        raise AssertionError(f"unknown plan {plan}")

    # Helpers for assertions -------------------------------------------------------------

    def ops(self) -> list[str]:
        return [" ".join(args[:2]) for args, _ in self.log]

    def create_names(self) -> list[str]:
        return [args[args.index("--name") + 1] for args, _ in self.log if args[1] == "create"]


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr("inodefence.execution.container.os.getuid", lambda: 1000)
    monkeypatch.setattr("inodefence.execution.container.os.getgid", lambda: 1000)
    monkeypatch.setattr("socket.gethostname", lambda: CONTROLLER[:12])
    clock = Clock()

    def build(plans: list[str] | None = None, **recovery: Any):
        daemon = StallDaemon(clock, plans)
        observed = ObservedDockerClient(daemon, monotonic=clock.monotonic, realtime=clock.realtime)
        backend = ContainerExecutionBackend(observed, CONTROLLER, "inodefence-runtime", OWNER)
        emitted: list[dict[str, object]] = []
        stall = StallRecovery(
            observed,
            OWNER,
            monotonic=clock.monotonic,
            realtime=clock.realtime,
            sleep=clock.advance,
            emit=emitted.append,
            **recovery,
        )
        return daemon, backend, stall, emitted

    return clock, build


def target_attempt(backend, roots: list[Path], *, probe: bool = False):
    """One case attempt shaped like run_node_tar_effect_case: [probe container,] target."""

    def attempt() -> ContainerOutcome:
        if probe:
            identify_image(backend, IMAGE, ("/identify",))
        with disposable_sandbox() as sandbox:
            roots.append(sandbox.root)
            request = ContainerRequest(IMAGE, ("/helper", "case"), sandbox.root, TIMEOUT)
            with backend.prepare(request) as prepared:
                return prepared.execute()

    return attempt


def run_case(stall: StallRecovery, attempt) -> ContainerOutcome:
    return stall.run(
        attempt,
        timed_out=lambda outcome: outcome.exit_code is None,
        timeout_seconds=TIMEOUT,
        step_index=3,
        case_id="case-3",
    )


def first_absent_answer(daemon: StallDaemon, tokens: set[str]) -> int:
    for index, (args, result) in enumerate(daemon.log):
        if (
            args[:2] == ("container", "inspect")
            and args[2] in tokens
            and result.returncode == 1
            and b"No such object" in result.stderr
        ):
            return index
    raise AssertionError("absence was never confirmed")


def create_indexes(daemon: StallDaemon) -> list[int]:
    return [index for index, (args, _) in enumerate(daemon.log) if args[1] == "create"]


# 1. Class S --------------------------------------------------------------------------------


@pytest.mark.parametrize("hang", (60.0, 140.0))
def test_class_s_start_hang_reexecutes_in_a_new_container_after_absence(world, hang) -> None:
    clock, build = world
    daemon, backend, stall, emitted = build([f"hang:{hang}", "normal"])
    roots: list[Path] = []

    outcome = run_case(stall, target_attempt(backend, roots))

    assert outcome.exit_code == 0
    first, second = daemon.create_names()
    assert first != second and roots[0] != roots[1]
    # The second create happens only after the daemon answered "no such container" for the
    # first container, so the stalled start cannot run after the re-execution began.
    absent = first_absent_answer(daemon, {first, f"{1:064x}"})
    assert absent < create_indexes(daemon)[1]
    # The target ran exactly once per container.
    assert daemon.ops().count("container start") == 2
    [event] = stall.events
    assert event["action"] == "reexecuted"
    assert event["invalid_reason"] == InvalidReason.CLEANUP_INSPECT.value
    assert cast(dict, event["stall_call"])["op"] == "container start"
    assert cast(dict, event["absence"])["confirmed"] is True
    assert cast(dict, event["absence"])["seconds"] <= STALL_ABSENCE_CONFIRM_SECONDS + 50
    assert emitted == stall.events
    assert stall.reexecution_count == 1


# 2. Class S variant: the start never completed but inspect answers "created" --------------


def test_start_timeout_in_created_state_is_not_recorded_as_target_timeout(world) -> None:
    _, build = world
    daemon, backend, stall, _ = build(["created", "normal"])

    outcome = run_case(stall, target_attempt(backend, []))

    assert outcome.exit_code == 0
    [event] = stall.events
    assert event["timeout_reclassified"] == TimeoutVerdict.START_NOT_COMPLETED.value
    assert event["invalid_reason"] == InvalidReason.RUNTIME_CALL.value
    assert event["action"] == "reexecuted"


# 3. Class G --------------------------------------------------------------------------------


def test_class_g_global_stall_after_a_normal_attach_reexecutes(world) -> None:
    _, build = world
    daemon, backend, stall, _ = build(["global:57.3", "normal"])

    outcome = run_case(stall, target_attempt(backend, []))

    assert outcome.exit_code == 0
    assert len(daemon.create_names()) == 2
    [event] = stall.events
    assert cast(dict, event["stall_call"])["op"] == "container inspect"
    assert event["action"] == "reexecuted"
    assert cast(dict, event["absence"])["probes"] >= 2


# 4. The misclassification case and the genuine-timeout boundary ---------------------------


def test_attach_stall_after_a_fast_target_exit_is_not_a_target_timeout(world) -> None:
    _, build = world
    daemon, backend, stall, _ = build(["attach_late", "normal"])

    outcome = run_case(stall, target_attempt(backend, []))

    assert outcome.exit_code == 0
    [event] = stall.events
    assert event["timeout_reclassified"] == TimeoutVerdict.DAEMON_RUNTIME_SHORT.value
    assert event["daemon_runtime_seconds"] == pytest.approx(0.107, abs=1e-6)


@pytest.mark.parametrize("plan", ("genuine", "late:0.5"))
def test_genuine_timeout_stays_timed_out_without_extra_calls(world, plan) -> None:
    """Daemon run time >= 9.0 s keeps TIMED_OUT, including the [9.0, 10.0) s band."""
    _, build = world
    daemon, backend, stall, _ = build([plan])
    plain_clock = Clock()
    plain = StallDaemon(plain_clock, [plan])
    plain_backend = ContainerExecutionBackend(plain, CONTROLLER, "inodefence-runtime", OWNER)

    outcome = run_case(stall, target_attempt(backend, []))
    expected = target_attempt(plain_backend, [])()

    assert outcome.exit_code is None and expected.exit_code is None
    assert stall.events == []
    assert normalized(daemon) == normalized(plain)
    verdict, runtime = classify_target_timeout(stall.client.calls, TIMEOUT)
    assert verdict == TimeoutVerdict.GENUINE
    assert runtime is not None and runtime >= 9.0
    if plan.startswith("late"):
        assert runtime < 10.0


def test_start_overhead_that_cut_the_target_budget_is_reexecuted(world) -> None:
    _, build = world
    _, backend, stall, _ = build(["late:3.0", "normal"])

    outcome = run_case(stall, target_attempt(backend, []))

    assert outcome.exit_code == 0
    [event] = stall.events
    assert event["timeout_reclassified"] == TimeoutVerdict.DAEMON_RUNTIME_SHORT.value
    assert cast(float, event["daemon_runtime_seconds"]) < 9.0


def test_daemon_runtime_reads_nanosecond_and_offset_timestamps() -> None:
    state = {
        "StartedAt": "2026-11-08T01:02:03.123456789Z",
        "FinishedAt": "2026-11-08T10:02:13.123456790+09:00",
    }
    assert daemon_runtime_seconds(state) == pytest.approx(10.000000001, abs=1e-9)
    assert daemon_runtime_seconds({"StartedAt": NEVER, "FinishedAt": NEVER}) is None
    assert daemon_runtime_seconds({"StartedAt": "garbage", "FinishedAt": NEVER}) is None


# 5. Per-case bound -------------------------------------------------------------------------


def test_case_bound_exhaustion_raises_the_original_failure(world) -> None:
    _, build = world
    plans = ["hang:25"] * (MAX_INFRA_RETRIES + 1)
    daemon, backend, stall, _ = build(plans)

    with pytest.raises(BackendError) as raised:
        run_case(stall, target_attempt(backend, []))

    # The same exception (type, message, chain) the campaign aborts with today.
    assert str(raised.value) == "container runtime cleanup inspect failed: timed out"
    assert isinstance(raised.value.__context__, BackendError)
    assert classify_abort_reason(f"x.BackendError: {raised.value}") == (
        InvalidReason.CLEANUP_INSPECT
    )
    assert [event["action"] for event in stall.events] == [
        "reexecuted",
        "reexecuted",
        "abort_case_bound",
    ]
    assert stall.events[-1]["absence"] is None  # no extra Docker call before the abort
    assert len(daemon.create_names()) == MAX_INFRA_RETRIES + 1


# 6. Per-campaign bound ---------------------------------------------------------------------


class JournalOnlyDaemon:
    """Answers routine calls; ``container start`` times out (a stall journal entry)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        self.calls.append(args)
        if args[:2] == ("container", "start"):
            return CommandResult(-9, b"", b"", True)
        return CommandResult(0, b"", b"")


def stalling_once[V](
    observed: ObservedDockerClient, value: V, stalls: set[str], key: str
) -> Callable[[], V]:
    def attempt() -> V:
        if key not in stalls:
            stalls.add(key)
            observed.run(("container", "start", "--attach", "d" * 64), TIMEOUT)
            raise BackendError("container runtime inspect failed: timed out")
        return value

    return attempt


def journal_recovery(**kwargs: Any) -> tuple[StallRecovery, ObservedDockerClient]:
    clock = Clock()
    observed = ObservedDockerClient(
        JournalOnlyDaemon(), monotonic=clock.monotonic, realtime=clock.realtime
    )
    stall = StallRecovery(
        observed,
        OWNER,
        monotonic=clock.monotonic,
        realtime=clock.realtime,
        sleep=clock.advance,
        emit=lambda _record: None,
        **kwargs,
    )
    return stall, observed


def test_campaign_bound_exhaustion_aborts() -> None:
    stall, observed = journal_recovery()
    stalls: set[str] = set()
    for index in range(MAX_INFRA_RETRIES_PER_CAMPAIGN):
        value = stall.run(
            stalling_once(observed, index, stalls, f"case-{index}"),
            timed_out=lambda _value: False,
            timeout_seconds=TIMEOUT,
            step_index=index,
            case_id=f"case-{index}",
        )
        assert value == index
    with pytest.raises(BackendError, match="inspect failed"):
        stall.run(
            stalling_once(observed, "late", stalls, "case-late"),
            timed_out=lambda _value: False,
            timeout_seconds=TIMEOUT,
            step_index=MAX_INFRA_RETRIES_PER_CAMPAIGN,
            case_id="case-late",
        )
    assert stall.reexecution_count == MAX_INFRA_RETRIES_PER_CAMPAIGN
    assert stall.events[-1]["action"] == "abort_campaign_bound"


# 7. Absence not confirmed ------------------------------------------------------------------


def test_unconfirmed_absence_aborts_without_a_second_container(world) -> None:
    clock, build = world
    daemon, backend, stall, _ = build(["hang:1000", "normal"])

    with pytest.raises(BackendError, match="cleanup inspect failed"):
        run_case(stall, target_attempt(backend, []))

    assert len(daemon.create_names()) == 1
    [event] = stall.events
    absence = cast(dict, event["absence"])
    assert event["action"] == "abort_absence_unconfirmed"
    assert absence["confirmed"] is False and absence["stopped_by"] == "bound"
    assert STALL_ABSENCE_CONFIRM_SECONDS <= absence["seconds"] <= STALL_ABSENCE_CONFIRM_SECONDS + 50


# 8. Failures that did not start with a timeout are never retried -------------------------


class RaisingDaemon(JournalOnlyDaemon):
    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        raise BackendError("trusted Docker broker disconnected or returned invalid data")


@pytest.mark.parametrize(
    "error",
    (
        BackendError("container runtime create failed: daemon error"),
        OutputLimitError(ContainerOutcome(0, b"", b"", 0.1, True)),
        RuntimeError("node-tar effect identity changed after setup"),
    ),
)
def test_non_stall_failures_propagate_unchanged(error) -> None:
    stall, observed = journal_recovery()

    def attempt():
        if not isinstance(error, BackendError) or isinstance(error, OutputLimitError):
            observed.run(("container", "start", "--attach", "d" * 64), TIMEOUT)
        raise error

    with pytest.raises(type(error)) as raised:
        stall.run(
            attempt, timed_out=lambda _v: False, timeout_seconds=TIMEOUT, step_index=0, case_id="c"
        )
    assert raised.value is error
    assert stall.events == []


def test_daemon_error_before_any_timeout_is_not_a_stall(world) -> None:
    clock, build = world
    daemon, backend, stall, _ = build(["normal"])
    original = daemon._create

    def failing_create(args):
        return CommandResult(1, b"", b"Error response from daemon: conflict\n")

    daemon._create = failing_create  # type: ignore[method-assign]
    with pytest.raises(BackendError, match="create failed"):
        run_case(stall, target_attempt(backend, []))
    daemon._create = original  # type: ignore[method-assign]
    assert stall.events == []


def test_broker_disconnect_is_not_a_stall() -> None:
    clock = Clock()
    observed = ObservedDockerClient(RaisingDaemon(), monotonic=clock.monotonic)
    stall = StallRecovery(observed, OWNER, emit=lambda _r: None)

    def attempt():
        observed.run(("container", "inspect", "d" * 64), TIMEOUT)

    with pytest.raises(BackendError, match="broker disconnected"):
        stall.run(
            attempt, timed_out=lambda _v: False, timeout_seconds=TIMEOUT, step_index=0, case_id="c"
        )
    assert stall.events == []
    assert observed.calls[-1].error == "BackendError"


def test_owner_mismatch_stops_absence_confirmation(world) -> None:
    clock, build = world
    daemon, backend, stall, _ = build(["foreign"])
    daemon.run(
        (
            "container",
            "create",
            "--name",
            "inodefence-" + "e" * 32,
            "--workdir",
            str(RUNTIME_BASE / "core-run-x" / "extract"),
            "--entrypoint",
            "/h",
            IMAGE,
        ),
        20,
    )

    result = confirm_absent(
        stall.client,
        ["inodefence-" + "e" * 32],
        OWNER,
        monotonic=clock.monotonic,
        realtime=clock.realtime,
        sleep=clock.advance,
    )

    assert result.confirmed is False and result.stopped_by == "non_timeout_failure"
    assert result.probes == 1
    assert "container rm" not in daemon.ops()


# 9. Determinism: same trajectory and step records with and without a stall --------------

CONFIG = EffectCampaignConfig(
    random_seed=123,
    execution_budget=12,
    search_policy=EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
    mutation_policy=MutationPolicy.M1,
)


def step_lines(steps) -> list[str]:
    reporter = EffectStepReporter()
    return [render_effect_step_line(reporter.add(step)) for step in steps]


def test_campaign_with_stalls_matches_the_campaign_without() -> None:
    baseline = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, CONFIG)
    stall, observed = journal_recovery()
    stalls: set[str] = set()

    calls = 0

    def produce(case):
        nonlocal calls
        calls += 1
        if calls % 2 == 0:  # every second case stalls once (within the campaign bound)
            stalls.add(case.case_id)
        return stall.run(
            stalling_once(observed, synthetic_effect_result(case), stalls, case.case_id),
            timed_out=lambda _value: False,
            timeout_seconds=TIMEOUT,
            step_index=0,
            case_id=case.case_id,
        )

    stalled = run_effect_campaign(minimal_seed_corpus(), produce, CONFIG)

    assert 0 < stall.reexecution_count <= MAX_INFRA_RETRIES_PER_CAMPAIGN
    assert step_lines(stalled.steps) == step_lines(baseline.steps)
    assert [step.parent_case_id for step in stalled.steps] == [
        step.parent_case_id for step in baseline.steps
    ]


# 10. No stall: identical report, steps and Docker call order -----------------------------

_TOKENS = re.compile(r"inodefence-[0-9a-f]{32}|core-run-[A-Za-z0-9_]+")


def normalized(daemon: StallDaemon) -> list[tuple[str, ...]]:
    seen: dict[str, str] = {}

    def token(match: re.Match[str]) -> str:
        return seen.setdefault(match.group(0), f"<{len(seen)}>")

    return [tuple(_TOKENS.sub(token, arg) for arg in args) for args, _ in daemon.log]


def test_no_stall_keeps_the_docker_call_sequence(world) -> None:
    _, build = world
    daemon, backend, stall, emitted = build(["normal", "normal"])
    plain = StallDaemon(Clock(), ["normal", "normal"])
    plain_backend = ContainerExecutionBackend(plain, CONTROLLER, "inodefence-runtime", OWNER)

    outcome = run_case(stall, target_attempt(backend, [], probe=True))
    expected = target_attempt(plain_backend, [], probe=True)()

    assert outcome == ContainerOutcome(0, b"out", b"err", outcome.duration_seconds, False)
    assert expected.exit_code == 0
    assert normalized(daemon) == normalized(plain)
    assert stall.events == [] and emitted == []


class _FakeTarget:
    tar_version = run_effect_demo.pinned_node_tar_version()
    node_version = "22.22.0"
    timeout_seconds = 10.0


class _FakeRun:
    def __init__(self, result) -> None:
        self.result = result
        self.controller_flush_verified = True
        self.transport_error = None
        self.raw_stream = b""


def _demo(monkeypatch, recovery: StallRecovery | None, fake_run) -> tuple[dict, list[str]]:
    monkeypatch.setattr(run_effect_demo.NodeTarEffectTarget, "bind", lambda *a, **k: _FakeTarget())
    monkeypatch.setattr(run_effect_demo, "run_node_tar_effect_case", fake_run)
    lines: list[str] = []
    report = run_effect_demo.native_demo_report(
        object(),  # type: ignore[arg-type]
        "sha256:" + "0" * 64,
        budget=6,
        step_sink=lambda record: lines.append(render_effect_step_line(record)),
        stall_recovery=recovery,
    )
    return report, lines


def _without_timing(report: dict) -> str:
    return json.dumps({k: v for k, v in report.items() if k != "timing"}, sort_keys=True)


def test_no_stall_keeps_the_report_and_steps_byte_identical(monkeypatch) -> None:
    def fake_run(case, target, **kwargs):
        return _FakeRun(synthetic_effect_result(case))

    plain_report, plain_lines = _demo(monkeypatch, None, fake_run)
    stall, _ = journal_recovery()
    report, lines = _demo(monkeypatch, stall, fake_run)

    assert lines == plain_lines
    assert _without_timing(report) == _without_timing(plain_report)
    assert "infra_reexecutions" not in report


def test_stalled_case_is_reexecuted_inside_the_demo_and_recorded(monkeypatch) -> None:
    stall, observed = journal_recovery()
    stalls: set[str] = set()

    def fake_run(case, target, **kwargs):
        return stalling_once(
            observed, _FakeRun(synthetic_effect_result(case)), stalls, "only-once"
        )()

    plain_report, plain_lines = _demo(
        monkeypatch, None, lambda case, target, **k: _FakeRun(synthetic_effect_result(case))
    )
    report, lines = _demo(monkeypatch, stall, fake_run)

    assert lines == plain_lines
    assert report["native_checks"] == plain_report["native_checks"]
    [event] = cast(list[dict], report["infra_reexecutions"])
    assert event["action"] == "reexecuted" and event["step_index"] == 0


def test_case_bound_abort_keeps_todays_reason_and_records_the_count(monkeypatch) -> None:
    def always_stalling(observed):
        def fake_run(case, target, **kwargs):
            observed.run(("container", "start", "--attach", "d" * 64), TIMEOUT)
            raise BackendError("container runtime inspect failed: timed out")

        return fake_run

    plain_stall, plain_observed = journal_recovery()
    with pytest.raises(run_effect_demo.NativeDemoAborted) as plain:
        _demo(monkeypatch, None, always_stalling(plain_observed))
    stall, observed = journal_recovery()
    with pytest.raises(run_effect_demo.NativeDemoAborted) as aborted:
        _demo(monkeypatch, stall, always_stalling(observed))

    assert aborted.value.reason == plain.value.reason
    assert aborted.value.step_index == plain.value.step_index
    stub: dict[str, object] = {"aborted": {"reason": aborted.value.reason}}
    apply_aborted_infra_reexecutions(stub, stall)
    assert cast(dict, stub["aborted"])["infra_reexecution_count"] == MAX_INFRA_RETRIES
    assert len(cast(list, stub["infra_reexecutions"])) == MAX_INFRA_RETRIES + 1
    untouched: dict[str, object] = {"aborted": {"reason": "x"}}
    apply_aborted_infra_reexecutions(untouched, plain_stall)
    apply_aborted_infra_reexecutions(untouched, None)
    assert untouched == {"aborted": {"reason": "x"}}


# 11. Records -------------------------------------------------------------------------------


def test_event_record_has_monotonic_and_realtime_stamps_and_a_stderr_line(world, capsys) -> None:
    clock, build = world
    daemon, backend, stall, _ = build(["hang:30", "normal"])
    stall.emit = StallRecovery.__dataclass_fields__["emit"].default  # the real stderr writer

    run_case(stall, target_attempt(backend, []))

    [event] = stall.events
    call = cast(dict, event["stall_call"])
    assert call["started_realtime"] == pytest.approx(call["started_monotonic"] + REALTIME_BASE)
    assert call["seconds"] == pytest.approx(TIMEOUT, abs=0.01)
    attempt = cast(dict, event["attempt"])
    assert attempt["started_realtime"] == pytest.approx(
        attempt["started_monotonic"] + REALTIME_BASE
    )
    absence = cast(dict, event["absence"])
    assert absence["started_realtime"] == pytest.approx(
        absence["started_monotonic"] + REALTIME_BASE
    )
    assert all(item["timed_out"] for item in cast(list[dict], event["anomalous_calls"]))
    [line] = [
        line for line in capsys.readouterr().err.splitlines() if line.startswith(STDERR_PREFIX)
    ]
    assert json.loads(line.removeprefix(STDERR_PREFIX + " ")) == json.loads(
        json.dumps(event, sort_keys=True)
    )


# 12. Stall in the identity-probe container -------------------------------------------------


@pytest.mark.parametrize("plan", ("hang:45", "created"))
def test_identity_probe_stall_reexecutes_the_whole_case(world, plan) -> None:
    _, build = world
    daemon, backend, stall, _ = build([plan, "normal", "normal"])
    roots: list[Path] = []

    outcome = run_case(stall, target_attempt(backend, roots, probe=True))

    assert outcome.exit_code == 0
    probe, retried_probe, target = daemon.create_names()
    assert len({probe, retried_probe, target}) == 3
    assert len(roots) == 1  # the first attempt never reached the target sandbox
    assert first_absent_answer(daemon, {probe, f"{1:064x}"}) < create_indexes(daemon)[1]
    [event] = stall.events
    assert event["action"] == "reexecuted"
    assert cast(dict, event["stall_call"])["op"] == "container start"
    assert event["timeout_reclassified"] is None  # an exception path, not a verdict


def test_target_timed_out_predicate_reads_the_execution_status() -> None:
    case = minimal_seed_corpus()[0]
    run = _FakeRun(synthetic_effect_result(case))
    assert run.result.base_result.execution.status != ExecutionStatus.TIMED_OUT
    assert run_effect_demo._target_timed_out(run) is False  # type: ignore[arg-type]
