"""Unit tests for the parallel native matrix planner (no Docker required)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.run_parallel_native import (
    TOKEN,
    Arm,
    Cell,
    build_cells,
    cell_env,
    github_matrix,
    main,
    parse_arm,
)

from inodefence.feedback import EffectSearchPolicy
from inodefence.mutator import MutationPolicy

ESCAPE = MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK


def test_parse_arm_default() -> None:
    assert parse_arm("default") == Arm("default", None, None)


def test_parse_arm_named_resolves_names_to_values() -> None:
    arm = parse_arm("p2-esc=P2_EFFECT_ADAPTIVE/M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK")
    assert arm == Arm("p2-esc", EffectSearchPolicy.P2_EFFECT_ADAPTIVE.value, ESCAPE.value)


def test_parse_arm_accepts_policy_values_too() -> None:
    arm = parse_arm(f"a={EffectSearchPolicy.P1_EFFECT_RETENTION.value}/{MutationPolicy.M1.value}")
    assert arm.search == EffectSearchPolicy.P1_EFFECT_RETENTION.value
    assert arm.mutation == MutationPolicy.M1.value


def test_parse_arm_dash_keeps_side_default() -> None:
    arm = parse_arm("only-search=P0_FINAL_STATE/-")
    assert arm.search == EffectSearchPolicy.P0_FINAL_STATE.value
    assert arm.mutation is None


@pytest.mark.parametrize("spec", ["x=NOPE/M1", "x=P2_EFFECT_ADAPTIVE/NOPE"])
def test_parse_arm_rejects_unknown_policy(spec: str) -> None:
    with pytest.raises(ValueError, match="unknown"):
        parse_arm(spec)


@pytest.mark.parametrize("spec", ["bad label=P2_EFFECT_ADAPTIVE/M1", "-lead=P2_EFFECT_ADAPTIVE/M1"])
def test_parse_arm_rejects_bad_label(spec: str) -> None:
    with pytest.raises(ValueError, match="label"):
        parse_arm(spec)


def test_parse_arm_requires_slash() -> None:
    with pytest.raises(ValueError, match="LABEL=SEARCH/MUTATION"):
        parse_arm("label=P2_EFFECT_ADAPTIVE")


def test_build_cells_cartesian_product_and_valid_ids() -> None:
    arms = [Arm("default", None, None), Arm("esc", None, ESCAPE.value)]
    cells = build_cells("demo-historical", ["7.5.2", "7.5.3"], arms, [123, 456], 100)
    assert len(cells) == 8
    run_ids = [c.run_id for c in cells]
    assert len(set(run_ids)) == 8
    assert all(TOKEN.fullmatch(rid) for rid in run_ids)
    assert "7.5.2-default-s123" in run_ids
    assert "7.5.3-esc-s456" in run_ids


def test_build_cells_duplicate_arm_labels_raise() -> None:
    arms = [Arm("dup", None, None), Arm("dup", None, ESCAPE.value)]
    with pytest.raises(ValueError, match="duplicate run ids"):
        build_cells("demo", [None], arms, [123], 20)


def test_cell_run_id_and_evidence_basename() -> None:
    demo = Cell("demo", None, Arm("default", None, None), 123, 20)
    assert demo.run_id == "native-default-s123"
    assert demo.evidence_basename == "inodefence-effect-demo-native-native-default-s123"
    hist = Cell("demo-historical", "7.5.2", Arm("esc", None, ESCAPE.value), 789, 100)
    assert hist.run_id == "7.5.2-esc-s789"
    assert hist.evidence_basename == "inodefence-effect-demo-historical-7.5.2-esc-s789"


def test_cell_env_default_arm_demo(tmp_path: Path) -> None:
    cell = Cell("demo", None, Arm("default", None, None), 123, 20)
    env = cell_env(cell, tmp_path, {})
    assert env["RUN_ID"] == "native-default-s123"
    assert env["SKIP_BUILD"] == "1"
    assert env["DEMO_SEED"] == "123"
    assert env["DEMO_BUDGET"] == "20"
    assert env["INODEFENCE_EVIDENCE_DIR"] == str(tmp_path)
    assert "DEMO_POLICY" not in env
    assert "DEMO_MUTATION_POLICY" not in env
    assert "TAR_VERSION" not in env


def test_cell_env_named_arm_historical(tmp_path: Path) -> None:
    arm = Arm("p2-esc", EffectSearchPolicy.P2_EFFECT_ADAPTIVE.value, ESCAPE.value)
    cell = Cell("demo-historical", "7.5.2", arm, 456, 100)
    env = cell_env(cell, tmp_path, {})
    assert env["TAR_VERSION"] == "7.5.2"
    assert env["DEMO_POLICY"] == EffectSearchPolicy.P2_EFFECT_ADAPTIVE.value
    assert env["DEMO_MUTATION_POLICY"] == ESCAPE.value


def test_cell_env_overrides_inherited_values(tmp_path: Path) -> None:
    cell = Cell("demo", None, Arm("default", None, None), 123, 20)
    base = {
        "BUILD_ONLY": "1",
        "TAR_VERSION": "9.9.9",
        "DEMO_POLICY": "stale",
        "DEMO_MUTATION_POLICY": "stale",
        "PATH": "/usr/bin",
    }
    env = cell_env(cell, tmp_path, base)
    assert "BUILD_ONLY" not in env
    assert "TAR_VERSION" not in env
    assert "DEMO_POLICY" not in env
    assert "DEMO_MUTATION_POLICY" not in env
    assert env["PATH"] == "/usr/bin"  # unrelated inherited values survive


def test_main_dry_run_lists_cells(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(
        [
            "--mode",
            "demo-historical",
            "--versions",
            "7.5.2,7.5.3",
            "--seeds",
            "123,456",
            "--arm",
            "default",
            "--budget",
            "100",
            "--output",
            str(tmp_path / "out"),
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "cells=4" in out
    assert "7.5.2-default-s123" in out
    assert "7.5.3-default-s456" in out
    assert not (tmp_path / "out").exists()  # dry run touches no Docker and no output dir


def test_main_demo_rejects_versions(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "demo", "--versions", "7.5.2", "--output", str(tmp_path), "--dry-run"])


def test_main_historical_requires_versions(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "demo-historical", "--output", str(tmp_path), "--dry-run"])


def test_github_matrix_demo_default_arm() -> None:
    cells = build_cells("demo", [None], [Arm("default", None, None)], [123, 456], 20)
    matrix = github_matrix(cells)
    assert set(matrix) == {"include"}
    assert len(matrix["include"]) == 2
    first = matrix["include"][0]
    assert first["run_id"] == "native-default-s123"
    assert first["mode"] == "demo"
    assert first["version"] == ""  # demo runs the pinned repository node-tar, no version
    assert first["seed"] == "123" and first["budget"] == "20"  # strings for the workflow env
    assert first["search"] == "" and first["mutation"] == ""  # empty => keep script default
    assert first["evidence_basename"] == "inodefence-effect-demo-native-native-default-s123"


def test_github_matrix_historical_named_arm_carries_policy_values() -> None:
    arm = parse_arm("p2=P2_EFFECT_ADAPTIVE/M1")
    cells = build_cells("demo-historical", ["7.5.2"], [arm], [123], 100)
    entry = github_matrix(cells)["include"][0]
    assert entry["version"] == "7.5.2"
    assert entry["run_id"] == "7.5.2-p2-s123"
    assert entry["search"] == EffectSearchPolicy.P2_EFFECT_ADAPTIVE.value
    assert entry["mutation"] == MutationPolicy.M1.value
    assert entry["evidence_basename"] == "inodefence-effect-demo-historical-7.5.2-p2-s123"


def test_main_emit_github_matrix_prints_json_and_skips_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--mode", "demo", "--seeds", "123,456", "--arm", "default", "--emit-github-matrix"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [entry["run_id"] for entry in payload["include"]] == [
        "native-default-s123",
        "native-default-s456",
    ]


def test_main_requires_output_without_emit_or_dry_run() -> None:
    with pytest.raises(SystemExit):  # no --output, no --dry-run, no --emit-github-matrix
        main(["--mode", "demo", "--seeds", "123"])
