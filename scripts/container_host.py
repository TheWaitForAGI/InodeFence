"""Explicit host-side trusted broker for an existing Linux controller.

Only Docker argv crosses this stdio channel. Target streams are returned as
base64 data, never interpreted as broker requests. No listening service/socket
is installed in the Dev Container. Requires Python 3.12 with the project installed.
"""

import argparse
import base64
import json
import shutil
import subprocess
import threading
from pathlib import Path
from time import monotonic
from uuid import uuid4

from inodefence.execution.container import OWNER_LABEL, checked, remove_owned
from inodefence.execution.docker_client import BackendError, DockerCLI


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--image", required=True, action="append")
    parser.add_argument(
        "--build-context",
        type=Path,
        action="append",
        default=[],
        help="affected then fixed prepared context; N01 qualification only",
    )
    parser.add_argument(
        "--evidence", type=Path, help="new absolute output path inside trusted Linux controller"
    )
    parser.add_argument(
        "mode",
        choices=(
            "validate",
            "validate-node-image",
            "validate-node-target",
            "validate-node-effect-producer",
            "qualify-node-effect-v2",
            "benign-node-smoke",
            "qualify-node-n01",
            "preflight-node-n04-5s",
        ),
    )
    args = parser.parse_args()
    evidence_modes = {
        "benign-node-smoke",
        "qualify-node-effect-v2",
        "qualify-node-n01",
        "preflight-node-n04-5s",
    }
    if (args.mode in evidence_modes) != (args.evidence is not None):
        parser.error("evidence mode requires --evidence; validation modes do not export")
    pair_mode = args.mode in {"qualify-node-n01", "preflight-node-n04-5s"}
    preflight_started = monotonic() if args.mode == "preflight-node-n04-5s" else None
    expected_images = 2 if pair_mode else 1
    if len(args.image) != expected_images:
        parser.error(f"{args.mode} requires exactly {expected_images} immutable image ID(s)")
    if pair_mode != bool(args.build_context):
        parser.error("--build-context is required only for historical pair modes")
    if pair_mode and len(args.build_context) != 2:
        parser.error("historical pair mode requires affected then fixed build contexts")
    executable = shutil.which("docker")
    if executable is None:
        raise BackendError("host Docker CLI unavailable")
    client = DockerCLI(executable, args.context)
    owner = uuid4().hex
    controller = json.loads(
        checked(client.run(("container", "inspect", args.controller), 10), "controller inspect")
    )[0]
    identity = controller["Id"]
    names: set[str] = set()
    command = (
        executable,
        "--context",
        args.context,
        "exec",
        "--interactive",
        "--user",
        "vscode",
        "--workdir",
        "/workspaces/InodeFence",
        identity,
        "python",
        "-m",
        "scripts.container_controller",
        "--controller",
        identity,
        "--volume",
        args.volume,
        "--owner",
        owner,
        *(argument for image in args.image for argument in ("--image", image)),
        *(("--evidence", str(args.evidence)) if args.evidence is not None else ()),
        args.mode,
    )
    try:
        with subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        ) as process:
            assert process.stdout is not None and process.stdin is not None
            if pair_mode:
                if args.mode == "qualify-node-n01":
                    from inodefence.evaluation.n01 import EXPECTED_BUILD_FILES, FROZEN_TARGETS
                else:
                    from inodefence.evaluation.n04_preflight import (
                        EXPECTED_BUILD_FILES,
                        FROZEN_TARGETS,
                        MAX_WALL_SECONDS,
                    )
                from inodefence.evaluation.node_packaging import validate_node_build

                contexts = []
                for context, image, frozen in zip(
                    args.build_context, args.image, FROZEN_TARGETS, strict=True
                ):
                    build = validate_node_build(context)
                    if build["image_id"] != image or build["tar_version"] != frozen.tar_version:
                        raise ValueError(
                            "historical image/build-context order or identity mismatch"
                        )
                    contexts.append(
                        {
                            name: base64.b64encode((context / name).read_bytes()).decode("ascii")
                            for name in EXPECTED_BUILD_FILES
                        }
                    )
                if args.mode == "qualify-node-n01":
                    initial = {"n01_build_contexts": contexts}
                else:
                    info = json.loads(
                        checked(client.run(("info", "--format", "{{json .}}"), 10), "daemon info")
                    )
                    version = json.loads(
                        checked(
                            client.run(("version", "--format", "{{json .}}"), 10),
                            "daemon version",
                        )
                    )
                    volume = json.loads(
                        checked(
                            client.run(("volume", "inspect", args.volume), 10), "volume inspect"
                        )
                    )[0]
                    inspected_images = []
                    for image in args.image:
                        inspected = json.loads(
                            checked(client.run(("image", "inspect", image), 10), "image inspect")
                        )[0]
                        if inspected["Id"] != image:
                            raise BackendError("target image inspection differs from requested ID")
                        inspected_images.append(
                            {
                                "image_id": inspected["Id"],
                                "operating_system": inspected["Os"],
                                "architecture": inspected["Architecture"],
                                "repo_digests": sorted(inspected.get("RepoDigests") or []),
                            }
                        )
                    mounts = [
                        {
                            "mount_type": item["Type"],
                            "source": item.get("Name")
                            if item["Type"] == "volume"
                            else item["Source"],
                            "destination": item["Destination"],
                            "read_write": item["RW"],
                        }
                        for item in sorted(
                            controller["Mounts"], key=lambda item: item["Destination"]
                        )
                    ]
                    initial = {
                        "n04_build_contexts": contexts,
                        "broker_attestation": {
                            "docker_executable": executable,
                            "context_name": args.context,
                            "daemon_id": info["ID"],
                            "daemon_name": info["Name"],
                            "daemon_version": version["Server"]["Version"],
                            "daemon_api_version": version["Server"]["ApiVersion"],
                            "daemon_os": version["Server"]["Os"],
                            "daemon_architecture": version["Server"]["Arch"],
                            "controller_id": identity,
                            "controller_image_id": controller["Image"],
                            "controller_running": controller["State"]["Running"],
                            "controller_privileged": controller["HostConfig"]["Privileged"],
                            "controller_mounts": mounts,
                            "runtime_volume_name": volume["Name"],
                            "runtime_volume_mountpoint": volume["Mountpoint"],
                            "target_images": inspected_images,
                            "max_wall_seconds": MAX_WALL_SECONDS,
                        },
                    }
                process.stdin.write(json.dumps(initial) + "\n")
                process.stdin.flush()
            expired = threading.Event()
            timer = None
            if args.mode == "preflight-node-n04-5s":

                def stop_at_deadline() -> None:
                    expired.set()
                    process.kill()

                assert preflight_started is not None
                remaining = MAX_WALL_SECONDS - (monotonic() - preflight_started)
                if remaining <= 0:
                    raise TimeoutError("N04 preflight exceeded the 30-minute wall-clock limit")
                timer = threading.Timer(remaining, stop_at_deadline)
                timer.start()
            try:
                for line in process.stdout:
                    request = json.loads(line)
                    if set(request) != {"args", "timeout"} or not isinstance(request["args"], list):
                        raise BackendError("malformed trusted controller request")
                    argv = tuple(request["args"])
                    if argv[:2] == ("container", "create"):
                        if f"{OWNER_LABEL}={owner}" not in argv:
                            raise BackendError("container request lacks invocation ownership")
                        names.add(argv[argv.index("--name") + 1])
                    outcome = client.run(argv, request["timeout"])
                    response = {
                        "returncode": outcome.returncode,
                        "stdout": base64.b64encode(outcome.stdout).decode("ascii"),
                        "stderr": base64.b64encode(outcome.stderr).decode("ascii"),
                        "timed_out": outcome.timed_out,
                        "truncated": outcome.truncated,
                    }
                    process.stdin.write(json.dumps(response) + "\n")
                    process.stdin.flush()
                returncode = process.wait()
                if expired.is_set():
                    raise TimeoutError("N04 preflight exceeded the 30-minute wall-clock limit")
                return returncode
            finally:
                if timer is not None:
                    timer.cancel()
    finally:
        # Covers controller interruption/crash and uncertain create responses.
        # Inspect only names created by this invocation, and verify ownership.
        errors = []
        for name in names:
            try:
                remove_owned(client, name, owner)
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("host target cleanup failed", errors)


if __name__ == "__main__":
    raise SystemExit(main())
