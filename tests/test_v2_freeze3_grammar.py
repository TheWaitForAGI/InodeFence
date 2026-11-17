"""v2 grammar `b-grammar-v2-freeze-3` against its frozen list (#512 U3, D061). Synthetic only.

One test per row of the inventory's engine-operation -> primitive-count table that the v2
engine implements, the parameter domains of each slot, L2/O1 reachability, and the cell
binding (three arms, one policy, record build-invalid, fixed-baseline pool). Registered
policies keep the V1 table (the two registered-arm golden files prove their bytes).
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import fields
from typing import Any

import pytest

from inodefence.effect_campaign import BuildInvalidPolicy, run_effect_campaign
from inodefence.effect_demo import effect_campaign_report
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation import rds_report
from inodefence.evaluation.rds import RdsArm, RdsCellConfig, RVariant, VocabularyMode
from inodefence.evaluation.rds_report_v2 import vocabulary_pools_from_records_v2
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.mutator import MutationPolicy, apply_operator, dispatch, operator_ids
from inodefence.mutator import v2_freeze3 as v2
from inodefence.mutator.dispatch import (
    OPERATOR_ORDER_V1,
    OPERATOR_ORDER_V2,
    MutationOperatorId,
)

POLICY = MutationPolicy.V2_FREEZE3_FIXED_BASELINE
OBSERVED = ("outside", "zz")  # generic stand-ins for observed names
POOL = (*v2.m1.COMPONENTS, *OBSERVED)
DRAWS = 3000


def _rich_case() -> ArchiveCase:
    entries = (
        *minimal_seed_corpus()[2].entries,  # regular + hardlink
        *minimal_seed_corpus()[3].entries,  # regular + symlink
        ArchiveEntry("d", EntryType.DIRECTORY, mode=0o755),
    )
    return ArchiveCase(entries)


def _attempts(slot: MutationOperatorId, case: ArchiveCase | None = None, draws: int = DRAWS):
    case = case or _rich_case()
    rng = random.Random(4242)
    for _ in range(draws):
        yield case, apply_operator(case, rng, POLICY, slot, extra_components=OBSERVED)


def _changed_fields(before: ArchiveEntry, after: ArchiveEntry) -> list[str]:
    return [
        f.name for f in fields(ArchiveEntry) if getattr(before, f.name) != getattr(after, f.name)
    ]


def _inserted(case: ArchiveCase, child: ArchiveCase) -> tuple[int, ArchiveEntry]:
    """The one entry whose removal gives back ``case`` (INSERT = 1 primitive)."""
    assert len(child.entries) == len(case.entries) + 1
    for index, entry in enumerate(child.entries):
        if child.entries[:index] + child.entries[index + 1 :] == case.entries:
            return index, entry
    raise AssertionError("child is not the parent plus one inserted entry")


# --- tables ------------------------------------------------------------------------------


def test_registered_and_v1_policies_keep_the_v1_table() -> None:
    for policy in MutationPolicy:
        expected = OPERATOR_ORDER_V2 if policy == POLICY else OPERATOR_ORDER_V1
        assert operator_ids(policy) == expected
    assert OPERATOR_ORDER_V1 == tuple(MutationOperatorId)[:8]
    # The historic name stays the registered eight slots (external tools import it).
    assert dispatch.OPERATOR_ORDER == OPERATOR_ORDER_V1
    assert OPERATOR_ORDER_V2[:8] == OPERATOR_ORDER_V1
    assert OPERATOR_ORDER_V2[8:] == (MutationOperatorId.SET_MODE, MutationOperatorId.SET_CONTENT)


def test_v1_policy_refuses_a_v2_slot() -> None:
    with pytest.raises(ValueError, match="not a slot"):
        apply_operator(
            _rich_case(),
            random.Random(1),
            MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE,
            MutationOperatorId.SET_MODE,
        )


# --- one test per primitive-count row --------------------------------------------------------


@pytest.mark.parametrize(
    "slot",
    [
        MutationOperatorId.ADD_ENTRY,
        MutationOperatorId.DUPLICATE_ENTRY,
        MutationOperatorId.ADD_HARDLINK,
        MutationOperatorId.ADD_SYMLINK,
    ],
)
def test_insert_slots_are_one_insert(slot: MutationOperatorId) -> None:
    applied = 0
    for case, attempt in _attempts(slot):
        if attempt.applied:
            applied += 1
            _inserted(case, attempt.child_case)
        else:
            assert attempt.child_case == case
    assert applied


def test_remove_entry_is_one_delete() -> None:
    for case, attempt in _attempts(MutationOperatorId.REMOVE_ENTRY):
        if attempt.applied:
            _inserted(attempt.child_case, case)  # case = child + one entry


@pytest.mark.parametrize(
    ("slot", "field"),
    [
        (MutationOperatorId.MUTATE_PATH, "path"),
        (MutationOperatorId.MUTATE_LINK_TARGET, "link_target"),
        (MutationOperatorId.SET_MODE, "mode"),
        (MutationOperatorId.SET_CONTENT, "content"),
    ],
)
def test_set_slots_change_one_field_of_one_entry(slot: MutationOperatorId, field: str) -> None:
    applied = 0
    for case, attempt in _attempts(slot):
        child = attempt.child_case
        assert len(child.entries) == len(case.entries)
        diffs = [
            _changed_fields(a, b)
            for a, b in zip(case.entries, child.entries, strict=True)
            if a != b
        ]
        if attempt.applied:
            applied += 1
            assert diffs == [[field]]
        else:
            assert diffs == []
    assert applied


def test_reorder_is_move_one_if_adjacent_else_two() -> None:
    for case, attempt in _attempts(MutationOperatorId.REORDER_ENTRIES):
        if not attempt.applied:
            continue
        moved = [
            i
            for i, (a, b) in enumerate(zip(case.entries, attempt.child_case.entries, strict=True))
            if a != b
        ]
        assert len(moved) == 2
        assert Counter(case.entries) == Counter(attempt.child_case.entries)


def test_unapplied_attempt_is_zero_primitives() -> None:
    empty = ArchiveCase(())
    rng = random.Random(3)
    for slot in (
        MutationOperatorId.REMOVE_ENTRY,
        MutationOperatorId.MUTATE_PATH,
        MutationOperatorId.MUTATE_LINK_TARGET,
        MutationOperatorId.SET_MODE,
        MutationOperatorId.SET_CONTENT,
    ):
        attempt = apply_operator(empty, rng, POLICY, slot)
        assert not attempt.applied and attempt.child_case == empty


# --- parameter domains ---------------------------------------------------------------------


def test_l1_hardlink_target_depth_domain_is_zero_to_three() -> None:
    """Depth 0..3 parent steps, then 1..3 tokens (a pool without ".." keeps it unambiguous)."""
    pool = ("a", "b", "zz")
    rng = random.Random(4242)
    case = _rich_case()
    depths, counts = Counter(), Counter()
    for _ in range(DRAWS):
        child = v2.add_hardlink(case, rng, components=pool, parameters=v2.FINAL_UNIFORM)
        _, entry = _inserted(case, child)
        assert entry.entry_type == EntryType.HARDLINK and entry.link_target is not None
        parts = entry.link_target.split("/")
        depth = parts.count("..")
        assert parts[:depth] == [".."] * depth
        assert all(token in pool for token in parts[depth:])
        depths[depth] += 1
        counts[len(parts) - depth] += 1
    assert set(depths) == {0, 1, 2, 3}
    assert set(counts) == {1, 2, 3}


PINNED_MODES = (0o644, 0o755, 0o4755, 0o2755, 0o1777)
PINNED_CONTENTS = (b"", b"x" * 8, b"x" * 16)


def test_h1_mode_values_are_the_pinned_five() -> None:
    modes = set()
    for case, attempt in _attempts(MutationOperatorId.SET_MODE):
        for a, b in zip(case.entries, attempt.child_case.entries, strict=True):
            if a != b:
                modes.add(b.mode)
    assert modes <= set(PINNED_MODES) and len(modes) >= 4  # a no-op if the mode was already it


def test_regular_contents_are_the_pinned_three() -> None:
    seen = set()
    for slot in (MutationOperatorId.SET_CONTENT, MutationOperatorId.ADD_ENTRY):
        for case, attempt in _attempts(slot):
            for entry in attempt.child_case.entries:
                if entry.entry_type == EntryType.REGULAR and entry not in case.entries:
                    seen.add(entry.content)
    assert seen <= set(PINNED_CONTENTS) and len(seen) >= 2


# --- L2 / O1 reachability --------------------------------------------------------------------


def test_l2_symlink_chain_link_is_reachable() -> None:
    symlinks = {e.path for e in _rich_case().entries if e.entry_type == EntryType.SYMLINK}
    found = False
    for case, attempt in _attempts(MutationOperatorId.ADD_SYMLINK):
        if attempt.applied:
            _, entry = _inserted(case, attempt.child_case)
            found |= entry.link_target in symlinks
    assert found


def test_l2_same_path_type_replacement_is_reachable() -> None:
    by_path = {e.path: e.entry_type for e in _rich_case().entries}
    found = False
    for slot in (MutationOperatorId.ADD_SYMLINK, MutationOperatorId.ADD_ENTRY):
        for case, attempt in _attempts(slot):
            if attempt.applied:
                _, entry = _inserted(case, attempt.child_case)
                found |= by_path.get(entry.path, entry.entry_type) != entry.entry_type
    assert found


def test_o1_extend_branch_passes_through_an_existing_path() -> None:
    existing = {e.path for e in _rich_case().entries}
    found = False
    for case, attempt in _attempts(MutationOperatorId.ADD_ENTRY):
        if attempt.applied:
            _, entry = _inserted(case, attempt.child_case)
            found |= any(
                entry.path.startswith(path + "/") and entry.path != path for path in existing
            )
    assert found


def test_new_paths_use_only_the_pool() -> None:
    rng = random.Random(9)
    empty = ArchiveCase(())
    for _ in range(500):
        path = v2.raw_path(empty, rng, components=POOL, parameters=v2.FINAL_UNIFORM)
        body = path.lstrip("./") if not path.startswith("../") else path[3:]
        tokens = [t for t in body.replace("//", "/").split("/") if t]
        assert all(token in POOL for token in tokens), path


# --- cell binding --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arm",
    [(RdsArm.R, RVariant.SEED_RESTART), (RdsArm.D, RVariant.WALK), (RdsArm.S_U, RVariant.WALK)],
)
def test_v2_cell_runs_with_one_policy_record_and_ten_slot_weights(arm) -> None:
    cell = RdsCellConfig(arm[0], 777, 48, VocabularyMode.OBSERVED_NAMES_V2_FREEZE3, arm[1])
    config = cell.campaign_config()
    assert config.mutation_policy == POLICY
    assert config.build_invalid_policy == BuildInvalidPolicy.RECORD
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    report: dict[str, Any] = effect_campaign_report(result, "synthetic")
    assert report["config"]["build_invalid"] == "record"
    mutations = [s for s in report["steps"] if s["mutation_attempt"] is not None]
    assert {s["mutation_attempt"]["mutation_policy"] for s in mutations} == {POLICY.value}
    weights = mutations[0]["scheduler_evidence"]["weights_before"]
    assert list(weights) == [op.value for op in OPERATOR_ORDER_V2]
    assert set(weights.values()) == {1}


def test_v2_vocabulary_pool_is_fixed_and_pinned_reader_would_misread_it() -> None:
    cell = RdsCellConfig(RdsArm.S_U, 5, 40, VocabularyMode.OBSERVED_NAMES_V2_FREEZE3, RVariant.WALK)
    result = run_effect_campaign(
        minimal_seed_corpus(), synthetic_effect_result, cell.campaign_config()
    )
    report: dict[str, Any] = effect_campaign_report(result, "synthetic")
    steps: list[dict[str, Any]] = report["steps"]
    initial = len(minimal_seed_corpus())
    fixed = vocabulary_pools_from_records_v2(
        VocabularyMode.OBSERVED_NAMES_V2_FREEZE3, steps, initial
    )
    as_v1 = rds_report.vocabulary_pools_from_records(VocabularyMode.OBSERVED_NAMES, steps, initial)
    assert fixed == as_v1 and fixed[0] == fixed[1]


# --- per-axis: every draw is a uniform draw over the pinned domain (W4 condition (c)) ------------


class _RecordingRandom(random.Random):
    """Records each draw's method and domain; the draws themselves are the stdlib ones."""

    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.calls: list[tuple[str, object]] = []

    def choice(self, seq):  # type: ignore[override]
        self.calls.append(("choice", tuple(seq[i] for i in range(len(seq)))))
        return super().choice(seq)

    def randrange(self, start, stop=None, step=1):  # type: ignore[override]
        self.calls.append(("randrange", (start, stop)))
        return (
            super().randrange(start, stop, step) if stop is not None else super().randrange(start)
        )

    def randbytes(self, n):  # type: ignore[override]
        self.calls.append(("randbytes", n))
        return super().randbytes(n)

    def randint(self, a, b):  # type: ignore[override]
        self.calls.append(("randint", (a, b)))
        return super().randint(a, b)


