"""Generality: the generic C0/C1/C2 oracle catches an archive boundary violation in a
SECOND, independent extractor -- Python's stdlib tarfile -- and the hardened ``data`` filter
(PEP 706) mitigates it.

This is a controlled reference differential (``fully_trusted`` vs ``data``) on the committed
C1 hardlink fixture, judged by the production Observer + Oracle through ``run_case``. It is
NOT a node-tar result and NOT a fuzzer finding: it shows the SAME outcome-based oracle,
unchanged, fires on a different extractor, and that the hardened policy blocks the violation.
The extraction runs in-process inside the disposable sandbox, like the controlled extractor
in ``scripts.oracle_fixture_check``; the ``..`` hardlink therefore reaches the sandbox
sentinel but never the host.
"""

import platform
import tarfile
from pathlib import Path
from typing import Literal

import pytest
from scripts.oracle_fixture_check import ORACLE_FIXTURES

from inodefence.model import ExecutionResult, ExecutionStatus, IdentityEvidence
from inodefence.pipeline import run_case

_FIXTURES = {fixture.name: fixture for fixture in ORACLE_FIXTURES}

Policy = Literal["fully_trusted", "data"]


class PythonTarfilePolicyExtractor:
    """Python stdlib tarfile under one extraction filter policy.

    ``fully_trusted`` applies no sanitation (affected behavior); ``data`` applies the hardened
    PEP 706 filter (mitigated). Runs inside the BEFORE/AFTER window and writes nothing besides
    the extraction itself; archive rejection returns REJECTED rather than raising.
    """

    def __init__(self, policy: Policy) -> None:
        self.policy: Policy = policy

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        status, code, stderr = ExecutionStatus.SUCCESS, 0, ""
        try:
            with tarfile.open(archive_path, mode="r:") as archive:
                archive.errorlevel = 2
                archive.extractall(extraction_root, filter=self.policy)
        except tarfile.FilterError as error:
            status, code, stderr = ExecutionStatus.REJECTED, 2, f"{type(error).__name__}: {error}"
        except tarfile.TarError as error:
            status, code, stderr = ExecutionStatus.FAILED, 3, f"{type(error).__name__}: {error}"
        target_id = f"python-tarfile-{self.policy.replace('_', '-')}"
        return ExecutionResult(
            target_id, platform.python_version(), (), status, code, "", stderr[:200], 0.0
        )


def _run(policy: Policy, fixture_name: str):
    return run_case(_FIXTURES[fixture_name].case, PythonTarfilePolicyExtractor(policy))


def test_fully_trusted_tarfile_aliases_external_sentinel_c1_and_c2() -> None:
    """Affected policy: the ``..`` hardlink makes an extract/ object share the sentinel inode."""
    result = _run("fully_trusted", "c1")
    assert result.execution.status == ExecutionStatus.SUCCESS
    assert "node" not in result.execution.target_id
    c0, c1, c2 = result.violations
    assert not c0.violated
    assert c1.violated and c2.violated
    (identity,) = c1.evidence
    assert isinstance(identity, IdentityEvidence)
    assert (identity.internal_path, identity.sentinel_path) == (
        "extract/alias",
        "outside/sentinel.txt",
    )


def test_data_filter_rejects_the_external_hardlink_with_no_violation() -> None:
    """Hardened policy: the ``..`` hardlink is rejected, so no boundary violation remains."""
    result = _run("data", "c1")
    assert result.execution.status == ExecutionStatus.REJECTED
    assert tuple(verdict.violated for verdict in result.violations) == (False, False, False)


@pytest.mark.parametrize("policy", ["fully_trusted", "data"])
def test_internal_hardlink_baseline_is_clean_under_both_policies(policy: Policy) -> None:
    """An internal a.txt<->b.txt hardlink (both inside extract/) is never a violation."""
    result = _run(policy, "normal")
    assert tuple(verdict.violated for verdict in result.violations) == (False, False, False)
