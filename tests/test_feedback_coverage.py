"""Baseline D: target-agnostic structure-coverage admission, no identity/effect.

These tests pin the separation point for H1: D admits a mutation parent on a new
generic extraction-structure feature, never on object-identity relations
(StateSignature.identity_groups), external-effect labels
(StateSignature.external_effects) or content/size/mode changes. That is what lets
A/B/C-vs-D isolate the specific contribution of identity/external-effect feedback
from the general contribution of any feedback-guided retention. No effectiveness
claim is made here; these are engineering contracts.
"""

import random
from dataclasses import replace

import pytest

from inodefence.campaign import SearchCampaignConfig, run_search_campaign
from inodefence.feedback import (
    FeedbackProjection,
    SearchPolicy,
    SearchState,
    StructureCoverageFeature,
    structure_coverage_features,
)
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ObjectType, Region, SignatureObject, StateSignature
from inodefence.mutator import MutationPolicy
from inodefence.targets import PythonTarfileTarget
from test_feedback_corpus import _case, _object, _result
from test_feedback_projection import _changed_result, _pair


def _with_symlink(result):
    """Add an internal symlink so the extraction gains a new structural feature."""
    sandbox = result.after.sandbox_root
    link = replace(
        _object("extract/link"),
        object_type=ObjectType.SYMLINK,
        content_digest=None,
        symlink_target=sandbox + "/extract/output",
    )
    after = replace(
        result.after, objects=tuple(sorted((*result.after.objects, link), key=lambda o: o.path))
    )
    return _changed_result(result, after)


def _regular(path: str) -> SignatureObject:
    return SignatureObject(path, ObjectType.REGULAR, 0o644, 1, 5, "0" * 64, None)


def _signature(*objects: SignatureObject) -> StateSignature:
    return StateSignature(3, tuple(objects), (), (), ())


# --- Pure coverage projection ------------------------------------------------


@pytest.mark.parametrize("projection", (FeedbackProjection.A1, FeedbackProjection.A2))
def test_coverage_excludes_identity_and_external_effect_labels(projection):
    first, second = _pair(projection)
    label = "identity_groups" if projection == FeedbackProjection.A1 else "external_effects"
    # The canonical pair differs ONLY in the label D must ignore.
    assert getattr(second.signature, label) and not getattr(first.signature, label)
    assert first.signature != second.signature
    assert structure_coverage_features(first.signature) == structure_coverage_features(
        second.signature
    )


def test_coverage_excludes_content_size_and_mode():
    base = _result(_case("a")).signature
    other = _result(_case("b"), b"a considerably longer and different payload").signature
    assert base != other  # content digests and sizes differ
    assert structure_coverage_features(base) == structure_coverage_features(other)


def test_coverage_distinguishes_type_region_depth_and_symlink_anchor():
    feats = structure_coverage_features
    reg = _signature(_regular("extract/a"))
    deeper = _signature(_regular("extract/sub/a"))
    directory = _signature(
        SignatureObject("extract/a", ObjectType.DIRECTORY, 0o755, None, None, None, None)
    )
    external = _signature(_regular("outside/a"))
    run_link = _signature(
        SignatureObject("extract/l", ObjectType.SYMLINK, 0o777, None, None, None, "run:/x")
    )
    literal_link = _signature(
        SignatureObject("extract/l", ObjectType.SYMLINK, 0o777, None, None, None, "literal:/x")
    )
    assert feats(reg) != feats(deeper)  # path depth
    assert feats(reg) != feats(directory)  # object type
    assert feats(reg) != feats(external)  # namespace region
    assert feats(run_link) != feats(literal_link)  # symlink anchor class
    assert all(len(feats(s)) == 1 for s in (reg, deeper, directory, external, run_link))
    # Structurally identical objects collapse to a single coverage feature.
    assert len(feats(_signature(_regular("extract/a"), _regular("extract/b")))) == 1


