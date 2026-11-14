"""make target-explore: point the fuzzer at an extractor version and run the existing loop on it.

A deployment tool: pick an extractor, prepare a version (``latest`` or an exact one), and run
exploration. It does not run an experiment -- the person using the tool does. This driver is
target-agnostic: it prepares the image through the common prepare layer and hands it to the
target's ``TargetAdapter.explore`` hook; the result format, options and output are shared across
targets. A target with no explore hook reports that exploration is not supported for it.

Output goes OUTSIDE the repository and outside ``~/inodefence-evidence`` (default
``~/inodefence-explore``). Only the inputs of cases the oracle flagged as violations are saved.

FOUND A BOUNDARY VIOLATION ON A MAINTAINED VERSION? Handle it responsibly, in order:
  1. keep the result, the inputs and the logs in the OFF-repository output folder only -- never in
     any branch, commit, PR body, PR comment, issue or log (this repository is public);
  2. re-run the same version twice more to see whether it reproduces;
  3. report the version, the violation count and the off-repo folder path to the maintainers of the
     extractor first -- disclosure to anyone else comes after they have had a chance to fix it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.run_target import (
    TARGETS,
    ExploreOptions,
    PreparedTargetImage,
    TargetAdapter,
    load_adapter,
    resolve_images,
    with_tag_suffix,
)

# Outside the repo AND outside ~/inodefence-evidence (confirmatory evidence lives there).
DEFAULT_OUT = Path.home() / "inodefence-explore"


def prepare_target_image(
    adapter: TargetAdapter,
    target: str,
    spec: str,
    *,
    image_tag_suffix: str,
    filters: list[str] | None = None,
) -> PreparedTargetImage:
    """Resolve the version and reuse or prepare its image, via the common prepare layer.

    Works for any target with ``resolve`` / ``cells`` / ``prepare``; no target-specific code here.
    """
    versions = adapter.resolve([spec]) if adapter.resolve is not None else [spec]
    if len(versions) != 1:
        raise ValueError(f"explore takes one version, got {versions!r}")
    (cell,) = adapter.cells(versions, filters or [])
    cell = with_tag_suffix(cell, image_tag_suffix)
    if cell.image_ref is None:
        raise ValueError(f"{target} {spec}: no image for this version")
    ready, errors = resolve_images(adapter, [cell], auto_prepare=True)
    if cell.image_ref in errors:
        raise ValueError(errors[cell.image_ref])
    return PreparedTargetImage(
        target=target,
        requested=spec,
        version=versions[0],
        image_ref=cell.image_ref,
        image_id=ready[cell.image_ref],
        exploratory=cell.exploratory,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="prepare an extractor version and run the existing effect loop on it",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", default="node-tar", choices=sorted(TARGETS))
    parser.add_argument("--version", required=True, help="latest or an exact version")
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="output dir (outside the repo)"
    )
    parser.add_argument("--image-tag-suffix", default="")
    parser.add_argument(
        "--auto-prepare",
        action="store_true",
        help="prepare (resolve/build/verify) the image; required for a real run",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan; prepare/run nothing"
    )
    # The target's own options are declared by its adapter; add them once the target is known
    # so the common driver stays target-agnostic. They become the `filters` passed to `cells`.
    pre, _ = parser.parse_known_args(argv)
    adapter = load_adapter(pre.target)
    for opt in adapter.options:
        parser.add_argument(
            f"--{opt.name}", required=opt.required, choices=opt.choices, help=opt.description
        )
    args = parser.parse_args(argv)

    if adapter.explore is None:
        print(
            f"TARGET-EXPLORE: exploration is not supported for {args.target} yet", file=sys.stderr
        )
        return 3

    if args.dry_run:
        print(
            json.dumps(
                {
                    "target": args.target,
                    "version": args.version,
                    "seed": args.seed,
                    "budget": args.budget,
                    "out": str(args.out),
                    "note": "dry-run: nothing resolved, prepared, run or written",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.auto_prepare:
        parser.error("pass AUTO_PREPARE=1 (--auto-prepare) to prepare the image and run")

    target_options = {
        opt.name: getattr(args, opt.name.replace("-", "_"))
        for opt in adapter.options
        if getattr(args, opt.name.replace("-", "_")) is not None
    }
    filters = [target_options[opt.name] for opt in adapter.options if opt.name in target_options]
    try:
        prepared = prepare_target_image(
            adapter,
            args.target,
            args.version,
            image_tag_suffix=args.image_tag_suffix,
            filters=filters,
        )
        outcome = adapter.explore(
            prepared,
            ExploreOptions(
                budget=args.budget,
                seed=args.seed,
                out=args.out,
                image_tag_suffix=args.image_tag_suffix,
                target_options=target_options,
            ),
        )
    except ValueError as error:
        print(f"TARGET-EXPLORE SETUP: {error}", file=sys.stderr)
        return 3

    print(
        f"TARGET-EXPLORE {outcome.verdict} {args.target} version={prepared.version} "
        f"(requested {prepared.requested}) runs={outcome.runs} violations={outcome.violations} "
        f"image={prepared.image_id} (exploration run)"
    )
    print(f"result: {outcome.result_path}")
    return 1 if outcome.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
