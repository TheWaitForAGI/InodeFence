"""Unit tests for the execution-method parity comparator (no Docker, no target)."""

from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.effect_campaign import (
    EffectCampaignConfig,
    EffectCampaignResult,
    run_effect_campaign,
)
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.execution_parity import (
    CanonicalSnapshot,
    ParityStep,
    ParitySubject,
    ResetVerification,
    canonical_object,
    canonical_snapshot,
    compare_subjects,
    extract_parity_subject,
    normalize_isolation,
)
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model.filesystem import ObjectSnapshot, ObjectType, SnapshotPhase, StateSnapshot
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance, ResourcePolicy
from inodefence.mutator import MutationPolicy

IMAGE_ID = "sha256:" + "a" * 64


def _run_synthetic_campaign(seed: int = 123, budget: int = 6) -> EffectCampaignResult:
    config = EffectCampaignConfig(
        random_seed=seed,
        execution_budget=budget,
        search_policy=EffectSearchPolicy.P1_EFFECT_RETENTION,
        mutation_policy=MutationPolicy.LEGACY,
    )
    return run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)


def _isolation() -> IsolationProvenance:
    policy = IsolationPolicy(IMAGE_ID, 1000, 1000, ResourcePolicy())
    return IsolationProvenance(
        policy, "docker-compatible", "27.0.0", "1.47", "linux", "amd64", "amd64"
    )


def _object(
    path: str, *, dev: int = 1, ino: int = 1, nlink: int = 1, content: bytes = b"x"
) -> ObjectSnapshot:
    return ObjectSnapshot(
        path,
        ObjectType.REGULAR,
        dev,
        ino,
        nlink,
        0o644,
        len(content),
        1000,
        1000,
        5,
        5,
        None,
        sha256(content).hexdigest(),
    )


def _snapshot(
    phase: SnapshotPhase, objects: tuple[ObjectSnapshot, ...], root: str
) -> StateSnapshot:
    return StateSnapshot(root, phase, objects, ("outside/sentinel",))


def _canon(objects: tuple[ObjectSnapshot, ...], groups=()) -> CanonicalSnapshot:
    return CanonicalSnapshot(
        phase="before",
        protected_paths=("outside/sentinel",),
        objects=tuple(canonical_object(obj) for obj in objects),
        identity_groups=groups,
    )


def _step(
    index: int, case_id: str, *, oracle=(("C0", False),), before=None, after=None, retry=0
) -> ParityStep:
    empty = CanonicalSnapshot("before", (), (), ())
    return ParityStep(
        index=index,
        case_id=case_id,
        oracle=oracle,
        feedback_keys=(),
        before=before or empty,
        after=after or empty,
        retry_count=retry,
    )


def _subject(
    label: str, steps: tuple[ParityStep, ...], *, isolation=None, resets=()
) -> ParitySubject:
    iso = None if isolation is None else normalize_isolation(isolation)
    return ParitySubject(label=label, steps=steps, isolation=iso, resets=resets)


# ---- canonicalization --------------------------------------------------------


def test_canonical_object_drops_identity_and_time_fields() -> None:
    a = _object("extract/f", dev=1, ino=1)
    b = _object("extract/f", dev=9, ino=9)  # same structure, different raw identity
    b = replace(b, mtime_ns=999, ctime_ns=999)
    assert canonical_object(a) == canonical_object(b)


def test_canonical_snapshot_excludes_sandbox_root() -> None:
    objs = (_object("extract/f"),)
    a = canonical_snapshot(_snapshot(SnapshotPhase.AFTER, objs, "/var/lib/inodefence/core-run-AAA"))
    b = canonical_snapshot(_snapshot(SnapshotPhase.AFTER, objs, "/var/lib/inodefence/core-run-BBB"))
    assert a == b


def test_canonical_snapshot_captures_identity_sharing() -> None:
    shared = (_object("extract/a", ino=7, nlink=2), _object("outside/b", ino=7, nlink=2))
    snap = canonical_snapshot(
        _snapshot(SnapshotPhase.AFTER, shared, "/var/lib/inodefence/core-run-X")
    )
    assert snap.identity_groups == (("extract/a", "outside/b"),)


# ---- extractor ---------------------------------------------------------------


