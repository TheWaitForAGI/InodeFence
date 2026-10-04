"""Ablations affect admission keys while full observations remain inspectable."""

import json
from dataclasses import replace

import pytest

from inodefence.feedback import (
    FeedbackProjection,
    SearchPolicy,
    SearchState,
    feedback_key,
    state_signature,
)
from inodefence.model import ObjectType, canonical_json
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts
from test_feedback_corpus import _case, _object, _result


def _changed_result(result, after):
    return replace(
        result,
        after=after,
        changes=compare_states(result.before, after),
        signature=state_signature(result.before, after),
        violations=evaluate_contracts(result.before, after),
    )


def _pair(projection):
    first = _result(_case("seed"))
    second = _result(_case("child"))
    if projection == FeedbackProjection.A1:
        # Keep object labels/counts unchanged, alter only the identity relation.
        after = replace(
            second.after,
            objects=tuple(
                replace(obj, st_ino=10) if obj.path == "extract/output" else obj
                for obj in second.after.objects
            ),
        )
    else:
        # Timestamp value is not a signature object field, but its effect label is.
        after = replace(
            second.after,
            objects=tuple(
                replace(obj, mtime_ns=11) if obj.path == "outside/sentinel.txt" else obj
                for obj in second.after.objects
            ),
        )
    return first, _changed_result(second, after)


@pytest.mark.parametrize("projection", (FeedbackProjection.A1, FeedbackProjection.A2))
def test_projection_omits_only_declared_field_and_preserves_raw_evidence(projection):
    first, second = _pair(projection)
    raw = canonical_json(second)
    assert first.signature != second.signature
    assert feedback_key(first.signature, projection) == feedback_key(second.signature, projection)
    projected = feedback_key(second.signature, projection).projected_signature
    omitted = "identity_groups" if projection == FeedbackProjection.A1 else "external_effects"
    assert projected == replace(second.signature, **{omitted: ()})
    assert getattr(second.signature, omitted)
    assert canonical_json(second) == raw
    assert any(verdict.violated for verdict in second.violations)


@pytest.mark.parametrize("projection", (FeedbackProjection.A1, FeedbackProjection.A2))
@pytest.mark.parametrize("policy", tuple(SearchPolicy))
def test_analysis_novelty_stays_full_and_b3_violation_channel_stays_enabled(projection, policy):
    first, second = _pair(projection)
    state = SearchState((first.case,), policy, projection=projection)
    state.consider(first)
    raw = canonical_json(second)
    decision = state.consider(second)
    assert decision.state_novel and not decision.feedback_key_novel
    assert decision.interesting and decision.new_violation_fingerprints
    assert decision.retained == (policy == SearchPolicy.B3)
    assert state.stats.unique_states == 2 and state.unique_feedback_keys == 1
    assert state.projection == projection
    assert state.entries[-1].admission_signature == second.signature if decision.retained else True
    assert canonical_json(second) == raw
    encoded = json.loads(canonical_json(decision))
    assert encoded["schema_version"] == 2
    assert encoded["value"]["feedback_key_novel"] is False


@pytest.mark.parametrize("projection", tuple(FeedbackProjection))
def test_key_ignores_inode_timestamp_and_run_uuid_values_but_keeps_semantics(projection):
    result = _result(_case("seed"))

    def anchored(root, shift):
        def relabel(snapshot):
            return replace(
                snapshot,
                sandbox_root=root,
                objects=tuple(
                    replace(
                        obj,
                        st_dev=obj.st_dev + shift,
                        st_ino=obj.st_ino + shift,
                        mtime_ns=obj.mtime_ns + shift,
                        ctime_ns=obj.ctime_ns + shift,
                    )
                    for obj in snapshot.objects
                ),
            )

        before, after = relabel(result.before), relabel(result.after)
        link = replace(
            _object("extract/link"),
            object_type=ObjectType.SYMLINK,
            content_digest=None,
            symlink_target=root + "/extract/output",
            st_dev=1 + shift,
            st_ino=30 + shift,
            mtime_ns=10 + shift,
            ctime_ns=10 + shift,
        )
        after = replace(
            after, objects=tuple(sorted((*after.objects, link), key=lambda obj: obj.path))
        )
        return _changed_result(replace(result, before=before), after)

    first = anchored("/var/lib/inodefence/run-11111111", 10)
    second = anchored("/var/lib/inodefence/run-99999999", 9000)
    assert first.after != second.after
    assert feedback_key(first.signature, projection) == feedback_key(second.signature, projection)
    changed = _changed_result(
        first,
        replace(
            first.after,
            objects=tuple(
                replace(obj, content_digest="0" * 64) if obj.path == "extract/output" else obj
                for obj in first.after.objects
            ),
        ),
    )
    assert feedback_key(first.signature, projection) != feedback_key(changed.signature, projection)
    state = SearchState((first.case,), SearchPolicy.B1, projection=projection)
    state.consider(first)
    decision = state.consider(replace(second, case=_case("next")))
    assert not decision.interesting and not decision.retained


def test_policy_projection_ids_are_distinct_and_invalid_projection_is_rejected():
    signature = _result(_case("seed")).signature
    assert len({feedback_key(signature, p) for p in FeedbackProjection}) == 3
    with pytest.raises(ValueError):
        FeedbackProjection("unknown")
    with pytest.raises(ValueError):
        SearchState((_case("seed"),), SearchPolicy.B1, projection="unknown")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        feedback_key(signature, "unknown")  # type: ignore[arg-type]
