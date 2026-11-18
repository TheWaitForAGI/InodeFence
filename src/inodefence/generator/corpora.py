"""Named seed corpora a mutation policy can bind to (v2.1, #512).

A seed corpus is a parameter of the mutation policy id, like the grammar and its axis
list: two v2 policy ids differ only in the corpus they bind. The campaign reads the
binding from the policy profile (``mutator.policy.SEED_CORPUS``), so a launcher that
always passes :func:`minimal_seed_corpus` (the shared launchers do) still runs the
policy's own corpus.

* ``minimal-seed-corpus-v1``: :func:`minimal_seed_corpus`, the registered four seeds
  (regular, directory, hardlink, symlink). Every registered setting and the v2 policy
  use it; its bytes are unchanged.
* ``minimal-empty-reg-v1``: an empty archive (no entries) and one regular file
  ``a.txt`` (:data:`MINIMAL_EMPTY_REG_REGULAR`). Observed, not assumed (2026-11-18): node-tar
  7.5.23 rejects the empty archive (the builder's 10,240 zero bytes) with ``TAR_BAD_ARCHIVE``;
  the run is recorded valid, rejected, no violation, and spends one budget unit. Policies
  bound to this corpus are refused off node-tar, for two separate reasons. The python-tarfile
  loop refuses them because no exploration plan is approved for them (the #533 reason is
  resolved). The decompress and oras-go loops refuse them because those loops cannot run a v2
  grammar policy (``v2-grammar-axes.md`` §4.1, "그 밖의 루프").

A corpus id fixes the whole logical content of every seed entry: name, type, mode,
content bytes and, for a link, its target (W4, 2026-11-18). Content bytes matter to the
draws: ``set_content`` is a no-op when it draws the bytes already there, which changes
``applied`` and every later draw. Changing any of these values means a new corpus id.

No target, CVE, victim path or sentinel name appears here.
"""

from __future__ import annotations

from enum import StrEnum

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType

from .minimal import minimal_seed_corpus


class SeedCorpusId(StrEnum):
    REGISTERED = "minimal-seed-corpus-v1"
    MINIMAL_EMPTY_REG = "minimal-empty-reg-v1"


#: The one regular entry of ``minimal-empty-reg-v1``: the single place its values live. These
#: are the values W3's p_R computation used, confirmed 2026-11-18 (the bytes and mode of the
#: registered ``a.txt`` seed). Changing them needs a new corpus, policy and vocabulary id.
MINIMAL_EMPTY_REG_REGULAR = ArchiveEntry(
    "a.txt", EntryType.REGULAR, content=b"hello inodefence", mode=0o644
)


def minimal_empty_reg_corpus() -> tuple[ArchiveCase, ...]:
    """Return the empty archive, then the one-regular-file archive, in that order."""
    return (ArchiveCase(()), ArchiveCase((MINIMAL_EMPTY_REG_REGULAR,)))


def seed_corpus(corpus: SeedCorpusId) -> tuple[ArchiveCase, ...]:
    """The cases of a named corpus, in campaign order."""
    if corpus == SeedCorpusId.REGISTERED:
        return minimal_seed_corpus()
    if corpus == SeedCorpusId.MINIMAL_EMPTY_REG:
        return minimal_empty_reg_corpus()
    raise ValueError(f"unknown seed corpus {corpus!r}")


def seed_corpus_label(case_ids: tuple[str, ...]) -> str:
    """The corpus id whose cases have exactly these IDs in this order, else ``"custom"``.

    Reports record this label next to ``initial_case_ids`` so a reader (G1 v2) can
    check that every arm of a cell ran the same named corpus.
    """
    for corpus in SeedCorpusId:
        if case_ids == tuple(case.case_id for case in seed_corpus(corpus)):
            return corpus.value
    return "custom"
