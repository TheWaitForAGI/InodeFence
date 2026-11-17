"""#519 entry-level violation minimization, re-run check and signature (synthetic, no Docker)."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.analysis.triage_violation_case import (
    EXIT_CONSISTENT,
    EXIT_NONDETERMINISTIC,
    EXIT_NOT_REPRODUCED,
    MINIMUM_FILE,
    exit_code,
    reserved,
    summary_line,
    verdict_of,
)

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.violation_triage import (
    NONDETERMINISTIC_LABEL,
    NOT_A_RESULT_LABEL,
    Determinism,
    KeepRule,
    ResultStatus,
    Termination,
    TriagePolicy,
    TrialVerdict,
    cause_signature,
    minimize_entries,
    triage,
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
    outcome = triage(case, Evaluator(), TriagePolicy(baseline_runs=3, verify_rounds=1))
    record = triage_record(outcome, label="exploratory test")
    text = json.dumps(record)
    assert "never a seed or corpus entry" in record["use_restriction"]
    minimization = record["minimization"]
    assert minimization["original"]["entries"] == 3 and minimization["minimal"]["entries"] == 2
    assert record["verification"]["consistent"] is True
    assert record["determinism"] == "deterministic" and record["reference_only"] is False
    assert record["counts"]["baseline_runs"] == 3
    assert "tar_b64" not in text  # no TAR bytes in the record


# -- nondeterministic targets (W4 ruling 2026-11-18): k-of-n rule -----------------------------


class Flaky:
    """The C2 structure (LINK before THROUGH) violates on every ``period``-th call only."""

    def __init__(self, period: int = 2) -> None:
        self.calls = 0
        self.period = period

    def __call__(self, case: ArchiveCase) -> TrialVerdict:
        self.calls += 1
        entries = list(case.entries)
        structure = (
            LINK in entries and THROUGH in entries and entries.index(LINK) < entries.index(THROUGH)
        )
        hit = structure and self.calls % self.period == 0
        termination = "success" if hit else "rejected"
        return TrialVerdict(True, frozenset({"C2"}) if hit else frozenset(), {"t": termination})


def test_default_counts_are_the_w4_numbers() -> None:
    policy = TriagePolicy()
    assert policy.baseline_runs == 10
    assert policy.nondeterministic_keep == KeepRule(5, 1)
    assert policy.final_runs == 20


@pytest.mark.parametrize(("runs", "min_hits"), [(0, 1), (5, 0), (5, 6)])
def test_keep_rule_bounds(runs: int, min_hits: int) -> None:
    with pytest.raises(ValueError):
        KeepRule(runs, min_hits)


def test_a_deterministic_case_keeps_the_original_rule() -> None:
    case = case_of([NOISE[0], LINK, NOISE[1], THROUGH, ESCAPE])
    outcome = triage(case, Evaluator(), TriagePolicy())
    assert outcome.determinism is Determinism.DETERMINISTIC
    assert outcome.baseline.hits == outcome.baseline.runs == 10
    assert outcome.run is not None and outcome.run.keep == KeepRule(1, 1)
    assert outcome.run.minimal.entries == (LINK, THROUGH, ESCAPE)
    assert outcome.consistent is True and outcome.final is None
    assert exit_code(outcome) == EXIT_CONSISTENT
    assert summary_line(outcome, "t", "1").startswith("TRIAGE CONSISTENT")


def test_a_nondeterministic_case_is_marked_and_minimized_k_of_n() -> None:
    case = case_of([NOISE[0], LINK, NOISE[1], THROUGH, NOISE[2]])
    outcome = triage(case, Flaky(period=2), TriagePolicy())
    assert outcome.determinism is Determinism.NONDETERMINISTIC
    assert outcome.baseline.runs == 10 and 0 < outcome.baseline.hits < 10
    run = outcome.run
    assert run is not None and run.keep == KeepRule(5, 1)
    assert run.minimal.entries == (LINK, THROUGH)
    # every candidate was run 5 times and its hit count recorded
    assert all(len(trial.verdicts) == 5 for trial in run.trials if not trial.reused)
    assert all(trial.kept == (trial.hits >= 1) for trial in run.trials)
    final = outcome.final
    assert final is not None and final.runs == 20 and final.case_id == run.minimal.case_id
    assert outcome.verification is None and outcome.consistent is None
    record = triage_record(outcome, label="t")
    assert record["reference_only"] is True and record["note"] == NONDETERMINISTIC_LABEL
    assert record["final"]["runs"] == 20 and record["baseline"]["runs"] == 10
    assert all("rate" in trial for trial in record["minimization"]["trials"])
    assert exit_code(outcome) == EXIT_NONDETERMINISTIC
    line = summary_line(outcome, "t", "1")
    assert line.startswith("TRIAGE NONDETERMINISTIC")
    assert f"original {outcome.baseline.hits}/10" in line and f"minimal {final.hits}/20" in line
    assert "reference only" in line


def test_a_rare_violation_can_fall_below_the_keep_rule() -> None:
    # Hits only every 7th call: a 1-of-5 candidate may see none and be rejected; that is the
    # documented looseness the n = 20 re-measurement makes visible, not an error.
    case = case_of([NOISE[0], LINK, THROUGH])
    outcome = triage(case, Flaky(period=7), TriagePolicy())
    assert outcome.determinism is Determinism.NONDETERMINISTIC
    assert outcome.final is not None and outcome.final.runs == 20


def test_an_original_that_never_violates_is_not_minimized() -> None:
    outcome = triage(case_of([NOISE[0], NOISE[1]]), Evaluator(), TriagePolicy(baseline_runs=4))
    assert outcome.determinism is Determinism.NOT_REPRODUCED
    assert outcome.run is None and outcome.final is None and outcome.verification is None
    assert exit_code(outcome) == EXIT_NOT_REPRODUCED
    assert summary_line(outcome, "t", "1").startswith("TRIAGE NOT REPRODUCED")


def test_budget_counts_every_run_of_a_k_of_n_candidate() -> None:
    case = case_of([*NOISE, LINK, THROUGH])
    flaky = Flaky(period=2)
    run = minimize_entries(
        case,
        flaky,
        execution_budget=12,
        contracts=frozenset({"C2"}),
        keep=KeepRule(5, 1),
    )
    assert run.termination is Termination.BUDGET
    assert run.executions == flaky.calls <= 12


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


# -- seed/corpus contamination guard and result status (QA notes 2026-11-18) -------------------

REPO = Path(__file__).resolve().parents[1]
#: The only non-test modules allowed to import the triage module (analysis output, not search).
TRIAGE_IMPORTERS = {Path("scripts/analysis/triage_violation_case.py")}


def _imports_triage(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.endswith("violation_triage") for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (
            (node.module or "").endswith("violation_triage")
            or any(alias.name == "violation_triage" for alias in node.names)
        ):
            return True
    return False


def test_no_engine_search_corpus_or_registered_path_imports_the_triage_module() -> None:
    """Minimized inputs and signatures can never reach a seed or corpus: nothing that searches,
    keeps a corpus, generates seeds or runs a registered experiment imports this module."""
    offenders = sorted(
        str(path.relative_to(REPO))
        for root in ("src", "scripts")
        for path in (REPO / root).rglob("*.py")
        if path.relative_to(REPO) not in TRIAGE_IMPORTERS
        and path.name != "violation_triage.py"
        and _imports_triage(path)
    )
    assert offenders == []


def test_status_and_minimum_file_name() -> None:
    deterministic = triage(case_of([NOISE[0], LINK, THROUGH]), Evaluator(), TriagePolicy())
    assert deterministic.status is ResultStatus.RESULT
    assert MINIMUM_FILE[deterministic.status] == "minimal.tar"
    flaky = triage(case_of([NOISE[0], LINK, THROUGH]), Flaky(period=2), TriagePolicy())
    assert flaky.status is ResultStatus.REFERENCE_ONLY
    assert MINIMUM_FILE[flaky.status] == "minimal.reference-only.tar"
    never = triage(case_of([NOISE[0]]), Evaluator(), TriagePolicy(baseline_runs=2))
    assert never.status is ResultStatus.NOT_A_RESULT and never.status not in MINIMUM_FILE


def test_a_failed_recheck_is_not_a_result_and_has_no_signature() -> None:
    class FlipsAfterBaseline(Evaluator):
        def __call__(self, case: ArchiveCase) -> TrialVerdict:
            verdict = super().__call__(case)
            # deterministic for the 10 baseline runs, then the verdict disappears
            return verdict if self.calls <= 10 else TrialVerdict(True, frozenset(), {})

    outcome = triage(case_of([LINK, THROUGH]), FlipsAfterBaseline(), TriagePolicy())
    assert outcome.determinism is Determinism.DETERMINISTIC and outcome.consistent is False
    assert outcome.status is ResultStatus.NOT_A_RESULT
    record = triage_record(outcome, label="t")
    assert record["result_status"] == "not-a-result"
    assert record["note"] == NOT_A_RESULT_LABEL
    assert record["minimization"]["signature"] is None
    assert exit_code(outcome) == EXIT_NOT_REPRODUCED
