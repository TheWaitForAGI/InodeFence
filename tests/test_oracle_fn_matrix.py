"""The generic oracle has no false negative over the executable placement matrix.

Each placement is a ground-truth boundary violation under ``fully_trusted`` and is
rejected under the hardened ``data`` filter. These tests assert the production oracle
fires the expected contract on every vulnerable row (no false negative) and stays clean
on every fixed row. The ``..`` reach lands inside the disposable sandbox temp dir, so it
never touches the host. Verdict rules are untouched (D038); this only measures coverage.

The matrix and the docker-only runtime-lane spec live in ``scripts.oracle_fn_matrix``.
"""

import pytest
from scripts.oracle_fn_matrix import (
    EXECUTABLE_CASES,
    NODE_TAR_RELEASES,
    RUNTIME_LANE_SPEC,
    FnCase,
    evaluate_executable,
)

from inodefence.model import ExecutionStatus

_IDS = [case.placement for case in EXECUTABLE_CASES]


@pytest.mark.parametrize("case", EXECUTABLE_CASES, ids=_IDS)
def test_vulnerable_policy_fires_expected_contract_no_false_negative(case: FnCase) -> None:
    verdicts, status = evaluate_executable(case, "fully_trusted")
    assert status == ExecutionStatus.SUCCESS
    assert verdicts == case.vulnerable_expected, f"false negative for {case.placement}"
    assert any(verdicts), "a ground-truth positive must trip at least one contract"


@pytest.mark.parametrize("case", EXECUTABLE_CASES, ids=_IDS)
def test_hardened_policy_rejects_and_stays_clean(case: FnCase) -> None:
    verdicts, status = evaluate_executable(case, "data")
    assert status == ExecutionStatus.REJECTED
    assert verdicts == (False, False, False)


def test_matrix_covers_the_expected_placement_mechanisms() -> None:
    placements = {case.placement for case in EXECUTABLE_CASES}
    assert placements == {
        "top-level-escape-c0",
        "top-level-hardlink-c1",
        "top-level-symlink-write-c2",
        "nested-symlink-write-c2",
        "symlinked-dir-write-c2",
    }
    # Each contract class is exercised by at least one executable row.
    fired = [case.vulnerable_expected for case in EXECUTABLE_CASES]
    assert any(e[0] for e in fired)  # C0
    assert any(e[1] for e in fired)  # C1
    assert any(e[2] for e in fired)  # C2


def test_runtime_lane_spec_is_data_only_and_well_formed() -> None:
    assert NODE_TAR_RELEASES  # a non-empty release axis for the Runtime lane
    required = {"placement", "entry", "ground_truth", "expected_contract", "reason"}
    for row in RUNTIME_LANE_SPEC:
        assert required <= set(row)
        assert "docker-only" in row["reason"]
