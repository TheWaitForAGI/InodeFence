"""Read model of runs for every interface (console, TUI, web): what the existing files say, typed.

This module renders nothing and writes nothing. It reads the artifacts a run already leaves --
``live/progress.json`` and the violation case folders (node-tar exploration), ``result.json``
(every explore result and verify cell), ``replay.json`` and the launcher log -- through the
existing readers (:mod:`inodefence.live_exploration`, :mod:`inodefence.drivers.progress`,
:mod:`inodefence.target_result`, :mod:`inodefence.case_replay`) and returns them as small frozen
records. There is no index or database: runs are found by scanning folders.

Rules every field follows, so no interface has to decide them again:

- **Unknown is not zero.** A count the files do not hold is ``None`` (shown as ``?`` / ``-``). Only
  node-tar writes live numbers while it runs; for python-tarfile, decompress and oras-go every
  mid-run number is ``None`` and :class:`RunProgress` says where the little it has came from
  (``source``).
- **Contracts stay three-valued.** ``c0``/``c1``/``c2`` are ``True`` (violated), ``False`` (judged,
  not violated) or ``None`` (not judged or not observed -- verify never observes C0). ``None`` is
  never folded into "no violation".
- **Separate axes stay separate** (one enum each): how the extractor ended (:class:`Termination`),
  whether the oracle was evaluated (:class:`Judgment`), the campaign verdict (:class:`Verdict`), a
  violation the oracle flagged (:class:`FindingClass` -- always a *candidate*), and what a replay
  of it concluded (:class:`ReplayConclusion`). Nothing here says "confirmed vulnerability"; the
  strongest statement the data supports is "reproduced under the same conditions in n of the
  judged rounds" (:class:`ReplayRecord`).
- **Broken input is a state, not an exception.** ``result.json`` is not written atomically, so a
  file that does not parse is :attr:`ReadState.NOT_READY`; a missing, unreadable or foreign file is
  reported as such. Keys a newer version adds are kept in ``extras``; a result the strict reader
  still refuses comes back as :attr:`ReadState.UNVALIDATED` with its stored values and the reason,
  never as ``OK``.
- **Coupling, on purpose:** the campaign key sets are the strict reader's own private
  ``_CAMPAIGN_KEYS`` / ``_CAMPAIGN_OPTIONAL`` (``target_result.py`` is not changed for the UI);
  ``tests/test_app_runs.py`` fails if they disappear, so the two never drift apart silently.
- **Hashes are shown as recorded.** Re-hashing the saved inputs happens only on request
  (:func:`recheck_inputs`); until then :attr:`Integrity.rechecked` is ``False``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from inodefence import case_replay
from inodefence.drivers import progress as progress_reader
from inodefence.drivers.repo import is_repo
from inodefence.live_exploration import (
    PROGRESS_FILE,
    find_live_dirs,
    list_violation_cases,
    read_progress,
)
from inodefence.target_result import (
    _CAMPAIGN_KEYS,
    _CAMPAIGN_OPTIONAL,
    CampaignInfo,
    CaseVerdict,
    TargetResult,
    TargetResultError,
    from_json_dict,
    no_extraction_warning,
)
from inodefence.target_result import (
    SCHEMA as RESULT_SCHEMA,
)
from inodefence.user_config import (
    EXPLORE_OUT_NAME,
    VERIFY_OUT_NAME,
    UserConfig,
    UserConfigError,
    load_user_config,
)

RESULT_FILE = "result.json"
#: Folder under an explore ``--out`` that holds loop reports, ``<run_id>-result/`` and live folders.
EXPLORE_DIR = "target-explore"
RESULT_SUFFIX = "-result"
#: Folder under an output folder with the runtime records and the launcher logs.
RUNTIME_DIR = progress_reader.LOG_DIR
LAUNCHER_LOG_GLOB = "explore-launcher-*.log"
#: How often node-tar's live folder is copied to the host (``LivePuller`` default): a snapshot older
#: than a few of these while the run says ``running`` is stale, not slow.
LIVE_PULL_INTERVAL_SECONDS = 15.0
CONTRACT_KEYS = ("c0", "c1", "c2")


class RunKind(StrEnum):
    EXPLORE = "explore"
    VERIFY = "verify"
    REPLAY = "replay"


class Source(StrEnum):
    """Where the numbers of a view were read."""

    LIVE = "live"  # live/progress.json (node-tar only)
    RESULT = "result"  # result.json of a finished run
    LAUNCHER_LOG = "launcher-log"  # only the launcher's ``==> [step]`` line (an estimate)
    NONE = "none"


class ReadState(StrEnum):
    OK = "ok"
    #: The file exists but does not parse (``result.json`` is written in place, not atomically).
    NOT_READY = "not_ready"
    #: The strict result reader refused it (e.g. written by a newer version): the values are the
    #: stored ones, NOT validated. Show them only with that mark and ``RunSummary.error``.
    UNVALIDATED = "unvalidated"
    #: Present but not readable as this record (permissions, wrong schema, invalid content).
    UNREADABLE = "unreadable"
    MISSING = "missing"


class Termination(StrEnum):
    """How the extractor ended; independent of whether the oracle judged the run."""

    SUCCESS = "success"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    #: v2 policy only: the builder could not represent the input, so no extractor ran.
    BUILD_INVALID = "build_invalid"
    UNKNOWN = "unknown"


class Judgment(StrEnum):
    """Whether the oracle was evaluated on a case."""

    JUDGED = "judged"
    #: The oracle ran but gave no verdict on any contract (c0..c2 all null).
    UNJUDGED = "unjudged"
    #: Harness / execution-infrastructure error: the oracle was not evaluated at all.
    RUN_ERROR = "run_error"


class FindingClass(StrEnum):
    """A violation the oracle flagged. Always a candidate until a replay says more."""

    CANDIDATE = "candidate"
    #: Flagged while the extractor did not succeed or the observation was incomplete.
    CANDIDATE_NEEDS_REPRO_CHECK = "candidate_needs_repro_check"


class ReplayConclusion(StrEnum):
    REPRODUCED_VIOLATION = case_replay.REPRODUCED_VIOLATION
    PARTIALLY_REPRODUCED = "partially_reproduced"
    NOT_REPRODUCED = case_replay.NOT_REPRODUCED
    NO_VIOLATION = case_replay.NO_VIOLATION
    NEW_VIOLATION = case_replay.NEW_VIOLATION
    UNJUDGED = case_replay.UNJUDGED
    INFRASTRUCTURE_FAILURE = case_replay.INFRASTRUCTURE_FAILURE
    NO_ROUNDS = "no_rounds"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


class RunOutcome(StrEnum):
    """What a command's exit code says (``refused`` writes no folder, so only this shows it)."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    REFUSED = "refused"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


