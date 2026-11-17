"""#519 entry-level violation minimization, re-run check and signature (synthetic, no Docker)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from scripts.analysis.triage_violation_case import reserved, verdict_of

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.violation_triage import (
    Termination,
    TrialVerdict,
    cause_signature,
    minimize_entries,
    triage_record,
    verify,
)


def regular(path: str) -> ArchiveEntry:
    return ArchiveEntry(path, EntryType.REGULAR, content=b"x")


def hardlink(path: str, target: str) -> ArchiveEntry:
    return ArchiveEntry(path, EntryType.HARDLINK, link_target=target)


def symlink(path: str, target: str) -> ArchiveEntry:
    return ArchiveEntry(path, EntryType.SYMLINK, link_target=target, mode=0o777)


NOISE = [regular(f"n{i}.txt") for i in range(8)]
LINK = symlink("d", "../outside")
THROUGH = regular("d/x")
ESCAPE = hardlink("h", "../../o/s")


class Evaluator:
    """Synthetic target: C2 needs both LINK before THROUGH; C1 needs ESCAPE. Counts executions."""

    def __init__(
        self, *, flaky_after: int | None = None, unjudged_with: ArchiveEntry | None = None
    ):
        self.calls = 0
        self.flaky_after = flaky_after
        self.unjudged_with = unjudged_with

    def __call__(self, case: ArchiveCase) -> TrialVerdict:
        self.calls += 1
        entries = list(case.entries)
        if self.unjudged_with is not None and self.unjudged_with in entries and len(entries) < 4:
            return TrialVerdict(False, frozenset(), {"reason": "infrastructure"})
        violated = set()
        if LINK in entries and THROUGH in entries and entries.index(LINK) < entries.index(THROUGH):
            violated.add("C2")
        if ESCAPE in entries:
            violated.add("C1")
        if self.flaky_after is not None and self.calls > self.flaky_after:
            violated.discard("C1")
        return TrialVerdict(True, frozenset(violated), {"call": self.calls})


def case_of(entries: list[ArchiveEntry]) -> ArchiveCase:
    return ArchiveCase(tuple(entries))


def test_minimizes_to_the_entries_that_keep_the_exact_contract_set() -> None:
    case = case_of([NOISE[0], LINK, NOISE[1], NOISE[2], THROUGH, NOISE[3], ESCAPE, NOISE[4]])
    run = minimize_entries(case, Evaluator(), execution_budget=100)
    assert run.contracts == frozenset({"C1", "C2"})
    assert run.minimal.entries == (LINK, THROUGH, ESCAPE)  # original order kept
    assert run.termination is Termination.FIXED_POINT
    assert run.trials[0].entry_count == 8 and run.trials[0].kept


def test_a_subset_with_a_different_contract_set_is_not_kept() -> None:
    # Dropping ESCAPE leaves C2 only: a different verdict, so it must not be accepted.
    case = case_of([LINK, THROUGH, ESCAPE])
    run = minimize_entries(case, Evaluator(), execution_budget=100)
    assert run.minimal == case
    rejected = [trial for trial in run.trials if not trial.kept]
    assert rejected and all(trial.verdict.violated != run.contracts for trial in rejected)


def test_order_dependence_is_preserved() -> None:
    case = case_of([NOISE[0], LINK, THROUGH, NOISE[1]])
    run = minimize_entries(case, Evaluator(), execution_budget=100)
    assert run.minimal.entries == (LINK, THROUGH)


def test_unjudged_runs_are_never_kept() -> None:
    case = case_of([NOISE[0], LINK, NOISE[1], THROUGH, NOISE[2]])
    run = minimize_entries(case, Evaluator(unjudged_with=LINK), execution_budget=100)
    for trial in run.trials:
        if not trial.verdict.judged:
            assert not trial.kept
    assert len(run.minimal.entries) >= 4  # smaller subsets were un-judged and therefore refused


def test_budget_counts_executions_and_returns_the_best_so_far() -> None:
    case = case_of([*NOISE, LINK, THROUGH])
    evaluator = Evaluator()
    run = minimize_entries(case, evaluator, execution_budget=3)
    assert run.termination is Termination.BUDGET
    assert run.executions == evaluator.calls <= 3
    assert set(run.minimal.entries) >= {LINK, THROUGH}


def test_same_candidate_is_not_executed_twice() -> None:
    case = case_of([NOISE[0], LINK, THROUGH, NOISE[1], NOISE[2], NOISE[3]])
    evaluator = Evaluator()
    run = minimize_entries(case, evaluator, execution_budget=200)
    assert evaluator.calls == run.executions == len({trial.case_id for trial in run.trials})


def test_the_original_must_be_a_judged_violation() -> None:
    with pytest.raises(ValueError, match="not a judged violation"):
        minimize_entries(case_of([NOISE[0]]), Evaluator(), execution_budget=5)


def test_single_entry_minimum() -> None:
    run = minimize_entries(case_of([NOISE[0], ESCAPE, NOISE[1]]), Evaluator(), execution_budget=50)
    assert run.minimal.entries == (ESCAPE,)
    assert run.termination is Termination.SINGLE_ENTRY


def test_unencodable_candidates_are_skipped_without_running() -> None:
    long_path = regular("p" * 120)  # over the USTAR name field; the original must still encode
    with pytest.raises(ValueError):
        minimize_entries(case_of([long_path, ESCAPE]), Evaluator(), execution_budget=5)


def test_verify_reports_consistency_and_detects_a_nondeterministic_verdict() -> None:
    case = case_of([NOISE[0], LINK, THROUGH, ESCAPE])
    run = minimize_entries(case, Evaluator(), execution_budget=100)
    assert verify(run, Evaluator(), rounds=3).consistent
    flaky = Evaluator(flaky_after=2)  # C1 stops showing after two calls
    result = verify(run, flaky, rounds=3)
    assert not result.consistent


def test_signature_has_structure_but_no_names() -> None:
    case = case_of([LINK, THROUGH, ESCAPE])
    signature = cause_signature(case, frozenset({"C2", "C1"}))
    assert signature["contracts"] == ["C1", "C2"]
    assert [item["type"] for item in signature["entries"]] == ["symlink", "regular", "hardlink"]
    assert [item["target"] for item in signature["entries"]] == ["parent-1", None, "parent-2"]
    text = json.dumps(signature)
    for name in ("outside", "d/x", "../", "o/s", "sentinel"):
        assert name not in text


def test_signature_is_the_same_for_renamed_structure() -> None:
    a = case_of([symlink("d", "../a"), regular("d/x"), hardlink("h", "/abs")])
    b = case_of([symlink("q", "../zz"), regular("q/y"), hardlink("k", "/other")])
    assert cause_signature(a, frozenset({"C2"})) == cause_signature(b, frozenset({"C2"}))


def test_signature_marks_targets_that_point_at_another_entry() -> None:
    case = case_of([regular("a.txt"), hardlink("b.txt", "a.txt")])
    assert cause_signature(case, frozenset({"C1"}))["entries"][1]["target"] == "entry"


def test_record_is_json_and_states_the_seed_restriction() -> None:
    case = case_of([NOISE[0], LINK, THROUGH])
    run = minimize_entries(case, Evaluator(), execution_budget=50)
    record = triage_record(run, verify(run, Evaluator(), rounds=1), label="exploratory test")
    text = json.dumps(record)
    assert "never a seed or corpus entry" in record["use_restriction"]
    assert record["original"]["entries"] == 3 and record["minimal"]["entries"] == 2
    assert record["verification"]["consistent"] is True
    assert "tar_b64" not in text  # no TAR bytes in the record


# -- the real-extractor script's pure helpers (no Docker) ----------------------------------------


@pytest.mark.parametrize(
    ("version", "refused"),
    [
        ("7.0.0", True),
        ("7.4.3", True),
        ("7.4.4", False),
        ("6.2.1", True),
        ("6.2.2", False),
        ("4.4.0", True),
        ("5.0.9", True),
        ("5.1.0", False),
        ("7.5.23", False),
        ("latest", True),
    ],
)
def test_reserved_node_tar_versions_are_refused(version: str, refused: bool) -> None:
    assert reserved("node-tar", version) is refused


def test_other_targets_are_not_subject_to_the_node_tar_reservation() -> None:
    assert not reserved("decompress", "decompress@4.2.1")


def _run(complete: bool, rounds: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(complete=complete, rounds=tuple(rounds), stop_reason=None)


def test_a_judged_round_becomes_its_contract_set() -> None:
    round_ = {
        "outcome": "judged",
        "c0": True,
        "c1": False,
        "c2": None,
        "observation_complete": True,
    }
    verdict = verdict_of(_run(True, [round_]))
    assert verdict.judged and verdict.violated == frozenset({"C0"})


@pytest.mark.parametrize(
    "run",
    [
        _run(False, []),
        _run(True, [{"outcome": "run_error", "c0": None, "c1": None, "c2": None}]),
        _run(True, [{"outcome": "judged", "c0": True, "observation_complete": False}]),
        _run(True, [{"outcome": "judged", "c0": None, "c1": None, "c2": None}]),
    ],
)
def test_incomplete_or_unjudged_runs_are_unjudged(run: SimpleNamespace) -> None:
    verdict = verdict_of(run)
    assert not verdict.judged and not verdict.violated
