"""The unchanged C0/C1/C2 oracle evaluates a whole generated sentinel set.

Multi-sentinel support is *additive*: the observer already captures every
``outside/`` object and the oracle already loops over all ``protected_paths``.
These tests drive a real generated set (>=3 sentinels) through the production
``run_case`` with the in-process controlled extractor (the same extractor as
``scripts.oracle_fixture_check``), so the ``..`` reach lands in the disposable
sandbox and never on the host. They confirm a violation is attributed to the
one targeted sentinel and that the other sentinels stay clean. The verdict
RULES are untouched (D038); only the sentinel SET is larger.
"""

from scripts.oracle_fixture_check import UncheckedControlledExtractor

from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ContractId,
    EntryType,
    IdentityEvidence,
    StateChange,
)
from inodefence.pipeline import run_case
from inodefence.sentinel_set import generate_sentinel_set

_SEED = 600
_COUNT = 3


def _verdicts(result):
    return {verdict.contract_id: verdict for verdict in result.violations}


def _changed_paths(verdict) -> set[str]:
    return {item.path for item in verdict.evidence if isinstance(item, StateChange)}


def test_c2_write_through_symlink_hits_only_the_targeted_sentinel() -> None:
    generated = generate_sentinel_set(_SEED, _COUNT)
    target = generated.names[1]
    case = ArchiveCase(
        (
            ArchiveEntry("link", EntryType.SYMLINK, link_target=f"../outside/{target}", mode=0o777),
            ArchiveEntry("link", EntryType.REGULAR, content=b"overwritten by extraction"),
        )
    )
    result = run_case(case, UncheckedControlledExtractor(), sentinels=generated.specs)
    verdicts = _verdicts(result)
    assert not verdicts[ContractId.C0].violated
    assert not verdicts[ContractId.C1].violated
    c2 = verdicts[ContractId.C2]
    assert c2.violated
    assert _changed_paths(c2) == {f"outside/{target}"}


def test_c1_hardlink_alias_to_one_sentinel_leaves_the_others_clean() -> None:
    generated = generate_sentinel_set(_SEED, _COUNT)
    target = generated.names[2]
    case = ArchiveCase(
        (ArchiveEntry("alias", EntryType.HARDLINK, link_target=f"../outside/{target}"),)
    )
    result = run_case(case, UncheckedControlledExtractor(), sentinels=generated.specs)
    verdicts = _verdicts(result)

    c1 = verdicts[ContractId.C1]
    assert c1.violated
    (identity,) = c1.evidence
    assert isinstance(identity, IdentityEvidence)
    assert identity.internal_path == "extract/alias"
    assert identity.sentinel_path == f"outside/{target}"

    # The hardlink also perturbs that sentinel's nlink/ctime (C1 is never alone).
    c2 = verdicts[ContractId.C2]
    assert c2.violated
    assert _changed_paths(c2) == {f"outside/{target}"}


def test_benign_extraction_leaves_every_sentinel_clean() -> None:
    generated = generate_sentinel_set(_SEED, _COUNT)
    case = ArchiveCase((ArchiveEntry("inside.txt", EntryType.REGULAR, content=b"benign"),))
    result = run_case(case, UncheckedControlledExtractor(), sentinels=generated.specs)
    assert tuple(v.violated for v in result.violations) == (False, False, False)


def test_protected_set_covers_all_generated_sentinels() -> None:
    generated = generate_sentinel_set(_SEED, _COUNT)
    case = ArchiveCase((ArchiveEntry("inside.txt", EntryType.REGULAR, content=b"benign"),))
    result = run_case(case, UncheckedControlledExtractor(), sentinels=generated.specs)
    assert result.before.protected_paths == generated.protected_paths
    for path in generated.protected_paths:
        assert result.before.get(path) is not None
