"""Bounded diagnostics, using an unchanged reference checkout through a stdio broker.

This is neither a qualification runner nor a campaign. Target containers receive
only a fresh run subdirectory. The controller has no Docker socket. Native runs
use the reference adapter/export/reader without changing options or definitions.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
import os
import platform
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

BASELINE = "0eb527f88aa8a4015544d2f6b0eabfebe079bf18"
REFERENCE_FILES = (
    "src/inodefence/targets/_node_effect_producer.cjs",
    "src/inodefence/targets/node_tar_effect.py",
    "src/inodefence/evaluation/native_effect_evidence.py",
    "scripts/qualify_node_effect_observation.py",
    "scripts/qualify_node_causal_effects.py",
)


def encoded(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def publish(path: Path, value: Any) -> None:
    with path.open("xb") as stream:
        stream.write(value if isinstance(value, bytes) else encoded(value))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True).stdout


def verify_reference(root: Path) -> dict:
    hashes = {}
    for name in REFERENCE_FILES:
        actual = digest(root / name)
        expected = hashlib.sha256(git(root, "show", f"{BASELINE}:{name}")).hexdigest()
        if actual != expected:
            raise ValueError(f"reference differs from frozen baseline: {name}")
        hashes[name] = actual
    # Generic code must also match the baseline; diagnostic work lives outside src/.
    if git(root, "diff", BASELINE, "--", "src", "scripts/qualify_node*"):
        raise ValueError("reference core/qualification delta is not allowed")
    return hashes


def cases(model: Any) -> list[dict]:
    entry, kind, case = model.ArchiveEntry, model.EntryType, model.ArchiveCase

    def file(name: str, content: bytes) -> Any:
        return entry(name, kind.REGULAR, content=content)

    def link(name: str, target: str) -> Any:
        return entry(name, kind.HARDLINK, link_target=target)

    values = [
        ("duplicate-default", (file("duplicate", b"first"), file("duplicate", b"second")), {}, {}),
        ("file-directory", (file("p", b"first"), entry("p", kind.DIRECTORY)), {}, {}),
        (
            "file-symlink",
            (
                file("safe", b"safe"),
                file("p", b"first"),
                entry("p", kind.SYMLINK, link_target="safe"),
            ),
            {},
            {},
        ),
        (
            "file-hardlink",
            (file("source", b"source"), file("p", b"first"), link("p", "source")),
            {},
            {},
        ),
        (
            "hardlink-anchor",
            (file("a", b"first"), link("alias", "a"), file("a", b"second")),
            {},
            {},
        ),
        (
            "duplicate-unlink",
            (file("duplicate", b"first"), file("duplicate", b"second")),
            {"unlink": True},
            {},
        ),
        (
            "duplicate-keep",
            (file("duplicate", b"first"), file("duplicate", b"second")),
            {"keep": True},
            {},
        ),
        (
            "nonempty-directory",
            (entry("p", kind.DIRECTORY), file("p/child", b"child"), file("p", b"second")),
            {},
            {},
        ),
        ("precreated-single", (file("p", b"second"),), {}, {"file": "p"}),
        ("precreated-hardlink", (file("p", b"second"),), {}, {"file": "p", "alias": "alias"}),
        ("precreated-symlink", (file("p", b"second"),), {}, {"symlink": "p", "file": "safe"}),
        (
            "precreated-newer",
            (file("p", b"second"),),
            {"newer": True},
            {"file": "p", "mtime": 1800000000},
        ),
    ]
    return [
        {"name": name, "case": case(tuple(entries)), "options": options, "setup": setup}
        for name, entries, options, setup in values
    ]


def independent_snapshot(root: Path) -> dict:
    """Separate Python lstat/digest observer; no target hook or held object pin."""
    objects = {}
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(parent) / name
            first = path.lstat()
            kind = (
                "regular"
                if stat.S_ISREG(first.st_mode)
                else ("directory" if stat.S_ISDIR(first.st_mode) else "symlink")
            )
            content = None
            if kind == "regular":
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    if (opened.st_dev, opened.st_ino) != (first.st_dev, first.st_ino):
                        raise ValueError("independent digest identity changed")
                    content = hashlib.file_digest(stream, "sha256").hexdigest()
                    final = os.fstat(stream.fileno())
                    if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
                        final.st_size,
                        final.st_mtime_ns,
                        final.st_ctime_ns,
                    ):
                        raise ValueError("independent digest version changed")
            last = path.lstat()
            if (
                first.st_dev,
                first.st_ino,
                first.st_nlink,
                first.st_size,
                first.st_mtime_ns,
                first.st_ctime_ns,
            ) != (
                last.st_dev,
                last.st_ino,
                last.st_nlink,
                last.st_size,
                last.st_mtime_ns,
                last.st_ctime_ns,
            ):
                raise ValueError("independent snapshot changed")
            objects[path.relative_to(root).as_posix()] = {
                "object_type": kind,
                "st_dev": first.st_dev,
                "st_ino": first.st_ino,
                "st_nlink": first.st_nlink,
                "size": first.st_size,
                "mode": stat.S_IMODE(first.st_mode),
                "content_digest": content,
                "link_target": os.readlink(path) if kind == "symlink" else None,
                "mtime_ns": first.st_mtime_ns,
                "ctime_ns": first.st_ctime_ns,
            }
    return objects


def reader_summary(verified: Any) -> dict:
    trace = verified.result.trace
    return {
        "integrity_valid": trace.integrity_valid,
        "completeness": trace.completeness.value,
        "termination": trace.termination.value,
        "manifest_sha256": verified.manifest_sha256,
        "effects": [
            {
                "ordinal": event.entry.entry_index,
                "operation": event.operation.value,
                "effect_class": event.effect_class.value,
                "paths": list(event.affected_paths),
                "start_sequence": event.start_sequence,
                "completion_sequence": event.completion_sequence,
                "outcome": event.outcome.value,
            }
            for event in trace.effect_events
        ],
        "feedback_key_count": len(verified.feedback_keys),
    }


def worker(args: argparse.Namespace) -> int:
    reference = args.reference.resolve()
    source_hashes = verify_reference(reference)
    sys.path.insert(0, str(reference / "src"))
    model = importlib.import_module("inodefence.model")
    runtime = importlib.import_module("inodefence.runtime")
    builder = importlib.import_module("inodefence.builder")
    observer = importlib.import_module("inodefence.observer")
    feedback = importlib.import_module("inodefence.feedback")
    oracle = importlib.import_module("inodefence.oracle")
    effect = importlib.import_module("inodefence.targets.node_tar_effect")
    pipeline = importlib.import_module("inodefence.effect_pipeline")
    evidence = importlib.import_module("inodefence.evaluation.native_effect_evidence")
    execution = importlib.import_module("inodefence.execution.container")
    transport = importlib.import_module("inodefence.execution.docker_client")
    base = importlib.import_module("inodefence.execution.base")
    client = transport.StdioDockerClient(sys.stdin, sys.stdout)
    backend = execution.ContainerExecutionBackend(client, args.controller, args.volume, args.owner)
    target = effect.NodeTarEffectTarget.bind(backend, args.native_image)
    backend.validate_image(args.image)
    output = args.output
    if not output.is_absolute() or output.parent != Path("/var/lib/inodefence"):
        raise ValueError("output must be a new direct child of the Linux runtime root")
    output.mkdir()
    config = {
        "baseline": BASELINE,
        "reference_head": git(reference, "rev-parse", "HEAD").decode().strip(),
        "reference_hashes": source_hashes,
        "repetitions": args.repetitions,
        "rng_seed": None,
        "timeout_seconds": 10,
        "event_bound": 256,
        "started_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "native_image": args.native_image,
        "diagnostic_image": args.image,
        "controller": args.controller,
        "volume": args.volume,
        "isolation": json.loads(model.canonical_json(target.capture_isolation())),
        "diagnostic_script_sha256": digest(Path(__file__)),
        "probe_sha256": digest(Path(__file__).with_name("replacement-probe.cjs")),
        "strace_exception": (
            "seccomp=unconfined; cap-drop ALL, uid 1000, no-new-privileges retained"
        ),
        "cases": [
            {
                "name": item["name"],
                "case": json.loads(model.canonical_json(item["case"])),
                "options": item["options"],
                "setup": item["setup"],
            }
            for item in cases(model)
        ],
    }
    publish(output / "config.json", config)
    for item in cases(model):
        profiles = ["stock", "branches", "syscalls"]
        if not item["options"]:
            profiles.append("native")
        for repetition in range(args.repetitions):
            for profile in profiles:
                run_id = f"{item['name']}-{profile}-{repetition}"
                folder = output / run_id
                folder.mkdir()
                with runtime.disposable_sandbox() as sandbox:
                    setup = item["setup"]
                    if "file" in setup:
                        (sandbox.extraction_root / setup["file"]).write_bytes(b"first")
                    if "alias" in setup:
                        os.link(
                            sandbox.extraction_root / setup["file"],
                            sandbox.extraction_root / setup["alias"],
                        )
                    if "symlink" in setup:
                        os.symlink(setup["file"], sandbox.extraction_root / setup["symlink"])
                    if "mtime" in setup:
                        os.utime(
                            sandbox.extraction_root / setup["file"],
                            (setup["mtime"], setup["mtime"]),
                        )
                    archive = builder.build_tar(item["case"])
                    sandbox.archive_path.write_bytes(archive)
                    publish(folder / "input.tar", archive)
                    native = None
                    if profile == "native":
                        prepared = target.prepare(sandbox.archive_path, sandbox.extraction_root)
                    else:
                        command = (
                            "/usr/local/bin/node",
                            "/target/replacement-probe.cjs",
                            str(sandbox.archive_path),
                            str(sandbox.extraction_root),
                            "branches" if profile == "branches" else "stock",
                            json.dumps(item["options"], sort_keys=True),
                        )
                        if profile == "syscalls":
                            command = (
                                "/usr/bin/strace",
                                "-f",
                                "-v",
                                "-yy",
                                "-s",
                                "256",
                                "-e",
                                "trace=%file,write,writev,close",
                                *command,
                            )
                        request = base.ContainerRequest(args.image, command, sandbox.root, 10)
                        # Keep the backend policy except the explicit ptrace seccomp exception.
                        if profile == "syscalls":

                            class TraceClient:
                                def run(self, argv: tuple[str, ...], timeout: float) -> Any:
                                    if argv[:2] == ("container", "create"):
                                        argv = (
                                            *argv[:2],
                                            "--security-opt",
                                            "seccomp=unconfined",
                                            *argv[2:],
                                        )
                                    return client.run(argv, timeout)

                            trace_backend = execution.ContainerExecutionBackend(
                                TraceClient(), args.controller, args.volume, args.owner
                            )
                            prepared = trace_backend.prepare(request)
                        else:
                            prepared = backend.prepare(request)
                    with prepared as execute:
                        before = observer.capture_state(
                            sandbox.root, model.SnapshotPhase.BEFORE, sandbox.protected_paths
                        )
                        independent_before = independent_snapshot(sandbox.root)
                        if profile == "native":
                            capture = execute()
                            outcome = capture.execution
                            raw_stdout = capture.raw_stream
                            raw_stderr = outcome.stderr.encode()
                            returncode = outcome.exit_code
                        else:
                            outcome = execute.execute()
                            raw_stdout, raw_stderr = outcome.stdout, outcome.stderr
                            returncode = outcome.exit_code
                        independent_after = independent_snapshot(sandbox.root)
                        after = observer.capture_state(
                            sandbox.root, model.SnapshotPhase.AFTER, sandbox.protected_paths
                        )
                        if profile == "native":
                            result = model.RunResult(
                                item["case"],
                                hashlib.sha256(archive).hexdigest(),
                                builder.BUILDER_FORMAT,
                                outcome,
                                before,
                                after,
                                observer.compare_states(before, after),
                                feedback.state_signature(before, after),
                                oracle.evaluate_contracts(before, after),
                            )
                            trace = effect.effect_trace_from_capture(
                                capture, target, item["case"], before, after
                            )
                            native = pipeline.NativeEffectRun(
                                model.EffectRunResult(result, trace),
                                raw_stdout,
                                capture.expected_archive_sha256,
                                capture.controller_flush_verified,
                                capture.transport_error,
                            )
                    # All evidence publication follows AFTER; no evidence enters the observed tree.
                    publish(folder / "stdout.bin", raw_stdout)
                    publish(folder / "stderr.bin", raw_stderr)
                    publish(folder / "before.json", independent_before)
                    publish(folder / "after.json", independent_after)
                    result_meta = {
                        "run_id": run_id,
                        "profile": profile,
                        "options": item["options"],
                        "setup": setup,
                        "archive_sha256": hashlib.sha256(archive).hexdigest(),
                        "case_id": item["case"].case_id,
                        "returncode": returncode,
                        "sandbox_root": str(sandbox.root),
                        "status": "process_returned",
                        "command": list(outcome.command) if profile == "native" else list(command),
                    }
                    if native is not None:
                        manifest_hash = evidence.export_native_effect_run(native, folder / "native")
                        verified = evidence.verify_native_effect_evidence(
                            folder / "native", expected_manifest_sha256=manifest_hash
                        )
                        publish(folder / "reader.json", reader_summary(verified))
                        result_meta["flush_verified"] = native.controller_flush_verified
                        result_meta["transport_error"] = native.transport_error
                    publish(folder / "run.json", result_meta)
                print(f"retained {run_id}: exit={returncode}", file=sys.stderr, flush=True)
    publish(output / "completed.json", {"completed_utc": datetime.now(UTC).isoformat()})
    return 0


def audit(args: argparse.Namespace) -> int:
    verify_reference(args.reference.resolve())
    sys.path.insert(0, str(args.reference.resolve() / "src"))
    evidence = importlib.import_module("inodefence.evaluation.native_effect_evidence")
    entries = []
    for path in sorted(args.output.iterdir()):
        if not path.is_dir():
            continue
        meta = json.loads((path / "run.json").read_bytes())
        if digest(path / "input.tar") != meta["archive_sha256"]:
            raise ValueError("TAR digest differs from retained run")
        if meta["profile"] == "native":
            verified = evidence.verify_native_effect_evidence(path / "native")
            current = reader_summary(verified)
            if current != json.loads((path / "reader.json").read_bytes()):
                raise ValueError("fresh reader differs from retained reader")
            for phase in ("before", "after"):
                independent = json.loads((path / f"{phase}.json").read_bytes())
                observed = getattr(verified.result.base_result, phase)
                # The separate observer records root contents; the canonical
                # observer additionally records the sandbox root itself as '.'.
                if set(independent) != {obj.path for obj in observed.objects if obj.path != "."}:
                    raise ValueError("independent snapshot paths differ from native snapshot")
                for obj in observed.objects:
                    if obj.path == ".":
                        continue
                    for field in (
                        "st_dev",
                        "st_ino",
                        "st_nlink",
                        "size",
                        "mode",
                        "content_digest",
                        "mtime_ns",
                        "ctime_ns",
                    ):
                        if independent[obj.path][field] != getattr(obj, field):
                            raise ValueError(
                                f"independent snapshot differs: {phase}/{obj.path}/{field}"
                            )
                    if independent[obj.path]["object_type"] != obj.object_type.value:
                        raise ValueError("independent object type differs")
                    if independent[obj.path]["link_target"] != obj.symlink_target:
                        raise ValueError("independent symlink text differs")
            entries.append({"run_id": meta["run_id"], **current})
    publish(args.audit_output, {"fresh_verified_native_runs": len(entries), "runs": entries})
    return 0


def host(args: argparse.Namespace) -> int:
    """Broker only trusted worker JSON requests; target output stays base64 data."""
    owner = uuid4().hex
    command = [
        "docker",
        "exec",
        "-i",
        "--user",
        "1000:1000",
        args.controller,
        "python",
        "/workspaces/InodeFence/tools/node-tar/diagnostics/investigate.py",
        "worker",
        "--controller",
        args.controller,
        "--volume",
        args.volume,
        "--image",
        args.image,
        "--native-image",
        args.native_image,
        "--reference",
        str(args.reference),
        "--output",
        str(args.output),
        "--owner",
        owner,
        "--repetitions",
        str(args.repetitions),
    ]
    log = args.broker_log
    with log.open("x", encoding="utf-8") as retained:
        with subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        ) as process:
            assert process.stdin is not None and process.stdout is not None
            for line in process.stdout:
                request = json.loads(line)
                argv = request["args"]
                if argv[:2] == ["container", "create"]:
                    if f"org.inodefence.execution-owner={owner}" not in argv:
                        raise ValueError("target request lacks broker ownership")
                elif argv[:2] in (["container", "rm"], ["container", "kill"]):
                    # Backend resolves created names to immutable IDs before removal.
                    info = subprocess.run(
                        ["docker", "container", "inspect", argv[-1]],
                        capture_output=True,
                        check=False,
                    )
                    if info.returncode == 0:
                        labels = json.loads(info.stdout)[0]["Config"].get("Labels") or {}
                        if labels.get("org.inodefence.execution-owner") != owner:
                            raise ValueError("refusing removal outside this invocation")
                started = monotonic()
                try:
                    result = subprocess.run(
                        ["docker", *argv],
                        capture_output=True,
                        timeout=request["timeout"],
                        check=False,
                    )
                    response = {
                        "returncode": result.returncode,
                        "stdout": base64.b64encode(result.stdout).decode(),
                        "stderr": base64.b64encode(result.stderr).decode(),
                        "timed_out": False,
                        "truncated": False,
                    }
                except subprocess.TimeoutExpired as error:
                    response = {
                        "returncode": -1,
                        "stdout": base64.b64encode(error.stdout or b"").decode(),
                        "stderr": base64.b64encode(error.stderr or b"").decode(),
                        "timed_out": True,
                        "truncated": False,
                    }
                retained.write(
                    json.dumps(
                        {
                            "request": request,
                            "response": response,
                            "duration_seconds": monotonic() - started,
                        }
                    )
                    + "\n"
                )
                retained.flush()
                process.stdin.write(json.dumps(response) + "\n")
                process.stdin.flush()
            return process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "worker", "audit"))
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--controller")
    parser.add_argument("--volume")
    parser.add_argument("--image")
    parser.add_argument("--native-image")
    parser.add_argument("--owner")
    parser.add_argument("--broker-log", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--repetitions", type=int, default=2, choices=(1, 2, 3))
    args = parser.parse_args()
    if args.mode == "audit":
        if args.audit_output is None:
            parser.error("audit requires a new --audit-output file")
        return audit(args)
    if not all((args.controller, args.volume, args.image, args.native_image)):
        parser.error("run/worker require controller, volume and both immutable image IDs")
    if args.mode == "worker":
        return worker(args)
    if args.broker_log is None:
        parser.error("run requires a new --broker-log file")
    return host(args)


if __name__ == "__main__":
    raise SystemExit(main())
