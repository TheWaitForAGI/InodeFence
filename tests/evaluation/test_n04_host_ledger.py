import argparse
import json
import sys
from hashlib import sha256

import pytest
import scripts.container_controller as container_controller
import scripts.container_host as container_host
from scripts.container_host import (
    N04HostLedger,
    _inspect_n04_host_metadata,
    _validate_n04_host_inputs,
    verify_n04_host_ledger,
)

from inodefence.evaluation import n04_preflight
from inodefence.execution.docker_client import BackendError, CommandResult


def _args(evidence, packages):
    return argparse.Namespace(
        controller="c" * 64,
        evidence=evidence,
        host_ledger=None,
        image=[item.image_id for item in n04_preflight.FROZEN_TARGETS],
        mode="preflight-node-n04-5s",
        package_tarball=packages,
        volume=n04_preflight.RUNTIME_VOLUME_NAME,
    )


def _freeze_paths(monkeypatch, evidence, ledger_root, packages):
    monkeypatch.setattr(n04_preflight, "EVIDENCE_ROOT", evidence)
    monkeypatch.setattr(n04_preflight, "HOST_LEDGER_ROOT", ledger_root)
    monkeypatch.setattr(n04_preflight, "HOST_PACKAGE_TARBALLS", tuple(packages))


def _manifest_digest(ledger_root):
    return sha256((ledger_root / "manifest.json").read_bytes()).hexdigest()


def _linux_terminal(evidence):
    raw = b"controlled raw manifest\n"
    final = b"controlled final manifest\n"
    evidence.mkdir()
    (evidence / "raw-manifest.json").write_bytes(raw)
    (evidence / "manifest.json").write_bytes(final)
    return {
        "final_manifest_sha256": sha256(final).hexdigest(),
        "final_status": "PREFLIGHT_PASS",
        "host_cleanup_pending": True,
        "independent_status": "PASS",
        "pilot_authorized": False,
        "preflight_verdict": "PASS",
        "raw_manifest_sha256": sha256(raw).hexdigest(),
        "reader_returncode": 0,
    }


def test_host_ledger_consumes_one_exact_attempt_and_binds_terminal_cleanup(tmp_path, monkeypatch):
    evidence = tmp_path / "linux-evidence"
    ledger_root = tmp_path / "host-ledger"
    packages = [tmp_path / "tar-7.5.2.tgz", tmp_path / "tar-7.5.3.tgz"]
    _freeze_paths(monkeypatch, evidence, ledger_root, packages)
    args = _args(evidence, packages)

    ledger = N04HostLedger(ledger_root, args)
    ledger.owner = "a" * 32
    ledger.controller_id = "c" * 64
    ledger.target_names.add("controlled-target")
    ledger.cleanup_status = "complete"
    ledger.linux_terminal = _linux_terminal(evidence)
    ledger.finish(0, None)

    manifest = json.loads((ledger_root / "manifest.json").read_text())
    assert manifest["format"] == "inodefence-n04-host-ledger-v1"
    for name, digest in manifest["files"].items():
        assert sha256((ledger_root / name).read_bytes()).hexdigest() == digest
    terminal = json.loads((ledger_root / "terminal.json").read_text())
    assert terminal["cleanup_status"] == "complete"
    assert terminal["controller_returncode"] == 0
    assert terminal["target_names"] == ["controlled-target"]
    assert terminal["overall_status"] == "PREFLIGHT_PASS"
    assert (
        verify_n04_host_ledger(
            ledger_root,
            evidence,
            expected_manifest_sha256=_manifest_digest(ledger_root),
        )["overall_status"]
        == "PREFLIGHT_PASS"
    )

    with pytest.raises(FileExistsError):
        N04HostLedger(ledger_root, args)


def test_host_cleanup_failure_downgrades_linux_pass_to_inconclusive(tmp_path, monkeypatch):
    evidence = tmp_path / "linux-evidence"
    ledger_root = tmp_path / "host-ledger"
    packages = [tmp_path / "tar-7.5.2.tgz", tmp_path / "tar-7.5.3.tgz"]
    _freeze_paths(monkeypatch, evidence, ledger_root, packages)
    ledger = N04HostLedger(ledger_root, _args(evidence, packages))
    ledger.owner = "a" * 32
    ledger.controller_id = "c" * 64
    ledger.linux_terminal = _linux_terminal(evidence)
    ledger.cleanup_status = "failed"
    ledger.cleanup_errors.append("controlled cleanup failure")
    ledger.finish(0, None)

    verified = verify_n04_host_ledger(
        ledger_root,
        evidence,
        expected_manifest_sha256=_manifest_digest(ledger_root),
    )
    assert verified["overall_status"] == "PREFLIGHT_INCONCLUSIVE"


def test_host_ledger_rejects_alternate_destination(tmp_path, monkeypatch):
    evidence = tmp_path / "linux-evidence"
    ledger_root = tmp_path / "host-ledger"
    monkeypatch.setattr(n04_preflight, "EVIDENCE_ROOT", evidence)
    monkeypatch.setattr(n04_preflight, "HOST_LEDGER_ROOT", ledger_root)

    with pytest.raises(ValueError, match="frozen host/evidence"):
        N04HostLedger(tmp_path / "alternate", _args(evidence, []))


