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


def test_fields_the_strict_reader_knows_are_read_as_fields_not_extras(tmp_path: Path) -> None:
    # Since #535 the reader knows campaign.mutation_policy and campaign.identity_checks; valid
    # values are ordinary fields (validated, no extras).
    from inodefence.mutator import MutationPolicy
    from inodefence.target_result import FAST_ACCEPTANCE_NOT_MEASURED, per_case_identity_marker

    data = syn.result(cases=[syn.case("step-1", False)]).to_json_dict()
    data["campaign"]["mutation_policy"] = MutationPolicy.V2_FREEZE3_FIXED_BASELINE.value
    data["campaign"]["identity_checks"] = per_case_identity_marker(
        "decompress", FAST_ACCEPTANCE_NOT_MEASURED
    )
    summary = runs.read_result(syn.write_result(tmp_path / "k", syn.result(),
                                                text=json.dumps(data)))  # fmt: skip
    assert summary.read_state is ReadState.OK and summary.validated
    assert summary.extras == {}


def test_a_key_the_strict_reader_does_not_know_is_kept_in_extras(tmp_path: Path) -> None:
    data = syn.result(cases=[syn.case("step-1", False)]).to_json_dict()
    data["campaign"]["future_key"] = {"from": "a newer version"}
    summary = runs.read_result(syn.write_result(tmp_path / "f", syn.result(),
                                                text=json.dumps(data)))  # fmt: skip
    assert summary.read_state is ReadState.OK and summary.validated
    assert summary.extras == {"future_key": {"from": "a newer version"}}


def test_an_invalid_known_record_or_derived_field_is_unvalidated(tmp_path: Path) -> None:
    data = syn.result(cases=[syn.case("step-1", False)]).to_json_dict()
    data["campaign"]["identity_checks"] = {"interval": 1}  # no total_checks, not a D065 marker
    bad = runs.read_result(syn.write_result(tmp_path / "b", syn.result(),
                                            text=json.dumps(data)))  # fmt: skip
    assert bad.read_state is ReadState.UNVALIDATED and not bad.validated
    assert bad.error and "identity_checks" in bad.error  # the reader's own reason
    del data["campaign"]["identity_checks"]
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


def test_an_unreadable_folder_is_listed_not_raised(tmp_path: Path) -> None:
    root = tmp_path / f"{syn.SYNTHETIC}-verify"
    locked = root / "locked"
    locked.mkdir(parents=True)
    os.chmod(locked, 0)
    try:
        listings = runs.discover_runs([root])
    finally:
        os.chmod(locked, 0o755)
    if os.geteuid() == 0:
        pytest.skip("root reads any folder")
    (listing,) = listings
    assert listing.path == locked and listing.read_state is ReadState.UNREADABLE and listing.error


def test_the_launcher_step_is_not_attached_to_an_ended_run(tmp_path: Path) -> None:
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    log = out / "runtime" / "explore-launcher-20260101T000000Z-1.log"
    log.parent.mkdir(parents=True)
    log.write_text("==> [run controller]\n", encoding="utf-8")
    syn.write_result(out / "target-explore" / f"{rid}-result", syn.result())
    snap = runs.read_run(_explore_ref(out, rid))
    assert snap.launcher_log is None
    assert snap.progress is not None and snap.progress.launcher_step is None
    finished = syn.run_id(2)
    syn.live_run(out, finished, [syn.step(0)], close="finished")
    progress = runs.read_run(_explore_ref(out, finished)).progress
    assert progress is not None and progress.launcher_step is None


def test_read_verify_and_read_result_name_target_and_version(tmp_path: Path) -> None:
    verify = tmp_path / f"{syn.SYNTHETIC}-verify"
    syn.write_result(verify / "node-tar-7.5.2", syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION))
    py = syn.result(target="python-tarfile", mode=syn.ResultMode.FIXTURE_REGRESSION)
    data = py.to_json_dict()
    data["axes"] = {
        "target_version": None,
        "runtime_version": "3.12.7",
        "extraction_filter": "data",
    }
    syn.write_result(verify / "python-tarfile-3.12.7-data", py, text=json.dumps(data))
    cells = {s.ref.run_id: s.ref for s in runs.read_verify(verify) if s.ref}
    assert (cells["node-tar-7.5.2"].target, cells["node-tar-7.5.2"].version) == (
        "node-tar",
        "7.5.2",
    )
    python = cells["python-tarfile-3.12.7-data"]
    assert (python.target, python.version) == ("python-tarfile", "3.12.7")
    assert runs.read_result(verify / "node-tar-7.5.2" / "result.json").ref is None  # no ref given


