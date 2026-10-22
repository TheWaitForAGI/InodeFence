"""Linux controller entry for one Track A plan freeze or campaign cell."""

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path
from uuid import uuid4

from inodefence.evaluation.encoding import json_bytes
from inodefence.evaluation.track_a_exploratory import (
    AFFECTED_IMAGE_ID,
    FIXED_IMAGE_ID,
    execute_track_a_slot,
    read_track_a_execution,
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
    parser.add_argument("--run-index", type=int)
    parser.add_argument("--execution-sha256")
    parser.add_argument("--preflight-manifest-sha256")
    parser.add_argument("--resource-authorization-sha256")
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
            "Track A prepare is disabled until verified admission transport is connected; "
            "digest-only preparation is forbidden"
        )
    parser.error(
        "Track A run-cell is disabled until admission transport and the host attempt ledger "
        "are connected"
    )


def main() -> int:
    args = _arguments()
    client = StdioDockerClient(sys.stdin, sys.stdout)
    with redirect_stdout(sys.stderr):
        backend = ContainerExecutionBackend(client, args.controller, args.volume, args.owner)
        if args.mode == "prepare":
            raise RuntimeError("unreachable disabled Track A prepare path")
        else:
            assert args.run_index is not None and args.execution_sha256 is not None
            snapshot = read_track_a_execution(
                args.evidence, expected_execution_sha256=args.execution_sha256
            )
            if not 0 <= args.run_index < len(snapshot.repetitions.plan.runs):
                raise ValueError("Track A run index is outside the frozen schedule")
            scheduled = snapshot.repetitions.plan.runs[args.run_index]
            image = args.image[1] if scheduled.arm_id == "fixed-b3" else args.image[0]
            target = NodeTarTarget.bind(backend, image, timeout_seconds=5.0)
            execute_track_a_slot(
                args.evidence,
                args.run_index,
                target,
                attempt_id=f"{scheduled.run_id}-{uuid4().hex}",
                expected_execution_sha256=args.execution_sha256,
                repository=Path.cwd(),
            )
            completed = read_track_a_execution(
                args.evidence, expected_execution_sha256=args.execution_sha256
            )
            slot = completed.repetitions.slots[args.run_index]
            result = {
                "classification": "track-a-cell-terminal-v1",
                "run_index": slot.run_index,
                "run_id": slot.run_id,
                "state": slot.state.value,
                "completed_steps": slot.completed_steps,
                "controller_memory_sha256": slot.controller_memory_sha256,
            }
        print(json_bytes(result).decode("ascii"), file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
