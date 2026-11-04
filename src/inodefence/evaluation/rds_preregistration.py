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
    observer_integrity_policy = invalid-continue
    # optional, experiment scale (EXP-3): compared when the launcher is given a value
    experiment_id = exp3
    execution_mode = per-case-container
    jobs_max = 4
    campaign_watchdog_seconds = 7200
    disk_pause_fraction = 0.9
    interim_analysis = forbidden
    hit_definition = c1-or-c2-and-contract-violated
    c0_counts_as_hit = false
    denominator = all-cells-including-abort
    abort_reporting = right-censored
    rule_of_three_unit = campaign
    ```

``require_preregistered_cell`` refuses to produce a cell config unless the request's
engine SHA (clean checkout), image digest, seed, budget, arm and — when declared —
sentinel generator identity/seed/count and observer-integrity policy all match the
block. A refusal runs nothing.

"Compare if provided": the rule keys (``hit_definition``, ``c0_counts_as_hit``,
``denominator``, ``abort_reporting``, ``rule_of_three_unit``) are optional, but when
present they must spell exactly the rule this engine implements (``RULE_CONSTANTS``);
a different value is a format error, because the file would then preregister a rule
the runner does not compute. ``observer_integrity_policy`` (``stop`` or
``invalid-continue``, the controller's ``--observer-integrity-policy`` values) must
equal the value the run is launched with. The experiment-scale keys (``experiment_id``,
``execution_mode``, ``jobs_max``, ``campaign_watchdog_seconds``, ``disk_pause_fraction``,
``interim_analysis``) are read by the launcher and compared against its own settings
when both sides give a value. Keys this module does not know are kept in
``unknown_keys`` and only warned about.
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
_OBSERVER_POLICY = "observer_integrity_policy"
OBSERVER_INTEGRITY_POLICIES = ("stop", "invalid-continue")
_EXPERIMENT_ID = "experiment_id"
_EXECUTION_MODE = "execution_mode"
_JOBS_MAX = "jobs_max"
_WATCHDOG = "campaign_watchdog_seconds"
_DISK_PAUSE = "disk_pause_fraction"
_INTERIM = "interim_analysis"
EXECUTION_MODES = ("per-case-container", "worker-pool")
INTERIM_ANALYSIS_VALUES = ("forbidden", "allowed")
# The measurement rules this engine implements (rds.py); a block may restate them
# with exactly these strings and nothing else.
RULE_CONSTANTS: Mapping[str, str] = MappingProxyType(
    {
        "hit_definition": "c1-or-c2-and-contract-violated",
        "c0_counts_as_hit": "false",
        "denominator": "all-cells-including-abort",
        "abort_reporting": "right-censored",
        "rule_of_three_unit": "campaign",
    }
)
KNOWN_KEYS = frozenset(
    (
        *_REQUIRED_KEYS,
        _SENTINEL_ID,
        _SENTINEL_SEED,
        _SENTINEL_COUNT,
        _OBSERVER_POLICY,
        _EXPERIMENT_ID,
        _EXECUTION_MODE,
        _JOBS_MAX,
        _WATCHDOG,
        _DISK_PAUSE,
        _INTERIM,
        *RULE_CONSTANTS,
    )
)


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
    observer_integrity_policy: str | None
    unknown_keys: tuple[str, ...]
    raw: Mapping[str, str]
    experiment_id: str | None = None
    execution_mode: str | None = None
    jobs_max: int | None = None
    campaign_watchdog_seconds: float | None = None
    disk_pause_fraction: float | None = None
    interim_analysis: str | None = None


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


def _float(values: Mapping[str, str], key: str) -> float:
    try:
        return float(values[key])
    except ValueError:
        raise PreregistrationFormatError(f"{key} must be a number") from None


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
    for key, expected in RULE_CONSTANTS.items():
        if key in values and values[key] != expected:
            raise PreregistrationFormatError(
                f"{key} = {values[key]!r} is not the rule this engine implements ({expected!r})"
            )
    observer_policy = values.get(_OBSERVER_POLICY)
    if observer_policy is not None and observer_policy not in OBSERVER_INTEGRITY_POLICIES:
        raise PreregistrationFormatError(
            f"{_OBSERVER_POLICY} must be one of {OBSERVER_INTEGRITY_POLICIES}"
        )
    unknown = tuple(key for key in values if key not in KNOWN_KEYS and not key.startswith(_ARM_KEY))
    execution_mode = values.get(_EXECUTION_MODE)
    if execution_mode is not None and execution_mode not in EXECUTION_MODES:
        raise PreregistrationFormatError(f"{_EXECUTION_MODE} must be one of {EXECUTION_MODES}")
    jobs_max = _int(values, _JOBS_MAX) if _JOBS_MAX in values else None
    if jobs_max is not None and jobs_max < 1:
        raise PreregistrationFormatError(f"{_JOBS_MAX} must be >= 1")
    watchdog = _float(values, _WATCHDOG) if _WATCHDOG in values else None
    if watchdog is not None and watchdog <= 0:
        raise PreregistrationFormatError(f"{_WATCHDOG} must be positive")
    disk_pause = _float(values, _DISK_PAUSE) if _DISK_PAUSE in values else None
    if disk_pause is not None and not 0 < disk_pause <= 1:
        raise PreregistrationFormatError(f"{_DISK_PAUSE} must be in (0, 1]")
    interim = values.get(_INTERIM)
    if interim is not None and interim not in INTERIM_ANALYSIS_VALUES:
        raise PreregistrationFormatError(f"{_INTERIM} must be one of {INTERIM_ANALYSIS_VALUES}")
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
        observer_policy,
        unknown,
        values,
        values.get(_EXPERIMENT_ID),
        execution_mode,
        jobs_max,
        watchdog,
        disk_pause,
        interim,
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
    observer_integrity_policy: str | None = None
    experiment_id: str | None = None
    execution_mode: str | None = None
    jobs: int | None = None


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
    if preregistration.observer_integrity_policy is not None:
        if request.observer_integrity_policy is None:
            problems.append(
                "observer_integrity_policy declared in preregistration but not supplied"
            )
        elif request.observer_integrity_policy != preregistration.observer_integrity_policy:
            problems.append(
                f"observer_integrity_policy {request.observer_integrity_policy!r} != "
                f"preregistered {preregistration.observer_integrity_policy!r}"
            )
    for label, declared, given in (
        ("experiment_id", preregistration.experiment_id, request.experiment_id),
        ("execution_mode", preregistration.execution_mode, request.execution_mode),
    ):
        if declared is not None and given is not None and given != declared:
            problems.append(f"{label} {given!r} != preregistered {declared!r}")
    if (
        preregistration.jobs_max is not None
        and request.jobs is not None
        and request.jobs > preregistration.jobs_max
    ):
        problems.append(f"jobs {request.jobs} > preregistered jobs_max {preregistration.jobs_max}")
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
