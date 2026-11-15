"""node-tar case replay inside the controller: run one exact case N times, as exploration ran it.

This is the in-controller half of ``inodefence replay`` for node-tar. The controller mode
``effect-replay-case`` reads the host's one input line (checked by
:func:`inodefence.case_replay.parse_replay_input`), binds the image, and calls
:func:`replay_case_report`. Everything that runs a case is the exploration path, reused unchanged:
``NodeTarEffectTarget.bind`` on the same backend and image id, and the exploration producer
``scripts.run_effect_demo._native_effect_producer`` (same disposable sandbox per run, same
sentinels, same observer-integrity policy, same stall recovery). Each round is one fresh
``produce(case)`` call. Verdict fields come from
:func:`inodefence.live_effect.effect_verdict_fields`, the same mapping live recording uses.

A round whose run the producer refuses to trust (``NativeDemoAborted``: an infrastructure failure,
or an untrustworthy trace under the default ``stop`` policy) is recorded as an un-judged
``run_error`` round with its reason, and the remaining rounds still run. Any other exception
propagates: the controller then reports the replay as incomplete, keeping the finished rounds.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from scripts.run_effect_demo import NativeDemoAborted, _native_effect_producer

from inodefence.case_replay import CaseReplayError, ReplayInput
from inodefence.execution.stall_recovery import StallRecovery
from inodefence.live_effect import effect_verdict_fields
from inodefence.model import ArchiveCase
from inodefence.runtime import SentinelSpec
from inodefence.sentinel_set import MAX_SENTINEL_COUNT, generate_sentinel_set
from inodefence.targets.node_tar_effect import NativeEffectProfile, NodeTarEffectTarget

REPLAY_RUN_SCHEMA = "inodefence-case-replay-run-v1"
#: The controller mode that runs :func:`run_case_replay` (one input case, read from stdin).
CASE_REPLAY_MODE = "effect-replay-case"
#: The ``run_settings`` keys node-tar exploration records (and replay requires).
NODE_TAR_SETTINGS = ("sentinel_count", "sentinel_seed", "observer_integrity_policy", "profile")
OBSERVER_POLICIES = ("stop", "invalid-continue")


def node_tar_conditions(
    settings: Mapping[str, Any],
) -> tuple[tuple[SentinelSpec, ...], bool, NativeEffectProfile]:
    """The exploration's run conditions from ``run_settings``; refuse anything unknown.

    Returns (sentinels, observer_integrity_continue, profile) exactly as exploration builds them:
    the default single sentinel unless both ``sentinel_count`` and ``sentinel_seed`` are set.
    """
    unknown = set(settings) - set(NODE_TAR_SETTINGS)
    missing = set(NODE_TAR_SETTINGS) - set(settings)
    if unknown or missing:
        raise CaseReplayError(
            f"node-tar run_settings keys mismatch: missing {sorted(missing)}, "
            f"unexpected {sorted(unknown)}"
        )
    count, seed = settings["sentinel_count"], settings["sentinel_seed"]
    if (count is None) != (seed is None):
        raise CaseReplayError("sentinel_count and sentinel_seed are set together or not at all")
    if count is None:
        sentinels: tuple[SentinelSpec, ...] = (SentinelSpec(),)
    else:
        if type(count) is not int or not 1 <= count <= MAX_SENTINEL_COUNT:
            raise CaseReplayError(f"sentinel_count must be in 1..{MAX_SENTINEL_COUNT}")
        if type(seed) is not int:
            raise CaseReplayError("sentinel_seed must be an integer")
        sentinels = generate_sentinel_set(seed, count).specs
    policy = settings["observer_integrity_policy"]
    if policy not in OBSERVER_POLICIES:
        raise CaseReplayError(f"observer_integrity_policy must be one of {OBSERVER_POLICIES}")
    try:
        profile = NativeEffectProfile(settings["profile"])
    except ValueError as error:
        raise CaseReplayError(f"unknown node-tar profile {settings['profile']!r}") from error
    return sentinels, policy == "invalid-continue", profile


def run_rounds(
    produce: Callable[[ArchiveCase], Any],
    case: ArchiveCase,
    rounds: int,
    *,
    round_sink: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Run ``case`` ``rounds`` times through ``produce``; one record per finished round."""
    records: list[dict[str, Any]] = []
    for number in range(1, rounds + 1):
        try:
            result = produce(case)
        except NativeDemoAborted as error:
            record: dict[str, Any] = {
                "round": number,
                "outcome": "run_error",
                "termination": None,
                "c0": None,
                "c1": None,
                "c2": None,
                "observation_complete": None,
                "fingerprints": [],
                "observation": [],
                "reason": error.reason,
            }
        else:
            fields = effect_verdict_fields(result)
            record = {
                "round": number,
                "outcome": "judged",
                **fields,
                "fingerprints": list(fields["fingerprints"]),
                "observation": list(fields["observation"]),
                "reason": None,
            }
        records.append(record)
        if round_sink is not None:
            round_sink(record)
    return records


