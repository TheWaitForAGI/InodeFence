"""#536 FAST fails closed on decompress and oras-go (W4, CI 44228097180 gap).

These two targets go through ``targets/isolated.py`` and have no per-case identity observation:
between probes only the campaign probes protect them, so their mismatch path is pinned here end
to end. An image identity that changes during a FAST campaign must give:

- a periodic probe mismatch: the campaign stops before that case's archive run;
- an end probe mismatch: every case ran, then the end probe refuses;
- either way: the controller writes an ``aborted`` loop report (no ``identity_checks``) and exits
  1; the product driver refuses it (``RuntimeError``); ``inodefence explore`` exits 2 and writes
  no ``result.json``.

The controller campaigns run for real against the targets' existing no-Docker extracting
backends (tests/test_*_effect_campaign.py); only the identity answer is made to drift.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from scripts.container_controller import (
    run_native_decompress_campaign,
    run_native_oras_go_campaign,
)
from tests import test_decompress_effect_campaign as dtest
from tests import test_oras_go_effect_campaign as otest

import inodefence.drivers.decompress.explore as dce
import inodefence.drivers.oras_go.explore as oge
import inodefence.drivers.run_target as rt
import inodefence.drivers.run_target_explore as rte

pytestmark = pytest.mark.skipif(
    not Path("/var/lib/inodefence").is_dir(),
    reason="disposable sandbox requires the Linux runtime root (Dev Container)",
)

DRIFTED_WORKER = "c" * 64


def _drifting(base: type, identity: bytes, drift_at_probe: int):
    """The target's extracting backend whose identity answer changes from probe ``drift_at_probe``
    on (1 = the bind probe), counting probes and archive runs."""

    drifted = json.dumps({**json.loads(identity), "worker_sha256": DRIFTED_WORKER}).encode()

    class Drifting(base):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__(identity)
            self.probes = 0
            self.archive_runs = 0

        @contextmanager
        def prepare(self, request):  # type: ignore[no-untyped-def]
            if "identify" in request.command:
                self.probes += 1
                self._identity = drifted if self.probes >= drift_at_probe else identity
            else:
                self.archive_runs += 1
            with super().prepare(request) as prepared:
                yield prepared

    return Drifting()


TARGETS = {
    "decompress": (
        dtest._ExtractingBackend,
        dtest._identity_bytes,
        dtest._IMAGE,
        run_native_decompress_campaign,
    ),
    "oras-go": (
        otest._ExtractingBackend,
        otest._identity_bytes,
        otest._IMAGE,
        run_native_oras_go_campaign,
    ),
}


def _campaign(name: str, tmp_path: Path, *, every: int, budget: int, drift_at_probe: int):
    base, identity, image, run = TARGETS[name]
    backend = _drifting(base, identity(), drift_at_probe)
    evidence = tmp_path / f"{name}-report.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    args = argparse.Namespace(
        seed=7, budget=budget, mutation_policy=None, policy=None, identity_check_every=every
    )
    code = run(backend, image, evidence, args)
    return code, json.loads(evidence.read_text(encoding="ascii")), backend


def _assert_aborted(code: int, report: dict[str, Any]) -> None:
    assert code == 1
    assert "identity changed" in report["aborted"]["reason"]
    assert "identity_checks" not in report and "steps" not in report


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_a_fast_campaign_without_drift_records_its_probes(name: str, tmp_path: Path) -> None:
    # The control: the same campaign with no drift finishes and records the schedule.
    code, report, backend = _campaign(name, tmp_path, every=2, budget=6, drift_at_probe=10**6)
    assert code == 0 and "aborted" not in report
    checks = report["identity_checks"]
    assert checks["interval"] == 2 and checks["total_checks"] == 1 + 3 + 1
    assert checks["per_case_identity_check"] is None  # no per-case observation on this target
    assert backend.archive_runs == 6 and backend.probes == 5


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_a_periodic_mismatch_stops_before_that_cases_archive_run(name: str, tmp_path: Path) -> None:
    # Probe 1 is the bind; with every=2 probe 2 is due before case 2's archive run.
    code, report, backend = _campaign(name, tmp_path, every=2, budget=6, drift_at_probe=2)
    _assert_aborted(code, report)
    assert backend.probes == 2
    assert backend.archive_runs == 1  # case 1 ran; case 2 never reached its archive container


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_an_end_mismatch_voids_the_finished_campaign(name: str, tmp_path: Path) -> None:
    # every=200 > budget: no periodic probe; probe 2 is the end probe after all cases ran.
    code, report, backend = _campaign(name, tmp_path, every=200, budget=4, drift_at_probe=2)
    _assert_aborted(code, report)
    assert backend.probes == 2 and backend.archive_runs == 4


DRIVERS = {
    "decompress": lambda path, runner: dce.run_controller(
        "img",
        path.parent,
        path.stem.removeprefix("inodefence-decompress-selfdiscover-"),
        seed=1,
        budget=4,
        mutation_policy=None,
        search_policy=None,
        runner=runner,
    ),  # fmt: skip
    "oras-go": lambda path, runner: oge.run_controller(
        rt.PreparedTargetImage("oras-go", "2.6.1", "2.6.1", "img", "sha256:" + "a" * 64, True),
        out=path.parent.parent,
        run_id=path.stem.removeprefix("inodefence-oras-go-selfdiscover-"),
        budget=4,
        seed=1,
        python="x",
        runner=runner,
    ),  # fmt: skip
}


def _driver_report_path(name: str, tmp_path: Path) -> Path:
    if name == "decompress":
        return dce.controller_report_path(tmp_path, "rid")
    return oge.controller_report_path(tmp_path, "rid")


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_the_driver_refuses_the_aborted_report_and_explore_exits_2(
    name: str, tmp_path: Path, monkeypatch
) -> None:
    # The controller's real aborted report (end mismatch) handed to the product driver as its
    # launcher would: exit 1 and the report on disk. The driver raises; the explore driver maps
    # that to exit 2 and no result.json is written anywhere.
    code, report, _ = _campaign(name, tmp_path / "c", every=200, budget=4, drift_at_probe=2)
    path = _driver_report_path(name, tmp_path / "out")

    def runner(cmd: Any, env: Any = None, **_: Any) -> Any:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="ascii")
        return subprocess.CompletedProcess(cmd, code)

    with pytest.raises(RuntimeError, match="controller run failed"):
        DRIVERS[name](path, runner)

    raised: list[BaseException] = []

    def explore(prepared: Any, options: rt.ExploreOptions) -> rt.ExploreOutcome:
        try:
            DRIVERS[name](path, runner)
        except BaseException as error:
            raised.append(error)
            raise
        raise AssertionError("unreachable: the driver raised")

    # The real adapter with this explore hook; its version check is not what this test is about.
    adapter = dataclasses.replace(
        rt.load_adapter(name), explore=explore, cells=lambda versions, filters: []
    )
    monkeypatch.setattr(rte, "load_adapter", lambda target: adapter)
    prepared = rt.PreparedTargetImage(name, "x", "x", "img", "sha256:" + "a" * 64, True)
    monkeypatch.setattr(rte, "prepare_target_image", lambda *a, **k: prepared)
    monkeypatch.setattr(rte, "docker_problem", lambda: None)
    argv = ["--target", name, "--version", "x", "--out", str(tmp_path / "product")]
    argv += ["--auto-prepare", "--output", "quiet", "--profile", "fast"]
    assert rte.main(argv) == 2
    # exit 2 for this reason: the driver's refusal of the failed controller run
    assert len(raised) == 1 and isinstance(raised[0], RuntimeError)
    assert "controller run failed (exit 1)" in str(raised[0])
    assert not list((tmp_path / "product").rglob("result.json"))
