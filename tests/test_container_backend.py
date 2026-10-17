"""Portable transport/policy regressions; real containment is tested separately."""

import base64
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from inodefence.execution.container import (
    OWNER_LABEL,
    ContainerExecutionBackend,
    ContainerRequest,
    ResourcePolicy,
    _container_absent,
    remove_owned,
)
from inodefence.execution.docker_client import (
    OUTPUT_LIMIT,
    BackendError,
    CommandResult,
    DockerCLI,
    StdioDockerClient,
    validate_command,
    validate_host_inspection_command,
)

IMAGE = "sha256:" + "a" * 64
CONTROLLER = "b" * 64
OWNER = "c" * 32


class FakeDocker:
    def __init__(self):
        self.calls = []
        self.target = None
        self.failure = None
        self.exit_code = 4
        self.timeout = False
        self.bad_policy = False

    def run(self, args, timeout):
        self.calls.append(args)
        if args[:2] == self.failure:
            return CommandResult(1, b"", b"controlled runtime failure")
        if args[0] == "version":
            return CommandResult(
                0, b'{"Os":"linux","Version":"test","ApiVersion":"1.54","Arch":"arm64"}', b""
            )
        if args[:2] == ("image", "inspect"):
            return self.result(
                {
                    "Id": IMAGE,
                    "Os": "linux",
                    "Architecture": "arm64",
                    "Config": {"Env": ["SECRET=ignored"]},
                }
            )
        if args[:2] == ("container", "create"):
            self.name = args[args.index("--name") + 1]
            root = args[args.index("--workdir") + 1].removesuffix("/extract")
            self.target = {
                "Id": "d" * 64,
                "Image": IMAGE,
                "Config": {
                    "Labels": {OWNER_LABEL: OWNER},
                    "User": "1000:1000",
                    "Entrypoint": [args[args.index("--entrypoint") + 1]],
                    "Cmd": list(args[args.index(IMAGE) + 1 :]) or None,
                    "WorkingDir": root + "/extract",
                    "Env": [args[index + 1] for index, arg in enumerate(args) if arg == "--env"],
                },
                "State": {"Running": False, "Pid": 0, "Status": "created"},
                "HostConfig": {
                    "NetworkMode": "bridge" if self.bad_policy else "none",
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
                            "VolumeOptions": {"NoCopy": True, "Subpath": Path(root).name},
                        }
                    ],
                },
                "Mounts": [{"Destination": root}],
            }
            return CommandResult(0, ("d" * 64).encode(), b"")
        if args[:2] == ("container", "inspect"):
            if args[2] == CONTROLLER:
                return self.result(
                    {
                        "Mounts": [
                            {
                                "Type": "volume",
                                "Name": "inodefence-runtime",
                                "Destination": "/var/lib/inodefence",
                                "RW": True,
                            }
                        ],
                        "Config": {"Hostname": CONTROLLER[:12]},
                    }
                )
            if self.target is None:
                return CommandResult(1, b"", f"Error: No such object: {args[2]}\n".encode())
            return self.result(self.target)
        if args[:2] == ("container", "start"):
            assert self.target is not None
            self.target["State"] = {
                "Running": self.timeout,
                "Pid": 42 if self.timeout else 0,
                "Status": "running" if self.timeout else "exited",
            }
            return CommandResult(self.exit_code, b"out", b"err", self.timeout)
        if args[:2] == ("container", "kill"):
            assert self.target is not None
            self.target["State"] = {"Running": False, "Pid": 0, "Status": "exited"}
        elif args[:2] == ("container", "wait"):
            return CommandResult(0, str(self.exit_code).encode(), b"")
        elif args[:2] == ("container", "rm"):
            self.target = None
        return CommandResult(0, b"", b"")

    @staticmethod
    def result(value):
        return CommandResult(0, json.dumps([value]).encode(), b"")


@pytest.fixture
def fake_backend(monkeypatch):
    monkeypatch.setattr("inodefence.execution.container.os.getuid", lambda: 1000)
    monkeypatch.setattr("inodefence.execution.container.os.getgid", lambda: 1000)
    monkeypatch.setattr("socket.gethostname", lambda: CONTROLLER[:12])
    docker = FakeDocker()
    return docker, ContainerExecutionBackend(docker, CONTROLLER, "inodefence-runtime", OWNER)


