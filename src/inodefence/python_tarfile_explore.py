"""python-tarfile exploration: the shared effect loop over the contained python-tarfile worker.

There is no python-specific loop. ``python_tarfile_exploration_report`` binds one prepared runtime
image with ONE extraction filter (``PythonTarfileContainedTarget``) and hands
``run_python_tarfile_contained_case`` to ``effect_campaign.run_effect_campaign`` -- the loop
node-tar's exploration uses -- with the same default search and mutation policies. The report has
node-tar exploration's shape (``effect_campaign_report`` plus ``case_records`` and
``violation_inputs``) so the host side converts both the same way.

Axes: a campaign runs on one runtime version (the bound image, checked against
``expected_python``) and one filter; comparing filters or runtimes means separate campaigns.

``fully_trusted`` runs only when the caller passes ``allow_fully_trusted=True``. The extraction is
inside the container boundary either way; the default is held until that use is approved.

Silent negatives: a step whose run did not complete (run error) has no C0/C1/C2 verdict and is
counted in ``undetermined_steps``; if every step is undetermined, ``all_undetermined`` is true and
the host side must report ERROR, never PASS.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from hashlib import sha256
from time import perf_counter
from typing import Any

from inodefence.builder import BUILDER_FORMAT, build_tar
from inodefence.campaign_hooks import CampaignHooks, LightCampaignResult
from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_demo import (
    DEMO_REPORT_SCHEMA,
    EffectStepReporter,
    effect_campaign_report,
)
from inodefence.effect_pipeline_python_tarfile import run_python_tarfile_contained_case
from inodefence.evaluation.rds import (
    VOCABULARY_MUTATION_POLICY,
    RdsArm,
    VocabularyMode,
    arm_search_policy,
)
from inodefence.execution.base import ExecutionBackend
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import SeedCorpusId, minimal_seed_corpus, seed_corpus_label
from inodefence.model import ArchiveCase, EffectRunResult, ExecutionStatus
from inodefence.mutator import MutationPolicy
from inodefence.mutator.policy import SEED_CORPUS
from inodefence.runtime import SentinelSpec
from inodefence.targets.identity_schedule import apply_identity_schedule, finish_identity_schedule
from inodefence.targets.python_tarfile_contained import (
    PythonTarfileContainedTarget,
    worker_reported_status,
)

EXPLORATION_LABEL = "exploratory demo run"
#: Defaults are the registered experiment's S-u arm, read from its definition (not copied):
#: state-retention uniform search over the observed-names (fixed-baseline) vocabulary.
DEFAULT_VOCABULARY = VocabularyMode.OBSERVED_NAMES
DEFAULT_SEARCH_POLICY = arm_search_policy(RdsArm.S_U)
DEFAULT_MUTATION_POLICY = VOCABULARY_MUTATION_POLICY[DEFAULT_VOCABULARY]


#: What the worker's own final line must say for the step to be attributed to the extractor.
_WORKER_STATUS = {
    ExecutionStatus.SUCCESS: "success",
    ExecutionStatus.REJECTED: "rejected",
    ExecutionStatus.FAILED: "failed",
}


#: User decision D1 (2026-11-16) with an ORCH-recorded deviation for python-tarfile: a ``failed``
#: run whose worker report agrees with the exit status (tarfile raised and the worker caught and
#: reported it -- an observed, explicit refusal by the extractor) stays judged on its snapshot
#: verdict. Set to ``False`` to apply D1 literally (every failed run without a violation is
#: unjudged), the single switch if the user overrules the deviation. Measured with the local
#: backend, data filter, budget 40: such failures were 8% / 8% / 28% of runs for seeds 1 / 7 / 123
#: (FileExistsError, IsADirectoryError, unresolvable/missing link) -- literal D1 would turn the
#: seed-123 clean exploration into ERROR (over the 0.2 ceiling).
REPORTED_FAILURE_IS_JUDGED = True


def worker_error_class(stdout: str) -> str | None:
    """The exception class the worker reported for a failed run (``"FileExistsError"``), if any."""
    lines = [line for line in stdout.splitlines() if line.strip()]
    try:
        error = json.loads(lines[-1]).get("error") if lines else None
    except (ValueError, AttributeError):
        return None
    if not isinstance(error, str) or not error:
        return None
    return error.split(":", 1)[0].strip() or None


def run_unjudged(result: EffectRunResult) -> bool:
    """Exploration only -- the ONE python-tarfile rule (D1, with the reported-failure deviation).

    1. The oracle saw a violation in the snapshots -> judged, always (kept with its input, read as
       "reproduction check needed" when the run was not clean).
    2. Otherwise unjudged when: the worker report is unreadable or contradicts the exit status
       (crash, truncation) for a non-timeout run; the run ``timed_out``; or it is a ``success``
       whose trace is not intact. A complete trace needs the worker's own member count to equal
       the entries (#533), so an empty archive's success is intact exactly when the worker
       reports ``members: 0``.
    3. A ``rejected`` run, and a ``failed`` run whose report agrees (see
       :data:`REPORTED_FAILURE_IS_JUDGED`), stays judged.

    The same rule decides the report's per-step ``validity``
    (``effect_demo.observer_integrity_validity``: a ``success`` without an intact trace is
    invalid), so the two records agree; there is no empty-archive exception (#533).
    """
    base = result.base_result
    status = base.execution.status
    if any(v.violated for v in base.violations):
        return False
    if status is ExecutionStatus.TIMED_OUT:
        return True
    if worker_reported_status(base.execution.stdout) != _WORKER_STATUS.get(status):
        return True
    if status is ExecutionStatus.FAILED:
        return not REPORTED_FAILURE_IS_JUDGED
    return status is ExecutionStatus.SUCCESS and not result.trace.integrity_valid


def case_record(run_index: int, result: EffectRunResult) -> dict[str, object]:
    """One step on the two separate axes of the common result format (#414).

    ``outcome`` is the judgment axis only: ``judged`` (C0/C1/C2 from the real host BEFORE/AFTER
    snapshots) or ``run_error`` (no verdict, all None), decided by :func:`run_unjudged`.
    ``termination`` is the execution status; ``observation_complete`` is the trace's
    ``integrity_valid``, as for node-tar. A failed run also carries ``worker_error`` (the
    exception class the worker reported), so the report shows why it failed and was still judged.
    Exploration record only: the loop receives the unchanged ``EffectRunResult``.
    """
    base = result.base_result
    status = base.execution.status
    record: dict[str, object] = {
        "run_index": run_index,
        "termination": status.value,
        # Same definition as node-tar: complete, no observation failure, flushed to the end.
        "observation_complete": result.trace.integrity_valid,
    }
    if status is ExecutionStatus.FAILED:
        record["worker_error"] = worker_error_class(base.execution.stdout)
    if run_unjudged(result):
        return {**record, "outcome": "run_error", "c0": None, "c1": None, "c2": None}
    hit = {v.contract_id.value: v.violated for v in base.violations}
    return {
        **record,
        "outcome": "judged",
        "c0": hit.get("C0"),
        "c1": hit.get("C1"),
        "c2": hit.get("C2"),
    }


def python_tarfile_exploration_report(
    backend: ExecutionBackend,
    image_id: str,
    extraction_filter: str,
    expected_python: str,
    *,
    seed: int = 123,
    budget: int = 20,
    policy: EffectSearchPolicy = DEFAULT_SEARCH_POLICY,
    mutation_policy: MutationPolicy = DEFAULT_MUTATION_POLICY,
    sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),),
    allow_fully_trusted: bool = False,
    step_sink: Callable[[dict[str, object]], None] | None = None,
    requested_spec: str | None = None,
    identity_check_every: int | None = None,
    stream: bool = True,
) -> dict[str, Any]:
    """Run the shared effect loop on one prepared python runtime image and one filter.

    ``identity_check_every`` (FAST exploration only, #536): probe the image identity every N cases
    and at the end instead of before every case; ``None`` keeps the per-case probe (STRICT).

    ``stream`` (default, #542): the loop keeps no step in memory; the report then has no ``steps``
    (they went to ``step_sink``, the controller's ``.steps.jsonl``) and says ``streaming: true``.
    ``stream=False`` is the retaining run (full ``steps`` in the report), kept as the comparison
    baseline: both give the same ``case_records``, ``violation_inputs`` and retained corpus.

    A mutation policy bound to a seed corpus other than the registered one (v2.1
    ``minimal-empty-reg-v1``) is refused before the target is bound: its empty-archive seed is
    recorded invalid on this target (#533; W4: not used off node-tar until fixed). The v2 policy
    on the registered corpus is accepted as before.
    """
    if SEED_CORPUS.get(mutation_policy, SeedCorpusId.REGISTERED) != SeedCorpusId.REGISTERED:
        raise ValueError(
            f"{mutation_policy.value} binds a non-registered seed corpus; it is not supported "
            "by the python-tarfile loop until #533 is fixed "
            "(등록 코퍼스가 아닌 v2.1 코퍼스 정책은 이 대상 루프에서 지원하지 않는다)"
        )
    if extraction_filter == "fully_trusted" and not allow_fully_trusted:
        raise ValueError(
            "fully_trusted exploration is held until approved; pass allow_fully_trusted=True "
            "only with that approval (data is the default)"
        )
    target = PythonTarfileContainedTarget.bind(
        backend, image_id, extraction_filter, expected_python=expected_python
    )
    target, schedule = apply_identity_schedule(target, identity_check_every)
    config = EffectCampaignConfig(
        random_seed=seed,
        execution_budget=budget,
        search_policy=policy,
        mutation_policy=mutation_policy,
    )
    case_records: list[dict[str, object]] = []
    violation_inputs: list[dict[str, object]] = []

    def produce(case: ArchiveCase) -> EffectRunResult:
        run_index = len(case_records)
        result = run_python_tarfile_contained_case(case, target, sentinels=sentinels)
        record = case_record(run_index, result)
        case_records.append(record)
        if record["c0"] or record["c1"] or record["c2"]:
            tar = build_tar(case)
            violation_inputs.append(
                {
                    "run_index": run_index,
                    "tar_sha256": sha256(tar).hexdigest(),
                    "tar_b64": base64.b64encode(tar).decode("ascii"),
                }
            )
        return result

    reporter = EffectStepReporter()

    def record_step(step) -> None:  # type: ignore[no-untyped-def]
        line = reporter.add(step)
        if step_sink is not None:
            step_sink(line)

    started = perf_counter()
    corpus = minimal_seed_corpus()
    # Streaming (#542): the loop keeps no step in memory (each one went to ``record_step`` and the
    # controller's ``.steps.jsonl``), so memory no longer grows with full per-step snapshots and
    # traces. ``case_records`` (one small verdict record per case) stays, so the common result
    # built from it is byte-identical to the retaining run.
    if stream:
        light = run_effect_campaign(
            corpus, produce, config, hooks=CampaignHooks(on_step=record_step, retain_steps=False)
        )
        assert isinstance(light, LightCampaignResult)
    else:
        full = run_effect_campaign(corpus, produce, config, on_step=record_step)
    identity_record = finish_identity_schedule(target, schedule)  # FAST: mismatch raises
    total = perf_counter() - started
    undetermined = sum(1 for record in case_records if record["outcome"] == "run_error")
    report = (
        _streaming_report(config, light, tuple(case.case_id for case in corpus))
        if stream
        else effect_campaign_report(full, PRODUCER)
    )
    report.update(
        label=EXPLORATION_LABEL,
        mode="exploration",
        qualification=False,
        target="python-tarfile",
        runtime_version=target.python_version,
        extraction_filter=extraction_filter,
        requested_spec=requested_spec,
        search_policy=policy.value,
        # The registered vocabulary mode this mutation policy realizes, or None if none does.
        vocabulary_mode=next(
            (
                mode.value
                for mode, mp in VOCABULARY_MUTATION_POLICY.items()
                if mp is mutation_policy
            ),
            None,
        ),
        image_id=image_id,
        worker_sha256=target.worker_sha256,
        tarfile_sha256=target.tarfile_sha256,
        timing={"total_seconds": total},
        case_records=case_records,
        violation_inputs=violation_inputs,
        undetermined_steps=undetermined,
        all_undetermined=bool(case_records) and undetermined == len(case_records),
    )
    report.update(identity_record)
    return report


PRODUCER = "native-python-tarfile-container"


def _streaming_report(
    config: EffectCampaignConfig, result: LightCampaignResult, initial_case_ids: tuple[str, ...]
) -> dict[str, Any]:
    """The loop report's common part without per-step records (#542).

    The same keys as ``effect_campaign_report`` except the three derived from retained steps
    (``steps``, ``observer_integrity_summary``, ``final_search_stats``), plus ``streaming: true``.
    The steps are in the controller's ``<report>.steps.jsonl`` (one line per step, written as each
    step completes), which is where step readers such as ``scripts/compare_fast_strict.py`` look
    first.
    """
    return {
        "demo_report_schema": DEMO_REPORT_SCHEMA,
        "producer": PRODUCER,
        "streaming": True,
        "mutation_policy": config.mutation_policy.value,
        "config": {
            "random_seed": config.random_seed,
            "execution_budget": config.execution_budget,
            "search_policy": config.search_policy.value,
            "mutation_policy": config.mutation_policy.value,
            "build_invalid": config.build_invalid_policy.value,
            "builder_format": BUILDER_FORMAT,
            "seed_corpus": seed_corpus_label(initial_case_ids),
        },
        "initial_case_ids": list(initial_case_ids),
        "retained_case_ids": list(result.retained_case_ids),
        "executed": result.executed,
    }
