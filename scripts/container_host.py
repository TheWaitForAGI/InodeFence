"""Explicit host-side trusted broker for an existing Linux controller.

Only Docker argv crosses this stdio channel. Target streams are returned as
base64 data, never interpreted as broker requests. No listening service/socket
is installed in the Dev Container. Requires Python 3.12 with the project installed.
"""

import argparse
import base64
import json
import math
import os
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import uuid4

from inodefence.execution.container import OWNER_LABEL, checked, remove_owned
from inodefence.execution.docker_client import BackendError, CommandResult, DockerCLI

_ACTIVE_N04_LEDGER: "N04HostLedger | None" = None


def _exclusive_json(path: Path, value: object) -> str:
    content = (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    return sha256(content).hexdigest()


def _read_canonical_json(path: Path) -> tuple[dict, str]:
    content = path.read_bytes()
    value = json.loads(content)
    if not isinstance(value, dict) or content != (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii"):
        raise ValueError(f"noncanonical N04 host ledger file: {path.name}")
    return value, sha256(content).hexdigest()


def _validate_linux_terminal(value: object) -> dict:
    fields = {
        "final_manifest_sha256",
        "final_status",
        "host_cleanup_pending",
        "independent_status",
        "pilot_authorized",
        "preflight_verdict",
        "raw_manifest_sha256",
        "reader_returncode",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise BackendError("malformed N04 controller terminal summary")
    if (
        not all(
            isinstance(value[name], str) and re.fullmatch(r"[0-9a-f]{64}", value[name])
            for name in ("raw_manifest_sha256", "final_manifest_sha256")
        )
        or value["final_status"]
        not in {
            "PREFLIGHT_PASS",
            "PREFLIGHT_FAIL",
            "PREFLIGHT_INCONCLUSIVE",
            "INDEPENDENT_VERIFICATION_FAILED",
        }
        or value["independent_status"] not in {"PASS", "FAIL"}
        or value["preflight_verdict"] not in {"PASS", "FAIL", "INCONCLUSIVE"}
        or value["pilot_authorized"] is not False
        or value["host_cleanup_pending"] is not True
        or type(value["reader_returncode"]) is not int
        or value["reader_returncode"] not in {0, 1}
        or value["reader_returncode"] != (0 if value["independent_status"] == "PASS" else 1)
    ):
        raise BackendError("invalid N04 controller terminal summary")
    expected_final = (
        "INDEPENDENT_VERIFICATION_FAILED"
        if value["independent_status"] == "FAIL"
        else {
            "PASS": "PREFLIGHT_PASS",
            "FAIL": "PREFLIGHT_FAIL",
            "INCONCLUSIVE": "PREFLIGHT_INCONCLUSIVE",
        }[value["preflight_verdict"]]
    )
    if value["final_status"] != expected_final:
        raise BackendError("inconsistent N04 controller terminal summary")
    return value


def _validate_n04_host_inputs(
    build_contexts: tuple[Path, ...], package_tarballs: tuple[Path, ...], volume: str
) -> None:
    from inodefence.evaluation.n04_preflight import (
        HOST_BUILD_CONTEXTS,
        HOST_PACKAGE_TARBALLS,
        RUNTIME_VOLUME_NAME,
    )

    if (
        build_contexts != HOST_BUILD_CONTEXTS
        or package_tarballs != HOST_PACKAGE_TARBALLS
        or volume != RUNTIME_VOLUME_NAME
    ):
        raise ValueError("N04 preflight requires its frozen host input paths")
    for path in (*HOST_BUILD_CONTEXTS, *HOST_PACKAGE_TARBALLS):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError("N04 preflight host inputs must not use symlinks")
    if not all(path.is_dir() for path in HOST_BUILD_CONTEXTS) or not all(
        path.is_file() for path in HOST_PACKAGE_TARBALLS
    ):
        raise ValueError("N04 preflight frozen host inputs are unavailable")


class N04HostLedger:
    """Host-side one-attempt and terminal-cleanup ledger outside Docker."""

    def __init__(self, root: Path, args: argparse.Namespace) -> None:
        from inodefence.evaluation.n04_preflight import (
            EVIDENCE_ROOT,
            HOST_LEDGER_ROOT,
            MAX_WALL_SECONDS,
        )

        if root != HOST_LEDGER_ROOT or args.evidence != EVIDENCE_ROOT:
            raise ValueError("N04 preflight requires its frozen host/evidence destinations")
        root.mkdir(parents=False, exist_ok=False, mode=0o700)
        self.root = root
        self.max_wall_seconds = MAX_WALL_SECONDS
        self.started_monotonic = monotonic()
        self.started_at = datetime.now(UTC).isoformat()
        self.owner: str | None = None
        self.controller_id: str | None = None
        self.target_names: set[str] = set()
        self.deadline_expired = False
        self.cleanup_status = "not_needed"
        self.cleanup_errors: list[str] = []
        self.linux_terminal: dict | None = None
        self._finished = False
        self.started_sha256 = _exclusive_json(
            root / "started.json",
            {
                "attempt_id": "n04-five-second-preflight-20261016T130000Z",
                "controller": args.controller,
                "evidence_root": str(args.evidence),
                "host_ledger_root": str(root),
                "images": args.image,
                "mode": args.mode,
                "package_tarballs": [str(path.resolve()) for path in args.package_tarball],
                "runtime_volume": args.volume,
                "started_at": self.started_at,
            },
        )

    def finish(self, returncode: int | None, error: BaseException | None) -> None:
        if self._finished:
            return
        self._finished = True
        linux_terminal = self.linux_terminal
        elapsed_seconds = monotonic() - self.started_monotonic
        terminal_consistent = (
            linux_terminal is not None and returncode == linux_terminal["reader_returncode"]
        )
        if (
            error is None
            and elapsed_seconds <= self.max_wall_seconds
            and self.cleanup_status in {"complete", "not_needed"}
            and terminal_consistent
        ):
            assert linux_terminal is not None
            overall_status = linux_terminal["final_status"]
        else:
            overall_status = "PREFLIGHT_INCONCLUSIVE"
        terminal = {
            "attempt_id": "n04-five-second-preflight-20261016T130000Z",
            "cleanup_status": self.cleanup_status,
            "cleanup_errors": self.cleanup_errors,
            "controller_id": self.controller_id,
            "controller_returncode": returncode,
            "deadline_expired": self.deadline_expired,
            "elapsed_seconds": elapsed_seconds,
            "ended_at": datetime.now(UTC).isoformat(),
            "exception": None
            if error is None
            else f"{type(error).__module__}.{type(error).__qualname__}: {error}",
            "owner": self.owner,
            "linux_terminal": self.linux_terminal,
            "overall_status": overall_status,
            "started_at": self.started_at,
            "target_names": sorted(self.target_names),
        }
        terminal_sha256 = _exclusive_json(self.root / "terminal.json", terminal)
        _exclusive_json(
            self.root / "manifest.json",
            {
                "attempt_id": terminal["attempt_id"],
                "files": {
                    "started.json": self.started_sha256,
                    "terminal.json": terminal_sha256,
                },
                "format": "inodefence-n04-host-ledger-v1",
                "overall_status": overall_status,
            },
        )


def verify_n04_host_ledger(root: Path, linux_evidence: Path) -> dict:
    """Verify the host finalizer and its binding to copied Linux evidence."""
    from inodefence.evaluation.n04_preflight import MAX_WALL_SECONDS

    started, started_sha256 = _read_canonical_json(root / "started.json")
    terminal, terminal_sha256 = _read_canonical_json(root / "terminal.json")
    manifest, _ = _read_canonical_json(root / "manifest.json")
    started_fields = {
        "attempt_id",
        "controller",
        "evidence_root",
        "host_ledger_root",
        "images",
        "mode",
        "package_tarballs",
        "runtime_volume",
        "started_at",
    }
    terminal_fields = {
        "attempt_id",
        "cleanup_errors",
        "cleanup_status",
        "controller_id",
        "controller_returncode",
        "deadline_expired",
        "elapsed_seconds",
        "ended_at",
        "exception",
        "linux_terminal",
        "overall_status",
        "owner",
        "started_at",
        "target_names",
    }
    if (
        set(started) != started_fields
        or set(terminal) != terminal_fields
        or set(manifest) != {"attempt_id", "files", "format", "overall_status"}
        or manifest["format"] != "inodefence-n04-host-ledger-v1"
        or manifest["attempt_id"] != "n04-five-second-preflight-20261016T130000Z"
        or manifest["files"] != {"started.json": started_sha256, "terminal.json": terminal_sha256}
        or terminal.get("attempt_id") != manifest["attempt_id"]
        or started.get("attempt_id") != manifest["attempt_id"]
        or terminal.get("overall_status") != manifest["overall_status"]
        or terminal.get("cleanup_status") not in {"not_needed", "complete", "failed"}
        or not isinstance(terminal.get("cleanup_errors"), list)
        or not all(isinstance(item, str) for item in terminal["cleanup_errors"])
        or (terminal["cleanup_status"] == "failed") != bool(terminal["cleanup_errors"])
        or type(terminal.get("deadline_expired")) is not bool
        or not isinstance(terminal.get("elapsed_seconds"), (int, float))
        or isinstance(terminal.get("elapsed_seconds"), bool)
        or not math.isfinite(terminal["elapsed_seconds"])
        or terminal["elapsed_seconds"] < 0
        or terminal.get("overall_status")
        not in {
            "PREFLIGHT_PASS",
            "PREFLIGHT_FAIL",
            "PREFLIGHT_INCONCLUSIVE",
            "INDEPENDENT_VERIFICATION_FAILED",
        }
        or not isinstance(terminal.get("target_names"), list)
        or not all(isinstance(item, str) for item in terminal["target_names"])
        or terminal["target_names"] != sorted(set(terminal["target_names"]))
    ):
        raise ValueError("N04 host ledger manifest binding is invalid")
    if terminal.get("linux_terminal") is None:
        if manifest["overall_status"] != "PREFLIGHT_INCONCLUSIVE":
            raise ValueError("missing Linux terminal cannot produce an overall verdict")
        return {
            "final_manifest_sha256": None,
            "overall_status": "PREFLIGHT_INCONCLUSIVE",
            "raw_manifest_sha256": None,
        }
    linux_terminal = _validate_linux_terminal(terminal["linux_terminal"])
    for name, digest in (
        ("raw-manifest.json", linux_terminal["raw_manifest_sha256"]),
        ("manifest.json", linux_terminal["final_manifest_sha256"]),
    ):
        if sha256((linux_evidence / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"N04 host/Linux digest mismatch: {name}")
    terminal_consistent = (
        terminal.get("controller_returncode") == linux_terminal["reader_returncode"]
    )
    expected = (
        linux_terminal["final_status"]
        if terminal.get("exception") is None
        and terminal["elapsed_seconds"] <= MAX_WALL_SECONDS
        and terminal.get("cleanup_status") in {"complete", "not_needed"}
        and terminal_consistent
        else "PREFLIGHT_INCONCLUSIVE"
    )
    if manifest["overall_status"] != expected:
        raise ValueError("N04 host overall status is inconsistent")
    return {
        "final_manifest_sha256": linux_terminal["final_manifest_sha256"],
        "overall_status": expected,
        "raw_manifest_sha256": linux_terminal["raw_manifest_sha256"],
    }


class _DeadlineDockerClient:
    def __init__(self, client: DockerCLI, bound: Callable[[float], float]) -> None:
        self.client = client
        self.bound = bound

    def run(self, args: tuple[str, ...], timeout: float) -> CommandResult:
        return self.client.run(args, self.bound(timeout))


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
        help="affected then fixed prepared context; historical pair modes only",
    )
    parser.add_argument(
        "--package-tarball",
        type=Path,
        action="append",
        default=[],
        help="exact affected then fixed npm tarballs; N04 preflight only",
    )
    parser.add_argument(
        "--evidence", type=Path, help="new absolute output path inside trusted Linux controller"
    )
    parser.add_argument(
        "--host-ledger",
        type=Path,
        help="new exact host-side attempt ledger; N04 preflight only",
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
    preflight_deadline = None
    if preflight_started is not None:
        from inodefence.evaluation.n04_preflight import (
            CONTROLLER_FINALIZATION_RESERVE_SECONDS,
            HOST_CLEANUP_RESERVE_SECONDS,
            MAX_WALL_SECONDS,
        )

        preflight_deadline = preflight_started + MAX_WALL_SECONDS

    def bounded_timeout(requested: float) -> float:
        if preflight_deadline is None:
            return requested
        remaining = preflight_deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("N04 preflight exceeded the 30-minute wall-clock limit")
        return min(requested, remaining)

    expected_images = 2 if pair_mode else 1
    if len(args.image) != expected_images:
        parser.error(f"{args.mode} requires exactly {expected_images} immutable image ID(s)")
    if pair_mode != bool(args.build_context):
        parser.error("--build-context is required only for historical pair modes")
    if pair_mode and len(args.build_context) != 2:
        parser.error("historical pair mode requires affected then fixed build contexts")
    if args.mode == "preflight-node-n04-5s":
        if len(args.package_tarball) != 2:
            parser.error("N04 preflight requires affected then fixed package tarballs")
        if args.host_ledger is None:
            parser.error("N04 preflight requires --host-ledger")
        try:
            _validate_n04_host_inputs(
                tuple(args.build_context), tuple(args.package_tarball), args.volume
            )
        except ValueError as error:
            parser.error(str(error))
    elif args.package_tarball:
        parser.error("--package-tarball is restricted to the N04 preflight")
    elif args.host_ledger is not None:
        parser.error("--host-ledger is restricted to the N04 preflight")
    global _ACTIVE_N04_LEDGER
    if args.mode == "preflight-node-n04-5s":
        assert args.host_ledger is not None
        _ACTIVE_N04_LEDGER = N04HostLedger(args.host_ledger, args)
    executable = shutil.which("docker")
    if executable is None:
        raise BackendError("host Docker CLI unavailable")
    client = DockerCLI(executable, args.context)
    owner = uuid4().hex
    if _ACTIVE_N04_LEDGER is not None:
        _ACTIVE_N04_LEDGER.owner = owner
    controller = json.loads(
        checked(
            client.run(("container", "inspect", args.controller), bounded_timeout(10)),
            "controller inspect",
        )
    )[0]
    identity = controller["Id"]
    if _ACTIVE_N04_LEDGER is not None:
        _ACTIVE_N04_LEDGER.controller_id = identity
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
                    )
                from inodefence.evaluation.node_packaging import validate_node_build

                contexts = []
                for context, image, frozen in zip(
                    args.build_context, args.image, FROZEN_TARGETS, strict=True
                ):
                    if args.mode == "preflight-node-n04-5s" and any(
                        (context / name).is_symlink()
                        or (context / name).resolve().parent != context
                        for name in EXPECTED_BUILD_FILES
                    ):
                        raise ValueError("N04 build context contains a symlinked input")
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
                    assert _ACTIVE_N04_LEDGER is not None
                    info = json.loads(
                        checked(
                            client.run(("info", "--format", "{{json .}}"), bounded_timeout(10)),
                            "daemon info",
                        )
                    )
                    version = json.loads(
                        checked(
                            client.run(("version", "--format", "{{json .}}"), bounded_timeout(10)),
                            "daemon version",
                        )
                    )
                    volume = json.loads(
                        checked(
                            client.run(("volume", "inspect", args.volume), bounded_timeout(10)),
                            "volume inspect",
                        )
                    )[0]
                    volume_consumers = tuple(
                        sorted(
                            item
                            for item in checked(
                                client.run(
                                    (
                                        "container",
                                        "ls",
                                        "--all",
                                        "--no-trunc",
                                        "--filter",
                                        f"volume={args.volume}",
                                        "--format",
                                        "{{.ID}}",
                                    ),
                                    bounded_timeout(10),
                                ),
                                "runtime volume consumer inspection",
                            )
                            .decode("utf-8")
                            .splitlines()
                            if item
                        )
                    )
                    inspected_images = []
                    for image in args.image:
                        inspected = json.loads(
                            checked(
                                client.run(("image", "inspect", image), bounded_timeout(10)),
                                "image inspect",
                            )
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
                    controller_deadline_seconds = (
                        bounded_timeout(MAX_WALL_SECONDS)
                        - HOST_CLEANUP_RESERVE_SECONDS
                        - CONTROLLER_FINALIZATION_RESERVE_SECONDS
                    )
                    if controller_deadline_seconds <= 0:
                        raise TimeoutError("N04 preflight lacks finalization/cleanup reserve")
                    initial = {
                        "n04_build_contexts": contexts,
                        "n04_package_tarballs": [
                            base64.b64encode(path.read_bytes()).decode("ascii")
                            for path in args.package_tarball
                        ],
                        "controller_deadline_seconds": controller_deadline_seconds,
                        "broker_attestation": {
                            "docker_executable": executable,
                            "context_name": args.context,
                            "broker_started_at": _ACTIVE_N04_LEDGER.started_at,
                            "daemon_id": info["ID"],
                            "daemon_name": info["Name"],
                            "daemon_version": version["Server"]["Version"],
                            "daemon_api_version": version["Server"]["ApiVersion"],
                            "daemon_os": version["Server"]["Os"],
                            "daemon_architecture": version["Server"]["Arch"],
                            "controller_id": identity,
                            "controller_image_id": controller["Image"],
                            "controller_created_at": controller["Created"],
                            "controller_running": controller["State"]["Running"],
                            "controller_privileged": controller["HostConfig"]["Privileged"],
                            "controller_label": (controller["Config"].get("Labels") or {}).get(
                                "org.inodefence.n04-preflight-controller"
                            ),
                            "controller_network_mode": controller["HostConfig"]["NetworkMode"],
                            "controller_readonly_rootfs": controller["HostConfig"][
                                "ReadonlyRootfs"
                            ],
                            "controller_cap_add": sorted(
                                controller["HostConfig"].get("CapAdd") or []
                            ),
                            "controller_cap_drop": sorted(
                                controller["HostConfig"].get("CapDrop") or []
                            ),
                            "controller_security_opt": sorted(
                                controller["HostConfig"].get("SecurityOpt") or []
                            ),
                            "controller_device_count": len(
                                controller["HostConfig"].get("Devices") or []
                            ),
                            "controller_device_request_count": len(
                                controller["HostConfig"].get("DeviceRequests") or []
                            ),
                            "controller_device_cgroup_rule_count": len(
                                controller["HostConfig"].get("DeviceCgroupRules") or []
                            ),
                            "controller_pid_mode": controller["HostConfig"]["PidMode"],
                            "controller_ipc_mode": controller["HostConfig"]["IpcMode"],
                            "controller_cgroupns_mode": controller["HostConfig"]["CgroupnsMode"],
                            "controller_memory_bytes": controller["HostConfig"]["Memory"],
                            "controller_memory_swap_bytes": controller["HostConfig"]["MemorySwap"],
                            "controller_pids_limit": controller["HostConfig"]["PidsLimit"],
                            "controller_tmpfs": sorted(
                                (controller["HostConfig"].get("Tmpfs") or {}).items()
                            ),
                            "controller_mounts": mounts,
                            "runtime_volume_name": volume["Name"],
                            "runtime_volume_created_at": volume["CreatedAt"],
                            "runtime_volume_driver": volume["Driver"],
                            "runtime_volume_scope": volume["Scope"],
                            "runtime_volume_label": (volume.get("Labels") or {}).get(
                                "org.inodefence.n04-preflight-volume"
                            ),
                            "runtime_volume_options": sorted((volume.get("Options") or {}).items()),
                            "runtime_volume_mountpoint": volume["Mountpoint"],
                            "runtime_volume_container_ids": volume_consumers,
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

                assert preflight_deadline is not None
                remaining = preflight_deadline - monotonic() - HOST_CLEANUP_RESERVE_SECONDS
                if remaining <= 0:
                    raise TimeoutError("N04 preflight exhausted its controller time budget")
                timer = threading.Timer(remaining, stop_at_deadline)
                timer.start()
            try:
                terminal_seen = False
                for line in process.stdout:
                    request = json.loads(line)
                    if set(request) == {"terminal"}:
                        if (
                            args.mode != "preflight-node-n04-5s"
                            or terminal_seen
                            or _ACTIVE_N04_LEDGER is None
                        ):
                            raise BackendError("unexpected controller terminal summary")
                        _ACTIVE_N04_LEDGER.linux_terminal = _validate_linux_terminal(
                            request["terminal"]
                        )
                        terminal_seen = True
                        continue
                    if terminal_seen:
                        raise BackendError("Docker request followed controller terminal summary")
                    if set(request) != {"args", "timeout"} or not isinstance(request["args"], list):
                        raise BackendError("malformed trusted controller request")
                    argv = tuple(request["args"])
                    if argv[:2] == ("container", "create"):
                        if f"{OWNER_LABEL}={owner}" not in argv:
                            raise BackendError("container request lacks invocation ownership")
                        names.add(argv[argv.index("--name") + 1])
                        if _ACTIVE_N04_LEDGER is not None:
                            _ACTIVE_N04_LEDGER.target_names.update(names)
                            _ACTIVE_N04_LEDGER.cleanup_status = "pending"
                    outcome = client.run(argv, bounded_timeout(request["timeout"]))
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
                    if _ACTIVE_N04_LEDGER is not None:
                        _ACTIVE_N04_LEDGER.deadline_expired = True
                    raise TimeoutError("N04 preflight exceeded the 30-minute wall-clock limit")
                if args.mode == "preflight-node-n04-5s" and not terminal_seen:
                    raise BackendError("N04 controller ended without a terminal summary")
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
                remove_owned(_DeadlineDockerClient(client, bounded_timeout), name, owner)
            except Exception as error:
                errors.append(error)
                if _ACTIVE_N04_LEDGER is not None:
                    _ACTIVE_N04_LEDGER.cleanup_errors.append(
                        f"{type(error).__module__}.{type(error).__qualname__}: {error}"
                    )
        if _ACTIVE_N04_LEDGER is not None:
            _ACTIVE_N04_LEDGER.cleanup_status = (
                "failed" if errors else "complete" if names else "not_needed"
            )
        if errors:
            raise ExceptionGroup("host target cleanup failed", errors)


if __name__ == "__main__":
    try:
        exit_code = main()
    except BaseException as error:
        if _ACTIVE_N04_LEDGER is not None:
            if isinstance(error, TimeoutError):
                _ACTIVE_N04_LEDGER.deadline_expired = True
            _ACTIVE_N04_LEDGER.finish(None, error)
        raise
    else:
        if _ACTIVE_N04_LEDGER is not None:
            _ACTIVE_N04_LEDGER.finish(exit_code, None)
        raise SystemExit(exit_code)
