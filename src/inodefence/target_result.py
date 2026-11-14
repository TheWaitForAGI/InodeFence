"""Common per-target result record: one JSON shape for every extractor run command.

``inodefence-target-result-v1`` is what a "run this target at this version" command writes:
which target, on which configuration axes, how many runs, the C0/C1/C2 verdict per case, where
the reproduction TAR inputs were saved (with their SHA-256), and which engine revision / image
produced it. Every target (node-tar, python-tarfile, ...) writes the same shape; target-specific
logic lives in the command/adapter that fills it, never here.

Configuration axes are separate fields on purpose. Python tarfile has an extraction-filter axis
(``data`` / ``fully_trusted``) that is independent of its interpreter (runtime) version, so the
two must never share one column. node-tar uses ``target_version`` and leaves the others ``None``.

Contract values are tri-state: ``True`` violated, ``False`` observed and not violated, ``None``
not observed (the mode does not observe that contract, or the run failed). ``None`` is never a
nonviolation. ``observed_contracts`` names what the mode actually observes; a contract outside it
must be ``None`` in every case.

Overall verdict (same rule as ``make regression``): ``ERROR`` if any case is a run error, else
``FAIL`` if any case violated an observed contract, else ``PASS``. ``PASS`` is not a safety proof.
Every record carries the label ``demo run``; it is not a qualification or experiment result.

Optional ``preparation`` (absent in older files, which still read unchanged) records how the cell
image was obtained: ``method`` ``committed-lock`` (a recipe committed in this repository) or
``registry`` (an exploratory build from a lock generated against the public package registry at
run time), the requested and actually installed versions, the SHA-256 of the lock inside the image,
the worker's SHA-256 and the build recipe; for a symbolic request (``latest``) also what was asked
and when it was resolved; and dependencies not seen in committed locks and packages whose install
scripts were disabled (recorded, not refused). A ``registry`` record is labelled
``exploratory demo run`` instead of ``demo run``; the reader enforces that pairing.

A ``mode=campaign`` result (a bounded feedback search, not a fixed fixture set) may also carry an
optional ``campaign`` block: the RNG seed, the execution budget, and the 1-based run index of the
first observed-contract violation (``None`` if the budget ran out with none). Run count and
violation count stay derivable from ``cases``; the block adds only what the cases cannot show. The
block is absent on ``fixture-regression`` results, which serialize exactly as before.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "inodefence-target-result-v1"
LABEL = "demo run"
#: Label of a run whose image was prepared from the public registry (``preparation.method``).
EXPLORATORY_LABEL = "exploratory demo run"
PREPARATION_METHODS = ("committed-lock", "registry")
CONTRACTS = ("C0", "C1", "C2")
#: Two independent per-case axes.
#:
#: *Judgment* (``outcome``): did the oracle get evaluated? ``RUN_ERROR`` = it was NOT (harness or
#: execution-infrastructure error, the run program produced no observation, no post-run snapshot);
#: its contracts are null and the case is un-judged. Any other outcome means the oracle ran;
#: campaigns write ``JUDGED``, fixture-regression results keep their target text (``resolved``,
#: ``declined``, ...).
RUN_ERROR = "run_error"
JUDGED = "judged"
#: *Termination* (``termination``): how the target process ended, independent of judgment. The
#: oracle judges the before/after snapshots whatever the exit status, so a violation left by a
#: rejected, crashed or timed-out extraction is still a violation.
SUCCESS = "success"
REJECTED = "rejected"
FAILED = "failed"
TIMED_OUT = "timed_out"
TERMINATIONS = (SUCCESS, REJECTED, FAILED, TIMED_OUT)

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")


class TargetResultError(ValueError):
    """The record does not satisfy the inodefence-target-result-v1 contract."""


class ResultMode(StrEnum):
    #: Fixed hand-built fixtures run once each (version-pair controlled reproduction).
    FIXTURE_REGRESSION = "fixture-regression"
    #: A bounded feedback campaign; each step is one case.
    CAMPAIGN = "campaign"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class TargetAxes:
    """Independent configuration axes. ``None`` means the axis does not apply to this target."""

    target_version: str | None = None
    runtime_version: str | None = None
    extraction_filter: str | None = None


@dataclass(frozen=True, slots=True)
class CaseVerdict:
    """One case: the oracle's verdicts plus the two independent axes (judgment, termination).

    ``termination`` (one of :data:`TERMINATIONS`, or ``None`` when unknown / no target ran) and
    ``observation_complete`` (whether the observation behind the verdicts was complete) are
    optional so fixture-regression results written before them read unchanged.
    """

    case_id: str
    outcome: str
    c0: bool | None
    c1: bool | None
    c2: bool | None
    termination: str | None = None
    observation_complete: bool | None = None

    @property
    def is_run_error(self) -> bool:
        return self.outcome == RUN_ERROR

    @property
    def is_unjudged(self) -> bool:
        """The oracle was not evaluated: a run error, or no verdict on any contract at all.

        The one shared definition of an un-judged step. Only these feed ``unjudged_steps`` and the
        campaign ERROR rule; a rejection, crash or timeout the oracle judged is NOT un-judged.
        """
        return self.is_run_error or (self.c0, self.c1, self.c2) == (None, None, None)

    @property
    def needs_repro_check(self) -> bool:
        """A violation seen when the target did not succeed or the observation was not complete.

        Still a violation, but shown apart in summaries as "reproduction check needed".
        """
        return self.violated and (
            self.termination != SUCCESS or self.observation_complete is not True
        )

    @property
    def violated(self) -> bool:
        return True in (self.c0, self.c1, self.c2)

    def contract(self, name: str) -> bool | None:
        return {"C0": self.c0, "C1": self.c1, "C2": self.c2}[name]


@dataclass(frozen=True, slots=True)
class ReproInput:
    """A saved TAR input; ``tar_path`` is POSIX-relative to the result file's directory."""

    case_id: str
    tar_path: str
    tar_sha256: str


