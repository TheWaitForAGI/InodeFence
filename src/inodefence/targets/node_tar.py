"""node-tar integration for explicitly controlled benign fixtures only today."""

import json
import math
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from inodefence.model import ExecutionResult, ExecutionStatus
from inodefence.model.provenance import TargetProvenance

from ._paths import validate_run_paths
from ._process import run_process

WORKER = Path(__file__).with_name("_node_worker.cjs")


def _identify(node: str, module: Path, cwd: Path) -> tuple[str, str]:
    outcome = run_process((node, str(WORKER), "--identify", str(module)), cwd, 5.0)
    if outcome.exit_code != 0:
        raise ValueError("node-tar version discovery failed")
    try:
        value = json.loads(outcome.stdout)
        return value["node_version"], value["tar_version"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("node-tar version discovery returned invalid metadata") from error


@dataclass(frozen=True, slots=True)
class NodeTarTarget:
    """Pin the executable/module location and discover exact versions at setup.

    Worker options are strict=true/preservePaths=false, otherwise node-tar defaults.
    Process group cleanup is lifecycle management, never filesystem isolation.
    Campaign execution is forbidden until a validated OS boundary is implemented.
    """

    package_root: Path
    timeout_seconds: float = 10.0
    node_executable: str = "node"
    node_version: str = field(init=False)
    tar_version: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        node = shutil.which(self.node_executable)
        if node is None:
            raise ValueError("node executable unavailable")
        root = self.package_root.resolve(strict=True)
        module = root / "node_modules" / "tar"
        version, tar_version = _identify(str(Path(node).resolve()), module, root)
        for value in (version, tar_version):
            if (
                not isinstance(value, str)
                or re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", value) is None
            ):
                raise ValueError("target version must be exact semantic version text")
        object.__setattr__(self, "package_root", root)
        object.__setattr__(self, "node_executable", str(Path(node).resolve()))
        object.__setattr__(self, "node_version", version)
        object.__setattr__(self, "tar_version", tar_version)

    @property
    def provenance(self) -> TargetProvenance:
        # Never allow the caller to downgrade this third-party target's requirement.
        return TargetProvenance(
            "node-tar-strict",
            f"node={self.node_version};tar={self.tar_version}",
            self.timeout_seconds,
        )

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        validate_run_paths(archive_path, extraction_root)
        command = (
            self.node_executable,
            str(WORKER),
            str(self.package_root / "node_modules" / "tar"),
            str(archive_path),
            str(extraction_root),
            self.node_version,
            self.tar_version,
        )
        outcome = run_process(command, extraction_root, self.timeout_seconds)
        if outcome.exit_code == 3:
            raise RuntimeError("node-tar execution identity changed after setup")
        status = (
            ExecutionStatus.TIMED_OUT
            if outcome.exit_code is None
            else ExecutionStatus.SUCCESS
            if outcome.exit_code == 0
            else ExecutionStatus.REJECTED
            if outcome.exit_code == 2
            else ExecutionStatus.FAILED
        )
        declared = self.provenance
        return ExecutionResult(
            declared.target_id,
            declared.target_version,
            command,
            status,
            outcome.exit_code,
            outcome.stdout.decode("utf-8", "surrogateescape"),
            outcome.stderr.decode("utf-8", "surrogateescape"),
            outcome.duration_seconds,
            self.timeout_seconds,
        )
