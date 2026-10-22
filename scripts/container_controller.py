"""Linux controller entry; explicit host broker, no socket/CLI inside controller."""

import argparse
import base64
import json
import math
import signal
import subprocess
import sys
from contextlib import redirect_stdout
from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.execution import ContainerExecutionBackend, StdioDockerClient


class IntegrationFixtures:
    def __init__(
        self, backend: ContainerExecutionBackend, image: str, evidence: Path | None
    ) -> None:
        self.backend = backend
        self.image = image
        self.evidence = evidence

    @pytest.fixture
    def container_backend(self):
        return self.backend

    @pytest.fixture
    def container_image(self):
        return self.image

    @pytest.fixture
    def campaign_evidence(self):
        assert self.evidence is not None
        return self.evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--image", required=True, action="append")
    parser.add_argument("--evidence", type=Path)
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
            "preflight-node-n05-5s-v2",
        ),
    )
    args = parser.parse_args()
    evidence_modes = {
        "benign-node-smoke",
        "qualify-node-effect-v2",
        "qualify-node-n01",
        "preflight-node-n04-5s",
        "preflight-node-n05-5s-v2",
    }
    if (args.mode in evidence_modes) != (args.evidence is not None):
        parser.error("evidence mode requires --evidence; validation modes do not export")
    pair_mode = args.mode in {
        "qualify-node-n01",
        "preflight-node-n04-5s",
        "preflight-node-n05-5s-v2",
    }
    expected_images = 2 if pair_mode else 1
    if len(args.image) != expected_images:
        parser.error(f"{args.mode} requires exactly {expected_images} immutable image ID(s)")
    if args.evidence is not None and (
        not args.evidence.is_absolute() or args.evidence.exists() or args.evidence.is_symlink()
    ):
        raise ValueError("evidence requires a new absolute controller destination")
    if args.mode == "preflight-node-n04-5s":
        from inodefence.evaluation.n04_preflight import ATTEMPT_CONSUMED

        if ATTEMPT_CONSUMED:
            raise RuntimeError(
                "N04 five-second preflight v1 attempt is consumed; a new Task Contract is required"
            )
    pair_initial_value = None
    if pair_mode:
        line = sys.stdin.readline(16 * 1024 * 1024)
        pair_initial_value = json.loads(line)
    client = StdioDockerClient(sys.stdin, sys.stdout)
    with redirect_stdout(sys.stderr):
        if args.mode == "preflight-node-n05-5s-v2":
            from inodefence.evaluation.encoding import decode
            from inodefence.evaluation.n05_preflight import (
                EVIDENCE_ROOT,
                EXPECTED_BUILD_FILES,
                N05BrokerAttestation,
                N05BuildContext,
                N05BuildFile,
                N05PackageTarball,
                N05PreflightRole,
                bind_targets,
                run_n05_preflight,
            )

            value = pair_initial_value
            expected_fields = {
                "n05_authorization",
                "n05_authorization_sha256",
                "n05_build_contexts",
                "n05_package_tarballs",
                "controller_deadline_seconds",
                "broker_attestation",
            }
            if not isinstance(value, dict) or set(value) != expected_fields:
                raise ValueError("missing N05 preflight initialization")
            raw_contexts = value["n05_build_contexts"]
            if not isinstance(raw_contexts, list) or len(raw_contexts) != 2:
                raise ValueError("N05 preflight requires two build contexts")
            contexts = []
            for role, raw in zip(N05PreflightRole, raw_contexts, strict=True):
                if not isinstance(raw, dict) or set(raw) != set(EXPECTED_BUILD_FILES):
                    raise ValueError("N05 build-context initialization has unexpected files")
                contexts.append(
                    N05BuildContext(
                        role,
                        tuple(
                            N05BuildFile(name, base64.b64decode(raw[name], validate=True))
                            for name in EXPECTED_BUILD_FILES
                        ),
                    )
                )
            raw_packages = value["n05_package_tarballs"]
            if not isinstance(raw_packages, list) or len(raw_packages) != 2:
                raise ValueError("N05 preflight requires two package tarballs")
            packages = (
                N05PackageTarball(
                    N05PreflightRole.AFFECTED,
                    base64.b64decode(raw_packages[0], validate=True),
                ),
                N05PackageTarball(
                    N05PreflightRole.FIXED,
                    base64.b64decode(raw_packages[1], validate=True),
                ),
            )
            authorization_content = base64.b64decode(value["n05_authorization"], validate=True)
            authorization_sha256 = value["n05_authorization_sha256"]
            if (
                not isinstance(authorization_sha256, str)
                or sha256(authorization_content).hexdigest() != authorization_sha256
            ):
                raise ValueError("N05 authorization transport binding is invalid")
            controller_deadline_seconds = value["controller_deadline_seconds"]
            if (
                not isinstance(controller_deadline_seconds, (int, float))
                or isinstance(controller_deadline_seconds, bool)
                or not math.isfinite(controller_deadline_seconds)
                or not 1 <= controller_deadline_seconds < 30 * 60
            ):
                raise ValueError("invalid N05 cooperative controller deadline")
            assert args.evidence is not None
            if args.evidence != EVIDENCE_ROOT:
                raise ValueError("N05 preflight requires its one frozen evidence destination")
            raw_broker = value["broker_attestation"]

            def n05_broker():
                return decode(N05BrokerAttestation, raw_broker)

            def n05_targets():
                backend = ContainerExecutionBackend(
                    client, args.controller, args.volume, args.owner
                )
                return bind_targets(backend, tuple(args.image))

            def n05_deadline_expired(_signum, _frame):
                raise TimeoutError("N05 controller cooperative deadline expired")

            previous_handler = signal.signal(signal.SIGALRM, n05_deadline_expired)
            signal.setitimer(signal.ITIMER_REAL, controller_deadline_seconds)
            try:
                outcome = run_n05_preflight(
                    args.evidence,
                    n05_targets,
                    tuple(contexts),
                    packages,
                    n05_broker,
                    authorization_content,
                    repository=Path.cwd(),
                )
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)
            verified = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "inodefence.evaluation.n05_preflight_reader",
                    str(args.evidence),
                    "--raw-manifest-sha256",
                    outcome.manifest_sha256,
                ),
                check=False,
                text=True,
                capture_output=True,
                timeout=120,
            )
            print(verified.stdout, end="")
            print(verified.stderr, end="", file=sys.stderr)
            terminal = json.loads(verified.stdout)
            if not isinstance(terminal, dict):
                raise ValueError("N05 reader did not emit a terminal object")
            terminal.update(
                raw_manifest_sha256=outcome.manifest_sha256,
                reader_returncode=verified.returncode,
            )
            client.writer.write(json.dumps({"terminal": terminal}, sort_keys=True) + "\n")
            client.writer.flush()
            return verified.returncode
        if args.mode == "preflight-node-n04-5s":
            from inodefence.evaluation.encoding import decode
            from inodefence.evaluation.n04_preflight import (
                EVIDENCE_ROOT,
                EXPECTED_BUILD_FILES,
                N04BrokerAttestation,
                N04BuildContext,
                N04BuildFile,
                N04PackageTarball,
                N04PreflightRole,
                bind_targets,
                run_n04_preflight,
            )

            value = pair_initial_value
            if not isinstance(value, dict) or set(value) != {
                "n04_build_contexts",
                "n04_package_tarballs",
                "controller_deadline_seconds",
                "broker_attestation",
            }:
                raise ValueError("missing N04 preflight initialization")
            raw_contexts = value["n04_build_contexts"]
            if not isinstance(raw_contexts, list) or len(raw_contexts) != 2:
                raise ValueError("N04 preflight requires two build contexts")
            contexts = []
            for role, raw in zip(N04PreflightRole, raw_contexts, strict=True):
                if not isinstance(raw, dict) or set(raw) != set(EXPECTED_BUILD_FILES):
                    raise ValueError("N04 build-context initialization has unexpected files")
                contexts.append(
                    N04BuildContext(
                        role,
                        tuple(
                            N04BuildFile(name, base64.b64decode(raw[name], validate=True))
                            for name in EXPECTED_BUILD_FILES
                        ),
                    )
                )
            raw_broker = value["broker_attestation"]
            raw_packages = value["n04_package_tarballs"]
            if not isinstance(raw_packages, list) or len(raw_packages) != 2:
                raise ValueError("N04 preflight requires two package tarballs")
            packages = (
                N04PackageTarball(
                    N04PreflightRole.AFFECTED,
                    base64.b64decode(raw_packages[0], validate=True),
                ),
                N04PackageTarball(
                    N04PreflightRole.FIXED,
                    base64.b64decode(raw_packages[1], validate=True),
                ),
            )
            controller_deadline_seconds = value["controller_deadline_seconds"]
            if (
                not isinstance(controller_deadline_seconds, (int, float))
                or isinstance(controller_deadline_seconds, bool)
                or not math.isfinite(controller_deadline_seconds)
                or not 1 <= controller_deadline_seconds < 30 * 60
            ):
                raise ValueError("invalid N04 cooperative controller deadline")
            assert args.evidence is not None
            if args.evidence != EVIDENCE_ROOT:
                raise ValueError("N04 preflight requires its one frozen evidence destination")

            def broker():
                return decode(N04BrokerAttestation, raw_broker)

            def targets():
                backend = ContainerExecutionBackend(
                    client, args.controller, args.volume, args.owner
                )
                return bind_targets(backend, tuple(args.image))

            def deadline_expired(_signum, _frame):
                raise TimeoutError("N04 controller cooperative deadline expired")

            previous_handler = signal.signal(signal.SIGALRM, deadline_expired)
            signal.setitimer(signal.ITIMER_REAL, controller_deadline_seconds)
            try:
                outcome = run_n04_preflight(
                    args.evidence,
                    targets,
                    tuple(contexts),
                    packages,
                    broker,
                    repository=Path.cwd(),
                )
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)
            verified = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "inodefence.evaluation.n04_preflight_reader",
                    str(args.evidence),
                    "--raw-manifest-sha256",
                    outcome.manifest_sha256,
                ),
                check=False,
                text=True,
                capture_output=True,
                timeout=120,
            )
            print(verified.stdout, end="")
            print(verified.stderr, end="", file=sys.stderr)
            terminal = json.loads(verified.stdout)
            if not isinstance(terminal, dict):
                raise ValueError("N04 reader did not emit a terminal object")
            terminal.update(
                raw_manifest_sha256=outcome.manifest_sha256,
                reader_returncode=verified.returncode,
            )
            client.writer.write(json.dumps({"terminal": terminal}, sort_keys=True) + "\n")
            client.writer.flush()
            return verified.returncode
        if args.mode == "qualify-node-n01":
            from inodefence.evaluation.n01 import (
                EXPECTED_BUILD_FILES,
                N01BuildContext,
                N01BuildFile,
                N01Role,
                run_n01_qualification,
            )
            from inodefence.targets.node_tar import NodeTarTarget

            value = pair_initial_value
            if not isinstance(value, dict) or set(value) != {"n01_build_contexts"}:
                raise ValueError("missing N01 build-context initialization")
            raw_contexts = value["n01_build_contexts"]
            if not isinstance(raw_contexts, list) or len(raw_contexts) != 2:
                raise ValueError("N01 requires two build contexts")
            contexts = []
            for role, raw in zip(N01Role, raw_contexts, strict=True):
                if not isinstance(raw, dict) or set(raw) != set(EXPECTED_BUILD_FILES):
                    raise ValueError("N01 build-context initialization has unexpected files")
                files = tuple(
                    N01BuildFile(name, base64.b64decode(raw[name], validate=True))
                    for name in EXPECTED_BUILD_FILES
                )
                contexts.append(N01BuildContext(role, files))

            def targets():
                backend = ContainerExecutionBackend(
                    client, args.controller, args.volume, args.owner
                )
                return (
                    NodeTarTarget.bind(backend, args.image[0], timeout_seconds=10),
                    NodeTarTarget.bind(backend, args.image[1], timeout_seconds=10),
                )

            assert args.evidence is not None
            outcome = run_n01_qualification(
                args.evidence,
                targets,
                tuple(contexts),
                repository=Path.cwd(),
            )
            verified = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "inodefence.evaluation.n01_reader",
                    str(args.evidence),
                    "--raw-manifest-sha256",
                    outcome.manifest_sha256,
                ),
                check=False,
                text=True,
                capture_output=True,
                timeout=120,
            )
            print(verified.stdout, end="")
            print(verified.stderr, end="", file=sys.stderr)
            return verified.returncode
        backend = ContainerExecutionBackend(client, args.controller, args.volume, args.owner)
        suite = {
            "validate": "check_boundary.py",
            "validate-node-image": "check_node_image.py",
            "validate-node-target": "check_node_target.py",
            "validate-node-effect-producer": "check_node_effect_producer.py",
            "qualify-node-effect-v2": "check_node_effect_qualification.py",
            "benign-node-smoke": "check_node_campaign.py",
        }[args.mode]
        return pytest.main(
            [f"tests/container_integration/{suite}", "-q", "-s", "-p", "no:cacheprovider"],
            plugins=[IntegrationFixtures(backend, args.image[0], args.evidence)],
        )


if __name__ == "__main__":
    raise SystemExit(main())
