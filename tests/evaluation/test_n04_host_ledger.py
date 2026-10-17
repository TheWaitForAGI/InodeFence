import argparse
import json
from hashlib import sha256

import pytest
from scripts.container_host import (
    N04HostLedger,
    _validate_n04_host_inputs,
    verify_n04_host_ledger,
)

from inodefence.evaluation import n04_preflight


def _args(evidence, packages):
    return argparse.Namespace(
        controller="controlled-controller",
        evidence=evidence,
        host_ledger=None,
        image=["sha256:" + "1" * 64, "sha256:" + "2" * 64],
        mode="preflight-node-n04-5s",
        package_tarball=packages,
        volume="inodefence-runtime",
    )


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
    monkeypatch.setattr(n04_preflight, "EVIDENCE_ROOT", evidence)
    monkeypatch.setattr(n04_preflight, "HOST_LEDGER_ROOT", ledger_root)
    args = _args(evidence, packages)

    ledger = N04HostLedger(ledger_root, args)
    ledger.owner = "a" * 32
    ledger.controller_id = "b" * 64
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
    assert verify_n04_host_ledger(ledger_root, evidence)["overall_status"] == "PREFLIGHT_PASS"

    with pytest.raises(FileExistsError):
        N04HostLedger(ledger_root, args)


def test_host_cleanup_failure_downgrades_linux_pass_to_inconclusive(tmp_path, monkeypatch):
    evidence = tmp_path / "linux-evidence"
    ledger_root = tmp_path / "host-ledger"
    monkeypatch.setattr(n04_preflight, "EVIDENCE_ROOT", evidence)
    monkeypatch.setattr(n04_preflight, "HOST_LEDGER_ROOT", ledger_root)
    ledger = N04HostLedger(ledger_root, _args(evidence, []))
    ledger.linux_terminal = _linux_terminal(evidence)
    ledger.cleanup_status = "failed"
    ledger.cleanup_errors.append("controlled cleanup failure")
    ledger.finish(0, None)

    verified = verify_n04_host_ledger(ledger_root, evidence)
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

    _validate_n04_host_inputs(builds, packages)
    with pytest.raises(ValueError, match="frozen host input paths"):
        _validate_n04_host_inputs(builds, (packages[1], packages[0]))

    linked = tmp_path / "linked-package.tgz"
    linked.symlink_to(packages[0])
    monkeypatch.setattr(n04_preflight, "HOST_PACKAGE_TARBALLS", (linked, packages[1]))
    with pytest.raises(ValueError, match="symlinks"):
        _validate_n04_host_inputs(builds, (linked, packages[1]))