@dataclass(frozen=True, slots=True)
class Provenance:
    engine_sha: str | None
    engine_dirty: bool
    image_ref: str | None = None
    image_id: str | None = None


@dataclass(frozen=True, slots=True)
class Preparation:
    """How the cell image was obtained; hashes are of the bytes found inside the image."""

    method: str  # one of PREPARATION_METHODS
    requested_version: str  # the exact version the cell ran (after resolving ``requested_spec``)
    installed_version: str
    lock_sha256: str | None
    worker_sha256: str | None
    recipe: str
    requested_spec: str | None = None  # what was asked, when not an exact version (``latest``)
    resolved_at: str | None = None  # UTC time ``requested_spec`` was resolved
    #: ``{"name", "version", "integrity"}`` of packages not in any committed lock (recorded only).
    new_dependencies: tuple[dict[str, str], ...] = ()
    #: Packages that declare install scripts; scripts are always disabled (recorded only).
    install_scripts_disabled: tuple[str, ...] = ()
    #: The exploration path's effect producer inside the image, and its offline check result.
    producer_sha256: str | None = None
    producer_check: str | None = None


@dataclass(frozen=True, slots=True)
class CampaignInfo:
    """Search bookkeeping for a ``mode=campaign`` result; absent on fixture-regression.

    ``seed`` is the RNG seed. ``budget`` is the execution budget, or ``None`` for a run with no
    fixed cap (``run until stopped``). ``runs_to_first_violation`` is the 1-based run index of the
    first case that violated an observed contract, or ``None`` when none did.

    The remaining fields let a large or unbounded campaign keep aggregates without listing every
    run in ``cases`` (``cases`` may then hold only the violations, or be empty). All are optional
    and fall back to what ``cases`` implies, so small-budget results that still list every run, and
    older files, read unchanged:

    - ``runs_executed``: how many cases actually ran; ``None`` -> ``len(cases)``.
    - ``errors``: ``run_error`` cases (the oracle was not evaluated) across all executions;
      ``None`` -> run errors in ``cases``. Always a subset of the un-judged steps.
    - ``stopped_early``: a person stopped the run before the budget or a natural end.
    - ``terminations``: how many executions ended ``success`` / ``rejected`` / ``failed`` /
      ``timed_out`` (the termination axis, independent of judgment); ``None`` -> counted from
      ``cases``. Executions with no known termination are not counted, so the sum may be below the
      number of runs.

    The oracle has a *silent voice*, so an un-judged run is never read as a clean one:

    - ``unjudged_steps``: executions where the oracle was not evaluated (run error, no observation,
      no post-run snapshot); ``None`` -> un-judged cases in ``cases``. Rejections, crashes and
      timeouts the oracle judged are NOT un-judged. Only this count drives a campaign ``ERROR``.
    - ``max_unjudged_ratio``: the ceiling a run was held to, stored so the verdict is reproducible
      from the file alone. ``None`` means no ceiling was set. When the derived ``unjudged_ratio``
      (:attr:`TargetResult.unjudged_ratio`) rises above it -- or every run went un-judged -- the
      campaign verdict is ``ERROR``, not a quiet ``PASS``.
    """

    seed: int
    budget: int | None
    runs_to_first_violation: int | None
    runs_executed: int | None = None
    errors: int | None = None
    stopped_early: bool = False
    unjudged_steps: int | None = None
    max_unjudged_ratio: float | None = None
    terminations: dict[str, int] | None = None


