"""#536 option 1, driver side: FAST asks for fewer image identity probes; nothing else does.

- Only a FAST exploration session puts ``DEMO_IDENTITY_CHECK_EVERY`` in its main launch.
- STRICT runs, replays and plain launches never pass the caller's own value (one warning line).
- The result records the loop's identity-probe record when FAST asked for it, and a FAST run
  whose loop report does not show the requested schedule publishes no result (ERROR).
- STRICT results are unchanged (the explore byte-identity fixture covers them).
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import inodefence.drivers.explore_result as er
import inodefence.drivers.node_tar.explore as nte
import inodefence.drivers.run_target as rt
from inodefence.drivers.launcher import IDENTITY_CHECK_ENV, run_launcher
from inodefence.drivers.runtime import policy
from inodefence.drivers.runtime.session import RuntimeSession
from inodefence.target_result import (
    NODE_TAR_ACCEPTED_FAST_SCOPE,
    TargetResultError,
    from_json_dict,
    load_target_result,
)
from inodefence.target_result_summary import render_summary

SCRIPT = Path("/no/such/launcher.sh")
RECORD = {
    "identity_checks": "campaign",
    "interval": 200,
    "cases_prepared": 450,
    "start_checks": 1,
    "periodic_checks": 2,
    "end_checks": 1,
    "total_checks": 4,
    "per_case_checks_skipped": 448,
    # W5 937c8aa: what the probes cover, and the target's own per-case check if any
    "artifact_identity_basis": "campaign-probes",
    "per_case_identity_check": "in-container-source-hashes",
}


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        er, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )
    monkeypatch.delenv(IDENTITY_CHECK_ENV, raising=False)


class _Runner:
    def __init__(self) -> None:
        self.envs: list[dict[str, str]] = []

    def __call__(self, argv: list[str], *, env: dict[str, str], **_: Any) -> Any:
        self.envs.append(dict(env))
        return subprocess.CompletedProcess(argv, 0)


def _session(profile: policy.RuntimePolicy, kind: str = "explore") -> RuntimeSession:
    # reuse_shared_images is the other FAST flag; leave it out so only the interval is exercised
    return RuntimeSession(
        target="node-tar",
        policy=dataclasses.replace(profile, reuse_shared_images=False),
        kind=kind,  # type: ignore[arg-type]
    )


# -- the launch environment ----------------------------------------------------------------------


def test_fast_is_the_only_profile_with_an_interval() -> None:
    assert policy.STRICT.identity_check_every is None
    assert policy.FAST.identity_check_every == policy.FAST_IDENTITY_CHECK_EVERY == 200


def test_the_interval_matches_the_targets_default_when_both_are_present() -> None:
    schedule = pytest.importorskip("inodefence.targets.identity_schedule")
    assert policy.FAST_IDENTITY_CHECK_EVERY == schedule.DEFAULT_INTERVAL


def test_a_fast_exploration_launch_carries_the_interval() -> None:
    runner = _Runner()
    run_launcher(SCRIPT, runner=runner, env={"RUN_ID": "r"}, session=_session(policy.FAST))
    assert runner.envs == [{"RUN_ID": "r", IDENTITY_CHECK_ENV: "200"}]


def test_a_strict_launch_without_an_inherited_value_is_unchanged(capsys) -> None:
    runner = _Runner()
    env = {"RUN_ID": "r"}
    run_launcher(SCRIPT, runner=runner, env=env, session=_session(policy.STRICT))
    assert runner.envs == [env]
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    ("session", "prefix"),
    [
        (lambda: _session(policy.STRICT), "TARGET-EXPLORE"),
        (lambda: _session(policy.STRICT, "replay"), "REPLAY"),
        (lambda: None, "INODEFENCE"),
    ],
)
def test_an_inherited_interval_never_reaches_a_strict_launch(session, prefix, capsys) -> None:
    # A STRICT run or a replay must not probe less because of the caller's environment.
    runner = _Runner()
    run_launcher(
        SCRIPT, runner=runner, env={"RUN_ID": "r", IDENTITY_CHECK_ENV: "5"}, session=session()
    )
    assert runner.envs == [{"RUN_ID": "r"}]
    err = capsys.readouterr().err
    assert err.count("WARNING") == 1
    assert f"{prefix} WARNING: environment variable {IDENTITY_CHECK_ENV}=5 is ignored" in err


def test_a_fast_launch_replaces_an_inherited_interval(capsys) -> None:
    runner = _Runner()
    run_launcher(
        SCRIPT, runner=runner, env={IDENTITY_CHECK_ENV: "5"}, session=_session(policy.FAST)
    )
    assert runner.envs == [{IDENTITY_CHECK_ENV: "200"}]
    assert "=5 is ignored" in capsys.readouterr().err


def test_a_replay_never_runs_fast() -> None:
    with pytest.raises(ValueError, match="strict"):
        RuntimeSession(target="node-tar", policy=policy.FAST, kind="replay")


def test_the_runtime_record_names_the_interval() -> None:
    session = _session(policy.FAST)
    run_launcher(SCRIPT, runner=_Runner(), env={"RUN_ID": "r"}, session=session)
    session.finish(result_written=True)
    record = session.to_json()
    assert record["policy"] == {"identity_check_every": 200}
    (launch,) = record["launches"]
    assert launch["env"][IDENTITY_CHECK_ENV] == "200"
    assert launch["policy_applied"]["identity_check_every"]["applied"] is True


# -- the result ----------------------------------------------------------------------------------


def _prepared() -> rt.PreparedTargetImage:
    return rt.PreparedTargetImage(
        "node-tar", "7.5.23", "7.5.23", "inodefence-node-tar-registry:7.5.23",
        "sha256:" + "a" * 64, True,
    )  # fmt: skip


def _report(**extra: Any) -> dict[str, Any]:
    return {
        "demo_report_schema": 5,
        "streaming": True,
        "aggregate": {
            "runs_executed": 20,
            "terminations": {"success": 20},
            "unjudged_steps": 0,
            "errors": 0,
        },
        "violation_cases": [],
        "violation_inputs": [],
        **extra,
    }


def _result(report: dict[str, Any]):
    return er.build_campaign_result(report, _prepared(), seed=1, budget=20)[0]


def test_strict_returns_the_result_unchanged() -> None:
    result = _result(_report(identity_checks=RECORD))
    assert er.with_identity_checks(result, _report(identity_checks=RECORD), None) is result


def test_fast_records_the_loops_identity_checks() -> None:
    report = _report(identity_checks=RECORD)
    result = er.with_identity_checks(_result(report), report, 200)
    assert result.campaign is not None and result.campaign.identity_checks == RECORD
    data = json.loads(result.dumps())
    assert data["campaign"]["identity_checks"] == RECORD
    # The provenance distinction is carried as the loop recorded it; no declared artifacts are
    # added (W4: a declaration must not be recorded as an observation).
    carried = data["campaign"]["identity_checks"]
    assert carried["artifact_identity_basis"] == "campaign-probes"
    assert carried["per_case_identity_check"] == "in-container-source-hashes"
    assert not {"artifacts", "artifact_origin"} & set(carried)
    assert from_json_dict(data).campaign == result.campaign
    summary = render_summary(result, source_name="result.json", inputs_verified=True)
    assert "| 이미지 신원 확인 | 캠페인 단위(시작·200건마다·끝), 총 4회" in summary


@pytest.mark.parametrize("record", [None, {**RECORD, "interval": 50}, "campaign"])
def test_fast_without_the_requested_record_is_an_error(record: Any) -> None:
    report = _report() if record is None else _report(identity_checks=record)
    with pytest.raises(er.IdentityRecordError, match="no result written"):
        er.with_identity_checks(_result(report), report, 200)
    assert issubclass(er.IdentityRecordError, RuntimeError)  # the drivers' ERROR path (exit 2)


@pytest.mark.parametrize(
    "record", [{"interval": 0, "total_checks": 2}, {"interval": 200}, ["campaign"]]
)
def test_the_reader_checks_the_record(record: Any) -> None:
    data = _result(_report()).to_json_dict()
    data["campaign"]["identity_checks"] = record
    with pytest.raises(TargetResultError, match="identity_checks"):
        from_json_dict(data)


def test_the_node_tar_hook_records_it_under_a_fast_session(monkeypatch, tmp_path: Path) -> None:
    # a filled stand-in scope: the real one is empty until the follow-up result (W4 Q2 (ii))
    filled = {**NODE_TAR_ACCEPTED_FAST_SCOPE, "counted_seeds": [1, 2, 3], "rule_sha": "0" * 64}
    monkeypatch.setitem(er.ACCEPTED_FAST_SCOPE, "node-tar", filled)

    def fake(prepared: Any, *, out: Path, run_id: str, **_: Any) -> Path:
        path = nte.controller_report_path(out, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_report(identity_checks=RECORD)), encoding="utf-8")
        return path

    monkeypatch.setattr(nte, "run_controller", fake)
    fast = rt.ExploreOptions(budget=20, seed=1, out=tmp_path / "f", runtime=_session(policy.FAST))
    outcome = nte.explore(_prepared(), fast)
    campaign = load_target_result(outcome.result_path).campaign
    # W4 Q2 (ii): the loop's record plus the scope label (7.5.23 is outside the measured scope)
    assert campaign is not None and campaign.identity_checks == {
        **RECORD,
        "fast_acceptance": "interval_on_unmeasured_scope",
        "acceptance_scope": filled,
    }
    strict = rt.ExploreOptions(budget=20, seed=1, out=tmp_path / "s")
    raw = json.loads(nte.explore(_prepared(), strict).result_path.read_text(encoding="utf-8"))
    assert "identity_checks" not in raw["campaign"]  # STRICT: the report is not consulted
