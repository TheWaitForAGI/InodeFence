"""Validate recorded host inputs against an explicitly approved execution plan.

This compares supplied evidence; it does not authenticate measurements, approve a plan,
execute Docker, select jobs, or independently reproduce benchmark decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.analyze_concurrency_benchmark import analyze
from scripts.run_concurrency_benchmark import load_design

from inodefence.evaluation.rds import RdsArm
from inodefence.evaluation.rds_preregistration import (
    CellRequest,
    Preregistration,
    load_preregistration,
    preregistration_mismatches,
)

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(
        raw, object_pairs_hook=unique, parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s))
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value, digest(raw)


def validate(plan: dict[str, Any], hosts: list[dict[str, Any]], h1: dict[str, Any]) -> list[str]:
    """Return all blockers; missing or malformed evidence cannot become a pass."""
    problems: list[str] = []

    def require(ok: bool, msg: str) -> None:
        if not ok:
            problems.append(msg)

    def nonempty(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "UNKNOWN"

    def integer(value: Any, minimum: int = 1) -> bool:
        return type(value) is int and value >= minimum

    def obj(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    require(plan.get("schema") == "inodefence-host-freeze-plan-v1", "plan: unsupported schema")
    sha = plan.get("execution_sha")
    require(
        isinstance(sha, str) and HEX40.fullmatch(sha) is not None,
        "plan: execution_sha missing or invalid",
    )
    for key in (
        "approval_ref",
        "prereg_sha256",
        "design_sha256",
        "target_version",
        "image_id",
        "engine_version",
        "execution_mode",
        "stop_rule",
        "seed_allocation_ref",
        "budget_ref",
        "backup_ref",
    ):
        require(nonempty(plan.get(key)), f"plan: {key} missing")
    for key in ("prereg_sha256", "design_sha256"):
        value = plan.get(key)
        require(
            isinstance(value, str) and HEX64.fullmatch(value) is not None, f"plan: {key} invalid"
        )
    require(
        isinstance(plan.get("image_id"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", plan["image_id"]) is not None,
        "plan: image_id invalid",
    )
    require(plan.get("execution_mode") == "per-case-container", "plan: unsupported execution mode")
    for key in ("minimum_available_bytes", "minimum_memory_bytes", "minimum_cpus"):
        require(integer(plan.get(key)), f"plan: {key} invalid")
    require(len(hosts) == 2, "exactly two hosts required")
    require(
        {h.get("host_id") for h in hosts if isinstance(h.get("host_id"), str)}
        == {"HOST1", "HOST2"},
        "HOST1 and HOST2 required",
    )
    settings = obj(plan.get("hosts"))
    output_paths: list[str] = []
    for host in hosts:
        host_id = host.get("host_id")
        label = str(host_id)
        inv = obj(host.get("linux_inventory"))
        win = obj(host.get("windows_inventory"))
        measured = obj(host.get("measured"))
        configured = obj(settings.get(host_id)) if isinstance(host_id, str) else {}
        require(host.get("schema") == "inodefence-host-evidence-v1", f"{label}: unsupported schema")
        for field in (
            "os",
            "cpu",
            "memory",
            "power_scheme",
            "sleep_settings",
            "docker_desktop",
            "wsl_version",
            "wsl_distributions",
        ):
            item = obj(win.get(field))
            require(
                item.get("status") == "VERIFIED"
                and item.get("value") not in (None, "", [], {}, "UNKNOWN"),
                f"{label}: Windows {field} UNKNOWN",
            )
        for field in ("os_release", "kernel", "cpu_model", "filesystem_type"):
            require(nonempty(inv.get(field)), f"{label}: Linux {field} missing")
        require(
            inv.get("git_head") == sha and inv.get("git_dirty") is False,
            f"{label}: clean Git SHA mismatch",
        )
        for field, minimum in (
            ("available_bytes", "minimum_available_bytes"),
            ("cpu_affinity_count", "minimum_cpus"),
        ):
            require(
                integer(inv.get(field))
                and integer(plan.get(minimum))
                and inv[field] >= plan[minimum],
                f"{label}: {field} below requirement or UNKNOWN",
            )
        for field in (
            "memory_available_bytes",
            "docker_cpus",
            "docker_memory_bytes",
            "cgroup_memory_limit_bytes",
            "cgroup_cpu_limit",
            "disk_available_bytes",
        ):
            require(integer(measured.get(field)), f"{label}: {field} UNKNOWN")
        for field in ("memory_available_bytes", "docker_memory_bytes", "cgroup_memory_limit_bytes"):
            require(
                integer(measured.get(field))
                and integer(plan.get("minimum_memory_bytes"))
                and measured[field] >= plan["minimum_memory_bytes"],
                f"{label}: {field} below requirement",
            )
        require(
            integer(measured.get("docker_cpus"))
            and integer(plan.get("minimum_cpus"))
            and measured["docker_cpus"] >= plan["minimum_cpus"],
            f"{label}: Docker CPU below requirement",
        )
        require(
            integer(measured.get("cgroup_cpu_limit"))
            and integer(plan.get("minimum_cpus"))
            and measured["cgroup_cpu_limit"] >= plan["minimum_cpus"],
            f"{label}: cgroup CPU below requirement",
        )
        require(
            integer(measured.get("disk_available_bytes"))
            and integer(plan.get("minimum_available_bytes"))
            and measured["disk_available_bytes"] >= plan["minimum_available_bytes"],
            f"{label}: output disk below requirement",
        )
        for field in (
            "docker_data_root",
            "docker_context",
            "output_path",
            "runtime_path",
            "qualification_ref",
        ):
            require(nonempty(measured.get(field)), f"{label}: {field} UNKNOWN")
        for field in ("docker_data_root", "output_path", "runtime_path"):
            require(
                isinstance(measured.get(field), str) and measured[field].startswith("/"),
                f"{label}: {field} must be absolute",
            )
        require(
            measured.get("docker_engine") == plan.get("engine_version")
            and nonempty(measured.get("docker_engine")),
            f"{label}: Docker engine mismatch",
        )
        require(
            measured.get("image_id") == plan.get("image_id") and nonempty(measured.get("image_id")),
            f"{label}: image mismatch",
        )
        require(
            measured.get("target_version") == plan.get("target_version")
            and nonempty(measured.get("target_version")),
            f"{label}: target version mismatch",
        )
        require(
            measured.get("qualification_execution_sha") == sha and nonempty(sha),
            f"{label}: qualification SHA mismatch",
        )
        require(
            measured.get("docker_available") is True and measured.get("wsl2_verified") is True,
            f"{label}: Docker/WSL2 unavailable or UNKNOWN",
        )
        require(
            measured.get("remaining_containers") == []
            and measured.get("remaining_experiment_volumes") == [],
            f"{label}: remaining resources or UNKNOWN",
        )
        jobs = configured.get("jobs")
        require(
            integer(jobs) and measured.get("qualified_jobs") == jobs,
            f"{label}: jobs not explicitly qualified",
        )
        for field in ("output_path", "runtime_path"):
            require(
                measured.get(field) == configured.get(field) and nonempty(configured.get(field)),
                f"{label}: {field} differs from plan",
            )
        if nonempty(measured.get("output_path")):
            output_paths.append(str(measured["output_path"]))
        require(nonempty(configured.get("assignment_ref")), f"{label}: assignment_ref missing")
    require(
        len(output_paths) == 2 and output_paths[0] != output_paths[1],
        "host output paths must be distinct",
    )
    decision = obj(h1.get("decision"))
    require(h1.get("design_sha256") == plan.get("design_sha256"), "H1 design digest mismatch")
    require(
        decision.get("status") == "selected"
        and integer(decision.get("selected_jobs"))
        and decision.get("fallback_jobs") is None
        and decision.get("stage_invalid") is None
        and decision.get("halts") == [],
        "H1 is not a valid selected decision",
    )
    first = obj(settings.get("HOST1"))
    require(
        integer(first.get("jobs"))
        and integer(decision.get("selected_jobs"))
        and first["jobs"] <= decision["selected_jobs"],
        "HOST1 jobs exceed selected H1 level",
    )
    return problems


def differences(host1: dict[str, Any], host2: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Expose differing observations without treating all differences as incompatibilities."""
    result: dict[str, dict[str, Any]] = {}
    for section, fields in {
        "linux_inventory": (
            "os_release",
            "kernel",
            "cpu_model",
            "cpu_affinity_count",
            "available_bytes",
        ),
        "windows_inventory": (
            "os",
            "cpu",
            "memory",
            "power_scheme",
            "docker_desktop",
            "wsl_version",
        ),
        "measured": (
            "docker_cpus",
            "docker_memory_bytes",
            "cgroup_cpu_limit",
            "cgroup_memory_limit_bytes",
            "disk_available_bytes",
            "docker_engine",
            "image_id",
            "qualified_jobs",
        ),
    }.items():
        first = host1.get(section)
        second = host2.get(section)
        if not isinstance(first, dict):
            first = {}
        if not isinstance(second, dict):
            second = {}
        for field in fields:
            if first.get(field) != second.get(field):
                result[f"{section}.{field}"] = {
                    "HOST1": first.get(field),
                    "HOST2": second.get(field),
                }
    return result


