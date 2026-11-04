"""Unit tests for the opt-in, seed-fixed multi-sentinel generator.

These cover reproducibility, validation and the recorded ``describe()`` shape.
They do not touch the oracle verdict rules (see ``test_multi_sentinel_oracle``).
"""

import re

import pytest

from inodefence.model.filesystem import validate_observed_path
from inodefence.runtime import SentinelSpec, disposable_sandbox
from inodefence.sentinel_set import (
    GENERATOR_ID,
    GeneratedSentinelSet,
    generate_sentinel_names,
    generate_sentinel_set,
)


def test_names_are_deterministic_for_a_fixed_seed() -> None:
    assert generate_sentinel_names(600, 3) == generate_sentinel_names(600, 3)
    first = generate_sentinel_set(600, 3)
    again = generate_sentinel_set(600, 3)
    assert first.names == again.names
    assert first.specs == again.specs


def test_different_seeds_yield_different_names() -> None:
    assert generate_sentinel_names(600, 3) != generate_sentinel_names(601, 3)


def test_count_is_respected_and_names_unique_and_safe() -> None:
    names = generate_sentinel_names(42, 5)
    assert len(names) == 5
    assert len(set(names)) == 5
    for name in names:
        validate_observed_path(name)  # raises if not sandbox-relative/canonical
        assert "/" not in name and name != "."


def test_generated_set_protected_paths_are_sorted_outside_paths() -> None:
    generated = generate_sentinel_set(7, 4)
    assert generated.protected_paths == tuple(sorted(f"outside/{name}" for name in generated.names))
    assert all(path.startswith("outside/") for path in generated.protected_paths)


def test_each_sentinel_has_distinct_content() -> None:
    generated = generate_sentinel_set(7, 4)
    contents = [spec.content for spec in generated.specs]
    assert len(set(contents)) == len(contents)


def test_describe_records_seed_count_and_names() -> None:
    generated = generate_sentinel_set(600, 3)
    described = generate_sentinel_set(600, 3).describe()
    assert described["generator_id"] == GENERATOR_ID
    assert described["generator_seed"] == 600
    assert described["count"] == 3
    assert described["names"] == list(generated.names)
    assert described["protected_paths"] == list(generated.protected_paths)
    for record in described["sentinels"]:
        assert re.fullmatch(r"[0-9a-f]{64}", record["content_sha256"])
        assert set(record) == {"name", "content_sha256", "mode"}
    # describe() is itself reproducible from the seed alone.
    assert described == generate_sentinel_set(600, 3).describe()


@pytest.mark.parametrize(
    "seed,count",
    [("600", 3), (1.0, 3), (600, 0), (600, 65), (600, -1)],
)
def test_invalid_arguments_are_rejected(seed: object, count: object) -> None:
    with pytest.raises(ValueError):
        generate_sentinel_set(seed, count)  # type: ignore[arg-type]


def test_generated_set_rejects_duplicate_specs() -> None:
    spec = SentinelSpec(name="dup.dat")
    with pytest.raises(ValueError, match="unique"):
        GeneratedSentinelSet(1, (spec, spec))


def test_default_sandbox_is_unchanged_single_sentinel() -> None:
    """Additivity: callers that do not opt in keep exactly one default sentinel."""
    with disposable_sandbox() as sandbox:
        assert sandbox.protected_paths == ("outside/sentinel.txt",)
