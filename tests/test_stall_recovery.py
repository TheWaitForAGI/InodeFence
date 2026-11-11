"""Docker infrastructure stalls re-execute a case instead of aborting or faking a timeout.

Deterministic fault injection without Docker: a scripted fake daemon drives the real
``ContainerExecutionBackend`` code path (and, for the end-to-end tests, the real
``NodeTarEffectTarget`` and ``run_node_tar_effect_case``), and a virtual clock stands in for
every wait (a timed-out call advances it by its timeout; nothing sleeps). The stall shapes
follow the HOST1 benchmark of 2026-11-07/08: Class S (one container's start never completes
and holds its lock), Class G (every call stalls for about a minute) and the 0.107 s target
whose attach timed out.
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
from inodefence.effect_demo import (
    EffectStepReporter,
    render_effect_campaign_report,
    render_effect_step_line,
)
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.abort_classification import (
    MAX_INFRA_RETRIES,
    MAX_INFRA_RETRIES_PER_CAMPAIGN,
    STALL_ABSENCE_CONFIRM_SECONDS,
    TARGET_TIMEOUT_STALL_MAX_RUNTIME_SECONDS,
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
    MAX_RECORDED_CALLS,
    STDERR_PREFIX,
    CallObservation,
    ObservedDockerClient,
    StallRecovery,
    TimeoutVerdict,
    classify_target_timeout,
    confirm_absent,
    daemon_runtime_seconds,
    is_stall_failure,
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
NEVER = "0001-01-01T00:00:00Z"
IDENTITY = {
    "node_version": "22.22.0",
    "tar_version": run_effect_demo.pinned_node_tar_version(),
    "producer_sha256": "1" * 64,
    "package_lock_sha256": "2" * 64,
    "package_entrypoint_sha256": "3" * 64,
    "unpack_sha256": "4" * 64,
}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def realtime(self) -> float:
        return REALTIME_BASE + self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def ns_of(clock_time: float) -> int:
    return round((REALTIME_BASE + clock_time) * 1e9)


def rfc3339(nanoseconds: int) -> str:
    whole, fraction = divmod(nanoseconds, 1_000_000_000)
    return datetime.fromtimestamp(whole, UTC).strftime("%Y-%m-%dT%H:%M:%S") + f".{fraction:09d}Z"


class StallDaemon:
    """Scripted daemon. ``plans`` gives each created container's start behavior, in order.

    Plans: ``normal`` (runs 0.1 s); ``hang:<s>`` (Class S: start never completes, every call
    on the container times out for <s> seconds after the start deadline); ``created``
    (start times out, container stays created, inspect works); ``exited:<s>`` (the target
    exits on its own after <s> daemon seconds, possibly negative, but the attach times
    out); ``exited_missing`` / ``exited_garbage`` (same, with absent or unparsable
    timestamps); ``genuine`` (target runs until killed); ``late:<s>`` (start overhead <s>,
    then runs until killed); ``global:<s>`` (normal start, then every daemon call times out
    for <s> seconds, Class G); ``foreign`` (owned by another invocation); ``hangbad:<s>``
    (like ``hang``, then inspect by name answers malformed JSON).

    A started command containing ``--identify`` prints the node-tar identity JSON; other
    targets exit with ``target_exit`` and print ``b"out"``.
    """

    def __init__(self, clock: Clock, plans: list[str] | None = None, target_exit: int = 0):
        self.clock = clock
        self.plans = list(plans or [])
        self.target_exit = target_exit
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
        return self.containers.get(self.names.get(token, token))

    def _state(self, container: dict[str, Any]) -> dict[str, object]:
        status = container["status"]
        state: dict[str, object] = {
            "Status": status,
            "Running": status == "running",
            "Pid": 42 if status == "running" else 0,
            "StartedAt": NEVER
            if container["started_ns"] is None
            else rfc3339(container["started_ns"]),
            "FinishedAt": NEVER
            if container["finished_ns"] is None
            else rfc3339(container["finished_ns"]),
        }
        if container["plan"] == "exited_missing":
            del state["StartedAt"], state["FinishedAt"]
        if container["plan"] == "exited_garbage":
            state["StartedAt"] = "yesterday"
        return state

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
            if container["plan"].startswith("hangbad") and token == container["name"]:
                return CommandResult(0, b"not json", b"")
            info = dict(container["info"])
            info["State"] = self._state(container)
            return CommandResult(0, json.dumps([info]).encode(), b"")
        if args[:2] == ("container", "start"):
            return self._start(container, timeout)
        if args[:2] == ("container", "kill"):
            if container["status"] != "running":
                return CommandResult(1, b"", b"Error: container is not running\n")
            container["status"] = "exited"
            container["finished_ns"] = ns_of(self.clock.now)
            return CommandResult(0, b"", b"")
        if args[:2] == ("container", "wait"):
            return CommandResult(0, f"{container['exit_code']}\n".encode(), b"")
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
        command = list(args[args.index(IMAGE) + 1 :])
        plan = self.plans.pop(0) if self.plans else "normal"
        owner = "f" * 32 if plan == "foreign" else OWNER
        info = {
            "Id": identity,
            "Image": IMAGE,
            "Config": {
                "Labels": {OWNER_LABEL: owner},
                "User": "1000:1000",
                "Entrypoint": [args[args.index("--entrypoint") + 1]],
                "Cmd": command or None,
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
        identify = "--identify" in command
        self.containers[identity] = {
            "id": identity,
            "name": name,
            "plan": plan,
            "info": info,
            "status": "created",
            "started_ns": None,
            "finished_ns": None,
            "locked_until": -1.0,
            "exit_code": 0 if identify else self.target_exit,
            "stdout": (json.dumps(IDENTITY) + "\n").encode() if identify else b"out",
        }
        self.names[name] = identity
        return CommandResult(0, identity.encode(), b"")

    def _exit_on_own(self, container: dict[str, Any], seconds: float) -> None:
        container["started_ns"] = ns_of(self.clock.now + 0.02)
        container["finished_ns"] = container["started_ns"] + round(seconds * 1e9)
        container["status"] = "exited"

    def _start(self, container: dict[str, Any], timeout: float) -> CommandResult:
        plan, _, argument = container["plan"].partition(":")
        if plan in ("normal", "foreign", "global"):
            self._exit_on_own(container, 0.1)
            self.clock.advance(0.2)
            if plan == "global":
                self.global_until = self.clock.now + float(argument)
            return CommandResult(container["exit_code"], container["stdout"], b"err")
        if plan in ("hang", "hangbad"):
            result = self._timeout(timeout)
            container["locked_until"] = self.clock.now + float(argument)
            return result
        if plan == "created":
            return self._timeout(timeout)
        if plan in ("exited", "exited_missing", "exited_garbage"):
            self._exit_on_own(container, float(argument) if argument else 0.107)
            return self._timeout(timeout)
        if plan in ("genuine", "late"):
            container["started_ns"] = ns_of(
                self.clock.now + (float(argument) if argument else 0.02)
            )
            container["status"] = "running"
            return self._timeout(timeout)
        raise AssertionError(f"unknown plan {plan}")

    # Helpers for assertions -------------------------------------------------------------

    def ops(self) -> list[str]:
        return [" ".join(args[:2]) for args, _ in self.log]

    def create_names(self) -> list[str]:
        return [args[args.index("--name") + 1] for args, _ in self.log if args[1] == "create"]


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setattr("inodefence.execution.container.os.getuid", lambda: 1000)
    monkeypatch.setattr("inodefence.execution.container.os.getgid", lambda: 1000)
    monkeypatch.setattr("socket.gethostname", lambda: CONTROLLER[:12])


@pytest.fixture
def world(host):
    clock = Clock()

    def build(plans: list[str] | None = None, target_exit: int = 0, **recovery: Any):
        daemon = StallDaemon(clock, plans, target_exit)
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


def plain_backend(plans: list[str] | None = None, target_exit: int = 0):
    daemon = StallDaemon(Clock(), plans, target_exit)
    return daemon, ContainerExecutionBackend(daemon, CONTROLLER, "inodefence-runtime", OWNER)


def target_attempt(backend, roots: list[Path], *, probe: bool = False):
    """One case attempt shaped like run_node_tar_effect_case: [probe container,] target."""

    def attempt() -> ContainerOutcome:
        if probe:
            identify_image(backend, IMAGE, ("/identify", "--identify"))
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
        step_index=3,
        case_id="case-3",
    )


def base_failure(plans: list[str], *, probe: bool = False) -> BaseException:
    """The exception the same stall raises on the base path (no stall recovery).

    Tests compare against this instead of spelling the backend's message, so they hold
    whatever wording and cleanup retry behavior the protected backend currently has.
    Needs the ``host`` fixture (directly or through ``world``).
    """
    _, backend = plain_backend(plans)
    with pytest.raises(Exception) as raised:
        target_attempt(backend, [], probe=probe)()
    return raised.value


def assert_same_failure(actual: BaseException, expected: BaseException) -> None:
    assert type(actual) is type(expected)
    assert str(actual) == str(expected)
    assert type(actual.__context__) is type(expected.__context__)
    assert str(actual.__context__) == str(expected.__context__)


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


_TOKENS = re.compile(r"inodefence-[0-9a-f]{32}|core-run-[A-Za-z0-9_]+")


def normalize(values: list[str]) -> list[str]:
    """Replace random container names and run roots by their order of appearance."""
    seen: dict[str, str] = {}

    def token(match: re.Match[str]) -> str:
        return seen.setdefault(match.group(0), f"<{len(seen)}>")

    return [_TOKENS.sub(token, value) for value in values]


def calls_of(daemon: StallDaemon) -> list[str]:
    return normalize(["\0".join(args) for args, _ in daemon.log])


# 1. Class S --------------------------------------------------------------------------------


@pytest.mark.parametrize("hang", (60.0, 140.0))
def test_class_s_start_hang_reexecutes_in_a_new_container_after_absence(world, hang) -> None:
    _, build = world
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
    assert daemon.ops().count("container start") == 2  # once per container
    [event] = stall.events
    assert event["action"] == "reexecuted"
    base = base_failure([f"hang:{hang}"])
    assert (
        event["invalid_reason"]
        == classify_abort_reason(f"{type(base).__module__}.{type(base).__qualname__}: {base}").value
    )
    assert cast(dict, event["stall_call"])["op"] == "container start"
    assert cast(dict, event["absence"])["confirmed"] is True
    assert cast(dict, event["absence"])["seconds"] <= STALL_ABSENCE_CONFIRM_SECONDS + 50
    assert event["anomalous_calls_dropped"] == 0
    assert emitted == stall.events
    assert stall.reexecution_count == 1


# 2-4. TIMED_OUT outcomes: reclassified only on positive stall evidence ---------------------


@pytest.mark.parametrize(
    ("plan", "verdict"),
    (
        ("created", TimeoutVerdict.START_NOT_COMPLETED),
        ("exited:0.107", TimeoutVerdict.ATTACH_NOT_RETURNED),
        ("exited:0", TimeoutVerdict.ATTACH_NOT_RETURNED),
        (f"exited:{TARGET_TIMEOUT_STALL_MAX_RUNTIME_SECONDS}", TimeoutVerdict.ATTACH_NOT_RETURNED),
    ),
)
def test_stall_states_are_reexecuted_not_recorded_as_target_timeout(world, plan, verdict) -> None:
    _, build = world
    daemon, backend, stall, _ = build([plan, "normal"])

    outcome = run_case(stall, target_attempt(backend, []))

    assert outcome.exit_code == 0
    [event] = stall.events
    assert event["timeout_reclassified"] == verdict.value
    assert event["invalid_reason"] == InvalidReason.RUNTIME_CALL.value
    assert event["action"] == "reexecuted"
    assert len(daemon.create_names()) == 2


@pytest.mark.parametrize(
    "plan",
    (
        "genuine",  # running at the deadline -> killed: no time comparison at all
        "late:3.0",  # start overhead ate part of the budget, still running -> killed
        "late:9.9",
        "exited:7.5",  # exited on its own near the deadline
        "exited:5.000000001",  # just above the stall bound
        "exited:-1.0",  # daemon clock stepped back
        "exited_missing",  # timestamps absent
        "exited_garbage",  # timestamps unparsable
    ),
)
def test_other_timeouts_stay_timed_out_with_no_extra_docker_call(world, plan) -> None:
    _, build = world
    daemon, backend, stall, _ = build([plan])
    plain, backend_without = plain_backend([plan])

    outcome = run_case(stall, target_attempt(backend, []))
    expected = target_attempt(backend_without, [])()

    assert outcome.exit_code is None and expected.exit_code is None  # TIMED_OUT, as before
    assert stall.events == []
    assert calls_of(daemon) == calls_of(plain)
    verdict, _ = classify_target_timeout(stall.client.calls)
    assert not verdict.is_stall


def test_running_target_is_a_target_timeout_without_reading_timestamps() -> None:
    def call(op, state=None, timed_out=False):
        return CallObservation(op, "d" * 64, 0, timed_out, False, 0.0, 0.0, 0.0, state=state)

    calls = [
        call("container start", timed_out=True),
        call("container inspect", {"Status": "running", "Running": True}),
        call("container kill"),
        call("container wait"),
        call("container inspect", {"Status": "exited", "StartedAt": "x", "FinishedAt": "y"}),
    ]
    assert classify_target_timeout(calls) == (TimeoutVerdict.TARGET_TIMEOUT, None)
    no_timeout = [call("container start"), *calls[1:]]
    assert classify_target_timeout(no_timeout) == (TimeoutVerdict.UNDETERMINED, None)


def test_daemon_runtime_reads_nanosecond_and_offset_timestamps() -> None:
    state = {
        "StartedAt": "2026-11-08T01:02:03.123456789Z",
        "FinishedAt": "2026-11-08T10:02:13.123456790+09:00",
    }
    assert daemon_runtime_seconds(state) == pytest.approx(10.000000001, abs=1e-9)
    assert daemon_runtime_seconds({"StartedAt": NEVER, "FinishedAt": NEVER}) is None
    assert daemon_runtime_seconds({"StartedAt": "garbage", "FinishedAt": NEVER}) is None


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


# 5. Per-case bound -------------------------------------------------------------------------


def test_case_bound_exhaustion_raises_the_backend_failure_unchanged(world) -> None:
    _, build = world
    daemon, backend, stall, _ = build(["hang:25"] * (MAX_INFRA_RETRIES + 1))

    with pytest.raises(BackendError) as raised:
        run_case(stall, target_attempt(backend, []))

    # A raised stall re-raises exactly the exception the base path raises for the same
    # stall (type, message, chained cause), i.e. what the campaign aborts with today.
    assert_same_failure(raised.value, base_failure(["hang:25"]))
    assert [event["action"] for event in stall.events] == [
        "reexecuted",
        "reexecuted",
        "abort_case_bound",
    ]
    assert stall.events[-1]["absence"] is None  # no extra Docker call before the abort
    assert len(daemon.create_names()) == MAX_INFRA_RETRIES + 1


def test_reclassified_timeout_beyond_the_bound_aborts_where_base_recorded_timed_out(
    world,
) -> None:
    """Documented difference: base would have kept TIMED_OUT; past the bound this aborts."""
    _, build = world
    _, backend, stall, _ = build(["exited:0.107"] * (MAX_INFRA_RETRIES + 1))
    _, backend_without = plain_backend(["exited:0.107"])

    assert target_attempt(backend_without, [])().exit_code is None  # base: TIMED_OUT result
    with pytest.raises(BackendError, match="start stalled") as raised:
        run_case(stall, target_attempt(backend, []))
    assert classify_abort_reason(f"x.BackendError: {raised.value}") == InvalidReason.RUNTIME_CALL
    assert stall.events[-1]["action"] == "abort_case_bound"


# 6. Per-campaign bound ---------------------------------------------------------------------


class JournalOnlyDaemon:
    """Answers routine calls; ``container start`` times out; ``create`` may fail."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fail_create = False

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        self.calls.append(args)
        if args[:2] == ("container", "start"):
            return CommandResult(-9, b"", b"", True)
        if args[:2] == ("container", "create") and self.fail_create:
            return CommandResult(1, b"", b"Error response from daemon: conflict\n")
        if (
            args[:2] == ("container", "inspect")
            and args[-1] == "flaky"
            and self.calls.count(args) == 1
        ):
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
            step_index=index,
            case_id=f"case-{index}",
        )
        assert value == index
    with pytest.raises(BackendError, match="inspect failed"):
        stall.run(
            stalling_once(observed, "late", stalls, "case-late"),
            timed_out=lambda _value: False,
            step_index=MAX_INFRA_RETRIES_PER_CAMPAIGN,
            case_id="case-late",
        )
    assert stall.reexecution_count == MAX_INFRA_RETRIES_PER_CAMPAIGN
    assert stall.events[-1]["action"] == "abort_campaign_bound"


