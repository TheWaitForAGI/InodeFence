"""Benign trusted-reference composition in the existing disposable runtime."""

from hashlib import sha256

from inodefence.minimizer import MinimizationTermination, minimize_case
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType, Region
from inodefence.pipeline import run_case
from inodefence.targets import PythonTarfileTarget


def test_minimizer_uses_caller_execution_and_preserves_observed_content():
    case = ArchiveCase(
        (
            ArchiveEntry("long-name", EntryType.REGULAR, content=b"x", mode=0o644),
            ArchiveEntry("unused", EntryType.REGULAR, content=b"extra"),
        )
    )
    target = PythonTarfileTarget()
    digest = sha256(b"x").hexdigest()

    def preserves(result):
        return any(
            obj.region == Region.EXTRACTION and obj.content_digest == digest
            for obj in result.after.objects
        )

    result = minimize_case(
        case, lambda trial: run_case(trial, target), preserves, execution_budget=40
    )
    assert result.termination == MinimizationTermination.FIXED_POINT
    assert result.final_case == ArchiveCase(
        (ArchiveEntry("a", EntryType.REGULAR, content=b"x", mode=0),)
    )
    assert all(preserves(step.result) for step in result.steps if step.accepted)
    assert all(not verdict.violated for step in result.steps for verdict in step.result.violations)
