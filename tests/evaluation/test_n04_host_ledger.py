import argparse
import json
from hashlib import sha256

import pytest
from scripts.container_host import N04HostLedger

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
    ledger.finish(0, None)

    manifest = json.loads((ledger_root / "manifest.json").read_text())
    assert manifest["format"] == "inodefence-n04-host-ledger-v1"
    for name, digest in manifest["files"].items():
        assert sha256((ledger_root / name).read_bytes()).hexdigest() == digest
    terminal = json.loads((ledger_root / "terminal.json").read_text())
    assert terminal["cleanup_status"] == "complete"
    assert terminal["controller_returncode"] == 0
    assert terminal["target_names"] == ["controlled-target"]

    with pytest.raises(FileExistsError):
        N04HostLedger(ledger_root, args)


def test_host_ledger_rejects_alternate_destination(tmp_path, monkeypatch):
    evidence = tmp_path / "linux-evidence"
    ledger_root = tmp_path / "host-ledger"
    monkeypatch.setattr(n04_preflight, "EVIDENCE_ROOT", evidence)
    monkeypatch.setattr(n04_preflight, "HOST_LEDGER_ROOT", ledger_root)

    with pytest.raises(ValueError, match="frozen host/evidence"):
        N04HostLedger(tmp_path / "alternate", _args(evidence, []))
