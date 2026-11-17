"""G1 v2 gate: per-target, per-arm vocabulary equality and three-valued id checks (v2 only).

Known limitation of the old path, kept as is (its file is a shared execution-path file and stays
byte-identical): ``scripts/run_g1_smoke.vocabulary_equality`` groups cells by seed only, so in a
multi-target plan cells of different targets with the same seed overwrite each other and an
unequal pool of one target can pass unseen (#524). Single-target registered runs (v1) are not
affected. The v2 gate is this module; ``scripts/check_g1_v2.py`` writes its result next to, not
into, the launcher's own ``summaries/`` (to ``summaries-v2/``), so the registered tool chain's
output stays byte-identical. Nothing here imports ``run_g1_smoke`` or ``run_exp0``. The logic was
first written for ``run_g1_smoke`` (commits 49ae01a, 1f3ad6c, fd1e8c4), reverted there because that
file is one of the shared execution-path files, and moved here unchanged in meaning (W4
2026-11-18); the builder-format and arm-identity checks are new.

Per (target, seed) group the gate checks:
* vocabulary: every arm the plan declares for that target is present exactly once and all have
  the same nonempty token pool (``vocabulary_pool_final``, reconstructed by the launcher from each
  cell's recorded name segments);
* ``mutation_policy`` id, builder format id (``archive_format``) and arm identity (recorded
  ``search_policy``), each three-valued -- ``equal`` / ``different`` / ``unverifiable``:
  - ids: every recording cell records exactly one id and all the same; fewer than two recording
    cells is unverifiable, never a pass;
  - arm identity: each recording cell records exactly one search policy and the arms of the group
    record pairwise different ones (``equal`` here means "arms distinguished as declared").
* seed corpus (W4 2026-11-18: the corpus is a property of the v2 policy id, and a gate, not only
  a record): each cell's recorded initial case ids must equal the case ids fixed by the corpus
  its recorded policy binds (``mutator.policy.SEED_CORPUS`` -> ``generator.seed_corpus``; the
  ids are imported from there, never copied), and the arms of a group must have recorded the
  same ids. A cell that records other ids is ``different`` and fails (listed per cell in
  ``seed_corpus_cells``); a cell with no recorded ids, no single recorded policy, or a policy
  that binds no corpus is ``unverifiable``.
``different`` fails the group; ``unverifiable`` does not, but is counted and listed for review
(``review_required``): a gate must not read "no recorded ids" as "same ids". Across the run, each
arm label must map to exactly one recorded search policy (``arm_policy_map``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from inodefence.evaluation.rds_report import load_cell_files
from inodefence.generator import seed_corpus
from inodefence.mutator.policy import SEED_CORPUS, MutationPolicy

EQUAL = "equal"
DIFFERENT = "different"
UNVERIFIABLE = "unverifiable"
CHECKS = ("mutation_policy", "archive_format", "arm_identity", "seed_corpus")
SINGLE_TARGET = "__single__"


def recorded_ids(
    report: Mapping[str, Any] | None, records: Sequence[Mapping[str, Any]], field: str
) -> list[str]:
    """Distinct ids a cell's own files record for ``field``, sorted.

    ``mutation_policy``: the report's ``config.mutation_policy`` and every mutation step's
    ``mutation_attempt.mutation_policy``. ``archive_format``: every step record's
    ``archive_format`` (build-invalid records carry ``None`` and give no evidence).
    ``search_policy``: the report's ``config.search_policy`` (step records do not carry it).
    """
    found: set[str] = set()
    config = report.get("config") if report is not None else None
    if field in ("mutation_policy", "search_policy") and isinstance(config, Mapping):
        if config.get(field) is not None:
            found.add(str(config[field]))
    for record in records:
        if field == "mutation_policy":
            attempt = record.get("mutation_attempt")
            if isinstance(attempt, Mapping) and attempt.get("mutation_policy") is not None:
                found.add(str(attempt["mutation_policy"]))
        elif field == "archive_format" and record.get("archive_format") is not None:
            found.add(str(record["archive_format"]))
    return sorted(found)


def recorded_initial_case_ids(
    report: Mapping[str, Any] | None, records: Sequence[Mapping[str, Any]]
) -> list[str] | None:
    """The cell's recorded initial case ids, in order, or ``None`` when nothing records them.

    The report's ``initial_case_ids`` when there is a report; otherwise (a streamed or aborted
    cell) the ``case_id`` of the seed steps, in step order. If both exist and disagree, the
    report's list is returned here and :func:`seed_steps_agree` reports the contradiction
    (the cell then fails the seed corpus check).
    """
    if report is not None and isinstance(report.get("initial_case_ids"), list):
        return [str(item) for item in report["initial_case_ids"]]
    seeds = [str(r["case_id"]) for r in records if r.get("origin") == "seed" and "case_id" in r]
    return seeds or None


def seed_steps_agree(
    report: Mapping[str, Any] | None, records: Sequence[Mapping[str, Any]]
) -> bool:
    """False if the report's initial ids and the recorded seed steps name different cases."""
    seeds = [str(r["case_id"]) for r in records if r.get("origin") == "seed" and "case_id" in r]
    if report is None or not isinstance(report.get("initial_case_ids"), list) or not seeds:
        return True
    return seeds == [str(item) for item in report["initial_case_ids"]]


