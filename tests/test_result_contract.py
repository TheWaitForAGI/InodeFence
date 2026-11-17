"""The 0.2.x compatibility promise for ``result.json`` (D049, docs/USAGE.md "호환 약속").

The files under ``tests/fixtures/result-contract-v1/`` are results as 0.2.0 writes them, committed
once and not regenerated. A change that makes the reader refuse them, or read a required field
differently, breaks the promise and must fail here. Adding an optional key stays allowed: these
tests read the committed files, they do not compare against what the writer emits today.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inodefence import cli
from inodefence.target_result import (
    SCHEMA,
    ResultMode,
    Verdict,
    from_json_dict,
    load_target_result,
)

GOLDEN = Path(__file__).parent / "fixtures" / "result-contract-v1"

#: Keys every v1 result carries. Removing or renaming one needs a new schema name.
REQUIRED_TOP_KEYS = {
    "schema",
    "label",
    "target",
    "axes",
    "mode",
    "observed_contracts",
    "runs",
    "verdict",
    "violating_cases",
    "cases",
    "repro_inputs",
    "provenance",
}
REQUIRED_CASE_KEYS = {"case_id", "outcome", "c0", "c1", "c2"}


def _raw(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def test_schema_name_is_unchanged() -> None:
    assert SCHEMA == "inodefence-target-result-v1"


@pytest.mark.parametrize("name", ["fixture-regression.json", "campaign.json"])
def test_committed_results_keep_their_required_keys(name: str) -> None:
    raw = _raw(name)
    assert raw["schema"] == "inodefence-target-result-v1"
    assert REQUIRED_TOP_KEYS <= set(raw)
    assert set(raw["runs"]) == {"executed", "errored"}
    assert all(set(case) >= REQUIRED_CASE_KEYS for case in raw["cases"])
    assert all(set(item) == {"case_id", "tar_path", "tar_sha256"} for item in raw["repro_inputs"])


def test_committed_fixture_regression_result_still_reads() -> None:
    result = from_json_dict(_raw("fixture-regression.json"))
    assert result.mode is ResultMode.FIXTURE_REGRESSION
    assert result.campaign is None
    assert result.target == "node-tar"
    assert result.executed == len(result.cases)


def test_committed_campaign_result_still_reads() -> None:
    result = from_json_dict(_raw("campaign.json"))
    assert result.mode is ResultMode.CAMPAIGN
    assert result.verdict is Verdict.FAIL
    assert result.violating_cases == ("step-1",)
    assert result.executed == 2
    assert result.campaign is not None
    assert (result.campaign.seed, result.campaign.budget) == (1234, 20)
    assert result.campaign.runs_to_first_violation == 2
    assert result.campaign.stopped_early is False


def test_committed_result_reads_from_a_file_without_its_inputs() -> None:
    # `status` and `summary --no-verify-inputs` read a result whose input folder was not kept.
    result = load_target_result(GOLDEN / "campaign.json", verify_inputs=False)
    assert result.verdict is Verdict.FAIL


def test_help_states_the_promised_exit_codes(capsys) -> None:
    # The codes themselves are covered by the driver tests; this pins what the user is told.
    for command in ("verify", "explore"):
        with pytest.raises(SystemExit):
            cli.main([command, "--help"])
        out = " ".join(capsys.readouterr().out.split())
        assert "0 PASS, 1 FAIL" in out and "2 ERROR" in out and "3 refused" in out
    with pytest.raises(SystemExit):
        cli.main(["replay", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "0 every round ran" in out and "4 unsupported" in out
