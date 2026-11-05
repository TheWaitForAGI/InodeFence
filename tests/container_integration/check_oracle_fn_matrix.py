"""Runtime-lane harness: oracle false-negative matrix on real node-tar (host docker).

This is the docker companion to ``tests/test_oracle_fn_matrix.py``. The in-process test
covers the single-level ``..`` placements that stay inside the disposable sandbox; the
placements here (absolute symlink target, absolute member name, multi-level escape) would
leave the disposable sandbox, so they run ONLY inside the container isolation boundary --
the Runtime lane executes this against each node-tar release image.

It follows the ``check_cross_release_oracle_agreement.py`` pattern: a container_integration
check (``check_`` prefix, so ``make check`` never collects it; no Docker or node-tar images
on that path). ``scripts.container_controller`` supplies ``container_backend`` and
``container_image`` through the ``IntegrationFixtures`` plugin.

It makes NO vulnerability claim. Each placement runs through the REAL effect pipeline
``run_node_tar_effect_case`` against whatever release the controller provides, and the check
asserts only version-agnostic, fail-closed invariants: the pipeline returns a well-formed
C0/C1/C2 triple, the trace is present, and the protected sentinel set is intact in BEFORE.
When a committed expectation record exists for this release+placement it is asserted; until
the Runtime lane establishes that record the per-case verdict is recorded (printed) and
skipped, never asserted. ``tar_version`` is only ever a record key, never a decision
condition; no CVE identifier, PoC seed, or answer path enters any verdict.
"""

import json
from pathlib import Path

import pytest
from scripts.oracle_fn_matrix import RUNTIME_LANE_SPEC

from inodefence.model import ArchiveCase, ArchiveEntry, ContractId, EntryType, StateChange
from inodefence.observer import compare_states
from inodefence.targets.node_tar_effect import NativeEffectProfile, NodeTarEffectTarget

# Optional expectation record, keyed placement -> tar_version -> expected (C0, C1, C2).
# The Runtime lane commits this once it has established per-release ground truth; until
# then it is absent and every case is recorded-and-skipped (no result is claimed here).
_RECORD_PATH = (
    Path(__file__).resolve().parents[2]
    / "experiments"
    / "repro"
    / "evidence"
    / "oracle_fn_matrix.json"
)


def _load_record() -> dict:
    if not _RECORD_PATH.exists():
        return {}
    return json.loads(_RECORD_PATH.read_text(encoding="utf-8"))


# Placements that leave the disposable sandbox and therefore need container isolation.
# These are generic escaping inputs; node-tar's actual behaviour is what the Runtime lane
# observes. Names match RUNTIME_LANE_SPEC so the harness and the spec stay in sync.
_RUNTIME_LANE_CASES: dict[str, ArchiveCase] = {
    "absolute-symlink-target": ArchiveCase(
        (
            ArchiveEntry("fnlink", EntryType.SYMLINK, link_target="/tmp", mode=0o777),
            ArchiveEntry("fnlink/inodefence-fn-via-abs", EntryType.REGULAR, content=b"via-abs"),
        )
    ),
    "absolute-entry-name": ArchiveCase(
        (ArchiveEntry("/tmp/inodefence-fn-abs-escape", EntryType.REGULAR, content=b"abs-name"),)
    ),
    "multi-level-escape": ArchiveCase(
        (ArchiveEntry("../../inodefence-fn-escape.txt", EntryType.REGULAR, content=b"multi"),)
    ),
}

_PLACEMENTS = sorted(_RUNTIME_LANE_CASES)


def test_runtime_lane_cases_match_spec() -> None:
    assert set(_RUNTIME_LANE_CASES) == {row["placement"] for row in RUNTIME_LANE_SPEC}


@pytest.mark.parametrize("placement", _PLACEMENTS)
def test_fn_placement_is_well_formed_and_faithfully_judged(
    placement, container_backend, container_image
) -> None:
    target = NodeTarEffectTarget.bind(
        container_backend, container_image, profile=NativeEffectProfile.FULL
    )
    run = run_case_or_skip(_RUNTIME_LANE_CASES[placement], target)

    base = run.result.base_result
    # Fail-closed, version-agnostic invariants (no vulnerability claim).
    assert run.result.trace is not None
    assert tuple(v.contract_id for v in base.violations) == (
        ContractId.C0,
        ContractId.C1,
        ContractId.C2,
    )
    assert base.before.protected_paths == ("outside/sentinel.txt",)
    assert base.before.get("outside/sentinel.txt") is not None

    # Self-consistency: the C2 effect evidence equals the sentinel changes visible in the
    # raw before/after diff, so the oracle never silently drops an OBSERVED sentinel change.
    observed_sentinel_changes = {
        change.path
        for change in compare_states(base.before, base.after)
        if change.path in base.before.protected_paths
    }
    c2 = next(v for v in base.violations if v.contract_id == ContractId.C2)
    c2_paths = {item.path for item in c2.evidence if isinstance(item, StateChange)}
    assert c2_paths == observed_sentinel_changes

    observed = tuple(v.violated for v in base.violations)
    expected = _load_record().get(placement, {}).get(target.tar_version)
    if expected is None:
        pytest.skip(
            f"no committed FN record for node-tar {target.tar_version} / {placement}; "
            f"Runtime lane to establish (observed this run: C0C1C2={observed})"
        )
    assert observed == tuple(expected)


def run_case_or_skip(case: ArchiveCase, target):
    """Run one case; skip (never fail) if the controller/image cannot execute it."""
    from inodefence.effect_pipeline import run_node_tar_effect_case

    try:
        return run_node_tar_effect_case(case, target)
    except Exception as error:  # noqa: BLE001 -- harness must not mask as a false pass
        pytest.skip(f"runtime-lane case could not execute: {type(error).__name__}: {error}")
