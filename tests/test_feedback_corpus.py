"""Pure Layer 5 contracts; raw filesystem behavior is covered in integration tests."""

import random
from dataclasses import FrozenInstanceError, fields, replace
from hashlib import sha256

import pytest

from inodefence.feedback import (
    ChangeFingerprint,
    Corpus,
    CorpusEntry,
    CorpusStats,
    FeedbackDecision,
    IdentityFingerprint,
    ViolationFingerprint,
    state_signature,
    violation_fingerprints,
)
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ChangeField,
    ContractId,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    IdentityEvidence,
    ObjectSnapshot,
    ObjectType,
    RunResult,
    SnapshotPhase,
    StateChange,
    StateSnapshot,
    ViolationResult,
)
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts


def _case(name: str) -> ArchiveCase:
    return ArchiveCase((ArchiveEntry(name, EntryType.REGULAR, content=b"input"),))


def _object(path: str, content: bytes = b"state", inode: int = 10) -> ObjectSnapshot:
    return ObjectSnapshot(
        path,
        ObjectType.REGULAR,
        1,
        inode,
        1,
        0o600,
        len(content),
        1000,
        1000,
        10,
        10,
        content_digest=sha256(content).hexdigest(),
    )


def _result(case: ArchiveCase, content: bytes = b"state") -> RunResult:
    """Coherent synthetic run with a fixed safe output, independent of input text."""
    sentinel = _object("outside/sentinel.txt")
    before = StateSnapshot(
        "/var/lib/inodefence/synthetic",
        SnapshotPhase.BEFORE,
        (sentinel,),
        (sentinel.path,),
    )
    after = replace(
        before,
        phase=SnapshotPhase.AFTER,
        objects=(_object("extract/output", content, inode=20), sentinel),
    )
    return RunResult(
        case,
        case.case_id,
        "synthetic-test",
        ExecutionResult("controlled", "test", (), ExecutionStatus.SUCCESS, 0, "", "", 0.0),
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )


def test_c1_fingerprint_ignores_raw_inode_and_device_allocation() -> None:
    first = ViolationResult(
        ContractId.C1,
        True,
        (IdentityEvidence("extract/a", "outside/sentinel.txt", 1, 10),),
        "shared identity",
        (),
    )
    second = replace(
        first,
        evidence=(IdentityEvidence("extract/a", "outside/sentinel.txt", 91, 9000),),
    )
    assert first.evidence != second.evidence
    assert (
        violation_fingerprints((first,))
        == violation_fingerprints((second,))
        == (
            ViolationFingerprint(
                ContractId.C1,
                (IdentityFingerprint("extract/a", "outside/sentinel.txt"),),
            ),
        )
    )


def test_different_case_identity_with_same_state_is_not_novel() -> None:
    first, second = _result(_case("a")), _result(_case("b"))
    assert first.case.case_id != second.case.case_id
    assert first.archive_sha256 != second.archive_sha256
    assert first.signature == second.signature
    corpus = Corpus()
    assert corpus.consider(first).retained
    decision = corpus.consider(second)
    assert not decision.state_novel and not decision.new_violation_fingerprints
    assert not decision.interesting and not decision.retained and not decision.already_retained
    assert len(corpus) == 1


def _identity(internal_path: str = "extract/a", inode: int = 10) -> ViolationResult:
    return ViolationResult(
        ContractId.C1,
        True,
        (IdentityEvidence(internal_path, "outside/sentinel.txt", 1, inode),),
        "controlled identity evidence",
        (),
    )


def _creation(path: str = "archive/escaped.txt") -> ViolationResult:
    change = StateChange(path, None, _object(path), (ChangeField.EXISTENCE,))
    return ViolationResult(ContractId.C0, True, (change,), "controlled namespace evidence", ())


def test_identity_path_relation_distinction() -> None:
    first = violation_fingerprints((_identity("extract/a"),))
    assert first != violation_fingerprints((_identity("extract/b"),))
    other_sentinel = replace(
        _identity(),
        evidence=(IdentityEvidence("extract/a", "outside/second", 1, 10),),
    )
    assert first != violation_fingerprints((other_sentinel,))


def test_contract_id_distinguishes_otherwise_identical_change_evidence() -> None:
    c0 = _creation("outside/sentinel.txt")
    c2 = replace(c0, contract_id=ContractId.C2)
    first, second = violation_fingerprints((c0,))[0], violation_fingerprints((c2,))[0]
    assert first.evidence == second.evidence and first != second


