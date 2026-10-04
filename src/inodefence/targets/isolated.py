"""Composition of target-specific invocation with an enforced execution backend."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol, final

from inodefence.execution.base import (
    ContainerOutcome,
    ContainerRequest,
    ExecutionBackend,
    OutputLimitError,
)
from inodefence.model import ExecutionResult
from inodefence.model.isolation import ArtifactDigest, IsolationPolicy, IsolationProvenance
from inodefence.model.provenance import ExecutionSafety, TargetProvenance

from ._paths import validate_run_paths


class TargetInvocation(Protocol):
    """WHAT to execute and classify; no process/container lifecycle or Oracle."""

    @property
    def image_id(self) -> str: ...

    @property
    def provenance(self) -> TargetProvenance: ...

    @property
    def artifacts(self) -> tuple[ArtifactDigest, ...]: ...

    def command(self, archive_path: Path, extraction_root: Path) -> tuple[str, ...]: ...

    def classify(self, outcome: ContainerOutcome, command: tuple[str, ...]) -> ExecutionResult: ...


@final
@dataclass(frozen=True, slots=True)
class IsolatedTarget:
    """The public executable adapter; descriptors cannot supply a direct fallback."""

    invocation: TargetInvocation
    backend: ExecutionBackend

    def __post_init__(self) -> None:
        if not isinstance(self.backend, ExecutionBackend):
            raise ValueError("target requires a trusted ExecutionBackend implementation")
        if self.provenance.execution_safety != ExecutionSafety.ISOLATION_REQUIRED:
            raise ValueError("contained targets cannot downgrade isolation requirement")
        timeout = self.provenance.timeout_seconds
        if timeout is None or timeout > 120:
            raise ValueError("isolated target requires a bounded timeout of at most 120 seconds")
        self.backend.validate_image(self.invocation.image_id)

    @property
    def provenance(self) -> TargetProvenance:
        return self.invocation.provenance

    @property
    def isolation_policy(self) -> IsolationPolicy:
        policy = self.backend.policy(self.invocation.image_id)
        if policy.image_id != self.invocation.image_id:
            raise ValueError("backend policy image identity differs from target invocation")
        return policy

    def capture_isolation(self) -> IsolationProvenance:
        captured = self.backend.capture_isolation(self.invocation.image_id)
        if captured.policy != self.isolation_policy:
            raise ValueError("backend attestation differs from configured policy")
        return replace(captured, artifacts=self.invocation.artifacts)

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
