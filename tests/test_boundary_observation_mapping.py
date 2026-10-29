"""M3: set-based boundary observation -> the existing external-resolve feedback key.

Covers the honest contract for a second extractor whose ordered entry-completion boundary
is not observable (decompress-class limit): it can still observe a *set* of boundary-relevant
operations, and `external_resolve_keys_from_observations` maps those into the same
`OBSERVED_EXTERNAL_RESOLVE` key the trace-based `external_resolve_keys` produces, so both
extractors' keys are drawn from one key space and the existing P3 consumption is unchanged.

Target-agnostic and answer-agnostic: the key reads only the operation kind and the EXTERNAL
region -- never the entry destination path, the realized-alias marker, a sentinel or a CVE.
A pair of tests pins that neither the concrete path nor the alias marker can raise or split a
key (that would drift the reward toward the protected sentinel, D005/D006).
"""

import pytest

from inodefence.feedback import (
    ObservedBoundaryOperation,
    external_resolve_keys_from_observations,
)
from inodefence.model import (
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    ExternalResolveSignature,
    ObservedOperationType,
    Region,
)


def _obs(
    operation: ObservedOperationType,
    target_region: Region,
    *,
    entry_dest: str = "extract/object-0",
    aliases_external: bool = False,
) -> ObservedBoundaryOperation:
    return ObservedBoundaryOperation(operation, entry_dest, target_region, aliases_external)


def test_external_link_observation_yields_one_external_resolve_key() -> None:
    keys = external_resolve_keys_from_observations(
        (_obs(ObservedOperationType.LINK, Region.EXTERNAL, aliases_external=True),)
    )

    assert len(keys) == 1
    assert keys[0].kind == EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE
    signature = keys[0].signature
    assert isinstance(signature, ExternalResolveSignature)
    assert signature.operation == ObservedOperationType.LINK
    assert signature.resolved_region == Region.EXTERNAL


def test_external_symlink_target_is_also_credited() -> None:
    # The decompress "external symlink target" set signal: a SYMLINK resolving outside the
    # root. Faithful to ExternalResolveSignature's own definition (any observed operation
    # resolving EXTERNAL), and distinct from the hardlink key by its operation kind.
    keys = external_resolve_keys_from_observations(
        (_obs(ObservedOperationType.SYMLINK, Region.EXTERNAL),)
    )

    assert len(keys) == 1
    assert keys[0].signature == ExternalResolveSignature(
        ObservedOperationType.SYMLINK, Region.EXTERNAL
    )


def test_the_two_observed_decompress_signals_form_two_distinct_keys() -> None:
    # Exactly the pair the decompress feasibility probe observed: an external sentinel inode
    # alias (hardlink) and an external symlink target. The operation discriminates them, so
    # they are two distinct keys, not one.
    keys = external_resolve_keys_from_observations(
        (
            _obs(ObservedOperationType.LINK, Region.EXTERNAL, aliases_external=True),
            _obs(ObservedOperationType.SYMLINK, Region.EXTERNAL, entry_dest="extract/link"),
        )
    )

    assert len(keys) == 2
    operations = {
        key.signature.operation
        for key in keys
        if isinstance(key.signature, ExternalResolveSignature)
    }
    assert operations == {ObservedOperationType.LINK, ObservedOperationType.SYMLINK}


@pytest.mark.parametrize("region", [Region.EXTRACTION, Region.HARNESS])
def test_non_external_region_yields_no_key(region: Region) -> None:
    # Only an EXTERNAL resolution is an external-resolve, exactly as the trace path credits
    # only Region.EXTERNAL. An in-root (EXTRACTION) or harness resolution is not a boundary
    # crossing for this signal.
    keys = external_resolve_keys_from_observations((_obs(ObservedOperationType.LINK, region),))
    assert keys == ()


def test_duplicate_observations_collapse_to_one_key() -> None:
    observation = _obs(ObservedOperationType.LINK, Region.EXTERNAL, aliases_external=True)
    assert len(external_resolve_keys_from_observations((observation, observation))) == 1


def test_key_is_answer_agnostic_to_the_entry_destination_path() -> None:
    # Two external LINK resolutions that differ ONLY in which external path they reached --
    # one the declared-protected sentinel, one an unrelated external object -- collapse to a
    # single key. The concrete path (and thus sentinel proximity) never enters the key.
    at_sentinel = _obs(
        ObservedOperationType.LINK, Region.EXTERNAL, entry_dest="outside/sentinel.txt"
    )
    at_other = _obs(ObservedOperationType.LINK, Region.EXTERNAL, entry_dest="outside/decoy")

    assert len(external_resolve_keys_from_observations((at_sentinel, at_other))) == 1


def test_key_is_answer_agnostic_to_the_realized_alias_marker() -> None:
    # A realized external identity alias and a dangling external reference at the same
    # operation/region collapse to one key: whether the alias was realized is a C1/C2 oracle
    # judgment, never a feedback reward dimension.
    realized = _obs(ObservedOperationType.LINK, Region.EXTERNAL, aliases_external=True)
    dangling = _obs(ObservedOperationType.LINK, Region.EXTERNAL, aliases_external=False)

    assert len(external_resolve_keys_from_observations((realized, dangling))) == 1


def test_key_is_identical_to_the_trace_path_construction() -> None:
    # Parity / one key space: the mapping builds the exact EffectFeedbackKey that
    # feedback.effect.external_resolve_keys constructs for an external-resolved operation
    # (effect.py: OBSERVED_EXTERNAL_RESOLVE + ExternalResolveSignature(operation, EXTERNAL)),
    # so the existing P3 consumption ranks keys from either extractor identically.
    expected = EffectFeedbackKey(
        EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE,
        ExternalResolveSignature(ObservedOperationType.LINK, Region.EXTERNAL),
    )
    (actual,) = external_resolve_keys_from_observations(
        (_obs(ObservedOperationType.LINK, Region.EXTERNAL, aliases_external=True),)
    )
    assert actual == expected


def test_empty_observations_yield_no_keys() -> None:
    assert external_resolve_keys_from_observations(()) == ()


def test_record_validates_its_fields() -> None:
    with pytest.raises(ValueError):
        ObservedBoundaryOperation("link", "extract/x", Region.EXTERNAL, False)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ObservedBoundaryOperation(ObservedOperationType.LINK, "", Region.EXTERNAL, False)
    with pytest.raises(ValueError):
        ObservedBoundaryOperation(ObservedOperationType.LINK, "extract/x", "external", False)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ObservedBoundaryOperation(ObservedOperationType.LINK, "extract/x", Region.EXTERNAL, 1)  # type: ignore[arg-type]


def test_mapping_rejects_a_non_tuple_argument() -> None:
    with pytest.raises(ValueError):
        external_resolve_keys_from_observations(
            [_obs(ObservedOperationType.LINK, Region.EXTERNAL)]  # type: ignore[arg-type]
        )
