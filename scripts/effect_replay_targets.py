"""Case replay inside the controller for python-tarfile, decompress and oras-go.

The node-tar half is :mod:`scripts.effect_replay`; this is the same controller mode
(``effect-replay-case``, entered through the same launcher, host broker and backend) for the three
targets whose exploration runs a case through its own pipeline function. Nothing here builds a
second way to run a case: each target binds the class and calls the function its exploration
controller mode calls, with that mode's defaults (one default sentinel, the binding's default
time limit), and judges the round with that exploration's own rule.

==================  ===============================================  ==========================
target              one round is                                     un-judged rule (mirrored)
==================  ===============================================  ==========================
``python-tarfile``  ``run_python_tarfile_contained_case`` on         ``python_tarfile_explore``
                    ``PythonTarfileContainedTarget`` (ONE filter,    ``.case_record``
                    the exact runtime ``X.Y.Z``)
``decompress``      ``run_decompress_frame_case`` on                 ``drivers.decompress``
                    ``DecompressFrameTarget``                        ``.explore.step_judged``
``oras-go``         ``run_oras_go_frame_case`` on                    ``container_controller``
                    ``OrasGoFrameTarget``                            ``.oras_go_recording_producer``
==================  ===============================================  ==========================

The host names the target in ``run_settings["target"]`` (node-tar's settings never carry that key,
so its path is untouched) together with what pins the same extractor: the filter and runtime
version, the package and version, or the oras-go version. Each is checked here again and compared
with what the bound image reports; a mismatch stops the replay before any round (the image is the
recorded id, but the settings must describe it too).

A round the target's rule does not trust as a verdict keeps its termination and is recorded as
``run_error`` with the reason (class ``unjudged`` in the replay record). An exception from the run
itself (backend, Docker) is not a round: it propagates, and the report is written incomplete with
the rounds that finished -- the same split node-tar's replay makes.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inodefence.case_replay import CaseReplayError, ReplayInput
from inodefence.feedback.fingerprint import violation_fingerprints
from inodefence.live_effect import effect_fingerprint_id
from inodefence.model import ArchiveCase

REPLAY_RUN_SCHEMA = "inodefence-case-replay-run-v1"
#: ``run_settings`` key that selects a target here; absent for node-tar.
TARGET_KEY = "target"
PYTHON_TARFILE = "python-tarfile"
DECOMPRESS = "decompress"
ORAS_GO = "oras-go"
#: What each target's ``run_settings`` must hold, exactly (besides ``target``).
SETTINGS_KEYS: dict[str, tuple[str, ...]] = {
    PYTHON_TARFILE: ("extraction_filter", "runtime_version"),
    DECOMPRESS: ("package", "version"),
    ORAS_GO: ("version",),
}
#: Filters python-tarfile exploration takes; ``fully_trusted`` exploration is held, so no
#: exploration can have produced a case under it and a replay under it is refused.
PYTHON_TARFILE_FILTERS = ("data",)
_EXACT = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_FINISHED = ("success", "rejected")


@dataclass(frozen=True, slots=True)
class BoundReplay:
    """One target bound to the exact image: how to run a round, and what the image reported."""

    #: ``case -> round fields`` (termination, c0/c1/c2, outcome, fingerprints, observation, ...)
    produce: Callable[[ArchiveCase], dict[str, Any]]
    identity: dict[str, Any]


def target_conditions(settings: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
    """``(target, its settings)`` from ``run_settings``; refuse anything unknown or incomplete."""
    name = settings.get(TARGET_KEY)
    if name not in SETTINGS_KEYS:
        raise CaseReplayError(f"replay target must be one of {sorted(SETTINGS_KEYS)}, got {name!r}")
    wanted = set(SETTINGS_KEYS[name])
    given = set(settings) - {TARGET_KEY}
    if given != wanted:
        raise CaseReplayError(
            f"{name} run_settings keys mismatch: missing {sorted(wanted - given)}, "
            f"unexpected {sorted(given - wanted)}"
        )
    values = {key: settings[key] for key in SETTINGS_KEYS[name]}
    if not all(isinstance(value, str) and value for value in values.values()):
        raise CaseReplayError(f"{name} run_settings values must be non-empty text")
    if name == PYTHON_TARFILE:
        if values["extraction_filter"] not in PYTHON_TARFILE_FILTERS:
            raise CaseReplayError(
                f"python-tarfile extraction_filter {values['extraction_filter']!r} is not "
                f"replayed: exploration runs only {', '.join(PYTHON_TARFILE_FILTERS)} "
                "(fully_trusted exploration is held until approved), so no explored case can "
                "carry it"
            )
        if _EXACT.fullmatch(values["runtime_version"]) is None:
            raise CaseReplayError("python-tarfile runtime_version must be exact X.Y.Z")
    return str(name), values


def _violation_fields(violations: Any) -> tuple[list[str], list[str]]:
    """``(fingerprint ids, observation lines)`` of the violated contracts, as live recording."""
    verdicts = tuple(violations)
    return (
        [effect_fingerprint_id(fp) for fp in violation_fingerprints(verdicts)],
        [f"{v.contract_id.value}: {v.explanation}" for v in verdicts if v.violated],
    )


def _round(
    base: Any,
    *,
    judged: bool,
    observation_complete: bool | None,
    reason: str | None,
) -> dict[str, Any]:
    """One round's fields from a ``RunResult``; an un-judged round keeps only its termination."""
    oracle = {v.contract_id.value: v.violated for v in base.violations}
    fingerprints, observation = _violation_fields(base.violations) if judged else ([], [])
    return {
        "outcome": "judged" if judged else "run_error",
        "termination": base.execution.status.value,
        "c0": oracle.get("C0") if judged else None,
        "c1": oracle.get("C1") if judged else None,
        "c2": oracle.get("C2") if judged else None,
        "observation_complete": observation_complete,
        "fingerprints": fingerprints,
        "observation": observation,
        "reason": reason,
    }


