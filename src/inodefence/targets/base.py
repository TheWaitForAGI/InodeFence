"""Target execution interface; filesystem observation belongs to the runner."""

from pathlib import Path
from typing import Protocol

from inodefence.model import ExecutionResult


class TargetAdapter(Protocol):
    """Implementations own invocation/version/options and execution classification.

    Return after the target has stopped, including on timeout. Unexpected harness
    failures raise; archive rejection and target failure return ExecutionResult.
    An adapter for an unsafe target must supply adequate process/filesystem
    isolation; a disposable directory alone does not restrict its OS privileges.
    """

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult: ...
