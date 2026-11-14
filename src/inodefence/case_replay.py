"""Replay one recorded violation case under the same conditions and measure how often it repeats.

The rule for a violation candidate is "run the same input again and see whether it reproduces".
``inodefence replay <case folder>`` implements it on the live violation case folders written
during exploration (``live/violations/run-NNNNNN/``: ``input.tar`` + ``case.json``):

1. :func:`load_replay_request` reads the case and refuses, with the reason, anything that would
   not be the *same input under the same conditions*: the TAR must hash to the recorded value, it
   must read back into a case whose re-encoding is byte-identical with the same ``case_id``
   (:mod:`inodefence.tar_reader`), the record must name an exact image id (``sha256:...``, never a
   tag), and it must carry the exploration's run settings (``run_settings``).
2. A target's replay hook (``TargetAdapter.replay``) re-runs the exact case N times on that image
   through the same isolation path as exploration and returns the rounds (:class:`ReplayRun`).
   The common driver checks the image is present locally first and never prepares or substitutes
   one.
3. :func:`build_replay_record` + :func:`publish_replay` write ``replay.json`` in a new folder
   *beside* the case folder (``run-NNNNNN.replay-<UTC>/``); the original folder is never touched.

Reproduction is reported two ways, separately: rounds that violated the same contracts again
(every contract the original violated is violated again), and rounds whose violation fingerprints
equal the original's. Rates are over *judged* rounds; an un-judged round (the oracle was not
evaluated) is counted but is not a "did not reproduce". A replay that stopped part-way keeps the
rounds it finished and is marked incomplete -- it is never reported as "not reproduced".
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from inodefence.model import ArchiveCase
from inodefence.tar_reader import MAX_TAR_BYTES, TarReadError, read_builder_tar

REPLAY_SCHEMA = "inodefence-case-replay-v1"
REPLAY_FILE = "replay.json"
CASE_SCHEMA = "inodefence-live-violation-v1"
CASE_FILE = "case.json"
CASE_TAR = "input.tar"
DEFAULT_ROUNDS = 3
MAX_ROUNDS = 20
CONTRACT_KEYS = ("c0", "c1", "c2")
OUTCOMES = ("judged", "run_error")
TERMINATIONS = ("success", "rejected", "failed", "timed_out")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
NOTE = (
    "Reproduction check of one recorded violation candidate: the same input bytes on the same "
    "image id, re-run under the exploration's isolation and run settings. Not a verdict on the "
    "extractor, and not a confirmed vulnerability."
)


class CaseReplayError(ValueError):
    """The case folder cannot be replayed as the same input under the same conditions."""


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    """Everything a target's replay hook needs, read and checked from one case folder."""

    case_dir: Path
    case: ArchiveCase
    tar_bytes: bytes
    tar_sha256: str
    case_id: str
    target: str
    version: str
    image_id: str
    engine_commit: str | None
    run_settings: dict[str, Any]
    #: The original step: run number, termination, verdicts, fingerprints, observation_complete.
    original: dict[str, Any]
    rounds: int


@dataclass(frozen=True, slots=True)
class ReplayRun:
    """What a target's replay hook returns.

    ``rounds`` holds one dict per finished round (see :func:`normalize_round`). ``complete`` is
    ``True`` only when every requested round finished; ``stop_reason`` says why it stopped early.
    ``engine_commit`` is the engine that ran the replay; ``runner`` records target-specific run
    identity (for example the controller image id).
    """

    rounds: tuple[dict[str, Any], ...]
    complete: bool
    stop_reason: str | None = None
    engine_commit: str | None = None
    runner: dict[str, Any] = field(default_factory=dict)


#: A target's replay hook: re-run ``request.case`` ``request.rounds`` times on
#: ``request.image_id`` through the same isolation path as exploration; ``work_dir`` is a scratch
#: folder (outside the repository) for the hook's own run evidence.
ReplayHook = Callable[[ReplayRequest, Path], ReplayRun]


def _read_case_json(case_dir: Path) -> dict[str, Any]:
    path = case_dir / CASE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CaseReplayError(
            f"{case_dir} is not a violation case folder (no {CASE_FILE})"
        ) from error
    except (OSError, ValueError) as error:
        raise CaseReplayError(f"{path} is unreadable: {error}") from error
    if not isinstance(data, dict) or data.get("schema") != CASE_SCHEMA:
        raise CaseReplayError(f"{path} is not an {CASE_SCHEMA} record")
    return data


