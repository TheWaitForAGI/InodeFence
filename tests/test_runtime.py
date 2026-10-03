from pathlib import Path

import pytest

from inodefence.runtime import SentinelSpec, disposable_sandbox, runtime_root
from inodefence.targets import PythonTarfileTarget


@pytest.mark.parametrize("configured", ["relative", "/tmp", "/var/lib/inodefence/../escape"])
def test_runtime_configuration_rejects_nonruntime_paths(
    configured: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INODEFENCE_RUNTIME_ROOT", configured)
    with pytest.raises(ValueError):
        runtime_root()


def test_runtime_configuration_rejects_symlinks(monkeypatch: pytest.MonkeyPatch) -> None:
    with disposable_sandbox() as sandbox:
        alias = sandbox.root / "alias"
        alias.symlink_to(sandbox.root / "outside", target_is_directory=True)
        monkeypatch.setenv("INODEFENCE_RUNTIME_ROOT", str(alias))
        with pytest.raises(OSError):
            runtime_root()


@pytest.mark.parametrize("name", ["../escape", "/absolute", ".", "a//b", "a\0b"])
def test_sentinel_names_are_harness_paths(name: str) -> None:
    with pytest.raises(ValueError):
        SentinelSpec(name)


def test_cleanup_does_not_follow_a_link_to_another_disposable_run() -> None:
    with disposable_sandbox() as neighbor:
        sentinel = neighbor.root / neighbor.protected_paths[0]
        original = sentinel.read_bytes()
        with disposable_sandbox() as sandbox:
            root = sandbox.root
            (sandbox.extraction_root / "neighbor").symlink_to(
                neighbor.root, target_is_directory=True
            )
        assert not root.exists()
        assert sentinel.read_bytes() == original


def test_cleanup_on_body_and_setup_failure() -> None:
    with pytest.raises(RuntimeError, match="controlled failure"), disposable_sandbox() as sandbox:
        root = sandbox.root
        raise RuntimeError("controlled failure")
    assert not root.exists()
    initial = set(runtime_root().iterdir())
    with (
        pytest.raises(OSError),
        disposable_sandbox(
            (
                SentinelSpec("parent"),
                SentinelSpec("parent/child"),
            )
        ),
    ):
        pytest.fail("setup must fail before yielding")
    assert set(runtime_root().iterdir()) == initial


def test_adapter_rejects_nonruntime_paths_without_launching() -> None:
    with pytest.raises(ValueError):
        PythonTarfileTarget().run(
            Path("/not-runtime/archive/input.tar"), Path("/not-runtime/extract")
        )


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_reference_timeout_config_validation(timeout: float) -> None:
    with pytest.raises(ValueError):
        PythonTarfileTarget(timeout)
