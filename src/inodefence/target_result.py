"""Common per-target result record: one JSON shape for every extractor run command.

``inodefence-target-result-v1`` is what a "run this target at this version" command writes:
which target, on which configuration axes, how many runs, the C0/C1/C2 verdict per case, where
the reproduction TAR inputs were saved (with their SHA-256), and which engine revision / image
produced it. Every target (node-tar, python-tarfile, ...) writes the same shape; target-specific
logic lives in the command/adapter that fills it, never here.

Configuration axes are separate fields on purpose. Python tarfile has an extraction-filter axis
(``data`` / ``fully_trusted``) that is independent of its interpreter (runtime) version, so the
two must never share one column. node-tar uses ``target_version`` and leaves the others ``None``.

Contract values are tri-state: ``True`` violated, ``False`` observed and not violated, ``None``
not observed (the mode does not observe that contract, or the run failed). ``None`` is never a
nonviolation. ``observed_contracts`` names what the mode actually observes; a contract outside it
must be ``None`` in every case.

Overall verdict (same rule as ``make regression``): ``ERROR`` if any case is a run error, else
``FAIL`` if any case violated an observed contract, else ``PASS``. ``PASS`` is not a safety proof.
Every record carries the label ``demo run``; it is not a qualification or experiment result.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "inodefence-target-result-v1"
LABEL = "demo run"
CONTRACTS = ("C0", "C1", "C2")
#: Case outcome that marks a failed run (no observation); any other outcome string is target text.
RUN_ERROR = "run_error"

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")


class TargetResultError(ValueError):
    """The record does not satisfy the inodefence-target-result-v1 contract."""


class ResultMode(StrEnum):
    #: Fixed hand-built fixtures run once each (version-pair controlled reproduction).
    FIXTURE_REGRESSION = "fixture-regression"
    #: A bounded feedback campaign; each step is one case.
    CAMPAIGN = "campaign"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class TargetAxes:
    """Independent configuration axes. ``None`` means the axis does not apply to this target."""

    target_version: str | None = None
    runtime_version: str | None = None
    extraction_filter: str | None = None


@dataclass(frozen=True, slots=True)
class CaseVerdict:
    case_id: str
    outcome: str
    c0: bool | None
    c1: bool | None
    c2: bool | None

    @property
    def is_run_error(self) -> bool:
        return self.outcome == RUN_ERROR

    @property
    def violated(self) -> bool:
        return True in (self.c0, self.c1, self.c2)

    def contract(self, name: str) -> bool | None:
        return {"C0": self.c0, "C1": self.c1, "C2": self.c2}[name]


@dataclass(frozen=True, slots=True)
class ReproInput:
    """A saved TAR input; ``tar_path`` is POSIX-relative to the result file's directory."""

    case_id: str
    tar_path: str
    tar_sha256: str


@dataclass(frozen=True, slots=True)
class Provenance:
    engine_sha: str | None
    engine_dirty: bool
    image_ref: str | None = None
    image_id: str | None = None


@dataclass(frozen=True, slots=True)
class TargetResult:
    target: str
    axes: TargetAxes
    mode: ResultMode
    observed_contracts: tuple[str, ...]
    cases: tuple[CaseVerdict, ...]
    repro_inputs: tuple[ReproInput, ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        _validate(self)

    @property
    def executed(self) -> int:
        return len(self.cases)

    @property
    def errored(self) -> int:
        return sum(case.is_run_error for case in self.cases)

    @property
    def verdict(self) -> Verdict:
        if self.errored:
            return Verdict.ERROR
        if any(case.violated for case in self.cases):
            return Verdict.FAIL
        return Verdict.PASS

    @property
    def violating_cases(self) -> tuple[str, ...]:
        return tuple(case.case_id for case in self.cases if case.violated)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "label": LABEL,
            "target": self.target,
            "axes": {
                "target_version": self.axes.target_version,
                "runtime_version": self.axes.runtime_version,
                "extraction_filter": self.axes.extraction_filter,
            },
            "mode": self.mode.value,
            "observed_contracts": list(self.observed_contracts),
            "runs": {"executed": self.executed, "errored": self.errored},
            "verdict": self.verdict.value,
            "violating_cases": list(self.violating_cases),
            "cases": [
                {
                    "case_id": c.case_id,
                    "outcome": c.outcome,
                    "c0": c.c0,
                    "c1": c.c1,
                    "c2": c.c2,
                }
                for c in self.cases
            ],
            "repro_inputs": [
                {"case_id": r.case_id, "tar_path": r.tar_path, "tar_sha256": r.tar_sha256}
                for r in self.repro_inputs
            ],
            "provenance": {
                "engine_sha": self.provenance.engine_sha,
                "engine_dirty": self.provenance.engine_dirty,
                "image_ref": self.provenance.image_ref,
                "image_id": self.provenance.image_id,
            },
        }

    def dumps(self) -> str:
        return json.dumps(self.to_json_dict(), indent=2, sort_keys=True) + "\n"


def repro_input(case_id: str, tar_path: str, tar_bytes: bytes) -> ReproInput:
    """Describe a TAR input saved at ``tar_path`` (relative), hashing its bytes."""
    return ReproInput(case_id, tar_path, sha256(tar_bytes).hexdigest())


