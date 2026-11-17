"""v2.1 seed corpus `minimal-empty-reg-v1` as a parameter of the v2 policy id (#512).

* The corpus: an empty archive, then the registered regular-file seed; the empty archive
  builds to a valid TAR and reads back with no entries.
* The binding: the v2.1 policy runs its corpus even when the launcher passes the registered
  seeds; every other policy (the registered ones and v2) runs the caller's cases unchanged.
* Empty input (ORCH/W4 (가)): ``add_entry``, ``add_hardlink`` and ``add_symlink`` apply; the
  other seven freeze-3 slots are no-ops recorded with ``applied`` False, and a chain over the
  empty seed counts every attempt in ``m`` but only applied ones in its depth.
* The empty seed as a run ((나)): one execution, no violation, valid observation, in all
  three arms, which record the same corpus.
* The product ((다)): no product default or allow-list uses a v2 policy, and the
  "no successful extraction" warning does not fire for successful empty extractions.

Synthetic producer only; no target is run.
"""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from typing import Any

import pytest

from inodefence.builder import build_tar
from inodefence.drivers.decompress import explore as decompress_explore
from inodefence.drivers.oras_go import explore as oras_go_explore
from inodefence.effect_campaign import (
    EffectCampaignConfig,
    bound_seed_cases,
    run_effect_campaign,
)
from inodefence.effect_demo import effect_campaign_report
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.evaluation.rds import (
    VOCABULARY_MUTATION_POLICY,
    RdsArm,
    RdsCellConfig,
    RVariant,
    VocabularyMode,
)
from inodefence.evaluation.rds_preregistration import (
    CellRequest,
    parse_preregistration,
    preregistration_mismatches,
    require_preregistered_cell,
)
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import (
    SeedCorpusId,
    minimal_empty_reg_corpus,
    minimal_seed_corpus,
    seed_corpus,
    seed_corpus_label,
)
from inodefence.generator.corpora import MINIMAL_EMPTY_REG_REGULAR
from inodefence.model import ArchiveCase
from inodefence.mutator import MutationOperatorId, MutationPolicy, apply_operator
from inodefence.mutator.chain import apply_chain
from inodefence.mutator.dispatch import operator_ids
from inodefence.mutator.policy import RECORDS_BUILD_INVALID, SEED_CORPUS
from inodefence.tar_reader import read_builder_tar
from inodefence.target_result import no_extraction_warning

V2 = MutationPolicy.V2_FREEZE3_FIXED_BASELINE
V21 = MutationPolicy.V2_FREEZE3_FIXED_BASELINE_MINIMAL_EMPTY_REG
EMPTY = ArchiveCase(())
APPLIES_TO_EMPTY = {
    MutationOperatorId.ADD_ENTRY,
    MutationOperatorId.ADD_HARDLINK,
    MutationOperatorId.ADD_SYMLINK,
}
S_U = EffectSearchPolicy(
    "effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1"
)
THREE_ARMS = (
    EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M4,
    EffectSearchPolicy.D_STRUCTURE_COVERAGE,
    S_U,
)


#: Case IDs and built-TAR SHA-256 of ``minimal_seed_corpus()`` computed from bed077a's
#: ``src`` (git archive, stdlib interpreter), 2026-11-18.
BED077A_REGISTERED = (
    (
        "c56da02197b3e8959e46c08c476c7fb15a13763ce9d8d57ac5151f4b1d709fd8",
        "a80171f86279bce96ae232a7a720b318c9fdf1e64728a2f585e497e2701401d8",
    ),
    (
        "cdcc8045e37293498ff2d8e69e6e5638ee470f1bd11b1d0b8f16f1f9e783208f",
        "9b82e0b00bc6da3760316311b59f1c1cee1d23f9fa87aa89fd544d7638af52c3",
    ),
    (
        "de8ddc5ca4c15fccb638257bbbe671c4fcc9c707962cb92de6589a09f6418620",
        "3a8a8f4ca31ea5c73c61f683112166644a49575ff1b5d55ac9306182d3487b42",
    ),
    (
        "842bdde9b083096d6f5f1c93c93efb3ff35d141b7311571dab281c771d83c0d1",
        "6cf67bab5248e3d0ecf3ec797a2f0f73273e999a32286a1446420b84cac432f1",
    ),
)

