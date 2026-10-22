"""Trusted-host broker for the separately authorized Track A pilot only."""

import argparse
import base64
import json
import selectors
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from time import monotonic
from uuid import uuid4

from inodefence.evaluation.track_a_exploratory import AFFECTED_IMAGE_ID, FIXED_IMAGE_ID
from inodefence.execution.container import OWNER_LABEL, checked, remove_owned
from inodefence.execution.docker_client import BackendError, DockerCLI

WATCHDOG_SECONDS = 7200


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--controller-worktree", required=True, type=PurePosixPath)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--image", required=True, action="append")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--run-index", type=int)
    parser.add_argument("--execution-sha256")
    parser.add_argument("--preflight-manifest-sha256")
    parser.add_argument("--resource-authorization-sha256")
    parser.add_argument("mode", choices=("prepare", "run-cell"))
    args = parser.parse_args()
    if (
        not args.controller_worktree.is_absolute()
        or ".." in args.controller_worktree.parts
        or args.controller_worktree == PurePosixPath("/workspaces/InodeFence")
    ):
        parser.error("Track A requires a separate absolute controller worktree")
    if args.image != [AFFECTED_IMAGE_ID, FIXED_IMAGE_ID]:
        parser.error("Track A requires the frozen affected/fixed image IDs in order")
    prepare = args.mode == "prepare"
    if prepare:
        parser.error(
            "Track A prepare is disabled until verified admission transport is connected; "
            "digest-only preparation is forbidden"
        )
    if args.preflight_manifest_sha256 or args.resource_authorization_sha256:
        parser.error("digest-only approval bindings are no longer accepted")
    parser.error(
        "Track A run-cell is disabled until admission transport and the host attempt ledger "
        "are connected"
    )


def main() -> int:
    args = _arguments()
    executable = shutil.which("docker")
    if executable is None:
        raise BackendError("host Docker CLI unavailable")
    client = DockerCLI(executable, args.context)
    owner = uuid4().hex
    controller = json.loads(
        checked(client.run(("container", "inspect", args.controller), 10), "controller inspect")
    )[0]
    identity = controller["Id"]
    command = (
        executable,
        "--context",
        args.context,
        "exec",
        "--interactive",
        "--user",
        "vscode",
        "--workdir",
        str(args.controller_worktree),
        identity,
        "env",
        f"PYTHONPATH={args.controller_worktree / 'src'}",
        "python3.12",
        "-m",
        "scripts.track_a_container_controller",
        "--controller",
        identity,
        "--volume",
        args.volume,
        "--owner",
        owner,
        *(argument for image in args.image for argument in ("--image", image)),
        "--evidence",
        str(args.evidence),
        *(("--run-index", str(args.run_index)) if args.run_index is not None else ()),
        *(("--execution-sha256", args.execution_sha256) if args.execution_sha256 else ()),
        args.mode,
    )
    names: set[str] = set()
    try:
        with subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        ) as process:
            assert process.stdout is not None and process.stdin is not None
            deadline = monotonic() + WATCHDOG_SECONDS if args.mode == "run-cell" else None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = None if deadline is None else deadline - monotonic()
                    if remaining is not None and remaining <= 0:
                        process.kill()
                        process.wait(timeout=10)
                        raise BackendError("Track A campaign exceeded the frozen 7200s watchdog")
                    if not selector.select(remaining):
                        process.kill()
                        process.wait(timeout=10)
                        raise BackendError("Track A campaign exceeded the frozen 7200s watchdog")
                    line = process.stdout.readline()
                    if not line:
                        break
                    request = json.loads(line)
                    if set(request) != {"args", "timeout"} or not isinstance(request["args"], list):
                        raise BackendError("malformed trusted controller request")
                    argv = tuple(request["args"])
                    if argv[:2] == ("container", "create"):
                        if f"{OWNER_LABEL}={owner}" not in argv:
                            raise BackendError("container request lacks invocation ownership")
                        names.add(argv[argv.index("--name") + 1])
                    outcome = client.run(argv, request["timeout"])
                    process.stdin.write(
                        json.dumps(
                            {
                                "returncode": outcome.returncode,
                                "stdout": base64.b64encode(outcome.stdout).decode("ascii"),
                                "stderr": base64.b64encode(outcome.stderr).decode("ascii"),
                                "timed_out": outcome.timed_out,
                                "truncated": outcome.truncated,
                            }
                        )
                        + "\n"
                    )
                    process.stdin.flush()
            return process.wait()
    finally:
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
