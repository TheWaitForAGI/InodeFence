"""node-tar's exploration hook: open the state-aware effect loop on a prepared node-tar image.

This is the node-tar implementation of ``TargetAdapter.explore``
(``inodefence.drivers.run_target``). The
common driver (``inodefence.drivers.run_target_explore``) prepares the image and passes a
``PreparedTargetImage`` plus target-agnostic ``ExploreOptions``; everything here is node-tar
specific -- the controller mode (``effect-demo-explore``), the run program, and the node-tar
observation -- and it emits the common ``inodefence-target-result-v1`` campaign result.

Other extractors register their own ``explore`` hook the same way; a target with no hook reports
"exploration not supported". The result format, options, output and (later) stop conditions and
sinks are reused unchanged across targets.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from inodefence.drivers.explore_result import (
    build_campaign_result,
    refuse_existing,
    with_fast_acceptance_scope,
    with_identity_checks,
    with_per_case_identity_marker,
    write_result,
)
from inodefence.drivers.launcher import launcher_path, run_launcher
from inodefence.drivers.repo import code_checkout
from inodefence.drivers.run_target import (
    MUTATION_POLICY_ENV,
    ExploreOptions,
    ExploreOutcome,
    PreparedTargetImage,
    drop_inherited_mutation_policy,
    drop_inherited_search_policy,
    engine_provenance,
    requested_identity_check_every,
)
from inodefence.drivers.runtime.hooks import LaunchArtifacts
from inodefence.evaluation.rds import VOCABULARY_MUTATION_POLICY, VocabularyMode
from inodefence.evaluation.rds_preregistration import parse_preregistration
from inodefence.generator import minimal_seed_corpus
from inodefence.live_exploration import LivePuller
from inodefence.target_result_summary import write_cell_summaries

REPO_ROOT = code_checkout()
SMOKE = launcher_path("node-tar", REPO_ROOT)
# Writable tmpfs path inside the controller (root is read-only); the host pulls it with docker cp.
CONTROLLER_LIVE_DIR = "/tmp/inodefence-live"
OBSERVED_CONTRACTS = ("C0", "C1", "C2")  # the effect path takes a full before/after snapshot
# One campaign must cover all initial seed cases, so a budget below the seed count is refused.
MIN_BUDGET = len(minimal_seed_corpus())
# Exploration matches the registered S-u sandbox: the same generated sentinel set and observer
# policy the confirmatory EXP-2 holdout uses, so the observed-names vocabulary pool and the
# invalid-trace handling are the experiment's, not a demo default. The values are READ from the
# frozen preregistration (never copied here), so the two cannot drift; the operator can still
# override them, and the run records what it actually used.
REGISTERED_PREREG = REPO_ROOT / "experiments" / "preregistration" / "exp2-v1.md"


def registered_sandbox_defaults() -> tuple[str, str, str]:
    """``(sentinel_seed, sentinel_count, observer_integrity_policy)`` of the registered S-u arm.

    The preregistration is the single source for these: if it does not carry one of the three
    fields, stop with the reason instead of silently falling back to a hardcoded value (or the
    literal string ``"None"``). A missing field means the preregistration changed and the
    reference drifted -- running exploration on a stale default would be a silent mismatch.
    """
    prereg = parse_preregistration(REGISTERED_PREREG.read_text(encoding="utf-8"))
    missing = [
        name
        for name, value in (
            ("sentinel_generator_seed", prereg.sentinel_generator_seed),
            ("sentinel_count", prereg.sentinel_count),
            ("observer_integrity_policy", prereg.observer_integrity_policy),
        )
        if value is None
    ]
    if missing:
        raise ValueError(
            f"{REGISTERED_PREREG.name} is missing registered sandbox field(s): "
            f"{', '.join(missing)}. Exploration must not fall back to a hardcoded default -- "
            f"update the preregistration (or its reference) so the field is present."
        )
    assert prereg.observer_integrity_policy is not None  # the check above guarantees this
    return (
        str(prereg.sentinel_generator_seed),
        str(prereg.sentinel_count),
        prereg.observer_integrity_policy,
    )


def controller_report_path(out: Path, run_id: str) -> Path:
    """Where ``local_node_tar_smoke.sh explore`` writes the loop's report for this run."""
    return out / "target-explore" / f"inodefence-effect-explore-{run_id}.json"


