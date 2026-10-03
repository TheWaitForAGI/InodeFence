"""Small safe-reference engineering pilot, not an effectiveness experiment.

Run in the Linux Dev Container: python -m scripts.reference_campaign_pilot
--output experiments/raw/<new-pilot-directory>. Output must not already exist.
"""

import argparse
import json
import platform
import subprocess
import time
import tracemalloc
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from scripts.generate_tar_fixtures import CASE_NAMES, baseline_case

from inodefence.campaign import CampaignConfig, CampaignResult, run_campaign
from inodefence.model import canonical_json
from inodefence.runtime import runtime_root
from inodefence.targets import PythonTarfileTarget


def _semantic(result: CampaignResult) -> tuple[object, ...]:
    return (
        tuple(
            (step.index, step.origin, step.parent_case_id, step.result.case, step.feedback)
            for step in result.steps
        ),
        result.retained_case_ids,
        result.final_corpus_stats,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    output = parser.parse_args().output
    root = runtime_root()
    baseline_directories = set(root.iterdir())
    initial = tuple(baseline_case(name) for name in CASE_NAMES)
    jobs = tuple((seed, budget) for seed in (11, 23) for budget in (25, 50, 100)) + ((23, 50),)
    # Capture established provenance before the first target execution.
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "src/inodefence"]).returncode:
        raise ValueError("pilot requires unchanged engine code at the recorded revision")
    provenance = {
        "classification": "engineering-validation-only",
        "engine_revision": revision,
        "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "target_id": "python-tarfile-data",
        "target_version": platform.python_version(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "runtime_root": str(root),
        "timeout_seconds": 5.0,
        "initial_cases": [json.loads(canonical_json(case)) for case in initial],
        "jobs": [{"random_seed": seed, "execution_budget": budget} for seed, budget in jobs],
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")
    summaries = []
    repeated: tuple[object, ...] | None = None
    for index, (seed, budget) in enumerate(jobs):
        tracemalloc.start()
        started = time.perf_counter()
        result = run_campaign(
            initial, PythonTarfileTarget(timeout_seconds=5.0), CampaignConfig(seed, budget)
        )
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert len(result.steps) == result.final_corpus_stats.observations == budget
        assert tuple(step.index for step in result.steps) == tuple(range(budget))
        assert all(not Path(step.result.after.sandbox_root).exists() for step in result.steps)
        assert set(root.iterdir()) == baseline_directories
        if (seed, budget) == (23, 50):
            if repeated is None:
                repeated = _semantic(result)
            else:
                assert repeated == _semantic(result)
        raw = (canonical_json(result) + "\n").encode("ascii")
        filename = f"campaign-{index}-seed-{seed}-budget-{budget}.json"
        (output / filename).write_bytes(raw)
        summary = {
            "random_seed": seed,
            "execution_budget": budget,
            "stats": asdict(result.final_corpus_stats),
            "statuses": dict(
                sorted(Counter(step.result.execution.status.value for step in result.steps).items())
            ),
            "elapsed_seconds": elapsed,
            "peak_traced_bytes": peak,
            "raw_file": filename,
            "raw_sha256": sha256(raw).hexdigest(),
        }
        summaries.append(summary)
        print(json.dumps(summary, sort_keys=True))
    (output / "summary.json").write_text(
        json.dumps(
            {
                "provenance": provenance,
                "runs": summaries,
                "repeat_semantics_match": True,
                "runtime_cleanup_verified": True,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
