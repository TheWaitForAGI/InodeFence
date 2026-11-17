"""Registered arms under a structure-dependent synthetic producer reproduce bed077a (v2 U2 prep).

``tests/test_registered_arms_golden.py`` uses ``synthetic_effect_result``, whose BEFORE/AFTER
snapshots never change with the input. Under it D's structure-coverage admission adds nothing
beyond the seeds and R's walk variant is not pinned. This file adds a deterministic producer
whose AFTER snapshot depends on the input entry structure (type, path depth, parent escape,
link target), so D's retention branch (a new structure feature admits a mutation) and R's
walk are exercised, and pins R (seed-restart and walk), D and S-u against the run SHA.

Three digests per cell:
* ``trajectory``: the same rows as ``test_registered_arms_golden._trajectory_digest``.
* ``inputs``: the same rows as ``test_registered_arms_golden._inputs_digest`` (operator,
  applied, policy, scheduler weights, child case ID, SHA-256 of the built TAR).
* ``steps``: SHA-256 over each step's ``canonical_json`` -- the serialized step record
  itself, so a schema id or field added to the step model (v2 U2 must not) is caught.

The producer is a test fixture, not native evidence, and it encodes no CVE, payload or target
path: it only maps generic entry shape to a generic snapshot shape.

Seeds 5, 777, 4242 are not registered (EXP-0 9001-9005, EXP-3 9006-9025, EXP-2 9026-9185,
8101-8110), not in the exploration ledger and not a HOST3 block (51600+).

How to regenerate (no Docker, code only): extract ``git archive GOLDEN_COMMIT src`` to a
scratch directory and run this file's functions over ``CELLS`` with the stdlib interpreter
and no site packages (``env -i PATH=/usr/bin:/bin PYTHONHASHSEED=<n> PYTHONPATH=<x>/src
/usr/bin/python3 -S -B mint.py``, with a stub ``pytest`` module). Minted 2026-11-18 from
bed077a with PYTHONHASHSEED 0, 17 and 999 (identical), and the same values from
research/b-engine 057a769 (after v2 U1).
"""

from __future__ import annotations

import dataclasses
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
from inodefence.feedback import state_signature
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model import (
    ArchiveCase,
    EffectRunResult,
    EntryType,
    ObjectSnapshot,
    ObjectType,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
    canonical_json,
)
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts

GOLDEN_COMMIT = "bed077af62b1cdd5cc8dec96eb9cbe93ba542f1d"

ARMS = {
    "R": (RdsArm.R, RVariant.SEED_RESTART),
    "R-walk": (RdsArm.R, RVariant.WALK),
    "D": (RdsArm.D, RVariant.WALK),
    "S-u": (RdsArm.S_U, RVariant.WALK),
}
SEEDS = (5, 777, 4242)
BUDGETS = (16, 64)
CELLS = tuple(f"{arm}:{seed}:{budget}" for arm in ARMS for seed in SEEDS for budget in BUDGETS)

