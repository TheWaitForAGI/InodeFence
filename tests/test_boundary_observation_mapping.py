"""M3: inodefence-boundary-attempt-v1 frame SET -> main M3.1 boundary-attempt keys.

Covers the honest contract for a second extractor whose ordered entry-completion boundary is
not observable (decompress-class limit): it still emits the locked v1 frame, an unordered SET of
boundary attempts, and `boundary_attempt_keys_from_observations` maps each into the same
`BOUNDARY_ESCAPE_ATTEMPT` key the trace-based `boundary_attempt_keys` produces, so both extractors'
keys are drawn from one key space and the existing P3 consumption is unchanged. The mapping is
uniform across node-tar-native and decompress frames (no per-target branch), and answer-agnostic:
the key encodes the operation kind, resolved region, coarse outcome and the bounded *escape shape*
of the raw target -- never the raw path, tail, a sentinel or a CVE.
"""

import pytest

from inodefence.feedback import (
    BoundaryAttemptObservation,
    EffectNoveltyDecision,
    FrameBoundaryNoveltyIndex,
    boundary_attempt_keys_from_observations,
    boundary_attempt_observation_from_frame,
)
from inodefence.model import (
    BoundaryAttemptShape,
    BoundaryAttemptSignature,
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    EntryType,
    OperationOutcome,
    Region,
)


def _obs(
    *,
    operation: EntryType = EntryType.HARDLINK,
    target_raw: str = "../outside/x",
    target_region: Region = Region.EXTERNAL,
    outcome: OperationOutcome = OperationOutcome.ACCESS_DENIED,
) -> BoundaryAttemptObservation:
    return BoundaryAttemptObservation(operation, target_raw, target_region, outcome)


def _frame_attempt(**overrides: object) -> dict[str, object]:
    # A full locked v1-frame attempt (all 8 fields), with the signature-irrelevant ones present
    # so the parser is exercised against the real shape.
    attempt: dict[str, object] = {
        "operation": "hardlink",
        "created_path": "extract/evil",
        "created_region": "extraction",
        "target_raw": "../outside/sentinel.txt",
        "target_resolved_absolute": "/sandbox/outside/sentinel.txt",
        "target_region": "external",
        "aliases_external_object": True,
        "outcome": "created",
    }
    attempt.update(overrides)
    return attempt


def test_external_hardlink_attempt_yields_one_boundary_key() -> None:
    (key,) = boundary_attempt_keys_from_observations((_obs(target_raw="../outside/x"),))

    assert key.kind == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT
    signature = key.signature
    assert isinstance(signature, BoundaryAttemptSignature)
    assert signature.trigger_entry_type == EntryType.HARDLINK
    assert signature.target_region == Region.EXTERNAL
    assert signature.operation_outcome == OperationOutcome.ACCESS_DENIED
    assert signature.escape_shape == BoundaryAttemptShape.PARENT_1


def test_external_symlink_target_is_keyed_by_operation() -> None:
    # The decompress "external symlink target" signal: a symlink whose raw target escapes the
    # root. It is a distinct key from the hardlink one by its entry_type (operation).
    (key,) = boundary_attempt_keys_from_observations(
        (
            _obs(
                operation=EntryType.SYMLINK,
                target_raw="../../x",
                outcome=OperationOutcome.SUCCEEDED,
            ),
        )
    )
    assert key.signature == BoundaryAttemptSignature(
        EntryType.SYMLINK,
        Region.EXTERNAL,
        OperationOutcome.SUCCEEDED,
        BoundaryAttemptShape.PARENT_2,
    )


def test_the_two_observed_frame_signals_form_two_distinct_keys() -> None:
    # The pair the decompress feasibility probe observed: an external sentinel inode alias
    # (hardlink) and an external symlink target. The operation discriminates them.
    keys = boundary_attempt_keys_from_observations(
        (
            _obs(operation=EntryType.HARDLINK, outcome=OperationOutcome.SUCCEEDED),
            _obs(operation=EntryType.SYMLINK, outcome=OperationOutcome.SUCCEEDED),
        )
    )
    assert len(keys) == 2
    entry_types = {
        key.signature.trigger_entry_type
        for key in keys
        if isinstance(key.signature, BoundaryAttemptSignature)
    }
    assert entry_types == {EntryType.HARDLINK, EntryType.SYMLINK}


def test_in_root_target_yields_no_key() -> None:
    assert boundary_attempt_keys_from_observations((_obs(target_region=Region.EXTRACTION),)) == ()


def test_non_escaping_raw_target_yields_no_key() -> None:
    # An EXTERNAL-resolved target whose raw text does not lexically escape has no bounded shape,
    # so it is skipped exactly as the trace derivation skips it.
    assert boundary_attempt_keys_from_observations((_obs(target_raw="a.txt"),)) == ()


def test_harness_target_is_keyed_like_any_non_extraction_region() -> None:
    (key,) = boundary_attempt_keys_from_observations((_obs(target_region=Region.HARNESS),))
    assert isinstance(key.signature, BoundaryAttemptSignature)
    assert key.signature.target_region == Region.HARNESS


def test_outcome_classes_map_and_stay_distinct() -> None:
    created = _obs(outcome=OperationOutcome.SUCCEEDED)
    refused = _obs(outcome=OperationOutcome.ACCESS_DENIED)
    io_error = _obs(outcome=OperationOutcome.OTHER_ERROR)
    keys = boundary_attempt_keys_from_observations((created, refused, io_error))
    assert len({key.signature for key in keys}) == 3