def test_structure_coverage_feature_validation():
    for bad in (
        (ObjectType.REGULAR, Region.EXTRACTION, 0, "run"),  # non-symlink carries an anchor
        (ObjectType.SYMLINK, Region.EXTRACTION, 0, None),  # symlink missing its anchor
        (ObjectType.REGULAR, Region.EXTRACTION, -1, None),  # negative depth
        (ObjectType.SYMLINK, Region.EXTRACTION, 0, "weird"),  # unknown anchor class
    ):
        with pytest.raises(ValueError):
            StructureCoverageFeature(*bad)


def test_structure_coverage_requires_a_state_signature():
    with pytest.raises(ValueError):
        structure_coverage_features(object())  # type: ignore[arg-type]


# --- D admission via SearchState --------------------------------------------


def test_d_admits_new_structure_but_not_content_or_repeat():
    seed = _case("seed")
    state = SearchState((seed,), SearchPolicy.D)
    assert state.consider(_result(seed)).retained  # first structure is novel
    assert not state.consider(_result(_case("c"), b"different")).retained  # content only
    assert not state.consider(_result(_case("c2"))).retained  # identical structure
    assert state.consider(_with_symlink(_result(_case("link")))).retained  # new symlink feature
    assert not state.consider(_with_symlink(_result(_case("l2")))).retained  # structure now seen
    assert state.stats.retained_cases == 2


@pytest.mark.parametrize("projection", (FeedbackProjection.A1, FeedbackProjection.A2))
def test_d_ignores_identity_or_external_only_change_unlike_b3(projection):
    first, second = _pair(projection)
    for policy, admits in ((SearchPolicy.D, False), (SearchPolicy.B3, True)):
        state = SearchState((first.case,), policy)
        assert state.consider(first).retained
        decision = state.consider(second)
        # Full diagnostics are identical across policies; only admission differs.
        assert decision.state_novel and decision.interesting
        assert decision.new_violation_fingerprints
        assert decision.retained == admits


def test_d_uses_uniform_parent_pool_not_b0_active_walk():
    seed = _case("seed")
    state = SearchState((seed,), SearchPolicy.D)
    state.consider(_result(seed))
    state.consider(_with_symlink(_result(_case("link"))))
    assert len(state.entries) == 2 and state.active_case is None
    pool = state.entries
    rng, expected = random.Random(5), random.Random(5)
    assert [state.select_case(rng) for _ in range(40)] == [
        expected.choice(pool).case for _ in range(40)
    ]
    assert rng.getstate() == expected.getstate()


# --- D through the real run_search_campaign path ----------------------------


def test_d_runs_via_run_search_campaign_and_retains_by_structure_coverage():
    cases = minimal_seed_corpus()
    config = SearchCampaignConfig(11, 6, SearchPolicy.D, MutationPolicy.M1_NO_REORDER)
    result = run_search_campaign(cases, PythonTarfileTarget(), config)
    assert len(result.steps) == result.final_corpus_stats.observations == 6
    assert result.config.search_policy == SearchPolicy.D
    assert result.active_case_id is None  # coverage pool, not a B0 active child
    assert len(result.retained_case_ids) == result.final_corpus_stats.retained_cases
    assert len(result.retained_case_ids) >= 1  # at least the first structurally novel seed
    # Same seeds and budget: the unretained B0 walk keeps no corpus at all.
    b0 = run_search_campaign(
        cases, PythonTarfileTarget(), replace(config, search_policy=SearchPolicy.B0)
    )
    assert b0.retained_case_ids == ()
    # D's coverage-guided lineage is deterministic for a fixed seed/config, even
    # though fresh-runtime raw evidence (timestamps, inodes, sandbox) varies.
    rerun = run_search_campaign(cases, PythonTarfileTarget(), config)
    assert rerun.retained_case_ids == result.retained_case_ids
    assert [(s.origin, s.parent_case_id, s.feedback.retained) for s in rerun.steps] == [
        (s.origin, s.parent_case_id, s.feedback.retained) for s in result.steps
    ]