@dataclass(frozen=True, slots=True)
class TargetResult:
    target: str
    axes: TargetAxes
    mode: ResultMode
    observed_contracts: tuple[str, ...]
    cases: tuple[CaseVerdict, ...]
    repro_inputs: tuple[ReproInput, ...]
    provenance: Provenance
    preparation: Preparation | None = None
    #: Optional; only a campaign (feedback search) sets it. Absent (``None``) for regression.
    campaign: CampaignInfo | None = None

    def __post_init__(self) -> None:
        _validate(self)

    @property
    def label(self) -> str:
        registry = self.preparation is not None and self.preparation.method == "registry"
        return EXPLORATORY_LABEL if registry else LABEL

    @property
    def executed(self) -> int:
        if self.campaign is not None and self.campaign.runs_executed is not None:
            return self.campaign.runs_executed
        return len(self.cases)

    @property
    def errored(self) -> int:
        if self.campaign is not None and self.campaign.errors is not None:
            return self.campaign.errors
        return sum(case.is_run_error for case in self.cases)

    @property
    def unjudged_steps(self) -> int:
        """Executions where the oracle was not evaluated (aggregate, else counted from cases)."""
        if self.campaign is not None and self.campaign.unjudged_steps is not None:
            return self.campaign.unjudged_steps
        return sum(case.is_unjudged for case in self.cases)

    @property
    def termination_counts(self) -> dict[str, int]:
        """Executions per termination (aggregate, else counted from cases); every key present."""
        if self.campaign is not None and self.campaign.terminations is not None:
            stored = self.campaign.terminations
            return {name: stored.get(name, 0) for name in TERMINATIONS}
        return {name: sum(case.termination == name for case in self.cases) for name in TERMINATIONS}

    @property
    def unjudged_ratio(self) -> float:
        """Fraction of executions that went un-judged, to 6 decimals; ``0.0`` when none ran."""
        executed = self.executed
        if executed == 0:
            return 0.0
        return round(self.unjudged_steps / executed, 6)

    @property
    def verdict(self) -> Verdict:
        """Campaign: ERROR only from un-judged steps (all of them, or above the stored ceiling) --
        rejections, crashes and timeouts the oracle judged never make it ERROR. Fixture-regression
        keeps its rule unchanged: any run error is ERROR. Then any violation is FAIL, else PASS."""
        if self.mode is ResultMode.CAMPAIGN:
            executed = self.executed
            all_unjudged = executed > 0 and self.unjudged_steps == executed
            max_ratio = self.campaign.max_unjudged_ratio if self.campaign is not None else None
            over_ratio = max_ratio is not None and self.unjudged_ratio > max_ratio
            if all_unjudged or over_ratio:
                return Verdict.ERROR
        elif self.errored:
            return Verdict.ERROR
        if any(case.violated for case in self.cases):
            return Verdict.FAIL
        return Verdict.PASS

    @property
    def violating_cases(self) -> tuple[str, ...]:
        return tuple(case.case_id for case in self.cases if case.violated)

    def to_json_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": SCHEMA,
            "label": self.label,
            "target": self.target,
            "axes": {
                "target_version": self.axes.target_version,
                "runtime_version": self.axes.runtime_version,
                "extraction_filter": self.axes.extraction_filter,
            },
            "mode": self.mode.value,
            "observed_contracts": list(self.observed_contracts),
            "runs": {"executed": self.executed, "errored": self.errored},
            "verdict": self.verdict.value,
            "violating_cases": list(self.violating_cases),
            "cases": [_case_json(c) for c in self.cases],
            "repro_inputs": [
                {"case_id": r.case_id, "tar_path": r.tar_path, "tar_sha256": r.tar_sha256}
                for r in self.repro_inputs
            ],
            "provenance": {
                "engine_sha": self.provenance.engine_sha,
                "engine_dirty": self.provenance.engine_dirty,
                "image_ref": self.provenance.image_ref,
                "image_id": self.provenance.image_id,
            },
        }
        if self.preparation is not None:
            p = self.preparation
            data["preparation"] = {
                "method": p.method,
                "requested_version": p.requested_version,
                "installed_version": p.installed_version,
                "lock_sha256": p.lock_sha256,
                "worker_sha256": p.worker_sha256,
                "recipe": p.recipe,
                "requested_spec": p.requested_spec,
                "resolved_at": p.resolved_at,
                "new_dependencies": [dict(d) for d in p.new_dependencies],
                "install_scripts_disabled": list(p.install_scripts_disabled),
                "producer_sha256": p.producer_sha256,
                "producer_check": p.producer_check,
            }
        if self.campaign is not None:
            data["campaign"] = {
                "seed": self.campaign.seed,
                "budget": self.campaign.budget,
                "runs_to_first_violation": self.campaign.runs_to_first_violation,
                "runs_executed": self.campaign.runs_executed,
                "errors": self.campaign.errors,
                "stopped_early": self.campaign.stopped_early,
                "unjudged_steps": self.campaign.unjudged_steps,
                "terminations": (
                    None
                    if self.campaign.terminations is None
                    else dict(sorted(self.campaign.terminations.items()))
                ),
                "max_unjudged_ratio": self.campaign.max_unjudged_ratio,
                "unjudged_ratio": self.unjudged_ratio,
            }
        return data

    def dumps(self) -> str:
        return json.dumps(self.to_json_dict(), indent=2, sort_keys=True) + "\n"