def test_changed_field_labels_distinguish_content_from_mode() -> None:
    before = _object("outside/sentinel.txt")
    content = StateChange(
        before.path,
        before,
        replace(before, content_digest="0" * 64),
        (ChangeField.CONTENT,),
    )
    mode = StateChange(before.path, before, replace(before, mode=0o640), (ChangeField.MODE,))
    c2 = ViolationResult(ContractId.C2, True, (content,), "content", ())
    assert violation_fingerprints((c2,)) != violation_fingerprints((replace(c2, evidence=(mode,)),))


@pytest.mark.parametrize("contract", (ContractId.C0, ContractId.C2))
def test_change_fingerprint_excludes_raw_observation_values(contract: ContractId) -> None:
    before = _object("outside/sentinel.txt")
    after = replace(before, st_ino=11, mtime_ns=12, ctime_ns=13, content_digest="0" * 64)
    labels = (ChangeField.IDENTITY, ChangeField.MTIME, ChangeField.CTIME, ChangeField.CONTENT)
    first_change = StateChange(before.path, before, after, labels)
    second_change = StateChange(
        before.path,
        replace(before, st_dev=91, st_ino=9000, mtime_ns=1200, ctime_ns=1300),
        replace(
            after, st_dev=91, st_ino=9001, mtime_ns=1201, ctime_ns=1301, content_digest="1" * 64
        ),
        labels,
    )
    first = ViolationResult(contract, True, (first_change,), "first explanation", ())
    second = replace(first, evidence=(second_change,))
    assert first.evidence != second.evidence
    assert (
        violation_fingerprints((first,))
        == violation_fingerprints((second,))
        == (ViolationFingerprint(contract, (ChangeFingerprint(before.path, labels),)),)
    )


@pytest.mark.parametrize("violation", (_identity(), _creation()))
def test_explanation_and_limitations_do_not_change_fingerprint(violation: ViolationResult) -> None:
    changed = replace(violation, explanation="different prose", limitations=("different limits",))
    assert changed != violation
    assert violation_fingerprints((changed,)) == violation_fingerprints((violation,))


def test_nonviolations_do_not_produce_fingerprints() -> None:
    safe = tuple(ViolationResult(contract, False, (), "no evidence", ()) for contract in ContractId)
    assert violation_fingerprints(()) == violation_fingerprints(safe) == ()
    assert violation_fingerprints((*safe, _identity())) == violation_fingerprints((_identity(),))


def test_fingerprint_evidence_and_result_order_is_canonical_and_duplicate_independent() -> None:
    a = IdentityEvidence("extract/a", "outside/sentinel.txt", 1, 10)
    b = IdentityEvidence("extract/b", "outside/sentinel.txt", 1, 10)
    c1 = replace(_identity(), evidence=(b, a, b))
    change_a = _creation("archive/a").evidence[0]
    change_b = _creation("archive/b").evidence[0]
    c0 = replace(_creation(), evidence=(change_b, change_a, change_b))
    c2 = replace(c0, contract_id=ContractId.C2)
    fingerprints = violation_fingerprints((c2, c1, c0, c1))
    assert fingerprints == (
        ViolationFingerprint(
            ContractId.C0,
            (
                ChangeFingerprint("archive/a", (ChangeField.EXISTENCE,)),
                ChangeFingerprint("archive/b", (ChangeField.EXISTENCE,)),
            ),
        ),
        ViolationFingerprint(
            ContractId.C1,
            (
                IdentityFingerprint("extract/a", "outside/sentinel.txt"),
                IdentityFingerprint("extract/b", "outside/sentinel.txt"),
            ),
        ),
        ViolationFingerprint(
            ContractId.C2,
            (
                ChangeFingerprint("archive/a", (ChangeField.EXISTENCE,)),
                ChangeFingerprint("archive/b", (ChangeField.EXISTENCE,)),
            ),
        ),
    )
    assert fingerprints == violation_fingerprints(
        (
            replace(c0, evidence=(change_a, change_b)),
            replace(c1, evidence=(a, b)),
            replace(c2, evidence=(change_a, change_b)),
        )
    )


def test_whole_contract_evidence_tuple_defines_a_violation_class() -> None:
    single = _identity()
    combined = replace(single, evidence=(*single.evidence, *_identity("extract/b").evidence))
    assert violation_fingerprints((single,)) != violation_fingerprints((combined,))


