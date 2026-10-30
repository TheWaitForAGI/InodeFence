"""The decompress self-discovery loop (M4): frame/violation feedback channels, loop mechanics,
determinism, and one real-pipeline end-to-end (fake backend, no docker) that aliases the sentinel
so the UNCHANGED production oracle fires C1 -- the "hit" a native campaign self-discovers.
"""

import json
import os
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.decompress_effect_campaign import (
    DecompressEffectCampaignConfig,
    DecompressEffectSearchState,
    decompress_effect_campaign_report,
    run_decompress_effect_campaign,
)
from inodefence.effect_pipeline_decompress import (
    DecompressFrameRun,
    _parse_frame,
    run_decompress_frame_case,
)
from inodefence.execution.base import ContainerOutcome, ExecutionBackend
from inodefence.feedback import state_signature
from inodefence.feedback.boundary_attempt_frame import FRAME_FORMAT
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    ObjectSnapshot,
    ObjectType,
    RunResult,
    SnapshotPhase,
    StateSnapshot,
)
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.targets.decompress_effect import DecompressFrameTarget
from inodefence.targets.isolated import IsolatedTarget

_ROOT = "/var/lib/inodefence/core-run-test"
_SENTINEL = "outside/sentinel.txt"
_IMAGE = "sha256:" + "a" * 64
_WORKER_SHA = "b" * 64


def _digest(content: bytes) -> str:
    return sha256(content).hexdigest()


def _obj(
    path: str, *, ino: int, nlink: int = 1, kind: ObjectType = ObjectType.REGULAR
) -> ObjectSnapshot:
    return ObjectSnapshot(
        path, kind, 9, ino, nlink, 0o600, 5, 0, 0, 1, 1, None, _digest(path.encode())
    )


def _snapshot(phase: SnapshotPhase, objects: tuple[ObjectSnapshot, ...]) -> StateSnapshot:
    # StateSnapshot requires unique, path-sorted objects; sort here so callers list in any order.
    return StateSnapshot(
        _ROOT, phase, tuple(sorted(objects, key=lambda obj: obj.path)), (_SENTINEL,)
    )


def _frame(attempts: tuple[dict, ...]) -> dict:
    return {
        "format": FRAME_FORMAT,
        "schema_version": 1,
        "extractor": "decompress@4.2.1",
        "extraction_root_absolute": _ROOT + "/extract",
        "attempts": list(attempts),
    }


def _external_hardlink_attempt() -> dict:
    return {
        "operation": "hardlink",
        "created_path": "extract/evil",
        "created_region": "extraction",
        "target_raw": "outside/sentinel.txt",
        "target_resolved_absolute": "outside/sentinel.txt",
        "target_region": "external",
        "aliases_external_object": True,
        "outcome": "created",
    }


def _run(
    case: ArchiveCase,
    *,
    before: tuple[ObjectSnapshot, ...],
    after: tuple[ObjectSnapshot, ...],
    frame: dict | None,
    frame_error: str | None = None,
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
) -> DecompressFrameRun:
    before_snap = _snapshot(SnapshotPhase.BEFORE, before)
    after_snap = _snapshot(SnapshotPhase.AFTER, after)
    execution = ExecutionResult(
        "decompress-boundary-attempt-frame",
        "decompress=decompress@4.2.1;node=22.23.4",
        ("node", "worker", "frame"),
        status,
        0 if status == ExecutionStatus.SUCCESS else 2,
        "",
        "",
        0.01,
    )
    base = RunResult(
        case,
        _digest(case.case_id.encode()),
        "ustar",
        execution,
        before_snap,
        after_snap,
        compare_states(before_snap, after_snap),
        state_signature(before_snap, after_snap),
        evaluate_contracts(before_snap, after_snap),
    )
    return DecompressFrameRun(base, frame, frame_error if frame is None else None)


_SENTINEL_ONLY = (_obj(_SENTINEL, ino=9),)
_BENIGN_CASE = ArchiveCase((ArchiveEntry("a.txt", EntryType.REGULAR, content=b"hi"),))
_ESCAPE_CASE = ArchiveCase(
    (ArchiveEntry("evil", EntryType.HARDLINK, link_target="outside/sentinel.txt"),)
)


def _benign_run(case: ArchiveCase) -> DecompressFrameRun:
    # A distinct extract object per case id keeps the full-state signature novel, so the corpus
    # grows from the benign seeds (no boundary attempt, no violation). The ino is a deterministic
    # function of the case id so two campaign runs with the same seed are byte-identical.
    ino = 100 + int(sha256(case.case_id.encode()).hexdigest()[:8], 16)
    extract = _obj(f"extract/{case.case_id[:8]}", ino=ino)
    return _run(case, before=_SENTINEL_ONLY, after=(*_SENTINEL_ONLY, extract), frame=_frame(()))


# --- feedback channels, via DecompressEffectSearchState.consider -----------------------------