#: ``"<arm>:<seed>:<budget>" -> (trajectory, inputs, steps)``, minted at GOLDEN_COMMIT.
GOLDEN: dict[str, tuple[str, str, str]] = {
    "D:4242:16": (
        "aa257606db16f48b9380a060207fe228b1251bc5d2c3819b22d3e0b01e8e635c",
        "4741c40ca81a8bf35531a04262146179fc763007a94b849793a79c1589ae5990",
        "978386775cd23532e1ec3611fe7ef5ed8c3bfab86b9dc5d63bae8a609c680abc",
    ),
    "D:4242:64": (
        "81231da3664943ac21a80f87e33a32ddcab61d5558b376f2b8e3faa3cc963ca0",
        "0e360cd0c5d31dc7be032acc6f774e22ef01dbfb52155d394001826a4acf87d7",
        "f6d20e914f94264c44229a1be9ae00489a1901f7897214c5777c6154c84ef575",
    ),
    "D:5:16": (
        "d37e97da55a68350122b63e90790ed9e149d2ecc925004155571f5618425a4d9",
        "7c7d4b9089eaeb4628fc51cc38306a94ec776e043b7467b75bbfe775cf40ac2b",
        "9f0950c1c6575da0a87e69af08a84419b577287d0af4876af95c102023a675d3",
    ),
    "D:5:64": (
        "1297953ecc81b43f6bcb4c0fd88988a988f1c2a18590fad674d9c598670a83a9",
        "9ade2ef23259f403898d989e39c6b55399678038534ee70894dddb45833bd7fa",
        "fe8d5773e9c22936f4984eaaca55081e303fb5cef62d3e732572800a8e133a14",
    ),
    "D:777:16": (
        "6bedf76203f21dffeb46bc2c626ec03a09e3eb5ed677ba7922a59588ee92559d",
        "916acf801d63324d0fe2553741b33415452ff80eaef5a635150b9ee33125d70f",
        "50ef346ed33c9227fec56364dc6c7db5729df83188fee221dd495e93f00ac558",
    ),
    "D:777:64": (
        "f19b89dfd7666f38368abf5b5d2282886c848f15482467053376c2bb5a1b6870",
        "b54ec9df407c6dbe3b37fd9137700db188b96fc14b98aa3ebaa929c91951d707",
        "469e2a4ad1aa77cc240cda2c0f0b665da1883f924a9e7a46e84c9cf52537e782",
    ),
    "R-walk:4242:16": (
        "dda82d6a84eb65d52da0bb43b6169025a4f6e9df94505e518db37fdba27ec994",
        "29c4aa82742d5e26f94243cd10b471cb89df0b264ee0f73891d583fe4e177535",
        "3453b4044cef422299d6d7e5b4647eeb50daae443c58ca6bea7e2a73ccf01274",
    ),
    "R-walk:4242:64": (
        "07ed16cecb90cb52be15effe09f73817ecce482a24b97c312ef29a4216d7a9b1",
        "7436ed3fccea88cecbaf555251abb4327cb83f54b135a90bad51b7d4df04146e",
        "4fd2951b199c3396687fd7a146b773f1dd6486a8635ce531533e41d7128520d2",
    ),
    "R-walk:5:16": (
        "cb731fc5ae7922836d58967e7360cc2be73de37384750a35c2c752b02890aadd",
        "57edbc6eb20d9544994dbc5d7bcb94adbfb39a2e573de36fc015796046c71047",
        "77de601959a1077a284a1c636a9f42162dedc558e21fcd98c4aa3eed56acef5d",
    ),
    "R-walk:5:64": (
        "90782434fe852fb88e801adf0eb48a06b01c5f3293d875fcdec20cfc103b160a",
        "c33289f5df9303e3e45a216f2e709cf88a4b682bb06ad7d8dd32f53bbf285f15",
        "a023f4f74cc1f321f8c05e84028c9301fd7785cf34e332c4a7990ae3babd992d",
    ),
    "R-walk:777:16": (
        "92238d613b8409a27a6c1005db90f962a807e7aeb4967902d4b1c286be58afc6",
        "178309a2949c76b129508090c0c5572ee61d7eee027a5b8691325f5947db939f",
        "2bb73c538f957dad63423ff7ae0918834424dfa6998e380e4e2d2424639f7c5f",
    ),
    "R-walk:777:64": (
        "cbd83269a7fc7ecce9bc886a81a32f8995d698856720fc442a8c9d6a9ee9dd83",
        "e7308830f127be14f3061584551691ae015a33b99ce330e7774938419703d518",
        "51c57ce1cf79b222a944e00047142dec0cdae8445f3aac8dcae8df69d4af4fea",
    ),
    "R:4242:16": (
        "d73ccafd49386f10772870324399b3f9bc3d0566418b45adfd05f0c5aa34144b",
        "b8d4b42dadaec38fd78efb4aa03a36748cd1592d06246a8f4c9bb74692e3ec7a",
        "72c5bf8ff9bb99ce0a97a327fb14a3a941c418335ffb199642d5918dc83497ff",
    ),
    "R:4242:64": (
        "59095f4dc0a4ea39a326d1392660f0e7e1087b99afc75eafafabf1f68bd2ed8f",
        "ba9b1ba2c6f419a8d5c5bb236e537aea0ad1d7e97af53d720c6b8d1e88957db1",
        "91a464a1797a684d9a08f7456b0c9a663f5c8b86bdcd397d19d6ae4bdf2bbf75",
    ),
    "R:5:16": (
        "73a7f1512c99bcec33f41e546a73143de7f8e5206caf841b2414405106d7dcb5",
        "07093a89f4ca03a7c6c5c5535faa13bb2e6575ad9e87c353a432bf9d6bf9bc45",
        "700d318ba28f7505261c94acebfe9b7829cab8f92aa4901b01cc3db3c22fd596",
    ),
    "R:5:64": (
        "08fb844106a0ef413c78efec14ed7d90ed5cb5d3ae5235106973e8d96d5cd773",
        "b1923df14d78d89621151323733b2a3865463b7600b8d7b6cf97ec276e222ecc",
        "bda41ff2421c476cdd151017eadbd83bfc56bc0163710362e11a317f9c16dbf5",
    ),
    "R:777:16": (
        "b9f475504badee6338f02dabc6eb99145f3881561b0116db94400de706a618e7",
        "4bbfc77912d6e8cfa3705f5b37def685098113a811e782ebba7d6e16f018176a",
        "ef407dbe809306a3cee281d208a9c306b500dc226b588ce8e96208df4561abf1",
    ),
    "R:777:64": (
        "0e99069e0fb878b997eac155fd33af59d6bd37c8b9ef9762689205e7a91b4652",
        "5ed7db5a4a605984a3ca6e89de19dd3ec1e3901ffd285d5b75c3d97c449235c9",
        "c8af5fc15e9cc1a3c689d2765ebe98ff74eb099189d6f26d68fb538150371139",
    ),
    "S-u:4242:16": (
        "23e06d25f791a03809dac9562acea5bcd145630b7fd1419cb36c35894883469b",
        "bf52e08af5326958b0eb84e7abf26185035303fcbef2beacc34d2b6d0aafbe65",
        "53fd6d18e3cdc136ae2cc7e7e7579bca884ec87f703ea757df58ffae4ff8b731",
    ),
    "S-u:4242:64": (
        "b20bc865b3034b5612cf61032734004d0d92f243b47c199ff60987ac0c9040cd",
        "e050a0d9d98e01adaaefaa082bd8ea2188c5a4104d9c19a7d90fbca0da104b1a",
        "fed6b90589f04fb66c4723cd527f338f468c2345b6ad9d1a3edc300cb51e8d19",
    ),
    "S-u:5:16": (
        "3514713f7868335f9ce0e5d8b30014eae7b991a3d25c100cce0c0e03b1b38b47",
        "9744d5c219cc520d90c17b1975e3bc53c20f12a6a09a9c1c3c9b354379991f94",
        "6b3c1e2572dd4813be63ef7689e597244761578f217b4c8d3da435a6ae0aeca8",
    ),
    "S-u:5:64": (
        "2a8bb5d20ec0361c754530b179adb3e1f0313841c6dd2e716bfd200cd55790b4",
        "359b1634684a03f11c36d6a28763ce17b29d971fd45ddd048b547605b3730d43",
        "b263d305d9e77281d88bafaf0a34ca14b7b09ccf38fb56490448ccd271b6b183",
    ),
    "S-u:777:16": (
        "ce183ae1c66cd31e0394653d11be7c7060dfa1b98b21dd4eea52cf32cc2d40d8",
        "5135ca01ea5d124ce65763d32393151e2e62bec8c663f96ceedc06b3b6f3c7a5",
        "e004f1fb7c577de6f73ca40e8f31553294cf969b7ec2074b3fdcb11112b39fa3",
    ),
    "S-u:777:64": (
        "f86cea9444c2974bae8fd663075068232f5c91645a58728047240855083aebd1",
        "7d23662eb301e424cb67864019546dadb11f743185b6d31bbd074d46c72391ec",
        "9aaf1aa98fb165d654da84864e199eaa829612d63b8670f39eaf6422fe34db58",
    ),
}