def _case_json(case: CaseVerdict) -> dict[str, Any]:
    """A case as JSON; the termination axis keys appear only when set, so results written before
    them (fixture-regression) serialize byte-identically."""
    data: dict[str, Any] = {
        "case_id": case.case_id,
        "outcome": case.outcome,
        "c0": case.c0,
        "c1": case.c1,
        "c2": case.c2,
    }
    if case.termination is not None:
        data["termination"] = case.termination
    if case.observation_complete is not None:
        data["observation_complete"] = case.observation_complete
    return data


def repro_input(case_id: str, tar_path: str, tar_bytes: bytes) -> ReproInput:
    """Describe a TAR input saved at ``tar_path`` (relative), hashing its bytes."""
    return ReproInput(case_id, tar_path, sha256(tar_bytes).hexdigest())


def _validate(result: TargetResult) -> None:
    if not isinstance(result.target, str) or not result.target:
        raise TargetResultError("target must be a non-empty name")
    if not isinstance(result.provenance.engine_dirty, bool):
        raise TargetResultError("engine_dirty must be true/false")
    if not isinstance(result.mode, ResultMode):
        raise TargetResultError(f"mode must be a ResultMode, got {result.mode!r}")
    observed = result.observed_contracts
    if not observed or len(set(observed)) != len(observed) or set(observed) - set(CONTRACTS):
        raise TargetResultError(f"observed_contracts must be distinct items of {CONTRACTS}")
    case_ids = [case.case_id for case in result.cases]
    if len(set(case_ids)) != len(case_ids) or not all(case_ids):
        raise TargetResultError("case_id values must be non-empty and unique")
    for case in result.cases:
        for name in CONTRACTS:
            value = case.contract(name)
            if value is not None and not isinstance(value, bool):
                raise TargetResultError(f"{case.case_id}.{name} must be true/false/null")
            if name not in observed and value is not None:
                raise TargetResultError(
                    f"{case.case_id}.{name} is set but {name} is not an observed contract"
                )
        if case.is_run_error and case.violated:
            raise TargetResultError(f"{case.case_id} is a run error but reports a violation")
        if case.termination is not None and case.termination not in TERMINATIONS:
            raise TargetResultError(
                f"{case.case_id}.termination must be one of {TERMINATIONS} or null"
            )
        if case.observation_complete is not None and type(case.observation_complete) is not bool:
            raise TargetResultError(f"{case.case_id}.observation_complete must be true/false/null")
    known = set(case_ids)
    seen_paths: set[str] = set()
    for item in result.repro_inputs:
        if item.case_id not in known:
            raise TargetResultError(f"repro input for unknown case {item.case_id!r}")
        path = PurePosixPath(item.tar_path)
        if not item.tar_path or path.is_absolute() or ".." in path.parts or "\\" in item.tar_path:
            raise TargetResultError(f"tar_path must be relative and inside: {item.tar_path!r}")
        if item.tar_path in seen_paths:
            raise TargetResultError(f"duplicate tar_path {item.tar_path!r}")
        seen_paths.add(item.tar_path)
        if _SHA256_RE.fullmatch(item.tar_sha256) is None:
            raise TargetResultError(f"tar_sha256 must be 64 lowercase hex: {item.tar_sha256!r}")
    _validate_preparation(result.preparation)
    _validate_campaign(result)
    sha = result.provenance.engine_sha
    if sha is not None and _GIT_SHA_RE.fullmatch(sha) is None:
        raise TargetResultError(f"engine_sha must be a 40-hex git commit or null: {sha!r}")


