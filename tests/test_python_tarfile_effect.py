"""The in-process Python-tarfile effect producer reproduces the M4.1b C1/C2 control.

Same generic C0/C1/C2 Oracle, unchanged, judged through the effect-campaign producer
path (not node-tar): ``fully_trusted`` aliases the external sentinel (C1+C2), the
hardened ``data`` filter rejects it. The producer also emits a valid, integrity-valid
effect trace marked ``mechanism = "python-tarfile-inprocess"``.
"""

import tarfile

import pytest
from scripts.oracle_fixture_check import ORACLE_FIXTURES

from inodefence.effect_demo import effect_campaign_report
from inodefence.evaluation.rds import RdsArm, RdsCellConfig, run_rds_cell
from inodefence.evaluation.rds_report import summarize_report_records
from inodefence.generator import minimal_seed_corpus
from inodefence.model import EffectStreamCompleteness, EffectTargetTermination, ExecutionStatus
from inodefence.targets.python_tarfile_effect import (
    PYTHON_TARFILE_MECHANISM,
    PythonTarfileEffectTarget,
    python_tarfile_lock,
    run_python_tarfile_effect_case,
)

_FIX = {fixture.name: fixture for fixture in ORACLE_FIXTURES}


def test_data_filter_is_available() -> None:
    # PEP 706: the hardened filter the control depends on.
    assert hasattr(tarfile, "FilterError")


def test_fully_trusted_producer_reproduces_c1_and_c2() -> None:
    run = run_python_tarfile_effect_case(
        _FIX["c1"].case, PythonTarfileEffectTarget("fully_trusted"), trusted_fixture=True
    )
    base = run.result.base_result
    assert base.execution.status == ExecutionStatus.SUCCESS
    assert "node" not in base.execution.target_id
    c0, c1, c2 = base.violations
    assert not c0.violated
    assert c1.violated and c2.violated
    # the trace is a complete, integrity-valid, feedback-eligible observation
    trace = run.result.trace
    assert trace.integrity_valid
    assert trace.completeness == EffectStreamCompleteness.COMPLETE
    assert trace.termination == EffectTargetTermination.SUCCESS
    assert run.mechanism == PYTHON_TARFILE_MECHANISM
    assert trace.provenance.sources[0].mechanism == PYTHON_TARFILE_MECHANISM
    # lifecycle covers every declared entry (READ + EFFECT_WORK_STARTED)
    assert len(trace.lifecycle_events) == 2 * len(trace.archive_entries)
    assert trace.effect_events  # at least the aliasing creation observed


def test_data_filter_rejects_the_boundary_violation() -> None:
    run = run_python_tarfile_effect_case(_FIX["c1"].case, PythonTarfileEffectTarget("data"))
    base = run.result.base_result
    assert base.execution.status == ExecutionStatus.REJECTED
    c0, c1, c2 = base.violations
    assert not c1.violated and not c2.violated
    # a clean rejection is a complete observation, but never feedback-eligible
    trace = run.result.trace
    assert trace.termination == EffectTargetTermination.REJECTED


def test_baseline_fixture_has_no_violation_and_valid_trace() -> None:
    run = run_python_tarfile_effect_case(
        _FIX["normal"].case, PythonTarfileEffectTarget("fully_trusted"), trusted_fixture=True
    )
    base = run.result.base_result
    assert base.execution.status == ExecutionStatus.SUCCESS
    assert all(not v.violated for v in base.violations)
    assert run.result.trace.integrity_valid


def test_lock_material_is_reproducible_and_wellformed() -> None:
    lock = PythonTarfileEffectTarget().lock
    assert lock.python_version and "Python" in lock.python_version
    assert len(lock.tarfile_sha256) == 64 and int(lock.tarfile_sha256, 16) >= 0
    assert lock.uname_sr and " " in lock.uname_sr
    assert lock == python_tarfile_lock()  # stable within a run


def test_policy_is_validated() -> None:
    with pytest.raises(ValueError):
        PythonTarfileEffectTarget("unknown")


def test_fully_trusted_fuzzing_input_is_rejected_fail_closed() -> None:
    # Safety boundary: fully_trusted in-process is refused for any input not explicitly
    # declared a trusted bounded fixture, so a fuzzing driver (which never sets the flag)
    # cannot escape the sandbox to the host. Only the controlled fixtures opt in.
    with pytest.raises(ValueError, match="trusted_fixture"):
        run_python_tarfile_effect_case(_FIX["c1"].case, PythonTarfileEffectTarget("fully_trusted"))


def test_report_records_pass_summarize_report_records() -> None:
    # The producer's report step records share node-tar's schema, so the RDS record
    # summary (and thus the #240 memory==report parity it feeds) applies to the python
    # target too. Fuzzed cases run under the hardened ``data`` filter, which confines
    # extraction to ``extract/`` -- ``fully_trusted`` must not fuzz in-process.
    target = PythonTarfileEffectTarget("data")

    def produce(case):
        return run_python_tarfile_effect_case(case, target).result

    config = RdsCellConfig(RdsArm.S_U, 7001, 8)
    cell = run_rds_cell(minimal_seed_corpus(), produce, config)
    report = effect_campaign_report(cell.campaign, "python-tarfile")
    steps = report["steps"]
    assert isinstance(steps, list) and len(steps) == 8
    summary = summarize_report_records(steps, config)
    assert summary.summary is not None