_OBJECT_TYPE = {
    EntryType.REGULAR: ObjectType.REGULAR,
    EntryType.HARDLINK: ObjectType.REGULAR,
    EntryType.DIRECTORY: ObjectType.DIRECTORY,
    EntryType.SYMLINK: ObjectType.SYMLINK,
}


def _shape_object(index: int, entry: Any) -> ObjectSnapshot:
    """One AFTER object whose type, depth, region and link text follow the entry's shape."""
    parts = [part for part in entry.path.split("/") if part not in ("", ".")]
    escapes = "/" not in entry.path[:1] and ".." in parts
    depth = min(len([part for part in parts if part != ".."]), 3)
    top = "escaped" if escapes or entry.path.startswith("/") else "extract"
    path = "/".join([top, *(f"d{level}" for level in range(max(depth - 1, 0))), f"o{index}"])
    kind = _OBJECT_TYPE[entry.entry_type]
    ino = 500 if entry.entry_type == EntryType.HARDLINK else 200 + index
    target = entry.link_target if kind == ObjectType.SYMLINK else None
    digest = hashlib.sha256(b"x").hexdigest() if kind == ObjectType.REGULAR else None
    mode = (
        0o777 if kind == ObjectType.SYMLINK else (0o755 if kind == ObjectType.DIRECTORY else 0o644)
    )
    return ObjectSnapshot(path, kind, 7, ino, 1, mode, 1, 1000, 1000, 1, 1, target, digest)


def _variable_result(case: ArchiveCase) -> EffectRunResult:
    """``synthetic_effect_result`` with an AFTER snapshot that depends on entry structure."""
    synthetic = synthetic_effect_result(case)
    run = synthetic.base_result
    before = run.before
    shaped = [_shape_object(index, entry) for index, entry in enumerate(case.entries)]
    objects = tuple(sorted((*before.objects, *shaped), key=lambda obj: obj.path))
    after = StateSnapshot(before.sandbox_root, SnapshotPhase.AFTER, objects, before.protected_paths)
    base = RunResult(
        case,
        run.archive_sha256,
        run.archive_format,
        run.execution,
        before,
        after,
        compare_states(before, after),
        state_signature(before, after),
        evaluate_contracts(before, after),
    )
    return EffectRunResult(base, dataclasses.replace(synthetic.trace, after=after))


