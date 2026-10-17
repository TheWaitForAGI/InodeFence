"""Linux controller entry; explicit host broker, no socket/CLI inside controller."""

import argparse
import base64
import json
import subprocess
import sys
from contextlib import redirect_stdout
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
    expected_images = 2 if pair_mode else 1
    if len(args.image) != expected_images:
        parser.error(f"{args.mode} requires exactly {expected_images} immutable image ID(s)")
    if args.evidence is not None and (
        not args.evidence.is_absolute() or args.evidence.exists() or args.evidence.is_symlink()
    ):
        raise ValueError("evidence requires a new absolute controller destination")
    n01_initial_value = None
    if pair_mode:
        line = sys.stdin.readline(16 * 1024 * 1024)
        n01_initial_value = json.loads(line)
    client = StdioDockerClient(sys.stdin, sys.stdout)
    with redirect_stdout(sys.stderr):
        if args.mode == "preflight-node-n04-5s":
            from inodefence.evaluation.encoding import decode
            from inodefence.evaluation.n04_preflight import (
                EXPECTED_BUILD_FILES,
                N04BrokerAttestation,
                N04BuildContext,
                N04BuildFile,
                N04PreflightRole,
                bind_targets,
                run_n04_preflight,
            )

            value = n01_initial_value
            if not isinstance(value, dict) or set(value) != {
                "n04_build_contexts",
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
            broker = decode(N04BrokerAttestation, value["broker_attestation"])
            backend = ContainerExecutionBackend(client, args.controller, args.volume, args.owner)
            assert args.evidence is not None
            outcome = run_n04_preflight(
                args.evidence,
                lambda: bind_targets(backend, tuple(args.image)),
                tuple(contexts),
                broker,
                repository=Path.cwd(),
            )
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

            value = n01_initial_value
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