def test_first_safe_state_is_retained_with_compact_admission_metadata() -> None:
    corpus = Corpus()
    assert len(corpus) == 0 and corpus.entries == ()
    assert corpus.stats == CorpusStats(0, 0, 0, 0, 0)
    result = _result(_case("a"))
    decision = corpus.consider(result)
    assert decision == FeedbackDecision(result.case.case_id, True, (), False)
    assert decision.interesting and decision.retained
    assert corpus.entries == (CorpusEntry(result.case, result.signature, ()),)
    assert {field.name for field in fields(corpus.entries[0])} == {
        "case",
        "admission_signature",
        "admission_violation_fingerprints",
    }
    assert corpus.stats == CorpusStats(1, 1, 1, 1, 0)


def test_repeated_observation_has_no_novelty_and_no_duplicate_entry() -> None:
    corpus = Corpus()
    result = _result(_case("a"))
    corpus.consider(result)
    entries = corpus.entries
    decision = corpus.consider(replace(result, case=ArchiveCase(tuple(result.case.entries))))
    assert decision == FeedbackDecision(result.case.case_id, False, (), True)
    assert not decision.interesting and not decision.retained
    assert corpus.entries == entries and corpus.stats == CorpusStats(2, 1, 1, 1, 0)


def test_new_normalized_state_retains_a_different_case() -> None:
    corpus = Corpus()
    first, second = _result(_case("a")), _result(_case("b"), b"new state")
    assert first.signature != second.signature
    corpus.consider(first)
    decision = corpus.consider(second)
    assert decision.state_novel and decision.interesting and decision.retained
    assert decision.new_violation_fingerprints == ()
    assert tuple(entry.case for entry in corpus.entries) == (first.case, second.case)
    assert corpus.stats == CorpusStats(2, 2, 2, 2, 0)


def test_same_state_new_violation_and_repeated_semantic_violation() -> None:
    corpus = Corpus()
    safe = _result(_case("safe"))
    first = replace(_result(_case("first")), violations=(_identity(),))
    second = replace(_result(_case("second")), violations=(_identity(inode=9999),))
    assert safe.signature == first.signature == second.signature
    corpus.consider(safe)
    decision = corpus.consider(first)
    assert not decision.state_novel and decision.retained
    assert decision.new_violation_fingerprints == violation_fingerprints(first.violations)
    repeated = corpus.consider(second)
    assert not repeated.state_novel and repeated.new_violation_fingerprints == ()
    assert not repeated.interesting and not repeated.retained and not repeated.already_retained
    assert corpus.stats == CorpusStats(3, 2, 2, 1, 1)


def test_new_violation_subset_is_reported_in_canonical_order() -> None:
    corpus = Corpus()
    first = replace(_result(_case("first")), violations=(_identity(),))
    corpus.consider(first)
    c0 = _creation()
    c2 = replace(_creation("outside/sentinel.txt"), contract_id=ContractId.C2)
    result = replace(_result(_case("second")), violations=(c2, _identity(), c0))
    decision = corpus.consider(result)
    assert decision.new_violation_fingerprints == violation_fingerprints((c0, c2))
    assert not decision.state_novel and decision.retained
    # Admission describes the whole admitting observation, including already-seen classes.
    assert corpus.entries[-1].admission_violation_fingerprints == violation_fingerprints(
        result.violations
    )
    assert corpus.stats == CorpusStats(2, 2, 2, 1, 3)


def test_retained_case_new_outcomes_advance_both_indexes_without_duplicate_insertion() -> None:
    corpus = Corpus()
    case = _case("a")
    first = _result(case)
    corpus.consider(first)
    admission = corpus.entries[0]
    changed = replace(_result(case, b"new state"), violations=(_creation(),))
    decision = corpus.consider(changed)
    assert decision.state_novel and decision.new_violation_fingerprints
    assert decision.interesting and decision.already_retained and not decision.retained
    assert corpus.stats == CorpusStats(2, 2, 1, 2, 1)
    # A new case observing either of these outcomes must see the advanced indexes.
    repeated_state = corpus.consider(_result(_case("b"), b"new state"))
    repeated_violation = corpus.consider(replace(_result(_case("c")), violations=(_creation(),)))
    for repeated in (repeated_state, repeated_violation):
        assert not repeated.state_novel and not repeated.new_violation_fingerprints
        assert not repeated.interesting and not repeated.retained and not repeated.already_retained
    assert corpus.entries == (admission,) and corpus.stats == CorpusStats(4, 2, 1, 2, 1)


