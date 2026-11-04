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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from inodefence.feedback import EffectSearchPolicy

from .rds import RdsArm, RdsCellConfig, RVariant, VocabularyMode, arm_for_policy

FENCE_OPEN = "```preregistration"
FENCE_CLOSE = "```"
_ENGINE_SHA = re.compile(r"[0-9a-f]{40}")
_IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_REQUIRED_KEYS = ("engine_sha", "seeds", "budget", "vocabulary")
_IMAGE_DIGEST_KEY = "image_digest"
# Multi-target (EXP-3) extension: dotted group keys ``targets.<id>.<field>``. A file
# declares EITHER the single ``image_digest`` (one node-tar target, the EXP-0 form)
# OR one or more ``targets.<id>.*`` groups — never both.
_TARGET_KEY = "targets."
_TARGET_ID = re.compile(r"[a-z0-9][a-z0-9.-]*")
TARGET_FIELDS = frozenset(
    (
        "extractor",
        "version",
        "image_digest",
        "lock_digest",
        "role",
        "hypothesis",
        "exposure",
        "exposure_ref",
        "exclusion_ref",
        "arms",
        "budget",
    )
)
_TARGET_REQUIRED = ("extractor", "version", "role", "hypothesis", "exposure")
TARGET_ROLES = ("train", "fix-verification", "holdout")
TARGET_HYPOTHESES = ("H-A", "H-B")
TARGET_EXPOSURES = ("none", "pre-exposed")
_EXPOSURE_LEDGER = "exposure_ledger"
_EXPOSURE_LEDGER_SHA = "exposure_ledger_sha256"
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_CONFIRMATORY_FAMILY = "confirmatory_family"
_CONFIRMATORY_TEST = "confirmatory_test"
_MULTIPLICITY = "multiplicity"
_PRIMARY_ENDPOINT = "primary_endpoint"
_EVENT_THRESHOLD = "event_threshold"
_CONTRAST = re.compile(r"holdout:(S-u-vs-R|S-u-vs-D)(,(S-u-vs-R|S-u-vs-D))*")
# exact-logrank-permutation-v1 is the confirmatory test at every n (seed-block,
# target-stratified permutation; a sparse-event family gives p ~ 1, a correct
# non-rejection). event_threshold is an underpowered FLAG, not a switch; the
# rule-of-three bound is descriptive. The other enum values are accepted by the
# parser for drafts but are not the engine's recommendation.
CONFIRMATORY_TESTS = (
    "exact-logrank-permutation-v1",
    "rule-of-three-bound-v1",
    "threshold-v1",
)
MULTIPLICITY_RULES = ("holm-fwer-v1",)
PRIMARY_ENDPOINTS = ("t_first", "u_viol")
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
        _IMAGE_DIGEST_KEY,
        _EXPOSURE_LEDGER,
        _EXPOSURE_LEDGER_SHA,
        _CONFIRMATORY_FAMILY,
        _CONFIRMATORY_TEST,
        _MULTIPLICITY,
        _PRIMARY_ENDPOINT,
        _EVENT_THRESHOLD,
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
class TargetSpec:
    """One extraction target of a multi-target registration (``targets.<id>.*``).

    ``digest`` is the image digest (container targets) or the lock digest
    (in-process targets: sha256 of ``python -VV`` + the tarfile.py file hash +
    ``uname -sr``; filesystem semantics are host-fixed and shared by every arm).
    ``role``: train (design input, exploratory), fix-verification (negative control,
    hit expected 0) or holdout (the only confirmatory test; must not be pre-exposed).
    """

    target_id: str
    extractor: str
    version: str
    digest: str
    digest_kind: str  # "image" | "lock"
    role: str
    hypothesis: str
    exposure: str
    exposure_ref: str | None
    exclusion_ref: str | None
    arms: tuple[RdsArm, ...] | None
    budget: int | None


