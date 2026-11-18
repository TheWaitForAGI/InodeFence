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

from inodefence.drivers.run_target import (
    DEFAULT_MAX_UNJUDGED_RATIO,
    PreparedTargetImage,
    engine_provenance,
)
from inodefence.live_exploration import list_violation_cases, read_progress
from inodefence.target_result import (
    JUDGED,
    CampaignInfo,
    CaseVerdict,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)

OBSERVED_CONTRACTS = ("C0", "C1", "C2")  # the effect path takes a full before/after snapshot


def build_campaign_result(
    report: dict,
    prepared: PreparedTargetImage,
    *,
    seed: int,
    budget: int,
    max_unjudged_ratio: float | None = DEFAULT_MAX_UNJUDGED_RATIO,
    live_dir: Path | None = None,
    mutation_policy: str | None = None,
) -> tuple[TargetResult, dict[str, bytes]]:
    """Convert the loop report into the common campaign result, plus the violating TARs to save.

    A streaming report (``aggregate`` present) lists only the violating cases and carries the rest
    as aggregate counts (``runs_executed`` / ``terminations`` / ``unjudged_steps`` / ``errors``); a
    non-streaming report lists every case. Either way the verdict, run count and violation count are
    the same -- the common campaign block derives what the listed cases cannot show. Only violating
    cases get a saved input; ``repro_inputs`` is that subset. ``target`` comes from
    ``prepared.target``.

    When ``live_dir`` is given for a streaming run, the violating cases and their inputs are read
    from the live folder the loop wrote them to AS THEY OCCURRED (``<live>/violations/run-*/``),
    not from the report -- so a large or force-stopped run keeps every saved violation off-report
    and in memory bounded. The report's ``violation_capture`` aggregate (total / retained /
    dropped at the per-fingerprint cap) then rides in the campaign block. Without ``live_dir``
    (non-streaming, other targets, or a recorder-less test) the report's own
    ``violation_inputs`` are used, unchanged.

    ``mutation_policy`` is recorded as given; the caller passes it only after checking the loop
    ran it. Only such a run (the v2 grammar policy) can have build-invalid runs -- the builder
    could not represent the child, so nothing was extracted -- and for it the count is required:
    see :func:`build_invalid_runs`. ``campaign.build_invalid`` is then written when it is > 0. A
    run without ``mutation_policy`` is unchanged (no count is derived, the key never appears).
    """
    aggregate = report.get("aggregate")
    disk_sourced = aggregate is not None and live_dir is not None
    repro = []
    tar_files: dict[str, bytes] = {}
    first_violation: int | None = None
    if disk_sourced:
        assert live_dir is not None  # narrowed by disk_sourced
        cases_list: list[CaseVerdict] = []
        for record in list_violation_cases(live_dir):
            index = record["index"]
            case_id = f"step-{index}"
            cases_list.append(
                CaseVerdict(
                    case_id,
                    JUDGED,  # a saved violation is judged (the oracle ruled on the snapshots)
                    record.get("c0"),
                    record.get("c1"),
                    record.get("c2"),
                    termination=record.get("status"),
                    observation_complete=record.get("observation_complete"),
                )
            )
            tar = (live_dir / record["dir"] / record.get("tar", "input.tar")).read_bytes()
            if sha256(tar).hexdigest() != record["tar_sha256"]:
                raise ValueError(f"violation input {case_id} failed its SHA-256 check")
            tar_path = f"inputs/{case_id}.tar"
            tar_files[tar_path] = tar
            repro.append(repro_input(case_id, tar_path, tar))
            rank = int(index) + 1
            first_violation = rank if first_violation is None else min(first_violation, rank)
        cases = tuple(cases_list)
    else:
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
            max_unjudged_ratio=max_unjudged_ratio,
            violation_capture=report.get("violation_capture"),
            build_invalid=(
                build_invalid_runs(aggregate, live_dir) or None
                if mutation_policy is not None
                else None
            ),
            mutation_policy=mutation_policy,
        )
    else:
        campaign = CampaignInfo(
            seed=seed,
            budget=budget,
            runs_to_first_violation=first_violation,
            max_unjudged_ratio=max_unjudged_ratio,
            mutation_policy=_no_aggregate_policy(mutation_policy),
        )
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


