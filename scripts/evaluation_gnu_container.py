"""Dedicated fixed-benign GNU integration runner through the trusted stdio boundary."""

import argparse
import base64
import json
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from uuid import uuid4

from inodefence.evaluation.failure import (
    ArtifactReference,
    FailureContext,
    FailurePhase,
    failure_record,
    write_failure,
)
from inodefence.execution import ContainerExecutionBackend, StdioDockerClient
from inodefence.execution.container import OWNER_LABEL, checked, remove_owned
from inodefence.execution.docker_client import BackendError, DockerCLI
from inodefence.provenance import capture_source
from inodefence.replay.execution import verify_replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context")
    parser.add_argument("--controller", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--inside-controller", action="store_true")
    parser.add_argument("--owner")
    args = parser.parse_args()
    if not args.evidence.is_absolute():
        parser.error("evidence must be a new absolute controller path")
    if args.inside_controller:
        if args.owner is None:
            parser.error("internal invocation ownership required")
        client = StdioDockerClient(sys.stdin, sys.stdout)
        with redirect_stdout(sys.stderr):
            from tests.container_integration.evaluation_gnu_checks import run_checks

            if args.evidence.exists() or args.evidence.is_symlink():
                raise FileExistsError(args.evidence)
            source = capture_source()
            backend = ContainerExecutionBackend(client, args.controller, args.volume, args.owner)
            try:
                print(json.dumps(run_checks(backend, args.image, args.evidence), sort_keys=True))
            except Exception as error:
                if args.evidence.is_dir() and not args.evidence.is_symlink():
                    target, last, artifacts = None, None, ()
                    try:
                        replay = verify_replay(args.evidence / "original", args.evidence / "replay")
                        source, target = (
                            replay.header.provenance.source,
                            replay.header.provenance.target,
                        )
                        last = len(replay.steps) - 1 if replay.steps else None
                        artifacts = (
                            ArtifactReference(
                                "original/manifest.json", replay.header.original_manifest_sha256
                            ),
                        )
                    except (ValueError, OSError):
                        pass  # Unavailable or unverified partial files remain unavailable.
                    context = FailureContext(
                        args.evidence.name,
                        "gnu-benign-integration",
                        source,
                        target,
                        None,
                        FailurePhase.UNKNOWN,
                        last_fully_completed_step=last,
                        diagnostics=(
                            "Integration incomplete; replay records are separately verified.",
                        ),
                        artifacts=artifacts,
                    )
                    try:
                        write_failure(
                            args.evidence / "runner-failure.json", failure_record(error, context)
                        )
                    except Exception as ledger_error:
                        raise ExceptionGroup(
                            "integration and failure publication failed", [error, ledger_error]
                        ) from error
                raise
        return 0
    if args.context is None or args.owner is not None:
        parser.error("host requires explicit Docker context and generates its own owner")
    executable = shutil.which("docker")
    if executable is None:
        raise BackendError("host Docker CLI unavailable")
    docker = DockerCLI(executable, args.context)
    controller = json.loads(
        checked(docker.run(("container", "inspect", args.controller), 10), "controller inspect")
    )[0]["Id"]
    owner, names = uuid4().hex, set()
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
        controller,
        "python",
        "-m",
        "scripts.evaluation_gnu_container",
        "--inside-controller",
        "--controller",
        controller,
        "--volume",
        args.volume,
        "--owner",
        owner,
        "--image",
        args.image,
        "--evidence",
        str(args.evidence),
    )
    try:
        with subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        ) as process:
            assert process.stdin is not None and process.stdout is not None
            for line in process.stdout:
                request = json.loads(line)
                if set(request) != {"args", "timeout"} or not isinstance(request["args"], list):
                    raise BackendError("malformed trusted controller request")
                argv = tuple(request["args"])
                if argv[:2] == ("container", "create"):
                    if f"{OWNER_LABEL}={owner}" not in argv:
                        raise BackendError("container request lacks invocation ownership")
                    names.add(argv[argv.index("--name") + 1])
                outcome = docker.run(argv, request["timeout"])
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
        errors = []
        for name in names:
            try:
                remove_owned(docker, name, owner)
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("GNU benign integration cleanup failed", errors)


if __name__ == "__main__":
    raise SystemExit(main())
