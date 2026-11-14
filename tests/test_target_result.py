"""inodefence-target-result-v1: shape, derived verdict, strict reader, saved-input hashes."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.target_result import (
    LABEL,
    SCHEMA,
    CampaignInfo,
    CaseVerdict,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    TargetResultError,
    Verdict,
    from_json_dict,
    load_target_result,
    repro_input,
)

TAR_A = b"tar-a"
TAR_B = b"tar-b"


def _result(*cases: CaseVerdict, observed: tuple[str, ...] = ("C1", "C2")) -> TargetResult:
    cases = cases or (
        CaseVerdict("toplevel_hardlink", "resolved", None, True, True),
        CaseVerdict("nested_hardlink", "declined", None, False, False),
    )
    return TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.2"),
        mode=ResultMode.FIXTURE_REGRESSION,
        observed_contracts=observed,
        cases=cases,
        repro_inputs=(repro_input(cases[0].case_id, f"inputs/{cases[0].case_id}.tar", TAR_A),),
        provenance=Provenance("a" * 40, False, "inodefence-node-tar-effect:7.5.2", None),
    )


def test_round_trip_and_derived_fields() -> None:
    result = _result()
    data = result.to_json_dict()
    assert data["schema"] == SCHEMA and data["label"] == LABEL
    assert data["runs"] == {"executed": 2, "errored": 0}
    assert data["verdict"] == "FAIL"
    assert data["violating_cases"] == ["toplevel_hardlink"]
    assert data["axes"] == {
        "target_version": "7.5.2",
        "runtime_version": None,
        "extraction_filter": None,
    }
    assert from_json_dict(json.loads(result.dumps())) == result


def test_verdict_rule_matches_make_regression() -> None:
    clean = CaseVerdict("a", "resolved", None, False, False)
    err = CaseVerdict("b", "run_error", None, None, None)
    hit = CaseVerdict("c", "resolved", None, True, False)
    assert _result(clean).verdict is Verdict.PASS
    assert _result(clean, hit).verdict is Verdict.FAIL
    assert _result(hit, err).verdict is Verdict.ERROR  # an error outranks a hit


def test_unobserved_contract_must_be_null_not_false() -> None:
    with pytest.raises(TargetResultError, match="C0 is set"):
        _result(CaseVerdict("a", "resolved", False, False, False))
    # The same value is fine once the mode says it observes C0.
    ok = _result(CaseVerdict("a", "resolved", False, False, False), observed=("C0", "C1", "C2"))
    assert ok.verdict is Verdict.PASS


def test_python_filter_and_runtime_axes_are_separate_fields() -> None:
    result = replace(
        _result(),
        target="python-tarfile",
        axes=TargetAxes(runtime_version="3.12.3", extraction_filter="data"),
    )
    axes = result.to_json_dict()["axes"]
    assert axes["runtime_version"] == "3.12.3" and axes["extraction_filter"] == "data"
    assert axes["target_version"] is None


@pytest.mark.parametrize(
    "path", ["/abs/x.tar", "../x.tar", "inputs/../../x.tar", "inputs\\x.tar", ""]
)
def test_repro_path_must_stay_inside(path: str) -> None:
    with pytest.raises(TargetResultError, match="tar_path"):
        replace(_result(), repro_inputs=(repro_input("toplevel_hardlink", path, TAR_A),))


def test_rejects_bad_cases_and_provenance() -> None:
    with pytest.raises(TargetResultError, match="unique"):
        _result(
            CaseVerdict("a", "resolved", None, False, False),
            CaseVerdict("a", "resolved", None, False, False),
        )
    with pytest.raises(TargetResultError, match="run error"):
        _result(CaseVerdict("a", "run_error", None, True, None))
    with pytest.raises(TargetResultError, match="true/false/null"):
        _result(CaseVerdict("a", "resolved", None, 1, False))  # type: ignore[arg-type]
    with pytest.raises(TargetResultError, match="engine_sha"):
        replace(_result(), provenance=Provenance("main", False))
    with pytest.raises(TargetResultError, match="unknown case"):
        replace(_result(), repro_inputs=(repro_input("nope", "inputs/x.tar", TAR_A),))


def test_reader_is_strict() -> None:
    good = _result().to_json_dict()
    for mutate, message in (
        (lambda d: d.update(extra=1), "unexpected"),
        (lambda d: d.update(schema="v0"), "schema"),
        (lambda d: d.update(label="experiment"), "label"),
        (lambda d: d.update(verdict="PASS"), "verdict"),
        (lambda d: d["runs"].update(executed=9), "runs"),
        (lambda d: d["axes"].pop("extraction_filter"), "missing"),
        (lambda d: d.update(mode="qualification"), "mode"),
    ):
        data = json.loads(json.dumps(good))
        mutate(data)
        with pytest.raises(TargetResultError, match=message):
            from_json_dict(data)


def test_load_rehashes_saved_inputs(tmp_path: Path) -> None:
    result = _result()
    (tmp_path / "inputs").mkdir()
    tar = tmp_path / "inputs" / "toplevel_hardlink.tar"
    tar.write_bytes(TAR_A)
    out = tmp_path / "result.json"
    out.write_text(result.dumps(), encoding="utf-8")
    assert load_target_result(out) == result
    assert result.repro_inputs[0].tar_sha256 == sha256(TAR_A).hexdigest()

    tar.write_bytes(TAR_B)
    with pytest.raises(TargetResultError, match="hash mismatch"):
        load_target_result(out)
    assert load_target_result(out, verify_inputs=False) == result
    tar.unlink()
    with pytest.raises(TargetResultError, match="missing"):
        load_target_result(out)


def _campaign_result(
    *cases: CaseVerdict,
    seed: int = 1234,
    budget: int = 20,
    runs_to_first_violation: int | None = None,
) -> TargetResult:
    cases = cases or (
        CaseVerdict("step-0", "declined", None, False, False),
        CaseVerdict("step-1", "resolved", None, True, True),
    )
    return TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.1"),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C1", "C2"),
        cases=cases,
        repro_inputs=(repro_input(cases[-1].case_id, f"inputs/{cases[-1].case_id}.tar", TAR_B),),
        provenance=Provenance("b" * 40, False, "inodefence-node-tar-effect:7.5.1-dev", None),
        campaign=CampaignInfo(
            seed=seed, budget=budget, runs_to_first_violation=runs_to_first_violation
        ),
    )


def test_regression_result_has_no_campaign_key_and_stays_backward_compatible() -> None:
    data = _result().to_json_dict()
    assert "campaign" not in data
    # A reader that predates the campaign block round-trips a regression file unchanged.
    assert from_json_dict(json.loads(_result().dumps())).campaign is None


def test_campaign_block_round_trips_and_serializes_only_when_present() -> None:
    result = _campaign_result(runs_to_first_violation=2)
    data = result.to_json_dict()
    assert data["mode"] == "campaign"
    assert data["campaign"] == {
        "seed": 1234,
        "budget": 20,
        "runs_to_first_violation": 2,
        "runs_executed": None,
        "errors": None,
        "stopped_early": False,
    }
    assert from_json_dict(json.loads(result.dumps())) == result


def test_campaign_none_first_violation_when_all_pass() -> None:
    result = _campaign_result(
        CaseVerdict("only", "declined", None, False, False),
        runs_to_first_violation=None,
    )
    assert result.verdict is Verdict.PASS
    assert from_json_dict(json.loads(result.dumps())) == result


def test_campaign_block_rejected_on_fixture_regression() -> None:
    with pytest.raises(TargetResultError, match="only valid when mode is campaign"):
        replace(_campaign_result(runs_to_first_violation=2), mode=ResultMode.FIXTURE_REGRESSION)


def test_campaign_budget_must_cover_runs() -> None:
    with pytest.raises(TargetResultError, match="budget must be null or an integer"):
        _campaign_result(runs_to_first_violation=2, budget=1)


def test_runs_to_first_violation_must_be_set_when_a_case_violated() -> None:
    with pytest.raises(TargetResultError, match="must be set when a case violated"):
        _campaign_result(runs_to_first_violation=None)


def test_runs_to_first_violation_must_be_null_when_nothing_violated() -> None:
    with pytest.raises(TargetResultError, match="must be null when nothing violated"):
        _campaign_result(
            CaseVerdict("only", "declined", None, False, False),
            runs_to_first_violation=1,
        )


def test_runs_to_first_violation_out_of_range_rejected() -> None:
    with pytest.raises(TargetResultError, match="in 1..runs"):
        _campaign_result(runs_to_first_violation=9)


def test_reader_still_rejects_unknown_top_level_keys() -> None:
    data = _result().to_json_dict()
    data["surprise"] = 1
    with pytest.raises(TargetResultError, match="unexpected \\['surprise'\\]"):
        from_json_dict(data)


def test_reader_rejects_campaign_block_with_wrong_keys() -> None:
    data = _campaign_result(runs_to_first_violation=2).to_json_dict()
    data["campaign"]["extra"] = 1
    with pytest.raises(TargetResultError, match="campaign keys mismatch"):
        from_json_dict(data)


def test_old_three_key_campaign_block_reads_with_defaults() -> None:
    # A block written before the large-campaign fields must still parse (optional keys absent).
    data = _campaign_result(runs_to_first_violation=2).to_json_dict()
    data["campaign"] = {"seed": 1234, "budget": 20, "runs_to_first_violation": 2}
    loaded = from_json_dict(data)
    assert loaded.campaign is not None
    assert loaded.campaign.runs_executed is None
    assert loaded.campaign.errors is None
    assert loaded.campaign.stopped_early is False


def _aggregate_result(
    *violations: CaseVerdict,
    runs_executed: int,
    errors: int = 0,
    budget: int | None = None,
    runs_to_first_violation: int | None = None,
    stopped_early: bool = False,
) -> TargetResult:
    # Large-campaign shape: cases hold only the violations (or none); counts live in the block.
    return TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.1"),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C1", "C2"),
        cases=violations,
        repro_inputs=tuple(
            repro_input(v.case_id, f"inputs/{v.case_id}.tar", f"v-{v.case_id}".encode())
            for v in violations
        ),
        provenance=Provenance("b" * 40, False, "inodefence-node-tar-registry:7.5.8", None),
        campaign=CampaignInfo(
            seed=7,
            budget=budget,
            runs_to_first_violation=runs_to_first_violation,
            runs_executed=runs_executed,
            errors=errors,
            stopped_early=stopped_early,
        ),
    )


def test_large_campaign_cases_are_violations_only_with_separate_run_count() -> None:
    result = _aggregate_result(
        CaseVerdict("step-14", "extracted", None, True, True),
        CaseVerdict("step-800", "extracted", None, True, False),
        runs_executed=1000,
        errors=3,
        budget=None,  # run until stopped
        runs_to_first_violation=15,
        stopped_early=True,
    )
    assert result.executed == 1000  # from runs_executed, not len(cases)==2
    assert result.errored == 3  # from the errors aggregate
    assert result.verdict is Verdict.ERROR  # errors dominate
    assert len(result.violating_cases) == 2
    assert from_json_dict(json.loads(result.dumps())) == result


def test_aggregate_errors_drive_error_verdict_even_with_no_error_case() -> None:
    result = _aggregate_result(runs_executed=50, errors=2)  # no cases at all
    assert result.executed == 50 and result.errored == 2
    assert result.verdict is Verdict.ERROR
    assert result.campaign is not None and result.campaign.budget is None


def test_runs_executed_cannot_be_below_case_count() -> None:
    with pytest.raises(TargetResultError, match="runs_executed must be an integer >= len"):
        _aggregate_result(
            CaseVerdict("step-0", "extracted", None, True, False),
            runs_executed=0,
            runs_to_first_violation=1,
        )


def test_errors_out_of_range_rejected() -> None:
    with pytest.raises(TargetResultError, match="errors must be an integer in 0..runs"):
        _aggregate_result(runs_executed=5, errors=6)


def test_first_violation_bounded_by_runs_executed_not_case_count() -> None:
    # 2 violation cases but 1000 runs: first violation at 999 is valid (<= executed).
    result = _aggregate_result(
        CaseVerdict("step-998", "extracted", None, True, False),
        CaseVerdict("step-999", "extracted", None, False, True),
        runs_executed=1000,
        runs_to_first_violation=999,
    )
    assert result.campaign is not None and result.campaign.runs_to_first_violation == 999
    with pytest.raises(TargetResultError, match="in 1..runs"):
        _aggregate_result(
            CaseVerdict("step-0", "extracted", None, True, False),
            runs_executed=10,
            runs_to_first_violation=11,
        )
