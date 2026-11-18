"""#536 option 1: FAST probes image identity at start, every N cases and at the end.

STRICT (no schedule) must keep probing before every archive, unchanged. No Docker: a counting
backend answers the identity probe and records archive-run requests without executing them.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from inodefence.execution.base import BackendError, ContainerOutcome, ExecutionBackend
from inodefence.runtime import disposable_sandbox
from inodefence.targets.identity_schedule import IdentitySchedule
from inodefence.targets.node_tar_effect import NodeTarEffectTarget
from inodefence.targets.python_tarfile_contained import PythonTarfileContainedTarget

IMAGE = "sha256:" + "a" * 64
SHA = "b" * 64

NODE_TAR = {
    "node_version": "22.11.0",
    "tar_version": "7.5.23",
    "producer_sha256": SHA,
    "package_lock_sha256": SHA,
    "package_entrypoint_sha256": SHA,
    "unpack_sha256": SHA,
}
PYTHON_TARFILE = {
    "python_version": "3.12.4",
    "tarfile_sha256": SHA,
    "worker_sha256": SHA,
    "has_data_filter": True,
}


class CountingBackend(ExecutionBackend):
    """Counts identity probes vs archive runs; ``drift()`` changes what the probe reports."""

    def __init__(self, identity: dict, marker: str) -> None:
        self.identity = dict(identity)
        self.marker = marker
        self.probes = 0
        self.archive_runs = 0

    def drift(self, key: str) -> None:
        self.identity[key] = "c" * 64

    def validate_image(self, image_id: str) -> None:
        assert image_id == IMAGE

    def policy(self, image_id):  # pragma: no cover - not used here
        raise AssertionError("not used")

    def capture_isolation(self, image_id):  # pragma: no cover - not used here
        raise AssertionError("not used")

    @contextmanager
    def prepare(self, request) -> Iterator[object]:  # type: ignore[no-untyped-def]
        probe = self.marker in request.command
        if probe:
            self.probes += 1
        else:
            self.archive_runs += 1
        stdout = (json.dumps(self.identity) + "\n").encode()

        class _Prepared:
            def execute(self) -> ContainerOutcome:
                assert probe, "archive runs are prepared, never executed, in these tests"
                return ContainerOutcome(0, stdout, b"", 0.0, False)

        yield _Prepared()


@pytest.fixture
def sandbox() -> Iterator[tuple[Path, Path]]:
    """Run paths inside the runtime root, as the targets require."""
    with disposable_sandbox() as box:
        box.archive_path.write_bytes(b"x")
        yield box.archive_path, box.extraction_root


def _node_tar(schedule: IdentitySchedule | None = None):
    backend = CountingBackend(NODE_TAR, "--identify")
    target = NodeTarEffectTarget.bind(backend, IMAGE)
    return backend, replace(target, identity_schedule=schedule) if schedule else target


def _python_tarfile(schedule: IdentitySchedule | None = None):
    backend = CountingBackend(PYTHON_TARFILE, "--identify")
    target = PythonTarfileContainedTarget.bind(backend, IMAGE, "data")
    return backend, replace(target, identity_schedule=schedule) if schedule else target


TARGETS = {"node-tar": _node_tar, "python-tarfile": _python_tarfile}


def _prepare_cases(target, n: int, paths: tuple[Path, Path]) -> None:
    archive, extract = paths
    for _ in range(n):
        with target.prepare(archive, extract):
            pass


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_strict_default_probes_before_every_case_and_end_is_a_no_op(name, sandbox) -> None:
    backend, target = TARGETS[name]()
    assert target.identity_schedule is None
    _prepare_cases(target, 5, sandbox)
    assert (backend.probes, backend.archive_runs) == (1 + 5, 5)  # bind + one per case
    target.verify_identity_at_end()
    assert backend.probes == 6


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_fast_probes_at_start_every_n_and_end(name, sandbox) -> None:
    schedule = IdentitySchedule(interval=4)
    backend, target = TARGETS[name](schedule)
    start = backend.probes  # bind's probe
    _prepare_cases(target, 10, sandbox)
    assert backend.archive_runs == 10  # one archive container per case, as in STRICT
    assert backend.probes - start == 2  # cases 4 and 8
    target.verify_identity_at_end()
    assert backend.probes - start == 3
    assert schedule.record() == {
        "identity_checks": "campaign",
        "interval": 4,
        "cases_prepared": 10,
        "start_checks": 1,
        "periodic_checks": 2,
        "end_checks": 1,
        "total_checks": 4,
        "per_case_checks_skipped": 8,
    }


@pytest.mark.parametrize(
    ("name", "key"), [("node-tar", "unpack_sha256"), ("python-tarfile", "worker_sha256")]
)
def test_fast_end_mismatch_fails_closed(name, key, sandbox) -> None:
    backend, target = TARGETS[name](IdentitySchedule(interval=200))
    _prepare_cases(target, 3, sandbox)
    backend.drift(key)
    with pytest.raises((RuntimeError, ValueError)):
        target.verify_identity_at_end()
    assert target.identity_schedule.end_checked is False


@pytest.mark.parametrize(
    ("name", "key"), [("node-tar", "unpack_sha256"), ("python-tarfile", "worker_sha256")]
)
def test_fast_periodic_mismatch_stops_before_the_archive_run(name, key, sandbox) -> None:
    backend, target = TARGETS[name](IdentitySchedule(interval=2))
    archive, extract = sandbox
    with target.prepare(archive, extract):
        pass
    backend.drift(key)
    runs = backend.archive_runs
    with pytest.raises((RuntimeError, ValueError)), target.prepare(archive, extract):
        pass
    assert backend.archive_runs == runs  # the probe failed before any archive container


def test_schedule_is_not_part_of_target_identity() -> None:
    _, strict = _node_tar()
    fast = replace(strict, identity_schedule=IdentitySchedule())
    assert fast == strict and hash(fast) == hash(strict)


@pytest.mark.parametrize("interval", [0, -1, 1.5, True])
def test_interval_must_be_a_positive_int(interval) -> None:
    with pytest.raises(ValueError):
        IdentitySchedule(interval=interval)


# ---- decompress and oras-go wrap IsolatedTarget ----


def test_isolated_target_strict_and_fast_counts(sandbox, monkeypatch) -> None:
    """IsolatedTarget (decompress, oras-go): same rule through _observe_artifacts."""
    from inodefence.targets import isolated

    calls = {"n": 0}

    def observe(self):
        calls["n"] += 1
        if getattr(self, "_fail", False):
            raise BackendError("target artifact identity changed after setup")
        return ()

    monkeypatch.setattr(isolated.IsolatedTarget, "_observe_artifacts", observe)
    backend = CountingBackend({}, "identify")

    class _Invocation:
        provenance = None

    target = object.__new__(isolated.IsolatedTarget)
    object.__setattr__(target, "invocation", _Invocation())
    object.__setattr__(target, "backend", backend)
    object.__setattr__(target, "identity_schedule", None)
    archive, extract = sandbox

    def run_cases(t, n):
        for _ in range(n):
            try:
                with t.prepare(archive, extract):
                    pass
            except AttributeError:
                pass  # invocation.command is not modelled; the probe decision came first

    run_cases(target, 3)
    assert calls["n"] == 3
    target.verify_identity_at_end()
    assert calls["n"] == 3  # STRICT: no-op

    fast = object.__new__(isolated.IsolatedTarget)
    for name in ("invocation", "backend"):
        object.__setattr__(fast, name, getattr(target, name))
    schedule = IdentitySchedule(interval=2)
    object.__setattr__(fast, "identity_schedule", schedule)
    calls["n"] = 0
    run_cases(fast, 5)
    assert calls["n"] == 2  # cases 2 and 4
    fast.verify_identity_at_end()
    assert calls["n"] == 3 and schedule.end_checked


def test_helpers_leave_strict_untouched_and_report_fast(sandbox) -> None:
    from inodefence.targets.identity_schedule import (
        apply_identity_schedule,
        finish_identity_schedule,
    )

    backend, strict = _node_tar()
    same, schedule = apply_identity_schedule(strict, None)
    assert same is strict and schedule is None
    probes = backend.probes
    assert finish_identity_schedule(strict, None) == {}
    assert backend.probes == probes  # STRICT: no extra probe at the end

    fast, schedule = apply_identity_schedule(strict, 3)
    assert schedule is not None and fast.identity_schedule is schedule
    _prepare_cases(fast, 6, sandbox)
    record = finish_identity_schedule(fast, schedule)
    assert record["identity_checks"]["total_checks"] == 1 + 2 + 1
    # Skipped cases are covered by the campaign probes, never reported as observed per case;
    # node-tar names its real per-case check, the other targets have none.
    assert record["identity_checks"]["artifact_identity_basis"] == "campaign-probes"
    assert record["identity_checks"]["per_case_identity_check"] == "in-container-source-hashes"
    backend.drift("unpack_sha256")
    with pytest.raises(RuntimeError):
        finish_identity_schedule(fast, schedule)