def _validate(result: TargetResult) -> None:
    if not isinstance(result.target, str) or not result.target:
        raise TargetResultError("target must be a non-empty name")
    if not isinstance(result.provenance.engine_dirty, bool):
        raise TargetResultError("engine_dirty must be true/false")
    if not isinstance(result.mode, ResultMode):
        raise TargetResultError(f"mode must be a ResultMode, got {result.mode!r}")
    observed = result.observed_contracts
    if not observed or len(set(observed)) != len(observed) or set(observed) - set(CONTRACTS):
        raise TargetResultError(f"observed_contracts must be distinct items of {CONTRACTS}")
    case_ids = [case.case_id for case in result.cases]
    if len(set(case_ids)) != len(case_ids) or not all(case_ids):
        raise TargetResultError("case_id values must be non-empty and unique")
    for case in result.cases:
        for name in CONTRACTS:
            value = case.contract(name)
            if value is not None and not isinstance(value, bool):
                raise TargetResultError(f"{case.case_id}.{name} must be true/false/null")
            if name not in observed and value is not None:
                raise TargetResultError(
                    f"{case.case_id}.{name} is set but {name} is not an observed contract"
                )
        if case.is_run_error and case.violated:
            raise TargetResultError(f"{case.case_id} is a run error but reports a violation")
    known = set(case_ids)
    seen_paths: set[str] = set()
    for item in result.repro_inputs:
        if item.case_id not in known:
            raise TargetResultError(f"repro input for unknown case {item.case_id!r}")
        path = PurePosixPath(item.tar_path)
        if not item.tar_path or path.is_absolute() or ".." in path.parts or "\\" in item.tar_path:
            raise TargetResultError(f"tar_path must be relative and inside: {item.tar_path!r}")
        if item.tar_path in seen_paths:
            raise TargetResultError(f"duplicate tar_path {item.tar_path!r}")
        seen_paths.add(item.tar_path)
        if _SHA256_RE.fullmatch(item.tar_sha256) is None:
            raise TargetResultError(f"tar_sha256 must be 64 lowercase hex: {item.tar_sha256!r}")
    sha = result.provenance.engine_sha
    if sha is not None and _GIT_SHA_RE.fullmatch(sha) is None:
        raise TargetResultError(f"engine_sha must be a 40-hex git commit or null: {sha!r}")


_TOP_KEYS = {
    "schema",
    "label",
    "target",
    "axes",
    "mode",
    "observed_contracts",
    "runs",
    "verdict",
    "violating_cases",
    "cases",
    "repro_inputs",
    "provenance",
}


def _keys(obj: object, expected: set[str], where: str) -> Mapping[str, Any]:
    if not isinstance(obj, Mapping):
        raise TargetResultError(f"{where} must be an object")
    keys = set(obj)
    if keys != expected:
        raise TargetResultError(
            f"{where} keys mismatch: missing {sorted(expected - keys)}, "
            f"unexpected {sorted(keys - expected)}"
        )
    return obj


def from_json_dict(data: object) -> TargetResult:
    """Strict reader: exact keys, and the derived fields must match what the cases imply."""
    top = _keys(data, _TOP_KEYS, "result")
    if top["schema"] != SCHEMA:
        raise TargetResultError(f"schema must be {SCHEMA!r}, got {top['schema']!r}")
    if top["label"] != LABEL:
        raise TargetResultError(f"label must be {LABEL!r}, got {top['label']!r}")
    axes = _keys(top["axes"], {"target_version", "runtime_version", "extraction_filter"}, "axes")
    prov = _keys(
        top["provenance"], {"engine_sha", "engine_dirty", "image_ref", "image_id"}, "provenance"
    )
    try:
        mode = ResultMode(top["mode"])
    except ValueError as error:
        raise TargetResultError(f"unknown mode {top['mode']!r}") from error
    case_keys = {"case_id", "outcome", "c0", "c1", "c2"}
    repro_keys = {"case_id", "tar_path", "tar_sha256"}
    result = TargetResult(
        target=top["target"],
        axes=TargetAxes(axes["target_version"], axes["runtime_version"], axes["extraction_filter"]),
        mode=mode,
        observed_contracts=tuple(top["observed_contracts"]),
        cases=tuple(
            CaseVerdict(**_keys(c, case_keys, "case")) for c in _as_list(top["cases"], "cases")
        ),
        repro_inputs=tuple(
            ReproInput(**_keys(r, repro_keys, "repro_input"))
            for r in _as_list(top["repro_inputs"], "repro_inputs")
        ),
        provenance=Provenance(
            prov["engine_sha"], prov["engine_dirty"], prov["image_ref"], prov["image_id"]
        ),
    )
    expected = result.to_json_dict()
    for derived in ("runs", "verdict", "violating_cases"):
        if top[derived] != expected[derived]:
            raise TargetResultError(
                f"{derived} {top[derived]!r} does not match the cases ({expected[derived]!r})"
            )
    return result


def _as_list(value: object, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise TargetResultError(f"{where} must be a list")
    return value


def load_target_result(path: Path, *, verify_inputs: bool = True) -> TargetResult:
    """Read a result file; by default also re-hash every saved TAR input next to it."""
    result = from_json_dict(json.loads(path.read_text(encoding="utf-8")))
    if verify_inputs:
        for item in result.repro_inputs:
            tar = path.parent / item.tar_path
            if not tar.is_file():
                raise TargetResultError(f"repro input missing: {item.tar_path}")
            if sha256(tar.read_bytes()).hexdigest() != item.tar_sha256:
                raise TargetResultError(f"repro input hash mismatch: {item.tar_path}")
    return result