def test_list_artifacts_is_metadata_only_and_marks_missing(tmp_path: Path, monkeypatch) -> None:
    from inodefence.app.runs import ArtifactKind, list_artifacts

    out, rid = syn.explore_out(tmp_path), syn.run_id()
    syn.live_run(out, rid, [syn.step(0, c1=True, fp="c1-a")])
    result_dir = out / "target-explore" / f"{rid}-result"
    syn.write_result(result_dir, syn.result(cases=[syn.case("step-1", True)], saved=["step-1"]))
    syn.replay(result_dir, {"case_id": "step-1", "c0": False, "c1": True, "c2": False},
               [syn.judged_round(True)])  # fmt: skip
    snap = runs.read_run(_explore_ref(out, rid))
    opened: list[str] = []
    real_open = Path.open

    def spy(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        opened.append(str(self))
        return real_open(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", spy)
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(AssertionError))
    entries = list_artifacts(snap)
    assert opened == []  # stat only: no file is opened
    kinds = [entry.kind for entry in entries]
    for kind in (ArtifactKind.RESULT, ArtifactKind.LIVE_PROGRESS, ArtifactKind.CASE_FOLDER,
                 ArtifactKind.INPUT_TAR, ArtifactKind.REPLAY):  # fmt: skip
        assert kind in kinds
    tar = next(e for e in entries if e.kind is ArtifactKind.INPUT_TAR and e.case_id == "step-1")
    assert tar.tar_sha256 and tar.size == len(syn.TAR) and tar.mtime is not None
    folder = next(e for e in entries if e.kind is ArtifactKind.CASE_FOLDER)
    assert folder.size is None and folder.read_state is ReadState.OK
    (tmp_path / "gone").mkdir()
    gone = runs.read_run(RunRef(RunKind.VERIFY, tmp_path / "gone", "gone"))
    (entry,) = list_artifacts(gone)
    assert entry.kind is ArtifactKind.RESULT and entry.read_state is ReadState.MISSING
    assert entry.size is None and entry.mtime is None


def test_list_artifacts_never_follows_links_and_marks_unreadable(tmp_path: Path) -> None:
    from inodefence.app.runs import ArtifactKind, list_artifacts

    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x" * 12345)
    out, rid = syn.explore_out(tmp_path), syn.run_id()
    result_dir = out / "target-explore" / f"{rid}-result"
    syn.write_result(result_dir, syn.result(cases=[syn.case("step-2", True)], saved=["step-2"]))
    tar = result_dir / "inputs" / "step-2.tar"
    tar.unlink()
    os.symlink(outside, tar)  # an input that is a link to a file outside the run folder
    os.symlink(outside, result_dir / "runtime-record.json")
    os.symlink(outside, out / "target-explore" / f"inodefence-effect-explore-{rid}.json")
    entries = list_artifacts(runs.read_run(_explore_ref(out, rid)))
    linked = [e for e in entries if e.symlink]
    assert {e.kind for e in linked} == {ArtifactKind.INPUT_TAR, ArtifactKind.RUNTIME_RECORD}
    assert all(e.size is None and e.read_state is ReadState.UNREADABLE for e in linked)
    assert all(e.size != 12345 for e in entries)  # the outside file is never measured
    assert ArtifactKind.LOOP_REPORT not in {e.kind for e in entries}  # globs skip links


def test_an_entry_that_cannot_be_stat_ed_is_unreadable_not_ok(tmp_path: Path) -> None:
    from inodefence.app.runs import ArtifactKind, list_artifacts

    if os.geteuid() == 0:
        pytest.skip("root stats any file")
    cell = tmp_path / f"{syn.SYNTHETIC}-verify" / "node-tar-7.5.2"
    syn.write_result(cell, syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION, saved=["fixture"],
                                      cases=[syn.case("fixture", False)]))  # fmt: skip
    snap = runs.read_run(RunRef(RunKind.VERIFY, cell, cell.name))
    os.chmod(cell / "inputs", 0)  # the input below cannot be stat-ed
    try:
        entries = list_artifacts(snap)
    finally:
        os.chmod(cell / "inputs", 0o755)
    (tar,) = [e for e in entries if e.kind is ArtifactKind.INPUT_TAR]
    assert tar.read_state is ReadState.UNREADABLE and tar.size is None