# 7. Absence not confirmed ------------------------------------------------------------------


def test_unconfirmed_absence_aborts_without_a_second_container(world) -> None:
    _, build = world
    daemon, backend, stall, _ = build(["hang:1000", "normal"])

    with pytest.raises(BackendError) as raised:
        run_case(stall, target_attempt(backend, []))

    assert_same_failure(raised.value, base_failure(["hang:1000"]))
    assert len(daemon.create_names()) == 1
    [event] = stall.events
    absence = cast(dict, event["absence"])
    assert event["action"] == "abort_absence_unconfirmed"
    assert absence["confirmed"] is False and absence["stopped_by"] == "bound"
    assert STALL_ABSENCE_CONFIRM_SECONDS <= absence["seconds"] <= STALL_ABSENCE_CONFIRM_SECONDS + 50


def test_unexpected_exception_during_absence_keeps_the_original_failure(world) -> None:
    _, build = world
    daemon, backend, stall, _ = build(["hangbad:25"])

    with pytest.raises(BackendError) as raised:
        run_case(stall, target_attempt(backend, []))

    # The original stall failure survives the JSONDecodeError raised while confirming.
    assert_same_failure(raised.value, base_failure(["hangbad:25"]))
    [event] = stall.events
    assert event["action"] == "abort_absence_unconfirmed"
    assert cast(dict, event["absence"])["stopped_by"] == "exception:JSONDecodeError"
    assert len(daemon.create_names()) == 1


