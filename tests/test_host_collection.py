"""Host evidence tests use synthetic data and do not qualify any machine."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from scripts.collect_host_evidence import collect
from scripts.verify_host_collection import verify


def test_command_timeout_preserves_partial_evidence(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output=b"partial")

    monkeypatch.setattr(subprocess, "run", timeout)
    result = collect(["test-command"], tmp_path, "test")
    assert result["timeout"] is True
    assert result["status"] == "UNKNOWN"
    assert (tmp_path / "test.stdout").read_bytes() == b"partial"


def fixture_collection(path: Path):
    names = (
        "windows linux git_head git_status docker_version docker_info docker_context "
        "docker_images docker_containers docker_volumes host_processes output_disk "
        "wsl_version wsl_list docker_vm"
    ).split()
    outputs = {
        "git_head": "a" * 40,
        "git_status": "",
        "docker_images": json.dumps(
            [{"Id": "sha256:" + "b" * 64, "RepoTags": ["inodefence-node-tar-effect:7.5.2"]}]
        ),
        "docker_info": json.dumps({"NCPU": 4, "MemTotal": 200}),
        "output_disk": "filesystem size used available percent mount\n/dev/x 1000 10 990 1% /",
    }
    records = {}
    for name in names:
        files = {}
        for suffix, value in (("stdout", outputs.get(name, "")), ("stderr", "")):
            file = path / f"{name}.{suffix}"
            file.write_text(value)
            files[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
        records[name] = {
            "exit_code": 0,
            "timeout": False,
            "truncated": False,
            "files_sha256": files,
        }
    data = {
        "schema": "inodefence-host-collection-v1",
        "host_id": "HOST2",
        "commands": records,
        "output_exists_at_collection": False,
    }
    f = path / "collection.json"
    f.write_text(json.dumps(data))
    return hashlib.sha256(f.read_bytes()).hexdigest()


def check(path, digest):
    return verify(path, digest, "a" * 40, "sha256:" + "b" * 64, 2, 100, 100)


def test_consistent_synthetic_never_qualifies(tmp_path):
    digest = fixture_collection(tmp_path)
    result = check(tmp_path, digest)
    assert not result["issues"]
    assert result["host-qualified"] == "UNKNOWN"
    assert result["configuration-freeze-eligible"] == "UNKNOWN"


@pytest.mark.parametrize("file", ["git_head.stdout", "docker_info.stdout", "windows.stderr"])
def test_altered_raw_is_rejected(tmp_path, file):
    digest = fixture_collection(tmp_path)
    (tmp_path / file).write_text("tampered")
    assert check(tmp_path, digest)["issues"]


def test_missing_or_modified_manifest_fails(tmp_path):
    digest = fixture_collection(tmp_path)
    (tmp_path / "windows.stdout").unlink()
    assert check(tmp_path, digest)["issues"]
    (tmp_path / "collection.json").write_text("{}")
    assert check(tmp_path, digest)["issues"]


def rewrite_record(path, name, value):
    report_path = path / "collection.json"
    report = json.loads(report_path.read_text())
    file = path / f"{name}.stdout"
    file.write_text(value)
    report["commands"][name]["files_sha256"][file.name] = hashlib.sha256(
        file.read_bytes()
    ).hexdigest()
    report_path.write_text(json.dumps(report))
    return hashlib.sha256(report_path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "name,value,expected",
    [
        ("git_head", "wrong", "checkout SHA"),
        ("docker_images", "[]", "image ID"),
        ("docker_info", '{"NCPU": 1, "MemTotal": 200}', "CPUs"),
        ("docker_info", '{"NCPU": 4, "MemTotal": 1}', "memory"),
        ("output_disk", "header\n/dev/x 1000 990 10 99% /", "disk"),
    ],
)
def test_resource_mismatch_never_qualifies(tmp_path, name, value, expected):
    fixture_collection(tmp_path)
    digest = rewrite_record(tmp_path, name, value)
    result = check(tmp_path, digest)
    assert any(expected in issue for issue in result["issues"])
    assert result["host-qualified"] != "PASS"


def test_failed_command_does_not_become_pass(tmp_path):
    fixture_collection(tmp_path)
    path = tmp_path / "collection.json"
    report = json.loads(path.read_text())
    report["commands"]["windows"]["exit_code"] = None
    report["commands"]["windows"]["timeout"] = True
    path.write_text(json.dumps(report))
    result = check(tmp_path, hashlib.sha256(path.read_bytes()).hexdigest())
    assert result["inputs-consistent"] == "UNKNOWN"
    assert result["host-qualified"] == "UNKNOWN"
