"""node-tar exploration's operator overrides of the registered sandbox are recorded (QA check 42).

``DEMO_SENTINEL_SEED``, ``DEMO_SENTINEL_COUNT`` and ``DEMO_OBSERVER_INTEGRITY_POLICY`` are read
from the environment on purpose (operator overrides; default: the preregistration's values). The
values a run actually used must be on record even when no live folder (and so no live
``run_settings``) exists: the runtime session records them in every launch's ``env`` (they are in
``hooks.RECORDED_ENV``), and the runtime record is written for every exploration, STRICT included.
``result.json`` is not changed by an override, so a default run's bytes stay as they are.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import inodefence.drivers.node_tar.explore as nte
import inodefence.drivers.run_target as rt
from inodefence.drivers.runtime.hooks import RECORDED_ENV
from inodefence.drivers.runtime.session import RuntimeSession

KEYS = ("DEMO_SENTINEL_SEED", "DEMO_SENTINEL_COUNT", "DEMO_OBSERVER_INTEGRITY_POLICY")


def _prepared() -> rt.PreparedTargetImage:
    return rt.PreparedTargetImage(
        "node-tar", "7.5.23", "7.5.23", "inodefence-node-tar-registry:7.5.23",
        "sha256:" + "a" * 64, True,
    )  # fmt: skip


def _launch_env(tmp_path: Path) -> dict[str, str]:
    session = RuntimeSession(target="node-tar")  # STRICT

    def runner(cmd: Any, env: Any = None, cwd: Any = None, **_: Any) -> Any:
        report = nte.controller_report_path(tmp_path, "rid")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    nte.run_controller(
        _prepared(), out=tmp_path, run_id="rid", budget=20, seed=1, python="x",
        runner=runner, session=session,
    )  # fmt: skip
    session.finish(result_written=True)
    (launch,) = session.to_json()["launches"]
    return launch["env"]


def test_the_three_keys_are_recorded_env() -> None:
    assert set(KEYS) <= set(RECORDED_ENV)


def test_default_values_are_on_record(monkeypatch, tmp_path: Path) -> None:
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    seed, count, policy = nte.registered_sandbox_defaults()
    assert {key: _launch_env(tmp_path)[key] for key in KEYS} == dict(
        zip(KEYS, (seed, count, policy), strict=True)
    )


@pytest.mark.parametrize(
    "override",
    [
        {"DEMO_SENTINEL_COUNT": "3"},
        {"DEMO_SENTINEL_SEED": "99", "DEMO_OBSERVER_INTEGRITY_POLICY": "stop"},
    ],
)
def test_an_override_is_on_record_without_a_live_folder(
    override: dict[str, str], monkeypatch, tmp_path: Path
) -> None:
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in override.items():
        monkeypatch.setenv(key, value)
    recorded = _launch_env(tmp_path)
    assert not (tmp_path / "target-explore" / "rid" / "live").exists()
    for key, value in override.items():
        assert recorded[key] == value
