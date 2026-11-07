"""Per-cell R/D/S-u summary from a controller-path demo report (JSON), not raw steps.

The native loop runs inside the controller (``scripts/run_effect_demo.py``) and
leaves a demo report (``effect_campaign_report``) plus a ``.steps.jsonl`` file of the
steps finished so far (kept on abort). This module turns those recorded step
records into the same ``RdsCellSummary`` that ``rds.summarize_rds_steps`` builds
from in-memory steps, so a G1 smoke or an EXP-0 cell run through the existing
controller path needs no controller change.

What the report cannot give (and the summary says so through its wrapper
``notes``):

* ``u_viol`` reads the per-step ``oracle_fingerprints`` (the oracle's normalized
  C1/C2 classes of every step, eligibility-independent; report schema 4), exactly
  the set the in-memory summary builds from the verdicts (``u_viol_source =
  "oracle"``). Records that predate ``oracle_fingerprints`` fall back to the
  recorded ``new_violation_fingerprints`` (``u_viol_source = "feedback-fallback"``);
  the loop records those only for feedback-eligible observations, so under the
  fallback a hit on an ineligible trace is not in ``u_viol`` (it is counted in
  ``unfingerprinted_hit_steps``). ``u_viol_feedback`` always counts the recorded
  feedback fingerprints (a search-behaviour descriptor). ``hit``/``t_first`` read
  the per-step ``oracle`` verdicts in every case.
* vocabulary pools and the BEFORE snapshot's protected paths are reconstructed
  from the per-step ``name_segments`` / ``before_protected_paths`` records (reports
  written by this engine version); older records lack them and report empty.
* ``observation_failures`` counts steps with recorded observation failures or an
  invalid stream (the in-memory flag also folds integrity, which the record lacks).
"""

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inodefence.model import ContractId, EffectFeedbackKeyKind, EffectTargetTermination
from inodefence.mutator import m1
from inodefence.mutator.m1_addressing import COMPONENTS as PROTECTED_COMPONENTS

from .rds import (
    HIT_CONTRACTS,
    U_VIOL_SOURCE_FEEDBACK_FALLBACK,
    U_VIOL_SOURCE_ORACLE,
    RdsArm,
    RdsCellConfig,
    RdsCellSummary,
    VocabularyMode,
    summary_record,
)

NOTES = (
    "u_viol reads oracle_fingerprints (every step's oracle C1/C2 classes, "
    "eligibility-independent; u_viol_source=oracle); records without them fall back to "
    "recorded new_violation_fingerprints (u_viol_source=feedback-fallback), where hit "
    "steps whose trace was not feedback-eligible carry no fingerprint and are only "
    "counted in unfingerprinted_hit_steps",
    "vocabulary pools are reconstructed from per-step name_segments exactly as the "
    "mutator saw them (fixed-baseline: step 0 before; accumulated: union of observed); "
    "empty when the records predate name_segments",
    "observation_failures = steps with recorded trace observation failures or an invalid stream",
)


class ReportFormatError(ValueError):
    """A step record or report does not have the demo-report shape."""


