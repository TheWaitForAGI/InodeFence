"""Judge the D042 stop/resume smoke against experiments/configs/stop-path-smoke-v1.md (#347).

Three subcommands:

* ``snapshot`` records one stage of a run (call it right after each call, and right before
  B-2, B-4 and the two B-5 calls so the injection is shown to be gone). It stores only
  what the criteria need: the event lines of ``cell-results.jsonl`` (no oracle values),
  the sha256 of every file of the output, counts and flags from ``summaries/index.json``
  and ``manifest-verification.json``, which summary files have which keys, gate verdict
  kinds, log markers, container destroy-event counts, host preflight/postflight problem
  counts, read-only docker state, whether ``HISTORICAL_IMAGE`` is set, and the exit code
  and stderr markers of the call just made.
* ``verify-tools`` runs ``analyze_exp0`` (B9) and ``make_raw_manifest --verify`` (A7) and
  keeps their exit codes and whether the analyzer output has a key, never its values.
* ``judge`` reads the snapshots and prints PASS/FAIL per criterion: A1-A8, N1, P1, B1-B9,
  C1, F1, X1-X3 (scenario B) and SA1-SA6 (scenario A, reported apart, not in the pass).

**No oracle value is read into a snapshot or printed.** Hit and first-time fields are only
checked for presence (A7); summaries only for keys; reports are never opened.

Stages of scenario B (stop-path-smoke-v1 section 4): ``b0`` (before B-1), ``b1`` (after
B-1), ``pre-b2``, ``b2``, ``pre-b4``, ``b4``, ``pre-b5a``, ``b5a``, ``pre-b5b``, ``b5b``, and
``tools`` (``verify-tools`` after B-5). Scenario A: ``a1`` (after the injected call),
``a-refused`` (the ``--resume-after-stop`` refused while U), ``a2`` (after the resume
following the ack), ``a-final`` (after a last call).

A7(ii), F1, B9 and C1 follow the wording corrected on 2026-11-11 (the #346 text misread the
code, so a correct run would always fail them; intent and thresholds unchanged, verifier
agreed): A7(ii) reads the manifest result from ``manifest-verification.json`` (the index
keeps ``{generated: null, verified: null}`` on success); F1 expects invalid cells to have a
summary file without ``dense_detail`` whose ``invalid_reason`` contains ``no-record:``; C1
allows exactly ``registration.json``, ``matrix.json`` and ``manifest-verification.json`` to
change and compares the raw manifest without those three lines. Two more of the same kind followed
the same day: A7(ii)'s ``--verify`` runs on a copy of the manifest without the
``manifest-verification.json`` line (rewritten after the manifest), and N1 accepts exit 0 or 1
(a stopped call exits 1). tests/test_stop_path_smoke_end_to_end.py runs the procedure with the
real launcher and fixes that a correct run passes every criterion.
SA1 (scenario A) is judged by the structure the launcher guarantees, not by a count (W4
wording, 2026-11-11): the starts before the stop are U cells (one or more, once each), cells
that ended S before the earliest U cell's end line, and starts the gate denied; U cells plus
denied starts are at most jobs. SA5 needs an ack for every U cell. X1 falls back to the
attempt logs when the docker event collector failed (F-3). Pass ``--manifest`` (the
``--manifest-out`` path, outside the output and the checkout) to the ``pre-b5b`` and ``b5b``
snapshots.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

CELL_RESULTS = "cell-results.jsonl"
INDEX = Path("summaries/index.json")
VERIFICATION = "manifest-verification.json"
OUTCOME_KEYS = ("hit", "t_first", "t_first_event", "t_first_censored")
STOP, RESUME = "infrastructure-stop", "infrastructure-resume"
START_DENIED = "start_denied"
RECORDED_STATES = ("complete", "abort-final")
APPROVAL = re.compile(r"D042-smoke-[12]-[AB]-\d{8}-\d{4}")
LOG_MARKERS = {
    "failed_effect_demo_historical": "FAILED at step: effect-demo-historical",
    "no_such_image": "No such image: inodefence-node-tar-effect:does-not-exist",
    "unknown_marker": "INODEFENCE_CLEANUP_UNKNOWN:",
    # The smoke script's cleanup trap logs nothing on success; a failed step logs this.
    "failed_cleanup": "FAILED cleanup",
}
STDERR_MARKERS = {
    "stop_in_effect": "infrastructure stop in effect",
    "gate_closed": "start gate still closed",
}
#: C1 (corrected 2026-11-11): files every call rewrites; the only exceptions allowed.
C1_EXCEPTIONS = ("registration.json", "matrix.json", "manifest-verification.json")
B_STAGES = ("b0", "b1", "pre-b2", "b2", "pre-b4", "b4", "pre-b5a", "b5a", "pre-b5b", "b5b")
A_STAGES = ("a1", "a-refused", "a2", "a-final")

Docker = Callable[..., str]


# ---- snapshot -------------------------------------------------------------------------------


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _events(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            events.append(record)
    return events


def index_facts(index: Any) -> dict[str, Any] | None:
    """Counts and flags only. Cell entries are reduced to key presence and their state."""
    if not isinstance(index, Mapping):
        return None
    cells = [cell for cell in index.get("cells") or () if isinstance(cell, Mapping)]
    interim = _map(index.get("interim"))
    completeness = _map(index.get("cell_completeness"))
    manifest = _map(interim.get("manifest"))
    return {
        "cells": len(cells),
        "outcomes_redacted": index.get("outcomes_redacted"),
        "interim_redacted": interim.get("redacted"),
        "interim_reasons": len(interim.get("reasons") or ()),
        "interim_integrity_problems": len(interim.get("integrity_problems") or ()),
        "interim_manifest": {
            "generated": manifest.get("generated"),
            "verified": manifest.get("verified"),
        },
        "cells_with_outcome_keys": sum(any(key in cell for key in OUTCOME_KEYS) for cell in cells),
        "cells_with_summary": sum(cell.get("summary") is not None for cell in cells),
        "invalid_run_ids": sorted(str(cell.get("run_id")) for cell in cells if cell.get("invalid")),
        "invalid_count": index.get("invalid_count"),
        "cell_states": dict(interim.get("cell_states") or {}),
        "completeness": {
            key: completeness.get(key)
            for key in ("complete", "aborts", "no_record", "record_inconsistent", "unattempted")
        },
        "infrastructure_stopped": completeness.get("infrastructure_stopped"),
        "stops": len(completeness.get("infrastructure_stops") or ()),
        "resume_approval_refs": [
            item.get("approval_ref")
            for item in completeness.get("infrastructure_resumes") or ()
            if isinstance(item, Mapping)
        ],
    }


def summary_facts(output: Path) -> dict[str, dict[str, bool]]:
    facts = {}
    for path in sorted((output / "summaries").glob("*.summary.json")):
        record = _json(path)
        if not isinstance(record, Mapping):
            facts[path.name] = {"readable": False}
            continue
        reason = record.get("invalid_reason")
        facts[path.name.removesuffix(".summary.json")] = {
            "readable": True,
            "dense_detail": "dense_detail" in record,
            "record_inconsistent_prefix": "record_inconsistent_prefix" in record,
            "invalid_no_record": isinstance(reason, str) and "no-record:" in reason,
        }
    return facts


def log_facts(output: Path) -> dict[str, dict[str, bool]]:
    facts = {}
    # Cell logs live under <output>/<target>/..., earlier attempts under attempts/.
    for path in sorted(output.rglob("*.log")):
        text = path.read_text(encoding="utf-8", errors="replace")
        entry = {name: marker in text for name, marker in LOG_MARKERS.items()}
        entry["engine_set"] = re.search(r"engine=\S", text) is not None
        facts[str(path.relative_to(output))] = entry
    return facts


def destroy_counts(output: Path) -> dict[str, int]:
    """Container destroy events per name (docker metadata from the host recording)."""
    counts: dict[str, int] = {}
    for path in (output / "host").glob("events*.jsonl"):
        for event in _events(path.read_text(encoding="utf-8", errors="replace")):
            name = _map(_map(event.get("Actor")).get("Attributes")).get("name")
            if event.get("Action") == "destroy" and isinstance(name, str):
                counts[name] = counts.get(name, 0) + 1
    return counts


def flight_facts(output: Path, kind: str) -> list[dict[str, Any]]:
    facts = []
    for path in sorted((output / "host").glob(f"{kind}-*.json")):
        record = _json(path)
        record = record if isinstance(record, Mapping) else {}
        facts.append(
            {
                "file": path.name,
                "problems": len(record.get("problems") or ()),
                "expected_images": record.get("expected_images") is not None,
            }
        )
    return facts


def events_recorder_failed(output: Path, matrix: Any) -> bool:
    """True when the docker event collector failed: a recorder-failures.jsonl line naming the
    events, or a recording note of the host records (matrix.json host_guards)."""
    failures = output / "host" / "recorder-failures.jsonl"
    text = failures.read_text(encoding="utf-8", errors="replace") if failures.is_file() else ""
    lines = [e for e in _events(text) if "event" in f"{e.get('recorder')} {e.get('message')}"]
    notes = _map(_map(matrix).get("host_guards")).get("recording_notes") or []
    return bool(lines) or any("docker events" in str(note) for note in notes)


def docker_state(docker: Docker) -> dict[str, Any]:
    return {
        "containers": docker(
            "ps", "-a", "--filter", "name=inodefence-", "--format", "{{.Names}}"
        ).split(),
        "volumes": docker(
            "volume", "ls", "--filter", "name=inodefence-local-", "--format", "{{.Name}}"
        ).split(),
        "context": docker("context", "show"),
    }


def manifest_facts(manifest: Path | None) -> dict[str, Any] | None:
    """sha256 of the raw manifest lines other than the three C1 exception files."""
    if manifest is None or not manifest.is_file():
        return None
    kept = [
        line
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.split("  ", 1)[-1] not in {f"./{name}" for name in C1_EXCEPTIONS}
    ]
    return {"lines": len(kept), "sha256": hashlib.sha256("\n".join(kept).encode()).hexdigest()}


def take_snapshot(
    output: Path,
    stage: str,
    *,
    manifest: Path | None = None,
    exit_code: int | None = None,
    stderr: str | None = None,
    docker: Docker | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    environ = os.environ if environ is None else environ
    results = output / CELL_RESULTS
    text = results.read_text(encoding="utf-8") if results.is_file() else ""
    gate_dir = output / "start-gate"
    verification = _json(output / VERIFICATION)
    verification = verification if isinstance(verification, Mapping) else None
    matrix = _json(output / "matrix.json")
    return {
        "stage": stage,
        "env_historical_image": "HISTORICAL_IMAGE" in environ,
        "exit_code": exit_code,
        "stderr": None
        if stderr is None
        else {name: marker in stderr for name, marker in STDERR_MARKERS.items()},
        "cell_results_text": text,
        "files": {
            str(path.relative_to(output)): _sha(path)
            for path in sorted(output.rglob("*"))
            if path.is_file()
        }
        if output.is_dir()
        else {},
        "index": index_facts(_json(output / INDEX)),
        "verification": None
        if verification is None
        else {
            "generated": (verification.get("raw_manifest") or {}).get("generated"),
            "verified": (verification.get("verification") or {}).get("verified"),
        },
        "summaries": summary_facts(output),
        "matrix_not_started": sorted(matrix.get("cells_not_started") or ())
        if isinstance(matrix, Mapping)
        else None,
        "disk_paused": sorted(_map(_map(matrix).get("disk_pauses"))),
        "events_recorder_failed": events_recorder_failed(output, matrix),
        "gate": {
            path.name.removesuffix(".verdict"): path.read_text(encoding="utf-8")[:1]
            for path in sorted(gate_dir.glob("*.verdict"))
        },
        "gate_acknowledged": len([p for p in (gate_dir / "acknowledged").glob("*") if p.is_dir()]),
        "logs": log_facts(output),
        "destroy_events": destroy_counts(output),
        "preflight": flight_facts(output, "preflight"),
        "postflight": flight_facts(output, "postflight"),
        "docker": None if docker is None else docker_state(docker),
        "manifest": manifest_facts(manifest),
    }


def _has_key(value: Any, key: str) -> bool:
    if isinstance(value, Mapping):
        return key in value or any(_has_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_has_key(item, key) for item in value)
    return False


REPO = Path(__file__).resolve().parents[1]
#: Rewritten by the launcher after the manifest is made and verified, so A7(ii) verifies a
#: copy of the manifest without its line (corrected 2026-11-11). registration.json and
#: matrix.json are written before the manifest and stay in the comparison.
REWRITTEN_AFTER_MANIFEST = "manifest-verification.json"


def manifest_without_rewritten(manifest: Path, copy: Path) -> Path:
    lines = manifest.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [
        line
        for line in lines
        if line.rstrip("\n").split("  ", 1)[-1] != f"./{REWRITTEN_AFTER_MANIFEST}"
    ]
    copy.write_text("".join(kept), encoding="utf-8")
    return copy


def verify_tools(output: Path, manifest: Path, python: str = sys.executable) -> dict[str, Any]:
    """Exit codes and key presence only; the analyzer output is deleted unread."""
    with tempfile.TemporaryDirectory() as scratch:
        analysis = Path(scratch) / "analysis.json"
        analyze = subprocess.run(
            [
                python,
                "-m",
                "scripts.analyze_exp0",
                "--index",
                str(output / INDEX),
                "--format",
                "json",
                "--output",
                str(analysis),
            ],
            capture_output=True,
            check=False,
            cwd=REPO,
        )
        has_key = analysis.is_file() and _has_key(_json(analysis), "number_blocks_invalid_excluded")
        copy = manifest_without_rewritten(manifest, Path(scratch) / "manifest.sha256")
        verify = subprocess.run(
            [
                python,
                str(REPO / "scripts" / "make_raw_manifest.py"),
                "--verify",
                str(copy),
                "--root",
                str(output),
            ],
            capture_output=True,
            check=False,
        )
    return {
        "stage": "tools",
        "analyze_rc": analyze.returncode,
        "analyze_has_number_blocks_invalid_excluded": has_key,
        "manifest_verify_rc": verify.returncode,
    }


# ---- judge ----------------------------------------------------------------------------------


def _result(ok: bool, **evidence: Any) -> dict[str, Any]:
    return {"result": "PASS" if ok else "FAIL", "evidence": evidence}


def _starts(
    events: Iterable[Mapping[str, Any]], run_id: str | None = None
) -> list[Mapping[str, Any]]:
    return [
        e
        for e in events
        if e.get("event") == "start" and (run_id is None or e.get("run_id") == run_id)
    ]


def _attempt_files(files: Mapping[str, str], run_id: str, attempt: int) -> dict[str, str]:
    prefix = f"attempts/{run_id}.attempt{attempt}."
    return {name: digest for name, digest in files.items() if name.startswith(prefix)}


def _residual_free(snapshot: Mapping[str, Any]) -> bool:
    docker = snapshot.get("docker")
    return bool(docker) and not docker["containers"] and not docker["volumes"]


def judge_b(
    snaps: Mapping[str, Mapping[str, Any]],
    tools: Mapping[str, Any] | None,
    *,
    cause_logged_at: float | None,
    round_number: int,
) -> dict[str, dict[str, Any]]:
    missing = [stage for stage in B_STAGES if stage not in snaps]
    if missing or tools is None:
        return {"inputs": _result(False, missing_stages=missing, tools=tools is not None)}
    b1, b2, b4, b5a, b5b = snaps["b1"], snaps["b2"], snaps["b4"], snaps["b5a"], snaps["b5b"]
    ev = {
        stage: _events(snaps[stage]["cell_results_text"])
        for stage in ("b1", "b2", "b4", "b5a", "b5b")
    }
    i1, i5 = b1["index"] or {}, b5b["index"] or {}
    states1 = i1.get("cell_states") or {}
    planned = sorted(states1)
    no_record = sorted(run for run, state in states1.items() if state == "no-record")
    started1 = sorted({e["run_id"] for e in _starts(ev["b1"])})
    out: dict[str, dict[str, Any]] = {}

    out["A1"] = _result(
        sum(e.get("event") == STOP for e in ev["b1"]) == 1
        and b1["exit_code"] in (0, 1)
        and i1.get("infrastructure_stopped") is True,
        stop_lines=sum(e.get("event") == STOP for e in ev["b1"]),
        exit_code=b1["exit_code"],
        stopped=i1.get("infrastructure_stopped"),
    )
    out["A2"] = _result(
        (i1.get("completeness") or {}).get("no_record") in (3, 4),
        no_record=(i1.get("completeness") or {}).get("no_record"),
    )
    a3_problems = []
    for run in no_record:
        lines = ev["b1"]
        starts = [
            n for n, e in enumerate(lines) if e.get("event") == "start" and e.get("run_id") == run
        ]
        ends = [
            n
            for n, e in enumerate(lines)
            if e.get("event") == "end" and e.get("run_id") == run and e.get("attempt") == 1
        ]
        attempts = [lines[n].get("attempt") for n in starts]
        if attempts != [1, 2] or not ends:
            a3_problems.append(f"{run}: starts {attempts}, attempt-1 end {bool(ends)}")
            continue
        jobs = int(lines[starts[0]].get("jobs") or 1)
        between = [
            e
            for e in lines[ends[0] + 1 : starts[1]]
            if e.get("event") == "start" and e.get("run_id") != run
        ]
        # A3(ii) is not applicable to a cell that waited for disk (matrix.json disk_pauses).
        paused = run in (b1.get("disk_paused") or ())
        if starts[1] < ends[0] or (len(between) > jobs - 1 and not paused):
            a3_problems.append(f"{run}: {len(between)} other starts before the retry")
        first = _attempt_files(b1["files"], run, 1)
        if not first or first != _attempt_files(b5b["files"], run, 1):
            a3_problems.append(f"{run}: attempt-1 files missing or changed")
    out["A3"] = _result(
        not a3_problems and bool(no_record),
        problems=a3_problems,
        ii_not_applicable=sorted(set(no_record) & set(b1.get("disk_paused") or ())),
    )
    first_only = [
        run
        for run in started1
        if len(_starts(ev["b1"], run)) == 1
        and any(e.get("event") == "end" and e.get("run_id") == run for e in ev["b1"])
    ]
    out["A5"] = _result(len(first_only) in (0, 1), first_attempt_only=len(first_only))
    # A4: the cells with no start line are all in cells_not_started. The launcher also lists
    # there a cell whose first attempt ended at the stop (its retry did not start, the A5 cell).
    not_started = [run for run in planned if run not in started1]
    listed = set(b1["matrix_not_started"] or ())
    out["A4"] = _result(
        len(started1) in (3, 4)
        and set(not_started) <= listed
        and listed - set(not_started) <= set(first_only),
        started=len(started1),
        unstarted_listed=set(not_started) <= listed,
        also_listed=sorted(listed - set(not_started)),
    )

    # X1: every no-record attempt verified clean. Attempt 1: the gate let attempt 2 start
    # and no stop names the gate; attempt 2: the gate verdict is S. Each attempt destroyed
    # its controller (host docker events).
    gate_stops = [
        e
        for e in ev["b1"]
        if e.get("event") == STOP
        and ("cleanup unknown" in str(e.get("reason")) or "start gate" in str(e.get("reason")))
    ]
    x1_problems = [
        f"{run}: verdict {b1['gate'].get(run)}" for run in no_record if b1["gate"].get(run) != "S"
    ]
    # F-3: the destroy events come from a record-only collector. When it failed, judge each
    # no-record attempt's log instead: no failed cleanup step and no unknown marker (the trap
    # logs nothing on success; S itself is written only after the trap verified cleanup).
    events_failed = bool(b1.get("events_recorder_failed"))
    for run in no_record:
        if events_failed:
            for name in (f"attempts/{run}.attempt1.log", f"{run}.log"):
                facts = next((v for k, v in b1["logs"].items() if k.endswith(name)), None)
                if not facts or facts.get("failed_cleanup") or facts.get("unknown_marker"):
                    x1_problems.append(f"{name}: cleanup trace")
            continue
        destroyed = sum(count for name, count in b1["destroy_events"].items() if name.endswith(run))
        if destroyed < 2:
            x1_problems.append(f"{run}: {destroyed} controller destroy events for 2 attempts")
    out["X1"] = _result(
        not x1_problems and not gate_stops,
        problems=x1_problems,
        gate_stops=len(gate_stops),
        cleanup_source="attempt logs (events recorder failed)" if events_failed else "events",
    )
    out["X2"] = _result(
        all(_residual_free(snaps[stage]) for stage in ("b1", "b2", "b4", "b5a", "b5b"))
        and all(item["problems"] == 0 for item in b5b["postflight"])
        and bool(b5b["postflight"]),
        residual_free={
            stage: _residual_free(snaps[stage]) for stage in ("b1", "b2", "b4", "b5a", "b5b")
        },
        postflight_problems=[item["problems"] for item in b5b["postflight"]],
    )
    out["A6"] = _result(
        (snaps["b0"].get("docker") or {}).get("context") == (b1.get("docker") or {}).get("context")
        and _residual_free(b1)
        and out["X1"]["result"] == "PASS",
        context_unchanged=(snaps["b0"].get("docker") or {}).get("context")
        == (b1.get("docker") or {}).get("context"),
        residual_free=_residual_free(b1),
        x1=out["X1"]["result"],
    )

    def redacted(snapshot: Mapping[str, Any]) -> bool:
        index = snapshot["index"] or {}
        return (
            index.get("outcomes_redacted") is True
            and index.get("interim_redacted") is True
            and index.get("interim_reasons", 0) > 0
            and index.get("cells_with_outcome_keys") == 0
            and index.get("cells_with_summary") == 0
            and not snapshot["summaries"]
        )

    verification = b5b["verification"] or {}
    out["A7"] = _result(
        redacted(b1)
        and redacted(b2)
        and verification.get("generated") is True
        and verification.get("verified") is True
        and i5.get("interim_manifest") == {"generated": None, "verified": None}
        and tools["manifest_verify_rc"] == 0,
        redacted_while_stopped={"b1": redacted(b1), "b2": redacted(b2)},
        manifest_generated=verification.get("generated"),
        manifest_verified=verification.get("verified"),
        manifest_verify_rc=tools["manifest_verify_rc"],
        reading="manifest-verification.json (index keeps nulls on success; corrected 2026-11-11)",
    )
    a8_problems = []
    for run in no_record:
        for name in (f"attempts/{run}.attempt1.log", f"{run}.log"):
            facts = next((v for k, v in b1["logs"].items() if k.endswith(name)), None)
            if not facts or not (
                facts["failed_effect_demo_historical"]
                and facts["no_such_image"]
                and facts["engine_set"]
                and not facts["unknown_marker"]
            ):
                a8_problems.append(name)
    out["A8"] = _result(not a8_problems and bool(no_record), problems=a8_problems)
    # N1 (corrected 2026-11-11): exit 0 or 1, not a signal; a stopped call exits 1 while the
    # no-record cells keep the G1 verdict from passing.
    out["N1"] = _result(
        len(_starts(ev["b2"])) == len(_starts(ev["b1"]))
        and b2["exit_code"] in (0, 1)
        and bool(b2["stderr"] and b2["stderr"]["stop_in_effect"]),
        new_starts=len(_starts(ev["b2"])) - len(_starts(ev["b1"])),
        exit_code=b2["exit_code"],
    )
    resumes = [e for e in ev["b4"] if e.get("event") == RESUME]
    resume = resumes[0] if len(resumes) == 1 else {}
    resume_time = (resume.get("clocks") or {}).get("realtime")
    out["P1"] = _result(
        cause_logged_at is not None
        and isinstance(resume_time, (int, float))
        and cause_logged_at < resume_time
        and bool(resume.get("approval_ref")),
        cause_before_resume=cause_logged_at is not None
        and isinstance(resume_time, (int, float))
        and cause_logged_at < resume_time,
    )
    approval = resume.get("approval_ref")
    out["B1"] = _result(
        isinstance(approval, str)
        and APPROVAL.fullmatch(approval) is not None
        and approval in (b4["index"] or {}).get("resume_approval_refs", []),
        format_ok=isinstance(approval, str) and APPROVAL.fullmatch(approval) is not None,
    )
    stop_lines = [e for e in ev["b1"] if e.get("event") == STOP]
    out["B2"] = _result(
        (b4["index"] or {}).get("infrastructure_stopped") is False
        and [e for e in ev["b4"] if e.get("event") == STOP][: len(stop_lines)] == stop_lines,
        stopped_after_resume=(b4["index"] or {}).get("infrastructure_stopped"),
    )
    out["B3"] = _result(
        all(len(_starts(ev["b5b"], run)) == 2 for run in no_record) and bool(no_record),
        starts={run: len(_starts(ev["b5b"], run)) for run in no_record},
    )
    b4_problems = []
    for run in first_only:
        later = _starts(ev["b4"], run)[1:]
        if [e.get("attempt") for e in later] != [2]:
            b4_problems.append(run)
    out["B4"] = _result(not b4_problems, problems=b4_problems)
    states5 = i5.get("cell_states") or {}
    others = [run for run in planned if run not in no_record]
    pending_abort = [run for run in others if states5.get(run) == "abort-pending"]
    out["B5"] = _result(
        bool(others) and all(states5.get(run) in RECORDED_STATES for run in others),
        not_recorded=[run for run in others if states5.get(run) not in RECORDED_STATES],
        # The targets form has no abort-pending state (cell_completeness.CELL_STATES) and
        # refuses --finalize-abort; if one appears, the run is not the targets form.
        **({"abort_pending_not_targets_form": pending_abort} if pending_abort else {}),
    )
    resumed_at = next((n for n, e in enumerate(ev["b4"]) if e.get("event") == RESUME), None)
    ran_after = (
        sorted(
            {e["run_id"] for e in ev["b4"][(resumed_at or 0) + 1 :] if e.get("event") == "start"}
        )
        if resumed_at is not None
        else []
    )
    calls_missing = [
        run for run in ran_after if not any(n.endswith(f"{run}.calls.jsonl") for n in b5b["files"])
    ]
    clocks_missing = [
        e.get("run_id")
        for e in ev["b5b"]
        if e.get("event") in ("start", "end")
        and not {"realtime", "monotonic"} <= set(e.get("clocks") or {})
    ]
    out["B6"] = _result(
        bool(ran_after) and not calls_missing and not clocks_missing,
        ran_after_resume=len(ran_after),
        calls_missing=calls_missing,
        clocks_missing=len(clocks_missing),
    )
    chain = ["b1", "b2", "b4", "b5a", "b5b"]
    prefix_ok = {
        f"{a}->{b}": snaps[b]["cell_results_text"].startswith(snaps[a]["cell_results_text"])
        for a, b in zip(chain, chain[1:], strict=False)
    }
    out["B7"] = _result(all(prefix_ok.values()), prefix=prefix_ok)
    completeness = i5.get("completeness") or {}
    recount = {
        "complete": sum(state == "complete" for state in states5.values()),
        "no_record": sum(state == "no-record" for state in states5.values()),
        "record_inconsistent": sum(state == "record-inconsistent" for state in states5.values()),
        "unattempted": sum(state == "unattempted" for state in states5.values()),
    }
    out["B8"] = _result(
        all(completeness.get(key) == value for key, value in recount.items())
        and completeness.get("no_record") == len(no_record),
        recount=recount,
        recorded={key: completeness.get(key) for key in recount},
    )
    out["B9"] = _result(
        i5.get("invalid_run_ids") == no_record
        and i5.get("invalid_count") == len(no_record)
        and i5.get("interim_integrity_problems") == 0
        and tools["analyze_rc"] == 0
        and tools["analyze_has_number_blocks_invalid_excluded"] is True,
        invalid_equals_no_record=i5.get("invalid_run_ids") == no_record,
        analyze_rc=tools["analyze_rc"],
    )
    # C1 (corrected 2026-11-11): every output file except the three a call rewrites is
    # byte-identical (cell-results, cell evidence, attempts/, start gate, host/ records — a
    # call with nothing pending writes no pre/postflight —, index and summaries), no new
    # start line, and the raw manifest equal apart from the three exception lines.
    changed = sorted(
        name
        for name in set(b5a["files"]) | set(b5b["files"])
        if name not in C1_EXCEPTIONS and b5a["files"].get(name) != b5b["files"].get(name)
    )
    manifests = (snaps["pre-b5b"].get("manifest"), b5b.get("manifest"))
    out["C1"] = _result(
        not changed
        and len(_starts(ev["b5b"])) == len(_starts(ev["b5a"]))
        and manifests[0] is not None
        and manifests[0] == manifests[1],
        changed=changed,
        new_starts=len(_starts(ev["b5b"])) - len(_starts(ev["b5a"])),
        manifest_equal_without_exceptions=manifests[0] is not None and manifests[0] == manifests[1],
        exceptions=list(C1_EXCEPTIONS),
        reading="exceptions registration/matrix/manifest-verification (corrected 2026-11-11)",
    )
    inconsistent = {run for run, state in states5.items() if state == "record-inconsistent"}
    f1_problems = []
    for run in planned:
        facts = b5b["summaries"].get(run)
        if facts is None or not facts.get("readable"):
            f1_problems.append(f"{run}: no readable summary")
        elif run in no_record:
            if facts["dense_detail"] or not facts["invalid_no_record"]:
                f1_problems.append(f"{run}: invalid summary keys")
        elif not facts["dense_detail"]:
            f1_problems.append(f"{run}: no dense_detail")
        if facts and facts.get("record_inconsistent_prefix") and run not in inconsistent:
            f1_problems.append(f"{run}: record_inconsistent_prefix")
    out["F1"] = _result(
        not f1_problems,
        problems=f1_problems,
        round=round_number,
        reading="invalid cells have a summary without dense_detail (corrected 2026-11-11)",
    )
    pre_env = {
        stage: snaps[stage]["env_historical_image"]
        for stage in ("pre-b2", "pre-b4", "pre-b5a", "pre-b5b")
    }
    resumed_logs_clean = all(
        not facts["no_such_image"]
        for name, facts in b5b["logs"].items()
        if not name.startswith("attempts/")
        and any(name.endswith(f"{run}.log") for run in ran_after)
    )
    later_preflights = [item for item in b5b["preflight"] if item not in b1["preflight"]]
    out["X3"] = _result(
        not any(pre_env.values())
        and resumed_logs_clean
        and bool(later_preflights)
        and all(item["problems"] == 0 and item["expected_images"] for item in later_preflights),
        historical_image_set=pre_env,
        resumed_logs_clean=resumed_logs_clean,
        later_preflights=len(later_preflights),
    )
    return out


def judge_a(snaps: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    missing = [stage for stage in A_STAGES if stage not in snaps]
    if missing:
        return {"inputs": _result(False, missing_stages=missing)}
    ev1 = _events(snaps["a1"]["cell_results_text"])
    ev2 = _events(snaps["a2"]["cell_results_text"])
    stop_at = [n for n, e in enumerate(ev1) if e.get("event") == STOP]
    jobs = max((int(e.get("jobs") or 1) for e in _starts(ev1)), default=1)
    reason = str(ev1[stop_at[0]].get("reason")) if stop_at else ""
    resumes = [e for e in ev2 if e.get("event") == RESUME]
    acks = (resumes[0].get("gate_acks") or []) if resumes else []
    refused = snaps["a-refused"]
    # SA1 (corrected 2026-11-11): the gate admits starts while the U cell still runs (its
    # lifetime lock is held, no verdict yet), so how many cells start before the U is timing.
    # What holds by code: every start before the stop line is the U cell, a cell that ran and
    # ended S, or an attempt the gate denied (end line with start_denied, target never ran);
    # after the U each other worker writes at most one denied start before the stop
    # (gate_stop -> guard.force_stop, then authorize_attempt refuses), so denied <= jobs - 1.
    gate = snaps["a1"].get("gate") or {}
    before = ev1[: stop_at[0]] if stop_at else []
    denied = {
        (e.get("run_id"), e.get("attempt"))
        for e in before
        if e.get("event") == "end" and e.get(START_DENIED) is not None
    }
    unknown = sorted(cell for cell, verdict in gate.items() if verdict == "U")
    kinds: dict[str, int] = {"unknown": 0, "ran_clean": 0, "denied": 0, "other": 0}
    unknown_starts = {cell: len(_starts(before, cell)) for cell in unknown}
    # A U is committed before its cell's end line (the child records it; the launcher writes
    # the end line after require_clean), so the earliest U cell's end line is an upper bound
    # for the U commit in the file order.
    u_ends = [
        n
        for n, e in enumerate(ev1)
        if e.get("event") == "end" and e.get("run_id") in unknown and e.get(START_DENIED) is None
    ]
    first_u_end = min(u_ends) if u_ends else len(ev1)
    clean_after = 0
    not_denied_after = 0
    for n, start in enumerate(before):
        if start.get("event") != "start":
            continue
        is_denied = (start.get("run_id"), start.get("attempt")) in denied
        if n > first_u_end and not is_denied:
            not_denied_after += 1
        if gate.get(str(start.get("run_id"))) == "S" and not is_denied and n > first_u_end:
            clean_after += 1
    for start in _starts(before):
        run, attempt = start.get("run_id"), start.get("attempt")
        if (run, attempt) in denied:
            kinds["denied"] += 1
        elif run in unknown:
            kinds["unknown"] += 1
        elif gate.get(str(run)) == "S":
            kinds["ran_clean"] += 1
        else:
            kinds["other"] += 1
    return {
        "SA1": _result(
            len(stop_at) == 1
            and ("cleanup unknown" in reason or "start gate denied" in reason)
            and len(unknown) >= 1
            and all(count == 1 for count in unknown_starts.values())
            and kinds["other"] == 0
            and len(unknown) + kinds["denied"] <= jobs
            and clean_after == 0
            and not_denied_after == 0,
            stop_lines=len(stop_at),
            starts_before_stop=kinds,
            unknown_cells=len(unknown),
            unknown_starts=unknown_starts,
            clean_starts_after_first_u_end=clean_after,
            non_denied_starts_after_first_u_end=not_denied_after,
            jobs=jobs,
            reading="starts before the stop: U cells (>= 1, once each), cells ended S before "
            "the earliest U end line, denied starts; U cells + denied <= jobs (W4 2026-11-11)",
        ),
        "SA2": _result(
            bool(stop_at) and not _starts(ev1[stop_at[0] + 1 :]),
            starts_after_stop=len(_starts(ev1[stop_at[0] + 1 :])) if stop_at else None,
        ),
        "SA3": _result(
            refused["exit_code"] == 2
            and bool(refused["stderr"] and refused["stderr"]["gate_closed"]),
            exit_code=refused["exit_code"],
        ),
        "SA4": _result(snaps["a2"]["exit_code"] == 0, exit_code=snaps["a2"]["exit_code"]),
        "SA5": _result(
            len(resumes) == 1
            and bool(resumes[0].get("approval_ref"))
            and len(acks) >= max(len(unknown), 1)
            and set(unknown) <= {ack.get("cell") for ack in acks}
            and all({"path", "cell", "note_sha256"} <= set(ack) for ack in acks),
            resumes=len(resumes),
            gate_acks=len(acks),
            unknown_cells=len(unknown),
        ),
        "SA6": _result(
            all(_residual_free(snaps[stage]) for stage in A_STAGES)
            and all(item["problems"] == 0 for item in snaps["a-final"]["postflight"]),
            residual_free={stage: _residual_free(snaps[stage]) for stage in A_STAGES},
        ),
    }


def load_snapshots(directory: Path) -> dict[str, dict[str, Any]]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--output", type=Path, required=True)
    snap.add_argument("--snapshots", type=Path, required=True)
    snap.add_argument("--stage", required=True, choices=(*B_STAGES, *A_STAGES))
    snap.add_argument("--exit-code", type=int)
    snap.add_argument("--stderr", type=Path, help="the stderr of the call just made")
    snap.add_argument("--context", default=None)
    snap.add_argument("--no-docker", action="store_true", help="tests only")
    snap.add_argument("--manifest", type=Path, help="the raw manifest (--manifest-out) to hash")
    tools = sub.add_parser("verify-tools")
    tools.add_argument("--output", type=Path, required=True)
    tools.add_argument("--snapshots", type=Path, required=True)
    tools.add_argument("--manifest", type=Path, required=True)
    judge = sub.add_parser("judge")
    judge.add_argument("--snapshots", type=Path, required=True)
    judge.add_argument("--scenario-a-snapshots", type=Path)
    judge.add_argument("--round", type=int, choices=(1, 2), required=True)
    judge.add_argument("--cause-logged-at", type=float, help="realtime of the W2 cause LOG line")
    judge.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "snapshot":
        from scripts import launcher_guards as guards

        prefix = ("--context", args.context) if args.context else ()
        docker = None if args.no_docker else (lambda *call: guards.docker_cli(*prefix, *call))
        stderr = args.stderr.read_text(encoding="utf-8", errors="replace") if args.stderr else None
        record = take_snapshot(
            args.output,
            args.stage,
            manifest=args.manifest,
            exit_code=args.exit_code,
            stderr=stderr,
            docker=docker,
        )
        args.snapshots.mkdir(parents=True, exist_ok=True)
        target = args.snapshots / f"{args.stage}.json"
        if target.exists():
            print(f"{target} exists; a stage is recorded once", file=sys.stderr)
            return 2
        target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"snapshot {args.stage}: {len(record['files'])} files")
        return 0
    if args.command == "verify-tools":
        record = verify_tools(args.output, args.manifest)
        args.snapshots.mkdir(parents=True, exist_ok=True)
        (args.snapshots / "tools.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(record))
        return 0
    snaps = load_snapshots(args.snapshots)
    report: dict[str, Any] = {
        "schema": "inodefence-stop-path-smoke-judgement-v1",
        "criteria_file": "experiments/configs/stop-path-smoke-v1.md",
        "round": args.round,
        "scenario_b": judge_b(
            {k: v for k, v in snaps.items() if k != "tools"},
            snaps.get("tools"),
            cause_logged_at=args.cause_logged_at,
            round_number=args.round,
        ),
    }
    if args.scenario_a_snapshots is not None:
        report["scenario_a"] = judge_a(load_snapshots(args.scenario_a_snapshots))
    report["passed"] = all(item["result"] == "PASS" for item in report["scenario_b"].values())
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, item in report["scenario_b"].items():
        print(f"{name}: {item['result']}")
    for name, item in report.get("scenario_a", {}).items():
        print(f"{name}: {item['result']} (scenario A, not in the pass)")
    print(f"passed: {report['passed']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
