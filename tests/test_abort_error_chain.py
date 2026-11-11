"""An abort report keeps the first error even when a cleanup failure replaced it."""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from scripts import container_controller, run_effect_demo
from scripts.run_effect_demo import (
    NativeDemoAborted,
    case_shape,
    exception_chain,
    historical_demo_report,
    native_demo_report,
)

from inodefence.evaluation.abort_classification import classify_abort_reason
from inodefence.execution import container as backend_module
from inodefence.execution.base import BackendError
from inodefence.execution.docker_client import CommandResult
from inodefence.model.archive import ArchiveCase, ArchiveEntry, EntryType
from inodefence.runtime import RUNTIME_BASE
from inodefence.targets import isolated, node_tar_effect

FIRST_ERROR = "created container differs from required execution policy"


class _CleanupFailsClient:
    """`create` works; the cleanup inspect afterwards reports a daemon timeout."""

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        if args[:2] == ("container", "create"):
            return CommandResult(0, b"identity\n", b"")
        return CommandResult(1, b"", b"daemon timeout", timed_out=True)


@pytest.fixture
def overlapping_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> BaseException:
    """Run the real prepare(): the first error happens in its body, then cleanup fails too."""

    @contextmanager
    def no_runtime_directory(_path: Path):
        yield None

    def first_failure(_identity: str) -> dict[str, Any]:
        raise BackendError(FIRST_ERROR)

    monkeypatch.setattr(backend_module, "open_runtime_directory", no_runtime_directory)
    monkeypatch.setattr(backend_module, "RUNTIME_BASE", tmp_path)
    fake_backend = SimpleNamespace(
        client=_CleanupFailsClient(),
        owner="o" * 32,
        image=lambda _image: {},
        create_command=lambda _request, _name, _image: ("container", "create"),
        inspect=first_failure,
    )
    request = SimpleNamespace(run_root=tmp_path / "run", image_id="i", command=("x",))
    with pytest.raises(BackendError) as caught:
        prepare = backend_module.ContainerExecutionBackend.prepare
        with prepare(fake_backend, request):  # type: ignore[arg-type]
            pytest.fail("the body must not run")
    return caught.value


def test_real_prepare_keeps_the_first_error_on_the_chain(
    overlapping_failure: BaseException,
) -> None:
    # What the report records today names only the cleanup, and is classified as cleanup.
    assert "cleanup inspect failed" in str(overlapping_failure)
    assert classify_abort_reason(str(overlapping_failure)).value == "cleanup_inspect"
    chain = exception_chain(overlapping_failure)
    assert [item["message"] for item in chain][-1] == FIRST_ERROR
    assert "cleanup inspect failed" in str(chain[0]["message"])
    assert str(chain[0]["type"]).endswith("BackendError")


def test_single_error_chain_is_that_error() -> None:
    chain = exception_chain(OSError("gone"))
    # Never raised, so it travelled nowhere.
    assert chain == [{"type": "builtins.OSError", "message": "gone", "frames": [], "frames_cut": 0}]


# ---- which call site: the same message comes from several places --------------------------


IMAGE = "sha256:" + "0" * 64


class _ScriptedClient:
    """`container inspect` of the identity answers until the listed calls time out."""

    def __init__(self, failing: set[int], *, running_first: bool = False, stuck: bool = False):
        self.failing = failing
        self.running_first = running_first
        self.stuck = stuck
        self.inspects = 0

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        if args[:2] == ("container", "create"):
            return CommandResult(0, b"identity\n", b"")
        if args[:2] == ("container", "inspect"):
            if args[2] != "identity":
                return CommandResult(1, b"", f"Error: No such object: {args[2]}".encode())
            self.inspects += 1
            if self.inspects in self.failing:
                return CommandResult(-9, b"", b"", timed_out=True)
            running = self.running_first and self.inspects == 1
            state = {"Status": "running" if running else "exited", "Running": running, "Pid": 0}
            return CommandResult(0, json.dumps([{"State": state}]).encode(), b"")
        if args[:2] == ("container", "start"):
            return CommandResult(-9 if self.stuck else 0, b"", b"", timed_out=self.stuck)
        if args[:2] == ("container", "kill"):
            return CommandResult(1, b"", b"is not running")
        if args[:2] == ("container", "wait"):
            return CommandResult(0, b"0\n", b"")
        raise AssertionError(f"unexpected call {args}")


