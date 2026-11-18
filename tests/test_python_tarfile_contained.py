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
from scripts.oracle_fixture_check import ORACLE_FIXTURES

import inodefence.drivers.python_tarfile.producer as producer
from inodefence.effect_pipeline_python_tarfile import run_python_tarfile_contained_case
from inodefence.evaluation.execution_parity import EXCLUDED_OBJECT_FIELDS
from inodefence.evaluation.rds import RdsArm, RdsCellConfig
from inodefence.execution.base import ContainerOutcome, ExecutionBackend
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EffectStreamCompleteness,
    EffectTargetTermination,
    EntryType,
    ExecutionStatus,
)
from inodefence.python_tarfile_explore import case_record, python_tarfile_exploration_report
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
    assert report["vocabulary_mode"] == "observed-names"
    assert len(report["case_records"]) == budget == len(steps)
    assert report["undetermined_steps"] == 0 and report["all_undetermined"] is False
    for record in report["case_records"]:
        assert record["outcome"] == "judged"
        assert record["termination"] in ("success", "rejected", "failed")
    assert len(report["violation_inputs"]) == sum(
        bool(r["c0"] or r["c1"] or r["c2"]) for r in report["case_records"]
    )


def _without_raw_identity(value: object) -> object:
    """``value`` with each step's raw object identity replaced by its sharing partition.

    The fields ``execution_parity`` excludes as raw values (``EXCLUDED_OBJECT_FIELDS``: st_dev,
    st_ino, mtime_ns, ctime_ns) are dropped from every observed object; the ``(st_dev, st_ino)``
    pair is replaced by a label numbered in first-appearance order within the step, so paths that
    share one inode still share one label (the C1-relevant partition), while the raw numbers --
    which differ per filesystem -- do not enter the comparison. Everything else is compared as is.
    """
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        return [_relabel(item, {}) for item in value]
    return _relabel(value, {})


def _relabel(value: object, labels: dict[tuple[object, object], int]) -> object:
    if isinstance(value, dict):
        out = {
            key: _relabel(item, labels)
            for key, item in value.items()
            if key not in EXCLUDED_OBJECT_FIELDS
        }
        if "st_ino" in value or "st_dev" in value:
            identity = (value.get("st_dev"), value.get("st_ino"))
            out["inode_class"] = labels.setdefault(identity, len(labels))
        return out
    if isinstance(value, list):
        return [_relabel(item, labels) for item in value]
    return value


def test_fast_identity_schedule_same_steps_fewer_probes_and_recorded() -> None:
    """#536: FAST probes start/every N/end; steps and verdicts equal STRICT on the same seed."""
    budget = len(minimal_seed_corpus()) + 4
    strict_backend, fast_backend = _LocalBackend(), _LocalBackend()
    strict = python_tarfile_exploration_report(
        strict_backend, IMAGE, "data", RUNTIME, seed=7, budget=budget
    )
    fast = python_tarfile_exploration_report(
        fast_backend, IMAGE, "data", RUNTIME, seed=7, budget=budget, identity_check_every=3
    )
    assert "identity_checks" not in strict
    record = fast.pop("identity_checks")
    assert record["interval"] == 3 and record["end_checks"] == 1
    # Raw inode numbers, devices and times depend on the filesystem the local backend extracts
    # on, so they are compared as the inode-sharing partition (QA check 44 follow-up), not raw.
    for key in ("case_records", "steps", "retained_case_ids"):
        assert _without_raw_identity(fast.get(key)) == _without_raw_identity(strict.get(key))
    assert _without_raw_identity(fast["steps"]) != _without_raw_identity(fast["steps"][:-1])
    # Not vacuous: the steps carry observed objects whose identity became a partition label.
    assert "inode_class" in repr(_without_raw_identity(strict["steps"]))
    assert "st_ino" in repr(strict["steps"])

    def probes(backend: _LocalBackend) -> int:
        return sum(1 for command in backend.commands if command[3] == "--identify")

    assert probes(strict_backend) == 1 + budget
    assert probes(fast_backend) == record["total_checks"] == 1 + budget // 3 + 1


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


# ---- found in the first real run: extractor errors are outcomes, not undetermined steps ----

_DANGLING_HARDLINK = ArchiveCase(
    (
        ArchiveEntry("dir", EntryType.DIRECTORY, mode=0o755),
        ArchiveEntry("dir/link", EntryType.HARDLINK, link_target="a.txt"),
    )
)


