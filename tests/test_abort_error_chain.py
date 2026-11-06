"""An abort report keeps the first error even when a cleanup failure replaced it."""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
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
    assert chain == [{"type": "builtins.OSError", "message": "gone"}]


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
    chain = [{"type": "builtins.OSError", "message": "first"}]
    shape = {"entries": 2, "entry_types": {"regular": 2}, "content_bytes": 9}

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