def test_a_summary_carries_the_result_files_mtime(tmp_path: Path) -> None:
    cell = tmp_path / f"{syn.SYNTHETIC}-verify" / "node-tar-7.5.2"
    path = syn.write_result(cell, syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION))
    os.utime(path, (1_800_000_000, 1_800_000_000))
    (summary,) = runs.read_verify(cell.parent)
    assert summary.result_mtime == 1_800_000_000
    assert runs.read_result(tmp_path / "absent" / "result.json").result_mtime is None
    linked = tmp_path / "linked"
    linked.mkdir()
    os.symlink(path, linked / "result.json")
    assert runs.read_result(linked / "result.json").result_mtime is None  # a link is not followed


def test_the_535_fields_read_ok(tmp_path: Path) -> None:
    # #535 shapes, built with main's own constants: a node-tar interval record with its scope
    # label, and a replay whose rounds carry additive-detector columns.
    from tests.test_fast_identity_driver import RECORD

    from inodefence.target_result import FAST_ACCEPTANCE_PASSED, NODE_TAR_ACCEPTED_FAST_SCOPE

    data = syn.result(cases=[syn.case("step-1", False)]).to_json_dict()
    data["campaign"]["identity_checks"] = {
        **RECORD,
        "fast_acceptance": FAST_ACCEPTANCE_PASSED,
        "acceptance_scope": NODE_TAR_ACCEPTED_FAST_SCOPE,
    }
    summary = runs.read_result(syn.write_result(tmp_path / "s", syn.result(),
                                                text=json.dumps(data)))  # fmt: skip
    assert summary.read_state is ReadState.OK and summary.validated and summary.extras == {}
    case_dir = tmp_path / "violations" / "run-000001"
    case_dir.mkdir(parents=True)
    path = syn.replay(case_dir, {"c0": False, "c1": True, "c2": False}, [syn.judged_round(True)])
    record = json.loads(path.read_text(encoding="utf-8"))
    record["rounds"][0]["additive_detectors"] = {"family": "additive-detectors-v1 (record-only)"}
    record["summary"]["fingerprints_comparable"] = False
    record["summary"]["same_fingerprints"] = None
    path.write_text(json.dumps(record), encoding="utf-8")
    replay = runs.read_replay(path)
    assert replay.read_state is ReadState.OK and replay.same_fingerprints is None  # not 0


# -- QA real-run defects on #549 candidate 02554c7 (D2, D3, candidate vs known fixture) ------------


def _fixture_cell(tmp_path: Path, *, termination: str | None) -> Path:
    cell = tmp_path / "verify" / "node-tar-7.5.2"
    cases = [syn.case("toplevel_hardlink", True, termination=termination),
             syn.case("dir_symlink_write", False, termination=termination)]  # fmt: skip
    return syn.write_result(cell, syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION, cases=cases))


def test_a_verify_cell_without_terminations_reports_them_unknown_not_zero(tmp_path: Path) -> None:
    path = _fixture_cell(tmp_path, termination=None)
    summary = runs.read_result(path)
    assert summary.read_state is ReadState.OK
    assert dict(summary.terminations) == dict.fromkeys(
        ("success", "rejected", "failed", "timed_out")
    )
    assert summary.no_extraction_warning is None
    snapshot = runs.read_run(runs.RunRef(runs.RunKind.VERIFY, path.parent, path.parent.name))
    assert snapshot.progress is not None
    assert all(v is None for v in snapshot.progress.terminations.values())


def test_recorded_terminations_are_still_counted(tmp_path: Path) -> None:
    summary = runs.read_result(_fixture_cell(tmp_path, termination="success"))
    assert summary.terminations["success"] == 2 and summary.terminations["failed"] == 0


def test_a_fixture_regression_violation_is_a_known_fixture_not_a_candidate(tmp_path: Path) -> None:
    path = _fixture_cell(tmp_path, termination=None)
    summary = runs.read_result(path)
    hardlink = next(row for row in summary.cases if row.case_id == "toplevel_hardlink")
    assert hardlink.violated and hardlink.known_fixture and hardlink.fixture_violation
    assert hardlink.finding is None  # never a candidate, so never "needs repro check"
    assert summary.candidates == () and [r.case_id for r in summary.fixture_violations] == [
        "toplevel_hardlink"
    ]
    snapshot = runs.read_run(runs.RunRef(runs.RunKind.VERIFY, path.parent, path.parent.name))
    assert snapshot.findings == ()
    assert [r.case_id for r in snapshot.fixture_violations] == ["toplevel_hardlink"]


