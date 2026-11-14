"""Contained python-tarfile effect target, case pipeline, exploration report, producer image.

No docker. ``_LocalBackend`` stands in for the trusted container backend: it runs the REAL worker
(``tools/python-tarfile/effect/worker.py``) with this interpreter on the disposable sandbox paths,
so the worker protocol, parsing, trace building and the shared effect loop are all exercised. The
only escaping input used is the committed oracle control fixture, whose escape lands on the
in-sandbox sentinel.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import scripts.python_tarfile_producer as producer
from scripts.oracle_fixture_check import ORACLE_FIXTURES

from inodefence.effect_pipeline_python_tarfile import run_python_tarfile_contained_case
from inodefence.evaluation.rds import RdsArm, RdsCellConfig
from inodefence.execution.base import ContainerOutcome, ExecutionBackend
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    EffectStreamCompleteness,
    EffectTargetTermination,
    ExecutionStatus,
)
from inodefence.python_tarfile_explore import python_tarfile_exploration_report
from inodefence.targets.python_tarfile_contained import (
    CONTAINER_MECHANISM,
    PYTHON,
    WORKER,
    PythonTarfileContainedTarget,
    parse_worker_output,
)

IMAGE = "sha256:" + "c" * 64
RUNTIME = platform.python_version()
WORKER_FILE = producer.WORKER
_FIX = {fixture.name: fixture for fixture in ORACLE_FIXTURES}


class _LocalBackend(ExecutionBackend):
    """Runs the worker argv locally; ``broken`` garbles extraction output, ``crash`` fails it."""

    def __init__(self, *, broken: bool = False, crash: bool = False) -> None:
        self.broken = broken
        self.crash = crash
        self.commands: list[tuple[str, ...]] = []

    def validate_image(self, image_id: str) -> None:
        assert image_id == IMAGE

    def policy(self, image_id):  # pragma: no cover - not used here
        raise AssertionError("not used")

    def capture_isolation(self, image_id):  # pragma: no cover - not used here
        raise AssertionError("not used")

    @contextmanager
    def prepare(self, request):  # type: ignore[no-untyped-def]
        command = request.command
        self.commands.append(command)
        assert command[:3] == (PYTHON, "-I", WORKER)
        local = [sys.executable, "-I", str(WORKER_FILE), *command[3:]]
        backend = self

        class _Run:
            def execute(self) -> ContainerOutcome:
                if command[3] == "extract" and backend.crash:
                    return ContainerOutcome(3, b"", b"boom", 0.0, False)
                done = subprocess.run(local, capture_output=True, check=False)
                garbled = command[3] == "extract" and backend.broken
                stdout = b"not json\n" if garbled else done.stdout
                return ContainerOutcome(done.returncode, stdout, done.stderr, 0.0, False)

        yield _Run()


def _target(policy: str = "data", backend: ExecutionBackend | None = None):
    return PythonTarfileContainedTarget.bind(backend or _LocalBackend(), IMAGE, policy)


# ---- worker (run here, exactly the file baked into the image) ----


def test_worker_identify_reports_runtime_module_and_itself() -> None:
    done = subprocess.run(
        [sys.executable, "-I", str(WORKER_FILE), "--identify"], capture_output=True, text=True
    )
    value = json.loads(done.stdout)
    assert value["python_version"] == RUNTIME
    assert value["worker_sha256"] == producer.worker_sha256()
    assert value["has_data_filter"] is True


def test_worker_self_test_and_usage() -> None:
    ok = subprocess.run(
        [sys.executable, "-I", str(WORKER_FILE), "--self-test"], capture_output=True
    )
    assert ok.returncode == 0 and b'"ok"' in ok.stdout
    bad = subprocess.run(
        [sys.executable, "-I", str(WORKER_FILE), "extract", "a", "b", "tar"], capture_output=True
    )
    assert bad.returncode == 4


def test_worker_output_is_parsed_strictly() -> None:
    final = {"format": "inodefence-python-tarfile-run-v1", "status": "success", "members": 1}
    line = b'{"ordinal": 0, "status": "succeeded", "error": null}\n'
    good = line + json.dumps(final).encode()
    members, error = parse_worker_output(good, False)
    assert error is None and len(members) == 1 and members[0].succeeded
    assert parse_worker_output(good, True)[1] == "worker output truncated"
    assert parse_worker_output(b"junk", False)[1] is not None
    skipped = line.replace(b'"ordinal": 0', b'"ordinal": 1') + json.dumps(final).encode()
    assert parse_worker_output(skipped, False)[1] is not None
    wrong_count = line + json.dumps({**final, "members": 2}).encode()
    assert parse_worker_output(wrong_count, False)[1] is not None


# ---- target binding ----


def test_bind_reads_identity_and_pins_one_filter() -> None:
    target = _target("data")
    assert target.python_version == RUNTIME
    assert target.worker_sha256 == producer.worker_sha256()
    assert target.policy == "data"
    with pytest.raises(ValueError, match="expected 9.9.9"):
        PythonTarfileContainedTarget.bind(_LocalBackend(), IMAGE, "data", expected_python="9.9.9")
    with pytest.raises(ValueError, match="policy"):
        PythonTarfileContainedTarget.bind(_LocalBackend(), IMAGE, "tar")
    with pytest.raises(ValueError, match="immutable image"):
        PythonTarfileContainedTarget.bind(_LocalBackend(), "python:3.14-slim", "data")


def test_command_is_the_worker_with_paths_and_filter_only(tmp_path: Path) -> None:
    archive, root = tmp_path / "a.tar", tmp_path / "extract"
    command = _target("data").command(archive, root)
    assert command == (PYTHON, "-I", WORKER, "extract", str(archive), str(root), "data")


# ---- one case through the contained path (fake backend) ----


def test_benign_case_extracts_with_complete_trace() -> None:
    result = run_python_tarfile_contained_case(_FIX["normal"].case, _target("data"))
    base = result.base_result
    assert base.execution.status is ExecutionStatus.SUCCESS
    assert not any(v.violated for v in base.violations)
    assert result.trace.completeness is EffectStreamCompleteness.COMPLETE
    assert result.trace.integrity_valid
    assert result.trace.provenance.sources[0].mechanism == CONTAINER_MECHANISM


def test_data_filter_declines_the_control_fixture() -> None:
    result = run_python_tarfile_contained_case(_FIX["c1"].case, _target("data"))
    base = result.base_result
    assert base.execution.status is ExecutionStatus.REJECTED
    assert not any(v.violated for v in base.violations)
    assert result.trace.termination is EffectTargetTermination.REJECTED


def test_fully_trusted_control_fixture_is_seen_by_the_unchanged_oracle() -> None:
    result = run_python_tarfile_contained_case(_FIX["c1"].case, _target("fully_trusted"))
    _, c1, c2 = result.base_result.violations
    assert c1.violated and c2.violated
    assert result.trace.completeness is EffectStreamCompleteness.COMPLETE


def test_unreadable_worker_output_fails_closed_but_keeps_the_real_verdict() -> None:
    result = run_python_tarfile_contained_case(
        _FIX["normal"].case, _target("data", _LocalBackend(broken=True))
    )
    assert result.trace.completeness is EffectStreamCompleteness.INCOMPLETE
    assert not result.trace.lifecycle_events
    assert not any(v.violated for v in result.base_result.violations)


# ---- the shared effect loop (no python-specific loop) ----


def test_exploration_runs_the_shared_loop_on_one_runtime_and_one_filter() -> None:
    steps: list[dict[str, Any]] = []
    budget = len(minimal_seed_corpus()) + 2
    report = python_tarfile_exploration_report(
        _LocalBackend(), IMAGE, "data", RUNTIME, seed=7, budget=budget, step_sink=steps.append
    )
    assert report["runtime_version"] == RUNTIME and report["extraction_filter"] == "data"
    assert report["label"] == "exploratory demo run" and report["qualification"] is False
    # Defaults are the registered S-u arm with the observed-names vocabulary.
    s_u = RdsCellConfig(RdsArm.S_U, 7, budget)
    assert report["search_policy"] == s_u.search_policy.value
    assert report["config"]["search_policy"] == s_u.search_policy.value
    assert report["config"]["mutation_policy"] == s_u.mutation_policy.value
    assert report["vocabulary"] == "observed-names"
    assert len(report["case_records"]) == budget == len(steps)
    assert report["undetermined_steps"] == 0 and report["all_undetermined"] is False
    for record in report["case_records"]:
        assert record["outcome"] in ("extracted", "declined")
    assert len(report["violation_inputs"]) == sum(
        bool(r["c0"] or r["c1"] or r["c2"]) for r in report["case_records"]
    )


def test_all_steps_undetermined_is_flagged_not_a_pass() -> None:
    report = python_tarfile_exploration_report(
        _LocalBackend(crash=True), IMAGE, "data", RUNTIME, budget=len(minimal_seed_corpus())
    )
    assert report["all_undetermined"] is True
    assert all(r["outcome"] == "run_error" for r in report["case_records"])


def test_fully_trusted_exploration_is_held_by_default_and_runtime_must_match() -> None:
    with pytest.raises(ValueError, match="held until approved"):
        python_tarfile_exploration_report(_LocalBackend(), IMAGE, "fully_trusted", RUNTIME)
    with pytest.raises(ValueError, match="expected 0.0.1"):
        python_tarfile_exploration_report(_LocalBackend(), IMAGE, "data", "0.0.1")


# ---- producer image: build on the verified base, check offline, check before reuse ----


class _FakeDocker:
    def __init__(self, *, version: str = "3.14.10", worker: str | None = None) -> None:
        self.version = version
        self.worker = worker or producer.worker_sha256()
        self.calls: list[list[str]] = []
        self.images: dict[str, str] = {"python:3.14.10-slim": "sha256:" + "b" * 64}

    def present(self, ref: str) -> str | None:
        return self.images.get(ref)

    def __call__(self, cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        if cmd[:2] == ["docker", "build"]:
            self.images[cmd[cmd.index("-t") + 1]] = "sha256:" + "d" * 64
            return subprocess.CompletedProcess(cmd, 0, "sha256:x", "")
        if cmd[:2] == ["docker", "tag"]:
            self.images[cmd[3]] = self.images[cmd[2]]
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:2] == ["docker", "rmi"]:
            self.images.pop(cmd[-1], None)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:2] == ["docker", "run"]:
            if cmd[-1] == "--identify":
                out: dict[str, object] = {
                    "python_version": self.version,
                    "tarfile_sha256": "e" * 64,
                    "worker_sha256": self.worker,
                    "has_data_filter": True,
                }
            else:
                out = {"self_test": "ok"}
            return subprocess.CompletedProcess(cmd, 0, json.dumps(out) + "\n", "")
        raise AssertionError(cmd)


def test_producer_is_built_offline_on_the_verified_base_then_checked_then_named() -> None:
    docker = _FakeDocker()
    made = producer.ensure_producer_image(
        "python:3.14.10-slim", "3.14.10", suffix="-dev", runner=docker, present=docker.present
    )
    assert made.image_ref == "inodefence-python-tarfile-effect:3.14.10-dev"
    assert made.check == "built, checked"
    build = next(c for c in docker.calls if c[:2] == ["docker", "build"])
    assert build[build.index("--network") + 1] == "none"
    assert "BASE=python:3.14.10-slim" in build
    runs = [c for c in docker.calls if c[:2] == ["docker", "run"]]
    assert runs
    for run in runs:
        assert run[2 : 2 + len(producer.CHECK_FLAGS)] == list(producer.CHECK_FLAGS)
    assert producer.CHECK_FLAGS == (
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--user",
        "65534:65534",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=16m",
        "--entrypoint",
        "/usr/local/bin/python",
    )
    assert "inodefence-python-tarfile-effect:3.14.10-dev-unverified" not in docker.images


def test_existing_producer_is_checked_before_reuse_and_a_stale_one_is_refused() -> None:
    docker = _FakeDocker()
    docker.images["inodefence-python-tarfile-effect:3.14.10"] = "sha256:" + "f" * 64
    made = producer.ensure_producer_image(
        "python:3.14.10-slim", "3.14.10", runner=docker, present=docker.present
    )
    assert made.check == "reused, checked"
    assert not any(c[:2] == ["docker", "build"] for c in docker.calls)
    stale = _FakeDocker(worker="0" * 64)
    stale.images["inodefence-python-tarfile-effect:3.14.10"] = "sha256:" + "f" * 64
    with pytest.raises(producer.ProducerImageError, match="worker differs"):
        producer.ensure_producer_image(
            "python:3.14.10-slim", "3.14.10", runner=stale, present=stale.present
        )
    assert not any(c[:2] == ["docker", "build"] for c in stale.calls)


def test_wrong_runtime_inside_a_fresh_build_leaves_no_named_image() -> None:
    docker = _FakeDocker(version="3.14.9")
    with pytest.raises(producer.ProducerImageError, match="not 3.14.10"):
        producer.ensure_producer_image(
            "python:3.14.10-slim", "3.14.10", runner=docker, present=docker.present
        )
    assert not [ref for ref in docker.images if ref.startswith("inodefence-python-tarfile")]


def test_producer_needs_exact_version_and_a_prepared_base() -> None:
    with pytest.raises(producer.ProducerImageError, match="exact"):
        producer.producer_ref("latest")
    docker = _FakeDocker()
    with pytest.raises(producer.ProducerImageError, match="not prepared"):
        producer.ensure_producer_image(
            "python:3.13.18-slim", "3.13.18", runner=docker, present=docker.present
        )
