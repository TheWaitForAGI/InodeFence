"""Metadata-only Node image validation; no archive campaign is authorized here."""

import json
from hashlib import sha256
from pathlib import Path

from inodefence.execution import ContainerRequest
from inodefence.runtime import disposable_sandbox


def test_pinned_node_image_identity_and_minimal_runtime(container_backend, container_image):
    with disposable_sandbox() as sandbox:
        command = (
            "/usr/local/bin/node",
            "/target/worker.cjs",
            "--identify",
            "/target/node_modules/tar",
            "/target/package-lock.json",
        )
        with container_backend.prepare(
            ContainerRequest(container_image, command, sandbox.root, 10)
        ) as prepared:
            result = prepared.execute()
            assert result.exit_code == 0, result.stderr
            assert not result.output_truncated
            metadata = json.loads(result.stdout)
            assert metadata["node_version"] == "22.22.0"
            assert metadata["tar_version"] == "7.5.22"
            for key, path in (
                ("worker_sha256", "src/inodefence/targets/_node_worker.cjs"),
                ("package_lock_sha256", "tools/node-tar/package-lock.json"),
            ):
                assert metadata[key] == sha256(Path(path).read_bytes()).hexdigest()
            assert metadata["unavailable_tools"] == ["sh", "npm", "git", "ssh", "curl", "gcc"]
            identity = prepared.identity
        assert container_backend.client.run(("container", "inspect", identity), 10).returncode != 0
    assert not sandbox.root.exists()


def test_frozen_image_runtime_and_worker_content_attestation(container_backend, container_image):
    from inodefence.targets.node_tar import NodeTarTarget

    target = NodeTarTarget.bind(container_backend, container_image)
    frozen = target.capture_isolation()
    assert frozen.policy == target.isolation_policy
    assert frozen.policy.image_id == container_image
    assert frozen.policy.network_policy == "none"
    assert frozen.policy.uid == frozen.policy.gid == 1000
    assert frozen.runtime_name == "docker-compatible"
    assert frozen.runtime_version and frozen.runtime_api_version
    assert frozen.runtime_os == "linux"
    assert frozen.runtime_architecture and frozen.image_architecture
    assert [(item.name, item.sha256) for item in frozen.artifacts] == [
        (
            "node-tar-package-lock",
            sha256(Path("tools/node-tar/package-lock.json").read_bytes()).hexdigest(),
        ),
        (
            "node-tar-worker",
            sha256(Path("src/inodefence/targets/_node_worker.cjs").read_bytes()).hexdigest(),
        ),
    ]
