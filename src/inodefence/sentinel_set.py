"""Deterministic multi-sentinel generation (opt-in; the default stays single).

Callers that do not opt in keep the unchanged default ``(SentinelSpec(),)``: this
module adds nothing to their behaviour. It exists so an experiment can place
three or more external sentinels whose names are drawn from a *recorded* PRNG
seed instead of being hardcoded. ``describe()`` pins the generator seed and the
resulting names so a result or report can record exactly which sentinels existed.

No sentinel name is hardcoded into the oracle, mutator or feedback: names come
only from this generator (or an explicit ``SentinelSpec``) and reach the oracle
as the sandbox ``protected_paths`` -- ``outside/<name>`` -- which the observer
captures as EXTERNAL objects in the BEFORE snapshot. Given the same seed and
count the generator is fully reproducible.
"""

import random
import string
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from inodefence.runtime import SentinelSpec

GENERATOR_ID = "sentinel-names/seed-random-v1"

_NAME_ALPHABET = string.ascii_lowercase + string.digits
_DEFAULT_COUNT = 3
_DEFAULT_NAME_LENGTH = 12
_DEFAULT_SUFFIX = ".dat"
_DEFAULT_MODE = 0o600
_CONTENT_PREFIX = b"inodefence generated sentinel "
_MAX_COUNT = 64


@dataclass(frozen=True, slots=True)
class GeneratedSentinelSet:
    """A reproducible set of external sentinels plus the seed that produced it."""

    generator_seed: int
    specs: tuple[SentinelSpec, ...]

    def __post_init__(self) -> None:
        if type(self.generator_seed) is not int:
            raise ValueError("generator_seed must be an int")
        if not isinstance(self.specs, tuple) or not self.specs:
            raise ValueError("specs must be a nonempty tuple of SentinelSpec")
        if not all(isinstance(spec, SentinelSpec) for spec in self.specs):
            raise ValueError("specs must contain only SentinelSpec")
        if len({spec.name for spec in self.specs}) != len(self.specs):
            raise ValueError("sentinel names must be unique")

    @property
    def names(self) -> tuple[str, ...]:
        """Bare sentinel names in generation order."""
        return tuple(spec.name for spec in self.specs)

    @property
    def protected_paths(self) -> tuple[str, ...]:
        """Sorted ``outside/<name>`` paths, matching the sandbox protected set."""
        return tuple(sorted(f"outside/{spec.name}" for spec in self.specs))

    def describe(self) -> dict[str, Any]:
        """Serialisable record for a result/report: seed, count and names.

        The shape is coordinated with the campaign-runner lane so the generator
        seed, names and protected paths are reproducible from the result alone.
        """
        return {
            "generator_id": GENERATOR_ID,
            "generator_seed": self.generator_seed,
            "count": len(self.specs),
            "names": list(self.names),
            "protected_paths": list(self.protected_paths),
            "sentinels": [
                {
                    "name": spec.name,
                    "content_sha256": sha256(spec.content).hexdigest(),
                    "mode": spec.mode,
                }
                for spec in sorted(self.specs, key=lambda spec: spec.name)
            ],
        }


def generate_sentinel_names(
    seed: int,
    count: int = _DEFAULT_COUNT,
    *,
    name_length: int = _DEFAULT_NAME_LENGTH,
    suffix: str = _DEFAULT_SUFFIX,
) -> tuple[str, ...]:
    """Draw ``count`` unique, sandbox-safe names deterministically from ``seed``.

    Names are ``<name_length> alnum chars`` + ``suffix`` (e.g. ``abc123...dat``).
    Order is the PRNG draw order, so a fixed seed always yields the same tuple.
    """
    if type(seed) is not int:
        raise ValueError("seed must be an int")
    if type(count) is not int or not 1 <= count <= _MAX_COUNT:
        raise ValueError(f"count must be an int in 1..{_MAX_COUNT}")
    if type(name_length) is not int or not 1 <= name_length <= 64:
        raise ValueError("name_length must be an int in 1..64")
    if not isinstance(suffix, str) or "/" in suffix or "\0" in suffix:
        raise ValueError("suffix must be text without '/' or NUL")
    rng = random.Random(seed)
    names: list[str] = []
    seen: set[str] = set()
    attempts = 0
    attempt_budget = max(count * 1000, 1000)
    while len(names) < count:
        body = "".join(rng.choice(_NAME_ALPHABET) for _ in range(name_length))
        name = f"{body}{suffix}"
        if name not in seen:
            seen.add(name)
            names.append(name)
        attempts += 1
        if attempts > attempt_budget:
            raise ValueError("could not draw enough unique names; widen name_length")
    return tuple(names)


def generate_sentinel_set(
    seed: int,
    count: int = _DEFAULT_COUNT,
    *,
    name_length: int = _DEFAULT_NAME_LENGTH,
    suffix: str = _DEFAULT_SUFFIX,
    mode: int = _DEFAULT_MODE,
) -> GeneratedSentinelSet:
    """Build a reproducible ``GeneratedSentinelSet`` of ``count`` sentinels.

    Each sentinel gets distinct content (prefix + its own name) so a later
    content change is attributable to a specific sentinel. Pass ``.specs`` to
    ``disposable_sandbox(sentinels=...)`` or ``run_case(sentinels=...)``.
    """
    names = generate_sentinel_names(seed, count, name_length=name_length, suffix=suffix)
    specs = tuple(
        SentinelSpec(name=name, content=_CONTENT_PREFIX + name.encode() + b"\n", mode=mode)
        for name in names
    )
    return GeneratedSentinelSet(seed, specs)
