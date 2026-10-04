"""Composition of target-specific invocation with an enforced execution backend."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inodefence.execution.base import (
    ContainerOutcome,
    ContainerRequest,
    ExecutionBackend,
    OutputLimitError,
)
from inodefence.model import ExecutionResult
from inodefence.model.provenance import TargetProvenance

from ._paths import validate_run_paths


class TargetInvocation(Protocol):
    """WHAT to execute and classify; no process/container lifecycle or Oracle."""

    @property
    def image_id(self) -> str: ...

    @property
    def provenance(self) -> TargetProvenance: ...

    def command(self, archive_path: Path, extraction_root: Path) -> tuple[str, ...]: ...

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult: ...


@dataclass(frozen=True, slots=True)
class IsolatedTarget:
    """The public executable adapter; descriptors cannot supply a direct fallback."""

    invocation: TargetInvocation
    backend: ExecutionBackend

    def __post_init__(self) -> None:
        if not isinstance(self.backend, ExecutionBackend):
            raise ValueError("target requires a trusted ExecutionBackend implementation")
        self.backend.validate_image(self.invocation.image_id)

    @property
    def provenance(self) -> TargetProvenance:
        return self.invocation.provenance

    @contextmanager
    def prepare(
        self, archive_path: Path, extraction_root: Path
    ) -> Iterator[Callable[[], ExecutionResult]]:
        validate_run_paths(archive_path, extraction_root)
        command = self.invocation.command(archive_path, extraction_root)
        timeout = self.provenance.timeout_seconds
        if timeout is None:
            raise ValueError("isolated execution requires a bounded timeout")
        request = ContainerRequest(
            self.invocation.image_id, command, extraction_root.parent, timeout
        )
        with self.backend.prepare(request) as prepared:

            def execute() -> ExecutionResult:
                outcome = prepared.execute()
                if outcome.output_truncated:
                    raise OutputLimitError(outcome)
                return self.invocation.classify(outcome, command)

            yield execute

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        with self.prepare(archive_path, extraction_root) as execute:
            return execute()