@pytest.mark.parametrize(
    "field,value",
    (
        ("Entrypoint", ["/different-benign-helper"]),
        ("Cmd", ["different"]),
        ("WorkingDir", "/tmp"),
        ("Env", ["AUDIT_DOUBLE=1"]),
        ("Env", ["SECRET=ignored", "PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8"]),
        ("Env", ["SECRET=", "PATH=/usr/bin", "LANG=C.UTF-8"]),
        ("Env", ["SECRET=", "PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8", "SECRET="]),
        ("Entrypoint", ["/expected-helper", "unexpected"]),
        ("Cmd", ["unexpected", "extra"]),
        ("Env", ["SECRET=", "PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8", "SECRET=other"]),
        ("Env", {"SECRET": "", "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}),
        ("Env", ["SECRET=", "PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8", None]),
    ),
)
def test_cr002_inspected_invocation_drift_fails_before_start(fake_backend, sandbox, field, value):
    docker, backend = fake_backend
    original = docker.run

    def drift(args, timeout):
        result = original(args, timeout)
        if args[:2] == ("container", "create"):
            docker.target["Config"][field] = value
        return result

    docker.run = drift
    with pytest.raises(BackendError, match="execution policy"):
        with backend.prepare(
            ContainerRequest(IMAGE, ("/expected-helper", "expected"), sandbox.root, 5)
        ):
            raise AssertionError("drift must fail during preparation")
    assert not any(call[:2] == ("container", "start") for call in docker.calls)
    assert docker.target is None


@pytest.mark.parametrize("field", ("Entrypoint", "Cmd", "WorkingDir", "Env"))
def test_cr002_missing_inspected_invocation_fields_fail_closed(fake_backend, sandbox, field):
    docker, backend = fake_backend
    original = docker.run

    def missing(args, timeout):
        result = original(args, timeout)
        if args[:2] == ("container", "create"):
            del docker.target["Config"][field]
        return result

    docker.run = missing
    with pytest.raises(BackendError, match="execution policy"):
        with backend.prepare(ContainerRequest(IMAGE, ("/expected-helper",), sandbox.root, 5)):
            raise AssertionError("missing invocation configuration must not execute")
    assert not any(call[:2] == ("container", "start") for call in docker.calls)
    assert docker.target is None


def test_cr002_environment_order_does_not_change_the_policy(fake_backend, sandbox):
    docker, backend = fake_backend
    original = docker.run

    def reordered(args, timeout):
        result = original(args, timeout)
        if args[:2] == ("container", "create"):
            docker.target["Config"]["Env"].reverse()
        return result

    docker.run = reordered
    with backend.prepare(
        ContainerRequest(IMAGE, ("/expected-helper", "argument"), sandbox.root, 5)
    ):
        pass


@pytest.mark.parametrize("empty_cmd", (None, []))
def test_final_cr002_cleared_cmd_accepts_only_documented_empty_forms(
    fake_backend, sandbox, empty_cmd
):
    docker, backend = fake_backend
    original = docker.run

    def normalized(args, timeout):
        result = original(args, timeout)
        if args[:2] == ("container", "create"):
            docker.target["Config"]["Cmd"] = empty_cmd
        return result

    docker.run = normalized
    with backend.prepare(ContainerRequest(IMAGE, ("/expected-helper",), sandbox.root, 5)):
        pass
    assert docker.target is None


@pytest.mark.parametrize("inspection", ("image", "prepared"))
def test_final_cr001_actual_image_mismatch_prevents_start(fake_backend, sandbox, inspection):
    docker, backend = fake_backend
    original = docker.run

    def altered(args, timeout):
        result = original(args, timeout)
        if inspection == "image" and args[:2] == ("image", "inspect"):
            info = json.loads(result.stdout)[0]
            info["Id"] = "sha256:" + "e" * 64
            return docker.result(info)
        if inspection == "prepared" and args[:2] == ("container", "create"):
            docker.target["Image"] = "sha256:" + "e" * 64
        return result

    docker.run = altered
    with pytest.raises(BackendError, match="identity|execution policy"):
        with backend.prepare(ContainerRequest(IMAGE, ("/expected-helper",), sandbox.root, 5)):
            raise AssertionError("mismatched image must not execute")
    assert not any(call[:2] == ("container", "start") for call in docker.calls)
    assert docker.target is None


def test_ex003_timed_out_cli_with_exited_zero_primary_is_not_success(fake_backend, sandbox):
    docker, backend = fake_backend
    docker.exit_code = 0
    original = docker.run

    def expired_pipes(args, timeout):
        result = original(args, timeout)
        if args[:2] == ("container", "start"):
            assert docker.target["State"]["Status"] == "exited"
            return replace(result, timed_out=True)
        return result

    docker.run = expired_pipes
    with backend.prepare(
        ContainerRequest(IMAGE, ("/expected-helper",), sandbox.root, 5)
    ) as prepared:
        assert prepared.execute().exit_code is None


@pytest.mark.parametrize("field", ResourcePolicy.__dataclass_fields__)
@pytest.mark.parametrize("value", (0, -1, True, 1.5))
def test_invalid_resources_rejected(field, value):
    with pytest.raises(ValueError):
        replace(ResourcePolicy(), **{field: value})


@pytest.mark.parametrize(
    "changes",
    (
        {"image_id": "node:latest"},
        {"command": ()},
        {"command": ("node\0",)},
        {"run_root": Path("/home/user/core-run-test")},
        {"run_root": Path("/var/lib/inodefence/../core-run-test")},
        {"run_root": Path("/var/lib/inodefence")},
        {"run_root": Path("/var/lib/inodefence/sub,readonly/core-run-test")},
        {"timeout_seconds": True},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("inf")},
    ),
)
def test_invalid_execution_request_rejected(changes):
    with pytest.raises(ValueError):
        ContainerRequest(
            **(
                {
                    "image_id": IMAGE,
                    "command": ("node",),
                    "run_root": Path("/var/lib/inodefence/core-run-test"),
                    "timeout_seconds": 5,
                }
                | changes
            )
        )


def test_policy_has_no_host_exposure_or_inherited_environment(fake_backend, sandbox):
    docker, backend = fake_backend
    request = ContainerRequest(IMAGE, ("python", "/helper.py"), sandbox.root, 5)
    with backend.prepare(request) as prepared:
        command = next(call for call in docker.calls if call[:2] == ("container", "create"))
        assert "--read-only" in command
        assert command[command.index("--network") + 1] == "none"
        assert command[command.index("--cap-drop") + 1] == "ALL"
        assert "no-new-privileges=true" in command
        assert "SECRET=" in command and "SECRET=ignored" not in command
        mounts = [command[i + 1] for i, arg in enumerate(command) if arg == "--mount"]
        assert mounts == [
            f"type=volume,src=inodefence-runtime,dst={sandbox.root},volume-subpath={sandbox.root.name},volume-nocopy"
        ]
        assert not any("socket" in arg or "workspaces" in arg or "/home" in arg for arg in command)
        result = prepared.execute()
        assert result.exit_code == 4 and result.stdout == b"out" and result.stderr == b"err"
        with pytest.raises(BackendError, match="exactly once"):
            prepared.execute()
    assert docker.target is None


def test_missing_backend_fails_before_runtime(monkeypatch):
    class Missing:
        def run(self, args, timeout):
            raise BackendError("unavailable")

    with pytest.raises(BackendError, match="unavailable"):
        ContainerExecutionBackend(Missing(), CONTROLLER, "inodefence-runtime", OWNER)


def test_wrong_controller_identity_fails_before_runtime(fake_backend, monkeypatch):
    docker, _ = fake_backend
    monkeypatch.setattr("socket.gethostname", lambda: "another-controller")
    with pytest.raises(BackendError, match="controller identity"):
        ContainerExecutionBackend(docker, CONTROLLER, "inodefence-runtime", OWNER)
    assert not any(call[:2] == ("container", "create") for call in docker.calls)


@pytest.mark.parametrize(
    "failure",
    (("image", "inspect"), ("container", "create"), ("container", "start"), ("container", "rm")),
)
def test_infrastructure_errors_are_visible_and_cleanup_attempted(fake_backend, sandbox, failure):
    docker, backend = fake_backend
    docker.failure = failure
    with pytest.raises(BackendError):
        with backend.prepare(ContainerRequest(IMAGE, ("python",), sandbox.root, 5)) as prepared:
            prepared.execute()
    if failure != ("container", "rm"):
        assert docker.target is None


def test_wrong_policy_prevents_start_and_removes_container(fake_backend, sandbox):
    docker, backend = fake_backend
    docker.bad_policy = True
    with pytest.raises(BackendError, match="policy"):
        with backend.prepare(ContainerRequest(IMAGE, ("python",), sandbox.root, 5)):
            pytest.fail("wrong boundary must not be yielded")
    assert docker.target is None
    assert not any(call[:2] == ("container", "start") for call in docker.calls)


@pytest.mark.parametrize("driver, accepted", (({}, True), ({"Name": "unapproved"}, False)))
def test_only_empty_runtime_default_volume_driver_is_accepted(
    fake_backend, sandbox, driver, accepted
):
    docker, backend = fake_backend
    original = docker.run

    def configured(args, timeout):
        outcome = original(args, timeout)
        if args[:2] == ("container", "create"):
            assert docker.target is not None
            docker.target["HostConfig"]["Mounts"][0]["VolumeOptions"]["DriverConfig"] = driver
        return outcome

    docker.run = configured
    if accepted:
        with backend.prepare(ContainerRequest(IMAGE, ("python",), sandbox.root, 5)) as prepared:
            assert prepared.execute().exit_code == 4
    else:
        with pytest.raises(BackendError, match="policy"):
            with backend.prepare(ContainerRequest(IMAGE, ("python",), sandbox.root, 5)):
                pytest.fail("unapproved driver must not execute")
    assert docker.target is None


def test_timeout_stops_context_before_return(fake_backend, sandbox):
    docker, backend = fake_backend
    docker.timeout = True
    with backend.prepare(ContainerRequest(IMAGE, ("python",), sandbox.root, 5)) as prepared:
        result = prepared.execute()
        assert result.exit_code is None
        assert not docker.target["State"]["Running"]
        assert any(call[:2] == ("container", "kill") for call in docker.calls)
    assert docker.target is None


@pytest.mark.parametrize(
    "message, accepted", ((b"container is not running", True), (b"permission denied", False))
)
def test_timeout_exit_race_only_accepts_confirmed_stopped_context(
    fake_backend, sandbox, message, accepted
):
    docker, backend = fake_backend
    docker.timeout = True
    original = docker.run

    def raced(args, timeout):
        if args[:2] == ("container", "kill"):
            assert docker.target is not None
            docker.target["State"] = {"Running": False, "Pid": 0, "Status": "exited"}
            return CommandResult(1, b"", message)
        return original(args, timeout)

    docker.run = raced
    with backend.prepare(ContainerRequest(IMAGE, ("python",), sandbox.root, 5)) as prepared:
        if accepted:
            assert prepared.execute().exit_code is None
        else:
            with pytest.raises(BackendError, match="permission denied"):
                prepared.execute()
    assert docker.target is None


def test_uncertain_create_response_removes_only_own_container(fake_backend, sandbox):
    docker, backend = fake_backend
    original = docker.run

    def uncertain(args, timeout):
        outcome = original(args, timeout)
        return (
            CommandResult(1, b"", b"lost create response")
            if args[:2] == ("container", "create")
            else outcome
        )

    docker.run = uncertain
    with pytest.raises(BackendError, match="create"):
        with backend.prepare(ContainerRequest(IMAGE, ("python",), sandbox.root, 5)):
            pytest.fail("uncertain create cannot execute")
    assert docker.target is None


def test_cleanup_refuses_another_invocation(fake_backend, sandbox):
    docker, backend = fake_backend
    command = backend.create_command(
        ContainerRequest(IMAGE, ("python",), sandbox.root, 5), "owned", backend.image(IMAGE)
    )
    docker.run(command, 10)
    assert docker.target is not None
    docker.target["Config"]["Labels"][OWNER_LABEL] = "other-owner"
    with pytest.raises(BackendError, match="another invocation"):
        remove_owned(docker, "owned", OWNER)
    assert not any(call[:2] == ("container", "rm") for call in docker.calls)


def test_missing_runtime_socket_is_not_proof_of_container_absence():
    class MissingSocket:
        def run(self, args, timeout):
            return CommandResult(1, b"", b"Cannot connect: No such file or directory")

    with pytest.raises(BackendError, match="cleanup inspect"):
        remove_owned(MissingSocket(), "inodefence-owned", OWNER)


def test_runtime_missing_container_empty_array_response_is_absence():
    identity = "inodefence-owned"
    result = CommandResult(
        1, b"[]\n", f"Error response from daemon: No such container: {identity}\n".encode()
    )
    assert _container_absent(result, identity)
    assert not _container_absent(result, "another-container")


@pytest.mark.parametrize(
    "response",
    (
        "",
        "{}",
        "not JSON",
        '{"returncode":true,"stdout":"","stderr":"","timed_out":false,"truncated":false}',
    ),
)
def test_broker_malformed_response_fails_closed(response):
    with pytest.raises(BackendError):
        StdioDockerClient(io.StringIO(response), io.StringIO()).run(("version",), 1)


def test_broker_transport_preserves_undecodable_bytes():
    response = {
        "returncode": 4,
        "stdout": base64.b64encode(b"out\xff").decode(),
        "stderr": "",
        "timed_out": False,
        "truncated": True,
    }
    writer = io.StringIO()
    result = StdioDockerClient(io.StringIO(json.dumps(response)), writer).run(("version",), 1)
    assert result.stdout == b"out\xff" and result.truncated
    assert json.loads(writer.getvalue()) == {"args": ["version"], "timeout": 1}


def test_cli_drains_large_output_and_reports_truncation(tmp_path):
    executable = tmp_path / "docker"
    executable.write_text(
        "#!/usr/bin/python3\nimport os\nos.write(1,b'a'*(2*1024*1024))\n"
        "os.write(2,b'b'*(2*1024*1024))\n"
    )
    executable.chmod(0o755)
    result = DockerCLI(str(executable), "test").run(("version",), 5)
    assert result.returncode == 0 and result.truncated and not result.timed_out
    assert result.stdout == b"a" * OUTPUT_LIMIT and result.stderr == b"b" * OUTPUT_LIMIT


def test_cli_deadline_still_applies_after_pipes_close(tmp_path):
    executable = tmp_path / "docker"
    executable.write_text(
        "#!/usr/bin/python3\nimport os,time\nos.close(1); os.close(2); time.sleep(0.5)\n"
    )
    executable.chmod(0o755)
    result = DockerCLI(str(executable), "test").run(("version",), 0.05)
    assert result.timed_out and result.returncode != 0


@pytest.mark.parametrize(
    "args, timeout", (((), 1), (("exec", "sh"), 1), (("version",), 0), (("version",), float("nan")))
)
def test_broker_rejects_invalid_command(args, timeout):
    with pytest.raises(BackendError):
        validate_command(args, timeout)


def test_host_inspection_allowlist_is_separate_and_exact():
    volume_consumers = (
        "container",
        "ls",
        "--all",
        "--no-trunc",
        "--filter",
        "volume=inodefence-n04-preflight-runtime-20261016T130000Z",
        "--format",
        "{{.ID}}",
    )
    validate_host_inspection_command(("info", "--format", "{{json .}}"), 10)
    validate_host_inspection_command(volume_consumers, 10)

    for rejected in (
        ("info",),
        ("container", "ls", "--all"),
        (*volume_consumers[:5], "volume=../../host", *volume_consumers[6:]),
    ):
        with pytest.raises(BackendError, match="host-only"):
            validate_host_inspection_command(rejected, 10)
        with pytest.raises(BackendError, match="trusted Docker"):
            validate_command(rejected, 10)


def test_start_deadline_before_launch_destroys_context_before_return(fake_backend, sandbox):
    docker, backend = fake_backend
    original = docker.run

    def expired(args, timeout):
        if args[:2] == ("container", "start"):
            return CommandResult(-9, b"", b"", timed_out=True)
        return original(args, timeout)

    docker.run = expired
    with backend.prepare(ContainerRequest(IMAGE, ("python",), sandbox.root, 1e-9)) as prepared:
        result = prepared.execute()
        assert result.exit_code is None
        assert docker.target is None
        assert not any(call[:2] == ("container", "wait") for call in docker.calls)