_HELLO = b"hello inodefence"
#: Whole logical content per corpus id (W4): path, type, mode, content bytes, link target.
LOGICAL_CONTENT = {
    SeedCorpusId.REGISTERED: (
        (("a.txt", "regular", 0o644, _HELLO, None),),
        (("dir/", "directory", 0o755, None, None), ("dir/a.txt", "regular", 0o644, _HELLO, None)),
        (("a.txt", "regular", 0o644, _HELLO, None), ("b.txt", "hardlink", 0o644, None, "a.txt")),
        (("a.txt", "regular", 0o644, _HELLO, None), ("b.txt", "symlink", 0o777, None, "a.txt")),
    ),
    SeedCorpusId.MINIMAL_EMPTY_REG: (
        (),
        (("a.txt", "regular", 0o644, _HELLO, None),),
    ),
}


def _logical(case: ArchiveCase) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (e.path, e.entry_type.value, e.mode, e.content, e.link_target) for e in case.entries
    )


@pytest.mark.parametrize("corpus", list(SeedCorpusId))
def test_corpus_id_fixes_whole_logical_content(corpus: SeedCorpusId) -> None:
    assert tuple(_logical(case) for case in seed_corpus(corpus)) == LOGICAL_CONTENT[corpus]


def test_registered_corpus_is_byte_identical_to_bed077a() -> None:
    assert (
        tuple(
            (case.case_id, hashlib.sha256(build_tar(case)).hexdigest())
            for case in seed_corpus(SeedCorpusId.REGISTERED)
        )
        == BED077A_REGISTERED
    )


def test_v21_regular_seed_is_the_one_constant() -> None:
    assert minimal_empty_reg_corpus()[1].entries == (MINIMAL_EMPTY_REG_REGULAR,)
    assert minimal_empty_reg_corpus()[0].entries == ()


def test_empty_archive_builds_and_reads_back() -> None:
    data = build_tar(EMPTY)
    assert len(data) == 10240 and set(data) == {0}  # end-of-archive blocks, padded to a record
    assert read_builder_tar(data, expected_case_id=EMPTY.case_id) == EMPTY


def test_policy_profiles_bind_corpora() -> None:
    assert SEED_CORPUS == {V2: SeedCorpusId.REGISTERED, V21: SeedCorpusId.MINIMAL_EMPTY_REG}
    assert V21 in RECORDS_BUILD_INVALID
    assert operator_ids(V21) == operator_ids(V2)
    assert (
        VOCABULARY_MUTATION_POLICY[VocabularyMode.OBSERVED_NAMES_V2_FREEZE3_MINIMAL_EMPTY_REG]
        == V21
    )


@pytest.mark.parametrize("policy", [p for p in MutationPolicy if p != V21])
def test_other_policies_run_the_callers_cases(policy: MutationPolicy) -> None:
    custom = (EMPTY,)
    assert bound_seed_cases(custom, policy) == custom
    assert bound_seed_cases(minimal_seed_corpus(), policy) == minimal_seed_corpus()


def test_v21_binds_its_corpus_and_refuses_others() -> None:
    corpus = minimal_empty_reg_corpus()
    assert bound_seed_cases(minimal_seed_corpus(), V21) == corpus
    assert bound_seed_cases(corpus, V21) == corpus
    with pytest.raises(ValueError, match="minimal-empty-reg-v1"):
        bound_seed_cases(minimal_seed_corpus()[:2], V21)
    with pytest.raises(ValueError, match="nonempty"):
        bound_seed_cases((), V21)


def test_seed_corpus_label() -> None:
    assert seed_corpus_label(tuple(c.case_id for c in minimal_seed_corpus())) == (
        "minimal-seed-corpus-v1"
    )
    assert seed_corpus_label(tuple(c.case_id for c in minimal_empty_reg_corpus())) == (
        "minimal-empty-reg-v1"
    )
    assert seed_corpus_label((EMPTY.case_id,)) == "custom"


@pytest.mark.parametrize("operator", list(operator_ids(V21)))
@pytest.mark.parametrize("seed", range(20))
def test_freeze3_slot_on_empty_input(operator: MutationOperatorId, seed: int) -> None:
    attempt = apply_operator(EMPTY, random.Random(seed), V21, operator)
    if operator in APPLIES_TO_EMPTY:
        assert attempt.applied and len(attempt.child_case.entries) == 1
    else:
        assert not attempt.applied and attempt.child_case == EMPTY