def test_the_classification_follows_the_mode_even_when_unvalidated(tmp_path: Path) -> None:
    path = _fixture_cell(tmp_path, termination=None)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["runs"]["executed"] = 99  # refused by the strict reader: values as stored
    path.write_text(json.dumps(data), encoding="utf-8")
    summary = runs.read_result(path)
    assert summary.read_state is ReadState.UNVALIDATED
    assert summary.candidates == () and len(summary.fixture_violations) == 1


def test_an_exploration_violation_is_still_a_candidate(tmp_path: Path) -> None:
    res = syn.result(cases=[syn.case("step-1", True)])
    summary = runs.read_result(syn.write_result(tmp_path / "e", res))
    assert [row.finding for row in summary.candidates] == [runs.FindingClass.CANDIDATE]
    assert summary.fixture_violations == ()


def _launcher_log(out: Path, stamp: str = "20261120T021743Z") -> Path:
    log = out / runs.RUNTIME_DIR / f"explore-launcher-{stamp}-4242.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("==> [preflight]\n==> [python-tarfile-effect-campaign]\n", encoding="utf-8")
    return log


def test_a_run_with_only_its_launcher_log_is_listed_as_running(tmp_path: Path) -> None:
    out = tmp_path / "pt-out"
    _launcher_log(out)
    refs = [listing.ref for listing in runs.discover_runs([out]) if listing.ref]
    assert [(r.kind, r.root, r.run_id) for r in refs] == [(runs.RunKind.EXPLORE, out, None)]
    snapshot = runs.read_run(refs[0])
    assert snapshot.summary is None and snapshot.findings == ()
    assert snapshot.progress is not None and snapshot.progress.source is runs.Source.LAUNCHER_LOG
    assert snapshot.progress.launcher_step == "python-tarfile-effect-campaign"
    assert snapshot.progress.runs is None  # unknown mid-run, never 0


def test_the_launcher_only_listing_ends_with_the_runtime_record(tmp_path: Path) -> None:
    out = tmp_path / "pt-out"
    log = _launcher_log(out)
    record = out / runs.RUNTIME_DIR / "py3.12.16-data-1-20-20261120T021743Z.json"
    record.write_text("{}", encoding="utf-8")
    later = log.stat().st_mtime + 1
    os.utime(record, (later, later))
    assert [listing.ref for listing in runs.discover_runs([out]) if listing.ref] == []


def test_an_id_less_run_never_takes_an_older_runs_folders(tmp_path: Path) -> None:
    out = syn.explore_out(tmp_path)
    old = syn.run_id(1)
    syn.live_run(out, old, [syn.step(1, c1=True)], close="finished")
    syn.write_result(out / "target-explore" / f"{old}-result",
                     syn.result(cases=[syn.case("step-1", True)]))  # fmt: skip
    for folder in (out / "target-explore").rglob("*"):
        os.utime(folder, (1_000_000_000, 1_000_000_000))  # written long before the new launch
    _launcher_log(out)
    pending = [x.ref for x in runs.discover_runs([out]) if x.ref and x.ref.run_id is None]
    assert len(pending) == 1
    snapshot = runs.read_run(pending[0])
    assert snapshot.summary is None and snapshot.findings == ()


def test_a_running_node_tar_run_is_not_listed_twice(tmp_path: Path) -> None:
    out = syn.explore_out(tmp_path)
    _launcher_log(out, stamp="20000101T000000Z")  # started before its live folder was written
    syn.live_run(out, syn.run_id(1), [syn.step(1)])
    refs = [x.ref for x in runs.discover_runs([out]) if x.ref]
    assert [r.run_id for r in refs] == [syn.run_id(1)]


def test_a_launcher_only_run_is_active_while_its_log_is_written(tmp_path: Path) -> None:
    out = tmp_path / "pt-out"
    log = _launcher_log(out)
    (ref,) = [x.ref for x in runs.discover_runs([out]) if x.ref]
    written = log.stat().st_mtime
    snapshot = runs.read_run(ref, now=written + 30)
    state = snapshot.launcher_state
    assert state is not None and state.estimated and state.log == log
    assert state.activity is runs.LaunchActivity.ACTIVE and state.age_seconds == pytest.approx(30)


