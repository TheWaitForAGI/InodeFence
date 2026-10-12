"""Linux controller entry; explicit host broker, no socket/CLI inside controller."""

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from inodefence.execution import ContainerExecutionBackend, StdioDockerClient


class IntegrationFixtures:
    def __init__(
        self, backend: ContainerExecutionBackend, images: tuple[str, ...], evidence: Path | None
    ) -> None:
        self.backend = backend
        self.images = images
        self.evidence = evidence

    @pytest.fixture
    def container_backend(self):
        return self.backend

    @pytest.fixture
    def container_image(self):
        assert len(self.images) == 1
        return self.images[0]

    @pytest.fixture
    def container_images(self):
        return self.images

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
            "benign-node-smoke",
            "qualify-node-n01",
        ),
    )
    args = parser.parse_args()
    exports = args.mode in {"benign-node-smoke", "qualify-node-n01"}
    if exports != (args.evidence is not None):
        parser.error("selected execution mode and --evidence do not match")
    expected_images = 2 if args.mode == "qualify-node-n01" else 1
    if len(args.image) != expected_images:
        parser.error(f"{args.mode} requires exactly {expected_images} image(s)")
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
            "benign-node-smoke": "check_node_campaign.py",
            "qualify-node-n01": "qualify_node_n01.py",
        }[args.mode]
        return pytest.main(
            [f"tests/container_integration/{suite}", "-q", "-s", "-p", "no:cacheprovider"],
            plugins=[IntegrationFixtures(backend, tuple(args.image), args.evidence)],
        )


if __name__ == "__main__":
    raise SystemExit(main())