class BuildInvalidUnknownError(RuntimeError):
    """A ``--mutation-policy`` run whose build-invalid count cannot be established exactly.

    A ``RuntimeError``: the run happened, so the explore drivers report it as ERROR (exit 2) and
    publish no result -- instead of leaving the key out, which would put build-invalid runs back
    into the un-judged ratio's denominator and loosen the ERROR ceiling without saying so.
    """


def build_invalid_runs(aggregate: dict, live_dir: Path | None = None) -> int:
    """The exact build-invalid count of a streaming run: ``runs_executed - sum(terminations)``.

    The loop's aggregate counts one termination per executed extraction, and a build-invalid run
    never reaches the extractor, so the difference is exact (QA check 33-B). When the live folder
    has a final snapshot covering the same runs, its own ``build_invalid`` count must agree.
    Anything that does not add up raises :class:`BuildInvalidUnknownError`.
    """
    runs = aggregate.get("runs_executed")
    terminations = aggregate.get("terminations")
    if (
        type(runs) is not int
        or not isinstance(terminations, dict)
        or not all(type(n) is int and n >= 0 for n in terminations.values())
    ):
        raise BuildInvalidUnknownError(
            "build-invalid count unknown: the loop report's aggregate has no runs/terminations; "
            "no result written"
        )
    count = runs - sum(terminations.values())
    if count < 0:
        raise BuildInvalidUnknownError(
            f"build-invalid count unknown: {sum(terminations.values())} terminations exceed "
            f"{runs} runs; no result written"
        )
    progress = read_progress(live_dir) if live_dir is not None else None
    if progress is not None and progress.get("runs_executed") == runs:
        block = progress.get("build_invalid")
        live = block.get("steps", 0) if isinstance(block, dict) else 0
        if live != count:
            raise BuildInvalidUnknownError(
                f"build-invalid count unknown: the loop report gives {count}, the live snapshot "
                f"{live}; no result written"
            )
    return count


def _no_aggregate_policy(mutation_policy: str | None) -> str | None:
    """A ``--mutation-policy`` run must stream (the count comes from the aggregate)."""
    if mutation_policy is not None:
        raise BuildInvalidUnknownError(
            "build-invalid count unknown: a --mutation-policy run produced a per-case report "
            "without the aggregate; no result written"
        )
    return None


class ResultExistsError(FileExistsError, ValueError):
    """An exploration result (or this run's loop report) is already there; nothing is overwritten.

    A ``FileExistsError`` as before, and also a ``ValueError`` so the explore drivers' existing
    setup path reports it in one line with exit 3 -- the code ``verify`` uses when its result
    already exists -- instead of a traceback.
    """


def existing_outputs(*paths: Path) -> list[Path]:
    """Which of this run's output paths (loop report, result folder's result.json) already exist.

    For a refusal before the run: an explore whose report or result is already in ``--out`` fails
    today only after the whole loop (the host copy of the report will not replace a file, and
    :func:`write_result` refuses), so the same condition can be refused first.
    """
    return [path for path in paths if path.exists()]


def refuse_existing(*paths: Path) -> None:
    """Raise :class:`ResultExistsError` naming what is already there (nothing is touched)."""
    found = existing_outputs(*paths)
    if found:
        raise ResultExistsError(
            f"{', '.join(str(path) for path in found)} already exists; choose another --out "
            "(nothing was run or overwritten)"
        )


def write_result(
    out_dir: Path,
    result: TargetResult,
    tar_files: dict[str, bytes],
    *,
    report: Path | None = None,
) -> Path:
    """Write result.json and the violating TARs under ``out_dir``; refuse to overwrite.

    ``report`` (the loop report this result was built from) is only named in the refusal, so the
    reader knows the run's own record was kept.
    """
    result_path = out_dir / "result.json"
    if result_path.exists():
        kept = f"; the loop report of this run is kept at {report}" if report is not None else ""
        raise ResultExistsError(
            f"refusing to overwrite {result_path}: choose another --out (nothing was "
            f"overwritten{kept})"
        )
    (out_dir / "inputs").mkdir(parents=True, exist_ok=True)
    for tar_path, data in tar_files.items():
        (out_dir / tar_path).write_bytes(data)
    result_path.write_text(result.dumps(), encoding="utf-8")
    return result_path
