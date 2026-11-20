"""#495: a refusal before the controller exists is a setup error (exit 3) on every explore target.

The common runtime session's ``before`` check (``HealthObserver``, shipped since 0.2.0) blocks a
launch when this run's controller or volume name is already taken, or when Docker cannot say
whether it is (``health.run_resources_exist``). The block is ``LaunchBlocked`` (a ``ValueError``),
which the explore driver turns into ``TARGET-EXPLORE SETUP`` and exit 3 -- not ERROR (2). This pins
that for the real python-tarfile, decompress and oras-go hooks. Nothing is launched: the worker
checks are stubbed and a launch past the block fails the test.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import inodefence.drivers.run_target_explore as rte
from inodefence.drivers.decompress import adapter as decompress_adapter
from inodefence.drivers.oras_go import explore as oras_go_explore
from inodefence.drivers.python_tarfile import producer as python_tarfile_producer
from inodefence.drivers.run_target import PreparedTargetImage
from inodefence.drivers.runtime import diagnostics, health
from inodefence.drivers.runtime.session import RuntimeSession

IMAGE_ID = "sha256:" + "d" * 64

CASES = {
    "python-tarfile": (["--version", "3.12.16", "--extraction-filter", "data"], "3.12.16"),
    "decompress": (["--version", "@xhmikosr/decompress@11.1.4"], "@xhmikosr/decompress@11.1.4"),
    "oras-go": (["--version", "2.6.2"], "2.6.2"),
}

REASONS = {
    "taken": "container inodefence-x already exists (left by an earlier run?)",
    "unanswered": "could not tell whether container inodefence-x exists (Docker did not answer)",
}


@pytest.fixture
def no_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shipped observers on; every Docker-touching step before the launch stubbed; a launch that
    gets past the block fails the test instead of starting a launcher."""
    monkeypatch.setattr(diagnostics, "OBSERVERS", diagnostics.DEFAULT_OBSERVERS)
    monkeypatch.setattr(rte, "docker_problem", lambda: None)

    def prepare(adapter: Any, target: str, spec: str, **kwargs: Any) -> PreparedTargetImage:
        return PreparedTargetImage(target, spec, CASES[target][1], "img:test", IMAGE_ID, True)

    monkeypatch.setattr(rte, "prepare_target_image", prepare)
    monkeypatch.setattr(
        decompress_adapter.registry, "worker_check", lambda *a, **k: {"ok": True, "reason": "ok"}
    )
    monkeypatch.setattr(oras_go_explore, "verify_existing", lambda *a, **k: "frame ok")
    monkeypatch.setattr(
        python_tarfile_producer,
        "ensure_producer_image",
        lambda *a, **k: SimpleNamespace(image_ref="img:test-producer"),
    )

    def launched(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the launcher ran although the before check should have blocked it")

    monkeypatch.setattr(RuntimeSession, "_run", staticmethod(launched))


@pytest.mark.parametrize("why", sorted(REASONS))
@pytest.mark.parametrize("target", sorted(CASES))
def test_a_blocked_launch_is_a_setup_refusal_exit_3(
    target: str,
    why: str,
    no_launch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(health, "run_resources_exist", lambda c, v, **kw: REASONS[why])
    argv = [
        "--target",
        target,
        *CASES[target][0],
        "--budget",
        "20",
        "--auto-prepare",
        "--out",
        str(tmp_path / "out"),
    ]
    assert rte.main(argv) == 3
    err = capsys.readouterr().err
    assert "TARGET-EXPLORE SETUP" in err and "run-resources-exist" in err
    assert REASONS[why] in err
    assert "TARGET-EXPLORE ERROR" not in err