def load_replay_request(case_dir: Path, *, rounds: int = DEFAULT_ROUNDS) -> ReplayRequest:
    """Read and check a violation case folder; refuse anything that would not be the same run."""
    if type(rounds) is not int or not 1 <= rounds <= MAX_ROUNDS:
        raise CaseReplayError(f"rounds must be an integer in 1..{MAX_ROUNDS}")
    case_dir = case_dir.resolve()
    record = _read_case_json(case_dir)
    for key in ("target", "version", "case_id"):
        if not isinstance(record.get(key), str) or not record[key]:
            raise CaseReplayError(f"{CASE_FILE} has no {key}")
    image_id = record.get("image_id")
    if not isinstance(image_id, str) or _IMAGE_ID.fullmatch(image_id) is None:
        raise CaseReplayError(
            f"{CASE_FILE} has no exact image id (got {image_id!r}); a tag could now name a "
            "different image, so this case cannot be replayed on the same image"
        )
    settings = record.get("run_settings")
    if not isinstance(settings, dict):
        raise CaseReplayError(
            f"{CASE_FILE} has no run_settings, so the exploration's run conditions (sentinels, "
            "observer policy, profile) are unknown and the replay could not match them"
        )
    expected_sha = record.get("tar_sha256")
    if not isinstance(expected_sha, str) or _SHA256.fullmatch(expected_sha) is None:
        raise CaseReplayError(f"{CASE_FILE} has no tar_sha256")
    tar_path = case_dir / str(record.get("tar") or CASE_TAR)
    if tar_path.parent != case_dir:
        raise CaseReplayError(f"{CASE_FILE} names an input outside the case folder")
    try:
        tar_bytes = tar_path.read_bytes()
    except OSError as error:
        raise CaseReplayError(f"input TAR unreadable: {error}") from error
    actual_sha = sha256(tar_bytes).hexdigest()
    if actual_sha != expected_sha:
        raise CaseReplayError(f"{tar_path.name} sha256 {actual_sha} != recorded {expected_sha}")
    try:
        case = read_builder_tar(tar_bytes, expected_case_id=record["case_id"])
    except TarReadError as error:
        raise CaseReplayError(f"not the same input: {error}") from error
    original = {
        "run": record.get("run"),
        "termination": record.get("status"),
        "observation_complete": record.get("observation_complete"),
        "fingerprints": list(record.get("fingerprints") or []),
        **{key: record.get(key) for key in CONTRACT_KEYS},
    }
    return ReplayRequest(
        case_dir=case_dir,
        case=case,
        tar_bytes=tar_bytes,
        tar_sha256=actual_sha,
        case_id=record["case_id"],
        target=record["target"],
        version=record["version"],
        image_id=image_id,
        engine_commit=record.get("engine_commit"),
        run_settings=dict(settings),
        original=original,
        rounds=rounds,
    )