def _validate_campaign(result: TargetResult) -> None:
    campaign = result.campaign
    if campaign is None:
        return
    if result.mode is not ResultMode.CAMPAIGN:
        raise TargetResultError("campaign block is only valid when mode is campaign")
    if type(campaign.seed) is not int:
        raise TargetResultError("campaign.seed must be an integer")
    if type(campaign.stopped_early) is not bool:
        raise TargetResultError("campaign.stopped_early must be true/false")
    if campaign.runs_executed is not None and (
        type(campaign.runs_executed) is not int or campaign.runs_executed < len(result.cases)
    ):
        raise TargetResultError("campaign.runs_executed must be an integer >= len(cases)")
    executed = result.executed
    if campaign.errors is not None and (
        type(campaign.errors) is not int or not 0 <= campaign.errors <= executed
    ):
        raise TargetResultError("campaign.errors must be an integer in 0..runs")
    stored = campaign.unjudged_steps
    if stored is not None:
        if type(stored) is not int or not 0 <= stored <= executed:
            raise TargetResultError("campaign.unjudged_steps must be null or an integer in 0..runs")
        listed_unjudged = sum(case.is_unjudged for case in result.cases)
        if stored < listed_unjudged:
            raise TargetResultError(
                f"campaign.unjudged_steps {stored} is below the {listed_unjudged} un-judged "
                "case(s) listed (the oracle was not evaluated)"
            )
    if result.errored > result.unjudged_steps:
        raise TargetResultError(
            f"campaign run errors ({result.errored}) exceed unjudged_steps "
            f"({result.unjudged_steps}); a run error is always un-judged"
        )
    terminations = campaign.terminations
    if terminations is not None:
        if not isinstance(terminations, dict) or set(terminations) - set(TERMINATIONS):
            raise TargetResultError(f"campaign.terminations keys must be from {TERMINATIONS}")
        if not all(type(n) is int and n >= 0 for n in terminations.values()):
            raise TargetResultError("campaign.terminations counts must be non-negative integers")
        if sum(terminations.values()) > executed:
            raise TargetResultError("campaign.terminations add up to more than the runs")
        for name in TERMINATIONS:
            listed = sum(case.termination == name for case in result.cases)
            if terminations.get(name, 0) < listed:
                raise TargetResultError(
                    f"campaign.terminations[{name!r}] is below the {listed} listed case(s)"
                )
    ratio = campaign.max_unjudged_ratio
    if ratio is not None and (type(ratio) not in (int, float) or not 0.0 <= ratio <= 1.0):
        raise TargetResultError("campaign.max_unjudged_ratio must be null or a number in 0.0..1.0")
    # budget may be null ("run until stopped"); otherwise it must cover the runs that happened.
    if campaign.budget is not None and (
        type(campaign.budget) is not int or campaign.budget < 1 or campaign.budget < executed
    ):
        raise TargetResultError("campaign.budget must be null or an integer >= the number of runs")
    first = campaign.runs_to_first_violation
    has_violation = bool(result.violating_cases)
    if first is None:
        if has_violation:
            raise TargetResultError("runs_to_first_violation must be set when a case violated")
    else:
        if not has_violation:
            raise TargetResultError("runs_to_first_violation must be null when nothing violated")
        if type(first) is not int or not 1 <= first <= executed:
            raise TargetResultError("runs_to_first_violation must be an integer in 1..runs")