P = v2.FINAL_UNIFORM
_PATH_DOMAINS = {
    P.path_branches,
    P.new_path_prefixes,
    P.new_path_depths,
    P.separators,
    P.extend_token_counts,
}
_SLOT_DOMAINS = {
    MutationOperatorId.ADD_ENTRY: {P.entry_kinds, P.contents},
    MutationOperatorId.ADD_HARDLINK: {P.hardlink_depths, P.hardlink_token_counts},
    MutationOperatorId.MUTATE_LINK_TARGET: {P.link_target_ways, P.link_target_affixes},
    MutationOperatorId.SET_MODE: {P.modes},
    MutationOperatorId.SET_CONTENT: {P.contents},
}


def test_pinned_axis_domains() -> None:
    """The domains W3/W4 recorded (axis list amended 2026-11-18). Changing one = new policy id."""
    assert POLICY.value == "uniform-b-grammar-v2-freeze-3-fixed-baseline-v1"
    assert len(OPERATOR_ORDER_V2) == 10
    assert P.hardlink_depths == (0, 1, 2, 3)
    assert P.modes == PINNED_MODES and P.contents == PINNED_CONTENTS
    assert P.path_branches == ("reuse", "extend", "new")
    assert P.new_path_prefixes == ("", "./", "../", "/") and P.new_path_depths == (1, 2, 3, 4)
    assert P.separators == ("/", "//") and P.extend_token_counts == (1, 2, 3)
    assert P.hardlink_token_counts == (1, 2, 3)
    assert P.link_target_ways == (False, True) and len(P.link_target_affixes) == 5
    assert P.entry_kinds == (EntryType.REGULAR, EntryType.DIRECTORY)
    assert len(set(P.modes)) == 5 and len(set(P.contents)) == 3


