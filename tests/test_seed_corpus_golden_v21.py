"""Regression golden for the v2 seed-corpus parameter (v2.1 `minimal-empty-reg-v1`, #512).

**Nature of this golden.** Unlike ``test_registered_arms_golden*.py`` (values minted at the
registered run SHA bed077a), there is no code at bed077a for the v2 grammar or the new
corpus. These values were **minted at the commit that added the corpus parameter** and only
pin that commit's behaviour against later change (W4, 2026-11-18). They are not evidence that
anything matches a registered run.

Cells: R (chain m <= 4, the main v2 R), D and S-u, under both v2 policy ids -- the registered
corpus (``observed-names-b-grammar-v2-freeze-3``) and ``minimal-empty-reg-v1`` -- with the
structure-dependent synthetic producer of ``test_registered_arms_golden_variable`` (a test
fixture, not native evidence). Four digests per cell: that file's ``trajectory``, ``inputs``
and ``steps``, plus ``extra`` over the initial case IDs, every build-invalid step and every
mutation chain (``canonical_json``), which the other three do not cover.

Seeds 5 and 777 are not registered and not in the exploration ledger (see the variable golden).
Regenerate with ``python tests/test_seed_corpus_golden_v21.py`` only when a change to these
cells is intended and recorded.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inodefence.evaluation.rds import (  # noqa: E402
    RdsArm,
    RdsCellConfig,
    RVariant,
    VocabularyMode,
    run_rds_cell,
)
from inodefence.generator import minimal_seed_corpus  # noqa: E402
from inodefence.model import canonical_json  # noqa: E402
from test_registered_arms_golden_variable import (  # noqa: E402
    _inputs_digest,
    _steps_digest,
    _trajectory_digest,
    _variable_result,
)

ARMS = {
    "R": (RdsArm.R, RVariant.CHAIN_M4),
    "D": (RdsArm.D, RVariant.WALK),
    "S-u": (RdsArm.S_U, RVariant.WALK),
}
CORPORA = {
    "v2": VocabularyMode.OBSERVED_NAMES_V2_FREEZE3,
    "v2.1": VocabularyMode.OBSERVED_NAMES_V2_FREEZE3_MINIMAL_EMPTY_REG,
}
SEEDS = (5, 777)
BUDGETS = (16, 64)
CELLS = tuple(
    f"{corpus}:{arm}:{seed}:{budget}"
    for corpus in CORPORA
    for arm in ARMS
    for seed in SEEDS
    for budget in BUDGETS
)

#: ``"<corpus>:<arm>:<seed>:<budget>" -> (trajectory, inputs, steps, extra)``.
GOLDEN: dict[str, tuple[str, str, str, str]] = {
    "v2:R:5:16": (
        "2f87e3778fc0bb330cfd1e3a7d1c76571181716e69c6737f4659de1a64ce1020",
        "b1fd32f02ce1a917960edbf9fd66d9152cbabd628a96e210e36b5c009bc24e86",
        "62a93adb844ebda12ca249d7637fc2c3fd6289ed164dbda451a42458175c5aa7",
        "4b661d47656da795a0f19c9739166d151387b2f5bcd6fd4251dcec4dff88cd3a",
    ),
    "v2:R:5:64": (
        "5877259f15bd94a8799a15818d36863386fad80ec77cf46594da42ab8feb9f19",
        "e91982151b466567f878ea5647f64dcad584baccdbd11a7c315067a1abaaf351",
        "6fbd27acd197bfe3352ea4e6f841512a91164d5411c62602aa5da928697c6387",
        "cd0cbfb32da4d44dc86460bf2430e8cba95e9d5b0339be7f0c612a1e67614d95",
    ),
    "v2:R:777:16": (
        "7eb268ffec3277bc78c0670b2eeb12ceffb6c41971e959f1c3d02448c483b784",
        "a3c284d2c2293fc74854dfb22189a82cd17471f6edc70229d6d65bed91d3d18c",
        "660e72b00f190373fd8f05b9cbaec8b4d74ccae46d42fbe4f0cd305e11ab0d16",
        "88dcad960cb03101eac10e9f6449714097208cf3ad55b35b280d26eb0fe82c5a",
    ),
    "v2:R:777:64": (
        "7fcaffb485fcc83cf5421ee3b2636cf2feb1c6905087af2561945a8e559875cd",
        "0461452608931e773ad25b98ae335dbcd70a6234a6cf48919e71999cb939c1eb",
        "970a1ecf7b38396eb72dd94f8dfac61f074747cdb0c70cd41e020bd8df7294ef",
        "959c7502ba3f1bff9eba468a3c5d531440a7fdef86eaaf6071cd120c4b061406",
    ),
    "v2:D:5:16": (
        "4871d0000ca37b0e047bac59206c1cc0aa830e7d052776fc7cd1772f7bf385d7",
        "16f4b74337c84f79a0cf7fec5550fc5a47fe2aea84bf2a137adc83764ac1827a",
        "fbd230d5fc753f11013ef06fd3cc21d9af7a2616e0634af8bf444cb186590184",
        "60268e1e1fd8183a5037d27992e5729066921d1719f3340554451a0f9fef1b2f",
    ),
    "v2:D:5:64": (
        "545d72e42d2506fa3a3fedb72b2876c6f1c70d3a2196c4eed57d3e811027c369",
        "6a18c3940d586167e95d78ed51b28b5bea94fe358ed075ba509ee6e26e8b5644",
        "c7e93042ff8e40cb8422a050a059cd7e2066a068f9a63620c6ae4e221a4547cf",
        "60268e1e1fd8183a5037d27992e5729066921d1719f3340554451a0f9fef1b2f",
    ),
    "v2:D:777:16": (
        "33645c27cda995eaf7d8fb784df142b6d56e508cc7b39cc05d9263c69929eb4b",
        "4153d5a13bcaaee39b96626e41e7d3367f2d89eb3a12ad0c85c45eefbd3d714b",
        "712119ff8b765daeadd29fb253ecd6dcf4a5e421ec52e0f6e0a74f3f8ad436c9",
        "60268e1e1fd8183a5037d27992e5729066921d1719f3340554451a0f9fef1b2f",
    ),
    "v2:D:777:64": (
        "73ec0fee718e6e060b7ace9640791c3b759166ace347b70ccda7735a0d42f0c3",
        "cf3d22ef8ec399b65a3e752531a415d44c431a92b28ea5236a8981dcd7cbee9c",
        "f5240281e6fa61729eabc0d3230db0041ff1741b24f29c7ae9cd3ce33091c0fa",
        "60268e1e1fd8183a5037d27992e5729066921d1719f3340554451a0f9fef1b2f",
    ),
    "v2:S-u:5:16": (
        "4e8f5ce2c404fa3956bd5d3ce624d73bbfea2d70c6d452a6b7cec76820a07863",
        "35cdc5819fe7a1e22bdda68c804f0e200383975776097ba3aa76ed4f4e5b21de",
        "356406a78494377f00702473fb8f509035e0037b04ea53cd3559e39e4d28d44b",
        "60268e1e1fd8183a5037d27992e5729066921d1719f3340554451a0f9fef1b2f",
    ),
    "v2:S-u:5:64": (
        "15b4de84c27c294cd58e596639ccb77813032128558727cf517d276551e0bce9",
        "ffe41aba9976e7a0dba3cd580ef3a74b101c1ded8da6abc3dedbd0fcc64b49b0",
        "37b77ace96697633138e9a80a961211f0ef8005fbe57f48a4f7912b6069252ef",
        "60268e1e1fd8183a5037d27992e5729066921d1719f3340554451a0f9fef1b2f",
    ),
    "v2:S-u:777:16": (
        "aaef4f65c8d7c429e8d5aa797dc660438c918e112993627e59d16b6b5e76923b",
        "b94edc5ecd261a524eb851549c2fcabfd5c6e01874fb5c3630d9142306848314",
        "f0486ab8103b0d62096a5c2e7356ea8f1a5053f5169b70b6f7b675d888c56b92",
        "60268e1e1fd8183a5037d27992e5729066921d1719f3340554451a0f9fef1b2f",
    ),
    "v2:S-u:777:64": (
        "7686af6a69987959fcf178cd009c01bbf4d310f346098c4c10d3f481743cd876",
        "94f19dc34cd90e9eaed39e5b44b70bfbd9253b0f9d5fca36e348db81100cd0ce",
        "4ba05b5d097c7c4257f62f7013f417ba4470b4e9482f491be5d1539dbe3b6ac0",
        "60268e1e1fd8183a5037d27992e5729066921d1719f3340554451a0f9fef1b2f",
    ),
    "v2.1:R:5:16": (
        "c8924d596ba5a5572a401f8864ebb6d7860d372bb85eff264794a102b236390c",
        "d64684c53f1b38ef79d5747e1d5fce8ab9d40724c83d1b9780bc32ac35d3f52d",
        "5d9a28fda252b7302832488ab1ce15bd50f442d62df1bb0f5c70f77a6e04fa66",
        "981fd8955def8e8fd31ea6a4912328a162ae6207a5ce38664efe32b6d415ad6d",
    ),
    "v2.1:R:5:64": (
        "b4430727d20a5b5909414a9dcaa8a4f1257b6c2631cac74ede482b8c49a39dc9",
        "45af05d1449f77420b5aa660e8308e5ecabcb5b1e3728286df45acd600332a2d",
        "98b7da2cf841f6be893913bfd5c4d31ae0cb3ea2291069e9f39864a2db85bbcb",
        "b7cb4efffa23d4a26fdd5251d30b63703a412c06b245f140c114da3986a1fcc1",
    ),
    "v2.1:R:777:16": (
        "074dc8c3a998db737e77dd7b4ed7e39a43a2f8c8133883bb88d67ff64b86d266",
        "9b832ac1c9ea4ca60b57c123ce0d29a7ec7bd7035eb7e2a4995866b37f842599",
        "862d9f96d49c05a96d0205c8b7f43da5486ec9cdf4f746b40a179ed68be004be",
        "dd79ba64b49fc1dc2240d76c099255c1047a526224617241882ab367806f18fb",
    ),
    "v2.1:R:777:64": (
        "315ef88067565a28555c4e107c28ae7150f32d87ef249d55a2558454d7e7c39d",
        "a45e21bb21714f9c0239a416e7677b1c61e4e17b3c14d3f553417a5586f5f94e",
        "bbbd8c55471ba77ef940228dea86bf57a6d41dea500c149d572ff7eced7bc528",
        "5cc256473409e4e3bfda7377f8d5b547a2771ad65f9a8827e11be67492b71552",
    ),
    "v2.1:D:5:16": (
        "98374c721aed64defbb8011b9b4b713e851df86f0988b5d0254e32a5fa9672cd",
        "242a44845f79147c788389195a3ce2eed148d155cbb781c1b48478fa40ca1eff",
        "05d4e26566f98fdce73bbef8fd686bd01a2779fc46375cd9034b61d4ec81a1ea",
        "b25323c457c3c1858fb79e130fe6ecc729c1ace6de2dfca21276e43cc8e94585",
    ),
    "v2.1:D:5:64": (
        "29015ceda0bd3ebeb769479d63ef5dab5677914dff8773d30cddf594a06cc80b",
        "6988a1cbef964861011b5076fd42c1a913a7b560d95319ea2d6923e71f73b430",
        "a657f174c035b9a9e20ddbb70985d2e1ad922544cfe331b4108df006ba0d77bb",
        "b25323c457c3c1858fb79e130fe6ecc729c1ace6de2dfca21276e43cc8e94585",
    ),
    "v2.1:D:777:16": (
        "f6d82d3bb321e3e4ed6b18653f59b0fe6de7b35e0141228f3ff56bf9601109db",
        "8d7fd822e05d33849369628bcb96aceca8f871cd8d9fe92af96999550b5b5817",
        "a08b691b0fcf1dca89c56095526fce03cf7c23ef01302ea96cf14798143a8af7",
        "b25323c457c3c1858fb79e130fe6ecc729c1ace6de2dfca21276e43cc8e94585",
    ),
    "v2.1:D:777:64": (
        "936a611806935209c85b511d600e040aa29cd758f8cfee86c1752ac131aabfe3",
        "df5bac55670522597593b54525df582b2f23fead00fd66bfa3b3eeb34ee71ed4",
        "fbe89401c4c91cf860e4539b05dc778b2865929c85c0bc14caa5d543c8a690c7",
        "b25323c457c3c1858fb79e130fe6ecc729c1ace6de2dfca21276e43cc8e94585",
    ),
    "v2.1:S-u:5:16": (
        "fcf1308ce956f9f19ecd39b1a52a2d38b543f2be80276b7311b604c2fd28a2ca",
        "70fd074982495dc097279cf428390ace273fb14a50ce22277e237404b3f67af9",
        "2de3df7bbaf6b64ccc4f84bc1839e40ab73ad5066fbad521f9b7c46d5ccdcc10",
        "b25323c457c3c1858fb79e130fe6ecc729c1ace6de2dfca21276e43cc8e94585",
    ),
    "v2.1:S-u:5:64": (
        "46fe6dd768c0ff493f598dac0fabdc1bcfdc292f8a123ccc80c3b0e787031b6e",
        "4aadd54790cf850b6ca115d1a73480a01af817839ea71087dc90ffd83f5232a2",
        "6ca5619a1c914478d88d769d6bed6c6f15ad986b8e3da13fb27c09c4eb76c833",
        "b25323c457c3c1858fb79e130fe6ecc729c1ace6de2dfca21276e43cc8e94585",
    ),
    "v2.1:S-u:777:16": (
        "79176969879f8227f4d7c12c3ae3f1d006da60b04f77d6db7553e2730a3ff282",
        "cec79a7b8ef8e21825828105976f1a60d71ac3ecc0ff3530f8ba88bedee8f1a6",
        "cfadc8eed9647ebe6e6a6d1a559198de3241d2d5caa6c8c72318c986fe7cf99e",
        "b25323c457c3c1858fb79e130fe6ecc729c1ace6de2dfca21276e43cc8e94585",
    ),
    "v2.1:S-u:777:64": (
        "e6c82004722c3d97948cc72b03ac5b84d4bac2b9b8713f544f1f59a88095274b",
        "a122940a2eb1e7f83a9188360da260e88ce17ac33f6a9a027ad38823853ca868",
        "6e4939a17c968b5b566353366cbd4fd24fd7b26d2cea9ed5cbe9cfe8005e6fa9",
        "b25323c457c3c1858fb79e130fe6ecc729c1ace6de2dfca21276e43cc8e94585",
    ),
}


def _run(cell: str) -> Any:
    corpus, arm, seed, budget = cell.split(":")
    rds_arm, variant = ARMS[arm]
    config = RdsCellConfig(rds_arm, int(seed), int(budget), CORPORA[corpus], variant)
    # The launcher's argument: the campaign binds the policy's corpus itself.
    return run_rds_cell(minimal_seed_corpus(), _variable_result, config).campaign


def _extra_digest(result: Any) -> str:
    sha = hashlib.sha256()
    sha.update(("I:" + "|".join(result.initial_case_ids) + "\x1e").encode())
    for step in result.build_invalid_steps:
        sha.update(("B:" + canonical_json(step) + "\x1e").encode())
    for chain in result.mutation_chains:
        sha.update(("C:" + canonical_json(chain) + "\x1e").encode())
    return sha.hexdigest()


def _digests(cell: str) -> tuple[str, str, str, str]:
    result = _run(cell)
    return (
        _trajectory_digest(result),
        _inputs_digest(result),
        _steps_digest(result),
        _extra_digest(result),
    )


def test_golden_covers_every_cell() -> None:
    assert set(GOLDEN) == set(CELLS)


@pytest.mark.parametrize("cell", CELLS)
def test_v2_corpus_cell_matches_regression_golden(cell: str) -> None:
    assert _digests(cell) == GOLDEN[cell]


if __name__ == "__main__":
    for cell in CELLS:
        print(f"    {cell!r}: {_digests(cell)!r},")