def bound_corpus_case_ids(policy: str) -> tuple[str, ...] | None:
    """Case ids fixed by the corpus ``policy`` binds; ``None`` if it binds none (or is unknown)."""
    try:
        corpus = SEED_CORPUS.get(MutationPolicy(policy))
    except ValueError:
        return None
    if corpus is None:
        return None
    return tuple(case.case_id for case in seed_corpus(corpus))


def seed_corpus_cell_check(cell: Mapping[str, Any]) -> str:
    """One cell: its recorded initial ids against its recorded policy's bound corpus."""
    recorded = cell.get("initial_case_ids")
    if cell.get("seed_steps_agree") is False:
        return DIFFERENT
    if recorded is None:
        return UNVERIFIABLE
    policies = cell.get("mutation_policies") or ()
    if len(policies) != 1:
        return UNVERIFIABLE
    expected = bound_corpus_case_ids(str(policies[0]))
    if expected is None:
        return UNVERIFIABLE
    return EQUAL if tuple(str(item) for item in recorded) == expected else DIFFERENT


def _seed_corpus_group_check(cells: Sequence[Mapping[str, Any]], per_cell: Sequence[str]) -> str:
    if DIFFERENT in per_cell:
        return DIFFERENT
    recorded = {
        tuple(cell["initial_case_ids"])
        for cell in cells
        if cell.get("initial_case_ids") is not None
    }
    if len(recorded) > 1:
        return DIFFERENT
    return EQUAL if per_cell and all(value == EQUAL for value in per_cell) else UNVERIFIABLE


def _same_id_check(recorded: Sequence[tuple[str, ...] | None]) -> str:
    evidence = [item for item in recorded if item]
    if any(len(item) != 1 for item in evidence):
        return DIFFERENT
    if len(evidence) < 2:
        return UNVERIFIABLE
    return EQUAL if len(set(evidence)) == 1 else DIFFERENT


def _arm_identity_check(recorded: Sequence[tuple[str, ...] | None]) -> str:
    evidence = [item for item in recorded if item]
    if any(len(item) != 1 for item in evidence):
        return DIFFERENT
    if len(evidence) < 2 or len(evidence) < len(recorded):
        return UNVERIFIABLE
    return EQUAL if len(set(evidence)) == len(evidence) else DIFFERENT