def test_retained_case_violation_only_novelty_updates_index_and_preserves_admission() -> None:
    corpus = Corpus()
    first = _result(_case("a"))
    corpus.consider(first)
    admission = corpus.entries
    changed = replace(first, violations=(_creation(),))
    decision = corpus.consider(changed)
    assert not decision.state_novel and decision.new_violation_fingerprints
    assert decision.interesting and decision.already_retained and not decision.retained
    repeated = corpus.consider(replace(changed, case=_case("b")))
    assert not repeated.interesting and not repeated.retained
    assert corpus.entries == admission and corpus.stats == CorpusStats(3, 2, 1, 1, 1)


@pytest.mark.parametrize("state_novel", (False, True))
@pytest.mark.parametrize("has_violation", (False, True))
@pytest.mark.parametrize("already_retained", (False, True))
def test_decision_properties_distinguish_interesting_observation_from_entry(
    state_novel: bool,
    has_violation: bool,
    already_retained: bool,
) -> None:
    fingerprints = violation_fingerprints((_creation(),)) if has_violation else ()
    decision = FeedbackDecision("case", state_novel, fingerprints, already_retained)
    assert decision.interesting == (state_novel or has_violation)
    assert decision.retained == ((state_novel or has_violation) and not already_retained)


def test_empty_selection_fails_explicitly_without_consuming_rng() -> None:
    corpus, rng = Corpus(), random.Random(1234)
    initial = rng.getstate()
    with pytest.raises(ValueError, match="empty corpus"):
        corpus.select_case(rng)
    assert rng.getstate() == initial and corpus.stats == CorpusStats(0, 0, 0, 0, 0)


def _populated_corpus() -> Corpus:
    corpus = Corpus()
    for name in ("z", "a", "m"):
        assert corpus.consider(_result(_case(name), name.encode())).retained
    return corpus


def test_selection_is_uniform_over_insertion_order_and_deterministic_from_rng_state() -> None:
    first, second = _populated_corpus(), _populated_corpus()
    rng, restored, reference = random.Random(1234), random.Random(999), random.Random(0)
    rng.random()  # Exercise an advanced state instead of only the seed.
    restored.setstate(rng.getstate())
    reference.setstate(rng.getstate())
    entries, stats = first.entries, first.stats
    parents = tuple(entry.case for entry in entries)
    selections = tuple(first.select_case(rng) for _ in range(64))
    assert selections == tuple(second.select_case(restored) for _ in range(64))
    assert selections == tuple(reference.choice(parents) for _ in range(64))
    assert set(selections) == set(parents)
    assert rng.getstate() == restored.getstate() == reference.getstate()
    assert first.entries == entries and first.stats == stats


def test_selection_uses_only_caller_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_global_random(*args: object, **kwargs: object) -> None:
        raise AssertionError("selection must use caller RNG only")

    initial = random.getstate()
    for name in (
        "seed",
        "random",
        "choice",
        "choices",
        "randrange",
        "randint",
        "sample",
        "shuffle",
    ):
        monkeypatch.setattr(random, name, fail_global_random)
    corpus, rng = _populated_corpus(), random.Random(1234)
    for _ in range(16):
        assert corpus.select_case(rng) in tuple(entry.case for entry in corpus.entries)
    assert random.getstate() == initial


def test_exposed_records_are_frozen_slots_values_and_containers_are_snapshots() -> None:
    corpus = Corpus()
    first = _result(_case("a"))
    decision = corpus.consider(first)
    entries, stats = corpus.entries, corpus.stats
    assert isinstance(entries, tuple)
    # Extending the caller's tuple cannot affect the corpus.
    extended = (*entries, entries[0])
    assert len(extended) == 2 and len(corpus) == 1
    records = (
        (decision, "state_novel", False),
        (stats, "observations", 99),
        (entries[0], "case", _case("other")),
        (ChangeFingerprint("archive/a", (ChangeField.EXISTENCE,)), "path", "archive/b"),
        (IdentityFingerprint("extract/a", "outside/sentinel.txt"), "internal_path", "extract/b"),
        (violation_fingerprints((_creation(),))[0], "evidence", ()),
    )
    for record, field, value in records:
        with pytest.raises(FrozenInstanceError):
            setattr(record, field, value)
        assert not hasattr(record, "__dict__")
    assert corpus.consider(_result(_case("b"), b"new state")).retained
    assert entries == (CorpusEntry(first.case, first.signature, ()),)
    assert stats == CorpusStats(1, 1, 1, 1, 0)
    assert len(corpus.entries) == 2 and corpus.stats == CorpusStats(2, 2, 2, 2, 0)
