"""M3: token-clean generic escape + state-aware composition (A1/A2/A3 arms).

Removes target-specific tokens from the escaping-hardlink vocabulary (so the generic
alphabet cannot spell an external reference target's name — the reachability floor),
and lets a run compose link targets from the names of objects it actually observed in
the general filesystem tree (target-agnostic reach). These tests are deterministic
(fixed RNG seeds) and prove reachability at the mutation level without any native run.
"""

import random

from inodefence.effect_campaign import (
    EffectCampaignConfig,
    _observed_name_segments,
    run_effect_campaign,
)
from inodefence.effect_synthetic import _result, synthetic_effect_result
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.mutator import MutationOperatorId, MutationPolicy, apply_operator, m1
from inodefence.mutator.m1_addressing import state_aware_escape_operators

BASE = ArchiveCase((ArchiveEntry("a.txt", EntryType.REGULAR, content=b"x"),))


def _escape_targets(pool: tuple[str, ...], n: int = 5000) -> list[str]:
    """Collect escaping-hardlink link targets over n fixed RNG seeds for one pool."""
    targets: list[str] = []
    for seed in range(n):
        child = m1.add_escaping_hardlink(BASE, random.Random(seed), components=pool)
        for entry in child.entries:
            if (
                entry.entry_type == EntryType.HARDLINK
                and entry.link_target
                and entry.link_target.startswith("..")
            ):
                targets.append(entry.link_target)
    return targets


def _segments(targets: list[str]) -> set[str]:
    return {seg for target in targets for seg in target.split("/")}


def test_generic_escape_cannot_spell_a_target_specific_name() -> None:
    # The generic vocabulary has no target-specific token, so no generated escaping
    # target can contain one. This is the reachability floor (A1).
    segments = _segments(_escape_targets(m1.COMPONENTS))
    assert "outside" not in segments
    assert "sentinel.txt" not in segments
    assert segments <= set(m1.COMPONENTS)


def test_state_aware_pool_can_compose_an_observed_external_path() -> None:
    # Given the names it observed (here "outside"/"sentinel.txt"), the state-aware
    # pool can compose the external path — reachability (A2/A3).
    pool = m1.COMPONENTS + ("outside", "sentinel.txt")
    targets = _escape_targets(pool)
    assert "../outside/sentinel.txt" in targets


def test_state_aware_reach_is_name_independent() -> None:
    # With different observed names, the same mechanism composes the different path,
    # and never invents the previous target's tokens — the reach is not tied to any
    # specific name.
    pool = m1.COMPONENTS + ("ext", "ref.dat")
    targets = _escape_targets(pool)
    assert "../ext/ref.dat" in targets
    segments = _segments(targets)
    assert "sentinel.txt" not in segments and "outside" not in segments


def test_state_aware_factory_empty_pool_matches_generic() -> None:
    # No observed names supplied => identical to the generic escape operator set.
    empty = state_aware_escape_operators(())
    generic = m1.add_escaping_hardlink
    # slot 5 is the escaping-hardlink operator; identical output over fixed seeds.
    for seed in range(200):
        a = empty[5](BASE, random.Random(seed))
        b = generic(BASE, random.Random(seed), components=m1.COMPONENTS)
        assert a == b


def test_apply_operator_rejects_extra_components_for_other_policies() -> None:
    import pytest

    with pytest.raises(ValueError, match="state-aware"):
        apply_operator(
            BASE,
            random.Random(0),
            MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK,
            MutationOperatorId.ADD_HARDLINK,
            extra_components=("outside",),
        )


def test_observed_name_segments_source_objects_not_protected_list() -> None:
    # The pool is drawn from observed object paths (general tree). The synthetic
    # snapshot carries an external object "outside/sentinel", so its segments appear.
    result = _result(BASE)
    names = _observed_name_segments(result)
    object_paths = {obj.path for obj in result.trace.before.objects}
    assert any("/" in p and p.split("/")[0] == "outside" for p in object_paths)
    assert "outside" in names and "sentinel" in names
    # "." and ".." are never contributed as composable names.
    assert "." not in names and ".." not in names


def test_state_aware_campaign_is_deterministic() -> None:
    config = EffectCampaignConfig(
        random_seed=123,
        execution_budget=12,
        search_policy=EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT,
        mutation_policy=MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK,
    )
    first = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    second = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    assert first == second
    mutations = first.steps[len(first.initial_case_ids) :]
    assert mutations and all(step.scheduler_evidence is not None for step in mutations)


def test_blind_observed_names_drop_external_region_only() -> None:
    # The blind control observes the same tree but excludes EXTERNAL-region objects,
    # so a name that exists only outside the extraction boundary (here the external
    # "outside/sentinel") never enters the pool, while EXTRACTION/HARNESS names the
    # run produced are kept. The filter is by common Region, not by a specific name.
    from inodefence.model.filesystem import Region, path_region

    result = _result(BASE)
    full = _observed_name_segments(result)
    blind = _observed_name_segments(result, exclude_external=True)
    # "outside"/"sentinel" exist only in the EXTERNAL object, so the blind pool drops them.
    assert "outside" in full and "sentinel" in full
    assert "outside" not in blind and "sentinel" not in blind
    assert blind < full
    # Exact characterization: the blind pool is precisely the non-EXTERNAL segments.
    non_external = {
        seg
        for snapshot in (result.trace.before, result.trace.after)
        for obj in snapshot.objects
        if path_region(obj.path) != Region.EXTERNAL
        for seg in obj.path.split("/")
        if seg and seg not in (".", "..")
    }
    assert blind == non_external


def test_blind_policy_accepts_extra_components() -> None:
    # The blind control is a state-aware policy, so apply_operator accepts its
    # (externally filtered) observed-name pool just like the full policy.
    attempt = apply_operator(
        BASE,
        random.Random(0),
        MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND,
        MutationOperatorId.ADD_HARDLINK,
        extra_components=("dir", "item"),
    )
    assert attempt.mutation_policy == MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND


def test_blind_state_aware_campaign_is_deterministic() -> None:
    config = EffectCampaignConfig(
        random_seed=123,
        execution_budget=12,
        search_policy=EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT,
        mutation_policy=MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_BLIND,
    )
    first = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    second = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    assert first == second
    mutations = first.steps[len(first.initial_case_ids) :]
    assert mutations and all(step.scheduler_evidence is not None for step in mutations)
