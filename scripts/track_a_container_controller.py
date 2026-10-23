"""Linux controller entry for one Track A plan freeze or campaign cell."""

import argparse
import base64
import json
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
    claim_track_a_controller_entry,
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
    parser.add_argument("--host-launch-sha256")
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
        or args.host_launch_sha256 is None
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


def _controller_launch_secret() -> bytes:
    line = sys.stdin.readline(1025)
    try:
        if not line.endswith("\n") or len(line) > 1024:
            raise ValueError("bounded launch frame required")
        value = json.loads(line)
        if not isinstance(value, dict) or set(value) != {"controller_launch_secret"}:
            raise ValueError("unexpected launch frame")
        encoded = value["controller_launch_secret"]
        if not isinstance(encoded, str):
            raise ValueError("launch secret must be encoded text")
        secret = base64.b64decode(encoded, validate=True)
        if len(secret) != 32:
            raise ValueError("launch secret must have exact entropy length")
        return secret
    except (ValueError, TypeError) as error:
        raise ValueError("invalid Track A live controller launch handshake") from error


def main() -> int:
    args = _arguments()
    broker_stdout = sys.stdout
    with redirect_stdout(sys.stderr):
        assert args.run_index is not None
        assert args.execution_sha256 is not None
        assert args.host_ledger is not None
        assert args.host_started_sha256 is not None
        assert args.host_launch_sha256 is not None
        assert args.attempt_id is not None
        assert args.protocol_config is not None
        launch_secret = _controller_launch_secret()
        host_attempt, _, snapshot = claim_track_a_controller_entry(
            args.host_ledger,
            args.run_index,
            expected_started_sha256=args.host_started_sha256,
            expected_launch_sha256=args.host_launch_sha256,
            expected_attempt_id=args.attempt_id,
            expected_execution_sha256=args.execution_sha256,
            controller_id=args.controller,
            runtime_volume_name=args.volume,
            image_ids=tuple(args.image),
            evidence_root=args.evidence,
            launch_secret=launch_secret,
            protocol_config_path=args.protocol_config,
        )
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
