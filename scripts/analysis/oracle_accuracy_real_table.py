"""Read #514 fixture replays into the real-extractor table (exploratory; counts, no run).

Design: Drive ``Research/02-엔진(…)/20261118-HOST1-514-실제추출기-표-설계.md`` §2b (W5, v3.7;
W4 method review). The rules below are that section's, not tuned here.

Inputs (standard library only; no InodeFence import):

* ``--labels``: the label file W5 writes before any run (``514-labels-v1.json``): per cell
  ``fixture``, ``cell{target, version}``, ``l_design[3]``, ``expect`` (``[C0, C1, C2]`` or
  ``"uncertain"``), ``termination`` (``success`` / ``rejected`` / null = not set), ``grades``,
  ``primary``, ``basis``, ``rounds``. Its SHA-256 goes in the output header.
* ``--manifest``: ``manifest.json`` of ``oracle_accuracy_real_cases`` (``{fixture, tar_sha256,
  case_dir, target, version}``). A replay is tied to its fixture by ``original.tar_sha256``
  against this list, never by folder name (§2b-6).
* ``--settings-file``: W5's run-settings file (``514-run-settings-v1.json``, §2b-10). Each
  replay's ``original.run_settings`` must equal the file's value for its cell, else exit 2. Its
  SHA-256 goes in the output header.
* ``--labels-sha256`` and ``--settings-sha256`` (required): the two files' SHA-256 as written in
  the ledger before the run; a file that differs is exit 2. Every manifest row must record the
  same run-settings SHA-256 (the folders were written with the file the reader is given).
* ``--replays``: a folder searched for ``replay.json`` (``inodefence-case-replay-v1``). Each file
  is read, reduced to its cell summary and dropped (memory stays flat in the file count).

Per cell, the first matching class from the top (§2b-8):

1. 미완료·미판정 -- no replay, a replay that did not complete (whatever its judged rounds), or no
   judged round;
2. 불확실 -- ``expect`` is ``"uncertain"``;
3. 라운드 갈림 -- judged rounds differ in C0, C1, C2 or termination (never a majority vote);
4. every judged round rejected with ``n n n`` observed: L_expect ``n n n`` and expected termination
   rejected -> 거부 동작 일치; L_expect ``n n n`` and success or null -> 추출기가 막음; L_expect has
   a ``y`` -> 거부로 기대 효과 차단;
5. observed C0-C2 equal L_expect -> 일치;
6. otherwise -> 불일치.

Accuracy counts are 일치 and 불일치 only; every cell caught by 1-4 is outside the denominator.

Termination is a flag, not a score (§2b-9): when the expected termination is set and differs from
the observed one, the cell gets "종료 기대와 다름" and keeps its class. A cell scored on fewer
judged rounds k than the n requested gets the display flag "판정 k/n" (§2b-11). Rounds with
``run_error`` are counted in their own column; the cell is classified on its judged rounds.

Scored cells are 일치 and 불일치 only. Two grade tables (§2b-2): a descriptive table by the
label's ``primary`` grade (checked against the fixed priority A > D > O > I), and a claim table by
membership -- external (A or D present) vs ours (O and I only) -- with the count of cells whose
only grade is I. Every other class is left out of both denominators and listed in one line. No
percentages. Two header lines (v3.9 §3): the hand-label sentence and the scope of the
accuracy (recorded verdicts only; not completeness).

This table holds controlled reproduction only (fixed fixtures on fixed versions); there is no
self-discovery column. Advisory identifiers appear only in the ``basis`` column copied from the
label file, never in a verdict or observation field. The control table (oracle vs filesystem
truth) is not part of this output (§2b-7).

Exit codes: 0 table written (mismatches included: this is a tally, not a verdict), 2 input error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPLAY_SCHEMA = "inodefence-case-replay-v1"
MANIFEST_SCHEMA = "inodefence-514-fixture-cases-v1"
LABELS_SCHEMA = "inodefence-514-labels-v1"
SETTINGS_SCHEMA = "inodefence-514-run-settings-v1"
CONTRACTS = ("c0", "c1", "c2")
TERMINATIONS = ("success", "rejected", "failed", "timed_out")
GRADE_PRIORITY = ("A", "D", "O", "I")
EXTERNAL_GRADES = frozenset({"A", "D"})
#: Printed in this order (W5 design v3.9 §3; the second line at W4's request).
HEADER = (
    "판정 대상은 손 라벨 기대값이지 파일시스템 진실이 아니다.",
    "이 정확도는 기록 verdict 범위(C0 외부 namespace, C1/C2 보호 센티넬)다. "
    "비보호 루트 밖 객체 경유 효과는 additive·이 표 밖이라 '정확도'를 완전성으로 읽지 "
    "않는다(상세: 분석설계 범위 주의).",
)
LABEL = "exploratory (등록 밖)"

UNFINISHED = "미완료·미판정"
UNCERTAIN = "불확실"
SPLIT = "라운드 갈림"
REFUSAL_MATCH = "거부 동작 일치"
BLOCKED = "추출기가 막음"
BLOCKED_EXPECTED = "거부로 기대 효과 차단"
MATCH = "일치"
MISMATCH = "불일치"
SCORED = (MATCH, MISMATCH)
#: Out of every denominator, in the order of the line the output prints (§2b, v3.7).
EXCLUDED = (SPLIT, REFUSAL_MATCH, BLOCKED, BLOCKED_EXPECTED, UNCERTAIN, UNFINISHED)
TERMINATION_FLAG = "종료 기대와 다름"
#: Display only (§2b-11): judged rounds k below the requested n. Class, score and denominator stay.
PARTIAL_ROUNDS_FLAG = "판정 {k}/{n}"
DESCRIPTIVE_FOOTNOTE = (
    "[A] 열은 주 근거가 A인 칸이다. A를 다른 근거와 함께 가진 칸은 그 주 등급 열에 있다."
)
NNN = (False, False, False)


class InputError(Exception):
    """Missing, unreadable or inconsistent input (exit 2)."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputError(f"{path}: cannot read JSON ({error})") from error


