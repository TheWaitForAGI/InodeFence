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
    freeze_track_a_execution,
    read_track_a_execution,
)
from inodefence.execution import ContainerExecutionBackend, StdioDockerClient
from inodefence.model.provenance import ExecutionProvenance
from inodefence.provenance import capture_environment, capture_source, sentinel_provenance
from inodefence.runtime import SentinelSpec
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
        if args.evidence.exists():
            parser.error("Track A preparation requires a new evidence root")
        if not args.preflight_manifest_sha256 or not args.resource_authorization_sha256:
            parser.error("Track A preparation lacks approval/preflight digest binding")
        if args.run_index is not None or args.execution_sha256 is not None:
            parser.error("Track A preparation cannot select a campaign")
    else:
        if not args.evidence.is_dir():
            parser.error("Track A cell requires its existing evidence root")
        if args.run_index is None or args.execution_sha256 is None:
            parser.error("Track A cell lacks its run index/execution digest")
        if args.preflight_manifest_sha256 or args.resource_authorization_sha256:
            parser.error("Track A cell cannot replace frozen approval bindings")
    return args


def main() -> int:
    args = _arguments()
    client = StdioDockerClient(sys.stdin, sys.stdout)
    with redirect_stdout(sys.stderr):
        backend = ContainerExecutionBackend(client, args.controller, args.volume, args.owner)
        if args.mode == "prepare":
            source = capture_source(Path.cwd())
            environment = capture_environment()
            sentinels = sentinel_provenance((SentinelSpec(),))
            affected = NodeTarTarget.bind(backend, args.image[0], timeout_seconds=5.0)
            fixed = NodeTarTarget.bind(backend, args.image[1], timeout_seconds=5.0)
            assert args.preflight_manifest_sha256 and args.resource_authorization_sha256
            frozen = freeze_track_a_execution(
                args.evidence,
                ExecutionProvenance(
                    source,
                    environment,
                    affected.provenance,
                    sentinels,
                    affected.capture_isolation(),
                ),
                ExecutionProvenance(
                    source,
                    environment,
                    fixed.provenance,
                    sentinels,
                    fixed.capture_isolation(),
                ),
                preflight_manifest_sha256=args.preflight_manifest_sha256,
                resource_authorization_sha256=args.resource_authorization_sha256,
            )
            result = {
                "classification": "track-a-frozen-pre-execution-v1",
                "execution_sha256": frozen.execution_sha256,
                "plan_sha256": frozen.repetitions.plan_sha256,
            }
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
