from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.evaluation.encoding import json_bytes, read_json
from inodefence.evaluation.node_packaging import (
    NODE_BASE,
    NODE_VERSION,
    RUNTIME_BASE,
    build_node_release,
    prepare_node_release,
    validate_node_build,
    validate_node_release,
)

REPOSITORY = Path(__file__).resolve().parents[2]
LOCK = REPOSITORY / "tools/node-tar/package-lock.json"


def test_exact_baseline_uses_same_worker_runtime_and_lock_bytes(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    a = prepare_node_release(LOCK, first, repository=REPOSITORY)
    b = prepare_node_release(LOCK, second, repository=REPOSITORY)
    assert a == b
    assert a["tar_version"] == "7.5.22" and a["node_version"] == NODE_VERSION
    assert (first / "package-lock.json").read_bytes() == LOCK.read_bytes()
    assert (first / "worker.cjs").read_bytes() == (
        REPOSITORY / "src/inodefence/targets/_node_worker.cjs"
    ).read_bytes()
    baseline = (REPOSITORY / "tools/node-tar/Dockerfile").read_text()
    assert NODE_BASE in baseline and RUNTIME_BASE in baseline
    assert (
        a["files_sha256"]["worker.cjs"] == sha256((first / "worker.cjs").read_bytes()).hexdigest()
    )
    assert "npm ci --ignore-scripts --engine-strict" in (first / "Dockerfile").read_text()
    assert validate_node_release(first) == a
    with pytest.raises(FileExistsError):
        prepare_node_release(LOCK, first, repository=REPOSITORY)


@pytest.mark.parametrize(
    "edit",
    [
        lambda lock: lock["packages"][""]["dependencies"].update(tar="latest"),
        lambda lock: lock["packages"][""]["dependencies"].update(tar="^7.5.22"),
        lambda lock: lock["packages"]["node_modules/tar"].update(version="7.5.21"),
        lambda lock: lock["packages"]["node_modules/tar"].update(resolved="file:/host/package"),
        lambda lock: lock["packages"]["node_modules/tar"].update(integrity="sha512-invalid"),
        lambda lock: lock["packages"]["node_modules/tar"].update(link=True),
        lambda lock: lock["packages"][""].update(name=None),
        lambda lock: lock.update(requires=False),
    ],
)
def test_floating_mismatched_local_or_unchecksummed_dependencies_fail(tmp_path, edit):
    lock = read_json(LOCK.read_bytes())
    edit(lock)
    path = tmp_path / "lock.json"
    path.write_bytes(json_bytes(lock) + b"\n")
    with pytest.raises(ValueError):
        prepare_node_release(path, tmp_path / "context", repository=REPOSITORY)
    assert not (tmp_path / "context").exists()


def test_tampered_partial_or_extra_context_never_builds(tmp_path, monkeypatch):
    context = tmp_path / "context"
    prepare_node_release(LOCK, context, repository=REPOSITORY)
    original = (context / "worker.cjs").read_bytes()
    (context / "worker.cjs").write_bytes(b"changed worker")

    def forbidden(*args, **kwargs):
        raise AssertionError("unverified context reached Docker")

    monkeypatch.setattr("inodefence.evaluation.node_packaging.subprocess.run", forbidden)
    with pytest.raises(ValueError, match="checksum"):
        build_node_release(context, docker_context="unit-unused")
    (context / "worker.cjs").write_bytes(original)
    (context / "unrelated-secret").write_bytes(b"unit marker")
    with pytest.raises(ValueError, match="unexpected"):
        build_node_release(context, docker_context="unit-unused")
    (context / "unrelated-secret").unlink()
    (context / "packaging.json").unlink()
    with pytest.raises(FileNotFoundError):
        build_node_release(context, docker_context="unit-unused")


def test_completed_build_record_is_strictly_bound_to_prepared_context(tmp_path):
    context = tmp_path / "context"
    manifest = prepare_node_release(LOCK, context, repository=REPOSITORY)
    record = {
        "format": "inodefence-node-image-build",
        "schema_version": 1,
        "image_id": "sha256:" + "a" * 64,
        "image_architecture": "arm64",
        "packaging_sha256": sha256((context / "packaging.json").read_bytes()).hexdigest(),
        "tar_version": manifest["tar_version"],
        "node_version": NODE_VERSION,
        "files_sha256": manifest["files_sha256"],
        "stdout": "controlled build output",
        "stderr": "",
    }
    (context / "build.json").write_bytes(json_bytes(record) + b"\n")

    assert validate_node_build(context) == record

    record["image_id"] = "mutable-tag"
    (context / "build.json").write_bytes(json_bytes(record) + b"\n")
    with pytest.raises(ValueError, match="immutable-image contract"):
        validate_node_build(context)