def _triple(value: object, where: str) -> tuple[bool, bool, bool]:
    if not isinstance(value, list) or len(value) != 3 or any(type(v) is not bool for v in value):
        raise InputError(f"{where}: must be three booleans")
    return (value[0], value[1], value[2])


CellKey = tuple[str, str, str, str]  # (fixture, target, version, extraction_filter or "")


@dataclass(frozen=True)
class Label:
    key: CellKey
    l_design: tuple[bool, bool, bool]
    expect: tuple[bool, bool, bool] | None  # None = "uncertain"
    termination: str | None
    grades: tuple[str, ...]
    primary: str | None
    basis: str
    rounds: int


def load_labels(path: Path) -> tuple[dict[str, Any], dict[CellKey, Label]]:
    data = _read(path)
    if not isinstance(data, dict) or data.get("schema") != LABELS_SCHEMA:
        raise InputError(f"{path}: not an {LABELS_SCHEMA} label file")
    if not isinstance(data.get("cells"), list):
        raise InputError(f"{path}: expected a 'cells' list")
    header = {k: v for k, v in data.items() if k != "cells"}
    labels: dict[CellKey, Label] = {}
    for index, raw in enumerate(data["cells"]):
        where = f"{path.name} cells[{index}]"
        if not isinstance(raw, dict) or not isinstance(raw.get("cell"), dict):
            raise InputError(f"{where}: needs fixture and cell{{target, version}}")
        key = (
            str(raw.get("fixture")),
            str(raw["cell"].get("target")),
            str(raw["cell"].get("version")),
            str(raw["cell"].get("extraction_filter") or ""),
        )
        if key in labels:
            raise InputError(f"{where}: cell {key} labelled twice")
        expect_raw = raw.get("expect")
        expect = None if expect_raw == "uncertain" else _triple(expect_raw, f"{where} expect")
        termination = raw.get("termination")
        if termination not in (None, "success", "rejected"):
            raise InputError(f"{where}: termination must be success, rejected or null")
        grades = tuple(raw.get("grades") or ())
        if any(g not in GRADE_PRIORITY for g in grades):
            raise InputError(f"{where}: grades must be among {GRADE_PRIORITY}")
        primary = raw.get("primary")
        if expect is not None:
            if not grades:
                raise InputError(f"{where}: a scored cell needs grades")
            wanted = next(g for g in GRADE_PRIORITY if g in grades)
            if primary != wanted:
                raise InputError(
                    f"{where}: primary {primary!r} is not the first of A > D > O > I in {grades}"
                )
        rounds = raw.get("rounds")
        if rounds not in (3, 20):
            raise InputError(f"{where}: rounds must be 3 or 20")
        labels[key] = Label(
            key,
            _triple(raw.get("l_design"), f"{where} l_design"),
            expect,
            termination,
            grades,
            primary,
            str(raw.get("basis") or ""),
            rounds,
        )
    return header, labels