def test_benign_run_is_full_state_novel_and_retained_without_key_or_violation() -> None:
    state = DecompressEffectSearchState((_BENIGN_CASE,))
    decision = state.consider(_benign_run(_BENIGN_CASE))
    assert decision.new_attempt_keys == ()
    assert decision.new_violation_fingerprints == ()
    assert decision.contract_violated is False
    assert decision.full_state_novel is True
    assert decision.reward == 0
    assert decision.retained is True


def test_external_boundary_attempt_frame_yields_a_new_key_and_rewards() -> None:
    state = DecompressEffectSearchState((_ESCAPE_CASE,))
    decision = state.consider(
        _run(
            _ESCAPE_CASE,
            before=_SENTINEL_ONLY,
            after=_SENTINEL_ONLY,
            frame=_frame((_external_hardlink_attempt(),)),
        )
    )
    assert decision.new_attempt_keys  # at least one boundary-attempt / external-resolve key
    assert decision.reward == 1
    assert decision.admission_eligible is True


def test_c1_hit_yields_a_new_violation_fingerprint_and_rewards() -> None:
    # extract/evil shares the sentinel inode (ino 9) -> the generic oracle fires C1 (+C2 nlink).
    after = (_obj(_SENTINEL, ino=9, nlink=2), _obj("extract/evil", ino=9, nlink=2))
    state = DecompressEffectSearchState((_ESCAPE_CASE,))
    decision = state.consider(
        _run(
            _ESCAPE_CASE,
            before=_SENTINEL_ONLY,
            after=after,
            frame=_frame((_external_hardlink_attempt(),)),
        )
    )
    assert decision.contract_violated is True
    assert decision.new_violation_fingerprints
    assert decision.reward == 1


def test_failed_termination_fails_closed() -> None:
    state = DecompressEffectSearchState((_ESCAPE_CASE,))
    decision = state.consider(
        _run(
            _ESCAPE_CASE,
            before=_SENTINEL_ONLY,
            after=_SENTINEL_ONLY,
            frame=_frame((_external_hardlink_attempt(),)),
            status=ExecutionStatus.FAILED,
        )
    )
    assert decision.eligible is False
    assert decision.new_attempt_keys == ()
    assert decision.new_violation_fingerprints == ()
    assert decision.admission_eligible is False
    assert decision.retained is False


def test_repeat_observation_is_not_novel() -> None:
    state = DecompressEffectSearchState((_ESCAPE_CASE,))
    run = _run(
        _ESCAPE_CASE,
        before=_SENTINEL_ONLY,
        after=_SENTINEL_ONLY,
        frame=_frame((_external_hardlink_attempt(),)),
    )
    assert state.consider(run).new_attempt_keys
    second = state.consider(run)
    assert second.new_attempt_keys == ()
    assert second.admission_eligible is False


def test_missing_frame_contributes_no_attempt_key_but_oracle_still_stands() -> None:
    after = (_obj(_SENTINEL, ino=9, nlink=2), _obj("extract/evil", ino=9, nlink=2))
    state = DecompressEffectSearchState((_ESCAPE_CASE,))
    decision = state.consider(
        _run(_ESCAPE_CASE, before=_SENTINEL_ONLY, after=after, frame=None, frame_error="no frame")
    )
    assert decision.frame_observed is False
    assert decision.new_attempt_keys == ()
    assert decision.contract_violated is True  # the oracle is independent of the frame


# --- loop mechanics, determinism, discovery --------------------------------------------------


def _seeds() -> tuple[ArchiveCase, ...]:
    return (
        ArchiveCase((ArchiveEntry("a.txt", EntryType.REGULAR, content=b"a"),)),
        ArchiveCase((ArchiveEntry("b.txt", EntryType.REGULAR, content=b"b"),)),
        _ESCAPE_CASE,
    )


def test_campaign_fills_budget_and_grows_a_corpus_from_seeds() -> None:
    seen: list[int] = []
    config = DecompressEffectCampaignConfig(random_seed=7, execution_budget=12)
    result = run_decompress_effect_campaign(
        _seeds(), _benign_run, config, on_step=lambda step: seen.append(step.index)
    )
    assert len(result.steps) == 12
    assert tuple(step.index for step in result.steps) == tuple(range(12))
    assert seen == list(range(12))  # on_step fired once per step, in order
    assert result.retained_case_ids  # the benign seeds (distinct states) seeded the corpus
    assert result.final_stats.observations == 12


def test_campaign_is_deterministic_for_a_fixed_seed_and_producer() -> None:
    config = DecompressEffectCampaignConfig(random_seed=11, execution_budget=10)
    first = run_decompress_effect_campaign(_seeds(), _benign_run, config)
    second = run_decompress_effect_campaign(_seeds(), _benign_run, config)

    def ids(result) -> tuple[str, ...]:
        return tuple(step.run.base_result.case.case_id for step in result.steps)

    assert ids(first) == ids(second)


