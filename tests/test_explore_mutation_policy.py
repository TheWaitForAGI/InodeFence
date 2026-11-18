"""``explore --mutation-policy`` (node-tar only, exploratory) and the build-invalid count.

- The option opens exactly one value, the v2 grammar policy; v2.1 is not offered.
- Other targets are refused before anything is prepared or run (exit 3).
- No explore driver passes the caller's own ``DEMO_MUTATION_POLICY`` to its launcher.
- The result records the policy only when the option was given, after checking the loop ran it.
- Build-invalid runs (v2 only) are recorded and left out of the un-judged ratio's denominator.
- A run without the option writes byte-identical ``result.json`` and ``summary.md``: compared with
  what main e1098d6 wrote for the same reports (``tests/fixtures/explore-default-v1``).
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests import explore_default_outputs

import inodefence.drivers.decompress.explore as dce
import inodefence.drivers.explore_result as er
import inodefence.drivers.node_tar.explore as nte
import inodefence.drivers.oras_go.explore as oge
import inodefence.drivers.python_tarfile.explore as pte
import inodefence.drivers.run_target as rt
import inodefence.drivers.run_target_explore as rte
from inodefence import cli
from inodefence.evaluation.rds import VOCABULARY_MUTATION_POLICY
from inodefence.mutator import MutationPolicy
from inodefence.target_result import (
    CampaignInfo,
    TargetResultError,
    Verdict,
    from_json_dict,
    load_target_result,
)
from inodefence.target_result_summary import render_summary

V2 = MutationPolicy.V2_FREEZE3_FIXED_BASELINE.value
V2_MODE = next(m.value for m, p in VOCABULARY_MUTATION_POLICY.items() if p.value == V2)
FIXTURE = Path(__file__).parent / "fixtures" / "explore-default-v1" / "outputs.json"


@pytest.fixture(autouse=True)
def _fixed_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        er, "engine_provenance", lambda image: rt.Provenance("b" * 40, False, image, None)
    )


def _prepared() -> rt.PreparedTargetImage:
    return rt.PreparedTargetImage(
        "node-tar", "7.5.23", "7.5.23", "inodefence-node-tar-registry:7.5.23",
        "sha256:" + "a" * 64, True,
    )  # fmt: skip


# -- the option's values -------------------------------------------------------------------------


def test_the_option_opens_only_the_v2_policy_and_the_cli_copy_matches() -> None:
    assert rt.EXPLORE_MUTATION_POLICIES == (V2,)
    assert cli.EXPLORE_MUTATION_POLICIES == rt.EXPLORE_MUTATION_POLICIES
    assert MutationPolicy.V2_FREEZE3_FIXED_BASELINE_MINIMAL_EMPTY_REG.value not in (
        rt.EXPLORE_MUTATION_POLICIES
    )
    assert rt.MUTATION_POLICY_TARGETS == ("node-tar",)
    assert rt.MUTATION_POLICY_ENV == "DEMO_MUTATION_POLICY"


def test_cli_forwards_the_option_only_when_given(monkeypatch, tmp_path: Path) -> None:
    calls: list = []
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(
        cli, "run_driver", lambda root, driver, argv, prog=None: calls.append(argv) or 0
    )
    base = ["explore", "--version", "7.5.23", "--auto-prepare", "--out", str(tmp_path)]
    assert cli.main(base) == 0
    assert cli.main([*base, "--mutation-policy", V2]) == 0
    without, with_option = calls
    assert "--mutation-policy" not in without
    assert with_option == [*without[:-2], "--mutation-policy", V2, *without[-2:]]


@pytest.mark.parametrize(
    "value",
    [MutationPolicy.V2_FREEZE3_FIXED_BASELINE_MINIMAL_EMPTY_REG.value, "uniform-generic-m1-v1"],
)
def test_cli_refuses_any_other_value_with_exit_3(value: str, capsys, tmp_path: Path) -> None:
    argv = ["explore", "--version", "7.5.23", "--dry-run", "--out", str(tmp_path)]
    with pytest.raises(SystemExit) as stop:
        cli.main([*argv, "--mutation-policy", value])
    assert stop.value.code == 3
    assert "invalid choice" in capsys.readouterr().err


# -- the driver: refusal for other targets, the plan, the hook's options -------------------------


@pytest.mark.parametrize(
    "target_argv",
    [
        ["--target", "python-tarfile", "--version", "3.12.7", "--extraction-filter", "data"],
        ["--target", "decompress", "--version", "decompress@4.2.1"],
        ["--target", "oras-go", "--version", "2.6.2"],
    ],
)
def test_driver_refuses_the_option_for_other_targets_before_anything(
    target_argv: list[str], monkeypatch, capsys, tmp_path: Path
) -> None:
    monkeypatch.setattr(rte, "prepare_target_image", lambda *a, **k: pytest.fail("prepared"))
    argv = [*target_argv, "--out", str(tmp_path), "--mutation-policy", V2]
    for extra in (["--dry-run"], ["--auto-prepare"]):
        assert rte.main([*argv, *extra]) == 3
        err = capsys.readouterr().err
        assert "available only for node-tar exploration" in err
        assert "nothing was prepared or run" in err
    assert not any(tmp_path.iterdir())


def test_driver_dry_run_plan_names_the_policy_only_when_given(capsys, tmp_path: Path) -> None:
    argv = ["--target", "node-tar", "--version", "7.5.23", "--out", str(tmp_path), "--dry-run"]
    assert rte.main(argv) == 0
    plan = json.loads(capsys.readouterr().out)
    assert "mutation_policy" not in plan
    assert rte.main([*argv, "--mutation-policy", V2]) == 0
    with_option = json.loads(capsys.readouterr().out)
    assert with_option.pop("mutation_policy") == V2
    assert with_option == plan


def test_driver_passes_the_option_to_the_hook(monkeypatch, tmp_path: Path) -> None:
    seen: list[rt.ExploreOptions] = []

    def fake_explore(prepared: Any, options: rt.ExploreOptions) -> rt.ExploreOutcome:
        seen.append(options)
        return rt.ExploreOutcome(tmp_path / "absent" / "result.json", "PASS", 20, 0)

    real = rt.load_adapter("node-tar")
    monkeypatch.setattr(
        rte, "load_adapter", lambda target: dataclasses.replace(real, explore=fake_explore)
    )
    monkeypatch.setattr(rte, "prepare_target_image", lambda *a, **k: _prepared())
    monkeypatch.setattr(rte, "docker_problem", lambda: None)
    argv = ["--target", "node-tar", "--version", "7.5.23", "--out", str(tmp_path / "out")]
    argv += ["--auto-prepare", "--output", "quiet"]
    assert rte.main(argv) == 0
    assert rte.main([*argv, "--mutation-policy", V2]) == 0
    assert [options.mutation_policy for options in seen] == [None, V2]


# -- no driver passes the caller's own DEMO_MUTATION_POLICY --------------------------------------


def _capture_env(report: Path):
    captured: dict[str, Any] = {}

    def runner(cmd: Any, env: Any = None, cwd: Any = None, **_: Any) -> Any:
        captured["env"] = env
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    return captured, runner


@pytest.mark.parametrize("option", [None, V2])
def test_node_tar_launcher_env_carries_only_the_option(
    option: str | None, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEMO_MUTATION_POLICY", "inherited-from-the-caller")
    captured, runner = _capture_env(nte.controller_report_path(tmp_path, "rid"))
    nte.run_controller(
        _prepared(), out=tmp_path, run_id="rid", budget=20, seed=1, python="x",
        mutation_policy=option, runner=runner,
    )  # fmt: skip
    assert captured["env"].get("DEMO_MUTATION_POLICY") == option


def test_python_tarfile_launcher_env_drops_the_callers_policy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEMO_MUTATION_POLICY", "inherited-from-the-caller")
    captured, runner = _capture_env(pte.report_path(tmp_path, "rid"))
    pte.run_controller("ref", "3.12.7", "data", out=tmp_path, run_id="rid", budget=8, seed=1,
                       runner=runner)  # fmt: skip
    assert "DEMO_MUTATION_POLICY" not in captured["env"]


@pytest.mark.parametrize("module", ["decompress", "oras-go"])
@pytest.mark.parametrize("option", [None, "their-own-default"])
def test_decompress_and_oras_go_launcher_env_carries_only_their_value(
    module: str, option: str | None, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEMO_MUTATION_POLICY", "inherited-from-the-caller")
    if module == "decompress":
        captured, runner = _capture_env(dce.controller_report_path(tmp_path, "rid"))
        dce.run_controller("img", tmp_path, "rid", seed=1, budget=8, mutation_policy=option,
                           search_policy=None, runner=runner)  # fmt: skip
    else:
        captured, runner = _capture_env(oge.controller_report_path(tmp_path, "rid"))
        try:
            oge.run_controller(_prepared(), out=tmp_path, run_id="rid", budget=8, seed=1,
                               python="x", mutation_policy=option, runner=runner)  # fmt: skip
        except RuntimeError:
            pass  # "{}" is no loop report; the env was already captured
    assert captured["env"].get("DEMO_MUTATION_POLICY") == option


# -- the node-tar hook: check, record ------------------------------------------------------------


def _v2_report(*, vocabulary_mode: str | None = V2_MODE, unjudged: int = 1) -> dict[str, Any]:
    return {
        "demo_report_schema": 5,
        "streaming": True,
        "vocabulary_mode": vocabulary_mode,
        "aggregate": {
            "runs_executed": 20,
            "terminations": {"success": 10, "rejected": 2},
            "unjudged_steps": unjudged,
            "errors": 0,
        },
        "violation_cases": [],
        "violation_inputs": [],
    }


def _write_live(out: Path, run_id: str, *, runs: int, build_invalid: int) -> None:
    live = out / "target-explore" / run_id / "live"
    live.mkdir(parents=True, exist_ok=True)
    progress: dict[str, Any] = {
        "schema": explore_default_outputs.PROGRESS_SCHEMA,
        "state": "finished",
        "runs_executed": runs,
    }
    if build_invalid:
        progress["build_invalid"] = {"steps": build_invalid}
    (live / "progress.json").write_text(json.dumps(progress), encoding="utf-8")


def _fake_controller(report: dict[str, Any], seen: list[str | None], *, build_invalid: int = 8):
    def fake(prepared: Any, *, out: Path, run_id: str, mutation_policy=None, **_: Any) -> Path:
        seen.append(mutation_policy)
        _write_live(out, run_id, runs=20, build_invalid=build_invalid)
        path = nte.controller_report_path(out, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    return fake


def test_v2_run_records_policy_and_build_invalid(monkeypatch, tmp_path: Path) -> None:
    seen: list[str | None] = []
    monkeypatch.setattr(nte, "run_controller", _fake_controller(_v2_report(), seen))
    options = rt.ExploreOptions(budget=20, seed=1, out=tmp_path, mutation_policy=V2)
    outcome = nte.explore(_prepared(), options)
    assert seen == [V2]
    raw = json.loads(outcome.result_path.read_text(encoding="utf-8"))
    assert raw["campaign"]["mutation_policy"] == V2
    assert raw["campaign"]["build_invalid"] == 8
    # 20 budget units, 8 of them build-invalid: 1 un-judged of 12 extraction runs, not of 20.
    assert raw["campaign"]["unjudged_ratio"] == round(1 / 12, 6)
    result = load_target_result(outcome.result_path)
    assert result.extraction_runs == 12 and result.executed == 20
    summary = (outcome.result_path.parent / "summary.md").read_text(encoding="utf-8")
    assert "| 빌드 불가(build-invalid) | 8건" in summary and V2 in summary


@pytest.mark.parametrize("mode", [None, "observed-names", "no-such-mode"])
def test_a_run_that_did_not_run_the_requested_policy_is_an_error(
    mode: str | None, monkeypatch, tmp_path: Path
) -> None:
    seen: list[str | None] = []
    report = _v2_report(vocabulary_mode=mode)
    monkeypatch.setattr(nte, "run_controller", _fake_controller(report, seen))
    options = rt.ExploreOptions(budget=20, seed=1, out=tmp_path, mutation_policy=V2)
    with pytest.raises(RuntimeError, match="requested"):
        nte.explore(_prepared(), options)
    assert not list(tmp_path.rglob("result.json"))


def test_without_the_option_nothing_is_checked_or_recorded(monkeypatch, tmp_path: Path) -> None:
    seen: list[str | None] = []
    report = _v2_report(vocabulary_mode="observed-names")
    monkeypatch.setattr(nte, "run_controller", _fake_controller(report, seen, build_invalid=0))
    outcome = nte.explore(_prepared(), rt.ExploreOptions(budget=20, seed=1, out=tmp_path))
    assert seen == [None]
    campaign = json.loads(outcome.result_path.read_text(encoding="utf-8"))["campaign"]
    assert "mutation_policy" not in campaign and "build_invalid" not in campaign


def _build(report: dict[str, Any], live: Path | None = None, policy: str | None = V2):
    return er.build_campaign_result(
        report, _prepared(), seed=1, budget=20, live_dir=live, mutation_policy=policy
    )[0]


def test_the_build_invalid_count_comes_from_the_aggregate(tmp_path: Path) -> None:
    # QA check 42: runs_executed - sum(terminations) is exact (one termination per extraction);
    # no live folder is needed, and a stale snapshot (other run count) is not consulted.
    result = _build(_v2_report())
    assert result.campaign is not None and result.campaign.build_invalid == 8
    _write_live(tmp_path, "rid", runs=15, build_invalid=4)  # the aggregate says 20 runs
    stale = _build(_v2_report(), tmp_path / "target-explore" / "rid" / "live")
    assert stale.campaign is not None and stale.campaign.build_invalid == 8
    assert stale.unjudged_ratio == round(1 / 12, 6)


def test_zero_build_invalid_runs_write_no_key() -> None:
    report = _v2_report()
    report["aggregate"]["terminations"] = {"success": 18, "rejected": 2}
    result = _build(report)
    assert result.campaign is not None and result.campaign.build_invalid is None
    assert "build_invalid" not in result.to_json_dict()["campaign"]


def _no_terminations() -> dict[str, Any]:
    report = _v2_report()
    del report["aggregate"]["terminations"]
    return report


def _too_many_terminations() -> dict[str, Any]:
    report = _v2_report()
    report["aggregate"]["terminations"] = {"success": 21}
    return report


def _per_case() -> dict[str, Any]:
    return {"demo_report_schema": 5, "case_records": [], "violation_inputs": []}


@pytest.mark.parametrize("report", [_no_terminations, _too_many_terminations, _per_case])
def test_an_unknown_build_invalid_count_is_an_error_not_a_silent_omission(report) -> None:
    # Leaving the key out would put build-invalid runs back into the denominator and loosen the
    # ERROR ceiling without saying so: a --mutation-policy run then gets no result (exit 2).
    with pytest.raises(er.BuildInvalidUnknownError, match="build-invalid count unknown"):
        _build(report())
    assert issubclass(er.BuildInvalidUnknownError, RuntimeError)  # the drivers' ERROR path


def test_a_live_snapshot_that_disagrees_with_the_aggregate_is_an_error(tmp_path: Path) -> None:
    _write_live(tmp_path, "rid", runs=20, build_invalid=5)  # the aggregate gives 8
    with pytest.raises(er.BuildInvalidUnknownError, match="live snapshot"):
        _build(_v2_report(), tmp_path / "target-explore" / "rid" / "live")


def test_without_the_option_no_count_is_derived() -> None:
    # A default-policy report whose terminations do not add up to the runs keeps today's bytes.
    result = _build(_v2_report(), policy=None)
    assert result.campaign is not None and result.campaign.build_invalid is None
    assert _build(_no_terminations(), policy=None).campaign is not None


# -- the un-judged ratio and the contract --------------------------------------------------------


def _campaign_result(**campaign: Any):
    result, _ = er.build_campaign_result(_v2_report(), _prepared(), seed=1, budget=20)
    assert result.campaign is not None
    return dataclasses.replace(result, campaign=dataclasses.replace(result.campaign, **campaign))


def test_every_extraction_run_unjudged_is_error_even_with_build_invalid_runs() -> None:
    result = _campaign_result(
        build_invalid=8, unjudged_steps=12, terminations={"failed": 12}, max_unjudged_ratio=None
    )
    assert result.unjudged_ratio == 1.0 and result.verdict is Verdict.ERROR
    assert "12건 중 12건에서" in render_summary(
        result, source_name="result.json", inputs_verified=True
    )


def test_the_ceiling_is_held_against_extraction_runs() -> None:
    # 3 of 12 extraction runs (0.25) is above 0.2; of all 20 budget units (0.15) it would not be.
    assert _campaign_result(build_invalid=8, unjudged_steps=3).verdict is Verdict.ERROR
    assert _campaign_result(unjudged_steps=3).verdict is Verdict.PASS


@pytest.mark.parametrize(
    ("campaign", "message"),
    [
        ({"build_invalid": 0}, "build_invalid"),
        ({"build_invalid": 21}, "build_invalid"),
        ({"build_invalid": 15, "unjudged_steps": 6}, "unjudged_steps"),
        ({"build_invalid": 10}, "terminations"),  # 12 terminations > 10 extraction runs
        ({"mutation_policy": ""}, "mutation_policy"),
    ],
)
def test_the_reader_checks_the_new_keys(campaign: dict[str, Any], message: str) -> None:
    data = _campaign_result().to_json_dict()
    data["campaign"].update(campaign)
    data["campaign"].pop("unjudged_ratio")
    with pytest.raises(TargetResultError, match=message):
        from_json_dict(data)


def test_the_new_keys_round_trip() -> None:
    result = _campaign_result(build_invalid=8, mutation_policy=V2)
    reread = from_json_dict(json.loads(result.dumps()))
    assert reread.campaign == result.campaign
    assert isinstance(reread.campaign, CampaignInfo)


# -- byte identity of a run without the option ---------------------------------------------------


def test_default_policy_outputs_are_byte_identical_to_main(tmp_path: Path) -> None:
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert explore_default_outputs.default_outputs(tmp_path) == expected


@pytest.mark.parametrize("inherited", [None, "uniform-b-grammar-v2-freeze-3-fixed-baseline-v1"])
def test_a_dropped_inherited_policy_is_warned_about_on_stderr(
    inherited: str | None, monkeypatch, capsys, tmp_path: Path
) -> None:
    # A caller that used to choose the policy through the environment must not silently run the
    # default policy: the drop is one stderr line naming the variable and the option.
    if inherited is None:
        monkeypatch.delenv("DEMO_MUTATION_POLICY", raising=False)
    else:
        monkeypatch.setenv("DEMO_MUTATION_POLICY", inherited)
    captured, runner = _capture_env(nte.controller_report_path(tmp_path, "rid"))
    nte.run_controller(
        _prepared(), out=tmp_path, run_id="rid", budget=20, seed=1, python="x", runner=runner
    )
    out, err = capsys.readouterr()
    assert "DEMO_MUTATION_POLICY" not in captured["env"] and out == ""
    if inherited is None:
        assert "DEMO_MUTATION_POLICY" not in err
    else:
        assert err.count("TARGET-EXPLORE WARNING") == 1
        assert f"DEMO_MUTATION_POLICY={inherited} is ignored; use --mutation-policy" in err
