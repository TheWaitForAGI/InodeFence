"""Preregistration gate: block parsing and refusal on any mismatch."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from inodefence.evaluation.rds import RdsArm, RVariant, VocabularyMode
from inodefence.evaluation.rds_preregistration import (
    CellRequest,
    PreregistrationFormatError,
    PreregistrationMismatch,
    load_preregistration,
    parse_preregistration,
    preregistration_mismatches,
    require_preregistered_cell,
)
from inodefence.feedback import EffectSearchPolicy

SHA = "0123456789abcdef0123456789abcdef01234567"
DIGEST = "sha256:" + "ab" * 32
BLOCK = f"""# EXP-0 v2.1 (test fixture)

prose above the block is ignored.

```preregistration
engine_sha = {SHA}
image_digest = {DIGEST}
seeds = 9001, 9002, 9003
budget = 200
vocabulary = observed-names
arm.R = unretained-walk-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
# optional ablation and sentinel generator binding
arm.S-a = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = 9001
sentinel_count = 3
```

prose below is ignored too.
"""
SENTINEL_SET = {"generator_id": "sentinel-names/seed-random-v1", "generator_seed": 9001, "count": 3}


def _request(
    arm: RdsArm = RdsArm.S_U,
    random_seed: int = 9002,
    execution_budget: int = 200,
    engine_sha: str | None = SHA,
    engine_dirty: bool | None = False,
    image_digest: str | None = DIGEST,
    sentinel_set: Mapping[str, object] | None = SENTINEL_SET,
) -> CellRequest:
    return CellRequest(
        arm, random_seed, execution_budget, engine_sha, engine_dirty, image_digest, sentinel_set
    )


def test_parse_reads_only_the_fenced_block() -> None:
    prereg = parse_preregistration(BLOCK)
    assert prereg.engine_sha == SHA and prereg.image_digest == DIGEST
    assert prereg.seeds == (9001, 9002, 9003) and prereg.budget == 200
    assert prereg.vocabulary_mode == VocabularyMode.OBSERVED_NAMES
    assert prereg.arm_policies[RdsArm.S_A] == EffectSearchPolicy.P3_BOUNDARY_ATTEMPT_GRADIENT
    assert prereg.r_variant == RVariant.WALK
    assert (prereg.sentinel_generator_seed, prereg.sentinel_count) == (9001, 3)
    assert "prose" not in " ".join(prereg.raw)


def test_matching_request_yields_cell_config_from_the_file() -> None:
    prereg = parse_preregistration(BLOCK)
    assert preregistration_mismatches(prereg, _request()) == ()
    config = require_preregistered_cell(prereg, _request())
    assert config.arm == RdsArm.S_U and config.random_seed == 9002
    assert config.execution_budget == 200
    assert config.vocabulary_mode == VocabularyMode.OBSERVED_NAMES
    assert config.search_policy == EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM


def test_r_variant_follows_the_declared_r_policy() -> None:
    text = BLOCK.replace(
        "arm.R = unretained-walk-v1-uniform-mutation-v1",
        "arm.R = unretained-seed-restart-v1-uniform-mutation-v1",
    )
    prereg = parse_preregistration(text)
    assert prereg.r_variant == RVariant.SEED_RESTART
    config = require_preregistered_cell(prereg, _request(arm=RdsArm.R))
    assert config.search_policy == EffectSearchPolicy.R_UNRETAINED_SEED_RESTART


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    (
        ({"engine_sha": "f" * 40}, "engine SHA"),
        ({"engine_sha": None}, "unavailable"),
        ({"engine_dirty": True}, "dirty"),
        ({"engine_dirty": None}, "dirty state unknown"),
        ({"image_digest": "sha256:" + "cd" * 32}, "image digest"),
        ({"image_digest": None}, "not supplied"),
        ({"random_seed": 9009}, "seed 9009"),
        ({"execution_budget": 50}, "budget 50"),
        ({"sentinel_set": None}, "sentinel set declared"),
        ({"sentinel_set": {**SENTINEL_SET, "generator_seed": 1}}, "sentinel_set.generator_seed"),
        ({"sentinel_set": {**SENTINEL_SET, "count": 1}}, "sentinel_set.count"),
    ),
)
def test_each_mismatch_refuses_the_run(overrides: dict[str, Any], fragment: str) -> None:
    prereg = parse_preregistration(BLOCK)
    mismatches = preregistration_mismatches(prereg, _request(**overrides))
    assert any(fragment in item for item in mismatches), mismatches
    with pytest.raises(PreregistrationMismatch) as info:
        require_preregistered_cell(prereg, _request(**overrides))
    assert info.value.mismatches == mismatches


def test_undeclared_arm_is_refused() -> None:
    text = "\n".join(line for line in BLOCK.splitlines() if not line.startswith("arm.S-a"))
    prereg = parse_preregistration(text)
    assert RdsArm.S_A not in prereg.arm_policies
    mismatches = preregistration_mismatches(prereg, _request(arm=RdsArm.S_A))
    assert any("not preregistered" in item for item in mismatches)


def test_sentinel_binding_is_optional_when_undeclared() -> None:
    text = "\n".join(line for line in BLOCK.splitlines() if not line.startswith("sentinel_"))
    prereg = parse_preregistration(text)
    assert preregistration_mismatches(prereg, _request(sentinel_set=None)) == ()


@pytest.mark.parametrize(
    ("edit", "fragment"),
    (
        (("```preregistration", "```other"), "no ```preregistration block"),
        (("```\n\nprose below is ignored too.\n", ""), "not closed"),
        (("budget = 200", "budget = many"), "integer"),
        (("engine_sha = " + SHA, "engine_sha = abc"), "40-hex"),
        (("seeds = 9001, 9002, 9003", "seeds = 9001, 9001"), "unique"),
        (("vocabulary = observed-names", "vocabulary = magic"), "unknown vocabulary"),
        (("arm.D = structure-coverage", "arm.D = unretained-walk"), "realizes R"),
        (("arm.D = structure-coverage-v1-uniform-mutation-v1", "arm.D = nope"), "unknown arm"),
        (
            (
                "arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1"
                "-uniform-mutation-v1\n",
                "",
            ),
            "not declared",
        ),
        (("sentinel_count = 3", "sentinel_count = 3\nsentinel_count = 4"), "duplicate"),
    ),
)
def test_malformed_blocks_fail_closed(edit: tuple[str, str], fragment: str) -> None:
    text = BLOCK.replace(*edit)
    assert text != BLOCK
    with pytest.raises(PreregistrationFormatError, match=fragment):
        parse_preregistration(text)


def test_load_from_file_and_cli_refuses_mismatch_without_running(tmp_path: Path, capsys) -> None:
    from scripts.run_rds_cell import main

    path = tmp_path / "exp0-pilot-v2.1.md"
    path.write_text(BLOCK, encoding="utf-8")
    assert load_preregistration(path).budget == 200
    # The fixture SHA is not this checkout's HEAD, so the gate must refuse.
    code = main(
        [
            "--arm",
            "S-u",
            "--seed",
            "9002",
            "--budget",
            "200",
            "--preregistration",
            str(path),
            "--image-digest",
            DIGEST,
        ]
    )
    captured = capsys.readouterr()
    assert code == 2 and captured.out == "" and "refusing to run" in captured.err
    assert "engine SHA" in captured.err or "dirty" in captured.err


def test_cli_unregistered_smoke_run_is_labelled(tmp_path: Path) -> None:
    import json

    from scripts.run_rds_cell import main

    out = tmp_path / "cell.json"
    assert main(["--arm", "R", "--seed", "1", "--budget", "6", "--out", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["preregistration"] is None
    assert any("unregistered" in label for label in report["label"])
    assert any("synthetic" in label for label in report["label"])
    assert report["summary"]["t_first"] == 6 and report["summary"]["t_first_censored"] is True
