"""Phase-1 audit witnesses, not fixes or assertions of correct production behavior.

PASS confirms the documented baseline defects. All target execution is replaced
by synthetic evidence; the CLI witness runs only a disposable benign helper.
Delete/convert these witnesses when a separately reviewed fix rejects the paths.
"""

import json
import os
import runpy
import signal
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.execution.base import ExecutionBackend
from inodefence.execution.container import ContainerExecutionBackend, ContainerRequest
from inodefence.execution.docker_client import DockerCLI
from inodefence.experiment_config import (
    FEEDBACK_POLICY,
    MUTATION_POLICY,
    SEED_PROFILE,
    ExperimentConfig,
    run_configured_campaign,
)
from inodefence.feedback import state_signature
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ExecutionResult,
    ExecutionStatus,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
)
from inodefence.model.isolation import IsolationPolicy, IsolationProvenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.isolated import IsolatedTarget
from inodefence.targets.node_tar import NodeTarTarget

IMAGE = "sha256:" + "a" * 64
OTHER_IMAGE = "sha256:" + "b" * 64
METADATA = {
    "node_version": "22.22.0",
    "tar_version": "7.5.22",
    "worker_sha256": "b" * 64,
    "package_lock_sha256": "c" * 64,
}


class IdentityOnlyBackend(ExecutionBackend):
    """A known test double; it cannot run a target and proves no containment."""

    def validate_image(self, image_id):
        assert image_id in (IMAGE, OTHER_IMAGE)

    def policy(self, image_id):
        return IsolationPolicy(image_id, 1000, 1000)

    def capture_isolation(self, image_id):
        return IsolationProvenance(
            self.policy(image_id), "audit-double", "test", "test", "linux", "test", "test"
        )

    @contextmanager
    def prepare(self, request):
        raise AssertionError("audit evidence witness must never execute a target")
        yield  # pragma: no cover


@pytest.mark.parametrize("configured", (False, True))
@pytest.mark.parametrize("construction", ("direct", "replace", "other-image"))
def test_ex001_unobserved_artifact_declarations_survive_admission_and_export(
    configured, construction, monkeypatch, tmp_path
):
    backend = IdentityOnlyBackend()
    identified = []

    def identify(_backend, image_id):
        identified.append(image_id)
        # Test testimony, not an actual image observation.
        assert image_id == IMAGE
        return dict(METADATA)

    monkeypatch.setattr("inodefence.targets.node_tar._identify", identify)
    if construction == "direct":
        descriptor = NodeTarTarget(IMAGE, "22.22.0", "7.5.22", "d" * 64, "e" * 64)
    else:
        bound = NodeTarTarget.bind(backend, IMAGE)
        assert isinstance(bound.invocation, NodeTarTarget)
        assert bound.invocation.worker_sha256 == METADATA["worker_sha256"]
        descriptor = (
            replace(bound.invocation, image_id=OTHER_IMAGE)
            if construction == "other-image"
            else replace(bound.invocation, worker_sha256="d" * 64, package_lock_sha256="e" * 64)
        )
    target = IsolatedTarget(descriptor, backend)
    calls = []

    def synthetic_run(case, adapter, *, sentinels):
        calls.append(case.case_id)
        before = StateSnapshot("/var/lib/inodefence/synthetic-audit", SnapshotPhase.BEFORE, (), ())
        after = replace(before, phase=SnapshotPhase.AFTER)
        declared = adapter.provenance
        execution = ExecutionResult(
            declared.target_id,
            declared.target_version,
            (),
            ExecutionStatus.SUCCESS,
            0,
            "",
            "",
            0,
            declared.timeout_seconds,
        )
        return RunResult(
            case,
            case.case_id,
            "synthetic-audit",
            execution,
            before,
            after,
            (),
            state_signature(before, after),
            (),
        )

    monkeypatch.setattr("inodefence.campaign.run_case", synthetic_run)
    seeds = minimal_seed_corpus()
    budget = CampaignConfig(11, 4)
    config = ExperimentConfig(
        target.provenance,
        SEED_PROFILE,
        tuple(case.case_id for case in seeds),
        budget,
        MUTATION_POLICY,
        FEEDBACK_POLICY,
        (SentinelSpec(),),
        "audit-double-v1",
        target.isolation_policy,
    )
    result = (
        run_configured_campaign(config, seeds, target)
        if configured
        else run_campaign(seeds, target, budget)
    )
    assert len(result.steps) == len(calls) == 4
    assert identified == ([] if construction == "direct" else [IMAGE])
    assert result.provenance.isolation is not None
    assert result.provenance.isolation.artifacts == descriptor.artifacts
    manifest, _ = export_campaign(
        result,
        tmp_path / "synthetic-evidence",
        experiment_config_json=config.to_json() if configured else None,
    )
    isolation = json.loads(manifest.read_bytes())["execution_provenance"]["isolation"]
    assert isolation["policy"]["image_id"] == descriptor.image_id
    assert isolation["artifacts"] == [
        {"name": item.name, "sha256": item.sha256} for item in descriptor.artifacts
    ]


@pytest.mark.skipif(sys.platform != "linux", reason="supported execution is Linux")
def test_ex003_cli_deadline_leaves_child_when_primary_already_exited(tmp_path):
    executable = tmp_path / "benign-docker-double"
    pid_file = tmp_path / "child.pid"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os,time\n"
        "child=os.fork()\n"
        "if child == 0:\n"
        "    time.sleep(30)\n"
        "    os._exit(0)\n"
        f"with open({str(pid_file)!r}, 'w') as stream:\n"
        "    stream.write(str(child))\n"
        "os.write(1, str(child).encode())\n"
        "os._exit(0)\n"
    )
    executable.chmod(0o700)
    try:
        outcome = DockerCLI(str(executable), "audit-double").run(("version",), 1)
        assert outcome.timed_out and outcome.returncode == 0
        child = int(pid_file.read_text())
        assert int(outcome.stdout) == child
        # A live sleeping child, rather than a reaped/zombie PID, proves the leak.
        assert Path(f"/proc/{child}/stat").read_text().split()[2] != "Z"
        os.kill(child, 0)
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_ex002_prepare_accepts_disagreeing_actual_command_config(monkeypatch, sandbox):
    # Reuse the baseline policy double rather than copy its large HostConfig.
    baseline_path = Path(__file__).resolve().parents[1] / "test_container_backend.py"
    baseline = runpy.run_path(str(baseline_path))
    docker = baseline["FakeDocker"]()
    controller = baseline["CONTROLLER"]
    monkeypatch.setattr("inodefence.execution.container.os.getuid", lambda: 1000)
    monkeypatch.setattr("inodefence.execution.container.os.getgid", lambda: 1000)
    monkeypatch.setattr("socket.gethostname", lambda: controller[:12])
    backend = ContainerExecutionBackend(docker, controller, "inodefence-runtime", baseline["OWNER"])
    original = docker.run

    def changed_config(args, timeout):
        result = original(args, timeout)
        if args[:2] == ("container", "create"):
            docker.target["Config"].update(
                Entrypoint=["/different-benign-helper"],
                Cmd=["different"],
                WorkingDir="/tmp",
                Env=["AUDIT_DOUBLE=1"],
            )
        return result

    docker.run = changed_config
    with backend.prepare(ContainerRequest(IMAGE, ("/expected-helper",), sandbox.root, 5)):
        assert docker.target["Config"]["WorkingDir"] != str(sandbox.extraction_root)
    assert not any(call[:2] == ("container", "start") for call in docker.calls)
    assert docker.target is None
