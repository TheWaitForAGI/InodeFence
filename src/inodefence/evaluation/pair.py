"""Generic side-by-side preservation of two already executed core results."""

from dataclasses import dataclass
from pathlib import Path

from inodefence.model import ArchiveCase, RunResult
from inodefence.model.provenance import ExecutionProvenance

from .storage import read_record, write_record
from .verify import verify_binding, verify_run


@dataclass(frozen=True, slots=True)
class PairArm:
    provenance: ExecutionProvenance
    result: RunResult

    def __post_init__(self) -> None:
        if not isinstance(self.result, RunResult) or not isinstance(
            self.provenance, ExecutionProvenance
        ):
            raise ValueError("pair arm requires raw run and execution provenance")
        verify_run(self.result)
        verify_binding(self.result, self.provenance)


@dataclass(frozen=True, slots=True)
class PairComparison:
    """No winner, expected violation, CVE or target-specific comparison policy.

    Logical input and TAR identities must agree. Provenance, statuses and
    observed outcomes may differ; no difference is rewritten or hidden.
    """

    case_id: str
    archive_sha256: str
    builder_format: str
    a: PairArm
    b: PairArm

    def __post_init__(self) -> None:
        if not isinstance(self.a, PairArm) or not isinstance(self.b, PairArm):
            raise ValueError("pair requires two evidence arms")
        for arm in (self.a, self.b):
            result = arm.result
            if (result.case.case_id, result.archive_sha256, result.archive_format) != (
                self.case_id,
                self.archive_sha256,
                self.builder_format,
            ):
                raise ValueError("pair logical case/TAR/builder mismatch")


def compare_pair(case: ArchiveCase, a: PairArm, b: PairArm) -> PairComparison:
    """Record results from caller-owned executions; does not execute targets."""
    if case != a.result.case or case != b.result.case:
        raise ValueError("both arms must execute the requested ArchiveCase")
    return PairComparison(case.case_id, a.result.archive_sha256, a.result.archive_format, a, b)


def export_pair(pair: PairComparison, path: Path) -> str:
    """Return whole-file SHA-256; existing destinations are never overwritten."""
    if not isinstance(pair, PairComparison):
        raise ValueError("expected a PairComparison")
    return write_record(path, pair)


def read_pair(path: Path, *, expected_sha256: str | None = None) -> PairComparison:
    return read_record(path, PairComparison, expected_sha256=expected_sha256)
