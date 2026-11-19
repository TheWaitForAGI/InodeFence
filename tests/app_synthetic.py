"""SYNTHETIC run folders for the UI read-model tests (``inodefence.app``). Test use only.

Everything here is made up: no extractor ran, no input was observed. The folders are built with
the real writers (``LiveRecorder``, ``TargetResult.dumps``, ``case_replay.summarize_rounds``) so
the files have exactly the shapes the drivers write, and every folder and run id carries the word
``synthetic`` so nothing built here can be mistaken for a real result. Nothing is written outside
the pytest temporary folder.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any

from inodefence import case_replay
from inodefence.live_exploration import LiveRecorder, LiveRunMeta, LiveStep
from inodefence.target_result import (
    JUDGED,
    RUN_ERROR,
    CampaignInfo,
    CaseVerdict,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    repro_input,
)

SYNTHETIC = "synthetic"
ENGINE = "e" * 40
IMAGE = "sha256:" + "a" * 64
TAR = b"synthetic tar bytes, not an archive"


class Clock:
    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def explore_out(tmp: Path) -> Path:
    out = tmp / f"{SYNTHETIC}-explore"
    (out / "target-explore").mkdir(parents=True, exist_ok=True)
    return out


def run_id(seed: int = 1) -> str:
    return f"{SYNTHETIC}-7.5.2-{seed}-20"


def live_run(
    out: Path,
    rid: str,
    steps: Sequence[LiveStep],
    *,
    clock: Clock | None = None,
    close: str | None = None,
    budget: int = 20,
) -> tuple[Path, LiveRecorder]:
    """A node-tar-shaped live folder written by the real recorder."""
    clock = clock or Clock()
    live = out / "target-explore" / rid / "live"
    meta = LiveRunMeta(target="node-tar", version="7.5.2", seed=1, budget=budget, image_id=IMAGE,
                       engine_commit=ENGINE)  # fmt: skip
    recorder = LiveRecorder(live, meta, every_runs=1, clock=clock)
    for step in steps:
        clock.now += 1
        recorder.on_step(step)
    if close is not None:
        clock.now += 1
        recorder.close(state=close)
    return live, recorder


def step(index: int, *, status: str = "success", c1: bool | None = False, fp: str = "") -> LiveStep:
    violated = c1 is True
    return LiveStep(
        index=index,
        case_id=f"{SYNTHETIC}-case-{index}",
        status=status,
        c0=False,
        c1=c1,
        c2=False,
        fingerprints=(fp,) if fp else (),
        new_fingerprints=(fp,) if fp else (),
        tar_bytes=TAR if violated else None,
        observation_complete=True,
    )


def result(
    *,
    target: str = "node-tar",
    version: str = "7.5.2",
    cases: Sequence[CaseVerdict] = (),
    mode: ResultMode = ResultMode.CAMPAIGN,
    saved: Sequence[str] = (),
    terminations: dict[str, int] | None = None,
) -> TargetResult:
    campaign = None
    if mode is ResultMode.CAMPAIGN:
        first = next((i + 1 for i, c in enumerate(cases) if c.violated), None)
        campaign = CampaignInfo(seed=1, budget=max(len(cases), 20), runs_to_first_violation=first,
                                terminations=terminations)  # fmt: skip
    return TargetResult(
        target=target,
        axes=TargetAxes(target_version=version),
        mode=mode,
        observed_contracts=("C0", "C1", "C2"),
        cases=tuple(cases),
        repro_inputs=tuple(repro_input(c, f"inputs/{c}.tar", TAR) for c in saved),
        provenance=Provenance(ENGINE, False, f"{SYNTHETIC}-image", IMAGE),
        campaign=campaign,
    )


def case(case_id: str, c1: bool | None, *, termination: str | None = "success") -> CaseVerdict:
    outcome = RUN_ERROR if c1 is None and termination is None else JUDGED
    c0 = None if outcome == RUN_ERROR else False
    c2 = None if outcome == RUN_ERROR else False
    return CaseVerdict(case_id, outcome, c0, c1, c2, termination=termination,
                       observation_complete=True if outcome == JUDGED else None)  # fmt: skip


def write_result(folder: Path, res: TargetResult, *, text: str | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "inputs").mkdir(exist_ok=True)
    for item in res.repro_inputs:
        (folder / item.tar_path).write_bytes(TAR)
    path = folder / "result.json"
    path.write_text(res.dumps() if text is None else text, encoding="utf-8")
    return path


def replay(folder: Path, original: dict[str, Any], rounds: list[dict[str, Any]]) -> Path:
    """A replay.json in a new ``<case>.replay-<UTC>`` folder, summary by the real function."""
    normalized = [case_replay.normalize_round(r, i + 1) for i, r in enumerate(rounds)]
    for entry in normalized:
        entry["classification"] = case_replay.classify_round(original, entry)
    record = {
        "schema": case_replay.REPLAY_SCHEMA,
        "note": f"{SYNTHETIC} record",
        "original": {
            "case_id": f"{SYNTHETIC}-case",
            "tar_sha256": sha256(TAR).hexdigest(),
            **original,
        },  # fmt: skip
        "replay": {
            "rounds_requested": len(rounds),
            "complete": True,
            "stop_reason": None,
            "image_id": IMAGE,
            "engine_differs": False,
        },  # fmt: skip
        "rounds": normalized,
        "summary": case_replay.summarize_rounds(original, normalized),
    }
    out = folder.parent / f"{folder.name}.replay-20260101T000000Z"
    out.mkdir(parents=True)
    path = out / case_replay.REPLAY_FILE
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def judged_round(c1: bool, termination: str = "success") -> dict[str, Any]:
    return {"outcome": "judged", "termination": termination, "c0": False, "c1": c1, "c2": False,
            "observation_complete": True}  # fmt: skip


def failed_round() -> dict[str, Any]:
    return {"outcome": "run_error", "termination": None, "c0": None, "c1": None, "c2": None}
