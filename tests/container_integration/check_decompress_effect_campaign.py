"""Native closure for M4 self-discovery: the generic fuzz loop drives REAL decompress and the
unchanged oracle decides the hit -- a second extractor attempting self-discovery, not a controlled
differential.

Unlike ``check_decompress_generality.py`` (a controlled reference differential on a committed
fixture), this runs the effect campaign (``run_decompress_effect_campaign``): it mutates the generic
benign seeds, runs each child through the real pinned decompress image (the ``frame`` worker, via
``run_decompress_frame_case``), and lets the feedback -- the set-based boundary-attempt v1 frame
(``frame_boundary_attempt_keys``) plus the generic C0/C1/C2 oracle verdict -- steer the next
mutation. A "hit" is a generic oracle violation the loop reached by mutation, never a planted PoC
(D006): the seeds are the benign ``minimal_seed_corpus`` baselines.

Honesty / pre-registration (fixed in this committed file; change it in a commit, not at run time):
  * seeds = ``minimal_seed_corpus()`` (benign regular/dir/hardlink-in-archive/symlink-in-archive).
  * mutation policy default = ``M1_GENERIC_ESCAPE_HARDLINK`` -- the TOKEN-CLEAN (blind) escaping
    arm: its link-target vocabulary is the generic alphabet only (a, b, dir, file, item, ., ..), so
    it can escape the extraction root but CANNOT spell a target-specific name such as the sentinel.
    An honest blind attempt. ``INODEFENCE_DECOMPRESS_POLICY`` may select
    ``M1_STATE_AWARE_ESCAPE_HARDLINK`` instead; that arm composes targets from object NAMES the run
    observes in the general tree (which include the external sentinel's name), so it is NOT blind --
    a positive under it must be disclosed as name-observation-driven, not blind rediscovery.
  * random seed, budget (``INODEFENCE_DECOMPRESS_BUDGET``, default 24) and image are fixed before
    the run; the result is reported positive OR negative as-is (a negative is a true negative, not a
    failure). The report distinguishes observed (the run output) from any later interpretation.

This is a container_integration check: it needs host Docker and the pinned affected decompress image
(``inodefence-decompress:4.2.1``, built from ``tools/decompress/Dockerfile`` with the updated
``worker.cjs`` that has the ``frame`` subcommand), supplied via the ``container_backend`` /
``container_image`` fixtures. The ``check_`` prefix keeps it out of ``make check``; it is the
controller-run companion, run by hand or a controller mode on a Docker host, under the SAME locked
harness (hardened isolation, no isolation-relaxing flag). Generic oracle only: no CVE identifier,
PoC seed, release string or answer path enters any verdict or the mutation vocabulary (D005/D006).
"""

import json
import os
from pathlib import Path

from inodefence.decompress_effect_campaign import (
    DecompressEffectCampaignConfig,
    decompress_effect_campaign_report,
    run_decompress_effect_campaign,
)
from inodefence.effect_pipeline_decompress import DecompressFrameRun, run_decompress_frame_case
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model import ArchiveCase, ExecutionStatus
from inodefence.mutator import MutationPolicy
from inodefence.targets.decompress_effect import DecompressFrameTarget

_RANDOM_SEED = 20261030
_DEFAULT_BUDGET = 24
_DEFAULT_EVIDENCE = "/tmp/inodefence-decompress-effect-campaign.json"


def test_native_decompress_effect_campaign_self_discovery(container_backend, container_image):
    budget = int(os.environ.get("INODEFENCE_DECOMPRESS_BUDGET", _DEFAULT_BUDGET))
    policy = MutationPolicy(
        os.environ.get(
            "INODEFENCE_DECOMPRESS_POLICY", MutationPolicy.M1_GENERIC_ESCAPE_HARDLINK.value
        )
    )
    evidence = Path(os.environ.get("INODEFENCE_DECOMPRESS_EVIDENCE", _DEFAULT_EVIDENCE))

    target = DecompressFrameTarget.bind(container_backend, container_image)
    # Distinguish the native producer in the report; never a synthetic/test label. The observed
    # module@version;node identity lives in the bound target's provenance.target_version.
    producer = f"native-decompress[{target.provenance.target_version}]"

    def produce(case: ArchiveCase) -> DecompressFrameRun:
        return run_decompress_frame_case(case, target)

    config = DecompressEffectCampaignConfig(
        random_seed=_RANDOM_SEED, execution_budget=budget, mutation_policy=policy
    )
    result = run_decompress_effect_campaign(minimal_seed_corpus(), produce, config)
    report = decompress_effect_campaign_report(result, producer=producer, label="demo run")
    evidence.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    # Loop invariants (NOT a positive-outcome assertion: a negative self-discovery is honest).
    assert len(result.steps) == budget
    for step in result.steps:
        # Each step is a real run: a parsed frame XOR a frame_error, and a 3-verdict oracle.
        assert (step.run.frame is not None) != (step.run.frame_error is not None)
        assert len(step.run.base_result.violations) == 3
        assert step.run.base_result.execution.status in ExecutionStatus
    # Report the self-discovery outcome as observed; do not assert a specific sign.
    print(
        f"decompress self-discovery: discovered_violation={result.discovered_violation} "
        f"unique_attempt_keys={result.final_stats.unique_attempt_keys} "
        f"unique_violation_fingerprints={result.final_stats.unique_violation_fingerprints} "
        f"evidence={evidence}"
    )
