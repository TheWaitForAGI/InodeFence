#!/usr/bin/env python3
"""Decompress C-vs-D boundary-channel campaign (A random floor / D boundary / C boundary+external).

Scoped question (NOT 'C > D' in general): in decompress's CWD-relative hardlink escape regime,
does arm C (external-resolve channel) generate/reach more boundary attempts -- specifically the
depth-0 CWD-relative hardlink class (C-without-D) that arm D's lexical boundary-attempt channel is
structurally blind to -- than arm D or the random floor A? Measure only.

Design (honest reduced scope, reported to the commander at the stage-3 gate):
  * Comparison = C-vs-D (+A random floor). NOT the node-tar A/B/C/D ladder: decompress exposes no
    faithful ordered effect trace (feasibility negative), so the base-effect retention channel
    (A/B) has no decompress data -- A is a pure uniform-mutation floor, and there is no B
    (structure base-effect) arm. Stated as a limitation, not hidden.
  * Grammar = MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK (uniform-generic-m1-escape-hardlink-v1),
    the item-3 token-clean escaping-hardlink grammar. Its generic vocabulary (a,b,dir,file,item,
    .,..) contains NO sentinel/outside/CVE/answer-path token (D005/D006), and because it includes
    '.'/'..' it naturally emits a mix of depth-0 targets (a/b -> CWD-escape -> C-without-D on
    decompress) and depth>=1 (../a -> C and D). The escaping target can never spell a name the
    generic alphabet does not contain, so a 'blind' claim holds.
  * Signal = the real decompress fs-wrap boundary-attempt-v1 frame -> the canonical #179 normalizer
    frame_boundary_attempt_keys (op-generic; reused, not duplicated). This is a frame-native loop,
    the honest set-based analog of run_effect_campaign (whose EffectEventTrace producer contract
    decompress cannot satisfy). It reuses the mutator grammar, minimal_seed_corpus and the
    canonical keys; only the thin uniform/adaptive retention loop is new. The adaptive retention
    (C/D retain a child that produced a NEW arm key and re-mutate the grown corpus; A stays uniform
    over the seeds) mirrors item-3's novel-key-driven retention; it is a SIMPLIFIED frame-native
    scheduler, not a byte-identical reuse of EffectAdaptiveMutationScheduler (which is trace-based).
  * Arms differ ONLY in the retention/novelty channel; grammar, seeds and budget are identical:
      A -> no boundary steering (uniform floor); D -> new BOUNDARY_ESCAPE_ATTEMPT key; C -> new
      BOUNDARY_ESCAPE_ATTEMPT or OBSERVED_EXTERNAL_RESOLVE key.

Primary metrics (pre-registered, right-censored): per arm, boundary-attempt rate + external-resolve
rate + executions-to-first-boundary / -external (None = right-censored, no occurrence in budget),
plus the cumulative unique-key counts. Terminal C1 is NOT computed here (secondary; the adapter's
job) -- this campaign measures the boundary/external search behavior (EN-008), not vulnerability
counts or effectiveness.

Safety: affected decompress 4.2.1 only, hardened docker (--network none / --read-only /
--cap-drop ALL / tmpfs), no isolation relaxation, 'demo run' label. observed (frame) vs inferred
distinguished; no synthetic run. Analysis is 주언's (routed by the commander); this script emits
raw + the pre-registration it ran under.

Reproduce (deterministic per cell by its seed):
  uv run python experiments/repro/decompress_cvd_campaign.py \\
      --arms A,C,D --seeds 90,91,92,93 --budget 500 --jobs 3 --out <dir>
"""

from __future__ import annotations

import argparse
import base64
import json
import random
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from inodefence.builder import build_tar
from inodefence.feedback.boundary_attempt_frame import FRAME_FORMAT, frame_boundary_attempt_keys
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model import EffectFeedbackKeyKind
from inodefence.mutator.policy import MutationPolicy, mutate_with_policy

IMAGE = "inodefence-decompress-effect-probe:4.2.1"
SENTINEL_CONTENT = b"inodefence protected sentinel\n"
GRAMMAR = MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK

_D_KIND = EffectFeedbackKeyKind.BOUNDARY_ESCAPE_ATTEMPT  # arm D channel
_C_KIND = EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE  # arm C adds this rung