def test_worker_reports_a_non_tarerror_exception_instead_of_crashing() -> None:
    # tarfile raises KeyError for a hard link whose target is not in the archive; the worker must
    # report it (errored member line + final line), never crash without its report.
    result = run_python_tarfile_contained_case(_DANGLING_HARDLINK, _target("data"))
    execution = result.base_result.execution
    assert execution.status is ExecutionStatus.FAILED
    members, error = parse_worker_output(execution.stdout.encode(), False)
    assert error is None
    assert [m.succeeded for m in members] == [True, False]
    assert members[1].error == "KeyError"
    assert "Traceback" not in execution.stderr


def test_a_reported_extraction_failure_keeps_its_oracle_verdict() -> None:
    result = run_python_tarfile_contained_case(_DANGLING_HARDLINK, _target("data"))
    record = case_record(0, result)
    assert (record["outcome"], record["termination"]) == ("judged", "failed")
    assert (record["c0"], record["c1"], record["c2"]) == (False, False, False)


def test_an_unreadable_report_is_still_undetermined() -> None:
    result = run_python_tarfile_contained_case(
        _FIX["normal"].case, _target("data", _LocalBackend(broken=True))
    )
    assert case_record(0, result)["outcome"] == "run_error"


def test_judgment_and_termination_are_separate_axes() -> None:
    rejected = case_record(0, run_python_tarfile_contained_case(_FIX["c1"].case, _target("data")))
    assert (rejected["outcome"], rejected["termination"]) == ("judged", "rejected")
    # Refused at the first member: no entry was observed, so the trace is not integrity-valid.
    assert rejected["observation_complete"] is False
    extracted = case_record(0, run_python_tarfile_contained_case(_FIX["normal"].case, _target()))
    assert (extracted["outcome"], extracted["termination"]) == ("judged", "success")
    assert extracted["observation_complete"] is True
    unread = case_record(
        0,
        run_python_tarfile_contained_case(
            _FIX["normal"].case, _target("data", _LocalBackend(broken=True))
        ),
    )
    assert unread["outcome"] == "run_error" and unread["observation_complete"] is False
    assert (unread["c0"], unread["c1"], unread["c2"]) == (None, None, None)


# ---- exploration record: no lost violation, no unobserved success read as clean (W1, 2026-11-16)


def test_a_violation_is_kept_even_when_the_worker_report_is_unreadable() -> None:
    # Before: report mismatch -> run_error with C0/C1/C2 None and no saved input, so a real effect
    # on disk vanished from the result (and could even end PASS under the 0.2 ceiling).
    result = run_python_tarfile_contained_case(
        _FIX["c1"].case, _target("fully_trusted", _LocalBackend(broken=True))
    )
    assert result.base_result.violations[1].violated  # the oracle saw the hardlink alias
    record = case_record(0, result)
    assert record["outcome"] == "judged" and record["c1"] is True
    assert record["observation_complete"] is False  # reads as "reproduction check needed"


def _with_trace(result, integrity_valid: bool):  # type: ignore[no-untyped-def]
    trace = type("T", (), {"integrity_valid": integrity_valid})()
    return type("R", (), {"base_result": result.base_result, "trace": trace})()


def test_success_of_a_non_empty_archive_without_an_intact_trace_is_unjudged() -> None:
    result = run_python_tarfile_contained_case(_FIX["normal"].case, _target())
    assert result.base_result.execution.status.value == "success"
    assert result.base_result.case.entries
    record = case_record(0, _with_trace(result, integrity_valid=False))  # type: ignore[arg-type]
    assert record["outcome"] == "run_error"
    assert (record["c0"], record["c1"], record["c2"]) == (None, None, None)
    assert case_record(0, result)["outcome"] == "judged"  # the intact trace stays judged


def test_empty_archive_and_rejection_stay_judged_though_their_trace_is_incomplete() -> None:
    from dataclasses import replace as dc_replace

    empty_case = dc_replace(_FIX["normal"].case, entries=())
    empty = run_python_tarfile_contained_case(empty_case, _target())
    assert empty.trace.integrity_valid is False  # incomplete by construction: no entry
    assert case_record(0, empty)["outcome"] == "judged"
    rejected = run_python_tarfile_contained_case(_FIX["c1"].case, _target("data"))
    assert rejected.trace.integrity_valid is False
    assert case_record(0, rejected)["outcome"] == "judged"


# ---- D1 regression matrix (user decision 2026-11-16, python-tarfile deviation) ----


