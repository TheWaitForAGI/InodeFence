"""Registered R/D/S-u x FIXED_BASELINE campaigns reproduce the code at the run SHA (bed077a).

The registered experiment (EXP-3/EXP-2) ran every cell through ``run_rds_cell`` with the
``OBSERVED_NAMES`` vocabulary (``M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE``) and the
uniform operator scheduler; R is the seed-restart variant. The golden digests below were
minted from the code at ``GOLDEN_COMMIT`` with the synthetic producer (no Docker), so this
test proves that the current loop, scheduler and mutator still make the exact same decisions
and inputs for those configurations. ``tests/test_campaign_hooks_contract.py`` covers only
P2 + M1; this file covers the registered arms (v2 U1/C0).

Two digests per cell:
* ``trajectory``: the same rows as ``test_campaign_hooks_contract._trajectory_digest``
  (every feedback decision, ``weights_after``, retained corpus).
* ``inputs``: every mutation step's operator, applied flag, mutation policy,
  ``weights_before``/``selected_weight``/``reward``/``weights_after``, child case ID and
  the SHA-256 of the built TAR -- the fields a scheduler-table change could move.

Synthetic results are not native evidence. With them D's structure-coverage admission adds
nothing beyond the seeds, so D draws the same parents as R (equal ``inputs`` digests, different
``trajectory`` digests); the golden still pins each arm's own decision path.

Seeds 5, 777, 4242 are not registered (EXP-0 9001-9005, EXP-3 9006-9025, EXP-2 9026-9185,
8101-8110), not in the exploration ledger and not a HOST3 block (51600+).

How to regenerate (no Docker, no sealed evidence -- code only): in a detached worktree at
GOLDEN_COMMIT, run the two digest functions below over ``CELLS`` with the stdlib interpreter
and no site packages, so the shared editable install cannot shadow the tree:
    env -i PATH=/usr/bin:/bin PYTHONHASHSEED=0 PYTHONPATH=<wt>/src:<wt> \
        /usr/bin/python3 -S -B mint.py
Minted 2026-11-18 with PYTHONHASHSEED 0, 17 and 999 (identical), and the same values from
research/b-engine 4d16395 before the scheduler change (v2 U1/C1).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from inodefence.builder import build_tar
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.rds import (
    RdsArm,
    RdsCellConfig,
    RVariant,
    VocabularyMode,
    run_rds_cell,
)
from inodefence.generator.minimal import minimal_seed_corpus

GOLDEN_COMMIT = "bed077af62b1cdd5cc8dec96eb9cbe93ba542f1d"

ARMS = {
    "R": (RdsArm.R, RVariant.SEED_RESTART),
    "D": (RdsArm.D, RVariant.WALK),
    "S-u": (RdsArm.S_U, RVariant.WALK),
}
SEEDS = (5, 777, 4242)
BUDGETS = (16, 64)
CELLS = tuple(f"{arm}:{seed}:{budget}" for arm in ARMS for seed in SEEDS for budget in BUDGETS)

#: ``"<arm>:<seed>:<budget>" -> (trajectory digest, inputs digest)``, minted at GOLDEN_COMMIT.
GOLDEN: dict[str, tuple[str, str]] = {
    "D:4242:16": (
        "ac62602eec016a897ab6954ef4cc25b8df773c65928324b5b8b3cd81aeb8ce92",
        "b8d4b42dadaec38fd78efb4aa03a36748cd1592d06246a8f4c9bb74692e3ec7a",
    ),
    "D:4242:64": (
        "a6f6a0f8f1193fde9e9c68319bc770c7410648619309a2811b8d258161cf1854",
        "ba9b1ba2c6f419a8d5c5bb236e537aea0ad1d7e97af53d720c6b8d1e88957db1",
    ),
    "D:5:16": (
        "adbe48829478d5a1796a2d751b24a2dea144c4b5c083744db18ea42c4ed20a29",
        "07093a89f4ca03a7c6c5c5535faa13bb2e6575ad9e87c353a432bf9d6bf9bc45",
    ),
    "D:5:64": (
        "c19868de37596dc516c42812c3d9366f660d10858274650f42f1b5fa48deaf9f",
        "b1923df14d78d89621151323733b2a3865463b7600b8d7b6cf97ec276e222ecc",
    ),
    "D:777:16": (
        "371e19c93f5d71f30636947787fb3824cdf7308ccd37a78fe63e7d2ae09792cb",
        "4bbfc77912d6e8cfa3705f5b37def685098113a811e782ebba7d6e16f018176a",
    ),
    "D:777:64": (
        "40cc1d9272cac565d3195289487feb54efc8828ebd7329387eaeed3547fcd964",
        "5ed7db5a4a605984a3ca6e89de19dd3ec1e3901ffd285d5b75c3d97c449235c9",
    ),
    "R:4242:16": (
        "29ed66287261fe2c2562981dd3d8f7bf6595fbd1c237a99bc8ed0136d81d2af6",
        "b8d4b42dadaec38fd78efb4aa03a36748cd1592d06246a8f4c9bb74692e3ec7a",
    ),
    "R:4242:64": (
        "ce8f26896f691d01eac25deda8c6bee19c3e3d6993ec0a65cf2fb71f20a2c04b",
        "ba9b1ba2c6f419a8d5c5bb236e537aea0ad1d7e97af53d720c6b8d1e88957db1",
    ),
    "R:5:16": (
        "2632b072ffb8978e9a19d92aba008462377ca47c49bdadd64bb109241622c73e",
        "07093a89f4ca03a7c6c5c5535faa13bb2e6575ad9e87c353a432bf9d6bf9bc45",
    ),
    "R:5:64": (
        "0fae5cc4662997f87a3d6c00d5b43a57ade4bb85b2ab1037f9cfd7f5f7af8ac9",
        "b1923df14d78d89621151323733b2a3865463b7600b8d7b6cf97ec276e222ecc",
    ),
    "R:777:16": (
        "7879bad9f31e1c10722544caeb1afc22ae1da4567846f690ac7fb4eafb8c5b67",
        "4bbfc77912d6e8cfa3705f5b37def685098113a811e782ebba7d6e16f018176a",
    ),
    "R:777:64": (
        "19075a37148f5854597a6bd6c5a7a13c8c975cd145f914eff7037f0a7d1131ed",
        "5ed7db5a4a605984a3ca6e89de19dd3ec1e3901ffd285d5b75c3d97c449235c9",
    ),
    "S-u:4242:16": (
        "135021a350975c3a656c30ecf75e984c137e0d7840545191f26393ab9944138b",
        "271ca6a323caeaca8c9090a1ec65c8871393a7b9cc4c61790d6d5f2a732c370f",
    ),
    "S-u:4242:64": (
        "c73b5ecba8454397680f8a5aa9f6bc3043ddfd83f5798cf5b273fe0a25c0c866",
        "e5e3e31d046a16a920ec2ebd985c76e622620d1e64c8286ccb513002edcdab09",
    ),
    "S-u:5:16": (
        "cde3de319c92160c05cee430e0f031fdd19a0a6aa40c32df255967795d3cd7e8",
        "9744d5c219cc520d90c17b1975e3bc53c20f12a6a09a9c1c3c9b354379991f94",
    ),
    "S-u:5:64": (
        "b40160f29c4df626d35521eac2eaef8d4ce8a8e31b54949fcafef84603bc763b",
        "c940889d3f0f216921f6dfb4769d1cddd029aa776df77f7dda7974d4f73aa31c",
    ),
    "S-u:777:16": (
        "d271d6199681a74b56079549d0892d6ab284f64692cb377417d198c497ff2f1d",
        "b93390bd6460fe85628750e7f199346424f78418f87aa5265e3a3eb81c8d7d5e",
    ),
    "S-u:777:64": (
        "29ac8bc46db501010f6a211bf2f4f07e3105fd5e185be1445e6ed77b5a7c7678",
        "d15bff730c8c56faeb79889561aa45b0b68d641da82e68fec83ab65ac27debb0",
    ),
}


def _trajectory_digest(result: Any) -> str:
    """Same rows as tests/test_campaign_hooks_contract.py::_trajectory_digest."""
    sha = hashlib.sha256()
    for step in result.steps:
        fb = step.feedback
        weights = (
            ""
            if step.scheduler_evidence is None
            else ",".join(f"{op.name}:{wt}" for op, wt in step.scheduler_evidence.weights_after)
        )
        row = "\x1f".join(
            [
                str(step.index),
                step.origin.name,
                step.parent_case_id or "",
                fb.case_id,
                str(fb.full_state_novel),
                str(fb.effect_novel),
                str(fb.contract_violated),
                str(fb.observation_failure),
                str(fb.feedback_eligible),
                str(fb.already_retained),
                str(fb.admission_eligible),
                "|".join(str(x) for x in fb.new_violation_fingerprints),
                "|".join(str(x) for x in fb.new_effect_keys),
                str(fb.trace_completeness),
                str(fb.trace_termination),
                weights,
            ]
        )
        sha.update((row + "\x1e").encode())
    sha.update(("R:" + "|".join(result.retained_case_ids)).encode())
    return sha.hexdigest()


def _archive_digest(case: Any) -> str:
    try:
        return hashlib.sha256(build_tar(case)).hexdigest()
    except ValueError as error:
        return "build-error:" + str(error)


def _inputs_digest(result: Any) -> str:
    sha = hashlib.sha256()
    for step in result.steps:
        attempt, evidence = step.mutation_attempt, step.scheduler_evidence
        if attempt is None:
            continue
        row = {
            "index": step.index,
            "parent": step.parent_case_id,
            "operator": attempt.operator_id.value,
            "applied": attempt.applied,
            "mutation_policy": attempt.mutation_policy.value,
            "weights_before": [[op.value, wt] for op, wt in evidence.weights_before],
            "selected_weight": evidence.selected_weight,
            "reward": evidence.reward,
            "weights_after": [[op.value, wt] for op, wt in evidence.weights_after],
            "child": attempt.child_case.case_id,
            "archive": _archive_digest(attempt.child_case),
        }
        sha.update((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\x1e").encode())
    return sha.hexdigest()


def _run(cell: str) -> Any:
    arm, seed, budget = cell.split(":")
    rds_arm, variant = ARMS[arm]
    config = RdsCellConfig(rds_arm, int(seed), int(budget), VocabularyMode.OBSERVED_NAMES, variant)
    return run_rds_cell(minimal_seed_corpus(), synthetic_effect_result, config).campaign


def test_golden_covers_every_registered_cell() -> None:
    assert set(GOLDEN) == set(CELLS)


@pytest.mark.parametrize("cell", CELLS)
def test_registered_arm_reproduces_run_sha_golden(cell: str) -> None:
    result = _run(cell)
    assert (_trajectory_digest(result), _inputs_digest(result)) == GOLDEN[cell]
