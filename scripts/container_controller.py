"""Linux controller entry; explicit host broker, no socket/CLI inside controller."""

import argparse
import sys
from contextlib import redirect_stdout

import pytest

from inodefence.execution import ContainerExecutionBackend, StdioDockerClient


class IntegrationFixtures:
    def __init__(self, backend: ContainerExecutionBackend, image: str) -> None:
        self.backend = backend
        self.image = image

    @pytest.fixture
    def container_backend(self):
        return self.backend

    @pytest.fixture
    def container_image(self):
        return self.image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("mode", choices=("validate", "validate-node-image"))
    args = parser.parse_args()
    client = StdioDockerClient(sys.stdin, sys.stdout)
    with redirect_stdout(sys.stderr):
        backend = ContainerExecutionBackend(client, args.controller, args.volume, args.owner)
        suite = "check_boundary.py" if args.mode == "validate" else "check_node_image.py"
        return pytest.main(
            [f"tests/container_integration/{suite}", "-q", "-s", "-p", "no:cacheprovider"],
            plugins=[IntegrationFixtures(backend, args.image)],
        )


if __name__ == "__main__":
    raise SystemExit(main())