def test_extract_parity_subject_contiguous_and_matches_campaign() -> None:
    result = _run_synthetic_campaign()
    subject = extract_parity_subject(result, label="synthetic")
    assert tuple(step.index for step in subject.steps) == tuple(range(len(result.steps)))
    assert [step.case_id for step in subject.steps] == [
        step.result.base_result.case.case_id for step in result.steps
    ]
    assert subject.retry_free is True


def test_two_runs_same_seed_are_parity_equal() -> None:
    result_a = _run_synthetic_campaign(seed=7)
    result_b = _run_synthetic_campaign(seed=7)
    clean = tuple(ResetVerification(i, False, False) for i in range(len(result_a.steps)))
    a = extract_parity_subject(result_a, label="per-case", isolation=_isolation(), resets=clean)
    b = extract_parity_subject(result_b, label="worker-pool", isolation=_isolation(), resets=clean)
    report = compare_subjects(a, b)
    assert report.passed is True
    assert report.core_parity is True
    assert report.both_retry_free is True
    assert all(dimension.agree for dimension in report.dimensions)


def test_different_seed_breaks_case_sequence() -> None:
    a = extract_parity_subject(_run_synthetic_campaign(seed=7), label="a")
    b = extract_parity_subject(_run_synthetic_campaign(seed=99), label="b")
    report = compare_subjects(a, b)
    # Seeds share the same initial cases but diverge once mutation starts.
    sequence = next(d for d in report.dimensions if d.name == "case_sequence")
    assert sequence.agree is False
    assert report.passed is False


# ---- dimension isolation: each meaningful diff hits exactly one dimension ----


def _pair(step_a: ParityStep, step_b: ParityStep, *, iso=True, resets=True):
    isolation = _isolation() if iso else None
    reset = (ResetVerification(0, False, False),) if resets else ()
    a = _subject("baseline", (step_a,), isolation=isolation, resets=reset)
    b = _subject("candidate", (step_b,), isolation=isolation, resets=reset)
    return compare_subjects(a, b)


def test_clean_identical_steps_pass_all_dimensions() -> None:
    objs = (_object("extract/f"),)
    before = _canon(objs)
    step = _step(0, "case-1", before=before, after=before)
    report = _pair(step, _step(0, "case-1", before=before, after=before))
    assert report.passed is True
    assert {d.name: d.agree for d in report.dimensions} == {
        "case_sequence": True,
        "oracle_and_feedback": True,
        "snapshots": True,
        "isolation_and_reset": True,
    }


def test_case_id_difference_fails_case_sequence_only() -> None:
    report = _pair(_step(0, "case-1"), _step(0, "case-2"))
    failed = {d.name for d in report.dimensions if not d.agree}
    assert failed == {"case_sequence"}


def test_oracle_difference_fails_oracle_dimension_only() -> None:
    report = _pair(
        _step(0, "case-1", oracle=(("C1", False),)),
        _step(0, "case-1", oracle=(("C1", True),)),
    )
    failed = {d.name for d in report.dimensions if not d.agree}
    assert failed == {"oracle_and_feedback"}


def test_content_digest_difference_fails_snapshots_only() -> None:
    before_a = _canon((_object("extract/f", content=b"x"),))
    before_b = _canon((_object("extract/f", content=b"y"),))
    report = _pair(
        _step(0, "case-1", before=before_a, after=before_a),
        _step(0, "case-1", before=before_b, after=before_b),
    )
    failed = {d.name for d in report.dimensions if not d.agree}
    assert failed == {"snapshots"}


def test_identity_partition_difference_fails_snapshots() -> None:
    # Same per-object canonical tuples, but a different inode-sharing partition.
    objs = (_object("extract/a", nlink=2), _object("outside/b", nlink=2))
    shared = _canon(objs, groups=(("extract/a", "outside/b"),))
    unshared = _canon(objs, groups=())
    report = _pair(
        _step(0, "case-1", before=shared, after=shared),
        _step(0, "case-1", before=unshared, after=unshared),
    )
    snapshots = next(d for d in report.dimensions if d.name == "snapshots")
    assert snapshots.agree is False
    assert any("partition" in line for line in snapshots.detail)


