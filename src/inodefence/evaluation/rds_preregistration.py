"""Preregistration gate for R/D/S-u cells: parse the fenced block, refuse mismatches.

A preregistration file under ``experiments/preregistration/`` is committed before
any run and never edited afterwards. The execution-valid version (e.g. EXP-0 v2.1)
carries one fenced block that this module reads; the prose around it is not
parsed. The block is ``key = value`` lines between a ```` ```preregistration ````
fence and the closing ```` ``` ````::

    ```preregistration
    engine_sha = <40-hex git commit of the engine (main) the run executes>
    image_digest = sha256:<64-hex frozen target image id>
    seeds = 9001, 9002, 9003, 9004, 9005
    budget = 200
    vocabulary = observed-names
    arm.R = unretained-walk-v1-uniform-mutation-v1
    arm.D = structure-coverage-v1-uniform-mutation-v1
    arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
    # optional
    arm.S-a = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1
    sentinel_generator_id = sentinel-names/seed-random-v1
    sentinel_generator_seed = 9001
    sentinel_count = 3
    ```

``require_preregistered_cell`` refuses to produce a cell config unless the request's
engine SHA (clean checkout), image digest, seed, budget, arm and — when declared —
sentinel generator identity/seed/count all match the block. A refusal runs nothing.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from inodefence.feedback import EffectSearchPolicy

from .rds import RdsArm, RdsCellConfig, RVariant, VocabularyMode, arm_for_policy

FENCE_OPEN = "```preregistration"
FENCE_CLOSE = "```"
_ENGINE_SHA = re.compile(r"[0-9a-f]{40}")
_IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_REQUIRED_KEYS = ("engine_sha", "image_digest", "seeds", "budget", "vocabulary")
_ARM_KEY = "arm."
_SENTINEL_ID = "sentinel_generator_id"
_SENTINEL_SEED = "sentinel_generator_seed"
_SENTINEL_COUNT = "sentinel_count"


class PreregistrationFormatError(ValueError):
    """The file has no usable block, or the block is malformed/inconsistent."""


class PreregistrationMismatch(ValueError):
    """The requested cell is not the preregistered one; nothing was run."""

    def __init__(self, mismatches: tuple[str, ...]) -> None:
        self.mismatches = mismatches
        super().__init__("preregistration mismatch: " + "; ".join(mismatches))


@dataclass(frozen=True, slots=True)
class Preregistration:
    engine_sha: str
    image_digest: str
    seeds: tuple[int, ...]
    budget: int
    vocabulary_mode: VocabularyMode
    arm_policies: Mapping[RdsArm, EffectSearchPolicy]
    r_variant: RVariant
    sentinel_generator_id: str | None
    sentinel_generator_seed: int | None
    sentinel_count: int | None
    raw: Mapping[str, str]


def parse_preregistration_block(text: str) -> Mapping[str, str]:
    """The first fenced ``preregistration`` block as an ordered key→value mapping."""
    lines = text.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == FENCE_OPEN)
    except StopIteration:
        raise PreregistrationFormatError(f"no {FENCE_OPEN} block found") from None
    values: dict[str, str] = {}
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped == FENCE_CLOSE:
            return MappingProxyType(values)
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not key or not value:
            raise PreregistrationFormatError(f"malformed line in block: {stripped!r}")
        if key in values:
            raise PreregistrationFormatError(f"duplicate key in block: {key}")
        values[key] = value
    raise PreregistrationFormatError("preregistration block is not closed")


def _int(values: Mapping[str, str], key: str) -> int:
    try:
        return int(values[key])
    except ValueError:
        raise PreregistrationFormatError(f"{key} must be an integer") from None


def parse_preregistration(text: str) -> Preregistration:
    values = parse_preregistration_block(text)
    missing = [key for key in _REQUIRED_KEYS if key not in values]
    arm_keys = [key for key in values if key.startswith(_ARM_KEY)]
    if missing or not arm_keys:
        raise PreregistrationFormatError(f"missing keys: {missing or ['arm.*']}")
    if _ENGINE_SHA.fullmatch(values["engine_sha"]) is None:
        raise PreregistrationFormatError("engine_sha must be a 40-hex git commit")
    if _IMAGE_DIGEST.fullmatch(values["image_digest"]) is None:
        raise PreregistrationFormatError("image_digest must be sha256:<64 hex>")
    try:
        seeds = tuple(int(item.strip()) for item in values["seeds"].split(","))
    except ValueError:
        raise PreregistrationFormatError("seeds must be comma-separated integers") from None
    if not seeds or len(set(seeds)) != len(seeds):
        raise PreregistrationFormatError("seeds must be nonempty and unique")
    budget = _int(values, "budget")
    if budget <= 0:
        raise PreregistrationFormatError("budget must be positive")
    try:
        vocabulary = VocabularyMode(values["vocabulary"])
    except ValueError:
        raise PreregistrationFormatError(f"unknown vocabulary {values['vocabulary']!r}") from None
    arm_policies: dict[RdsArm, EffectSearchPolicy] = {}
    r_variant = RVariant.WALK
    for key in arm_keys:
        label = key[len(_ARM_KEY) :]
        try:
            arm = RdsArm(label)
            policy = EffectSearchPolicy(values[key])
            realized, variant = arm_for_policy(policy)
        except ValueError:
            raise PreregistrationFormatError(f"{key} has an unknown arm or policy ID") from None
        if realized != arm:
            raise PreregistrationFormatError(f"{key} names a policy that realizes {realized.value}")
        if variant is not None:
            r_variant = variant
        arm_policies[arm] = policy
    for arm in (RdsArm.R, RdsArm.D, RdsArm.S_U):
        if arm not in arm_policies:
            raise PreregistrationFormatError(f"main arm {arm.value} is not declared")
    generator_seed = _int(values, _SENTINEL_SEED) if _SENTINEL_SEED in values else None
    count = _int(values, _SENTINEL_COUNT) if _SENTINEL_COUNT in values else None
    if count is not None and count <= 0:
        raise PreregistrationFormatError("sentinel_count must be positive")
    return Preregistration(
        values["engine_sha"],
        values["image_digest"],
        seeds,
        budget,
        vocabulary,
        MappingProxyType(arm_policies),
        r_variant,
        values.get(_SENTINEL_ID),
        generator_seed,
        count,
        values,
    )


def load_preregistration(path: Path) -> Preregistration:
    return parse_preregistration(Path(path).read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class CellRequest:
    """What the caller is about to run; ``None`` provenance never passes the gate."""

    arm: RdsArm
    random_seed: int
    execution_budget: int
    engine_sha: str | None
    engine_dirty: bool | None
    image_digest: str | None
    sentinel_set: Mapping[str, object] | None = None


def preregistration_mismatches(
    preregistration: Preregistration, request: CellRequest
) -> tuple[str, ...]:
    """Every reason the request is not the preregistered cell (empty means it is)."""
    problems: list[str] = []
    if request.engine_sha is None:
        problems.append("engine SHA unavailable (not a git checkout?)")
    elif request.engine_sha != preregistration.engine_sha:
        problems.append(
            f"engine SHA {request.engine_sha} != preregistered {preregistration.engine_sha}"
        )
    if request.engine_dirty is None:
        problems.append("engine checkout dirty state unknown")
    elif request.engine_dirty:
        problems.append("engine checkout is dirty (uncommitted or untracked changes)")
    if request.image_digest is None:
        problems.append("image digest not supplied")
    elif request.image_digest != preregistration.image_digest:
        problems.append(
            f"image digest {request.image_digest} != preregistered {preregistration.image_digest}"
        )
    if request.random_seed not in preregistration.seeds:
        problems.append(f"seed {request.random_seed} not in preregistered {preregistration.seeds}")
    if request.execution_budget != preregistration.budget:
        problems.append(
            f"budget {request.execution_budget} != preregistered {preregistration.budget}"
        )
    if request.arm not in preregistration.arm_policies:
        problems.append(f"arm {request.arm.value} is not preregistered")
    declared = {
        "generator_id": preregistration.sentinel_generator_id,
        "generator_seed": preregistration.sentinel_generator_seed,
        "count": preregistration.sentinel_count,
    }
    if any(value is not None for value in declared.values()):
        if request.sentinel_set is None:
            problems.append("sentinel set declared in preregistration but not supplied")
        else:
            for key, expected in declared.items():
                if expected is not None and request.sentinel_set.get(key) != expected:
                    problems.append(
                        f"sentinel_set.{key} {request.sentinel_set.get(key)!r} != "
                        f"preregistered {expected!r}"
                    )
    return tuple(problems)


def require_preregistered_cell(
    preregistration: Preregistration, request: CellRequest
) -> RdsCellConfig:
    """The cell config for a matching request; raises ``PreregistrationMismatch`` otherwise."""
    mismatches = preregistration_mismatches(preregistration, request)
    if mismatches:
        raise PreregistrationMismatch(mismatches)
    return RdsCellConfig(
        request.arm,
        request.random_seed,
        request.execution_budget,
        preregistration.vocabulary_mode,
        preregistration.r_variant,
    )