def run_controller(
    prepared: PreparedTargetImage,
    *,
    out: Path,
    run_id: str,
    budget: int,
    seed: int,
    python: str,
    mutation_policy: str | None = None,
    runner=subprocess.run,
    session=None,
) -> Path:
    """Run the loop in the controller via the smoke script; return the report path it wrote.

    The image is already prepared host-side; the script only builds the controller/helper images,
    creates the disposable controller, and drives ``effect-demo-explore``. The target containers'
    isolation is the controller's, unchanged.

    ``mutation_policy`` (``--mutation-policy``) is the only way a policy reaches the launcher: the
    caller's own ``DEMO_MUTATION_POLICY`` is not passed through, so a run without the option is
    the default run whatever the environment holds.
    """
    sentinel_seed, sentinel_count, observer_policy = registered_sandbox_defaults()
    # The engine revision is read host-side (the controller's read-only repo mount cannot run git)
    # and recorded in the live meta so a saved violation's replay can tell if the engine has moved.
    engine = engine_provenance(None)
    engine_commit = f"{engine.engine_sha or 'unknown'}{'-dirty' if engine.engine_dirty else ''}"
    # The controller name matches the smoke script's ``inodefence-local-controller[-RUN_ID]``; the
    # host live folder is ``<out>/target-explore/<run_id>/live`` so ``inodefence status
    # <out>/target-explore`` finds it (find_live_dirs matches ``*/live``) and parallel runs never
    # share a live folder.
    controller_name = f"inodefence-local-controller{f'-{run_id}' if run_id else ''}"
    host_live_dir = out / "target-explore" / run_id / "live"
    env = {
        **os.environ,
        "EXPLORE_IMAGE": prepared.image_ref,
        "TAR_VERSION": prepared.version,
        "DEMO_BUDGET": str(budget),
        "DEMO_SEED": str(seed),
        "DEMO_ENGINE_COMMIT": engine_commit,
        # Registered S-u sandbox defaults (overridable by the operator's own DEMO_* env).
        "DEMO_SENTINEL_SEED": os.environ.get("DEMO_SENTINEL_SEED", sentinel_seed),
        "DEMO_SENTINEL_COUNT": os.environ.get("DEMO_SENTINEL_COUNT", sentinel_count),
        "DEMO_OBSERVER_INTEGRITY_POLICY": os.environ.get(
            "DEMO_OBSERVER_INTEGRITY_POLICY", observer_policy
        ),
        "INODEFENCE_EVIDENCE_DIR": str(out),
        "RUN_ID": run_id,
        "PYTHON": python,
        # The controller writes live snapshots to this tmpfs path; the host pulls it below.
        "DEMO_LIVE_DIR": CONTROLLER_LIVE_DIR,
        # Where the smoke script copies the live folder on the host, BEFORE it removes the
        # controller -- the same folder the timer pulls to, so the final (state=finished) snapshot
        # reaches the host reliably instead of a post-removal pull failing with "No such container".
        "DEMO_HOST_LIVE_DIR": str(host_live_dir),
    }
    drop_inherited_mutation_policy(env)
    drop_inherited_search_policy(env)
    if mutation_policy is not None:
        env[MUTATION_POLICY_ENV] = mutation_policy
    # Pull the controller's live folder to the host on a timer while the loop runs, so progress and
    # violation cases appear during the run (and survive a forced stop). The controller name matches
    # the smoke script's ``inodefence-local-controller[-RUN_ID]``; a pull before it exists fails
    # quietly (recorded in fetch.json) and never stops the campaign. The final snapshot is taken by
    # the smoke script's copy before it removes the controller, so stop() skips a last pull.
    puller = LivePuller(controller_name, CONTROLLER_LIVE_DIR, host_live_dir).start()
    try:
        done = run_launcher(
            SMOKE,
            ["explore"],
            runner=runner,
            env=env,
            session=session,
            artifacts=LaunchArtifacts(
                report=controller_report_path(out, run_id), live=host_live_dir
            ),
            cwd=str(REPO_ROOT),
        )
    finally:
        puller.stop(final_pull=False)  # the smoke script's pre-removal copy is the final snapshot
    if done.returncode != 0:
        raise RuntimeError(f"controller run failed (exit {done.returncode}); see output above")
    report = controller_report_path(out, run_id)
    if not report.is_file():
        raise RuntimeError(f"controller run produced no report at {report}")
    return report