@pytest.mark.parametrize("slot", OPERATOR_ORDER_V2)
def test_every_draw_is_uniform_over_a_pinned_domain(slot: MutationOperatorId) -> None:
    """Each rng call in a slot is choice() over a pinned tuple, the name pool or the case's own
    entries/paths, or randrange() over a position range. No randbytes, no weighted draw."""
    case = _rich_case()
    pool = (*v2.m1.COMPONENTS, *OBSERVED)
    allowed = _PATH_DOMAINS | _SLOT_DOMAINS.get(slot, set()) | {pool}
    for seed in range(300):
        rng = _RecordingRandom(seed)
        apply_operator(case, rng, POLICY, slot, extra_components=OBSERVED)
        for method, domain in rng.calls:
            assert method in ("choice", "randrange"), (slot, method)
            if method == "randrange":
                start, stop = domain  # type: ignore[misc]
                assert stop is None and start in (len(case.entries), len(case.entries) + 1)
                continue
            assert isinstance(domain, tuple)
            if domain in allowed:
                continue
            # target selection: the case's own entries, paths or indices (uniform over them)
            entries, paths = case.entries, tuple(e.path for e in case.entries)
            indices = tuple(range(len(entries)))
            assert set(domain) <= set(entries) | set(paths) | set(indices), (slot, domain)


def test_pool_is_components_plus_distinct_observed_names() -> None:
    ops = v2.operators(("outside", "a", "outside", ".."), P)
    pools = {op.keywords["components"] for op in ops}  # type: ignore[attr-defined]
    assert pools == {(*v2.m1.COMPONENTS, "outside")}


def test_scheduler_draws_the_slot_uniformly_over_ten() -> None:
    from inodefence.effect_scheduler import EffectUniformMutationScheduler

    rng = _RecordingRandom(1)
    EffectUniformMutationScheduler(OPERATOR_ORDER_V2).choose_operator(OPERATOR_ORDER_V2, rng)
    assert rng.calls == [("choice", OPERATOR_ORDER_V2)]
