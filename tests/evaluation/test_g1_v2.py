"""G1 v2 gate (``inodefence.evaluation.g1_v2``, ``scripts/check_g1_v2.py``), v2 U3/C11.

The first four tests are the reverted run_g1_smoke tests (49ae01a, 1f3ad6c, fd1e8c4) moved to
the new module with their assertions kept; ``per_seed`` is now ``groups`` and the declared arms
are always given (the v2 gate has no legacy call without a plan, so the old
"legacy single-target shape" test has no counterpart here).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.check_g1_v2 import main as check_main

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_demo import effect_campaign_report, render_effect_step_line
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.g1_v2 import (
    SINGLE_TARGET,
    check_output,
    g1_v2_equality,
    recorded_ids,
)
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.mutator import MutationPolicy

THREE = frozenset({"R", "D", "S-u"})


def test_groups_the_same_seed_by_target() -> None:
    cells = [
        {"target_id": target, "seed": 42, "arm": arm, "vocabulary_pool_final": [pool]}
        for target, pool in (("target-a", "a"), ("target-b", "b"))
        for arm in ("R", "S-u")
    ]
    expected = {"target-a": frozenset({"R", "S-u"}), "target-b": frozenset({"R", "S-u"})}
    result = g1_v2_equality(cells, expected_arms_by_target=expected)
    assert result["equal"] is True
    assert set(result["groups"]) == {"target-a/42", "target-b/42"}
    assert result["groups"]["target-a/42"]["pool_sizes"] == {"R": 1, "S-u": 1}


def test_another_target_with_the_same_seed_cannot_mask_an_unequal_pool() -> None:
    # #524: grouping by seed alone let target-b's cells overwrite target-a's, so
    # target-a's differing D pool was never compared and the check passed.
    cells = [
        {"target_id": "a", "seed": 42, "arm": "R", "vocabulary_pool_final": ["x"]},
        {"target_id": "a", "seed": 42, "arm": "D", "vocabulary_pool_final": ["other"]},
        {"target_id": "a", "seed": 42, "arm": "S-u", "vocabulary_pool_final": ["x"]},
        *(
            {"target_id": "b", "seed": 42, "arm": arm, "vocabulary_pool_final": ["y"]}
            for arm in ("R", "D", "S-u")
        ),
    ]
    expected = {target: THREE for target in ("a", "b")}
    result = g1_v2_equality(cells, expected_arms_by_target=expected)
    assert result["equal"] is False
    assert result["groups"]["a/42"]["equal"] is False
    assert result["groups"]["b/42"]["equal"] is True


def test_requires_every_declared_arm_and_nonempty_pools() -> None:
    cells = [
        {"target_id": "one", "seed": 1, "arm": "R", "vocabulary_pool_final": ["a"]},
        {"target_id": "one", "seed": 1, "arm": "S-u", "vocabulary_pool_final": ["a"]},
    ]
    expected = {"one": frozenset({"R", "S-u"})}
    assert g1_v2_equality(cells, expected_arms_by_target=expected)["equal"] is True
    assert g1_v2_equality(cells[:1], expected_arms_by_target=expected)["equal"] is False
    assert g1_v2_equality(cells, expected_arms_by_target={"one": THREE})["equal"] is False
    duplicate = [*cells, dict(cells[1])]
    assert g1_v2_equality(duplicate, expected_arms_by_target=expected)["equal"] is False
    empty = [dict(cell, vocabulary_pool_final=[]) for cell in cells]
    assert g1_v2_equality(empty, expected_arms_by_target=expected)["equal"] is False


def _cells(key: str, *values: list[str] | None, arms=("R", "D", "S-u")) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for arm, recorded in zip(arms, values, strict=True):
        cell: dict[str, Any] = {"seed": 1, "arm": arm, "vocabulary_pool_final": ["a"]}
        if recorded is not None:
            cell[key] = recorded
        out.append(cell)
    return out


def _check(cells: list[dict[str, Any]], name: str) -> tuple[bool, str, dict[str, Any]]:
    result = g1_v2_equality(cells, expected_arms_by_target={SINGLE_TARGET: THREE})
    return result["equal"], result["groups"]["1"][f"{name}_check"], result["summaries"][name]


def test_mutation_policy_check_is_three_valued() -> None:
    for same in (
        _cells("mutation_policies", ["m"], ["m"], ["m"]),
        _cells("mutation_policies", ["m"], None, ["m"]),
        _cells("mutation_policies", ["m"], [], ["m"]),
    ):
        equal, check, _ = _check(same, "mutation_policy")
        assert equal and check == "equal"
    # Zero or one recording cell: not a pass of the check, and not a vocabulary failure.
    for unverifiable in (
        _cells("mutation_policies", None, None, None),
        _cells("mutation_policies", ["m"], None, []),
        _cells("mutation_policies", [], [], []),
    ):
        equal, check, summary = _check(unverifiable, "mutation_policy")
        assert equal and check == "unverifiable"
        assert summary["review_required"] is True and summary["unverifiable_groups"] == ["1"]
    for bad in (
        _cells("mutation_policies", ["m"], ["m"], ["n"]),
        _cells("mutation_policies", ["m"], ["m", "n"], ["m"]),
        _cells("mutation_policies", ["m", "n"], None, None),
    ):
        equal, check, _ = _check(bad, "mutation_policy")
        assert equal is False and check == "different"


def test_builder_format_check_is_three_valued() -> None:
    equal, check, _ = _check(
        _cells("archive_formats", ["ustar-utf8-v1"], ["ustar-utf8-v1"], ["ustar-utf8-v1"]),
        "archive_format",
    )
    assert equal and check == "equal"
    equal, check, summary = _check(
        _cells("archive_formats", ["ustar-utf8-v1"], None, None), "archive_format"
    )
    assert equal and check == "unverifiable" and summary["review_required"]
    equal, check, _ = _check(
        _cells("archive_formats", ["ustar-utf8-v1"], ["pax-utf8-v1"], ["ustar-utf8-v1"]),
        "archive_format",
    )
    assert equal is False and check == "different"


def test_arm_identity_uses_the_recorded_search_policy() -> None:
    chain = "unretained-seed-chain-m4-v1-uniform-mutation-v1"
    d, su = (
        "structure-coverage-v1-uniform-mutation-v1",
        "effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1",
    )
    equal, check, _ = _check(_cells("search_policies", [chain], [d], [su]), "arm_identity")
    assert equal and check == "equal"
    # Two arms recording the same search policy are not distinguished: the gate fails.
    equal, check, _ = _check(_cells("search_policies", [d], [d], [su]), "arm_identity")
    assert equal is False and check == "different"
    # An arm without a recorded search policy cannot be identified: review, not pass.
    equal, check, summary = _check(_cells("search_policies", [chain], None, [su]), "arm_identity")
    assert equal and check == "unverifiable" and summary["review_required"]


def test_each_arm_label_maps_to_one_search_policy_across_the_run() -> None:
    chain, d = (
        "unretained-seed-chain-m4-v1-uniform-mutation-v1",
        "structure-coverage-v1-uniform-mutation-v1",
    )
    cells = [
        {"seed": seed, "arm": arm, "vocabulary_pool_final": ["a"], "search_policies": [policy]}
        for seed, arm, policy in ((1, "R", chain), (1, "D", d), (2, "R", d), (2, "D", chain))
    ]
    result = g1_v2_equality(cells, expected_arms_by_target={SINGLE_TARGET: frozenset({"R", "D"})})
    assert result["arm_policy_map"]["consistent"] is False and result["equal"] is False


def test_recorded_ids_read_config_and_steps() -> None:
    report = {"config": {"mutation_policy": "m", "search_policy": "s"}}
    records = [
        {"mutation_attempt": None, "archive_format": "ustar-utf8-v1"},
        {"mutation_attempt": {"mutation_policy": "m"}, "archive_format": None},
    ]
    assert recorded_ids(report, records, "mutation_policy") == ["m"]
    assert recorded_ids(report, records, "archive_format") == ["ustar-utf8-v1"]
    assert recorded_ids(report, records, "search_policy") == ["s"]
    assert recorded_ids(None, records, "search_policy") == []


ARM_POLICIES = {
    "R": EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M4,
    "D": EffectSearchPolicy.D_STRUCTURE_COVERAGE,
    "S-u": EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM,
}


def _write_output(
    root: Path, targets: dict[str, int], *, mutation_override: str | None = None
) -> None:
    """A launcher-like output folder: summaries/index.json and per-cell report + steps."""
    cells = []
    for target, seed in targets.items():
        for arm, policy in ARM_POLICIES.items():
            config = EffectCampaignConfig(
                seed, 12, policy, MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE
            )
            result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
            report: dict[str, Any] = effect_campaign_report(result, "synthetic")
            if mutation_override and arm == "D":
                for step in report["steps"]:
                    if step.get("mutation_attempt"):
                        step["mutation_attempt"]["mutation_policy"] = mutation_override
                report["config"]["mutation_policy"] = mutation_override
            run_id = f"{target}-{arm}-s{seed}"
            folder = root / target
            folder.mkdir(parents=True, exist_ok=True)
            base = folder / f"inodefence-effect-demo-historical-{run_id}"
            Path(f"{base}.json").write_text(json.dumps(report), encoding="utf-8")
            Path(f"{base}.steps.jsonl").write_text(
                "".join(render_effect_step_line(s) for s in report["steps"]), encoding="utf-8"
            )
            cells.append(
                {
                    "run_id": run_id,
                    "target_id": target,
                    "seed": seed,
                    "arm": arm,
                    "vocabulary_pool_final": ["a", "b"],
                }
            )
    (root / "summaries").mkdir(parents=True, exist_ok=True)
    (root / "summaries" / "index.json").write_text(json.dumps({"cells": cells}), encoding="utf-8")


def test_end_to_end_over_a_launcher_output_folder(tmp_path: Path) -> None:
    _write_output(tmp_path, {"t1": 5, "t2": 5})  # two targets, the same seed (#524 shape)
    document = check_output(tmp_path)
    assert document["pass"] is True and document["review_required"] is False
    assert set(document["groups"]) == {"t1/5", "t2/5"}
    for group in document["groups"].values():
        assert group["mutation_policy_check"] == "equal"
        assert group["archive_format_check"] == "equal"
        assert group["arm_identity_check"] == "equal"
    assert document["arm_policy_map"]["by_arm"]["R"] == [
        EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M4.value
    ]
    # The script writes summaries-v2/ and leaves the launcher's summaries/ untouched.
    before = (tmp_path / "summaries" / "index.json").read_bytes()
    assert check_main(["--output", str(tmp_path)]) == 0
    assert (tmp_path / "summaries-v2" / "g1-v2.json").is_file()
    assert (tmp_path / "summaries" / "index.json").read_bytes() == before
    assert sorted(p.name for p in (tmp_path / "summaries").iterdir()) == ["index.json"]


def test_end_to_end_detects_a_different_operator_table(tmp_path: Path) -> None:
    _write_output(tmp_path, {"t1": 5}, mutation_override="some-other-table-v1")
    document = check_output(tmp_path)
    assert document["pass"] is False
    assert document["groups"]["5"]["mutation_policy_check"] == "different"
    assert check_main(["--output", str(tmp_path)]) == 1