_RUN_EXIT = {0: RunOutcome.PASS, 1: RunOutcome.FAIL, 2: RunOutcome.ERROR, 3: RunOutcome.REFUSED}
_REPLAY_EXIT = {
    0: RunOutcome.COMPLETE,
    1: RunOutcome.INCOMPLETE,
    2: RunOutcome.REFUSED,  # the folder cannot be replayed as the same input / conditions
    3: RunOutcome.REFUSED,  # image not on this host, folder inside the repository, usage
    4: RunOutcome.UNSUPPORTED,
}


def outcome_from_exit_code(command: str, code: int) -> RunOutcome:
    """The documented meaning of ``inodefence <command>``'s exit code (``cli.py`` epilogs)."""
    table = _REPLAY_EXIT if command == "replay" else _RUN_EXIT
    if command not in ("explore", "verify", "replay"):
        return RunOutcome.UNKNOWN
    return table.get(code, RunOutcome.UNKNOWN)


# -- records ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunRef:
    """One run as found on disk. ``run_id_derived``: the id comes from a folder name."""

    kind: RunKind
    root: Path
    run_id: str | None
    run_id_derived: bool = True
    target: str | None = None
    version: str | None = None

    @property
    def key(self) -> str:
        """Stable identity of the run across scans (kind, folder, id)."""
        return f"{self.kind.value}:{self.root}:{self.run_id or ''}"


@dataclass(frozen=True, slots=True)
class RunProgress:
    source: Source
    state: str | None = None
    runs: int | None = None
    budget: int | None = None
    runs_per_second: float | None = None
    #: violating runs (each a candidate)
    violations: int | None = None
    unique_fingerprints: int | None = None
    contracts: Mapping[str, int | None] = field(
        default_factory=lambda: dict.fromkeys(CONTRACT_KEYS, None)
    )
    #: per-contract counts are a lower bound (not every violating run's case was readable)
    contracts_lower_bound: bool = False
    unjudged: int | None = None
    terminations: Mapping[str, int | None] = field(default_factory=dict)
    build_invalid: int | None = None
    #: epoch seconds of the snapshot's own ``updated_at``
    updated_at: float | None = None
    #: the launcher's last ``==> [step]`` label (a hint of what it is doing, never a decision)
    launcher_step: str | None = None
    launcher_step_estimated: bool = True


@dataclass(frozen=True, slots=True)
class CaseRow:
    case_id: str
    run: int | None
    termination: Termination
    outcome: str | None
    judgment: Judgment
    c0: bool | None
    c1: bool | None
    c2: bool | None
    observation_complete: bool | None
    finding: FindingClass | None
    fingerprints: tuple[str, ...] = ()
    tar_sha256: str | None = None
    input_path: Path | None = None
    recorded_at: str | None = None
    source: Source = Source.RESULT

    @property
    def violated(self) -> bool:
        return True in (self.c0, self.c1, self.c2)

    @property
    def contracts(self) -> dict[str, bool | None]:
        return {"c0": self.c0, "c1": self.c1, "c2": self.c2}


