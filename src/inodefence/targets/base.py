"""Target execution interface; filesystem observation belongs to the runner."""

from pathlib import Path
from typing import Protocol

from inodefence.model import ExecutionResult
from inodefence.model.provenance import TargetProvenance


class TargetAdapter(Protocol):
    """Implementations own invocation/version/options and execution classification.

    Return after the target has stopped, including on timeout. Unexpected harness
    failures raise; archive rejection and target failure return ExecutionResult.
    Record the configured timeout_seconds separately from duration_seconds,
    the actual monotonic elapsed process time including timeout cleanup/wait.
    Timing is raw evidence: Observer/Oracle/Feedback do not use it as a verdict
    or include it in StateSignature or ArchiveCase identity.
    An adapter for an unsafe target must supply adequate process/filesystem
    isolation; a disposable directory alone does not restrict its OS privileges.

    run is inside the BEFORE/AFTER observation window. Harness namespace writes
    (setup, logs, bookkeeping) must not occur there: return diagnostics in
    ExecutionResult. Setup belongs before BEFORE and bookkeeping after AFTER.
    Otherwise snapshots cannot distinguish harness effects from target effects.
    """

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult: ...


class CampaignTarget(TargetAdapter, Protocol):
    """Campaign adapters additionally declare stable pre-execution configuration."""

    @property
    def provenance(self) -> TargetProvenance: ...
