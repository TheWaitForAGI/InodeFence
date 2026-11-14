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
from collections.abc import Callable
from hashlib import sha256
from time import perf_counter
from typing import Any

from inodefence.builder import build_tar
from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_demo import EffectStepReporter, effect_campaign_report
from inodefence.effect_pipeline_python_tarfile import run_python_tarfile_contained_case
from inodefence.evaluation.rds import (
    VOCABULARY_MUTATION_POLICY,
    RdsArm,
    VocabularyMode,
    arm_search_policy,
)
from inodefence.execution.base import ExecutionBackend
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ArchiveCase, EffectRunResult, ExecutionStatus
from inodefence.mutator import MutationPolicy
from inodefence.runtime import SentinelSpec
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


def case_record(run_index: int, result: EffectRunResult) -> dict[str, object]:
    """One step's verdict; only a run the extractor's report does not account for has none.

    SUCCESS / REJECTED, and FAILED with a readable worker report (tarfile raised while
    extracting), all have real host snapshots, so the oracle verdict stands. A timeout or a worker
    report that cannot be read (crash, truncation) is ``run_error``: no verdict.
    """
    base = result.base_result
    status = base.execution.status
    reported = worker_reported_status(base.execution.stdout)
    outcome = {
        ExecutionStatus.SUCCESS: "extracted",
        ExecutionStatus.REJECTED: "declined",
        ExecutionStatus.FAILED: "failed",
    }.get(status)
    if (
        outcome is None
        or reported is None
        or reported
        != {
            "extracted": "success",
            "declined": "rejected",
            "failed": "failed",
        }[outcome]
    ):
        return {"run_index": run_index, "outcome": "run_error", "c0": None, "c1": None, "c2": None}
    hit = {v.contract_id.value: v.violated for v in base.violations}
    return {
        "run_index": run_index,
        "outcome": outcome,
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
) -> dict[str, Any]:
    """Run the shared effect loop on one prepared python runtime image and one filter."""
    if extraction_filter == "fully_trusted" and not allow_fully_trusted:
        raise ValueError(
            "fully_trusted exploration is held until approved; pass allow_fully_trusted=True "
            "only with that approval (data is the default)"
        )
    target = PythonTarfileContainedTarget.bind(
        backend, image_id, extraction_filter, expected_python=expected_python
    )
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
    result = run_effect_campaign(minimal_seed_corpus(), produce, config, on_step=record_step)
    total = perf_counter() - started
    undetermined = sum(1 for record in case_records if record["outcome"] == "run_error")
    report = effect_campaign_report(result, "native-python-tarfile-container")
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
        vocabulary=next(
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
    return report