def test_campaign_records_a_self_discovered_violation() -> None:
    # A producer that returns a C1 hit for the escaping case and benign runs otherwise, so a
    # seed self-discovers the violation (budget = seed count keeps it a pure seed campaign).
    def produce(case: ArchiveCase) -> DecompressFrameRun:
        if case == _ESCAPE_CASE:
            after = (_obj(_SENTINEL, ino=9, nlink=2), _obj("extract/evil", ino=9, nlink=2))
            return _run(
                case,
                before=_SENTINEL_ONLY,
                after=after,
                frame=_frame((_external_hardlink_attempt(),)),
            )
        return _benign_run(case)

    config = DecompressEffectCampaignConfig(random_seed=1, execution_budget=len(_seeds()))
    result = run_decompress_effect_campaign(_seeds(), produce, config)
    assert result.discovered_violation is True


def test_campaign_report_is_json_serializable_and_records_the_outcome() -> None:
    config = DecompressEffectCampaignConfig(random_seed=3, execution_budget=5)
    result = run_decompress_effect_campaign(_seeds(), _benign_run, config)
    report = decompress_effect_campaign_report(result, producer="unit-test", label="demo")
    # Round-trips through JSON (no non-serializable values leak into the evidence).
    assert json.loads(json.dumps(report))["producer"] == "unit-test"
    assert report["discovered_violation"] is False  # benign producer -> honest negative
    steps = report["steps"]
    stats = report["final_stats"]
    assert isinstance(steps, list) and len(steps) == 5
    assert isinstance(stats, dict) and stats["observations"] == 5


# --- frame parsing ---------------------------------------------------------------------------


def test_parse_frame_reads_the_last_stdout_line() -> None:
    good = json.dumps({"format": FRAME_FORMAT, "schema_version": 1, "attempts": []})
    frame, error = _parse_frame("noise\n" + good + "\n")
    assert error is None
    assert frame is not None and frame["format"] == FRAME_FORMAT


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "not json\n",
        json.dumps({"format": "other", "schema_version": 1, "attempts": []}) + "\n",
        json.dumps({"format": FRAME_FORMAT}) + "\n",  # no schema_version / attempts
    ],
)
def test_parse_frame_rejects_malformed_or_foreign_frames(stdout: str) -> None:
    frame, error = _parse_frame(stdout)
    assert frame is None
    assert error


# --- end-to-end: real pipeline + unchanged oracle, fake backend that aliases the sentinel -----


class _ExtractingBackend(ExecutionBackend):
    """No docker: answers the identity probe and, for the frame command, performs the decompress
    4.2.1 bug (a relative hardlink target resolved against the sandbox root) so capture_state sees
    an extract/ object aliasing the sentinel and the production oracle fires C1.
    """

    def __init__(self, identity: bytes) -> None:
        self._identity = identity

    def validate_image(self, image_id: str) -> None:
        assert image_id == _IMAGE

    def policy(self, image_id):  # pragma: no cover - unused on the prepare path
        raise AssertionError("not used")

    def capture_isolation(self, image_id):  # pragma: no cover - unused on the prepare path
        raise AssertionError("not used")

    @contextmanager
    def prepare(self, request):
        identity, command = self._identity, request.command
        if "identify" in command:

            class _Identity:
                def execute(self) -> ContainerOutcome:
                    return ContainerOutcome(0, identity, b"", 0.0, False)

            yield _Identity()
            return

        extract = Path(command[4])
        root = extract.parent

        class _Frame:
            def execute(self) -> ContainerOutcome:
                extract.mkdir(exist_ok=True)
                # The bug: os.link resolves the relative target against CWD (sandbox root).
                os.link(root / "outside" / "sentinel.txt", extract / "evil")
                frame = {
                    "format": FRAME_FORMAT,
                    "schema_version": 1,
                    "extractor": "decompress@4.2.1",
                    "extraction_root_absolute": str(extract),
                    "attempts": [_external_hardlink_attempt()],
                }
                return ContainerOutcome(0, (json.dumps(frame) + "\n").encode(), b"", 0.0, False)

        yield _Frame()


def _identity_bytes() -> bytes:
    return json.dumps(
        {
            "decompress_module": "decompress",
            "decompress_version": "4.2.1",
            "node_version": "22.23.4",
            "worker_sha256": _WORKER_SHA,
        }
    ).encode()


@pytest.mark.skipif(
    not Path("/var/lib/inodefence").is_dir(),
    reason="disposable sandbox requires the Linux runtime root (Dev Container)",
)
def test_run_decompress_frame_case_end_to_end_hits_c1() -> None:
    backend = _ExtractingBackend(_identity_bytes())
    target = DecompressFrameTarget.bind(backend, _IMAGE)
    assert isinstance(target, IsolatedTarget)
    run = run_decompress_frame_case(_ESCAPE_CASE, target)

    assert run.base_result.execution.status == ExecutionStatus.SUCCESS
    c0, c1, c2 = run.base_result.violations
    assert (c0.violated, c1.violated, c2.violated) == (False, True, True)
    assert run.frame is not None and run.frame["format"] == FRAME_FORMAT
    # The frame's external hardlink attempt normalizes to a real boundary-attempt feedback key.
    state = DecompressEffectSearchState((_ESCAPE_CASE,))
    decision = state.consider(run)
    assert decision.new_attempt_keys and decision.new_violation_fingerprints
