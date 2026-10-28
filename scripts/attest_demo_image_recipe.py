"""Attest the `make demo` node-tar image recipe: same recipe -> same digest.

Without options this prints the content-addressed recipe provenance of the
committed demo image (``tools/node-tar/Dockerfile`` and its build context),
including ``recipe_sha256``. This computation touches no container runtime.

  python -m scripts.attest_demo_image_recipe
  python -m scripts.attest_demo_image_recipe --check
  python -m scripts.attest_demo_image_recipe --report <demo-report.json>

``--check`` verifies the attestation invariants offline: the recipe renders
deterministically, every recorded per-file digest matches a fresh hash of the
committed file, and ``recipe_sha256`` is the digest of those file hashes. This is
the direct evidence that the same committed recipe always yields the same
fingerprint. ``--report`` loads a demo report's recorded ``image_recipe`` and
confirms it equals the current committed recipe, binding that report's image to
today's recipe (it names any drifted file otherwise).
"""

import argparse
import json
import sys
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path

from inodefence.targets.node_tar_recipe import (
    DEMO_IMAGE_RECIPE_FILES,
    demo_image_recipe,
    recipe_digest,
    repository_root,
)


def _render(recipe: Mapping[str, object]) -> str:
    return json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def check_recipe() -> list[str]:
    """Return the attestation failures (empty means the recipe attests cleanly)."""
    failures: list[str] = []
    recipe = demo_image_recipe()
    if demo_image_recipe() != recipe:
        failures.append("recipe is not deterministic across invocations")
    root = repository_root()
    recorded = recipe["files_sha256"]
    assert isinstance(recorded, dict)
    if set(recorded) != set(DEMO_IMAGE_RECIPE_FILES):
        failures.append("recorded files differ from the declared recipe inputs")
    for name in DEMO_IMAGE_RECIPE_FILES:
        fresh = sha256((root / name).read_bytes()).hexdigest()
        if recorded.get(name) != fresh:
            failures.append(f"recorded digest does not match the committed file: {name}")
    if recipe["recipe_sha256"] != recipe_digest(recorded):
        failures.append("recipe_sha256 is not the digest of files_sha256")
    return failures


def compare_report(report_path: Path) -> list[str]:
    """Return how a demo report's recorded recipe differs from the committed one."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    recorded = report.get("image_recipe") if isinstance(report, dict) else None
    if not isinstance(recorded, dict):
        return [f"{report_path} has no image_recipe provenance"]
    current = demo_image_recipe()
    if recorded == current:
        return []
    differences: list[str] = []
    if recorded.get("recipe_sha256") != current["recipe_sha256"]:
        differences.append(
            f"recipe_sha256 differs: report {recorded.get('recipe_sha256')} "
            f"!= current {current['recipe_sha256']}"
        )
    report_files = recorded.get("files_sha256") or {}
    current_files = current["files_sha256"]
    assert isinstance(current_files, dict)
    for name in sorted(set(report_files) | set(current_files)):
        if report_files.get(name) != current_files.get(name):
            differences.append(f"file digest differs: {name}")
    return differences or ["image_recipe differs from the committed recipe"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check", action="store_true", help="verify the recipe attestation invariants offline"
    )
    group.add_argument(
        "--report", type=Path, help="confirm a demo report's recipe equals the committed recipe"
    )
    args = parser.parse_args(argv)
    if args.check:
        failures = check_recipe()
        if failures:
            for item in failures:
                print(f"recipe attestation FAILED: {item}", file=sys.stderr)
            return 1
        print(f"recipe attestation OK: recipe_sha256={demo_image_recipe()['recipe_sha256']}")
        return 0
    if args.report is not None:
        differences = compare_report(args.report)
        if differences:
            for item in differences:
                print(f"recipe mismatch: {item}", file=sys.stderr)
            return 1
        print(f"recipe matches report: {args.report}")
        return 0
    sys.stdout.write(_render(demo_image_recipe()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
