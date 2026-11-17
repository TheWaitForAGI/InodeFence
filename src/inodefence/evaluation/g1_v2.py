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

EQUAL = "equal"
DIFFERENT = "different"
UNVERIFIABLE = "unverifiable"
CHECKS = ("mutation_policy", "archive_format", "arm_identity")
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
    for cell in cells:
        target = str(cell.get("target_id", SINGLE_TARGET))
        seed = int(cell["seed"])
        arm = str(cell["arm"])
        pools = pools_by_group.setdefault(target, {}).setdefault(seed, {})
        if arm in pools:
            duplicate_groups.add((target, seed))
        pools[arm] = frozenset(cell.get("vocabulary_pool_final", ()))
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
    report = reports[0] if reports else output / f"__missing__-{run_id}.json"
    steps = report.with_name(report.name[: -len(".json")] + ".steps.jsonl")
    return report, steps


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