def test_key_is_answer_agnostic_to_the_target_tail() -> None:
    # Two external hardlink attempts that differ ONLY in which external path they reached --
    # one the declared-protected sentinel, one an unrelated external object, both parent_1 --
    # collapse to a single key. The concrete path (sentinel proximity) never enters the key.
    at_sentinel = _obs(target_raw="../outside/sentinel.txt")
    at_other = _obs(target_raw="../outside/decoy")
    assert len(boundary_attempt_keys_from_observations((at_sentinel, at_other))) == 1


def test_duplicate_observations_collapse_to_one_key() -> None:
    assert len(boundary_attempt_keys_from_observations((_obs(), _obs()))) == 1


def test_key_is_identical_to_the_trace_path_construction() -> None:
    # Parity / one key space: the mapping builds the exact EffectFeedbackKey that
    # feedback.effect.boundary_attempt_keys constructs (effect.py: BOUNDARY_ESCAPE_ATTEMPT +
    # BoundaryAttemptSignature(entry_type, target_region, outcome, escape_shape)), so the
    # existing P3 consumption ranks keys from either extractor identically.
    expected = EffectFeedbackKey(
        EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT,
        BoundaryAttemptSignature(
            EntryType.HARDLINK,
            Region.EXTERNAL,
            OperationOutcome.ACCESS_DENIED,
            BoundaryAttemptShape.PARENT_1,
        ),
    )
    (actual,) = boundary_attempt_keys_from_observations((_obs(target_raw="../outside/x"),))
    assert actual == expected


def test_uniform_across_node_tar_and_decompress_frames() -> None:
    # The mapping has no target field, so the same signature-relevant attempt observed from
    # either extractor produces the same single key. This is the "one frame SET, no per-target
    # branch" property.
    node_tar_frame = _obs(target_raw="../../x", outcome=OperationOutcome.SUCCEEDED)
    decompress_frame = _obs(target_raw="../../x", outcome=OperationOutcome.SUCCEEDED)
    assert len(boundary_attempt_keys_from_observations((node_tar_frame, decompress_frame))) == 1


def test_parser_maps_the_locked_v1_vocabulary() -> None:
    observation = boundary_attempt_observation_from_frame(_frame_attempt())
    assert observation == BoundaryAttemptObservation(
        EntryType.HARDLINK, "../outside/sentinel.txt", Region.EXTERNAL, OperationOutcome.SUCCEEDED
    )
    # "dir" -> DIRECTORY and "io_error" -> OTHER_ERROR (the value-mismatched entries).
    dir_io = boundary_attempt_observation_from_frame(
        _frame_attempt(operation="dir", outcome="io_error", target_region="harness")
    )
    assert dir_io.operation == EntryType.DIRECTORY
    assert dir_io.outcome == OperationOutcome.OTHER_ERROR
    assert dir_io.target_region == Region.HARNESS


def test_parser_rejects_unknown_enum_and_missing_fields() -> None:
    with pytest.raises(ValueError):
        boundary_attempt_observation_from_frame(_frame_attempt(operation="device"))
    with pytest.raises(ValueError):
        boundary_attempt_observation_from_frame(_frame_attempt(outcome="maybe"))
    bad = _frame_attempt()
    del bad["target_raw"]
    with pytest.raises(ValueError):
        boundary_attempt_observation_from_frame(bad)


def test_parser_output_maps_through_to_a_key() -> None:
    observation = boundary_attempt_observation_from_frame(_frame_attempt(target_raw="../../../x"))
    (key,) = boundary_attempt_keys_from_observations((observation,))
    assert isinstance(key.signature, BoundaryAttemptSignature)
    assert key.signature.escape_shape == BoundaryAttemptShape.PARENT_3_PLUS


def test_novelty_index_admits_then_dedups() -> None:
    index = FrameBoundaryNoveltyIndex()
    first = index.observe((_obs(target_raw="../outside/x"),))
    assert isinstance(first, EffectNoveltyDecision)
    assert first.feedback_eligible and first.effect_novel and len(first.new_effect_keys) == 1

    # Same attempt again: already admitted, so nothing new, but still eligible.
    second = index.observe((_obs(target_raw="../outside/x"),))
    assert second.feedback_eligible and not second.effect_novel and second.new_effect_keys == ()

    # A different shape is a new key.
    third = index.observe((_obs(target_raw="../../x"),))
    assert third.effect_novel and len(third.new_effect_keys) == 1
    assert len(index.keys) == 2


def test_novelty_index_empty_frame_is_eligible_with_no_keys() -> None:
    decision = FrameBoundaryNoveltyIndex().observe(())
    assert decision.feedback_eligible and not decision.effect_novel
    assert decision.new_effect_keys == ()


def test_observation_validates_its_fields() -> None:
    with pytest.raises(ValueError):
        BoundaryAttemptObservation(
            "hardlink",  # type: ignore[arg-type]
            "../x",
            Region.EXTERNAL,
            OperationOutcome.SUCCEEDED,
        )
    with pytest.raises(ValueError):
        BoundaryAttemptObservation(
            EntryType.HARDLINK,
            "../x",
            "external",  # type: ignore[arg-type]
            OperationOutcome.SUCCEEDED,
        )
    with pytest.raises(ValueError):
        BoundaryAttemptObservation(
            EntryType.HARDLINK,
            "../x",
            Region.EXTERNAL,
            "refused",  # type: ignore[arg-type]
        )


def test_mapping_rejects_a_non_tuple_argument() -> None:
    with pytest.raises(ValueError):
        boundary_attempt_keys_from_observations([_obs()])  # type: ignore[arg-type]
