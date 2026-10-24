"""M3: observed boundary-approach feedback (P3 arm), additive over P0/P1/P2.

The key is derived from observed symlink state (ObjectSnapshot.symlink_target whose
text escapes the extraction root), target-agnostic (no path, protected object or CVE),
and only under the opt-in P3 arm. P0/P1/P2 and benign loops stay unchanged.
"""

from dataclasses import replace

import pytest

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_synthetic import _result, synthetic_effect_result
from inodefence.feedback import (
    EffectSearchPolicy,
    EffectSearchState,
    observed_boundary_escape_keys,
)
from inodefence.feedback.effect import _boundary_escape_shape
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    BoundaryEscapeShape,
    EffectClass,
    EffectFeedbackKeyKind,
    EntryType,
    ObservedBoundaryEscapeSignature,
)
from inodefence.mutator import MutationPolicy

SYMLINK_CASE = ArchiveCase(
    (
        ArchiveEntry("a.txt", EntryType.REGULAR, b"x"),
        ArchiveEntry("link", EntryType.SYMLINK, link_target="a.txt"),
    )
)


def _with_observed_symlink_target(result, target: str | None):
    """Rewrite only the observed readlink text of the trace's symlink creation events."""
    events = []
    for event in result.trace.effect_events:
        if event.effect_class == EffectClass.SYMLINK_CREATION:
            item = event.object_evidence[0]
            obj = replace(item.after.object, symlink_target=target)
            after = replace(item.after, object=obj)
            event = replace(event, object_evidence=(replace(item, after=after),))
        events.append(event)
    return replace(result, trace=replace(result.trace, effect_events=tuple(events)))


@pytest.mark.parametrize(
    "object_path, target, expected",
    [
        ("extract/link", "../outside/x", BoundaryEscapeShape.PARENT_1),
        ("extract/a/link", "../../outside/x", BoundaryEscapeShape.PARENT_2),
        ("extract/link", "../../../x", BoundaryEscapeShape.PARENT_3_PLUS),
        ("extract/link", "/etc/passwd", BoundaryEscapeShape.ABSOLUTE),
        ("extract/link", "sub/file", None),
        ("extract/link", "a.txt", None),
        ("extract/link", "", None),
    ],
)
def test_boundary_escape_shape_classifies_only_root_escaping_targets(object_path, target, expected):
    assert _boundary_escape_shape(object_path, target) == expected


def test_non_escaping_symlink_yields_no_boundary_key() -> None:
    # Stock synthetic symlinks carry the benign target "target" (stays inside extract/).
    assert observed_boundary_escape_keys(_result(SYMLINK_CASE).trace) == ()


def test_escaping_symlink_yields_one_observed_boundary_key() -> None:
    result = _with_observed_symlink_target(_result(SYMLINK_CASE), "../outside/x")

    keys = observed_boundary_escape_keys(result.trace)

    assert len(keys) == 1
    key = keys[0]
    assert key.kind == EffectFeedbackKeyKind.OBSERVED_BOUNDARY_ESCAPE
    signature = key.signature
    assert isinstance(signature, ObservedBoundaryEscapeSignature)
    assert signature.escape_shape == BoundaryEscapeShape.PARENT_1
    assert signature.object_type.value == "symlink"
    assert signature.object_region.value == "extraction"


def test_p3_keys_the_boundary_escape_while_p2_does_not() -> None:
    result = _with_observed_symlink_target(_result(SYMLINK_CASE), "../outside/x")

    p2 = EffectSearchState((SYMLINK_CASE,), EffectSearchPolicy.P2_EFFECT_ADAPTIVE).consider(result)
    p3 = EffectSearchState((SYMLINK_CASE,), EffectSearchPolicy.P3_BOUNDARY_GRADIENT).consider(
        result
    )

    def boundary(decision):
        kind = EffectFeedbackKeyKind.OBSERVED_BOUNDARY_ESCAPE
        return [k for k in decision.new_effect_keys if k.kind == kind]

    assert boundary(p2) == []
    assert len(boundary(p3)) == 1
    # P3 is a strict superset of P2's keys for the same observation.
    assert set(p2.new_effect_keys).issubset(set(p3.new_effect_keys))
    assert p3.admission_eligible and p3.effect_novel


def test_p3_campaign_is_deterministic_and_adaptive() -> None:
    config = EffectCampaignConfig(
        random_seed=123,
        execution_budget=12,
        search_policy=EffectSearchPolicy.P3_BOUNDARY_GRADIENT,
        mutation_policy=MutationPolicy.M1,
    )

    first = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    second = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)

    assert first == second
    # Adaptive scheduler is wired for P3 (mutation steps carry scheduler evidence).
    mutations = first.steps[len(first.initial_case_ids) :]
    assert all(step.scheduler_evidence is not None for step in mutations)
