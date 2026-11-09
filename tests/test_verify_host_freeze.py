"""Synthetic evidence: these tests never authorize a real experiment."""

import copy
import json
from types import SimpleNamespace

import pytest
from scripts.verify_host_freeze import differences, digest, main, validate


@pytest.fixture
def evidence():
    sha = "a" * 40
    image = "sha256:" + "b" * 64
    plan = {
        "schema": "inodefence-host-freeze-plan-v1",
        "execution_sha": sha,
        "approval_ref": "approval-1",
        "prereg_sha256": digest(b"prereg"),
        "design_sha256": digest(b"design"),
        "target_version": "7.5.2",
        "image_id": image,
        "engine_version": "29.8.0",
        "execution_mode": "per-case-container",
        "stop_rule": "registered-rule",
        "seed_allocation_ref": "allocation-1",
        "budget_ref": "budget-1",
        "backup_ref": "backup-1",
        "minimum_available_bytes": 100,
        "minimum_memory_bytes": 100,
        "minimum_cpus": 2,
        "hosts": {
            name: {
                "jobs": jobs,
                "output_path": f"/output/{name}",
                "runtime_path": f"/runtime/{name}",
                "assignment_ref": f"cells-{name}",
            }
            for name, jobs in (("HOST1", 2), ("HOST2", 1))
        },
    }
    windows = {
        name: {"status": "VERIFIED", "value": "observed"}
        for name in (
            "os",
            "cpu",
            "memory",
            "power_scheme",
            "sleep_settings",
            "docker_desktop",
            "wsl_version",
            "wsl_distributions",
        )
    }
    linux = {
        "os_release": "Ubuntu",
        "kernel": "WSL2",
        "cpu_model": "CPU",
        "filesystem_type": "ext4",
        "git_head": sha,
        "git_dirty": False,
        "available_bytes": 1000,
        "cpu_affinity_count": 8,
    }
    hosts = []
    for name, jobs in (("HOST1", 2), ("HOST2", 1)):
        hosts.append(
            {
                "schema": "inodefence-host-evidence-v1",
                "host_id": name,
                "windows_inventory": copy.deepcopy(windows),
                "linux_inventory": copy.deepcopy(linux),
                "measured": {
                    "memory_available_bytes": 1000,
                    "docker_cpus": 8,
                    "docker_memory_bytes": 1000,
                    "cgroup_memory_limit_bytes": 1000,
                    "cgroup_cpu_limit": 8,
                    "disk_available_bytes": 1000,
                    "docker_data_root": "/docker",
                    "docker_context": "desktop",
                    "output_path": f"/output/{name}",
                    "runtime_path": f"/runtime/{name}",
                    "qualification_ref": "measured",
                    "qualification_execution_sha": sha,
                    "target_version": "7.5.2",
                    "docker_engine": "29.8.0",
                    "image_id": image,
                    "docker_available": True,
                    "wsl2_verified": True,
                    "remaining_containers": [],
                    "remaining_experiment_volumes": [],
                    "qualified_jobs": jobs,
                },
            }
        )
    h1 = {
        "design_sha256": plan["design_sha256"],
        "decision": {
            "status": "selected",
            "selected_jobs": 2,
            "fallback_jobs": None,
            "stage_invalid": None,
            "halts": [],
        },
    }
    return plan, hosts, h1


def test_consistent_synthetic_evidence(evidence):
    assert validate(*evidence) == []
    assert differences(*evidence[1])["measured.qualified_jobs"] == {"HOST1": 2, "HOST2": 1}


@pytest.mark.parametrize(
    "change, expected",
    [
        (lambda p, h, d: h[1]["windows_inventory"].pop("os"), "Windows os UNKNOWN"),
        (lambda p, h, d: h[1]["linux_inventory"].update(git_head="bad"), "Git SHA mismatch"),
        (lambda p, h, d: h[1]["measured"].update(image_id="unknown"), "image mismatch"),
        (lambda p, h, d: h[1]["measured"].update(docker_memory_bytes=1), "below requirement"),
        (
            lambda p, h, d: h[1]["measured"].update(qualified_jobs=4),
            "jobs not explicitly qualified",
        ),
        (lambda p, h, d: h[1]["measured"].update(remaining_containers=None), "remaining resources"),
        (
            lambda p, h, d: h[1]["measured"].update(qualification_execution_sha="bad"),
            "qualification SHA mismatch",
        ),
        (lambda p, h, d: d["decision"].update(status="halted"), "H1 is not a valid"),
        (lambda p, h, d: d["decision"].update(selected_jobs=True), "H1 is not a valid"),
        (lambda p, h, d: p.update(approval_ref="UNKNOWN"), "approval_ref missing"),
    ],
)
def test_unknown_mismatch_and_halted_block(evidence, change, expected):
    change(*evidence)
    assert any(expected in issue for issue in validate(*evidence))


