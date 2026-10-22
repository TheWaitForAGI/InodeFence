"""Linux controller entry for one Track A plan freeze or campaign cell."""

import argparse
import sys
from contextlib import redirect_stdout
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from inodefence.evaluation.encoding import json_bytes
from inodefence.evaluation.failure import ArtifactReference
from inodefence.evaluation.track_a_exploratory import (
    AFFECTED_IMAGE_ID,
    FIXED_IMAGE_ID,
    execute_track_a_slot,
    read_track_a_execution,
)
from inodefence.evaluation.track_a_host_ledger import (
    TrackAControllerTerminal,
    read_track_a_host_attempt_started,
)
from inodefence.execution import ContainerExecutionBackend, StdioDockerClient
from inodefence.targets.node_tar import NodeTarTarget


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--image", required=True, action="append")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--host-ledger", type=Path)
    parser.add_argument("--host-started-sha256")
    parser.add_argument("--attempt-id")
    parser.add_argument("--run-index", type=int)
    parser.add_argument("--execution-sha256")
    parser.add_argument("--protocol-config", type=Path)
    parser.add_argument("mode", choices=("prepare", "run-cell"))
    args = parser.parse_args()
    if Path.cwd().resolve() == Path("/workspaces/InodeFence").resolve():
        parser.error("Track A cannot run from the primary controller checkout")
    if args.image != [AFFECTED_IMAGE_ID, FIXED_IMAGE_ID]:
        parser.error("Track A requires the frozen affected/fixed image IDs in order")
    if not args.evidence.is_absolute() or args.evidence.is_symlink():
        parser.error("Track A evidence must be an absolute nonsymlink path")
    if args.mode == "prepare":
        parser.error(
            "Track A prepare is not a controller transport; freeze requires a live admission "
            "in the validating process"
        )
    if (
        args.run_index is None
        or args.execution_sha256 is None
        or args.host_ledger is None
        or args.host_started_sha256 is None
        or args.attempt_id is None
        or args.protocol_config is None
    ):
        parser.error("Track A run-cell requires the complete host attempt binding")
    for path, label in (
        (args.host_ledger, "host ledger"),
        (args.protocol_config, "protocol config"),
    ):
        if not path.is_absolute() or path.is_symlink():
            parser.error(f"Track A {label} must be an absolute nonsymlink path")
    return args


def main() -> int:
    args = _arguments()
    broker_stdout = sys.stdout
    with redirect_stdout(sys.stderr):
        assert args.run_index is not None
        assert args.execution_sha256 is not None
        assert args.host_ledger is not None
        assert args.host_started_sha256 is not None
        assert args.attempt_id is not None
        assert args.protocol_config is not None
        host_attempt, snapshot = read_track_a_host_attempt_started(
            args.host_ledger,
            args.run_index,
            expected_started_sha256=args.host_started_sha256,
            protocol_config_path=args.protocol_config,
        )
        if host_attempt.attempt_id != args.attempt_id:
            raise ValueError("controller attempt ID differs from the host-published attempt")
        if host_attempt.execution_sha256 != args.execution_sha256:
            raise ValueError("controller execution digest differs from the host attempt")
        authorization = snapshot.admission.pilot_authorization
        if (
            args.controller != authorization.controller_id
            or args.volume != authorization.runtime_volume_name
            or args.image != [item.image_id for item in authorization.targets]
            or args.evidence != Path(host_attempt.output_root)
        ):
            raise ValueError("controller launch inputs differ from the admitted host attempt")
        client = StdioDockerClient(sys.stdin, broker_stdout)
        backend = ContainerExecutionBackend(client, args.controller, args.volume, args.owner)
        scheduled = snapshot.repetitions.plan.runs[args.run_index]
        image = args.image[1] if scheduled.arm_id == "fixed-b3" else args.image[0]
        target = NodeTarTarget.bind(backend, image, timeout_seconds=5.0)
        execute_track_a_slot(
            args.evidence,
            args.run_index,
            target,
            host_attempt=host_attempt,
            expected_execution_sha256=args.execution_sha256,
            repository=Path.cwd(),
            protocol_config_path=args.protocol_config,
        )
        completed = read_track_a_execution(
            args.evidence,
            expected_execution_sha256=args.execution_sha256,
            protocol_config_path=args.protocol_config,
        )
        slot = completed.repetitions.slots[args.run_index]
        if slot.claim is None or slot.terminal is None or slot.controller_memory_sha256 is None:
            raise ValueError("successful Track A controller lacks terminal campaign evidence")
        campaign_root = args.evidence / "repetitions" / slot.result_directory
        result = TrackAControllerTerminal(
            host_attempt.attempt_id,
            slot.run_index,
            slot.run_id,
            completed.execution_sha256,
            completed.repetitions.plan_sha256,
            slot.state,
            slot.completed_steps,
            ArtifactReference(
                f"repetitions/{slot.result_directory}/claim.json",
                sha256((campaign_root / "claim.json").read_bytes()).hexdigest(),
            ),
            ArtifactReference(
                f"repetitions/{slot.result_directory}/terminal.json",
                sha256((campaign_root / "terminal.json").read_bytes()).hexdigest(),
            ),
            slot.controller_memory_sha256,
        )
    print(json_bytes({"terminal": asdict(result)}).decode("ascii"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