# 8. Failures that are not an unrecovered time-out are never retried ------------------------


class RaisingDaemon(JournalOnlyDaemon):
    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        raise BackendError("trusted Docker broker disconnected or returned invalid data")


@pytest.mark.parametrize(
    "error",
    (
        OutputLimitError(ContainerOutcome(0, b"", b"", 0.1, True)),
        RuntimeError("node-tar effect identity changed after setup"),
    ),
)
def test_non_backend_failures_propagate_even_after_a_timeout(error) -> None:
    stall, observed = journal_recovery()

    def attempt():
        observed.run(("container", "start", "--attach", "d" * 64), TIMEOUT)
        raise error

    with pytest.raises(type(error)) as raised:
        stall.run(attempt, timed_out=lambda _v: False, step_index=0, case_id="c")
    assert raised.value is error
    assert stall.events == []


def test_failure_after_a_recovered_timeout_is_not_a_stall() -> None:
    """F10: an H1-style recovered time-out does not turn a later daemon error into a stall."""
    stall, observed = journal_recovery()
    daemon = cast(JournalOnlyDaemon, observed._inner)

    def attempt():
        observed.run(("container", "inspect", "flaky"), TIMEOUT)  # times out
        observed.run(("container", "inspect", "flaky"), TIMEOUT)  # immediate retry succeeds
        daemon.fail_create = True
        observed.run(("container", "create", "--name", "inodefence-x", IMAGE), 20)
        raise BackendError("container runtime create failed: conflict")

    with pytest.raises(BackendError, match="create failed"):
        stall.run(attempt, timed_out=lambda _v: False, step_index=0, case_id="c")
    assert stall.events == []