def g1_v2_equality(
    cells: Sequence[Mapping[str, Any]],
    *,
    expected_arms_by_target: Mapping[str, frozenset[str]],
) -> dict[str, Any]:
    """The per-group result over cell entries (see the module docstring)."""
    pools_by_group: dict[str, dict[int, dict[str, frozenset[str]]]] = {}
    recorded: dict[str, dict[tuple[str, int], list[tuple[str, ...] | None]]] = {
        check: {} for check in CHECKS
    }
    duplicate_groups: set[tuple[str, int]] = set()
    arm_policies: dict[str, set[str]] = {}
    group_cells: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    for cell in cells:
        target = str(cell.get("target_id", SINGLE_TARGET))
        seed = int(cell["seed"])
        arm = str(cell["arm"])
        pools = pools_by_group.setdefault(target, {}).setdefault(seed, {})
        if arm in pools:
            duplicate_groups.add((target, seed))
        pools[arm] = frozenset(cell.get("vocabulary_pool_final", ()))
        group_cells.setdefault((target, seed), []).append(cell)
        for check, key in (
            ("mutation_policy", "mutation_policies"),
            ("archive_format", "archive_formats"),
            ("arm_identity", "search_policies"),
        ):
            value = cell.get(key)
            recorded[check].setdefault((target, seed), []).append(
                None if value is None else tuple(str(item) for item in value)
            )
        arm_policies.setdefault(arm, set()).update(
            str(p) for p in cell.get("search_policies") or ()
        )
    multiple_targets = len(pools_by_group) > 1
    groups: dict[str, dict[str, Any]] = {}
    seed_corpus_cells: dict[str, str] = {}
    for target, by_seed in sorted(pools_by_group.items()):
        expected = expected_arms_by_target.get(target)
        for seed, pools in sorted(by_seed.items()):
            arms = sorted(pools)
            distinct = set(pools.values())
            checks = {
                "mutation_policy": _same_id_check(recorded["mutation_policy"][(target, seed)]),
                "archive_format": _same_id_check(recorded["archive_format"][(target, seed)]),
                "arm_identity": _arm_identity_check(recorded["arm_identity"][(target, seed)]),
            }
            members = group_cells[(target, seed)]
            per_cell = [seed_corpus_cell_check(cell) for cell in members]
            for cell, value in zip(members, per_cell, strict=True):
                seed_corpus_cells[str(cell.get("run_id", f"{target}/{seed}/{cell['arm']}"))] = value
            checks["seed_corpus"] = _seed_corpus_group_check(members, per_cell)
            vocabulary_equal = (
                expected is not None
                and set(arms) == set(expected)
                and len(arms) >= 2
                and len(distinct) == 1
                and bool(next(iter(distinct)))
                and (target, seed) not in duplicate_groups
            )
            key = f"{target}/{seed}" if multiple_targets else str(seed)
            groups[key] = {
                "equal": vocabulary_equal and DIFFERENT not in checks.values(),
                "vocabulary_equal": vocabulary_equal,
                "arms": arms,
                "pool_sizes": {arm: len(pools[arm]) for arm in arms},
                **{f"{name}_check": value for name, value in checks.items()},
            }
    labels = sorted(arm_policies)
    policy_owner: dict[str, list[str]] = {}
    for label in labels:
        for policy in arm_policies[label]:
            policy_owner.setdefault(policy, []).append(label)
    # A label with no recorded search policy is unverifiable (listed), not inconsistent: only
    # two policies for one label, or one policy for two labels, is a contradiction.
    arm_policy_map = {
        "by_arm": {label: sorted(arm_policies[label]) for label in labels},
        "unrecorded_arms": [label for label in labels if not arm_policies[label]],
        "consistent": all(len(arm_policies[label]) <= 1 for label in labels)
        and all(len(owners) == 1 for owners in policy_owner.values()),
    }
    return {
        "equal": bool(groups)
        and all(item["equal"] for item in groups.values())
        and arm_policy_map["consistent"],
        "groups": groups,
        "summaries": {check: check_summary(groups, check) for check in CHECKS},
        "arm_policy_map": arm_policy_map,
        "seed_corpus_cells": seed_corpus_cells,
    }


