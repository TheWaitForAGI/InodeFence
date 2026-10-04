"""Namespace prerequisites are observed, never an execution-safety attestation."""

import json
import subprocess

import pytest
from scripts import check_linux_isolation_support as support

from inodefence.model.provenance import SourceProvenance


@pytest.fixture
def commands(monkeypatch):
    calls = []
    monkeypatch.setattr(support.platform, "system", lambda: "Linux")
    monkeypatch.setattr(support.shutil, "which", lambda name: f"/usr/bin/{name}")

    def execute(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(support.subprocess, "run", execute)
    # Source capture shares subprocess; keep these tests about namespace probes.
    monkeypatch.setattr(support, "capture_source", lambda: SourceProvenance())
    return calls


def test_present_tools_with_denied_namespaces_report_unavailable(commands, monkeypatch):
    def denied(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 1, "", "unshare: Operation not permitted\n")

    monkeypatch.setattr(support.subprocess, "run", denied)
    report = support.collect_support()
    assert report["namespace_creation"] == "unavailable"
    assert len(report["namespace_probes"]) == len(commands) == 8
    assert all(probe["status"] == "denied_or_failed" for probe in report["namespace_probes"])
    assert all(probe["returncode"] == 1 for probe in report["namespace_probes"])
    assert all("Operation not permitted" in probe["stderr"] for probe in report["namespace_probes"])


def test_creation_success_has_no_containment_claim_and_uses_fixed_benign_commands(commands):
    report = support.collect_support()
    assert report["namespace_creation"] == "available"
    assert report["assessment_scope"] == "namespace-prerequisites-only"
    assert report["schema_version"] == 1
    assert len(commands) == 8
    for command, kwargs in commands:
        assert command[0] == "/usr/bin/unshare" and command[-1] == "/usr/bin/true"
        assert "--fork" not in command and "--mount-proc" not in command
        if "--mount" in command:
            assert command[command.index("--propagation") + 1] == "unchanged"
        assert kwargs["timeout"] == 5.0
        assert kwargs["env"] == {"PATH": support.os.defpath, "LANG": "C.UTF-8"}
        assert not kwargs.get("shell", False)
    assert "secure" not in report and "validated" not in report


def test_direct_namespace_denial_does_not_hide_rootless_creation_support(commands, monkeypatch):
    def rootless_only(command, **kwargs):
        return subprocess.CompletedProcess(command, 0 if "--user" in command else 1, "", "")

    monkeypatch.setattr(support.subprocess, "run", rootless_only)
    report = support.collect_support()
    assert report["namespace_creation"] == "available"
    assert sum(probe["returncode"] == 1 for probe in report["namespace_probes"]) == 3


@pytest.mark.parametrize("missing", ("unshare", "true"))
def test_missing_tool_never_claims_creation_or_invokes_commands(commands, monkeypatch, missing):
    monkeypatch.setattr(
        support.shutil, "which", lambda name: None if name == missing else f"/usr/bin/{name}"
    )
    report = support.collect_support()
    assert report["namespace_creation"] == "unavailable"
    assert all(probe["status"] == "missing_tool" for probe in report["namespace_probes"])
    assert commands == []


@pytest.mark.parametrize(
    "error", (PermissionError("denied"), subprocess.TimeoutExpired("unshare", 5))
)
def test_launch_error_and_timeout_are_unavailable_and_preserved(commands, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(support.subprocess, "run", fail)
    report = support.collect_support()
    assert report["namespace_creation"] == "unavailable"
    assert all(probe["returncode"] is None for probe in report["namespace_probes"])
    assert all(type(error).__name__ in probe["error"] for probe in report["namespace_probes"])


def test_nonlinux_platform_is_explicit_and_does_not_probe(commands, monkeypatch):
    monkeypatch.setattr(support.platform, "system", lambda: "Darwin")
    report = support.collect_support()
    assert report["namespace_creation"] == "unsupported_platform"
    assert report["linux_facts"] is None
    assert commands == []


@pytest.mark.parametrize("returncode,expected", ((0, 0), (1, 1)))
def test_cli_json_and_exit_status_preserve_observed_availability(
    commands, monkeypatch, capsys, returncode, expected
):
    monkeypatch.setattr(
        support.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, returncode, "", ""),
    )
    assert support.main() == expected
    raw = capsys.readouterr().out
    report = json.loads(raw)
    assert (
        raw == json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    )
    assert report["assessment_scope"] == "namespace-prerequisites-only"
