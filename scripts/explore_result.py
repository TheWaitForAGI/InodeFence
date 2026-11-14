"""Target-agnostic conversion of a controller loop report into the common campaign result.

Every target's explore hook (node-tar, oras-go, decompress) produces the same shape of loop
report (``case_records`` + ``violation_inputs``) and wants the same common
``inodefence-target-result-v1`` campaign result. This module does that conversion once, keyed on
``prepared.target`` -- no target-specific code and no per-target copies.
"""

from __future__ import annotations

import base64
from hashlib import sha256
from pathlib import Path

from scripts.run_target import PreparedTargetImage, engine_provenance

from inodefence.target_result import (
    CampaignInfo,
    CaseVerdict,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)

OBSERVED_CONTRACTS = ("C0", "C1", "C2")  # the effect path takes a full before/after snapshot


def build_campaign_result(
    report: dict, prepared: PreparedTargetImage, *, seed: int, budget: int
) -> tuple[TargetResult, dict[str, bytes]]:
    """Convert the loop report into the common campaign result, plus the violating TARs to save.

    A streaming report (``aggregate`` present) lists only the violating cases and carries the rest
    as aggregate counts (``runs_executed`` / ``terminations`` / ``unjudged_steps`` / ``errors``); a
    non-streaming report lists every case. Either way the verdict, run count and violation count are
    the same -- the common campaign block derives what the listed cases cannot show. Only violating
    cases get a saved input; ``repro_inputs`` is that subset. ``target`` comes from
    ``prepared.target``.
    """
    aggregate = report.get("aggregate")
    listed = (
        report.get("violation_cases", [])
        if aggregate is not None
        else report.get("case_records", [])
    )
    cases = tuple(
        CaseVerdict(
            f"step-{r['run_index']}",
            r["outcome"],
            r["c0"],
            r["c1"],
            r["c2"],
            termination=r.get("termination"),
            observation_complete=r.get("observation_complete"),
        )
        for r in listed
    )
    repro = []
    tar_files: dict[str, bytes] = {}
    first_violation: int | None = None
    for item in report.get("violation_inputs", []):
        run_index = item["run_index"]
        tar = base64.b64decode(item["tar_b64"])
        if sha256(tar).hexdigest() != item["tar_sha256"]:
            raise ValueError(f"violation input step-{run_index} failed its SHA-256 check")
        tar_path = f"inputs/step-{run_index}.tar"
        tar_files[tar_path] = tar
        repro.append(repro_input(f"step-{run_index}", tar_path, tar))
        rank = int(run_index) + 1
        first_violation = rank if first_violation is None else min(first_violation, rank)
    base = engine_provenance(prepared.image_ref)
    provenance = type(base)(
        base.engine_sha, base.engine_dirty, prepared.image_ref, prepared.image_id
    )
    if aggregate is not None:
        campaign = CampaignInfo(
            seed=seed,
            budget=budget,
            runs_to_first_violation=first_violation,
            runs_executed=aggregate.get("runs_executed"),
            errors=aggregate.get("errors"),
            unjudged_steps=aggregate.get("unjudged_steps"),
            terminations=aggregate.get("terminations"),
        )
    else:
        campaign = CampaignInfo(seed=seed, budget=budget, runs_to_first_violation=first_violation)
    result = TargetResult(
        target=prepared.target,
        axes=TargetAxes(target_version=prepared.version),
        mode=ResultMode.CAMPAIGN,
        observed_contracts=OBSERVED_CONTRACTS,
        cases=cases,
        repro_inputs=tuple(repro),
        provenance=provenance,
        campaign=campaign,
    )
    return result, tar_files


def write_result(out_dir: Path, result: TargetResult, tar_files: dict[str, bytes]) -> Path:
    """Write result.json and the violating TARs under ``out_dir``; refuse to overwrite."""
    result_path = out_dir / "result.json"
    if result_path.exists():
        raise FileExistsError(f"refusing to overwrite {result_path}")
    (out_dir / "inputs").mkdir(parents=True, exist_ok=True)
    for tar_path, data in tar_files.items():
        (out_dir / tar_path).write_bytes(data)
    result_path.write_text(result.dumps(), encoding="utf-8")
    return result_path