def test_isolation_mismatch_fails_isolation_dimension() -> None:
    other = IsolationProvenance(
        IsolationPolicy("sha256:" + "b" * 64, 1000, 1000, ResourcePolicy()),
        "docker-compatible",
        "27.0.0",
        "1.47",
        "linux",
        "amd64",
        "amd64",
    )
    a = _subject(
        "baseline",
        (_step(0, "case-1"),),
        isolation=_isolation(),
        resets=(ResetVerification(0, False, False),),
    )
    b = _subject(
        "candidate",
        (_step(0, "case-1"),),
        isolation=other,
        resets=(ResetVerification(0, False, False),),
    )
    report = compare_subjects(a, b)
    failed = {d.name for d in report.dimensions if not d.agree}
    assert failed == {"isolation_and_reset"}


def test_failed_reset_fails_isolation_dimension() -> None:
    a = _subject(
        "baseline",
        (_step(0, "case-1"),),
        isolation=_isolation(),
        resets=(ResetVerification(0, False, False),),
    )
    b = _subject(
        "candidate",
        (_step(0, "case-1"),),
        isolation=_isolation(),
        resets=(ResetVerification(0, True, False),),
    )
    report = compare_subjects(a, b)
    reset_dim = next(d for d in report.dimensions if d.name == "isolation_and_reset")
    assert reset_dim.agree is False
    assert report.passed is False


def test_missing_isolation_reports_not_provided() -> None:
    a = _subject("baseline", (_step(0, "case-1"),), isolation=None, resets=())
    b = _subject("candidate", (_step(0, "case-1"),), isolation=None, resets=())
    report = compare_subjects(a, b)
    reset_dim = next(d for d in report.dimensions if d.name == "isolation_and_reset")
    assert reset_dim.agree is False
    assert any("not provided" in line for line in reset_dim.detail)


# ---- retry handling (condition c) --------------------------------------------


def test_retried_step_is_excluded_from_headline_and_judged_separately() -> None:
    objs = (_object("extract/f"),)
    before = _canon(objs)
    # Baseline is retry-free; candidate retried step 1 but produced the same result.
    base_steps = (
        _step(0, "c0", before=before, after=before),
        _step(1, "c1", before=before, after=before),
    )
    cand_steps = (
        _step(0, "c0", before=before, after=before),
        _step(1, "c1", before=before, after=before, retry=2),
    )
    a = _subject(
        "baseline",
        base_steps,
        isolation=_isolation(),
        resets=(ResetVerification(0, False, False), ResetVerification(1, False, False)),
    )
    b = _subject(
        "candidate",
        cand_steps,
        isolation=_isolation(),
        resets=(ResetVerification(0, False, False), ResetVerification(1, False, False)),
    )
    report = compare_subjects(a, b)
    assert report.both_retry_free is False
    assert report.core_parity is True  # clean step 0 agrees on all dimensions
    assert len(report.retried_steps) == 1
    verdict = report.retried_steps[0]
    assert verdict.index == 1
    assert verdict.candidate_retries == 2
    assert verdict.matches_retry_free is True
    assert report.passed is True


def test_retried_step_with_divergent_result_fails_overall_but_core_holds() -> None:
    objs = (_object("extract/f", content=b"x"),)
    other = (_object("extract/f", content=b"y"),)
    clean = _canon(objs)
    before = _canon(objs)
    after_bad = _canon(other)
    base_steps = (
        _step(0, "c0", before=clean, after=clean),
        _step(1, "c1", before=before, after=before),
    )
    cand_steps = (
        _step(0, "c0", before=clean, after=clean),
        _step(1, "c1", before=before, after=after_bad, retry=1),
    )
    a = _subject(
        "baseline",
        base_steps,
        isolation=_isolation(),
        resets=(ResetVerification(0, False, False), ResetVerification(1, False, False)),
    )
    b = _subject(
        "candidate",
        cand_steps,
        isolation=_isolation(),
        resets=(ResetVerification(0, False, False), ResetVerification(1, False, False)),
    )
    report = compare_subjects(a, b)
    assert report.core_parity is True
    assert report.retried_steps[0].matches_retry_free is False
    assert report.passed is False


# ---- validation --------------------------------------------------------------


def test_parity_subject_requires_contiguous_indexes() -> None:
    with pytest.raises(ValueError):
        ParitySubject("x", (_step(0, "c0"), _step(2, "c2")), None, ())


def test_reset_verification_rejects_non_bool() -> None:
    with pytest.raises(ValueError):
        ResetVerification(0, True, "yes")  # type: ignore[arg-type]


def test_extract_rejects_wrong_type() -> None:
    with pytest.raises(ValueError):
        extract_parity_subject(object(), label="x")  # type: ignore[arg-type]