def check_ran_mutation_policy(report: dict, requested: str) -> None:
    """The loop report must show it ran ``requested`` (its ``vocabulary_mode``), or no result.

    The result records the policy only after this check, so ``campaign.mutation_policy`` is what
    the loop ran, not just what was asked for. A mismatch is an ERROR (exit 2): the run happened.
    """
    mode = report.get("vocabulary_mode")
    try:
        ran = VOCABULARY_MUTATION_POLICY[VocabularyMode(mode)].value
    except (ValueError, KeyError):
        ran = None
    if ran != requested:
        raise RuntimeError(
            f"the loop ran vocabulary mode {mode!r} (mutation policy {ran!r}), requested "
            f"{requested!r}; no result written"
        )


def explore(prepared: PreparedTargetImage, options: ExploreOptions) -> ExploreOutcome:
    """``TargetAdapter.explore`` for node-tar: run the loop in the controller, write the result."""
    if options.budget < MIN_BUDGET:
        raise ValueError(f"budget must be >= {MIN_BUDGET} (the loop's seed count)")
    options.out.mkdir(parents=True, exist_ok=True)
    run_id = f"{prepared.version}-{options.seed}-{options.budget}{options.image_tag_suffix}"
    # This run's report and result must not be there yet: refuse now (exit 3), not after the loop.
    planned = controller_report_path(options.out, run_id)
    refuse_existing(planned, planned.parent / f"{run_id}-result" / "result.json")
    python = os.environ.get("PYTHON", sys.executable)
    report_path = run_controller(
        prepared,
        out=options.out,
        run_id=run_id,
        budget=options.budget,
        seed=options.seed,
        python=python,
        mutation_policy=options.mutation_policy,
        session=getattr(options, "runtime", None),
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if "aborted" in report:  # the loop stopped after it started: ERROR (exit 2), no result
        aborted = report["aborted"]
        reason = aborted.get("reason") if isinstance(aborted, dict) else aborted
        raise RuntimeError(f"exploration aborted: {reason}")
    if options.mutation_policy is not None:
        check_ran_mutation_policy(report, options.mutation_policy)
    # The loop wrote each violation to this folder as it happened (pulled to the host during the
    # run); for a streaming report the result reads its violating cases and inputs from there, not
    # from the report, so a large or force-stopped run keeps every saved violation. Same path as
    # ``run_controller`` builds; absent only if no live folder was produced (then the report path).
    host_live_dir = options.out / "target-explore" / run_id / "live"
    result, tar_files = build_campaign_result(
        report,
        prepared,
        seed=options.seed,
        budget=options.budget,
        max_unjudged_ratio=options.max_unjudged_ratio,
        live_dir=host_live_dir if host_live_dir.is_dir() else None,
        mutation_policy=options.mutation_policy,
    )
    # FAST (#536): the loop's identity-probe record; STRICT: unchanged.
    result = with_identity_checks(result, report, requested_identity_check_every(options))
    # D065: when this target's FAST keeps the rebuild skip only, the result says so per case.
    result = with_per_case_identity_marker(result, getattr(options, "runtime", None))
    # W4 Q2 (ii): a FAST run with the interval says whether it is inside the measured scope.
    result = with_fast_acceptance_scope(
        result,
        getattr(options, "runtime", None),
        version=prepared.version,
        policy=options.mutation_policy or "default",
        budget=options.budget,
    )
    result_path = write_result(
        report_path.parent / f"{run_id}-result", result, tar_files, report=report_path
    )
    try:  # the result is written; a summary failure must not lose it
        write_cell_summaries([result_path])
    except Exception as error:  # noqa: BLE001
        print(f"TARGET-EXPLORE SUMMARY: summary.md not written ({error})", file=sys.stderr)
    print(f"loop report: {report_path}")
    return ExploreOutcome(
        result_path=result_path,
        verdict=result.verdict.value,
        runs=result.executed,
        violations=len(result.violating_cases),
    )
