"""Additive symlink-referent confinement: a complement to C1 for the documented limitation
that C1 compares a symlink's OWN lstat identity and never follows its referent.

The detector resolves each extraction symlink's raw readlink text lexically and reports those
pointing outside the extraction root (HARNESS/EXTERNAL). It is strictly additive: it never
changes the C0/C1/C2 ViolationResult tuple, so existing verdicts and fixtures are unchanged.
These are contract-candidate observations judged by the production Observer; not a node-tar
result and not a fuzzer finding.
"""

from scripts.oracle_fixture_check import ORACLE_FIXTURES, UncheckedControlledExtractor

from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, Region, SymlinkReferentEvidence
from inodefence.oracle import symlink_referent_confinement
from inodefence.pipeline import run_case

_FIXTURES = {fixture.name: fixture for fixture in ORACLE_FIXTURES}


def test_flags_extraction_symlink_pointing_at_external_sentinel() -> None:
    """The c2 fixture's extract/link -> ../outside/sentinel.txt is an external referent that
    C1 (own-identity) does not flag, but the additive referent detector does."""
    result = run_case(_FIXTURES["c2"].case, UncheckedControlledExtractor())
    _, c1, _ = result.violations
    assert not c1.violated  # C1 compares the symlink's own identity, not its referent
    (evidence,) = symlink_referent_confinement(result.after)
    assert isinstance(evidence, SymlinkReferentEvidence)
    assert evidence.internal_path == "extract/link"
    assert evidence.referent_region == Region.EXTERNAL
    assert ".." in evidence.referent_target


def test_does_not_change_the_c0_c1_c2_tuple_for_any_committed_fixture() -> None:
    """Strictly additive: for every committed fixture the 3-tuple verdicts are unchanged."""
    for fixture in ORACLE_FIXTURES:
        result = run_case(fixture.case, UncheckedControlledExtractor())
        assert tuple(verdict.violated for verdict in result.violations) == fixture.expected


def test_ignores_a_benign_internal_symlink() -> None:
    """A symlink whose referent stays inside extract/ is not reported and is not a violation."""
    case = ArchiveCase(
        (
            ArchiveEntry("inner", EntryType.REGULAR, content=b"x"),
            ArchiveEntry("link", EntryType.SYMLINK, link_target="inner", mode=0o777),
        )
    )
    result = run_case(case, UncheckedControlledExtractor())
    assert symlink_referent_confinement(result.after) == ()
    assert tuple(verdict.violated for verdict in result.violations) == (False, False, False)


def test_flags_symlink_referent_into_the_harness_region() -> None:
    """A symlink into the reserved harness namespace (archive/) is a non-extraction referent."""
    case = ArchiveCase(
        (ArchiveEntry("link", EntryType.SYMLINK, link_target="../archive/input.tar", mode=0o777),)
    )
    result = run_case(case, UncheckedControlledExtractor())
    (evidence,) = symlink_referent_confinement(result.after)
    assert evidence.internal_path == "extract/link"
    assert evidence.referent_region == Region.HARNESS
