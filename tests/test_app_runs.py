"""``inodefence.app.runs``: the read model gives the existing readers' values, typed, unknown kept
unknown, distinctions kept apart. All folders are SYNTHETIC (``tests/app_synthetic.py``)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from tests import app_synthetic as syn

from inodefence.app import runs
from inodefence.app.runs import (
    FindingClass,
    Judgment,
    ReadState,
    ReplayConclusion,
    RunKind,
    RunOutcome,
    RunRef,
    Source,
    Termination,
    Verdict,
)
from inodefence.drivers import progress as progress_reader
from inodefence.target_result import load_target_result


def _explore_ref(out: Path, rid: str) -> RunRef:
    return RunRef(RunKind.EXPLORE, out, rid)


# -- live (node-tar) -------------------------------------------------------------------------------


def test_running_live_run_matches_the_existing_reader(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    live, _ = syn.live_run(out, rid, [syn.step(0), syn.step(1, c1=True, fp="c1-a")])
    snap = runs.read_run(_explore_ref(out, rid), now=1_800_000_100.0)
    expected = progress_reader.read_live_counts(live)
    assert expected is not None
    p = snap.progress
    assert p is not None and p.source is Source.LIVE and p.state == "running"
    assert (p.runs, p.budget, p.violations, p.unjudged) == (
        expected.runs, expected.budget, expected.violations, expected.unjudged,
    )  # fmt: skip
    assert dict(p.contracts) == dict(expected.contracts)
    assert p.unique_fingerprints == 1 and p.build_invalid == 0
    assert snap.ref.target == "node-tar" and snap.ref.version == "7.5.2"
    (finding,) = snap.findings
    assert finding.finding is FindingClass.CANDIDATE and finding.c1 is True
    assert finding.source is Source.LIVE and finding.input_path and finding.input_path.is_file()
    assert snap.summary is None  # no result yet
    age = snap.progress_age()
    assert age is not None and age > 0


def test_finished_and_stopped_states_are_kept(tmp_path: Path) -> None:
    out = syn.explore_out(tmp_path)
    for state, seed in (("finished", 1), ("stopped", 2), ("failed", 3)):
        rid = syn.run_id(seed)
        syn.live_run(out, rid, [syn.step(0)], close=state)
        progress = runs.read_run(_explore_ref(out, rid)).progress
        assert progress is not None and progress.state == state


def test_a_violation_seen_on_a_rejected_run_needs_a_repro_check(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    syn.live_run(out, rid, [syn.step(0, status="rejected", c1=True, fp="c1-b")])
    (row,) = runs.read_run(_explore_ref(out, rid)).findings
    assert row.finding is FindingClass.CANDIDATE_NEEDS_REPRO_CHECK
    assert row.termination is Termination.REJECTED


# -- other targets: nothing while running -----------------------------------------------


def test_a_run_without_live_numbers_stays_unknown(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), f"{syn.SYNTHETIC}-3.12.7-data-1-20"
    snap = runs.read_run(_explore_ref(out, rid))
    p = snap.progress
    assert p is not None and p.source is Source.NONE
    assert p.runs is None and p.violations is None and p.budget is None  # never 0
    assert all(v is None for v in p.contracts.values())
    log = out / "runtime" / "explore-launcher-20260101T000000Z-1.log"
    log.parent.mkdir(parents=True)
    log.write_text("==> [build image]\n==> [run controller]\n==> [partial", encoding="utf-8")
    p = runs.read_run(_explore_ref(out, rid)).progress
    assert p is not None and p.source is Source.LAUNCHER_LOG
    assert p.launcher_step == "run-controller" and p.launcher_step_estimated
    assert p.runs is None


# -- results ---------------------------------------------------------------------------------------


def test_finished_result_matches_load_target_result(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    res = syn.result(cases=[syn.case("step-1", False), syn.case("step-2", True)], saved=["step-2"])
    path = syn.write_result(out / "target-explore" / f"{rid}-result", res)
    snap = runs.read_run(_explore_ref(out, rid))
    loaded = load_target_result(path)
    summary = snap.summary
    assert summary is not None and summary.read_state is ReadState.OK and summary.validated
    assert summary.verdict is Verdict.FAIL and loaded.verdict.value == "FAIL"
    assert (summary.executed, summary.unjudged_steps) == (loaded.executed, loaded.unjudged_steps)
    assert summary.runs_to_first_violation == 2
    progress = snap.progress
    assert progress is not None and progress.source is Source.RESULT and progress.runs == 2
    (finding,) = snap.findings
    assert finding.case_id == "step-2" and finding.run == 2 and finding.tar_sha256
    integrity = summary.integrity
    assert integrity is not None and integrity.image_id == syn.IMAGE and not integrity.rechecked
    checked = runs.recheck_inputs(summary)
    assert checked.rechecked and checked.recheck_failures == ()
    (path.parent / "inputs" / "step-2.tar").write_bytes(b"changed")
    assert runs.recheck_inputs(summary).recheck_failures


def test_no_violation_and_null_contracts_stay_apart(tmp_path: Path) -> None:
    cases = [syn.case("a", False), syn.case("b", None, termination=None)]
    res = syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION, cases=cases)
    summary = runs.read_result(syn.write_result(tmp_path / "cell", res))
    a, b = summary.cases
    assert a.judgment is Judgment.JUDGED and a.c1 is False and a.c0 is False
    assert b.judgment is Judgment.RUN_ERROR and b.c1 is None and b.c0 is None
    assert summary.verdict is Verdict.ERROR  # fixture regression: a run error is ERROR
    assert a.finding is None and b.finding is None


def test_no_extraction_warning_is_carried(tmp_path: Path) -> None:
    res = syn.result(cases=[syn.case("step-1", False, termination="rejected")],
                     terminations={"rejected": 1})  # fmt: skip
    summary = runs.read_result(syn.write_result(tmp_path / "r", res))
    assert summary.verdict is Verdict.PASS and summary.no_extraction_warning


def test_half_written_result_is_not_ready_not_an_error(tmp_path: Path) -> None:
    path = syn.write_result(tmp_path / "r", syn.result(), text='{"schema": "inodefence-tar')
    summary = runs.read_result(path)
    assert summary.read_state is ReadState.NOT_READY and summary.verdict is None
    assert runs.read_result(tmp_path / "absent" / "result.json").read_state is ReadState.MISSING
    foreign = syn.write_result(tmp_path / "f", syn.result(), text='{"schema": "other"}')
    assert runs.read_result(foreign).read_state is ReadState.UNREADABLE


def test_newer_campaign_keys_are_read_either_way(tmp_path: Path) -> None:
    data = syn.result(cases=[syn.case("step-1", False)]).to_json_dict()
    data["campaign"]["mutation_policy"] = "x"
    data["campaign"]["identity_checks"] = {"interval": 1}
    summary = runs.read_result(syn.write_result(tmp_path / "n", syn.result(),
                                                text=json.dumps(data)))  # fmt: skip
    assert summary.read_state is ReadState.OK and summary.validated
    assert summary.extras == {"mutation_policy": "x", "identity_checks": {"interval": 1}}
    data["runs"]["executed"] = 99  # a derived field the strict reader refuses
    refused = runs.read_result(syn.write_result(tmp_path / "m", syn.result(),
                                                text=json.dumps(data)))  # fmt: skip
    assert refused.read_state is ReadState.UNVALIDATED and not refused.validated
    assert refused.has_values and refused.verdict is not None  # values, marked
    assert refused.executed == 99 and refused.error and "strict reader" in refused.error


def test_compare_results_marks_same_input_only_with_equal_hashes(tmp_path: Path) -> None:
    def cell(name: str, c1: bool, saved: bool):
        res = syn.result(
            version=name,
            mode=syn.ResultMode.FIXTURE_REGRESSION,
            cases=[syn.case("fixture", c1)],
            saved=["fixture"] if saved else [],
        )
        return runs.read_result(syn.write_result(tmp_path / name, res))  # fmt: skip

    old, new, bare = cell("7.5.2", True, True), cell("7.5.3", False, True), cell("x", False, False)
    (cmp,) = runs.compare_results(old, new)
    assert cmp.same_input is True and cmp.a and cmp.b and cmp.a.c1 is True and cmp.b.c1 is False
    (cmp,) = runs.compare_results(old, bare)
    assert cmp.same_input is None  # no hash on one side: cannot say "same input"


# -- replay ----------------------------------------------------------------------------------------


def test_replay_rates_use_judged_rounds_as_denominator(tmp_path: Path) -> None:
    case_dir = tmp_path / "violations" / "run-000002"
    case_dir.mkdir(parents=True)
    original = {"c0": False, "c1": True, "c2": False, "fingerprints": []}
    rounds = [syn.judged_round(True), syn.judged_round(False), syn.failed_round()]
    path = syn.replay(case_dir, original, rounds)
    record = runs.read_replay(path)
    assert record.read_state is ReadState.OK
    assert record.rounds_done == 3 and record.judged == 2 and record.unjudged == 1
    assert record.same_contracts == 1 and record.same_contracts_rate == 0.5  # 1 / judged 2
    assert record.conclusion is ReplayConclusion.PARTIALLY_REPRODUCED
    only_failed = syn.replay(tmp_path / "violations" / "run-000003", original, [syn.failed_round()])
    record = runs.read_replay(only_failed)
    assert record.judged == 0 and record.same_contracts_rate is None
    assert record.conclusion is ReplayConclusion.INFRASTRUCTURE_FAILURE


def test_the_enums_hold_no_confirmed_label() -> None:
    labels = {m.value for e in (FindingClass, ReplayConclusion, Verdict) for m in e}
    assert not any("confirm" in label for label in labels)


# -- discovery and exit codes ----------------------------------------------------------------------


def test_discover_finds_each_kind_and_skips_links_and_dots(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    syn.live_run(out, rid, [syn.step(0)])
    syn.write_result(out / "target-explore" / f"{rid}-result", syn.result())
    verify = tmp_path / f"{syn.SYNTHETIC}-verify"
    syn.write_result(verify / "node-tar-7.5.2", syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION))
    syn.write_result(verify / ".hidden", syn.result())
    os.symlink(verify / "node-tar-7.5.2", verify / "linked")
    listings = runs.discover_runs([out, verify])
    kinds = sorted((item.ref.kind.value, item.ref.run_id) for item in listings if item.ref)
    assert kinds == [("explore", rid), ("verify", "node-tar-7.5.2")]  # one explore run, grouped
    assert runs.discover_runs([verify / "linked"])[0].read_state is ReadState.UNREADABLE


def test_discover_refuses_the_repository() -> None:
    repo = Path(__file__).resolve().parents[1]
    (listing,) = runs.discover_runs([repo])
    assert listing.ref is None and listing.error and "repository" in listing.error


@pytest.mark.parametrize(
    ("command", "code", "outcome"),
    [("verify", 0, RunOutcome.PASS), ("explore", 1, RunOutcome.FAIL),
     ("explore", 2, RunOutcome.ERROR), ("verify", 3, RunOutcome.REFUSED),
     ("replay", 0, RunOutcome.COMPLETE), ("replay", 1, RunOutcome.INCOMPLETE),
     ("replay", 4, RunOutcome.UNSUPPORTED), ("status", 0, RunOutcome.UNKNOWN)],
)  # fmt: skip
def test_exit_codes(command: str, code: int, outcome: RunOutcome) -> None:
    assert runs.outcome_from_exit_code(command, code) is outcome


def test_a_finished_result_without_a_live_snapshot_leaves_build_invalid_unknown(
    tmp_path: Path,
) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    syn.write_result(
        out / "target-explore" / f"{rid}-result", syn.result(cases=[syn.case("step-1", False)])
    )
    progress = runs.read_run(_explore_ref(out, rid)).progress
    assert progress is not None and progress.source is Source.RESULT
    assert progress.build_invalid is None  # not 0: result.json does not say


def test_symlinks_inside_the_scan_are_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    syn.write_result(outside / "node-tar-7.5.2", syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION))
    root = tmp_path / f"{syn.SYNTHETIC}-verify"
    root.mkdir()
    os.symlink(outside / "node-tar-7.5.2", root / "linked-cell")
    os.symlink(outside, root / "linked-tree")
    assert runs.discover_runs([root]) == []


def test_the_strict_readers_private_key_sets_still_exist() -> None:
    # runs.py reads these private names on purpose (target_result.py is not changed for the UI);
    # if they are renamed or removed this fails instead of the extras split drifting silently.
    from inodefence import target_result

    keys = target_result._CAMPAIGN_KEYS | target_result._CAMPAIGN_OPTIONAL
    assert {"seed", "budget", "runs_to_first_violation", "unjudged_steps"} <= keys
    assert keys <= runs._KNOWN_CAMPAIGN