def test_a_launcher_only_run_gone_quiet_is_no_activity_not_running(tmp_path: Path) -> None:
    out = tmp_path / "pt-out"
    log = _launcher_log(out)
    (ref,) = [x.ref for x in runs.discover_runs([out]) if x.ref]
    later = log.stat().st_mtime + runs.LAUNCHER_QUIET_MAX_SECONDS + 1
    state = runs.read_run(ref, now=later).launcher_state
    assert state is not None and state.activity is runs.LaunchActivity.NO_ACTIVITY
    assert (
        runs.launcher_activity(0.0, runs.LAUNCHER_QUIET_MAX_SECONDS) is runs.LaunchActivity.ACTIVE
    )


def test_runs_with_their_own_folders_have_no_launcher_state(tmp_path: Path) -> None:
    out = syn.explore_out(tmp_path)
    _launcher_log(out, stamp="20000101T000000Z")
    syn.live_run(out, syn.run_id(1), [syn.step(1)])
    snapshot = runs.read_run(runs.RunRef(runs.RunKind.EXPLORE, out, syn.run_id(1)))
    assert snapshot.launcher_state is None


def test_the_quiet_limit_follows_the_launchers_build_deadline() -> None:
    import re

    script = Path(__file__).resolve().parents[1] / "scripts" / "launcher_bounded.sh"
    match = re.search(r"^DEADLINE_BUILD=(\d+)", script.read_text(encoding="utf-8"), re.M)
    assert match is not None
    assert runs.LAUNCHER_QUIET_MAX_SECONDS == int(match[1]) + 120


_SHAPE_KEYS = ("provenance", "preparation", "benign_control", "repro_inputs", "cases",
               "observed_contracts", "campaign", "runs", "axes",
               "verdict", "label", "mode")  # fmt: skip


@pytest.mark.parametrize("key", _SHAPE_KEYS)
@pytest.mark.parametrize("value", ["broken", 7, ["x"], None, {"a": 1}])
def test_a_wrongly_shaped_section_never_raises(tmp_path: Path, key: str, value: object) -> None:
    # QA: "provenance": "broken" raised AttributeError and took the whole web run list down (500)
    path = _fixture_cell(tmp_path, termination=None)
    data = json.loads(path.read_text(encoding="utf-8"))
    data[key] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    summary = runs.read_result(path)
    assert summary.read_state in (ReadState.OK, ReadState.UNVALIDATED, ReadState.UNREADABLE)
    if summary.read_state is not ReadState.OK:
        assert summary.error
    snapshot = runs.read_run(runs.RunRef(runs.RunKind.VERIFY, path.parent, path.parent.name))
    assert snapshot.ref.root == path.parent


def test_a_broken_provenance_reads_as_stored_with_unknown_integrity(tmp_path: Path) -> None:
    path = _fixture_cell(tmp_path, termination=None)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["provenance"] = "broken"
    path.write_text(json.dumps(data), encoding="utf-8")
    summary = runs.read_result(path)
    assert summary.read_state is ReadState.UNVALIDATED and summary.integrity is not None
    assert summary.integrity.engine_sha is None and summary.integrity.image_id is None
    assert len(summary.fixture_violations) == 1  # still classified by mode


def test_one_broken_cell_does_not_hide_the_others(tmp_path: Path) -> None:
    good = _fixture_cell(tmp_path, termination=None)
    bad = tmp_path / "verify" / "node-tar-7.5.3" / "result.json"
    bad.parent.mkdir(parents=True)
    data = json.loads(good.read_text(encoding="utf-8"))
    data["provenance"] = "broken"
    data["preparation"] = 3
    bad.write_text(json.dumps(data), encoding="utf-8")
    found = [x.ref for x in runs.discover_runs([tmp_path / "verify"]) if x.ref]
    assert {r.run_id for r in found} == {"node-tar-7.5.2", "node-tar-7.5.3"}
    states = {r.run_id: runs.read_run(r).summary.read_state for r in found}  # type: ignore[union-attr]
    assert states["node-tar-7.5.2"] is ReadState.OK
    assert states["node-tar-7.5.3"] is ReadState.UNVALIDATED


