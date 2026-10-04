"""Input-domain and stop/preserve behavior using only a disposable controlled effect."""

from pathlib import Path

import pytest
from scripts.benign_validation import (
    UnexpectedContractEvidence,
    preserve_unexpected,
    validate_benign_case,
)

from inodefence.generator import minimal_seed_corpus
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, canonical_json
from inodefence.pipeline import run_case
from inodefence.provenance import freeze_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets import PythonTarfileTarget


@pytest.mark.parametrize("case", minimal_seed_corpus())
def test_ordinary_seed_domain_accepted(case):
    validate_benign_case(case)


@pytest.mark.parametrize("spelling", ("../outside", "/absolute", "a/../b", "a\\b"))
@pytest.mark.parametrize("link", (False, True))
def test_unapproved_spelling_rejected_before_execution(spelling, link):
    entry = (
        ArchiveEntry("link", EntryType.SYMLINK, link_target=spelling)
        if link
        else ArchiveEntry(spelling, EntryType.REGULAR, content=b"ordinary test data")
    )
    with pytest.raises(ValueError, match="benign smoke"):
        validate_benign_case(ArchiveCase((entry,)))


def test_unexpected_controlled_effect_preserved_and_stops(tmp_path):
    reference = PythonTarfileTarget()
    frozen = freeze_provenance(reference.provenance, (SentinelSpec(),))

    class ControlledEffect:
        def run(self, archive_path, extraction_root):
            result = reference.run(archive_path, extraction_root)
            (extraction_root.parent / "outside/sentinel.txt").chmod(0o640)
            return result

    result = run_case(minimal_seed_corpus()[0], ControlledEffect())
    # Real disposable metadata effect; no archive trick.
    assert result.violations[2].violated
    output = tmp_path / "unexpected"
    with pytest.raises(UnexpectedContractEvidence, match="stopped"):
        preserve_unexpected(result, frozen, '{"controlled_test":true}', output)
    assert (output / "unexpected-run.json").read_text() == canonical_json(result) + "\n"
    assert (output / "provenance.json").read_text() == canonical_json(frozen) + "\n"
    assert (output / "experiment.json").read_text() == '{"controlled_test":true}\n'
    assert not Path(result.after.sandbox_root).exists()