def test_cli_writes_hash_bound_manifest_and_refuses_overwrite(
    evidence, tmp_path, monkeypatch, capsys
):
    plan, hosts, h1 = evidence
    h1["stages"] = {"A": {}}
    prereg = f"""```preregistration
engine_sha = {plan["execution_sha"]}
image_digest = {plan["image_id"]}
seeds = 9001, 9002
budget = 200
vocabulary = observed-names
arm.R = unretained-walk-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
execution_mode = per-case-container
jobs_max = 2
```
""".encode()
    plan["prereg_sha256"] = digest(prereg)
    plan["hosts"]["HOST1"]["cells"] = [{"target_id": None, "seed": 9001, "arm": "R", "budget": 200}]
    plan["hosts"]["HOST2"]["cells"] = [{"target_id": None, "seed": 9002, "arm": "D", "budget": 200}]
    monkeypatch.setattr(
        "scripts.verify_host_freeze.load_design",
        lambda _: SimpleNamespace(stages={"A": (2, 4, 4, 2)}),
    )
    monkeypatch.setattr("scripts.verify_host_freeze.analyze", lambda *_: h1)
    for index, jobs in enumerate((2, 4, 4, 2), 1):
        directory = tmp_path / "h1-run" / "A" / f"block-{index}-j{jobs}"
        directory.mkdir(parents=True)
        (directory / "preflight.json").write_text(
            json.dumps(
                {
                    "design_sha256": plan["design_sha256"],
                    "approval_ref": "approved",
                    "preflight": {
                        "checkout_head": plan["execution_sha"],
                        "checkout_dirty": False,
                        "docker_server": plan["engine_version"],
                        "image_id": plan["image_id"],
                    },
                }
            )
        )
    for name, value in (("plan", plan), ("host1", hosts[0]), ("host2", hosts[1]), ("h1", h1)):
        (tmp_path / name).write_text(json.dumps(value))
    (tmp_path / "prereg").write_bytes(prereg)
    (tmp_path / "design").write_bytes(b"design")
    argv = ["verify"]
    for name in ("plan", "host1", "host2", "h1", "h1-run", "prereg", "design", "output"):
        argv += [f"--{name}", str(tmp_path / name)]
    monkeypatch.setattr("sys.argv", argv)
    assert main() == 0
    original = (tmp_path / "output").read_bytes()
    assert digest(original) in capsys.readouterr().out
    assert json.loads(original)["status"] == "inputs-consistent"
    assert main() == 1
    assert (tmp_path / "output").read_bytes() == original
    duplicated = copy.deepcopy(plan)
    duplicated["hosts"]["HOST2"]["cells"] = duplicated["hosts"]["HOST1"]["cells"]
    (tmp_path / "plan").write_text(json.dumps(duplicated))
    argv[-1] = str(tmp_path / "duplicate-output")
    assert main() == 1
    assert "duplicate assigned cell" in capsys.readouterr().err
    assert not (tmp_path / "duplicate-output").exists()
    (tmp_path / "plan").write_text(json.dumps(plan))
    block = tmp_path / "h1-run" / "A" / "block-1-j2" / "preflight.json"
    preflight = json.loads(block.read_text())
    preflight["preflight"]["checkout_head"] = "b" * 40
    block.write_text(json.dumps(preflight))
    argv[-1] = str(tmp_path / "other-output")
    assert main() == 1
    assert not (tmp_path / "other-output").exists()
    assert "H1 block preflight mismatch" in capsys.readouterr().err


def test_duplicate_json_is_rejected(tmp_path):
    from scripts.verify_host_freeze import read_json

    path = tmp_path / "duplicate.json"
    path.write_text('{"decision": 1, "decision": 2}')
    with pytest.raises(ValueError, match="duplicate"):
        read_json(path)
