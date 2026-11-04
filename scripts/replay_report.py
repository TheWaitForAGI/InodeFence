"""Reproduce a demo report's run: emit its command and verify the offline parts.

A demo report records everything needed to reproduce the run that produced it:
the random seed, the search and mutation policy IDs, the pinned target version, the
content-addressed image (``image_id`` / ``image_recipe.recipe_sha256``) and the
ordered ``case_id`` sequence the feedback loop actually visited. This tool reads a
report and, without a container runtime (``--dry-run``, the only mode here):

  * extracts the knobs and prints the exact ``make`` command that reproduces the run,
  * binds the report's recorded image recipe to the current committed recipe
    (reusing the recipe attestation), so a drifted image is caught before any re-run,
  * checks the recorded ``case_id`` sequence for internal consistency and prints its
    fingerprint, which a native re-run can be compared against.

Actually re-executing in a container and comparing the freshly produced ``case_id``
sequence is the Runtime lane's step; this tool deliberately does not run docker.

    python -m scripts.replay_report --report <demo-report.json>
    make replay REPORT=<demo-report.json>
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from scripts.attest_demo_image_recipe import compare_report

IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
CASE_ID = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ReplayPlan:
    report: Path
    producer: str
    seed: int | None
    budget: int | None
    search_policy: str
    mutation_policy: str
    target_version: str | None
    image_id: str | None
    recipe_sha256: str | None
    make_target: str
    case_ids: tuple[str, ...]
    initial_case_ids: tuple[str, ...]
    retained_case_ids: tuple[str, ...]

    @property
    def sequence_fingerprint(self) -> str:
        """Stable digest of the ordered case_id sequence, for cross-run comparison."""
        return sha256("\n".join(self.case_ids).encode("utf-8")).hexdigest()

    def command(self) -> str:
        parts = [
            "make",
            self.make_target,
            f"DEMO_SEED={self.seed}",
            f"DEMO_BUDGET={self.budget}",
            f"DEMO_POLICY={self.search_policy}",
            f"DEMO_MUTATION_POLICY={self.mutation_policy}",
        ]
        if self.make_target == "demo-native-historical" and self.target_version:
            parts.append(f"TAR_VERSION={self.target_version}")
        return " ".join(parts)


def _as_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def build_plan(report_path: Path) -> ReplayPlan:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError(f"{report_path}: report is not a JSON object")
    config = report.get("config") if isinstance(report.get("config"), dict) else {}
    assert isinstance(config, dict)

    def pick(key: str) -> object:
        return config.get(key, report.get(key))

    recipe = report.get("image_recipe") if isinstance(report.get("image_recipe"), dict) else None
    recipe_sha = recipe.get("recipe_sha256") if isinstance(recipe, dict) else None
    tar_version = report.get("node_tar_version")
    if tar_version is None and isinstance(recipe, dict):
        tar_version = recipe.get("tar_version")

    label = str(report.get("label", ""))
    producer = str(report.get("producer", ""))
    historical = "historical" in f"{label} {producer} {report_path.name}".lower()

    seed = pick("random_seed")
    budget = pick("execution_budget")
    steps = report.get("steps")
    case_ids = (
        tuple(
            str(step["case_id"]) for step in steps if isinstance(step, dict) and "case_id" in step
        )
        if isinstance(steps, list)
        else ()
    )

    return ReplayPlan(
        report=report_path,
        producer=producer,
        seed=seed if isinstance(seed, int) else None,
        budget=budget if isinstance(budget, int) else None,
        search_policy=str(pick("search_policy") or ""),
        mutation_policy=str(pick("mutation_policy") or ""),
        target_version=str(tar_version) if tar_version is not None else None,
        image_id=str(report["image_id"]) if isinstance(report.get("image_id"), str) else None,
        recipe_sha256=str(recipe_sha) if isinstance(recipe_sha, str) else None,
        make_target="demo-native-historical" if historical else "demo",
        case_ids=case_ids,
        initial_case_ids=_as_tuple(report.get("initial_case_ids")),
        retained_case_ids=_as_tuple(report.get("retained_case_ids")),
    )


def dry_run_problems(plan: ReplayPlan) -> list[str]:
    """Return the offline reproduction problems (empty means the report replays clean)."""
    problems: list[str] = []
    if plan.seed is None:
        problems.append("missing/invalid random_seed")
    if plan.budget is None or plan.budget <= 0:
        problems.append("missing/invalid execution_budget")
    if not plan.search_policy:
        problems.append("missing search_policy")
    if not plan.mutation_policy:
        problems.append("missing mutation_policy")
    if plan.image_id is not None and not IMAGE_ID.match(plan.image_id):
        problems.append(f"image_id is not a sha256 digest: {plan.image_id}")

    if plan.recipe_sha256 is not None:
        problems.extend(f"recipe binding: {item}" for item in compare_report(plan.report))

    if not plan.case_ids:
        problems.append("no case_id sequence recorded in steps[]")
    bad = [cid for cid in plan.case_ids if not CASE_ID.match(cid)]
    if bad:
        problems.append(f"{len(bad)} case_id(s) are not 64-hex")
    if plan.budget is not None and plan.case_ids and len(plan.case_ids) != plan.budget:
        problems.append(f"case_id count {len(plan.case_ids)} != execution_budget {plan.budget}")
    recorded = set(plan.case_ids)
    for name, ids in (
        ("initial_case_ids", plan.initial_case_ids),
        ("retained_case_ids", plan.retained_case_ids),
    ):
        stray = [cid for cid in ids if cid not in recorded]
        if stray:
            problems.append(f"{len(stray)} {name} not present in the step sequence")
    return problems


def _render(plan: ReplayPlan, problems: list[str]) -> str:
    lines = [
        f"report:            {plan.report}",
        f"producer:          {plan.producer or '(none)'}",
        f"target version:    {plan.target_version or '(none)'}",
        f"image_id:          {plan.image_id or '(none)'}",
        f"recipe_sha256:     {plan.recipe_sha256 or '(none; recipe binding skipped)'}",
        f"case_id sequence:  {len(plan.case_ids)} steps, fingerprint {plan.sequence_fingerprint}",
        "",
        "reproduction command (native re-run is the Runtime lane; this tool runs no docker):",
        f"  {plan.command()}",
        "",
    ]
    if problems:
        lines.append("DRY-RUN FAIL:")
        lines.extend(f"  - {item}" for item in problems)
    else:
        lines.append(
            "DRY-RUN OK: report fields, recipe binding and case_id sequence are consistent."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="demo report JSON to replay")
    parser.add_argument("--json", action="store_true", help="print the plan and problems as JSON")
    args = parser.parse_args(argv)

    if not args.report.is_file():
        parser.error(f"report not found: {args.report}")
    plan = build_plan(args.report)
    problems = dry_run_problems(plan)

    if args.json:
        print(
            json.dumps(
                {
                    "report": str(plan.report),
                    "command": plan.command(),
                    "sequence_fingerprint": plan.sequence_fingerprint,
                    "case_id_count": len(plan.case_ids),
                    "problems": problems,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(_render(plan, problems))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