def validate_assignments(plan: dict[str, Any], registration: Preregistration) -> list[str]:
    """Check each assigned cell against the registered gate and reject duplicates."""
    issues: list[str] = []
    seen: set[tuple[str | None, int, str]] = set()
    for host_id in ("HOST1", "HOST2"):
        host = plan["hosts"][host_id]
        cells = host.get("cells")
        if not isinstance(cells, list) or not cells:
            issues.append(f"{host_id}: explicit assigned cells missing")
            continue
        for cell in cells:
            if not isinstance(cell, dict):
                issues.append(f"{host_id}: invalid cell")
                continue
            seed, budget, target = cell.get("seed"), cell.get("budget"), cell.get("target_id")
            try:
                arm = RdsArm(cell.get("arm"))
            except (ValueError, TypeError):
                issues.append(f"{host_id}: unknown arm")
                continue
            if (
                type(seed) is not int
                or type(budget) is not int
                or not (target is None or isinstance(target, str))
            ):
                issues.append(f"{host_id}: invalid cell seed, budget or target")
                continue
            identity = (target, seed, arm.value)
            if identity in seen:
                issues.append(f"{host_id}: duplicate assigned cell {identity}")
            seen.add(identity)
            sentinel = {
                "generator_id": registration.sentinel_generator_id,
                "generator_seed": registration.sentinel_generator_seed,
                "count": registration.sentinel_count,
            }
            request = CellRequest(
                arm,
                seed,
                budget,
                plan["execution_sha"],
                False,
                plan["image_id"],
                sentinel,
                registration.observer_integrity_policy,
                registration.experiment_id,
                plan["execution_mode"],
                host["jobs"],
                target,
            )
            issues.extend(
                f"{host_id}: {reason}"
                for reason in preregistration_mismatches(registration, request)
            )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "host1", "host2", "h1", "h1-run", "prereg", "design", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        items = [read_json(path) for path in (args.plan, args.host1, args.host2, args.h1)]
        plan, host1, host2, h1 = [item[0] for item in items]
        issues = validate(plan, [host1, host2], h1)
        prereg_hash = digest(args.prereg.read_bytes())
        design_hash = digest(args.design.read_bytes())
        preflight_hashes: dict[str, str] = {}
        if prereg_hash != plan.get("prereg_sha256"):
            issues.append("preregistration file digest mismatch")
        if design_hash != plan.get("design_sha256"):
            issues.append("benchmark design file digest mismatch")
        if not issues:
            registration = load_preregistration(args.prereg)
            if registration.engine_sha != plan["execution_sha"]:
                issues.append("registered execution SHA mismatch")
            if registration.execution_mode != plan["execution_mode"]:
                issues.append("registered execution mode missing or mismatched")
            image_ok = registration.image_digest == plan["image_id"] or any(
                target.digest_kind == "image"
                and target.digest == plan["image_id"]
                and target.version == plan["target_version"]
                for target in registration.targets
            )
            if not image_ok:
                issues.append("registered target image/version mismatch")
            for host_settings in plan["hosts"].values():
                if registration.jobs_max is None or host_settings["jobs"] > registration.jobs_max:
                    issues.append("host jobs exceed or lack registered jobs_max")
            issues.extend(validate_assignments(plan, registration))
        if not issues:
            design = load_design(args.design)
            stages = h1.get("stages", {})
            if not isinstance(stages, dict) or "A" not in stages:
                issues.append("H1 stage A evidence missing")
            else:
                for stage, stage_report in stages.items():
                    if stage not in design.stages or not isinstance(stage_report, dict):
                        issues.append(f"invalid H1 stage {stage}")
                        continue
                    for index, jobs in enumerate(design.stages[stage], start=1):
                        path = args.h1_run / stage / f"block-{index}-j{jobs}" / "preflight.json"
                        preflight, preflight_hash = read_json(path)
                        preflight_hashes[str(path.relative_to(args.h1_run))] = preflight_hash
                        facts = preflight.get("preflight", {})
                        if not isinstance(facts, dict) or not (
                            preflight.get("design_sha256") == design_hash
                            and isinstance(preflight.get("approval_ref"), str)
                            and bool(preflight["approval_ref"].strip())
                            and facts.get("checkout_head") == plan["execution_sha"]
                            and facts.get("checkout_dirty") is False
                            and facts.get("docker_server") == plan["engine_version"]
                            and facts.get("image_id") == plan["image_id"]
                        ):
                            issues.append(f"H1 block preflight mismatch: {path}")
                if not issues and analyze(args.h1_run, design) != h1:
                    issues.append("H1 report does not match reanalysis of supplied run")
        if issues:
            for issue in issues:
                print(f"BLOCKED: {issue}", file=sys.stderr)
            return 1
        result = {
            "schema": "inodefence-host-freeze-manifest-v1",
            "status": "inputs-consistent",
            "limitation": (
                "Supplied evidence compared; independent verification and execution "
                "authorization remain required."
            ),
            "input_sha256": dict(
                zip(("plan", "host1", "host2", "h1"), (item[1] for item in items), strict=True)
            ),
            "plan": plan,
            "hosts": [host1, host2],
            "differences": differences(host1, host2),
            "h1_decision": h1["decision"],
            "prereg_sha256": prereg_hash,
            "design_sha256": design_hash,
            "h1_preflight_sha256": preflight_hashes,
        }
        payload = (
            json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode()
        with args.output.open("xb") as output:
            output.write(payload)
        print(f"{digest(payload)}  {args.output}")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