def _real_inspect_backend(client: _ScriptedClient) -> Any:
    backend: Any = SimpleNamespace(client=client, owner="o" * 32)
    backend.inspect = partial(backend_module.ContainerExecutionBackend.inspect, backend)
    return backend


def _failing_execute(client: _ScriptedClient) -> BaseException:
    request = SimpleNamespace(timeout_seconds=10.0)
    prepared = backend_module.PreparedContainer(
        _real_inspect_backend(client),  # type: ignore[arg-type]
        "identity",
        request,  # type: ignore[arg-type]
    )
    with pytest.raises(BackendError) as caught:
        prepared.execute()
    return caught.value


def _calls(error: BaseException) -> list[str]:
    return [str(frame["function"]) for frame in exception_chain(error)[-1]["frames"]]  # type: ignore[union-attr]


def _caller_of_inspect(error: BaseException) -> dict[str, object]:
    frames: Any = exception_chain(error)[-1]["frames"]
    assert [frame["function"] for frame in frames[-2:]] == [
        "ContainerExecutionBackend.inspect",
        "checked",
    ]
    return frames[-3]


def test_call_sites_with_the_same_message_are_told_apart() -> None:
    after_start = _failing_execute(_ScriptedClient({1}))
    after_wait = _failing_execute(_ScriptedClient({2}))
    kill_race = _failing_execute(_ScriptedClient({2}, running_first=True, stuck=True))
    errors = (after_start, after_wait, kill_race)
    # The record's reason cannot tell these three apart.
    assert {str(error) for error in errors} == {"container runtime inspect failed: "}
    callers = [_caller_of_inspect(error) for error in errors]
    assert {caller["function"] for caller in callers} == {"PreparedContainer.execute"}
    assert {caller["file"] for caller in callers} == {"inodefence/execution/container.py"}
    assert len({caller["line"] for caller in callers}) == 3


