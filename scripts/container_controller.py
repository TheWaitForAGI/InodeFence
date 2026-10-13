"""Linux controller entry; explicit host broker, no socket/CLI inside controller."""

import argparse
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
    parser.add_argument("--image", required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "mode",
        choices=(
            "validate",
            "validate-node-image",
            "validate-node-target",
            "validate-node-effect-producer",
            "benign-node-smoke",
        ),
    )
    args = parser.parse_args()
    if (args.mode == "benign-node-smoke") != (args.evidence is not None):
        parser.error("benign-node-smoke requires --evidence; validation modes do not export")
    if args.evidence is not None and (
        not args.evidence.is_absolute() or args.evidence.exists() or args.evidence.is_symlink()
    ):
        raise ValueError("evidence requires a new absolute controller destination")
    client = StdioDockerClient(sys.stdin, sys.stdout)
    with redirect_stdout(sys.stderr):
        backend = ContainerExecutionBackend(client, args.controller, args.volume, args.owner)
        suite = {
            "validate": "check_boundary.py",
            "validate-node-image": "check_node_image.py",
            "validate-node-target": "check_node_target.py",
            "validate-node-effect-producer": "check_node_effect_producer.py",
            "benign-node-smoke": "check_node_campaign.py",
        }[args.mode]
        return pytest.main(
            [f"tests/container_integration/{suite}", "-q", "-s", "-p", "no:cacheprovider"],
            plugins=[IntegrationFixtures(backend, args.image, args.evidence)],
        )


if __name__ == "__main__":
    raise SystemExit(main())
