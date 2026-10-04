"""Capture configuration before execution, outside the pure model layer."""

import platform
import subprocess
from hashlib import sha256
from pathlib import Path

from inodefence.model.isolation import IsolationProvenance
from inodefence.model.provenance import (
    EnvironmentProvenance,
    ExecutionProvenance,
    SentinelProvenance,
    SourceProvenance,
    TargetProvenance,
)
from inodefence.runtime import SentinelSpec


def capture_environment() -> EnvironmentProvenance:
    """Kernel/platform strings from this process; no host/user identifiers."""
    return EnvironmentProvenance(
        platform.system(), platform.release(), platform.machine(), platform.python_version()
    )


def capture_source(repository: Path | None = None) -> SourceProvenance:
    """Read Git at the source checkout root, never an unrelated enclosing repo.

    Installed distributions without .git report None. Dirty includes tracked and
    untracked nonignored files; it is not a content hash or reproducible patch.
    Git errors/timeouts report explicit unavailable provenance, never fake IDs.
    """
    root = repository if repository is not None else Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        return SourceProvenance()
    try:
        revision = subprocess.run(
            ("git", "-C", str(root), "rev-parse", "HEAD"),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ("git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout
        return SourceProvenance(revision, bool(dirty))
    except (OSError, subprocess.SubprocessError, ValueError):
        return SourceProvenance()


def sentinel_provenance(sentinels: tuple[SentinelSpec, ...]) -> tuple[SentinelProvenance, ...]:
    """Describe configured sentinel bytes, not their post-execution state."""
    if (
        not isinstance(sentinels, tuple)
        or not sentinels
        or not all(isinstance(spec, SentinelSpec) for spec in sentinels)
    ):
        raise ValueError("sentinels must be a nonempty SentinelSpec tuple")
    records = tuple(
        sorted(
            (
                SentinelProvenance(spec.name, sha256(spec.content).hexdigest(), spec.mode)
                for spec in sentinels
            ),
            key=lambda spec: spec.name,
        )
    )
    if len({record.name for record in records}) != len(records):
        raise ValueError("sentinel names must be unique")
    return records


def freeze_provenance(
    target: TargetProvenance,
    sentinels: tuple[SentinelSpec, ...],
    *,
    source: SourceProvenance | None = None,
    isolation: IsolationProvenance | None = None,
) -> ExecutionProvenance:
    """Capture exactly once before the first run; supplied source is preserved."""
    return ExecutionProvenance(
        capture_source() if source is None else source,
        capture_environment(),
        target,
        sentinel_provenance(sentinels),
        isolation,
    )
