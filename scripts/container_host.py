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
from uuid import uuid4

from inodefence.execution.container import OWNER_LABEL, checked, remove_owned
from inodefence.execution.docker_client import BackendError, DockerCLI


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("mode", choices=("validate", "validate-node-image"))
    args = parser.parse_args()
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
        "--image",
        args.image,
        args.mode,
    )
    try:
        with subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        ) as process:
            assert process.stdout is not None and process.stdin is not None
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
            return process.wait()
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