def replay_case_report(
    target: Any,
    image_id: str,
    replay_input: ReplayInput,
    *,
    stall_recovery: StallRecovery | None = None,
    round_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Replay ``replay_input.case`` on a bound ``NodeTarEffectTarget`` and return the run report.

    ``target`` must be bound with the profile :func:`node_tar_conditions` returns for these
    settings (the controller mode binds it); the producer, sentinels and observer policy are the
    exploration's.
    """
    sentinels, observer_continue, _profile = node_tar_conditions(replay_input.run_settings)
    checks: list[dict[str, object]] = []
    timing: list[dict[str, object]] = []
    produce = _native_effect_producer(
        target,
        sentinels,
        stall_recovery,
        checks=checks,
        timing=timing,
        observer_integrity_continue=observer_continue,
    )
    rounds = run_rounds(produce, replay_input.case, replay_input.rounds, round_sink=round_sink)
    return {
        "schema": REPLAY_RUN_SCHEMA,
        "case_id": replay_input.case.case_id,
        "tar_sha256": replay_input.tar_sha256,
        "image_id": image_id,
        "node_tar_version": getattr(target, "tar_version", None),
        "node_version": getattr(target, "node_version", None),
        "rounds_requested": replay_input.rounds,
        "rounds": rounds,
        "complete": len(rounds) == replay_input.rounds,
        "native_checks": checks,
        "timing": timing,
    }


def replay_rounds_path(evidence: Path) -> Path:
    """Where the controller journals each finished round: ``<name>.steps.jsonl`` beside the
    report -- the same name and meaning ("finished so far, kept even on abort") as the other
    effect modes, so the smoke script's existing copy-out brings it to the host unchanged."""
    return evidence.with_suffix(".steps.jsonl")


def run_case_replay(
    backend: Any,
    image: str,
    evidence: Path,
    replay_input: ReplayInput,
    stall_recovery: StallRecovery | None,
) -> int:
    """The ``effect-replay-case`` controller mode body: bind, run the rounds, write evidence.

    Each finished round is appended to :func:`replay_rounds_path` and fsynced before the next
    starts, so a replay that dies part-way still leaves its finished rounds. The report written to
    ``evidence`` says ``complete: false`` and why when the rounds did not all finish.
    """
    _sentinels, _continue, profile = node_tar_conditions(replay_input.run_settings)
    rounds_path = replay_rounds_path(evidence)
    finished: list[dict[str, Any]] = []
    with rounds_path.open("x", encoding="utf-8") as stream:

        def persist(record: dict[str, Any]) -> None:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            finished.append(record)
            print(
                f"effect-replay-case round {record['round']}/{replay_input.rounds}: "
                f"{record['outcome']} termination={record['termination']} "
                f"c0={record['c0']} c1={record['c1']} c2={record['c2']}",
                file=sys.stderr,
            )

        try:
            target = NodeTarEffectTarget.bind(backend, image, profile=profile)
            report = replay_case_report(
                target, image, replay_input, stall_recovery=stall_recovery, round_sink=persist
            )
            returncode = 0 if report["complete"] else 1
        except Exception as error:  # noqa: BLE001 -- keep the finished rounds, say why it stopped
            report = {
                "schema": REPLAY_RUN_SCHEMA,
                "case_id": replay_input.case.case_id,
                "tar_sha256": replay_input.tar_sha256,
                "image_id": image,
                "rounds_requested": replay_input.rounds,
                "rounds": finished,
                "complete": False,
                "stop_reason": f"{type(error).__name__}: {error}",
            }
            returncode = 1
    with evidence.open("x", encoding="utf-8") as out:
        out.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(f"effect-replay-case report: {evidence}", file=sys.stderr)
    return returncode
