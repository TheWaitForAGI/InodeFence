"""Controlled oracle check (not node-tar): C0/C1/C2 demo fixture verdicts (P0-3)."""

import pytest
from scripts.oracle_fixture_check import (
    CONTROLLED_EXTRACTOR_ID,
    CONTROLLED_LABEL,
    ORACLE_FIXTURES,
    UncheckedControlledExtractor,
    main,
    render_oracle_fixture,
    run_oracle_fixture,
)

from inodefence.builder import build_tar
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ChangeField,
    EntryType,
    IdentityEvidence,
    StateChange,
)
from inodefence.pipeline import run_case

FIXTURES = {fixture.name: fixture for fixture in ORACLE_FIXTURES}


@pytest.mark.parametrize("fixture", ORACLE_FIXTURES, ids=lambda fixture: fixture.name)
def test_controlled_oracle_fixture_verdicts_match_expectation(fixture) -> None:
    assert fixture.fixture.read_bytes() == build_tar(fixture.case)
    result = run_oracle_fixture(fixture)
    assert result.execution.target_id == CONTROLLED_EXTRACTOR_ID
    assert "node" not in result.execution.target_id
    assert tuple(verdict.violated for verdict in result.violations) == fixture.expected
    rendered = render_oracle_fixture(fixture, result)
    assert rendered.splitlines()[0].startswith(f"[{CONTROLLED_LABEL}]")
    assert "UNEXPECTED" not in rendered


def test_c0_fixture_creates_a_path_outside_extraction_root() -> None:
    c0, _, _ = run_oracle_fixture(FIXTURES["c0"]).violations
    (change,) = c0.evidence
    assert isinstance(change, StateChange)
    assert (change.path, change.fields) == ("escape.txt", (ChangeField.EXISTENCE,))


def test_c1_fixture_is_c1_plus_c2_not_c1_alone() -> None:
    # A sentinel hardlink changes the sentinel's nlink/ctime on a real filesystem.
    c0, c1, c2 = run_oracle_fixture(FIXTURES["c1"]).violations
    assert not c0.violated
    assert c1.violated and c2.violated
    (identity,) = c1.evidence
    assert isinstance(identity, IdentityEvidence)
    assert (identity.internal_path, identity.sentinel_path) == (
        "extract/alias",
        "outside/sentinel.txt",
    )
    (change,) = c2.evidence
    assert isinstance(change, StateChange) and change.path == "outside/sentinel.txt"
    assert ChangeField.NLINK in change.fields
    assert ChangeField.CONTENT not in change.fields


def test_c2_fixture_changes_sentinel_content_without_identity_sharing() -> None:
    c0, c1, c2 = run_oracle_fixture(FIXTURES["c2"]).violations
    assert not c0.violated and not c1.violated
    (change,) = c2.evidence
    assert isinstance(change, StateChange) and change.path == "outside/sentinel.txt"
    assert ChangeField.CONTENT in change.fields
    assert ChangeField.IDENTITY not in change.fields


def test_controlled_extractor_refuses_to_leave_the_sandbox() -> None:
    escape = ArchiveCase((ArchiveEntry("../../escape.txt", EntryType.REGULAR, content=b"x"),))
    with pytest.raises(AssertionError, match="left the sandbox"):
        run_case(escape, UncheckedControlledExtractor())


def test_oracle_fixture_cli_reports_controlled_label_and_known_limitations(capsys) -> None:
    assert main() == 0
    output = capsys.readouterr().out
    assert output.count(f"[{CONTROLLED_LABEL}]") == len(ORACLE_FIXTURES)
    assert "알려진 한계:" in output
    assert "C1은 단독으로 나오지 않는다" in output