def python_tarfile_round(result: Any) -> dict[str, Any]:
    """Judge one ``EffectRunResult`` with python-tarfile exploration's own record function."""
    from inodefence.python_tarfile_explore import case_record

    record = case_record(0, result)
    judged = record["outcome"] == "judged"
    reason = None
    if not judged:
        reason = (
            "un-judged by the python-tarfile exploration rule (timed out, worker report missing "
            f"or contradicting the exit status, or an incomplete trace on success): termination "
            f"{record['termination']}, observation_complete {record['observation_complete']}"
        )
    return _round(
        result.base_result,
        judged=judged,
        observation_complete=bool(record["observation_complete"]),
        reason=reason,
    )


def decompress_round(run: Any) -> dict[str, Any]:
    """Judge one ``DecompressFrameRun`` as ``drivers.decompress.explore.step_judged`` does.

    Judged when the oracle saw a violation (whatever the exit status or frame), else only when the
    worker finished (success / rejected), the oracle gave a value and the worker emitted its
    frame. The report has no trace-integrity field, so ``observation_complete`` stays unknown.
    """
    base = run.base_result
    oracle = {v.contract_id.value: v.violated for v in base.violations}
    status = base.execution.status.value
    violated = any(value is True for value in oracle.values())
    judged = violated or (
        status in _FINISHED
        and any(value is not None for value in oracle.values())
        and not run.frame_error
    )
    reason = None
    if not judged:
        reason = (
            "un-judged by the decompress exploration rule: "
            + (f"termination {status}" if status not in _FINISHED else "no worker frame")
            + (f" ({run.frame_error})" if run.frame_error else "")
        )
    return _round(base, judged=judged, observation_complete=None, reason=reason)


def oras_go_round(run: Any) -> dict[str, Any]:
    """Judge one ``OrasGoFrameRun`` as the controller's ``oras_go_recording_producer`` does: only
    a run that ended ``success`` or ``rejected`` carries a verdict; anything else is un-judged."""
    base = run.base_result
    status = base.execution.status.value
    judged = status in _FINISHED
    reason = None if judged else f"un-judged by the oras-go exploration rule: termination {status}"
    return _round(base, judged=judged, observation_complete=None, reason=reason)


def bind_python_tarfile(backend: Any, image: str, values: Mapping[str, str]) -> BoundReplay:
    from inodefence.effect_pipeline_python_tarfile import run_python_tarfile_contained_case
    from inodefence.targets.python_tarfile_contained import PythonTarfileContainedTarget

    try:
        target = PythonTarfileContainedTarget.bind(
            backend, image, values["extraction_filter"], expected_python=values["runtime_version"]
        )
    except ValueError as error:
        raise CaseReplayError(f"python-tarfile image does not match the case: {error}") from error
    return BoundReplay(
        lambda case: python_tarfile_round(run_python_tarfile_contained_case(case, target)),
        {
            "extraction_filter": values["extraction_filter"],
            "python_version": target.python_version,
            "worker_sha256": target.worker_sha256,
            "tarfile_sha256": target.tarfile_sha256,
        },
    )