def _str(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise ReportFormatError(f"{what} must be a string")
    return value


def _record_hit_contracts(record: Mapping[str, Any]) -> frozenset[ContractId]:
    oracle = record.get("oracle")
    if not isinstance(oracle, Mapping):
        raise ReportFormatError(f"step {record.get('index')} lacks an oracle mapping")
    return frozenset(ContractId(key) for key, violated in oracle.items() if violated)


def _fingerprint_key(item: Mapping[str, Any]) -> tuple[ContractId, str]:
    value = item.get("value", item)
    contract = ContractId(_str(value.get("contract_id"), "fingerprint contract_id"))
    return contract, json.dumps(value, sort_keys=True, separators=(",", ":"))


def _key_kind(item: Mapping[str, Any]) -> str:
    value = item.get("value", item)
    return _str(value.get("kind"), "effect key kind")


def _pool(observed: set[str]) -> tuple[str, ...]:
    return m1.COMPONENTS + tuple(sorted(observed))


def vocabulary_pools_from_records(
    mode: VocabularyMode, records: Sequence[Mapping[str, Any]], initial_count: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(after seed phase, final) pools from recorded ``name_segments``; empty if absent."""
    if mode == VocabularyMode.GENERIC:
        return m1.COMPONENTS, m1.COMPONENTS
    if mode == VocabularyMode.PROTECTED_COMPONENTS:
        return PROTECTED_COMPONENTS, PROTECTED_COMPONENTS
    segments: list[Mapping[str, Any]] = []
    for record in records:
        item = record.get("name_segments")
        if not isinstance(item, Mapping):
            return (), ()
        segments.append(item)
    if not segments:
        return (), ()
    if mode == VocabularyMode.OBSERVED_NAMES:
        fixed = _pool(set(segments[0]["before"]))
        return fixed, fixed
    after_seed: set[str] = set()
    for item in segments[:initial_count]:
        after_seed |= set(item["observed"])
    final = set(after_seed)
    for item in segments[initial_count:]:
        final |= set(item["observed"])
    return _pool(after_seed), _pool(final)


@dataclass(frozen=True, slots=True)
class ReportSummary:
    """The cell summary plus the report-specific caveats."""

    summary: RdsCellSummary
    unfingerprinted_hit_steps: int
    notes: tuple[str, ...] = NOTES

    def record(self) -> dict[str, object]:
        return {
            "summary": summary_record(self.summary),
            "unfingerprinted_hit_steps": self.unfingerprinted_hit_steps,
            "notes": list(self.notes),
        }


def summarize_report_records(
    records: Sequence[Mapping[str, Any]],
    config: RdsCellConfig,
    *,
    aborted_at_step: int | None = None,
    abort_reason: str | None = None,
    sentinel_set: Mapping[str, object] | None = None,
) -> ReportSummary:
    """Build the per-cell summary from recorded step records (report ``steps``/JSONL)."""
    if not isinstance(config, RdsCellConfig):
        raise ReportFormatError("summary requires an RdsCellConfig")
    steps = tuple(records)
    if [step.get("index") for step in steps] != list(range(len(steps))):
        raise ReportFormatError("step records must be contiguous from index 0")
    if len(steps) > config.execution_budget:
        raise ReportFormatError("recorded steps exceed the execution budget")
    if (aborted_at_step is None) != (abort_reason is None):
        raise ReportFormatError("abort step and reason must appear together")
    if aborted_at_step is not None and aborted_at_step != len(steps):
        raise ReportFormatError("abort step index must equal the number of completed steps")
    completed = len(steps)
    aborted = aborted_at_step is not None
    complete = not aborted and completed == config.execution_budget
    if not complete and not aborted:
        raise ReportFormatError("an incomplete cell must declare its abort step and reason")

    hit_indexes: list[int] = []
    per_contract: dict[ContractId, list[int]] = {contract: [] for contract in ContractId}
    oracle_hit: set[tuple[ContractId, str]] = set()
    oracle_c0: set[tuple[ContractId, str]] = set()
    feedback_hit: set[tuple[ContractId, str]] = set()
    feedback_c0: set[tuple[ContractId, str]] = set()
    oracle_records = 0
    unfingerprinted = 0
    boundary_keys = 0
    unique_keys = 0
    retained = 0
    rejected = 0
    observation_failures = 0
    initial = 0
    for step in steps:
        feedback = step.get("feedback")
        trace = step.get("trace")
        if not isinstance(feedback, Mapping) or not isinstance(trace, Mapping):
            raise ReportFormatError(f"step {step['index']} lacks feedback/trace mappings")
        contracts = _record_hit_contracts(step)
        for contract in contracts:
            per_contract[contract].append(step["index"])
        hit = bool(contracts & HIT_CONTRACTS)
        if hit:
            hit_indexes.append(step["index"])
        if "oracle_fingerprints" in step:
            oracle_records += 1
            for item in step["oracle_fingerprints"]:
                contract, key = _fingerprint_key(item)
                (oracle_hit if contract in HIT_CONTRACTS else oracle_c0).add((contract, key))
        for item in feedback.get("new_violation_fingerprints", ()):
            contract, key = _fingerprint_key(item)
            (feedback_hit if contract in HIT_CONTRACTS else feedback_c0).add((contract, key))
        if hit and not feedback.get("feedback_eligible", False):
            unfingerprinted += 1
        keys = feedback.get("new_effect_keys", ())
        unique_keys += len(keys)
        boundary_keys += sum(
            1
            for item in keys
            if _key_kind(item) == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT.value
        )
        retained += 1 if feedback.get("retained") else 0
        if feedback.get("trace_termination") == EffectTargetTermination.REJECTED.value:
            rejected += 1
        if trace.get("observation_failures") or feedback.get("trace_completeness") == "invalid":
            observation_failures += 1
        if step.get("origin") == "seed":
            initial += 1

    first_hit = hit_indexes[0] + 1 if hit_indexes else None
    if oracle_records == len(steps):
        u_viol, u_viol_c0, u_viol_source = len(oracle_hit), len(oracle_c0), U_VIOL_SOURCE_ORACLE
    else:
        # Older records (or a mixed report) lack the oracle classes on some step: fall
        # back to what the loop fed back and say so; never mix the two sources.
        u_viol, u_viol_c0 = len(feedback_hit), len(feedback_c0)
        u_viol_source = U_VIOL_SOURCE_FEEDBACK_FALLBACK
    after_seed, final = vocabulary_pools_from_records(config.vocabulary_mode, steps, initial)
    protected = steps[0].get("before_protected_paths", ()) if steps else ()

    def first(contract: ContractId) -> int | None:
        return per_contract[contract][0] + 1 if per_contract[contract] else None

    summary = RdsCellSummary(
        arm=config.arm,
        r_variant=config.r_variant if config.arm == RdsArm.R else None,
        search_policy=config.search_policy,
        mutation_policy=config.mutation_policy,
        vocabulary_mode=config.vocabulary_mode,
        random_seed=config.random_seed,
        execution_budget=config.execution_budget,
        initial_cases=initial,
        executions_completed=completed,
        complete=complete,
        aborted=aborted,
        abort_step_index=aborted_at_step,
        abort_reason=abort_reason,
        hit=first_hit is not None,
        t_first=first_hit if first_hit is not None else completed,
        t_first_event=1 if first_hit is not None else 0,
        t_first_censored=first_hit is None,
        first_hit_step_index=hit_indexes[0] if hit_indexes else None,
        hit_steps=len(hit_indexes),
        u_viol=u_viol,
        u_viol_c0=u_viol_c0,
        u_viol_source=u_viol_source,
        u_viol_feedback=len(feedback_hit),
        first_c0=first(ContractId.C0),
        first_c1=first(ContractId.C1),
        first_c2=first(ContractId.C2),
        c0_steps=len(per_contract[ContractId.C0]),
        rejected_executions=rejected,
        observation_failures=observation_failures,
        boundary_attempt_keys=boundary_keys,
        unique_effect_keys=unique_keys,
        retained_cases=retained,
        vocabulary_pool_after_seed=after_seed,
        vocabulary_pool_final=final,
        observed_protected_paths=tuple(_str(item, "protected path") for item in protected),
        sentinel_set=sentinel_set,
    )
    return ReportSummary(summary, unfingerprinted)


def _rank(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, -(-int(fraction * len(ordered) * 1000) // 1000) - 1))
    return ordered[index]


def timing_record(report: Mapping[str, Any] | None, execution_mode: str | None) -> dict[str, Any]:
    """Timing fields for the statistics lane; every unknown value is None, never guessed.

    Reads the demo report's ``timing`` (``total_seconds`` and per-case ``wall_seconds`` /
    ``target_seconds`` in step order). ``execution_mode`` is the caller's declaration of
    the path used (``per-case-container`` for the controller demo path).
    """
    timing = report.get("timing") if isinstance(report, Mapping) else None
    wall = None
    steps_wall: list[float] | None = None
    steps_target: list[float] | None = None
    if isinstance(timing, Mapping):
        total = timing.get("total_seconds")
        wall = float(total) if isinstance(total, int | float) else None
        per_case = timing.get("per_case")
        if isinstance(per_case, list):
            steps_wall = [float(item["wall_seconds"]) for item in per_case]
            steps_target = [float(item["target_seconds"]) for item in per_case]
    executions = len(steps_wall) if steps_wall is not None else None
    return {
        "wall_seconds": wall,
        "step_wall_seconds": steps_wall,
        "step_target_seconds": steps_target,
        "full_step_seconds_p50": _rank(steps_wall, 0.5) if steps_wall else None,
        "full_step_seconds_p95": _rank(steps_wall, 0.95) if steps_wall else None,
        "full_step_seconds_max": max(steps_wall) if steps_wall else None,
        "exec_per_hour": (executions / wall * 3600.0) if wall and executions else None,
        "execution_mode": execution_mode,
    }


def environment_record(
    report: Mapping[str, Any] | None, host: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Image/target/host passthrough; absent values stay None."""
    source: Mapping[str, Any] = report if isinstance(report, Mapping) else {}
    host_map: Mapping[str, Any] = host if isinstance(host, Mapping) else {}
    return {
        "host_machine": host_map.get("machine"),
        "host_system": host_map.get("system"),
        "host_release": host_map.get("release"),
        "docker_server_version": host_map.get("docker_server_version"),
        "image_id": source.get("image_id"),
        "recipe_sha256": source.get("recipe_sha256"),
        "node_tar_version": source.get("node_tar_version"),
        "node_version": source.get("node_version"),
    }


def check_report_config(report: Mapping[str, Any], config: RdsCellConfig) -> None:
    """Refuse a report whose recorded config is not the cell the caller planned."""
    recorded = report.get("config")
    if not isinstance(recorded, Mapping):
        return
    expected = {
        "random_seed": config.random_seed,
        "execution_budget": config.execution_budget,
        "search_policy": config.search_policy.value,
        "mutation_policy": config.mutation_policy.value,
    }
    differences = {
        key: (recorded.get(key), value)
        for key, value in expected.items()
        if recorded.get(key) != value
    }
    if differences:
        raise ReportFormatError(f"report config differs from the planned cell: {differences}")


@dataclass(frozen=True, slots=True)
class LoadedCell:
    """Step records and abort facts read from a cell's report and/or steps JSONL."""

    records: tuple[Mapping[str, Any], ...]
    steps_from: str
    report_present: bool
    aborted_at_step: int | None
    abort_reason: str | None
    report: Mapping[str, Any] | None
    torn_last_line: bool = False


def load_cell_files(
    report_path: Path, steps_path: Path, *, drop_torn_last_line: bool = False
) -> LoadedCell:
    """Read a cell's evidence; a missing report means the run did not finish cleanly.

    Precedence: a report with ``steps`` is authoritative; otherwise the steps JSONL
    (written before each next case) supplies the completed steps and the cell is
    treated as aborted after them, with the report's ``aborted`` reason when present.

    ``drop_torn_last_line`` is for a cell the launcher's watchdog terminated, and only the
    caller knows that: its last line may be cut by the kill. Only an unparsable last line is
    dropped and reported as ``torn_last_line``. Anywhere else, or without the flag, the
    parse error stands.
    """
    report: Mapping[str, Any] | None = None
    if report_path.is_file():
        loaded = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, Mapping):
            raise ReportFormatError(f"{report_path} is not a JSON object")
        report = loaded
    records: list[Mapping[str, Any]] = []
    steps_from = "none"
    torn_last_line = False
    if report is not None and isinstance(report.get("steps"), list):
        records = list(report["steps"])
        steps_from = "report"
    elif steps_path.is_file():
        lines = [
            line for line in steps_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        for position, line in enumerate(lines):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                if not drop_torn_last_line or position != len(lines) - 1:
                    raise
                torn_last_line = True
        steps_from = "steps_jsonl"
    aborted_at: int | None = None
    reason: str | None = None
    if report is not None and isinstance(report.get("aborted"), Mapping):
        aborted = report["aborted"]
        aborted_at = len(records)
        reason = f"{aborted.get('reason')} (reported step_index={aborted.get('step_index')})"
    elif report is None:
        aborted_at = len(records)
        reason = "no report written (controller run did not finish; see the cell log)"
    return LoadedCell(
        tuple(records), steps_from, report is not None, aborted_at, reason, report, torn_last_line
    )


def registered_dense_detail(
    records: Sequence[Mapping[str, Any]], report: Mapping[str, Any] | None
) -> dict[str, object]:
    """Per-cell inputs of the registered dense table that the cell summary does not carry.

    Boundary keys keep their identity so an arm's unique keys are a union, not a sum of per-cell
    counts; they come only from clean traces, as the novelty index admits them. Failure kinds count
    steps with that kind: a step with several kinds counts once under each, so the kinds do not sum
    to a total. An abort stub with ``observed`` means the target ran and its result was dropped, a
    lower bound on steps lost after execution.
    """
    boundary: set[str] = set()
    failure_kinds: Counter[str] = Counter()
    ineligible = 0
    for step in records:
        feedback = step.get("feedback")
        trace = step.get("trace")
        if not isinstance(feedback, Mapping) or not isinstance(trace, Mapping):
            raise ReportFormatError(f"step {step.get('index')} lacks feedback/trace mappings")
        for item in feedback.get("new_effect_keys", ()):
            if _key_kind(item) == EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT.value:
                boundary.add(json.dumps(item, sort_keys=True, separators=(",", ":")))
        failure_kinds.update(
            {
                _str(failure.get("kind"), "observation failure kind")
                for failure in trace.get("observation_failures", ())
            }
        )
        if not feedback.get("feedback_eligible", False):
            ineligible += 1
    aborted = report.get("aborted") if report is not None else None
    return {
        "boundary_keys": sorted(boundary),
        "observation_failures_by_kind": dict(sorted(failure_kinds.items())),
        "feedback_ineligible_steps": ineligible,
        "recorded_steps": len(records),
        "abort_observed_present": isinstance(aborted, Mapping)
        and aborted.get("observed") is not None,
    }


def consistent_prefix(steps_path: Path) -> dict[str, int]:
    """The steps before a record's first inconsistency, for the record-damage sensitivity only.

    Stops at the first line that does not parse, is not an object with the next index, or has no
    readable oracle. ``t_first_event`` is 1 when the prefix holds a C1 or C2 step.
    """
    count = 0
    first_hit: int | None = None
    if steps_path.is_file():
        for line in steps_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                step = json.loads(line)
                if not isinstance(step, Mapping) or step.get("index") != count:
                    break
                hit = bool(_record_hit_contracts(step) & HIT_CONTRACTS)
            except (json.JSONDecodeError, ReportFormatError, ValueError):
                break
            count += 1
            if hit and first_hit is None:
                first_hit = count
    return {
        "steps": count,
        "t_first": first_hit if first_hit is not None else count,
        "t_first_event": int(first_hit is not None),
    }


def summarize_cell_files(
    report_path: Path,
    steps_path: Path,
    config: RdsCellConfig,
    *,
    sentinel_set: Mapping[str, object] | None = None,
) -> tuple[ReportSummary, LoadedCell]:
    """Summarize one cell from its files; the planned config is cross-checked."""
    loaded = load_cell_files(report_path, steps_path)
    if loaded.report is not None:
        check_report_config(loaded.report, config)
    aborted_at = loaded.aborted_at_step
    reason = loaded.abort_reason
    if aborted_at is None and len(loaded.records) < config.execution_budget:
        aborted_at = len(loaded.records)
        reason = "report has fewer steps than the budget and no abort record"
    summary = summarize_report_records(
        loaded.records,
        config,
        aborted_at_step=aborted_at,
        abort_reason=reason,
        sentinel_set=sentinel_set,
    )
    return summary, loaded