def test_failure_right_after_create_names_prepare(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @contextmanager
    def no_runtime_directory(_path: Path):
        yield None

    monkeypatch.setattr(backend_module, "open_runtime_directory", no_runtime_directory)
    backend = _real_inspect_backend(_ScriptedClient({1}))
    backend.image = lambda _image: {}
    backend.create_command = lambda _request, _name, _image: ("container", "create")
    request = SimpleNamespace(run_root=tmp_path / "run", image_id="i", command=("x",))
    with pytest.raises(BackendError) as caught:
        prepare = backend_module.ContainerExecutionBackend.prepare
        with prepare(backend, request):  # type: ignore[arg-type]
            pytest.fail("the body must not run")
    # The cleanup succeeded, so the inspect failure is the only error on the chain.
    assert len(exception_chain(caught.value)) == 1
    assert _caller_of_inspect(caught.value)["function"] == "ContainerExecutionBackend.prepare"


def _backend_preparing(client: _ScriptedClient) -> Any:
    backend = _real_inspect_backend(client)
    backend.validate_image = lambda _image: None

    @contextmanager
    def prepare(request: Any):
        yield backend_module.PreparedContainer(backend, "identity", request)

    backend.prepare = prepare
    return backend


def test_identity_container_and_target_container_are_told_apart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @contextmanager
    def sandbox():
        yield SimpleNamespace(root=RUNTIME_BASE / "core-run-identity")

    monkeypatch.setattr(isolated, "disposable_sandbox", sandbox)
    with pytest.raises(BackendError) as identity:
        isolated.identify_image(
            _backend_preparing(_ScriptedClient({1})),  # type: ignore[arg-type]
            IMAGE,
            ("probe",),
        )

    monkeypatch.setattr(node_tar_effect, "validate_run_paths", lambda *_args: None)
    archive = tmp_path / "case.tar"
    archive.write_bytes(b"")
    fake_target = SimpleNamespace(
        _verify_identity=lambda: None,
        command=lambda _archive, _root: ("run",),
        image_id=IMAGE,
        timeout_seconds=10.0,
        backend=_backend_preparing(_ScriptedClient({1})),
    )
    prepare = node_tar_effect.NodeTarEffectTarget.prepare
    with pytest.raises(BackendError) as target:
        with prepare(
            fake_target,  # type: ignore[arg-type]
            archive,
            RUNTIME_BASE / "core-run-target" / "extract",
        ) as execute:
            execute()

    assert "identify_image" in _calls(identity.value)
    assert "NodeTarEffectTarget.prepare.<locals>.execute" not in _calls(identity.value)
    assert "NodeTarEffectTarget.prepare.<locals>.execute" in _calls(target.value)
    assert "identify_image" not in _calls(target.value)


def test_first_error_keeps_its_call_site_when_cleanup_replaced_it(
    overlapping_failure: BaseException,
) -> None:
    chain: Any = exception_chain(overlapping_failure)
    assert [frame["function"] for frame in chain[-1]["frames"]][-1] == (
        "overlapping_failure.<locals>.first_failure"
    )
    replacing = [frame["function"] for frame in chain[0]["frames"]]
    assert replacing[-2:] == ["remove_owned", "checked"]


def test_frames_hold_names_and_lines_only() -> None:
    def fails(secret_argument: str) -> None:
        secret_local = "SECRET-LOCAL" + secret_argument
        raise ValueError(f"len {len(secret_local)}")

    with pytest.raises(ValueError) as caught:
        fails("SECRET-ARGUMENT")
    chain: Any = exception_chain(caught.value)
    frames = chain[0]["frames"]
    assert set(chain[0]) == {"type", "message", "frames", "frames_cut"}
    assert all(set(frame) == {"file", "line", "function"} for frame in frames)
    assert all(isinstance(frame["line"], int) for frame in frames)
    assert all(not str(frame["file"]).startswith("/") for frame in frames)
    text = json.dumps(chain)
    assert "SECRET" not in text
    assert str(Path.home()) not in text
    # The source line of the raise is not read either.
    assert "len(secret_local)" not in text
    assert frames[-1]["function"].endswith("<locals>.fails")


def test_frames_keep_the_innermost_when_too_deep() -> None:
    def deep(remaining: int) -> None:
        if remaining == 0:
            raise ValueError("bottom")
        deep(remaining - 1)

    extra = 5
    with pytest.raises(ValueError) as caught:
        # With the calling frame, the depth is the limit plus `extra`.
        deep(run_effect_demo.ERROR_CHAIN_FRAME_LIMIT + extra - 2)
    chain: Any = exception_chain(caught.value)
    assert len(chain[0]["frames"]) == run_effect_demo.ERROR_CHAIN_FRAME_LIMIT
    assert chain[0]["frames_cut"] == extra
    assert chain[0]["frames"][-1]["line"] != chain[0]["frames"][-2]["line"]


def test_exactly_the_limit_cuts_nothing() -> None:
    def deep(remaining: int) -> None:
        if remaining == 0:
            raise ValueError("bottom")
        deep(remaining - 1)

    with pytest.raises(ValueError) as caught:
        deep(run_effect_demo.ERROR_CHAIN_FRAME_LIMIT - 2)
    chain: Any = exception_chain(caught.value)
    assert len(chain[0]["frames"]) == run_effect_demo.ERROR_CHAIN_FRAME_LIMIT
    assert chain[0]["frames_cut"] == 0


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "/workspaces/InodeFence/src/inodefence/execution/container.py",
            "inodefence/execution/container.py",
        ),
        ("/workspaces/InodeFence/scripts/run_effect_demo.py", "scripts/run_effect_demo.py"),
        ("/usr/lib/python3.12/contextlib.py", "contextlib.py"),
        ("/home/someone/private/thing.py", "thing.py"),
        # The last matching directory wins, so the part before it never appears.
        ("/home/inodefence/src/inodefence/runtime.py", "inodefence/runtime.py"),
    ],
)
def test_frame_file_never_keeps_an_absolute_path(path: str, expected: str) -> None:
    assert run_effect_demo._frame_file(path) == expected


def test_explicit_cause_is_followed() -> None:
    try:
        try:
            raise KeyError("first")
        except KeyError as first:
            raise ValueError("second") from first
    except ValueError as error:
        chain = exception_chain(error)
    assert [item["type"] for item in chain] == ["builtins.ValueError", "builtins.KeyError"]


def test_chain_length_and_message_are_bounded() -> None:
    error: BaseException = ValueError("x" * 5000)
    for index in range(run_effect_demo.ERROR_CHAIN_LIMIT + 3):
        next_error = ValueError(str(index))
        next_error.__cause__ = error
        error = next_error
    chain = exception_chain(error)
    assert len(chain) == run_effect_demo.ERROR_CHAIN_LIMIT + 1
    assert chain[-1] == {"truncated": True}
    long_chain = exception_chain(ValueError("y" * 5000))
    assert len(str(long_chain[0]["message"])) == run_effect_demo.ERROR_CHAIN_MESSAGE_LIMIT