@dataclass(frozen=True, slots=True)
class Integrity:
    engine_sha: str | None
    engine_dirty: bool | None
    image_ref: str | None
    image_id: str | None
    lock_sha256: str | None = None
    worker_sha256: str | None = None
    #: ``(case_id, tar_sha256, path)`` of every saved input, as recorded
    inputs: tuple[tuple[str, str, Path], ...] = ()
    #: ``False`` until :func:`recheck_inputs` re-hashed the inputs ("not re-checked")
    rechecked: bool = False
    recheck_failures: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunSummary:
    ref: RunRef | None
    read_state: ReadState
    #: ``True``: the strict result reader accepted the file (``read_state`` OK). ``False`` with
    #: values: ``read_state`` is UNVALIDATED and the values are as stored (see ``error``).
    validated: bool = False
    result_path: Path | None = None
    verdict: Verdict | None = None
    label: str | None = None
    mode: str | None = None
    observed_contracts: tuple[str, ...] = ()
    executed: int | None = None
    errored: int | None = None
    unjudged_steps: int | None = None
    unjudged_ratio: float | None = None
    max_unjudged_ratio: float | None = None
    terminations: Mapping[str, int | None] = field(default_factory=dict)
    no_extraction_warning: str | None = None
    runs_to_first_violation: int | None = None
    violation_capture: Mapping[str, Any] | None = None
    integrity: Integrity | None = None
    preparation: Mapping[str, Any] | None = None
    benign_control: Mapping[str, Any] | None = None
    cases: tuple[CaseRow, ...] = ()
    #: campaign keys this reader does not know (a newer version's), as stored
    extras: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def has_values(self) -> bool:
        """Values were read: validated (``OK``) or as stored (``UNVALIDATED``, show the mark)."""
        return self.read_state in (ReadState.OK, ReadState.UNVALIDATED)


@dataclass(frozen=True, slots=True)
class CaseComparison:
    case_id: str
    in_a: bool
    in_b: bool
    tar_sha256_a: str | None
    tar_sha256_b: str | None
    #: ``True`` only when both sides recorded the same SHA-256; ``None`` when either is missing
    same_input: bool | None
    a: CaseRow | None
    b: CaseRow | None