def check_sha256(path: Path, expected: str, what: str) -> str:
    """The file's SHA-256, which must equal ``expected`` (the value written in the ledger before
    the run; given as an argument, never stored in code), else :class:`InputError`."""
    actual = _sha256(path)
    if actual != expected.strip().lower():
        raise InputError(f"{what} {path.name} sha256 {actual} != expected {expected}")
    return actual


def load_run_settings(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """W5's run-settings file (§2b-10, fixed by its SHA-256 before any run):
    ``(target, version) -> run_settings``. Shared by the case generator and this reader."""
    data = _read(path)
    if not isinstance(data, dict) or data.get("schema") != SETTINGS_SCHEMA:
        raise InputError(f"{path}: not an {SETTINGS_SCHEMA} file")
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(data.get("cells") or []):
        if not isinstance(raw, dict) or not isinstance(raw.get("run_settings"), dict):
            raise InputError(f"{path.name} cells[{index}]: needs target, version, run_settings")
        key = (str(raw.get("target")), str(raw.get("version")))
        if key in cells:
            raise InputError(f"{path.name}: cell {key} listed twice")
        cells[key] = dict(raw["run_settings"])
    return cells


def settings_mismatch(
    settings: Mapping[tuple[str, str], Mapping[str, Any]],
    target: str,
    version: str,
    given: object,
) -> str | None:
    """Why ``given`` is not exactly the file's run_settings for the cell (None when it is)."""
    wanted = settings.get((target, version))
    if wanted is None:
        return f"{target} {version} is not in the run-settings file"
    if given != wanted:
        return f"run_settings {given!r} differ from the file's {dict(wanted)!r}"
    return None


def load_manifest(
    path: Path, settings_sha256: str | None = None
) -> dict[tuple[str, str, str, str], CellKey]:
    """``(tar_sha256, target, version, filter) -> (fixture, target, version, filter)``. With
    ``settings_sha256``, every row must record that run-settings file (the folders were written
    with the same file the reader is given), else :class:`InputError`."""
    data = _read(path)
    if not isinstance(data, dict) or data.get("schema") != MANIFEST_SCHEMA:
        raise InputError(f"{path}: not an {MANIFEST_SCHEMA} manifest")
    index: dict[tuple[str, str, str, str], CellKey] = {}
    for row in data.get("cases") or []:
        key = (
            str(row["fixture"]),
            str(row["target"]),
            str(row["version"]),
            str(row.get("extraction_filter") or ""),
        )
        if settings_sha256 is not None and row.get("run_settings_sha256") != settings_sha256:
            raise InputError(
                f"{path}: {key} was written with run-settings sha256 "
                f"{row.get('run_settings_sha256')!r}, not the given file's {settings_sha256}"
            )
        lookup = (str(row["tar_sha256"]), key[1], key[2], key[3])
        if lookup in index:
            raise InputError(f"{path}: two fixtures of one cell share tar {lookup[0][:12]}")
        index[lookup] = key
    return index


@dataclass
class CellSummary:
    """What one replay.json says about its cell (the file itself is not kept)."""

    rounds_requested: int
    complete: bool
    judged: list[tuple[tuple[bool, bool, bool], str | None]] = field(default_factory=list)
    run_errors: int = 0
    run_error_reasons: list[str] = field(default_factory=list)
    observation_incomplete: int = 0
    terminations: Counter[str] = field(default_factory=Counter)
    provenance: dict[str, object] = field(default_factory=dict)


def summarize_replay(path: Path, data: Mapping[str, Any]) -> CellSummary:
    replay = data.get("replay") or {}
    original = data.get("original") or {}
    rounds = data.get("rounds")
    if not isinstance(rounds, list):
        raise InputError(f"{path}: no rounds list")
    summary = CellSummary(
        rounds_requested=int(replay.get("rounds_requested") or 0),
        complete=replay.get("complete") is True,
        provenance={
            "tar_sha256": original.get("tar_sha256"),
            "image_id": original.get("image_id"),
            "engine_commit": replay.get("engine_commit"),
            "replay_json_sha256": _sha256(path),
        },
    )
    for entry in rounds:
        termination = entry.get("termination")
        if termination is not None and termination not in TERMINATIONS:
            raise InputError(f"{path}: unknown termination {termination!r}")
        summary.terminations[str(termination)] += 1
        if entry.get("observation_complete") is False:
            summary.observation_incomplete += 1
        if entry.get("outcome") == "judged":
            verdict = tuple(entry.get(k) for k in CONTRACTS)
            if any(type(v) is not bool for v in verdict):
                raise InputError(f"{path}: a judged round without three verdicts")
            summary.judged.append(((verdict[0], verdict[1], verdict[2]), termination))
        elif entry.get("outcome") == "run_error":
            summary.run_errors += 1
            if entry.get("reason"):
                summary.run_error_reasons.append(str(entry["reason"]))
        else:
            raise InputError(f"{path}: round outcome must be judged or run_error")
    return summary


def read_replays(
    folder: Path,
    manifest: Mapping[tuple[str, str, str, str], CellKey],
    labels: Mapping[CellKey, Label],
    settings: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[CellKey, CellSummary]:
    """One summary per cell; every replay.json is read and dropped in turn."""
    if not folder.is_dir():
        raise InputError(f"{folder}: not a folder")
    found: dict[CellKey, CellSummary] = {}
    for path in sorted(folder.rglob("replay.json")):
        data = _read(path)
        if not isinstance(data, dict) or data.get("schema") != REPLAY_SCHEMA:
            raise InputError(f"{path}: not an {REPLAY_SCHEMA} record")
        original = data.get("original") or {}
        replay_settings = original.get("run_settings") or {}
        sha, target, version, extraction_filter = (
            str(original.get("tar_sha256")),
            str(original.get("target")),
            str(original.get("version")),
            str(replay_settings.get("extraction_filter") or ""),
        )
        problem = settings_mismatch(settings, target, version, original.get("run_settings"))
        if problem is not None:
            raise InputError(f"{path}: {problem}")
        key = manifest.get((sha, target, version, extraction_filter))
        if key is None:
            raise InputError(
                f"{path}: tar {sha[:12]} for {target} {version} is not in the manifest"
            )
        if key not in labels:
            raise InputError(f"{path}: cell {key} has no label")
        if key in found:
            raise InputError(f"{path}: a second replay.json for cell {key}")
        summary = summarize_replay(path, data)
        if summary.rounds_requested != labels[key].rounds:
            raise InputError(
                f"{path}: {summary.rounds_requested} rounds requested, the label fixes "
                f"{labels[key].rounds}"
            )
        found[key] = summary
        del data
    return found


def classify(label: Label, summary: CellSummary | None) -> tuple[str, list[str]]:
    """(class, flags) by the §2b-8 order."""
    if summary is None or not summary.complete or not summary.judged:
        return UNFINISHED, []
    if label.expect is None:
        return UNCERTAIN, []
    if len(set(summary.judged)) > 1:
        return SPLIT, []
    observed, termination = summary.judged[0]
    flags = []
    if label.termination is not None and termination != label.termination:
        flags.append(TERMINATION_FLAG)
    if termination == "rejected" and observed == NNN:
        if label.expect == NNN:
            return (REFUSAL_MATCH if label.termination == "rejected" else BLOCKED), flags
        return BLOCKED_EXPECTED, flags
    return (MATCH if observed == label.expect else MISMATCH), flags


def _yn(triple: Sequence[bool] | None) -> str:
    return "uncertain" if triple is None else " ".join("y" if v else "n" for v in triple)


def build_table(
    labels: Mapping[CellKey, Label], summaries: Mapping[CellKey, CellSummary]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for key in sorted(labels):
        label, summary = labels[key], summaries.get(key)
        cls, flags = classify(label, summary)
        judged = summary.judged if summary else []
        if summary is not None and judged and len(judged) < summary.rounds_requested:
            flags = [*flags, PARTIAL_ROUNDS_FLAG.format(k=len(judged), n=summary.rounds_requested)]
        rows.append(
            {
                "fixture": key[0],
                "cell": " ".join(part for part in key[1:] if part),
                "l_design": _yn(label.l_design),
                "l_expect": _yn(label.expect),
                "expected_termination": label.termination,
                "grades": list(label.grades),
                "primary": label.primary,
                "basis": label.basis,
                "rounds_requested": summary.rounds_requested if summary else None,
                "judged_rounds": len(judged),
                "contract_y_rounds": {
                    name.upper(): f"{sum(1 for v, _ in judged if v[i])}/{len(judged)}"
                    for i, name in enumerate(CONTRACTS)
                },
                "terminations": dict(summary.terminations) if summary else {},
                "run_errors": summary.run_errors if summary else None,
                "run_error_reasons": sorted(set(summary.run_error_reasons)) if summary else [],
                "observation_incomplete_rounds": summary.observation_incomplete
                if summary
                else None,
                "class": cls,
                "flags": flags,
                "provenance": summary.provenance if summary else {"replay": "none"},
                "_observed": judged[0][0] if judged and cls in SCORED else None,
                "_expect": label.expect,
            }
        )
    return {"rows": rows}


def _mismatch_split(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    out = {c.upper(): {"oracle_y_expect_n": 0, "oracle_n_expect_y": 0} for c in CONTRACTS}
    for row in rows:
        if row["class"] != MISMATCH or row["_observed"] is None:
            continue
        for i, c in enumerate(CONTRACTS):
            seen, want = row["_observed"][i], row["_expect"][i]
            if seen and not want:
                out[c.upper()]["oracle_y_expect_n"] += 1
            elif want and not seen:
                out[c.upper()]["oracle_n_expect_y"] += 1
    return out


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_cell: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cell[row["cell"]].append(row)
    out: dict[str, Any] = {}
    for cell, cell_rows in sorted(by_cell.items()):
        scored = [r for r in cell_rows if r["class"] in SCORED]
        excluded = Counter(r["class"] for r in cell_rows if r["class"] in EXCLUDED)
        descriptive = {}
        for grade in GRADE_PRIORITY:
            group = [r for r in scored if r["primary"] == grade]
            descriptive[grade] = {
                MATCH: sum(1 for r in group if r["class"] == MATCH),
                MISMATCH: sum(1 for r in group if r["class"] == MISMATCH),
                "mismatch_by_contract": _mismatch_split(group),
            }
        membership = {}
        for name, test in (
            ("external (A or D)", lambda g: bool(EXTERNAL_GRADES & set(g))),
            ("ours (O and I only)", lambda g: not (EXTERNAL_GRADES & set(g))),
        ):
            group = [r for r in scored if test(r["grades"])]
            membership[name] = {
                MATCH: sum(1 for r in group if r["class"] == MATCH),
                MISMATCH: sum(1 for r in group if r["class"] == MISMATCH),
                "mismatch_by_contract": _mismatch_split(group),
            }
        out[cell] = {
            "scored_cells": len(scored),
            "descriptive_by_primary_grade": descriptive,
            "descriptive_footnote": DESCRIPTIVE_FOOTNOTE,
            "claim_by_membership": membership,
            "i_only_cells": sum(1 for r in scored if set(r["grades"]) == {"I"}),
            "excluded_line": "분모에서 제외: "
            + ", ".join(f"{name} {excluded.get(name, 0)}" for name in EXCLUDED),
            "termination_flags": sum(1 for r in cell_rows if TERMINATION_FLAG in r["flags"]),
        }
    return out


def run(
    labels_path: Path,
    manifest_path: Path,
    replays: Path,
    settings_path: Path,
    *,
    labels_sha256: str,
    settings_sha256: str,
) -> dict[str, Any]:
    check_sha256(labels_path, labels_sha256, "label file")
    settings_sha = check_sha256(settings_path, settings_sha256, "run-settings file")
    header, labels = load_labels(labels_path)
    settings = load_run_settings(settings_path)
    manifest = load_manifest(manifest_path, settings_sha)
    summaries = read_replays(replays, manifest, labels, settings)
    table = build_table(labels, summaries)
    rows = table["rows"]
    output = {
        "label": LABEL,
        "header": list(HEADER),
        "scope": "통제 재현만(정해진 fixture, 정해진 버전). 자력 발견 열 없음.",
        "inputs": {
            "labels_sha256": _sha256(labels_path),
            "labels_header": header,
            "run_settings_sha256": _sha256(settings_path),
            "manifest_sha256": _sha256(manifest_path),
            "replays_read": len(summaries),
        },
        "summary": summarize(rows),
        "rows": [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows],
    }
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--replays", type=Path, required=True)
    parser.add_argument("--settings-file", type=Path, required=True, help="514-run-settings-v1")
    parser.add_argument(
        "--labels-sha256", required=True, help="the label file's SHA-256 as written in the ledger"
    )
    parser.add_argument(
        "--settings-sha256",
        required=True,
        help="the run-settings file's SHA-256 as written in the ledger",
    )
    parser.add_argument("--json", type=Path, help="write the table here too")
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return 2 if error.code else 0
    try:
        output = run(
            args.labels,
            args.manifest,
            args.replays,
            args.settings_file,
            labels_sha256=args.labels_sha256,
            settings_sha256=args.settings_sha256,
        )
    except InputError as error:
        print(json.dumps({"verdict": "input_error", "error": str(error)}))
        print(f"input error: {error}", file=sys.stderr)
        return 2
    text = json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False)
    if args.json is not None:
        args.json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
