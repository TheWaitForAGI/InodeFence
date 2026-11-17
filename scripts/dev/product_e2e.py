"""End-to-end check of the installed ``inodefence`` command against real extractors (demo run).

Runs the user command exactly as a user would -- ``inodefence`` from ``PATH`` after
``pip install -e .`` -- for one target: ``verify`` on a pinned version, then a small ``explore``,
then ``status`` and ``summary`` on what they wrote. It checks the two things the 0.2.x
compatibility promise covers (D049): the exit code and a ``result.json`` that the reader accepts
with its saved inputs.

This is an engineering smoke of the product path, not a registered experiment, and its results
are a ``demo run``. It adds no isolation setting of its own: every run goes through the same
drivers and launchers as a user's.

Public logs: this runs in CI on a public repository. The child commands' output is written to
files under ``--out`` and is printed only for a harness failure (exit 2 or 3). If a run ends with
a FAIL verdict, only that fact is printed -- no case, input or version detail (SECURITY.md).

Usage::

    python scripts/dev/product_e2e.py --target node-tar --out /tmp/inodefence-e2e
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from inodefence.target_result import (
    ResultMode,
    TargetResult,
    TargetResultError,
    Verdict,
    load_target_result,
)

#: One pinned version per target: the ones the recorded demo runs used (docs/USAGE.md). ``args``
#: are the target's own options. ``extraction_expected`` is False only where a known gap makes the
#: extractor refuse the common seeds; the count is still printed.
PINS: dict[str, dict[str, object]] = {
    "node-tar": {"version": "7.5.23", "args": [], "extraction_expected": True},
    "python-tarfile": {
        "version": "3.12.16",
        "args": ["--extraction-filter", "data"],
        "extraction_expected": True,
    },
    "decompress": {
        "version": "@xhmikosr/decompress@11.1.4",
        "args": [],
        "extraction_expected": True,
    },
    # Common seeds lack the ``d/`` title prefix oras-go requires, so every run is rejected
    # (BACKLOG P-3). Flip this to True in the change that fixes the seeds.
    "oras-go": {"version": "2.6.2", "args": [], "extraction_expected": False},
}

DEFAULT_BUDGET = 20
DEFAULT_SEED = 123
COMMAND_TIMEOUT_SECONDS = 1500


@dataclass
class Step:
    name: str
    exit_code: int
    log: Path


class E2EFailure(Exception):
    """A check of this script failed; the message is safe to print in a public log."""


def _run(inodefence: str, name: str, argv: list[str], logs: Path) -> Step:
    log = logs / f"{name}.log"
    with log.open("w", encoding="utf-8") as handle:
        handle.write(f"$ inodefence {' '.join(argv)}\n")
        handle.flush()
        try:
            done = subprocess.run(
                [inodefence, *argv],
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise E2EFailure(f"{name}: no exit after {COMMAND_TIMEOUT_SECONDS}s") from error
    print(f"{name}: exit {done.returncode}", flush=True)
    return Step(name, done.returncode, log)


def _show(step: Step) -> None:
    """Print a step's captured output (harness failures only; see the module docstring)."""
    print(f"----- {step.name} output -----")
    print(step.log.read_text(encoding="utf-8", errors="replace"))
    print(f"----- end {step.name} -----", flush=True)


def _expect_exit(step: Step, allowed: tuple[int, ...]) -> None:
    if step.exit_code in allowed:
        return
    if step.exit_code == 1:
        raise E2EFailure(
            f"{step.name}: ended with a FAIL verdict. Details are not printed in a public log; "
            "reproduce on a private host and follow SECURITY.md."
        )
    _show(step)
    raise E2EFailure(f"{step.name}: exit {step.exit_code}, expected one of {allowed}")


def _only_result(folder: Path, what: str) -> Path:
    found = sorted(folder.rglob("result.json"))
    if len(found) != 1:
        raise E2EFailure(f"{what}: expected one result.json under {folder}, found {len(found)}")
    return found[0]