@dataclass(frozen=True, slots=True)
class ReplayRound:
    round: int | None
    classification: str | None
    termination: str | None
    outcome: str | None
    c0: bool | None
    c1: bool | None
    c2: bool | None
    fingerprints: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    path: Path
    read_state: ReadState
    conclusion: ReplayConclusion | None = None
    classification: Mapping[str, int] = field(default_factory=dict)
    rounds_requested: int | None = None
    rounds_done: int | None = None
    #: the denominator of both rates (rounds the oracle judged), not ``rounds_done``
    judged: int | None = None
    unjudged: int | None = None
    same_contracts: int | None = None
    same_fingerprints: int | None = None
    same_contracts_rate: float | None = None
    fingerprint_match_rate: float | None = None
    complete: bool | None = None
    stop_reason: str | None = None
    engine_differs: bool | None = None
    original_case_id: str | None = None
    original_tar_sha256: str | None = None
    image_id: str | None = None
    rounds: tuple[ReplayRound, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    ref: RunRef
    #: epoch seconds when these files were read
    read_at: float
    progress: RunProgress | None = None
    summary: RunSummary | None = None
    findings: tuple[CaseRow, ...] = ()
    replays: tuple[ReplayRecord, ...] = ()
    read_errors: tuple[str, ...] = ()
    launcher_log: Path | None = None

    def progress_age(self, now: float | None = None) -> float | None:
        """Seconds since the progress snapshot's own ``updated_at`` (``None`` when unknown)."""
        if self.progress is None or self.progress.updated_at is None:
            return None
        return max((self.read_at if now is None else now) - self.progress.updated_at, 0.0)


@dataclass(frozen=True, slots=True)
class RunListing:
    path: Path
    ref: RunRef | None
    read_state: ReadState
    error: str | None = None


# -- small readers ---------------------------------------------------------------------------------


def _map(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int(value: object) -> int | None:
    return value if type(value) is int else None


def _bool(value: object) -> bool | None:
    return value if type(value) is bool else None


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _termination(value: object) -> Termination:
    if value == "build-invalid":
        return Termination.BUILD_INVALID
    try:
        return Termination(str(value))
    except ValueError:
        return Termination.UNKNOWN


def _load_json(path: Path) -> tuple[Any, ReadState, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, ReadState.MISSING, f"{path.name} not found"
    except OSError as error:
        return None, ReadState.UNREADABLE, f"{path}: {error}"
    try:
        return json.loads(text), ReadState.OK, None
    except ValueError as error:
        return None, ReadState.NOT_READY, f"{path.name} does not parse yet ({error})"


def _row_from_verdict(
    case: CaseVerdict, inputs: Mapping[str, tuple[str, Path]], run: int | None
) -> CaseRow:
    """A result case as a row; judgment and the repro-check flag come from :class:`CaseVerdict`."""
    if case.is_run_error:
        judgment = Judgment.RUN_ERROR
    elif case.is_unjudged:
        judgment = Judgment.UNJUDGED
    else:
        judgment = Judgment.JUDGED
    finding = None
    if case.violated:
        finding = (
            FindingClass.CANDIDATE_NEEDS_REPRO_CHECK
            if case.needs_repro_check
            else FindingClass.CANDIDATE
        )
    sha, path = inputs.get(case.case_id, (None, None))
    return CaseRow(
        case_id=case.case_id,
        run=run,
        termination=_termination(case.termination),
        outcome=case.outcome,
        judgment=judgment,
        c0=case.c0,
        c1=case.c1,
        c2=case.c2,
        observation_complete=case.observation_complete,
        finding=finding,
        tar_sha256=sha,
        input_path=path,
        source=Source.RESULT,
    )


def _run_number(case_id: str) -> int | None:
    """``step-N`` (an exploration case) -> ``N``; any other id has no run number."""
    head, _, tail = case_id.partition("-")
    return int(tail) if head == "step" and tail.isdigit() else None


def _row_from_live_case(record: Mapping[str, Any], live_dir: Path) -> CaseRow:
    contracts = {key: _bool(record.get(key)) for key in CONTRACT_KEYS}
    unjudged = record.get("unjudged") is True or all(v is None for v in contracts.values())
    violated = True in contracts.values()
    finding = None
    if violated:
        finding = (
            FindingClass.CANDIDATE_NEEDS_REPRO_CHECK
            if record.get("needs_repro_check") is True
            else FindingClass.CANDIDATE
        )
    folder = _str(record.get("dir"))
    tar = _str(record.get("tar"))
    return CaseRow(
        case_id=str(record.get("case_id") or record.get("dir") or "?"),
        run=_int(record.get("run")),
        termination=_termination(record.get("status")),
        outcome=None,
        judgment=Judgment.UNJUDGED if unjudged else Judgment.JUDGED,
        observation_complete=_bool(record.get("observation_complete")),
        finding=finding,
        fingerprints=tuple(str(fp) for fp in record.get("fingerprints") or ()),
        tar_sha256=_str(record.get("tar_sha256")),
        input_path=live_dir / folder / tar if folder and tar else None,
        recorded_at=_str(record.get("recorded_at")),
        source=Source.LIVE,
        **contracts,
    )


_KNOWN_CAMPAIGN = (
    (_CAMPAIGN_KEYS | _CAMPAIGN_OPTIONAL)
    | {f.name for f in fields(CampaignInfo)}
    | {"unjudged_ratio"}
)


def _split_extras(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """``data`` without the campaign keys this reader does not know, and those keys."""
    campaign = data.get("campaign")
    if not isinstance(campaign, Mapping):
        return dict(data), {}
    extras = {k: v for k, v in campaign.items() if k not in _KNOWN_CAMPAIGN}
    if not extras:
        return dict(data), {}
    known = {k: v for k, v in campaign.items() if k in _KNOWN_CAMPAIGN}
    return {**data, "campaign": known}, extras


def _integrity(
    provenance: Mapping[str, Any] | None,
    preparation: Mapping[str, Any] | None,
    inputs: Mapping[str, tuple[str, Path]],
) -> Integrity:
    prov = provenance or {}
    prep = preparation or {}
    return Integrity(
        engine_sha=_str(prov.get("engine_sha")),
        engine_dirty=_bool(prov.get("engine_dirty")),
        image_ref=_str(prov.get("image_ref")),
        image_id=_str(prov.get("image_id")),
        lock_sha256=_str(prep.get("lock_sha256")),
        worker_sha256=_str(prep.get("worker_sha256")),
        inputs=tuple((case_id, sha, path) for case_id, (sha, path) in inputs.items()),
    )


def _inputs(data: Mapping[str, Any], folder: Path) -> dict[str, tuple[str, Path]]:
    found: dict[str, tuple[str, Path]] = {}
    for item in data.get("repro_inputs") or ():
        if isinstance(item, Mapping):
            case_id, sha, rel = item.get("case_id"), item.get("tar_sha256"), item.get("tar_path")
            if isinstance(case_id, str) and isinstance(sha, str) and isinstance(rel, str):
                found[case_id] = (sha, folder / rel)
    return found


def _summary_from_result(
    result: TargetResult, data: Mapping[str, Any], path: Path, ref: RunRef | None, extras: dict
) -> RunSummary:
    inputs = _inputs(data, path.parent)
    campaign = result.campaign
    terminations = result.termination_counts
    return RunSummary(
        ref=ref,
        read_state=ReadState.OK,
        validated=True,
        result_path=path,
        verdict=Verdict(result.verdict.value),
        label=result.label,
        mode=result.mode.value,
        observed_contracts=tuple(result.observed_contracts),
        executed=result.executed,
        errored=result.errored,
        unjudged_steps=result.unjudged_steps,
        unjudged_ratio=result.unjudged_ratio,
        max_unjudged_ratio=campaign.max_unjudged_ratio if campaign else None,
        terminations=dict(terminations),
        no_extraction_warning=no_extraction_warning(terminations),
        runs_to_first_violation=campaign.runs_to_first_violation if campaign else None,
        violation_capture=campaign.violation_capture if campaign else None,
        integrity=_integrity(data.get("provenance"), data.get("preparation"), inputs),
        preparation=data.get("preparation"),
        benign_control=data.get("benign_control"),
        cases=tuple(
            _row_from_verdict(case, inputs, _run_number(case.case_id)) for case in result.cases
        ),
        extras=extras,
    )


def _summary_as_stored(
    data: Mapping[str, Any], path: Path, ref: RunRef | None, extras: dict, error: str
) -> RunSummary:
    """The stored values of a result the strict reader refused (``validated=False``)."""
    inputs = _inputs(data, path.parent)
    campaign = _map(data.get("campaign"))
    runs = _map(data.get("runs"))
    stored = campaign.get("terminations")
    terminations = {k: _int(v) for k, v in stored.items()} if isinstance(stored, Mapping) else {}
    verdict = data.get("verdict")
    rows = []
    for case in data.get("cases") or ():
        if not isinstance(case, Mapping) or not isinstance(case.get("case_id"), str):
            continue
        verdict_case = CaseVerdict(
            case_id=case["case_id"],
            outcome=str(case.get("outcome")),
            c0=_bool(case.get("c0")),
            c1=_bool(case.get("c1")),
            c2=_bool(case.get("c2")),
            termination=_str(case.get("termination")),
            observation_complete=_bool(case.get("observation_complete")),
        )
        rows.append(_row_from_verdict(verdict_case, inputs, _run_number(case["case_id"])))
    known_terminations = {k: v for k, v in terminations.items() if v is not None}
    return RunSummary(
        ref=ref,
        read_state=ReadState.UNVALIDATED,
        validated=False,
        result_path=path,
        verdict=Verdict(verdict) if verdict in Verdict.__members__ else None,
        label=_str(data.get("label")),
        mode=_str(data.get("mode")),
        observed_contracts=tuple(str(c) for c in data.get("observed_contracts") or ()),
        executed=_int(runs.get("executed")),
        errored=_int(runs.get("errored")),
        unjudged_steps=_int(campaign.get("unjudged_steps")),
        unjudged_ratio=campaign.get("unjudged_ratio")
        if isinstance(campaign.get("unjudged_ratio"), int | float)
        else None,
        max_unjudged_ratio=campaign.get("max_unjudged_ratio")
        if isinstance(campaign.get("max_unjudged_ratio"), int | float)
        else None,
        terminations=terminations,
        no_extraction_warning=no_extraction_warning(known_terminations)
        if known_terminations
        else None,
        runs_to_first_violation=_int(campaign.get("runs_to_first_violation")),
        violation_capture=campaign.get("violation_capture"),
        integrity=_integrity(data.get("provenance"), data.get("preparation"), inputs),
        preparation=data.get("preparation"),
        benign_control=data.get("benign_control"),
        cases=tuple(rows),
        extras=extras,
        error=error,
    )


def read_result(path: Path, ref: RunRef | None = None) -> RunSummary:
    """One ``result.json`` (an explore result or a verify cell) as a :class:`RunSummary`.

    The strict reader (:func:`inodefence.target_result.from_json_dict`) is tried first, after
    campaign keys it does not know are set aside in ``extras``; if it still refuses the file (a
    newer version's derived fields, say), the stored values are returned with ``validated=False``
    and the reason in ``error``. Inputs are not re-hashed here (:func:`recheck_inputs`).
    """
    data, state, error = _load_json(path)
    if state is not ReadState.OK:
        return RunSummary(ref=ref, read_state=state, result_path=path, error=error)
    if not isinstance(data, Mapping) or data.get("schema") != RESULT_SCHEMA:
        return RunSummary(
            ref=ref,
            read_state=ReadState.UNREADABLE,
            result_path=path,
            error=f"{path.name} is not an {RESULT_SCHEMA} record",
        )
    known, extras = _split_extras(data)
    try:
        result = from_json_dict(known)
    except (TargetResultError, TypeError, ValueError, KeyError) as refused:
        return _summary_as_stored(data, path, ref, extras, f"strict reader refused: {refused}")
    return _summary_from_result(result, data, path, ref, extras)


def recheck_inputs(summary: RunSummary) -> Integrity:
    """Re-hash every saved input against its recorded SHA-256 (only when asked)."""
    if summary.integrity is None:
        return Integrity(None, None, None, None, rechecked=True, recheck_failures=("no result",))
    failures = []
    for case_id, recorded, path in summary.integrity.inputs:
        try:
            actual = sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            failures.append(f"{case_id}: {error}")
            continue
        if actual != recorded:
            failures.append(f"{case_id}: SHA-256 {actual} != recorded {recorded}")
    return replace(summary.integrity, rechecked=True, recheck_failures=tuple(failures))


def compare_results(a: RunSummary, b: RunSummary) -> tuple[CaseComparison, ...]:
    """Two results case by case (scene "same input, two versions"). ``same_input`` is ``True``
    only when both sides recorded the same input SHA-256; a missing side or hash gives ``None``."""
    rows_a = {row.case_id: row for row in a.cases}
    rows_b = {row.case_id: row for row in b.cases}
    ordered = list(rows_a) + [case_id for case_id in rows_b if case_id not in rows_a]
    out = []
    for case_id in ordered:
        row_a, row_b = rows_a.get(case_id), rows_b.get(case_id)
        sha_a = row_a.tar_sha256 if row_a else None
        sha_b = row_b.tar_sha256 if row_b else None
        same = None if sha_a is None or sha_b is None else sha_a == sha_b
        out.append(
            CaseComparison(
                case_id, row_a is not None, row_b is not None, sha_a, sha_b, same, row_a, row_b
            )  # fmt: skip
        )
    return tuple(out)


def read_replay(path: Path) -> ReplayRecord:
    """One ``replay.json`` (or its folder). Rates are over judged rounds, as the record stores."""
    file = path / case_replay.REPLAY_FILE if path.is_dir() else path
    data, state, error = _load_json(file)
    if state is not ReadState.OK:
        return ReplayRecord(path=file, read_state=state, error=error)
    if not isinstance(data, Mapping) or data.get("schema") != case_replay.REPLAY_SCHEMA:
        return ReplayRecord(
            path=file,
            read_state=ReadState.UNREADABLE,
            error=f"{file.name} is not an {case_replay.REPLAY_SCHEMA} record",
        )
    summary = _map(data.get("summary"))
    replay = _map(data.get("replay"))
    original = _map(data.get("original"))
    try:
        conclusion = ReplayConclusion(str(summary.get("conclusion")))
    except ValueError:
        conclusion = None
    rounds = tuple(
        ReplayRound(
            round=_int(entry.get("round")),
            classification=_str(entry.get("classification")),
            termination=_str(entry.get("termination")),
            outcome=_str(entry.get("outcome")),
            c0=_bool(entry.get("c0")),
            c1=_bool(entry.get("c1")),
            c2=_bool(entry.get("c2")),
            fingerprints=tuple(str(fp) for fp in entry.get("fingerprints") or ()),
            reason=_str(entry.get("reason")),
        )
        for entry in data.get("rounds") or ()
        if isinstance(entry, Mapping)
    )
    classification = summary.get("classification")

    def rate(key: str) -> float | None:
        value = summary.get(key)
        return float(value) if isinstance(value, int | float) and type(value) is not bool else None

    return ReplayRecord(
        path=file,
        read_state=ReadState.OK,
        conclusion=conclusion,
        classification={str(k): v for k, v in classification.items() if type(v) is int}
        if isinstance(classification, Mapping)
        else {},
        rounds_requested=_int(replay.get("rounds_requested")),
        rounds_done=_int(summary.get("rounds_done")),
        judged=_int(summary.get("judged")),
        unjudged=_int(summary.get("unjudged")),
        same_contracts=_int(summary.get("same_contracts")),
        same_fingerprints=_int(summary.get("same_fingerprints")),
        same_contracts_rate=rate("same_contracts_rate"),
        fingerprint_match_rate=rate("fingerprint_match_rate"),
        complete=_bool(replay.get("complete")),
        stop_reason=_str(replay.get("stop_reason")),
        engine_differs=_bool(replay.get("engine_differs")),
        original_case_id=_str(original.get("case_id")),
        original_tar_sha256=_str(original.get("tar_sha256")),
        image_id=_str(replay.get("image_id")),
        rounds=rounds,
    )


# -- runs on disk ----------------------------------------------------------------------------------


def default_roots(config: UserConfig | None = None) -> tuple[Path, ...]:
    """The default ``--out`` folders of explore and verify (under the configured output base)."""
    if config is None:
        try:
            config = load_user_config()
        except (UserConfigError, OSError):
            return (Path.home() / EXPLORE_OUT_NAME, Path.home() / VERIFY_OUT_NAME)
    return (config.default_out(EXPLORE_OUT_NAME), config.default_out(VERIFY_OUT_NAME))


def _inside_repository(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return any(is_repo(candidate) for candidate in (resolved, *resolved.parents))


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _classify(folder: Path) -> RunRef | None:
    """The run a folder is, by the layout the drivers write (``None``: not a run folder)."""
    name = folder.name
    if (folder / case_replay.REPLAY_FILE).is_file():
        return RunRef(RunKind.REPLAY, folder, name)
    parent = folder.parent
    if parent.name == EXPLORE_DIR and name.endswith(RESULT_SUFFIX):
        if (folder / RESULT_FILE).exists():
            return RunRef(RunKind.EXPLORE, parent.parent, name[: -len(RESULT_SUFFIX)])
    if parent.name == EXPLORE_DIR and (folder / "live").is_dir():
        return RunRef(RunKind.EXPLORE, parent.parent, name)
    if (folder / RESULT_FILE).exists() and parent.name != EXPLORE_DIR:
        return RunRef(RunKind.VERIFY, folder, name)
    return None


def discover_runs(
    roots: Iterable[Path] | None = None,
    *,
    extra: Iterable[Path] = (),
    max_depth: int = 4,
    max_entries: int = 5000,
) -> list[RunListing]:
    """Runs under ``roots`` (default :func:`default_roots`) plus ``extra`` folders, newest first.

    Read-only: nothing is written or cached on disk. Symbolic links are not followed, folders
    inside this repository are not scanned (outputs never belong there), dot folders are skipped,
    and the walk stops at ``max_depth`` levels and ``max_entries`` folders. A folder that cannot be
    read is listed as :attr:`ReadState.UNREADABLE` instead of raising.
    """
    starts = [*(default_roots() if roots is None else roots), *extra]
    found: dict[str, tuple[float, RunListing]] = {}
    seen = 0
    for start in starts:
        start = Path(start).expanduser()
        if not start.exists():
            continue
        if start.is_symlink() or _inside_repository(start):
            reason = "symbolic link" if start.is_symlink() else "inside the repository"
            found[f"skip:{start}"] = (
                0.0,
                RunListing(start, None, ReadState.UNREADABLE, f"not scanned: {reason}"),
            )
            continue
        stack = [(start, 0)]
        while stack and seen < max_entries:
            folder, depth = stack.pop()
            seen += 1
            try:
                ref = _classify(folder)
            except OSError as error:  # Path.is_file() raises on EACCES (only ENOENT is quiet)
                found[f"error:{folder}"] = (
                    0.0,
                    RunListing(folder, None, ReadState.UNREADABLE, str(error)),
                )
                continue
            if ref is not None:
                listing = RunListing(folder, ref, ReadState.OK)
                found.setdefault(ref.key, (_mtime(folder), listing))
            if depth >= max_depth:
                continue
            try:
                entries = list(os.scandir(folder))
            except OSError as error:
                found[f"error:{folder}"] = (
                    0.0,
                    RunListing(folder, None, ReadState.UNREADABLE, str(error)),
                )
                continue
            for entry in entries:
                if entry.name.startswith(".") or entry.is_symlink():
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((Path(entry.path), depth + 1))
                except OSError:
                    continue
    ordered = sorted(found.values(), key=lambda item: item[0], reverse=True)
    return [listing for _, listing in ordered]


def _latest_launcher_log(root: Path) -> Path | None:
    """The newest explore launcher log under ``<root>/runtime`` (an estimate: logs are named by
    time and process, not by run id, so with several runs in one folder this is the newest)."""
    try:
        logs = sorted((root / RUNTIME_DIR).glob(LAUNCHER_LOG_GLOB), key=_mtime)
    except OSError:
        return None
    return logs[-1] if logs else None


def _progress(counts: progress_reader.Counts, raw: Mapping[str, Any] | None, step: str | None):
    violations = raw.get("violations") if raw else None
    build_invalid = raw.get("build_invalid") if raw else None
    return RunProgress(
        source=Source(counts.source),
        state=counts.state,
        runs=counts.runs,
        budget=counts.budget,
        runs_per_second=counts.runs_per_second,
        violations=counts.violations,
        unique_fingerprints=_int(violations.get("unique_fingerprints"))
        if isinstance(violations, Mapping)
        else None,
        contracts=dict(counts.contracts),
        contracts_lower_bound=counts.contracts_lower_bound,
        unjudged=counts.unjudged,
        terminations=dict(counts.terminations),
        # absent in progress.json means zero only on a live snapshot (it is written when > 0)
        build_invalid=(
            _int(build_invalid.get("steps"))
            if isinstance(build_invalid, Mapping)
            else (0 if raw is not None else None)
        ),
        updated_at=counts.updated_at,
        launcher_step=step,
    )


def _replays_beside(folders: Sequence[Path]) -> tuple[ReplayRecord, ...]:
    """Replay folders written beside case or result folders (``<name>.replay-<UTC>/``)."""
    records = []
    for folder in folders:
        try:
            candidates = sorted(folder.parent.glob(f"{folder.name}.replay-*"))
        except OSError:
            continue
        records += [read_replay(c) for c in candidates if c.is_dir() and not c.is_symlink()]
    return tuple(records)


def read_run(ref: RunRef, *, now: float | None = None) -> RunSnapshot:
    """Everything the files say about one run right now. Never raises for bad input."""
    import time

    read_at = time.time() if now is None else now
    errors: list[str] = []
    if ref.kind is RunKind.REPLAY:
        record = read_replay(ref.root)
        if record.error:
            errors.append(record.error)
        return RunSnapshot(ref, read_at, replays=(record,), read_errors=tuple(errors))
    if ref.kind is RunKind.VERIFY:
        summary = read_result(ref.root / RESULT_FILE, ref)
        if summary.error:
            errors.append(summary.error)
        ref = _with_axes(ref, summary)
        progress = None
        if summary.has_values:
            progress = _progress_from_summary(summary)
        return RunSnapshot(
            ref, read_at, progress=progress, summary=replace(summary, ref=ref),
            findings=tuple(row for row in summary.cases if row.finding is not None),
            read_errors=tuple(errors),
        )  # fmt: skip
    # explore
    base = ref.root / EXPLORE_DIR
    run_id = ref.run_id or ""
    result_dir = base / f"{run_id}{RESULT_SUFFIX}"
    live_dirs = find_live_dirs(base / run_id) if (base / run_id).is_dir() else []
    live = live_dirs[0] if live_dirs else None
    summary = None
    if (result_dir / RESULT_FILE).exists():
        summary = read_result(result_dir / RESULT_FILE, ref)
        if summary.error:
            errors.append(summary.error)
    raw = read_progress(live) if live is not None else None
    # The launcher log is named by time and process, not by run: attach its step only to a run that
    # has not ended (no result file, no ended live state), and only as an estimate.
    ended = summary is not None or (raw is not None and raw.get("state") != "running")
    log = None if ended else _latest_launcher_log(ref.root)
    step = progress_reader.last_launcher_step(log) if log is not None else None
    progress: RunProgress | None = None
    findings: list[CaseRow] = []
    if live is not None:
        if raw is None and (live / PROGRESS_FILE).exists():
            errors.append(f"{live / PROGRESS_FILE} could not be read")
        try:
            cases = list_violation_cases(live)
        except OSError as error:
            errors.append(f"violation cases: {error}")
            cases = None
        if raw is not None:
            progress = _progress(progress_reader.counts_from_progress(raw, cases), raw, step)
        findings = [_row_from_live_case(case, live) for case in cases or ()]
    if summary is not None and summary.has_values and progress is None:
        progress = replace(_progress_from_summary(summary), launcher_step=step)
    if progress is None:
        progress = RunProgress(
            source=Source.LAUNCHER_LOG if step else Source.NONE, launcher_step=step
        )
    if not findings and summary is not None:
        findings = [row for row in summary.cases if row.finding is not None]
    if summary is not None:
        ref = _with_axes(ref, summary)
        summary = replace(summary, ref=ref)
    elif raw is not None:
        ref = replace(ref, target=_str(raw.get("target")), version=_str(raw.get("version")))
    replay_sources = [result_dir] + [
        live / str(row.input_path.parent.relative_to(live))
        for row in findings
        if live is not None and row.input_path is not None and row.input_path.is_relative_to(live)
    ]
    return RunSnapshot(
        ref,
        read_at,
        progress=progress,
        summary=summary,
        findings=tuple(findings),
        replays=_replays_beside(replay_sources),
        read_errors=tuple(errors),
        launcher_log=log,
    )


def _with_axes(ref: RunRef, summary: RunSummary) -> RunRef:
    if not summary.has_values or summary.result_path is None:
        return ref
    data, state, _ = _load_json(summary.result_path)
    if state is not ReadState.OK or not isinstance(data, Mapping):
        return ref
    axes = _map(data.get("axes"))
    version = _str(axes.get("target_version")) or _str(axes.get("runtime_version"))
    return replace(ref, target=_str(data.get("target")), version=version)


def _progress_from_summary(summary: RunSummary) -> RunProgress:
    """A finished run's numbers through the existing result reader (``counts_from_result``)."""
    counts = (
        progress_reader.counts_from_result(summary.result_path)
        if summary.validated and summary.result_path is not None
        else None
    )
    if counts is None:
        return RunProgress(
            source=Source.RESULT,
            runs=summary.executed,
            unjudged=summary.unjudged_steps,
            terminations=dict(summary.terminations),
        )
    return _progress(counts, None, None)


def read_verify(out_dir: Path) -> tuple[RunSummary, ...]:
    """Every verify cell under ``out_dir`` (``<out>/<cell>/result.json``), by folder name."""
    try:
        cells = sorted(p for p in out_dir.iterdir() if p.is_dir() and not p.is_symlink())
    except OSError:
        return ()
    return tuple(
        read_result(cell / RESULT_FILE, RunRef(RunKind.VERIFY, cell, cell.name))
        for cell in cells
        if (cell / RESULT_FILE).exists()
    )


__all__ = [
    "LIVE_PULL_INTERVAL_SECONDS",
    "CaseComparison",
    "CaseRow",
    "FindingClass",
    "Integrity",
    "Judgment",
    "ReadState",
    "ReplayConclusion",
    "ReplayRecord",
    "ReplayRound",
    "RunKind",
    "RunListing",
    "RunOutcome",
    "RunProgress",
    "RunRef",
    "RunSnapshot",
    "RunSummary",
    "Source",
    "Termination",
    "Verdict",
    "compare_results",
    "default_roots",
    "discover_runs",
    "outcome_from_exit_code",
    "read_replay",
    "read_result",
    "read_run",
    "read_verify",
    "recheck_inputs",
]
