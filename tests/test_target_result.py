"""inodefence-target-result-v1: shape, derived verdict, strict reader, saved-input hashes."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.target_result import (
    LABEL,
    SCHEMA,
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