def _load(path: Path, what: str) -> TargetResult:
    try:
        return load_target_result(path, verify_inputs=True)
    except (TargetResultError, OSError, ValueError) as error:
        raise E2EFailure(f"{what}: result.json was not accepted by the reader: {error}") from error


def check_target(inodefence: str, target: str, out: Path, budget: int, seed: int) -> None:
    pin = PINS[target]
    version = str(pin["version"])
    extra = [str(item) for item in pin["args"]]  # type: ignore[union-attr]
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    selector = ["--target", target, "--version", version, *extra]

    verify_out = out / "verify"
    verify_argv = ["verify", *selector, "--auto-prepare", "--out", str(verify_out)]
    verify = _run(inodefence, "verify", verify_argv, logs)
    _expect_exit(verify, (0,))
    verified = _load(_only_result(verify_out, "verify"), "verify")
    if verified.mode is not ResultMode.FIXTURE_REGRESSION or verified.verdict is not Verdict.PASS:
        raise E2EFailure("verify: exit 0 but the result is not a PASS fixture regression")
    if verified.target != target or verified.executed == 0:
        raise E2EFailure("verify: the result names another target or ran no case")
    if "BENIGN-CONTROL ok" not in verify.log.read_text(encoding="utf-8", errors="replace"):
        _show(verify)
        raise E2EFailure("verify: the benign-input control did not report ok")

    explore_out = out / "explore"
    explore = _run(
        inodefence,
        "explore",
        [
            "explore",
            *selector,
            "--budget",
            str(budget),
            "--seed",
            str(seed),
            "--auto-prepare",
            "--out",
            str(explore_out),
        ],
        logs,
    )
    _expect_exit(explore, (0,))
    result_path = _only_result(explore_out, "explore")
    explored = _load(result_path, "explore")
    if explored.mode is not ResultMode.CAMPAIGN or explored.campaign is None:
        raise E2EFailure("explore: the result is not a campaign result")
    if explored.target != target or explored.executed != budget:
        raise E2EFailure(
            f"explore: ran {explored.executed} of {budget} executions (or another target)"
        )
    extracted = explored.termination_counts["success"]
    print(f"explore: {extracted}/{explored.executed} executions extracted", flush=True)
    if pin["extraction_expected"] and extracted == 0:
        raise E2EFailure("explore: no execution was extracted, so nothing was really explored")

    for name, argv in (
        ("status", ["status", str(explore_out)]),
        ("summary", ["summary", str(result_path)]),
        ("replay-refuses-verify-folder", ["replay", str(_only_result(verify_out, "v").parent)]),
    ):
        step = _run(inodefence, name, argv, logs)
        # A verify result folder holds no exploration case: replay must say it cannot (exit 2).
        _expect_exit(step, (2,) if name.startswith("replay") else (0,))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end check of the installed inodefence command (demo run)."
    )
    parser.add_argument("--target", required=True, choices=sorted(PINS))
    parser.add_argument("--out", required=True, type=Path, help="empty folder outside the repo")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    inodefence = shutil.which("inodefence")
    if inodefence is None:
        print("inodefence is not on PATH (pip install -e . first)", file=sys.stderr)
        return 3
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        print(f"--out {out} is not empty", file=sys.stderr)
        return 3
    out.mkdir(parents=True, exist_ok=True)

    try:
        for name, command in (("doctor", ["doctor"]), ("targets", ["targets"])):
            (out / "logs").mkdir(exist_ok=True)
            step = _run(inodefence, name, command, out / "logs")
            if step.exit_code != 0:
                _show(step)
                raise E2EFailure(f"{name}: exit {step.exit_code}")
        check_target(inodefence, args.target, out, args.budget, args.seed)
    except E2EFailure as failure:
        print(f"PRODUCT-E2E FAIL ({args.target}): {failure}", file=sys.stderr)
        return 1
    print(f"PRODUCT-E2E PASS ({args.target}, demo run): verify, explore, status, summary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