def _real_stdouts() -> dict[str, str]:
    """Genuine worker outputs (local backend) for a success, a rejection and a reported failure."""
    return {
        "success": run_python_tarfile_contained_case(
            _FIX["normal"].case, _target()
        ).base_result.execution.stdout,
        "rejected": run_python_tarfile_contained_case(
            _FIX["c1"].case, _target("data")
        ).base_result.execution.stdout,
        "failed": run_python_tarfile_contained_case(
            _DANGLING_HARDLINK, _target("data")
        ).base_result.execution.stdout,
    }


def _fake_run(status: str, stdout: str, *, intact: bool, hit: bool, entries: bool = True):  # type: ignore[no-untyped-def]
    from inodefence.model import ExecutionStatus as ES

    class _V:
        def __init__(self, cid: str, violated: bool) -> None:
            self.contract_id = type("C", (), {"value": cid})()
            self.violated = violated

    execution = type("E", (), {"status": ES(status), "stdout": stdout})()
    case = type("K", (), {"entries": (1,) if entries else ()})()
    violations = (_V("C0", False), _V("C1", hit), _V("C2", False))
    base = type("B", (), {"execution": execution, "violations": violations, "case": case})()
    trace = type("T", (), {"integrity_valid": intact})()
    return type("R", (), {"base_result": base, "trace": trace})()


def _py_verdict(records: list[dict]) -> str:
    import base64
    from hashlib import sha256

    from inodefence.drivers.explore_result import build_campaign_result
    from inodefence.drivers.run_target import PreparedTargetImage

    tar = b"t" * 512
    inputs = [
        {
            "run_index": r["run_index"],
            "tar_b64": base64.b64encode(tar).decode(),
            "tar_sha256": sha256(tar).hexdigest(),
        }
        for r in records
        if r["c1"]
    ]
    prepared = PreparedTargetImage(
        "python-tarfile", "x", "3.12.3", "img", "sha256:" + "a" * 64, True
    )
    result, _ = build_campaign_result(
        {"case_records": records, "violation_inputs": inputs}, prepared, seed=1, budget=len(records)
    )
    return result.verdict.value


def test_d1_python_matrix() -> None:
    out = _real_stdouts()
    ok = ("success", out["success"])
    rej = ("rejected", out["rejected"])
    failed = ("failed", out["failed"])
    garbled = ("failed", "not a worker report")
    timeout = ("timed_out", out["success"])

    def records(spec):  # type: ignore[no-untyped-def]
        return [
            case_record(i, _fake_run(s, o, intact=intact, hit=hit))  # type: ignore[arg-type]
            for i, ((s, o), intact, hit) in enumerate(spec)
        ]

    clean = [(ok, True, False)]
    # Rejections (explicit refusal) and reported failures (deviation) stay judged.
    assert _py_verdict(records([(rej, False, False)] * 10)) == "PASS"
    assert _py_verdict(records([(failed, False, False)] * 10)) == "PASS"
    # Timeouts, unreadable reports, and successes with a broken trace are unjudged.
    assert _py_verdict(records([(timeout, False, False)] * 10)) == "ERROR"
    assert _py_verdict(records([(garbled, False, False)] * 10)) == "ERROR"
    assert _py_verdict(records([(ok, False, False)] * 10)) == "ERROR"
    # Observed violations are kept, whatever the exit, report or trace.
    for bad in (timeout, garbled, failed, ok):
        recs = records([(bad, False, True)] + clean * 9)
        assert recs[0]["outcome"] == "judged" and recs[0]["c1"] is True
        assert _py_verdict(recs) == "FAIL"
    # The ceiling: 2/10 unjudged passes, 3/10 is ERROR.
    assert _py_verdict(records([(timeout, False, False)] * 2 + clean * 8)) == "PASS"
    assert _py_verdict(records([(timeout, False, False)] * 3 + clean * 7)) == "ERROR"


def test_d1_python_failed_record_names_the_worker_exception() -> None:
    result = run_python_tarfile_contained_case(_DANGLING_HARDLINK, _target("data"))
    record = case_record(0, result)
    assert record["termination"] == "failed" and record["outcome"] == "judged"
    assert record["worker_error"] == "KeyError"


def test_d1_python_literal_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    # The single switch back to D1's literal wording: a reported failure becomes unjudged.
    import inodefence.python_tarfile_explore as pe

    result = run_python_tarfile_contained_case(_DANGLING_HARDLINK, _target("data"))
    assert pe.case_record(0, result)["outcome"] == "judged"
    monkeypatch.setattr(pe, "REPORTED_FAILURE_IS_JUDGED", False)
    assert pe.case_record(0, result)["outcome"] == "run_error"