def image_id() -> str:
    return subprocess.run(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def run_probe(tar_bytes: bytes) -> dict:
    """One hardened decompress fs-wrap run -> one boundary-attempt-v1 frame (or an error marker)."""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/work:rw,size=16m,mode=1777",
            "--tmpfs",
            "/tmp:rw,size=16m,mode=1777",
            "--cap-drop",
            "ALL",
            "-e",
            f"TAR_B64={base64.b64encode(tar_bytes).decode()}",
            "-e",
            f"SENTINEL_B64={base64.b64encode(SENTINEL_CONTENT).decode()}",
            IMAGE,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except (ValueError, TypeError):
            continue
    return {"_run_error": True, "_rc": result.returncode}


def _arm_keys(keys: tuple, arm: str) -> frozenset:
    if arm == "A":
        return frozenset()
    if arm == "D":
        return frozenset(key for key in keys if key.kind == _D_KIND)
    return frozenset(key for key in keys if key.kind in (_D_KIND, _C_KIND))  # arm C


def run_cell(arm: str, seed: int, budget: int) -> dict:
    """One deterministic (arm, seed) campaign cell over the frame-native boundary channel."""
    rng = random.Random(seed)
    seeds_corpus = list(minimal_seed_corpus())
    corpus = list(seeds_corpus)
    seen: set = set()
    steps: list[dict] = []
    first_boundary: int | None = None
    first_external: int | None = None
    unique_boundary: set = set()
    unique_external: set = set()

    for i in range(budget):
        pool = seeds_corpus if arm == "A" else corpus
        child = mutate_with_policy(rng.choice(pool), rng, GRAMMAR)
        frame = run_probe(build_tar(child))
        keys: tuple = ()
        if isinstance(frame, dict) and frame.get("format") == FRAME_FORMAT:
            keys = frame_boundary_attempt_keys(frame)
        kinds = {key.kind for key in keys}
        has_boundary = _D_KIND in kinds
        has_external = _C_KIND in kinds
        if has_boundary and first_boundary is None:
            first_boundary = i + 1
        if has_external and first_external is None:
            first_external = i + 1
        for key in keys:
            (unique_boundary if key.kind == _D_KIND else unique_external).add(key)
        arm_keys = _arm_keys(keys, arm)
        new = arm_keys - seen
        seen |= arm_keys
        if new and arm != "A":
            corpus.append(child)
        steps.append(
            {
                "i": i,
                "boundary": has_boundary,
                "external": has_external,
                "n_attempts": len(frame.get("attempts", [])) if isinstance(frame, dict) else 0,
                "new_arm_keys": len(new),
                "error": bool(frame.get("_run_error")) if isinstance(frame, dict) else True,
            }
        )

    n = len(steps)
    return {
        "arm": arm,
        "seed": seed,
        "budget": budget,
        "grammar": GRAMMAR.value,
        "boundary_attempt_rate": sum(s["boundary"] for s in steps) / n,
        "external_resolve_rate": sum(s["external"] for s in steps) / n,
        "exec_to_first_boundary": first_boundary,  # None => right-censored
        "exec_to_first_external": first_external,  # None => right-censored
        "unique_boundary_keys": len(unique_boundary),
        "unique_external_keys": len(unique_external),
        "corpus_size": len(corpus),
        "errors": sum(s["error"] for s in steps),
        "steps": steps,
    }


def _cell_task(args: tuple) -> dict:
    arm, seed, budget = args
    return run_cell(arm, seed, budget)


def summarize(cells: list[dict], arms: list[str], seeds: list[int]) -> dict:
    per_arm = {}
    for arm in arms:
        arm_cells = [c for c in cells if c["arm"] == arm]
        br = [c["boundary_attempt_rate"] for c in arm_cells]
        er = [c["external_resolve_rate"] for c in arm_cells]
        per_arm[arm] = {
            "boundary_attempt_rate_mean": sum(br) / len(br) if br else None,
            "external_resolve_rate_mean": sum(er) / len(er) if er else None,
            "boundary_attempt_rate_per_seed": {
                c["seed"]: c["boundary_attempt_rate"] for c in arm_cells
            },
            "external_resolve_rate_per_seed": {
                c["seed"]: c["external_resolve_rate"] for c in arm_cells
            },
            "exec_to_first_boundary_per_seed": {
                c["seed"]: c["exec_to_first_boundary"] for c in arm_cells
            },
            "exec_to_first_external_per_seed": {
                c["seed"]: c["exec_to_first_external"] for c in arm_cells
            },
            "right_censored_boundary_seeds": [
                c["seed"] for c in arm_cells if c["exec_to_first_boundary"] is None
            ],
            "right_censored_external_seeds": [
                c["seed"] for c in arm_cells if c["exec_to_first_external"] is None
            ],
            "unique_boundary_keys_per_seed": {
                c["seed"]: c["unique_boundary_keys"] for c in arm_cells
            },
            "unique_external_keys_per_seed": {
                c["seed"]: c["unique_external_keys"] for c in arm_cells
            },
            "errors_per_seed": {c["seed"]: c["errors"] for c in arm_cells},
        }
    return per_arm


def main() -> None:
    ap = argparse.ArgumentParser(description="decompress C-vs-D boundary-channel campaign")
    ap.add_argument("--arms", default="A,C,D")
    ap.add_argument("--seeds", default="90,91,92,93")
    ap.add_argument("--budget", type=int, default=500)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=str(Path.home() / "inodefence-evidence"))
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    assert all(a in ("A", "C", "D") for a in arms), "arms must be in {A,C,D}"
    img = image_id()

    tasks = [(arm, seed, args.budget) for arm in arms for seed in seeds]
    cells: list[dict] = []
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / f"decompress-cvd-campaign-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(_cell_task, t): t for t in tasks}
        for fut in as_completed(futures):
            cell = fut.result()
            cells.append(cell)
            (out_dir / f"cell-{cell['arm']}-s{cell['seed']}.json").write_text(
                json.dumps(cell, sort_keys=True)
            )
            print(
                f"cell {cell['arm']} s{cell['seed']}: "
                f"boundary_rate={cell['boundary_attempt_rate']:.3f} "
                f"external_rate={cell['external_resolve_rate']:.3f} "
                f"first_b={cell['exec_to_first_boundary']} "
                f"first_e={cell['exec_to_first_external']} errors={cell['errors']}"
            )

    summary = {
        "experiment": "decompress C-vs-D boundary-channel campaign",
        "label": "demo run",
        "scope": "C-vs-D (+A random floor) boundary channel; NOT general 'C>D'; scoped to the "
        "CWD-relative hardlink escape class on decompress. B (structure base-effect) arm not "
        "mapped (decompress has no faithful ordered trace).",
        "preregistration": {
            "arms": arms,
            "seeds": seeds,
            "budget": args.budget,
            "grammar": GRAMMAR.value,
            "grammar_cleanliness": "generic vocabulary a,b,dir,file,item,.,.. only; no "
            "sentinel/outside/CVE/answer-path token (D005/D006); escaping target cannot spell a "
            "name outside the generic alphabet.",
            "primary_metrics": [
                "boundary_attempt_rate per arm",
                "external_resolve_rate per arm",
                "exec_to_first_boundary / exec_to_first_external per seed (None = right-censored)",
            ],
            "question": "In the CWD-relative hardlink regime, does arm C reach boundary attempts "
            "(the depth-0 C-without-D class) that arm D's lexical channel misses? Measure only; "
            "no C>D assumption; results scoped to this escape class.",
            "equivalence_margin_delta": 0.05,
            "tost": "To claim C==D equivalence (not merely 'no C-advantage'), a two one-sided test "
            "against a pre-registered negligible margin delta=0.05 (5pp, small vs the ~40pp "
            "gradient-over-floor gap) must reject non-equivalence on the primary metric. Otherwise "
            "the claim is only the negative 'no C-advantage'. Statistics/CI/TOST are computed by "
            "independent verification (this build lane emits raw only).",
            "disclosed_prior": "The 4-seed run (decompress-cvd-campaign-20261030-030752) showed a "
            "borderline boundary-attempt D-lean of ~3.1pp (|D-C| on boundary rate; CI barely "
            "excludes 0, external-resolve sign-reversed). It is NOT claimed as strict C=D; this "
            "8-seed re-run (true unit = seed, df 7) addresses that underpowering.",
        },
        "target": {"extractor": "decompress", "version": "4.2.1", "image_id": img},
        "isolation": (
            "hardened docker run: --network none --read-only --cap-drop ALL tmpfs; no relaxation"
        ),
        "signal": (
            "real decompress fs-wrap boundary-attempt-v1 frame -> "
            "frame_boundary_attempt_keys (#179)"
        ),
        "per_arm": summarize(cells, arms, seeds),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    print("\nSUMMARY:")
    print(json.dumps(summary["per_arm"], indent=2, sort_keys=True))
    print("EVIDENCE:", out_dir)


if __name__ == "__main__":
    main()
