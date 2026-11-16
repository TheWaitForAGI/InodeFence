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
import os
import sys
from pathlib import Path

from inodefence.drivers import progress as progress_display
from inodefence.drivers.repo import code_checkout, require_repository_or_exit
from inodefence.drivers.run_target import (
    DEFAULT_MAX_UNJUDGED_RATIO,
    TARGETS,
    ExploreOptions,
    PreparedTargetImage,
    RefusalParser,
    TargetAdapter,
    auto_prepare_hint,
    docker_advice_for,
    docker_problem,
    load_adapter,
    resolve_images,
    with_tag_suffix,
)
from inodefence.drivers.runtime.session import RuntimeSession
from inodefence.target_result import load_target_result, no_extraction_warning

# Outside the repo AND outside ~/inodefence-evidence (confirmatory evidence lives there).
DEFAULT_OUT = Path.home() / "inodefence-explore"
# This repository is public; a violating-case TAR written inside it could be committed and leak.
REPO_ROOT = code_checkout()


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


def write_runtime_record(session: RuntimeSession, out: Path, *, result_written: bool) -> None:
    """Write the session's runtime record (if it launched anything); a failure: one stderr line."""
    session.finish(result_written=result_written)
    try:
        session.write(out.expanduser().resolve())
    except OSError as error:
        print(f"TARGET-EXPLORE RUNTIME: runtime record not written ({error})", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    # Discover --target first with a help-free parser so it does NOT consume -h/--help: the real
    # parser below is built with the target's declared options already added, so --help lists them
    # and --dry-run can print them (the common driver stays target-agnostic -- it only reads the
    # adapter's declarations).
    target_parser = RefusalParser(add_help=False)
    target_parser.add_argument("--target", default="node-tar", choices=sorted(TARGETS))
    pre, _ = target_parser.parse_known_args(argv)
    adapter = load_adapter(pre.target)

    parser = RefusalParser(
        description="prepare an extractor version and run the existing effect loop on it",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", default="node-tar", choices=sorted(TARGETS))
    parser.add_argument("--version", required=True, help="latest or an exact version")
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument(
        "--max-unjudged-ratio",
        type=float,
        default=DEFAULT_MAX_UNJUDGED_RATIO,
        help="ERROR ceiling for the un-judged ratio (above it the verdict is ERROR, not PASS)",
    )
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
    parser.add_argument(
        "--output",
        choices=progress_display.MODES,
        default=progress_display.STREAM,
        help="terminal output: stream = the launcher's raw output (default here); progress = "
        "progress lines, raw output to a log under <out>/runtime/ (the `inodefence explore` "
        "default); quiet = progress without the progress lines",
    )
    # The target's declared options become the `filters` passed to `cells`, in declaration order.
    # Exploration runs one configuration, so it takes one value per option: a multi-value option
    # (``single=False``, a target-run concept) has no meaning here and is refused up front.
    for opt in adapter.options:
        if not opt.single:
            parser.error(
                f"--{opt.name} is declared multi-value (target-run only); "
                "exploration takes one value per option"
            )
        parser.add_argument(
            f"--{opt.name}", required=opt.required, choices=opt.choices, help=opt.description
        )
    args = parser.parse_args(argv)
    require_repository_or_exit(parser, 3)

    target_options = {
        opt.name: getattr(args, opt.name.replace("-", "_"))
        for opt in adapter.options
        if getattr(args, opt.name.replace("-", "_")) is not None
    }

    if adapter.explore is None:
        print(
            f"TARGET-EXPLORE: exploration is not supported for {args.target} yet", file=sys.stderr
        )
        return 3

    # The target's own version/option validation (the same ``cells`` verify uses), also on
    # --dry-run, so a malformed version is refused (3) before a plan is printed.
    filters = [target_options[opt.name] for opt in adapter.options if opt.name in target_options]
    try:
        adapter.cells([args.version], filters)
    except ValueError as error:
        print(f"TARGET-EXPLORE SETUP: {error}", file=sys.stderr)
        return 3
    min_budget = adapter.explore_min_budget() if adapter.explore_min_budget else None
    if min_budget is not None and args.budget < min_budget:
        parser.error(f"--budget must be >= {min_budget} for {args.target} (the loop's seed count)")

    if args.dry_run:
        print(
            json.dumps(
                {
                    "target": args.target,
                    "version": args.version,
                    "seed": args.seed,
                    "budget": args.budget,
                    "out": str(args.out),
                    "target_options": target_options,
                    "note": "dry-run: nothing resolved, prepared, run or written",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.auto_prepare:
        parser.error(f"pass {auto_prepare_hint()} to prepare the image and run")

    out = args.out.expanduser().resolve()
    if out.is_relative_to(REPO_ROOT):
        print(
            f"TARGET-EXPLORE SETUP: --out must be outside the repository (this repo is public and "
            f"results may hold real violating inputs); {out} is inside {REPO_ROOT}",
            file=sys.stderr,
        )
        return 3

    # Docker first, with the same check as verify: a missing or unresponsive daemon fails here with
    # the fix, instead of later inside preparation or the launcher. The advice names this command.
    command = parser.prog if os.environ.get("INODEFENCE_PROG") else "target-explore"
    problem = docker_advice_for(docker_problem(), command)
    if problem is not None:
        print(f"TARGET-EXPLORE SETUP: {problem}", file=sys.stderr)
        return 3

    session = RuntimeSession(target=args.target)  # STRICT: the verified execution
    result_written = False  # the hook returns only after writing its result
    progress = progress_display.ExploreProgress(
        args.output,
        session=session,
        target=args.target,
        requested=args.version,
        seed=args.seed,
        budget=args.budget,
        out=out,
    )
    progress.start()  # nothing in stream mode
    try:
        prepared = prepare_target_image(
            adapter,
            args.target,
            args.version,
            image_tag_suffix=args.image_tag_suffix,
            filters=filters,
        )
        progress.prepared(prepared.version)
        outcome = adapter.explore(
            prepared,
            ExploreOptions(
                budget=args.budget,
                seed=args.seed,
                out=args.out,
                image_tag_suffix=args.image_tag_suffix,
                target_options=target_options,
                max_unjudged_ratio=args.max_unjudged_ratio,
                runtime=session,
            ),
        )
        result_written = True
        progress.completed(outcome.result_path, outcome.verdict)
    except ValueError as error:
        progress.failed(error)
        print(f"TARGET-EXPLORE SETUP: {error}", file=sys.stderr)
        return 3
    except RuntimeError as error:
        progress.failed(error)
        # The controller aborted or failed to run (e.g. the loop could not finish). That is an
        # ERROR, not a FAIL (no violation was judged), and it exits 2 like a worst-verdict ERROR --
        # a one-line reason, not a traceback.
        print(f"TARGET-EXPLORE ERROR: {error}", file=sys.stderr)
        return 2
    finally:
        # Also after a failed or interrupted launch: that is when the record is needed most. An
        # additional file; it never changes the result, the verdict or the exit code.
        write_runtime_record(session, args.out, result_written=result_written)
        progress.finish()  # last progress line; on a failure the cause and the log's last lines

    print(
        f"TARGET-EXPLORE {outcome.verdict} {args.target} version={prepared.version} "
        f"(requested {prepared.requested}) runs={outcome.runs} violations={outcome.violations} "
        f"image={prepared.image_id} (exploration run)"
    )
    print(f"result: {outcome.result_path}")
    try:  # a summary line only; the verdict and exit code below are unchanged
        warning = no_extraction_warning(load_target_result(outcome.result_path).termination_counts)
    except Exception:  # noqa: BLE001 - never let the warning hide the result
        warning = None
    if warning:
        print(f"TARGET-EXPLORE WARNING: {warning}")
    # Exit code from the verdict, same rule as target-run (0 PASS, 1 FAIL, 2 ERROR; setup/refusal
    # exits 3 earlier). A campaign whose verdict is ERROR with zero violations must not exit 0, or
    # automation reads "nothing extracted" as success.
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}.get(outcome.verdict, 2)


if __name__ == "__main__":
    raise SystemExit(main())
