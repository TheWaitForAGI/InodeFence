"""D065 table: which targets' FAST keeps the rebuild skip only, and the marker each one gets.

The decompress/oras-go marker is byte-for-byte the 2b one. A target in the table gets the same
record with its own ``fast_acceptance``; a FAST run without an interval on a target outside the
table cannot be described and publishes no result.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import inodefence.drivers.explore_result as er
import inodefence.drivers.run_target as rt
from inodefence.drivers.runtime import policy as pol
from inodefence.target_result import (
    FAST_ACCEPTANCE_NOT_MEASURED,
    PER_CASE_IDENTITY_MARKER,
    CampaignInfo,
    ResultMode,
    TargetAxes,
    TargetResult,
    from_json_dict,
    per_case_identity_marker,
)

FAST_2B = pol.RuntimePolicy(pol.RuntimeProfile.FAST, reuse_shared_images=True)


def _result() -> TargetResult:
    return TargetResult(
        target="x",
        axes=TargetAxes(target_version="1"),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cases=(),
        repro_inputs=(),
        provenance=rt.Provenance("b" * 40, False, "img", "sha256:" + "a" * 64),
        campaign=CampaignInfo(seed=1, budget=4, runs_to_first_violation=None, runs_executed=4),
    )


def test_the_tuple_is_the_tables_keys() -> None:
    assert rt.FAST_PER_CASE_IDENTITY_TARGETS == tuple(rt.FAST_PER_CASE_IDENTITY)
    assert rt.FAST_PER_CASE_IDENTITY["decompress"] == FAST_ACCEPTANCE_NOT_MEASURED
    assert rt.FAST_PER_CASE_IDENTITY["oras-go"] == FAST_ACCEPTANCE_NOT_MEASURED


@pytest.mark.parametrize("target", ["decompress", "oras-go"])
def test_the_2b_marker_is_unchanged_for_the_two_targets(target: str) -> None:
    assert (
        per_case_identity_marker(target, FAST_ACCEPTANCE_NOT_MEASURED) == PER_CASE_IDENTITY_MARKER
    )


def test_another_state_keeps_the_rule_and_names_its_state_only() -> None:
    marker = per_case_identity_marker("t", "some_state")
    assert marker["fast_acceptance"] == "some_state" and marker["interval"] == 1
    assert marker["acceptance_evidence"] is False and "total_checks" not in marker
    assert (
        marker["basis"] == "D065: t FAST keeps reuse_shared_images only; D064 interval not applied"
    )
    data = _result().to_json_dict()
    data["campaign"]["identity_checks"] = marker
    from_json_dict(data)  # the relaxed check accepts it (acceptance_evidence false, interval 1)
    with pytest.raises(ValueError):
        per_case_identity_marker("t", "")


def test_fast_without_an_interval_outside_the_table_publishes_nothing() -> None:
    session = SimpleNamespace(target="not-in-the-table", policy=FAST_2B)
    with pytest.raises(RuntimeError, match="no D065 entry"):
        er.with_per_case_identity_marker(_result(), session)