def _validate_preparation(prep: Preparation | None) -> None:
    if prep is None:
        return
    if prep.method not in PREPARATION_METHODS:
        raise TargetResultError(f"preparation.method must be one of {PREPARATION_METHODS}")
    for name in ("requested_version", "installed_version", "recipe"):
        if not isinstance(getattr(prep, name), str) or not getattr(prep, name):
            raise TargetResultError(f"preparation.{name} must be a non-empty string")
    if prep.installed_version != prep.requested_version:
        raise TargetResultError(
            f"preparation installed {prep.installed_version!r} != requested "
            f"{prep.requested_version!r}"
        )
    for name in ("lock_sha256", "worker_sha256", "producer_sha256"):
        value = getattr(prep, name)
        if value is not None and _SHA256_RE.fullmatch(value) is None:
            raise TargetResultError(f"preparation.{name} must be 64 lowercase hex or null")
    if (prep.requested_spec is None) != (prep.resolved_at is None):
        raise TargetResultError("preparation.requested_spec and resolved_at go together")
    for dep in prep.new_dependencies:
        if not isinstance(dep, dict) or set(dep) != {"name", "version", "integrity"}:
            raise TargetResultError(
                "preparation.new_dependencies items need name/version/integrity"
            )
    if not all(isinstance(n, str) and n for n in prep.install_scripts_disabled):
        raise TargetResultError("preparation.install_scripts_disabled must be package names")


_PREPARATION_KEYS = {
    "method",
    "requested_version",
    "installed_version",
    "lock_sha256",
    "worker_sha256",
    "recipe",
    "requested_spec",
    "resolved_at",
    "new_dependencies",
    "install_scripts_disabled",
    "producer_sha256",
    "producer_check",
}

_CAMPAIGN_KEYS = {"seed", "budget", "runs_to_first_violation"}
#: Added for large/unbounded campaigns; absent in older or small-budget blocks (read as defaults).
#: ``unjudged_ratio`` is derived (not a constructor arg): tolerated on read, then cross-checked.
_CAMPAIGN_OPTIONAL = {
    "runs_executed",
    "errors",
    "stopped_early",
    "unjudged_steps",
    "max_unjudged_ratio",
    "unjudged_ratio",
    "terminations",
}

_TOP_KEYS = {
    "schema",
    "label",
    "target",
    "axes",
    "mode",
    "observed_contracts",
    "runs",
    "verdict",
    "violating_cases",
    "cases",
    "repro_inputs",
    "provenance",
}


def _keys(obj: object, expected: set[str], where: str) -> Mapping[str, Any]:
    if not isinstance(obj, Mapping):
        raise TargetResultError(f"{where} must be an object")
    keys = set(obj)
    if keys != expected:
        raise TargetResultError(
            f"{where} keys mismatch: missing {sorted(expected - keys)}, "
            f"unexpected {sorted(keys - expected)}"
        )
    return obj


def _keys_optional(
    obj: object, required: set[str], optional: set[str], where: str
) -> Mapping[str, Any]:
    """Like ``_keys`` but tolerant of named optional keys; unknown keys are still rejected."""
    if not isinstance(obj, Mapping):
        raise TargetResultError(f"{where} must be an object")
    keys = set(obj)
    missing = required - keys
    unexpected = keys - required - optional
    if missing or unexpected:
        raise TargetResultError(
            f"{where} keys mismatch: missing {sorted(missing)}, unexpected {sorted(unexpected)}"
        )
    return obj