def test_policy_violation_after_a_recovered_timeout_is_not_a_stall() -> None:
    calls = [
        CallObservation("container inspect", "n", -9, True, False, 0.0, 0.0, 10.0),
        CallObservation("container inspect", "n", 0, False, False, 10.0, 0.0, 0.1),
    ]
    policy = BackendError("created container differs from required execution policy")
    assert not is_stall_failure(policy, calls)
    assert is_stall_failure(policy, calls[:1])


def test_non_timeout_failure_of_the_reexecution_propagates() -> None:
    """F10: attempt 2 fails without a time-out -> raised unchanged, not retried again."""
    stall, observed = journal_recovery()
    daemon = cast(JournalOnlyDaemon, observed._inner)
    attempts = 0

    def attempt():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            observed.run(("container", "start", "--attach", "d" * 64), TIMEOUT)
            raise BackendError("container runtime inspect failed: timed out")
        daemon.fail_create = True
        observed.run(("container", "create", "--name", "inodefence-x", IMAGE), 20)
        raise BackendError("container runtime create failed: conflict")

    with pytest.raises(BackendError, match="create failed"):
        stall.run(attempt, timed_out=lambda _v: False, step_index=0, case_id="c")
    assert attempts == 2
    assert [event["action"] for event in stall.events] == ["reexecuted"]