def test_chain_cycle_terminates() -> None:
    first = ValueError("a")
    second = ValueError("b")
    first.__cause__ = second
    second.__cause__ = first
    assert len(exception_chain(first)) == 2


@pytest.mark.parametrize("historical", [False, True])
def test_producer_records_the_chain_and_keeps_the_reason(
    monkeypatch: pytest.MonkeyPatch, overlapping_failure: BaseException, historical: bool
) -> None:
    def fake_run(_case: object, _target: object, **_kwargs: object) -> None:
        raise overlapping_failure

    class FakeTarget:
        tar_version = "7.5.2" if historical else run_effect_demo.pinned_node_tar_version()
        node_version = "22.22.0"

    monkeypatch.setattr(
        run_effect_demo.NodeTarEffectTarget, "bind", lambda *args, **kwargs: FakeTarget()
    )
    monkeypatch.setattr(run_effect_demo, "run_node_tar_effect_case", fake_run)
    monkeypatch.setattr(run_effect_demo, "historical_target_versions", lambda: {"7.5.2": "x"})
    image = "sha256:" + "0" * 64
    with pytest.raises(NativeDemoAborted) as aborted:
        if historical:
            historical_demo_report(object(), image, "7.5.2", budget=6)  # type: ignore[arg-type]
        else:
            native_demo_report(object(), image, budget=6)  # type: ignore[arg-type]
    # Reason and category are what they were before this field existed.
    assert "BackendError: container runtime cleanup inspect failed" in aborted.value.reason
    assert classify_abort_reason(aborted.value.reason).value == "cleanup_inspect"
    assert aborted.value.error_chain is not None
    assert aborted.value.error_chain[-1]["message"] == FIRST_ERROR
    assert aborted.value.case_shape is not None
    assert int(str(aborted.value.case_shape["entries"])) >= 0


def test_case_shape_counts_without_names() -> None:
    case = ArchiveCase(
        (
            ArchiveEntry("secret-dir", EntryType.DIRECTORY),
            ArchiveEntry("secret-file", EntryType.REGULAR, content=b"abc"),
            ArchiveEntry("secret-link", EntryType.HARDLINK, link_target="secret-target"),
        )
    )
    shape = case_shape(case)
    assert shape == {
        "entries": 3,
        "entry_types": {"directory": 1, "hardlink": 1, "regular": 1},
        "content_bytes": 3,
    }
    assert "secret" not in json.dumps(shape)


@pytest.mark.parametrize("historical", [False, True])
def test_controller_writes_the_chain_into_the_abort_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, historical: bool
) -> None:
    chain: list[dict[str, object]] = [{"type": "builtins.OSError", "message": "first"}]
    shape: dict[str, object] = {"entries": 2, "entry_types": {"regular": 2}, "content_bytes": 9}

    def fake_report(*_args: object, **_kwargs: object) -> None:
        raise NativeDemoAborted(
            3, "case", "builtins.OSError: first", error_chain=chain, case_shape=shape
        )

    evidence = tmp_path / "demo.json"
    if historical:
        monkeypatch.setattr(container_controller, "historical_demo_report", fake_report)
        monkeypatch.setattr(container_controller, "sentinel_set_from_args", lambda _args: None)
        args = argparse.Namespace(
            seed=None, budget=None, policy=None, mutation_policy=None, tar_version="7.5.2"
        )
        code = container_controller.run_native_historical_demo(
            object(),  # type: ignore[arg-type]
            "img",
            evidence,
            args,
        )
    else:
        monkeypatch.setattr(container_controller, "native_demo_report", fake_report)
        args = argparse.Namespace(seed=None, budget=None, policy=None, mutation_policy=None)
        code = container_controller.run_native_effect_demo(
            object(),  # type: ignore[arg-type]
            "img",
            evidence,
            args,
        )
    assert code == 1
    aborted = json.loads(evidence.read_text(encoding="ascii"))["aborted"]
    assert aborted["error_chain"] == chain
    assert aborted["case_shape"] == shape
    assert aborted["reason"] == "builtins.OSError: first"
    assert aborted["category"] == "other"