@dataclass(frozen=True, slots=True)
class Preregistration:
    engine_sha: str
    image_digest: str | None
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
    targets: tuple[TargetSpec, ...] = ()
    exposure_ledger: str | None = None
    exposure_ledger_sha256: str | None = None
    confirmatory_family: str | None = None
    confirmatory_test: str | None = None
    multiplicity: str | None = None
    primary_endpoint: str | None = None
    event_threshold: int | None = None

    def target(self, target_id: str) -> TargetSpec | None:
        for item in self.targets:
            if item.target_id == target_id:
                return item
        return None


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
    image_digest = values.get(_IMAGE_DIGEST_KEY)
    target_keys = [key for key in values if key.startswith(_TARGET_KEY)]
    if image_digest is None and not target_keys:
        raise PreregistrationFormatError("missing keys: ['image_digest' or 'targets.<id>.*']")
    if image_digest is not None and target_keys:
        raise PreregistrationFormatError(
            "image_digest and targets.<id>.* are mutually exclusive (the single key is the "
            "one-target shorthand)"
        )
    if image_digest is not None and _IMAGE_DIGEST.fullmatch(image_digest) is None:
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
    targets = _parse_targets(values, target_keys, tuple(arm_policies))
    ledger = values.get(_EXPOSURE_LEDGER)
    ledger_sha = values.get(_EXPOSURE_LEDGER_SHA)
    if ledger_sha is not None and _SHA256_HEX.fullmatch(ledger_sha) is None:
        raise PreregistrationFormatError(f"{_EXPOSURE_LEDGER_SHA} must be 64 hex")
    if (ledger is None) != (ledger_sha is None):
        raise PreregistrationFormatError(
            f"{_EXPOSURE_LEDGER} and {_EXPOSURE_LEDGER_SHA} must be declared together"
        )
    if any(target.role == "holdout" for target in targets) and ledger is None:
        raise PreregistrationFormatError(
            f"a holdout target requires {_EXPOSURE_LEDGER} and {_EXPOSURE_LEDGER_SHA}"
        )
    family = values.get(_CONFIRMATORY_FAMILY)
    if family is not None and _CONTRAST.fullmatch(family) is None:
        raise PreregistrationFormatError(
            f"{_CONFIRMATORY_FAMILY} must be holdout:<contrast>[,<contrast>] with contrasts "
            "S-u-vs-R / S-u-vs-D"
        )
    for key, allowed in (
        (_CONFIRMATORY_TEST, CONFIRMATORY_TESTS),
        (_MULTIPLICITY, MULTIPLICITY_RULES),
        (_PRIMARY_ENDPOINT, PRIMARY_ENDPOINTS),
    ):
        if key in values and values[key] not in allowed:
            raise PreregistrationFormatError(f"{key} must be one of {allowed}")
    event_threshold = _int(values, _EVENT_THRESHOLD) if _EVENT_THRESHOLD in values else None
    if event_threshold is not None and event_threshold < 1:
        raise PreregistrationFormatError(f"{_EVENT_THRESHOLD} must be >= 1")
    unknown = tuple(
        key
        for key in values
        if key not in KNOWN_KEYS
        and not key.startswith(_ARM_KEY)
        and not key.startswith(_TARGET_KEY)
    )
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
        image_digest,
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
        targets=targets,
        exposure_ledger=ledger,
        exposure_ledger_sha256=ledger_sha,
        confirmatory_family=family,
        confirmatory_test=values.get(_CONFIRMATORY_TEST),
        multiplicity=values.get(_MULTIPLICITY),
        primary_endpoint=values.get(_PRIMARY_ENDPOINT),
        event_threshold=event_threshold,
    )


def _parse_targets(
    values: Mapping[str, str], target_keys: Sequence[str], declared_arms: Sequence[RdsArm]
) -> tuple[TargetSpec, ...]:
    """``targets.<id>.<field>`` groups; an unknown field is a format error (fail-closed)."""
    groups: dict[str, dict[str, str]] = {}
    for key in target_keys:
        rest = key[len(_TARGET_KEY) :]
        target_id, dot, field = rest.rpartition(".")  # ids may contain dots (7.5.2)
        if not dot or _TARGET_ID.fullmatch(target_id) is None:
            raise PreregistrationFormatError(f"{key}: expected targets.<id>.<field>")
        if field not in TARGET_FIELDS:
            raise PreregistrationFormatError(f"{key}: unknown target field {field!r}")
        groups.setdefault(target_id, {})[field] = values[key]
    targets: list[TargetSpec] = []
    for target_id, fields in groups.items():
        missing = [name for name in _TARGET_REQUIRED if name not in fields]
        if missing:
            raise PreregistrationFormatError(f"targets.{target_id}: missing {missing}")
        has_image, has_lock = "image_digest" in fields, "lock_digest" in fields
        if has_image == has_lock:
            raise PreregistrationFormatError(
                f"targets.{target_id}: exactly one of image_digest / lock_digest is required"
            )
        digest = fields["image_digest"] if has_image else fields["lock_digest"]
        if _IMAGE_DIGEST.fullmatch(digest) is None:
            raise PreregistrationFormatError(f"targets.{target_id}: digest must be sha256:<64 hex>")
        for name, allowed in (
            ("role", TARGET_ROLES),
            ("hypothesis", TARGET_HYPOTHESES),
            ("exposure", TARGET_EXPOSURES),
        ):
            if fields[name] not in allowed:
                raise PreregistrationFormatError(
                    f"targets.{target_id}.{name} must be one of {allowed}"
                )
        if fields["exposure"] == "pre-exposed" and not fields.get("exposure_ref"):
            raise PreregistrationFormatError(
                f"targets.{target_id}: exposure = pre-exposed requires exposure_ref"
            )
        if fields["role"] == "holdout" and fields["exposure"] == "pre-exposed":
            raise PreregistrationFormatError(
                f"targets.{target_id}: a holdout target cannot be pre-exposed"
            )
        arms: tuple[RdsArm, ...] | None = None
        if "arms" in fields:
            try:
                arms = tuple(RdsArm(item.strip()) for item in fields["arms"].split(","))
            except ValueError:
                raise PreregistrationFormatError(
                    f"targets.{target_id}.arms has an unknown arm label"
                ) from None
            undeclared = [arm.value for arm in arms if arm not in declared_arms]
            if undeclared or len(set(arms)) != len(arms):
                raise PreregistrationFormatError(
                    f"targets.{target_id}.arms must be unique declared arms (bad: {undeclared})"
                )
        budget: int | None = None
        if "budget" in fields:
            budget = _int(fields, "budget")
            if budget <= 0:
                raise PreregistrationFormatError(f"targets.{target_id}.budget must be positive")
        targets.append(
            TargetSpec(
                target_id,
                fields["extractor"],
                fields["version"],
                digest,
                "image" if has_image else "lock",
                fields["role"],
                fields["hypothesis"],
                fields["exposure"],
                fields.get("exposure_ref"),
                fields.get("exclusion_ref"),
                arms,
                budget,
            )
        )
    return tuple(targets)