def _trajectory_digest(result: Any) -> str:
    """Same rows as tests/test_registered_arms_golden.py::_trajectory_digest."""
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
    """Same rows as tests/test_registered_arms_golden.py::_inputs_digest."""
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


def _steps_digest(result: Any) -> str:
    sha = hashlib.sha256()
    for step in result.steps:
        sha.update((canonical_json(step) + "\x1e").encode())
    return sha.hexdigest()


def _run(cell: str) -> Any:
    arm, seed, budget = cell.split(":")
    rds_arm, variant = ARMS[arm]
    config = RdsCellConfig(rds_arm, int(seed), int(budget), VocabularyMode.OBSERVED_NAMES, variant)
    return run_rds_cell(minimal_seed_corpus(), _variable_result, config).campaign


def _digests(cell: str) -> tuple[str, str, str]:
    result = _run(cell)
    return _trajectory_digest(result), _inputs_digest(result), _steps_digest(result)


def test_golden_covers_every_cell() -> None:
    assert set(GOLDEN) == set(CELLS)


@pytest.mark.parametrize("cell", CELLS)
def test_registered_arm_reproduces_run_sha_golden_under_variable_producer(cell: str) -> None:
    assert _digests(cell) == GOLDEN[cell]


def test_variable_producer_exercises_d_retention_and_r_walk() -> None:
    """The point of this file: D retains a mutation, and R's two variants differ."""
    seeds = len(minimal_seed_corpus())
    d = _run("D:777:64")
    assert len(d.retained_case_ids) > seeds
    walk, restart = _run("R-walk:777:64"), _run("R:777:64")
    assert _inputs_digest(walk) != _inputs_digest(restart)
    assert _inputs_digest(d) != _inputs_digest(restart)


def _lineage_depths(result: Any) -> dict[int, int]:
    """Lineage depth per executed step index, from the run record only.

    Fields: ``step.origin`` (seed -> depth 0), ``step.parent_case_id`` and
    ``step.mutation_attempt.applied``. A child's depth is its parent's depth + 1 when the
    attempt was applied, else the parent's depth (``applied=False`` returns the parent
    unchanged, so it is not a lineage step). A parent's depth is the depth recorded the
    first time that case ID was executed.
    """
    by_case: dict[str, int] = {}
    depths: dict[int, int] = {}
    for step in result.steps:
        case_id = step.result.base_result.case.case_id
        if step.parent_case_id is None:
            depth = 0
        else:
            parent = by_case[step.parent_case_id]
            depth = parent + 1 if step.mutation_attempt.applied else parent
        depths[step.index] = depth
        by_case.setdefault(case_id, depth)
    return depths


@pytest.mark.parametrize("seed", SEEDS)
def test_d_admits_non_seed_non_violating_inputs_and_reaches_depth_two(seed: int) -> None:
    """D can reach lineage depth >= 2 under the registered logic (W4, before v2 freeze).

    Shown with the bed077a-pinned variable producer, not on any target. D differs from S-u
    only in its admission rule: the cell configs are equal except ``search_policy`` (same
    grammar/vocabulary, seed corpus, parent selection, operator distribution, budget).
    Asserts, within budget 64: (1) D's corpus holds a mutation child that is not a seed
    and violated no contract; (2) some executed step has such a retained child as its
    parent and lineage depth >= 2.
    """
    d_cell = RdsCellConfig(RdsArm.D, seed, 64, VocabularyMode.OBSERVED_NAMES, RVariant.WALK)
    s_cell = RdsCellConfig(RdsArm.S_U, seed, 64, VocabularyMode.OBSERVED_NAMES, RVariant.WALK)
    d_config, s_config = d_cell.campaign_config(), s_cell.campaign_config()
    assert d_config.search_policy != s_config.search_policy
    assert dataclasses.replace(d_config, search_policy=s_config.search_policy) == s_config

    result = _run(f"D:{seed}:64")
    seed_ids = {case.case_id for case in minimal_seed_corpus()}
    steps = {step.result.base_result.case.case_id: step for step in result.steps}
    admitted = [
        case_id
        for case_id in result.retained_case_ids
        if case_id not in seed_ids
        and not any(verdict.violated for verdict in steps[case_id].result.base_result.violations)
    ]
    assert admitted, "D admitted no non-seed, non-violating input"
    depths = _lineage_depths(result)
    deep = [
        step for step in result.steps if step.parent_case_id in admitted and depths[step.index] >= 2
    ]
    assert deep, "no child of an admitted non-seed input reached depth 2"