def test_an_unforeseen_error_in_one_run_is_that_runs_unreadable_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _fixture_cell(tmp_path, termination=None)
    ref = runs.RunRef(runs.RunKind.VERIFY, path.parent, path.parent.name)

    def explode(*_: object, **__: object) -> None:
        raise RuntimeError("unforeseen")

    monkeypatch.setattr(runs, "read_result", explode)
    snapshot = runs.read_run(ref, now=1.0)
    assert snapshot.ref is ref and snapshot.summary is not None
    assert snapshot.summary.read_state is ReadState.UNREADABLE
    assert snapshot.read_errors and "RuntimeError: unforeseen" in snapshot.read_errors[0]


def test_a_folder_that_breaks_discovery_is_listed_not_fatal(tmp_path: Path) -> None:
    _fixture_cell(tmp_path, termination=None)  # tmp/verify/node-tar-7.5.2
    odd = tmp_path / "verify" / "odd-out"
    _launcher_log(odd, stamp="20261399T999999Z")  # matches the name pattern, not a real time
    listings = runs.discover_runs([tmp_path / "verify"])
    assert [x.ref.run_id for x in listings if x.ref] == ["node-tar-7.5.2"]
    (broken,) = [x for x in listings if x.ref is None]
    assert broken.path == odd and broken.read_state is ReadState.UNREADABLE and broken.error


_BROKEN_MODES = ["broken", "", 7, None, ["fixture-regression"], {"mode": "fixture-regression"}]


def _broken_mode_cell(tmp_path: Path, mode: object) -> Path:
    path = _fixture_cell(tmp_path, termination=None)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["mode"] = mode
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("mode", _BROKEN_MODES)
def test_a_verify_cell_with_a_broken_mode_still_holds_fixtures(
    tmp_path: Path, mode: object
) -> None:
    # ORCH/QA: a broken mode made the cell's fixture violation a "needs repro check" candidate
    path = _broken_mode_cell(tmp_path, mode)
    ref = runs.RunRef(runs.RunKind.VERIFY, path.parent, path.parent.name)
    snapshot = runs.read_run(ref)
    assert snapshot.summary is not None
    assert snapshot.summary.read_state is ReadState.UNVALIDATED
    assert snapshot.findings == () and snapshot.summary.candidates == ()
    assert [r.case_id for r in snapshot.fixture_violations] == ["toplevel_hardlink"]
    assert snapshot.unclassified_violations == ()


@pytest.mark.parametrize("mode", _BROKEN_MODES)
def test_with_neither_mode_nor_kind_a_violation_is_unclassified(
    tmp_path: Path, mode: object
) -> None:
    summary = runs.read_result(_broken_mode_cell(tmp_path, mode))  # no ref: kind unknown
    assert summary.read_state is ReadState.UNVALIDATED
    assert summary.candidates == () and summary.fixture_violations == ()
    (row,) = summary.unclassified_violations
    assert row.known_fixture is None and row.finding is None and row.case_id == "toplevel_hardlink"


def test_a_broken_mode_in_an_exploration_keeps_its_candidates(tmp_path: Path) -> None:
    out = syn.explore_out(tmp_path)
    rid = syn.run_id()
    path = syn.write_result(out / "target-explore" / f"{rid}-result",
                            syn.result(cases=[syn.case("step-1", True)]))  # fmt: skip
    data = json.loads(path.read_text(encoding="utf-8"))
    data["mode"] = 7
    path.write_text(json.dumps(data), encoding="utf-8")
    snapshot = runs.read_run(runs.RunRef(runs.RunKind.EXPLORE, out, rid))
    assert [r.case_id for r in snapshot.findings] == ["step-1"]
    assert snapshot.fixture_violations == () and snapshot.unclassified_violations == ()


def test_a_non_string_case_id_the_strict_reader_accepts_does_not_crash_the_read(
    tmp_path: Path,
) -> None:
    """#552: the strict reader lets a numeric case_id through on a non-violated case; the read model
    must not raise on it (it has no run number), and compare must not raise either."""
    data = json.loads(
        (Path(__file__).parent / "fixtures" / "result-contract-v1" / "campaign.json").read_text(
            encoding="utf-8"
        )
    )
    violated = set(data["violating_cases"])
    index = next(i for i, c in enumerate(data["cases"]) if c["case_id"] not in violated)
    data["cases"][index]["case_id"] = 7
    path = tmp_path / "result.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    summary = runs.read_result(path)
    assert summary.read_state is ReadState.OK and summary.validated
    assert 7 in [row.case_id for row in summary.cases]
    assert runs.compare_results(summary, summary)  # rows built, nothing raised