def bind_decompress(backend: Any, image: str, values: Mapping[str, str]) -> BoundReplay:
    from inodefence.effect_pipeline_decompress import run_decompress_frame_case
    from inodefence.targets.decompress_effect import DecompressFrameTarget

    target = DecompressFrameTarget.bind(backend, image)
    described: Any = target.invocation  # the DecompressFrameTarget identity it bound
    found = (described.decompress_module, described.decompress_version)
    if found != (values["package"], values["version"]):
        raise CaseReplayError(
            f"decompress image holds {found[0]}@{found[1]}, the case names "
            f"{values['package']}@{values['version']}"
        )
    return BoundReplay(
        lambda case: decompress_round(run_decompress_frame_case(case, target)),
        {
            "package": found[0],
            "package_version": found[1],
            "node_version": described.node_version,
            "worker_sha256": described.worker_sha256,
        },
    )


def bind_oras_go(backend: Any, image: str, values: Mapping[str, str]) -> BoundReplay:
    from inodefence.effect_pipeline_oras_go import run_oras_go_frame_case
    from inodefence.targets.oras_go_effect import OrasGoFrameTarget

    target = OrasGoFrameTarget.bind(backend, image)
    described: Any = target.invocation  # the OrasGoFrameTarget identity it bound
    found = described.oras_go_version
    if found.removeprefix("v") != values["version"].removeprefix("v"):
        raise CaseReplayError(f"oras-go image holds {found}, the case names {values['version']}")
    return BoundReplay(
        lambda case: oras_go_round(run_oras_go_frame_case(case, target)),
        {
            "oras_go_version": found,
            "go_version": described.go_version,
            "worker_sha256": described.worker_sha256,
        },
    )


BINDERS: dict[str, Callable[[Any, str, Mapping[str, str]], BoundReplay]] = {
    PYTHON_TARFILE: bind_python_tarfile,
    DECOMPRESS: bind_decompress,
    ORAS_GO: bind_oras_go,
}


def run_target_case_replay(
    backend: Any,
    image: str,
    evidence: Path,
    replay_input: ReplayInput,
    *,
    binders: Mapping[str, Callable[[Any, str, Mapping[str, str]], BoundReplay]] | None = None,
) -> int:
    """The ``effect-replay-case`` body for a target named in ``run_settings``.

    Same evidence contract as node-tar's: each finished round is appended to
    ``<evidence>.steps.jsonl`` and fsynced before the next starts; the report says
    ``complete: false`` and why when the rounds did not all finish.
    """
    rounds_path = evidence.with_suffix(".steps.jsonl")
    finished: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema": REPLAY_RUN_SCHEMA,
        "case_id": replay_input.case.case_id,
        "tar_sha256": replay_input.tar_sha256,
        "image_id": image,
        "target": replay_input.run_settings.get(TARGET_KEY),
        "rounds_requested": replay_input.rounds,
    }
    with rounds_path.open("x", encoding="utf-8") as stream:
        try:
            name, values = target_conditions(replay_input.run_settings)
            bound = (binders or BINDERS)[name](backend, image, values)
            report["target_identity"] = bound.identity
            for number in range(1, replay_input.rounds + 1):
                record = {"round": number, **bound.produce(replay_input.case)}
                stream.write(json.dumps(record, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                finished.append(record)
                print(
                    f"effect-replay-case[{name}] round {number}/{replay_input.rounds}: "
                    f"{record['outcome']} termination={record['termination']} "
                    f"c0={record['c0']} c1={record['c1']} c2={record['c2']}",
                    file=sys.stderr,
                )
            report.update(rounds=finished, complete=len(finished) == replay_input.rounds)
            returncode = 0 if report["complete"] else 1
        except Exception as error:  # noqa: BLE001 -- keep the finished rounds, say why it stopped
            report.update(
                rounds=finished, complete=False, stop_reason=f"{type(error).__name__}: {error}"
            )
            returncode = 1
    with evidence.open("x", encoding="utf-8") as out:
        out.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(f"effect-replay-case report: {evidence}", file=sys.stderr)
    return returncode