def test_chain_over_empty_seed_counts_noops_in_m_not_depth() -> None:
    table = operator_ids(V21)
    seen: Counter[bool] = Counter()
    for seed in range(200):
        rng = random.Random(seed)
        links, attempt = apply_chain(EMPTY, rng, V21, 4, lambda r: (r.choice(table), 1))
        assert len(links) == 4
        assert attempt.parent_case_id == EMPTY.case_id
        first = links[0]
        assert first.applied == (first.operator_id in APPLIES_TO_EMPTY)
        seen.update(link.applied for link in links)
    assert seen[False] and seen[True]


@pytest.mark.parametrize("search", THREE_ARMS)
def test_v21_campaign_runs_corpus_from_registered_launcher_argument(
    search: EffectSearchPolicy,
) -> None:
    config = EffectCampaignConfig(5, 32, search, V21)
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    report: dict[str, Any] = effect_campaign_report(result, "synthetic")
    corpus_ids = [case.case_id for case in minimal_empty_reg_corpus()]
    assert report["initial_case_ids"] == corpus_ids
    assert report["config"]["seed_corpus"] == "minimal-empty-reg-v1"
    seeds = [step for step in report["steps"] if step["origin"] == "seed"]
    assert [step["case_id"] for step in seeds] == corpus_ids
    empty = seeds[0]
    assert empty["outcome"] == "executed"
    assert empty["validity"] == "valid"
    assert empty["oracle"] == {"C0": False, "C1": False, "C2": False}
    assert len(report["steps"]) == 32


def test_registered_and_v2_reports_label_the_registered_corpus() -> None:
    for policy in (MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE, V2):
        config = EffectCampaignConfig(5, 8, EffectSearchPolicy.D_STRUCTURE_COVERAGE, policy)
        result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
        report: dict[str, Any] = effect_campaign_report(result, "synthetic")
        assert report["config"]["seed_corpus"] == "minimal-seed-corpus-v1"
        assert len(report["initial_case_ids"]) == 4


_PLAN = """```preregistration
experiment_id = v21-synthetic
engine_sha = 0123456789abcdef0123456789abcdef01234567
seeds = 5, 777
budget = 64
vocabulary = observed-names-b-grammar-v2-freeze-3-minimal-empty-reg-v1
arm.R = unretained-seed-chain-m4-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
image_digest = sha256:{digest}
hit_definition = c1-or-c2-and-contract-violated
c0_counts_as_hit = false
denominator = all-cells-including-abort
abort_reporting = right-censored
rule_of_three_unit = campaign
primary_endpoint = t_first
```
"""


def test_v21_plan_passes_parser_and_gate() -> None:
    """Synthetic plan (not a registration): made-up SHA and digest."""
    assert EffectSearchPolicy.R_UNRETAINED_SEED_CHAIN_M4.value == (
        "unretained-seed-chain-m4-v1-uniform-mutation-v1"
    )
    digest = "b" * 64
    plan = parse_preregistration(_PLAN.format(digest=digest))
    assert plan.r_variant == RVariant.CHAIN_M4
    sha = "0123456789abcdef0123456789abcdef01234567"
    for arm in (RdsArm.R, RdsArm.D, RdsArm.S_U):
        request = CellRequest(arm, 5, 64, sha, False, "sha256:" + digest)
        assert preregistration_mismatches(plan, request) == ()
        cell = require_preregistered_cell(plan, request)
        assert isinstance(cell, RdsCellConfig)
        assert cell.mutation_policy == V21


def test_no_product_policy_is_a_v2_policy() -> None:
    from scripts import run_effect_demo

    product = {
        *decompress_explore.SUPPORTED_MUTATION_POLICIES,
        decompress_explore.DEFAULT_MUTATION_POLICY,
        *oras_go_explore.SUPPORTED_MUTATION_POLICIES,
        oras_go_explore.DEFAULT_MUTATION_POLICY,
        run_effect_demo.EXPLORE_MUTATION_POLICY.value,
        run_effect_demo.HISTORICAL_MUTATION_POLICY.value,
    }
    assert not product & {V2.value, V21.value}


def test_no_extraction_warning_ignores_successful_empty_extractions() -> None:
    # An empty archive that extracts nothing still terminates "success".
    assert no_extraction_warning({"success": 2}) is None
    assert no_extraction_warning({"success": 1, "rejected": 5}) is None