def test_daemon_error_before_any_timeout_is_not_a_stall(world) -> None:
    _, build = world
    daemon, backend, stall, _ = build(["normal"])

    def failing_create(args):
        return CommandResult(1, b"", b"Error response from daemon: conflict\n")

    daemon._create = failing_create  # type: ignore[method-assign]
    with pytest.raises(BackendError, match="create failed"):
        run_case(stall, target_attempt(backend, []))
    assert stall.events == []


def test_broker_disconnect_is_not_a_stall() -> None:
    clock = Clock()
    observed = ObservedDockerClient(RaisingDaemon(), monotonic=clock.monotonic)
    stall = StallRecovery(observed, OWNER, emit=lambda _r: None)

    def attempt():
        observed.run(("container", "inspect", "d" * 64), TIMEOUT)

    with pytest.raises(BackendError, match="broker disconnected"):
        stall.run(attempt, timed_out=lambda _v: False, step_index=0, case_id="c")
    assert stall.events == []
    assert observed.calls[-1].error == "BackendError"


def test_owner_mismatch_stops_absence_confirmation(world) -> None:
    clock, build = world
    daemon, _, stall, _ = build(["foreign"])
    name = "inodefence-" + "e" * 32
    workdir = str(RUNTIME_BASE / "core-run-x" / "extract")
    daemon.run(
        ("container", "create", "--name", name, "--workdir", workdir, "--entrypoint", "/h", IMAGE),
        20,
    )

    result = confirm_absent(
        stall.client,
        [name],
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


def test_no_stall_keeps_the_docker_call_sequence(world) -> None:
    _, build = world
    daemon, backend, stall, emitted = build(["normal", "normal"])
    plain, backend_without = plain_backend(["normal", "normal"])

    outcome = run_case(stall, target_attempt(backend, [], probe=True))
    expected = target_attempt(backend_without, [], probe=True)()

    assert outcome == ContainerOutcome(0, b"out", b"err", outcome.duration_seconds, False)
    assert expected.exit_code == 0
    assert calls_of(daemon) == calls_of(plain)
    assert stall.events == [] and emitted == []


def real_demo(backend, recovery: StallRecovery | None) -> tuple[dict, list[str]]:
    """The real native_demo_report path: real bind and run_node_tar_effect_case, fake daemon."""
    lines: list[str] = []
    report = run_effect_demo.native_demo_report(
        backend,
        IMAGE,
        budget=4,
        step_sink=lambda record: lines.append(render_effect_step_line(record)),
        stall_recovery=recovery,
    )
    return report, lines


def comparable(report: dict) -> list[str]:
    """The rendered report without its per-run wall-clock timing."""
    return normalize(
        [render_effect_campaign_report({k: v for k, v in report.items() if k != "timing"})]
    )


def test_real_path_without_stall_is_byte_identical(world) -> None:
    """Rec. 5: no monkeypatched bind or case runner; only the daemon and the clock are fake."""
    _, build = world
    daemon, backend, stall, emitted = build(target_exit=2)
    plain, backend_without = plain_backend(target_exit=2)

    report, lines = real_demo(backend, stall)
    plain_report, plain_lines = real_demo(backend_without, None)

    assert normalize(lines) == normalize(plain_lines)
    assert comparable(report) == comparable(plain_report)
    assert calls_of(daemon) == calls_of(plain)
    assert "infra_reexecutions" not in report and "infra_reexecution_count" not in report
    assert stall.events == [] and emitted == []
    assert len(lines) == 4


def test_real_path_with_a_class_s_stall_keeps_steps_and_records_it(world) -> None:
    _, build = world
    # bind probe, then per case: probe + target; the second case's target start hangs.
    plans = ["normal", "normal", "normal", "normal", "hang:40"]
    daemon, backend, stall, _ = build(plans, target_exit=2)
    _, backend_without = plain_backend(target_exit=2)

    report, lines = real_demo(backend, stall)
    plain_report, plain_lines = real_demo(backend_without, None)

    assert normalize(lines) == normalize(plain_lines)
    assert report["native_checks"] == plain_report["native_checks"]
    assert report["infra_reexecution_count"] == 1
    [event] = cast(list[dict], report["infra_reexecutions"])
    assert event["action"] == "reexecuted" and event["step_index"] == 1
    assert set(event) >= {"case_id", "stall_call", "absence", "attempt"}
    assert "oracle" not in json.dumps(event)  # outcome-blind


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
    _, build = world
    _, backend, stall, _ = build(["hang:30", "normal"])
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


def test_anomalous_call_list_is_bounded_and_counts_what_it_dropped() -> None:
    stall, observed = journal_recovery()
    total = MAX_RECORDED_CALLS + 5
    stalls: set[str] = set()

    def attempt():
        if "once" not in stalls:
            stalls.add("once")
            for _ in range(total):
                observed.run(("container", "start", "--attach", "d" * 64), TIMEOUT)
            raise BackendError("container runtime inspect failed: timed out")
        return "ok"

    assert stall.run(attempt, timed_out=lambda _v: False, step_index=0, case_id="c") == "ok"
    [event] = stall.events
    assert len(cast(list, event["anomalous_calls"])) == MAX_RECORDED_CALLS
    assert event["anomalous_calls_dropped"] == 5


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