def from_json_dict(data: object) -> TargetResult:
    """Strict reader: exact keys, and the derived fields must match what the cases imply."""
    optional = {"preparation", "campaign"} & set(data) if isinstance(data, Mapping) else set()
    top = _keys(data, _TOP_KEYS | optional, "result")
    if top["schema"] != SCHEMA:
        raise TargetResultError(f"schema must be {SCHEMA!r}, got {top['schema']!r}")
    if top["label"] not in (LABEL, EXPLORATORY_LABEL):
        raise TargetResultError(f"label must be {LABEL!r}, got {top['label']!r}")
    preparation = None
    if "preparation" in top:
        prep = dict(_keys(top["preparation"], _PREPARATION_KEYS, "preparation"))
        prep["new_dependencies"] = tuple(_as_list(prep["new_dependencies"], "new_dependencies"))
        prep["install_scripts_disabled"] = tuple(
            _as_list(prep["install_scripts_disabled"], "install_scripts_disabled")
        )
        preparation = Preparation(**prep)
    campaign = None
    campaign_block: Mapping[str, Any] | None = None
    if "campaign" in top:
        campaign_block = _keys_optional(
            top["campaign"], _CAMPAIGN_KEYS, _CAMPAIGN_OPTIONAL, "campaign"
        )
        campaign = CampaignInfo(
            seed=campaign_block["seed"],
            budget=campaign_block["budget"],
            runs_to_first_violation=campaign_block["runs_to_first_violation"],
            runs_executed=campaign_block.get("runs_executed"),
            errors=campaign_block.get("errors"),
            stopped_early=campaign_block.get("stopped_early", False),
            unjudged_steps=campaign_block.get("unjudged_steps"),
            max_unjudged_ratio=campaign_block.get("max_unjudged_ratio"),
            terminations=campaign_block.get("terminations"),
        )
    axes = _keys(top["axes"], {"target_version", "runtime_version", "extraction_filter"}, "axes")
    prov = _keys(
        top["provenance"], {"engine_sha", "engine_dirty", "image_ref", "image_id"}, "provenance"
    )
    try:
        mode = ResultMode(top["mode"])
    except ValueError as error:
        raise TargetResultError(f"unknown mode {top['mode']!r}") from error
    case_keys = {"case_id", "outcome", "c0", "c1", "c2"}
    case_optional = {"termination", "observation_complete"}
    repro_keys = {"case_id", "tar_path", "tar_sha256"}
    result = TargetResult(
        target=top["target"],
        axes=TargetAxes(axes["target_version"], axes["runtime_version"], axes["extraction_filter"]),
        mode=mode,
        observed_contracts=tuple(top["observed_contracts"]),
        cases=tuple(
            CaseVerdict(**_keys_optional(c, case_keys, case_optional, "case"))
            for c in _as_list(top["cases"], "cases")
        ),
        repro_inputs=tuple(
            ReproInput(**_keys(r, repro_keys, "repro_input"))
            for r in _as_list(top["repro_inputs"], "repro_inputs")
        ),
        provenance=Provenance(
            prov["engine_sha"], prov["engine_dirty"], prov["image_ref"], prov["image_id"]
        ),
        preparation=preparation,
        campaign=campaign,
    )
    expected = result.to_json_dict()
    for derived in ("label", "runs", "verdict", "violating_cases"):
        if top[derived] != expected[derived]:
            raise TargetResultError(
                f"{derived} {top[derived]!r} does not match the cases ({expected[derived]!r})"
            )
    # ``unjudged_ratio`` is derived inside the campaign block; cross-check it when a file stored it
    # (older files have no such key and are read unchanged).
    if campaign_block is not None and "unjudged_ratio" in campaign_block:
        stored_ratio = campaign_block["unjudged_ratio"]
        if stored_ratio != result.unjudged_ratio:
            raise TargetResultError(
                f"campaign.unjudged_ratio {stored_ratio!r} does not match the runs "
                f"({result.unjudged_ratio!r})"
            )
    return result


def _as_list(value: object, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise TargetResultError(f"{where} must be a list")
    return value


def load_target_result(path: Path, *, verify_inputs: bool = True) -> TargetResult:
    """Read a result file; by default also re-hash every saved TAR input next to it."""
    result = from_json_dict(json.loads(path.read_text(encoding="utf-8")))
    if verify_inputs:
        for item in result.repro_inputs:
            tar = path.parent / item.tar_path
            if not tar.is_file():
                raise TargetResultError(f"repro input missing: {item.tar_path}")
            if sha256(tar.read_bytes()).hexdigest() != item.tar_sha256:
                raise TargetResultError(f"repro input hash mismatch: {item.tar_path}")
    return result