def test_host_inputs_require_exact_nonsymlink_paths(tmp_path, monkeypatch):
    builds = (tmp_path / "affected", tmp_path / "fixed")
    packages = (tmp_path / "tar-7.5.2.tgz", tmp_path / "tar-7.5.3.tgz")
    for path in builds:
        path.mkdir()
    for path in packages:
        path.write_bytes(b"controlled package")
    monkeypatch.setattr(n04_preflight, "HOST_BUILD_CONTEXTS", builds)
    monkeypatch.setattr(n04_preflight, "HOST_PACKAGE_TARBALLS", packages)
    monkeypatch.setattr(n04_preflight, "RUNTIME_VOLUME_NAME", "controlled-volume")

    _validate_n04_host_inputs(builds, packages, "controlled-volume")
    with pytest.raises(ValueError, match="frozen host input paths"):
        _validate_n04_host_inputs(builds, (packages[1], packages[0]), "controlled-volume")
    with pytest.raises(ValueError, match="frozen host input paths"):
        _validate_n04_host_inputs(builds, packages, "wrong-volume")

    linked = tmp_path / "linked-package.tgz"
    linked.symlink_to(packages[0])
    monkeypatch.setattr(n04_preflight, "HOST_PACKAGE_TARBALLS", (linked, packages[1]))
    with pytest.raises(ValueError, match="symlinks"):
        _validate_n04_host_inputs(builds, (linked, packages[1]), "controlled-volume")


def test_early_failure_ledger_rejects_rebound_frozen_fields(tmp_path, monkeypatch):
    evidence = tmp_path / "linux-evidence"
    ledger_root = tmp_path / "host-ledger"
    packages = [tmp_path / "tar-7.5.2.tgz", tmp_path / "tar-7.5.3.tgz"]
    _freeze_paths(monkeypatch, evidence, ledger_root, packages)
    ledger = N04HostLedger(ledger_root, _args(evidence, packages))
    ledger.owner = "a" * 32
    ledger.controller_id = "c" * 64
    ledger.finish(None, BackendError("controlled early failure"))
    trusted_digest = _manifest_digest(ledger_root)

    started = json.loads((ledger_root / "started.json").read_text())
    started["images"].reverse()
    started_bytes = (
        json.dumps(started, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")
    (ledger_root / "started.json").write_bytes(started_bytes)
    manifest = json.loads((ledger_root / "manifest.json").read_text())
    manifest["files"]["started.json"] = sha256(started_bytes).hexdigest()
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")
    (ledger_root / "manifest.json").write_bytes(manifest_bytes)

    with pytest.raises(ValueError, match="manifest binding"):
        verify_n04_host_ledger(
            ledger_root,
            evidence,
            expected_manifest_sha256=sha256(manifest_bytes).hexdigest(),
        )
    with pytest.raises(ValueError, match="manifest binding"):
        verify_n04_host_ledger(
            ledger_root,
            evidence,
            expected_manifest_sha256=trusted_digest,
        )


def test_consumed_mode_rejects_before_ledger_or_docker(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("consumed mode crossed its source gate")

    monkeypatch.setattr(container_host, "N04HostLedger", forbidden)
    monkeypatch.setattr(container_host.shutil, "which", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "container_host.py",
            "--context",
            "orbstack",
            "--controller",
            "c" * 64,
            "--volume",
            "controlled-volume",
            "--image",
            "sha256:" + "1" * 64,
            "--image",
            "sha256:" + "2" * 64,
            "--build-context",
            str(tmp_path / "affected"),
            "--build-context",
            str(tmp_path / "fixed"),
            "--package-tarball",
            str(tmp_path / "affected.tgz"),
            "--package-tarball",
            str(tmp_path / "fixed.tgz"),
            "--evidence",
            "/var/lib/inodefence/evidence/controlled",
            "--host-ledger",
            str(tmp_path / "ledger"),
            "preflight-node-n04-5s",
        ],
    )

    with pytest.raises(BackendError, match="attempt is consumed"):
        container_host.main()
    assert not (tmp_path / "ledger").exists()


def test_consumed_controller_mode_rejects_before_stdin(tmp_path, monkeypatch):
    class ForbiddenStdin:
        def readline(self, *args, **kwargs):
            pytest.fail("consumed controller mode attempted to read initialization")

    monkeypatch.setattr(sys, "stdin", ForbiddenStdin())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "container_controller.py",
            "--controller",
            "c" * 64,
            "--volume",
            "controlled-volume",
            "--owner",
            "a" * 32,
            "--image",
            "sha256:" + "1" * 64,
            "--image",
            "sha256:" + "2" * 64,
            "--evidence",
            str(tmp_path / "evidence"),
            "preflight-node-n04-5s",
        ],
    )

    with pytest.raises(RuntimeError, match="attempt is consumed"):
        container_controller.main()


def test_host_metadata_uses_only_host_inspection_channel():
    class FakeDocker:
        def __init__(self):
            self.calls = []

        def run(self, args, timeout):
            pytest.fail("host metadata crossed the controller-visible channel")

        def run_host_inspection(self, args, timeout):
            self.calls.append((args, timeout))
            if args[0] == "info":
                return CommandResult(0, b'{"ID":"controlled-daemon"}', b"")
            return CommandResult(0, ("b" * 64 + "\n" + "a" * 64 + "\n").encode(), b"")

    client = FakeDocker()
    info, consumers = _inspect_n04_host_metadata(client, "controlled-volume", lambda value: value)

    assert info == {"ID": "controlled-daemon"}
    assert consumers == ("a" * 64, "b" * 64)
    assert [call[0] for call in client.calls] == [
        ("info", "--format", "{{json .}}"),
        (
            "container",
            "ls",
            "--all",
            "--no-trunc",
            "--filter",
            "volume=controlled-volume",
            "--format",
            "{{.ID}}",
        ),
    ]