def parse_exposure_ledger(text: str) -> frozenset[tuple[str, str]]:
    """(extractor, version) pairs listed in an exposure ledger (markdown pipe tables).

    Every pipe table whose header has ``extractor`` and ``version`` columns
    (case-insensitive) contributes its rows; prose and other tables are ignored.
    """
    listed: set[tuple[str, str]] = set()
    columns: dict[str, int] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            columns = None
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        lowered = [cell.lower() for cell in cells]
        if "extractor" in lowered and "version" in lowered:
            columns = {"extractor": lowered.index("extractor"), "version": lowered.index("version")}
            continue
        if columns is None or all(set(cell) <= set("-: ") for cell in cells):
            continue
        if max(columns.values()) < len(cells):
            listed.add((cells[columns["extractor"]], cells[columns["version"]]))
    return frozenset(listed)


def ledger_problems(
    preregistration: Preregistration, ledger_text: str | None, ledger_sha256: str | None
) -> tuple[str, ...]:
    """Holdout guard against the committed exposure ledger (the single source of truth).

    The ledger must exist and hash to the registered sha256; a holdout target whose
    (extractor, version) the ledger lists is refused.
    """
    holdouts = [target for target in preregistration.targets if target.role == "holdout"]
    if not holdouts:
        return ()
    if ledger_text is None:
        return (f"exposure ledger {preregistration.exposure_ledger} not readable",)
    if ledger_sha256 != preregistration.exposure_ledger_sha256:
        return (
            f"exposure ledger sha256 {ledger_sha256} != preregistered "
            f"{preregistration.exposure_ledger_sha256}",
        )
    listed = parse_exposure_ledger(ledger_text)
    return tuple(
        f"holdout target {target.target_id} ({target.extractor} {target.version}) is in the "
        "exposure ledger"
        for target in holdouts
        if (target.extractor, target.version) in listed
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
    target_id: str | None = None


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
    expected_digest = preregistration.image_digest
    expected_budget = preregistration.budget
    digest_label = "image digest"
    if preregistration.targets:
        target = (
            preregistration.target(request.target_id) if request.target_id is not None else None
        )
        if request.target_id is None:
            problems.append("target not supplied (the preregistration declares targets)")
        elif target is None:
            problems.append(f"target {request.target_id!r} is not preregistered")
        if target is not None:
            expected_digest = target.digest
            digest_label = f"target {target.target_id} {target.digest_kind} digest"
            if target.budget is not None:
                expected_budget = target.budget
            if target.arms is not None and request.arm not in target.arms:
                problems.append(
                    f"arm {request.arm.value} is not preregistered for target {target.target_id}"
                )
    elif request.target_id is not None:
        problems.append("target supplied but the preregistration declares no targets")
    if request.image_digest is None:
        problems.append(f"{digest_label} not supplied")
    elif expected_digest is not None and request.image_digest != expected_digest:
        problems.append(f"{digest_label} {request.image_digest} != preregistered {expected_digest}")
    if request.random_seed not in preregistration.seeds:
        problems.append(f"seed {request.random_seed} not in preregistered {preregistration.seeds}")
    if request.execution_budget != expected_budget:
        problems.append(f"budget {request.execution_budget} != preregistered {expected_budget}")
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