def check_summary(groups: Mapping[str, Mapping[str, Any]], check: str) -> dict[str, Any]:
    """Counts of the three values for one check, the unverifiable groups and review_required."""
    field = f"{check}_check"
    counts = {
        value: sum(1 for item in groups.values() if item[field] == value)
        for value in (EQUAL, DIFFERENT, UNVERIFIABLE)
    }
    unverifiable = sorted(key for key, item in groups.items() if item[field] == UNVERIFIABLE)
    return {
        "counts": counts,
        "unverifiable_groups": unverifiable,
        "review_required": bool(unverifiable),
    }


def _cell_files(output: Path, run_id: str) -> tuple[Path, Path]:
    """The cell's report and steps JSONL, found by run id (no launcher path rule imported)."""
    reports = sorted(
        p for p in output.rglob(f"inodefence-effect-demo-*-{run_id}.json") if p.is_file()
    )
    if len(reports) > 1:
        raise ValueError(f"run id {run_id!r} matches more than one report: {reports}")
    if reports:
        report = reports[0]
        return report, report.with_name(report.name[: -len(".json")] + ".steps.jsonl")
    # No report (aborted or still streaming): the steps JSONL alone, found the same way.
    streams = sorted(
        p for p in output.rglob(f"inodefence-effect-demo-*-{run_id}.steps.jsonl") if p.is_file()
    )
    if len(streams) > 1:
        raise ValueError(f"run id {run_id!r} matches more than one steps file: {streams}")
    if streams:
        steps = streams[0]
        return steps.with_name(steps.name[: -len(".steps.jsonl")] + ".json"), steps
    return output / f"__missing__-{run_id}.json", output / f"__missing__-{run_id}.steps.jsonl"


def load_g1_cells(output: Path) -> tuple[list[dict[str, Any]], dict[str, frozenset[str]]]:
    """Cell entries from the launcher's ``summaries/index.json`` plus the recorded ids.

    The index lists every planned cell (complete, aborted or invalid), so the declared arms per
    target come from it, not from whichever cells produced usable files.
    """
    index = json.loads((output / "summaries" / "index.json").read_text(encoding="utf-8"))
    cells: list[dict[str, Any]] = []
    expected: dict[str, set[str]] = {}
    for entry in index["cells"]:
        target = str(entry.get("target_id", SINGLE_TARGET))
        expected.setdefault(target, set()).add(str(entry["arm"]))
        cell = {
            "run_id": entry["run_id"],
            "target_id": target,
            "seed": entry["seed"],
            "arm": entry["arm"],
            "vocabulary_pool_final": list(entry.get("vocabulary_pool_final", ())),
        }
        report_path, steps_path = _cell_files(output, str(entry["run_id"]))
        if report_path.is_file() or steps_path.is_file():
            loaded = load_cell_files(report_path, steps_path)
            cell["mutation_policies"] = recorded_ids(
                loaded.report, loaded.records, "mutation_policy"
            )
            cell["archive_formats"] = recorded_ids(loaded.report, loaded.records, "archive_format")
            cell["search_policies"] = recorded_ids(loaded.report, loaded.records, "search_policy")
            cell["initial_case_ids"] = recorded_initial_case_ids(loaded.report, loaded.records)
            cell["seed_steps_agree"] = seed_steps_agree(loaded.report, loaded.records)
        cells.append(cell)
    return cells, {target: frozenset(arms) for target, arms in expected.items()}


def check_output(output: Path) -> dict[str, Any]:
    """Run the gate over a launcher output folder; the document ``check_g1_v2`` writes."""
    cells, expected = load_g1_cells(output)
    result = g1_v2_equality(cells, expected_arms_by_target=expected)
    return {
        "schema_version": 1,
        "gate": "g1-v2",
        "pass": result["equal"],
        "review_required": any(s["review_required"] for s in result["summaries"].values())
        or bool(result["arm_policy_map"]["unrecorded_arms"]),
        "cells": cells,
        **result,
    }