def normalize_round(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    """Check one round from a hook and return it in the record's shape."""
    outcome = raw.get("outcome")
    if outcome not in OUTCOMES:
        raise CaseReplayError(f"round {index}: outcome must be one of {OUTCOMES}")
    termination = raw.get("termination")
    if termination is not None and termination not in TERMINATIONS:
        raise CaseReplayError(f"round {index}: termination must be one of {TERMINATIONS} or null")
    contracts = {key: raw.get(key) for key in CONTRACT_KEYS}
    if any(value is not None and type(value) is not bool for value in contracts.values()):
        raise CaseReplayError(f"round {index}: c0/c1/c2 must be true/false/null")
    if outcome == "run_error" and any(value is not None for value in contracts.values()):
        raise CaseReplayError(f"round {index}: a run_error round has no verdicts")
    complete = raw.get("observation_complete")
    if complete is not None and type(complete) is not bool:
        raise CaseReplayError(f"round {index}: observation_complete must be true/false/null")
    return {
        "round": index,
        "outcome": outcome,
        "termination": termination,
        **contracts,
        "observation_complete": complete,
        "fingerprints": sorted(str(fp) for fp in raw.get("fingerprints") or ()),
        "observation": [str(line) for line in raw.get("observation") or ()],
        "reason": None if raw.get("reason") is None else str(raw["reason"]),
    }


def _violated(entry: Mapping[str, Any]) -> set[str]:
    return {key.upper() for key in CONTRACT_KEYS if entry.get(key) is True}


def _judged(entry: Mapping[str, Any]) -> bool:
    return entry["outcome"] == "judged" and any(entry.get(key) is not None for key in CONTRACT_KEYS)


def summarize_rounds(original: Mapping[str, Any], rounds: Sequence[Mapping[str, Any]]) -> dict:
    """Reproduction counts and rates over judged rounds (``None`` rate when none was judged)."""
    target_contracts = _violated(original)
    target_fps = set(original.get("fingerprints") or ())
    judged = [entry for entry in rounds if _judged(entry)]
    same_contracts = sum(
        bool(target_contracts) and target_contracts <= _violated(entry) for entry in judged
    )
    same_fps = sum(
        bool(target_fps) and set(entry["fingerprints"]) == target_fps for entry in judged
    )
    violated_again = sum(bool(_violated(entry)) for entry in judged)

    def rate(count: int) -> float | None:
        return round(count / len(judged), 6) if judged else None

    return {
        "rounds_done": len(rounds),
        "judged": len(judged),
        "unjudged": len(rounds) - len(judged),
        "violated_again": violated_again,
        "same_contracts": same_contracts,
        "same_fingerprints": same_fps,
        "same_contracts_rate": rate(same_contracts),
        "fingerprint_match_rate": rate(same_fps),
        "original_contracts": sorted(target_contracts),
        "original_fingerprints": sorted(target_fps),
    }


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def build_replay_record(
    request: ReplayRequest,
    run: ReplayRun,
    *,
    started_at: datetime,
    finished_at: datetime,
) -> dict[str, Any]:
    rounds = [normalize_round(raw, index + 1) for index, raw in enumerate(run.rounds)]
    if len(rounds) > request.rounds:
        raise CaseReplayError(f"hook returned {len(rounds)} rounds, {request.rounds} requested")
    complete = run.complete and len(rounds) == request.rounds
    engine_differs = (
        None
        if request.engine_commit is None or run.engine_commit is None
        else request.engine_commit != run.engine_commit
    )
    return {
        "schema": REPLAY_SCHEMA,
        "note": NOTE,
        "original": {
            "case_dir": request.case_dir.name,
            "case_id": request.case_id,
            "tar_sha256": request.tar_sha256,
            "target": request.target,
            "version": request.version,
            "image_id": request.image_id,
            "engine_commit": request.engine_commit,
            "run_settings": request.run_settings,
            **request.original,
        },
        "replay": {
            "rounds_requested": request.rounds,
            "complete": complete,
            "stop_reason": None if complete else (run.stop_reason or "stopped before all rounds"),
            "started_at": _iso(started_at),
            "finished_at": _iso(finished_at),
            "image_id": request.image_id,
            "engine_commit": run.engine_commit,
            "engine_differs": engine_differs,
            "runner": dict(run.runner),
        },
        "rounds": rounds,
        "summary": summarize_rounds(request.original, rounds),
    }


def replay_dir_name(case_dir: Path, moment: datetime) -> str:
    return f"{case_dir.name}.replay-{moment.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def publish_replay(case_dir: Path, record: Mapping[str, Any], *, moment: datetime) -> Path:
    """Write ``replay.json`` in a new folder beside the case folder, in one rename.

    The case folder itself is never written to, and an existing replay folder is never reused.
    """
    final = case_dir.parent / replay_dir_name(case_dir, moment)
    if final.exists():
        raise CaseReplayError(f"{final} already exists; a replay never overwrites another")
    tmp = case_dir.parent / f".tmp-{final.name}-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        (tmp / REPLAY_FILE).write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.rename(tmp, final)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return final


def read_replays(case_dir: Path) -> list[dict[str, Any]]:
    """Replay records published beside a case folder, oldest first."""
    found = []
    for folder in sorted(case_dir.parent.glob(f"{case_dir.name}.replay-*")):
        try:
            data = json.loads((folder / REPLAY_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("schema") == REPLAY_SCHEMA:
            data["dir"] = folder.name
            found.append(data)
    return found


def replay_brief(record: Mapping[str, Any]) -> str:
    """One line for status listings, e.g. ``replayed 3/3: same contracts 3/3, fingerprints 2/3``."""
    replay = record.get("replay") or {}
    summary = record.get("summary") or {}
    done, wanted = summary.get("rounds_done", 0), replay.get("rounds_requested", 0)
    judged = summary.get("judged", 0)
    head = "replayed" if replay.get("complete") else "replay INCOMPLETE"
    text = (
        f"{head} {done}/{wanted}: same contracts {summary.get('same_contracts', 0)}/{judged}, "
        f"fingerprints {summary.get('same_fingerprints', 0)}/{judged}"
    )
    if summary.get("unjudged"):
        text += f", un-judged {summary['unjudged']}"
    if replay.get("engine_differs"):
        text += " (engine commit differs)"
    return text


# -- host -> controller input (one JSON line on the controller's stdin) ------------------------

REPLAY_INPUT_SCHEMA = "inodefence-case-replay-input-v1"
#: The controller reads at most 16 MiB for its one input line; base64 of MAX_TAR_BYTES fits.
MAX_INPUT_LINE_BYTES = 16 * 1024 * 1024
_INPUT_KEYS = {"schema", "case_id", "tar_sha256", "tar_b64", "rounds", "run_settings"}


def replay_input_line(request: ReplayRequest) -> str:
    """The single JSON line the host writes to the controller's stdin before brokering starts."""
    line = json.dumps(
        {
            "schema": REPLAY_INPUT_SCHEMA,
            "case_id": request.case_id,
            "tar_sha256": request.tar_sha256,
            "tar_b64": base64.b64encode(request.tar_bytes).decode("ascii"),
            "rounds": request.rounds,
            "run_settings": request.run_settings,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(line) + 1 > MAX_INPUT_LINE_BYTES:
        raise CaseReplayError("replay input is larger than the controller's input line limit")
    return line + "\n"


@dataclass(frozen=True, slots=True)
class ReplayInput:
    """The controller's checked view of the input line."""

    case: ArchiveCase
    tar_sha256: str
    rounds: int
    run_settings: dict[str, Any]


def parse_replay_input(line: str) -> ReplayInput:
    """Validate the input line inside the controller: shape, size, the TAR's SHA-256 recomputed
    from the decoded bytes, and the byte-identical case reconstruction with the same case_id."""
    if not isinstance(line, str) or not line.strip():
        raise CaseReplayError("empty replay input")
    if len(line.encode("utf-8", "surrogateescape")) > MAX_INPUT_LINE_BYTES:
        raise CaseReplayError("replay input line is over the size limit")
    try:
        data = json.loads(line)
    except ValueError as error:
        raise CaseReplayError(f"replay input is not JSON: {error}") from error
    if not isinstance(data, dict) or set(data) != _INPUT_KEYS:
        raise CaseReplayError(f"replay input keys must be exactly {sorted(_INPUT_KEYS)}")
    if data["schema"] != REPLAY_INPUT_SCHEMA:
        raise CaseReplayError(f"replay input schema must be {REPLAY_INPUT_SCHEMA}")
    rounds = data["rounds"]
    if type(rounds) is not int or not 1 <= rounds <= MAX_ROUNDS:
        raise CaseReplayError(f"rounds must be an integer in 1..{MAX_ROUNDS}")
    if not isinstance(data["run_settings"], dict):
        raise CaseReplayError("run_settings must be an object")
    for key in ("case_id", "tar_sha256"):
        if not isinstance(data[key], str) or _SHA256.fullmatch(data[key]) is None:
            raise CaseReplayError(f"{key} must be 64 lowercase hex")
    encoded = data["tar_b64"]
    if not isinstance(encoded, str) or len(encoded) > (MAX_TAR_BYTES * 4) // 3 + 4:
        raise CaseReplayError("tar_b64 is missing or over the size limit")
    try:
        tar_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise CaseReplayError(f"tar_b64 is not valid base64: {error}") from error
    actual = sha256(tar_bytes).hexdigest()
    if actual != data["tar_sha256"]:
        raise CaseReplayError(f"input TAR sha256 {actual} != the host's {data['tar_sha256']}")
    try:
        case = read_builder_tar(tar_bytes, expected_case_id=data["case_id"])
    except TarReadError as error:
        raise CaseReplayError(f"not the same input: {error}") from error
    return ReplayInput(case, actual, rounds, dict(data["run_settings"]))
