"""Group per-case triage records of one exploration into cause-signature bundles (#519).

:mod:`inodefence.violation_triage` minimizes ONE violating case and writes one record
(``inodefence-violation-triage-v2``). A large exploration yields many violating cases, most of
them the same cause; this module reads those records -- nothing is run -- and groups them by the
record's cause signature id, so a person sees one line per bundle instead of one per case.

Per bundle: the violated contracts, the signature (entry kinds and link-target shapes only; no
path, link text, file name, sentinel or protected-path name -- the signature never had them), the
case ids, how many records are a result, reference-only (nondeterministic target) or not a result,
and the range of the minimal entry counts. A bundle with any reference-only record is marked
nondeterministic, and both the original's and the minimum's re-measured rates are listed, so a
reader never takes a loose k-of-n minimum for a checked one. Records that are not a result carry no
signature (``violation_triage``: nothing to cite) and are counted apart, never bundled.

**Analysis output only: a bundle, its signature or its minimum is never a seed or corpus entry
of any exploration, benchmark or comparison arm.** The summary holds no TAR bytes.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from inodefence.violation_triage import RECORD_SCHEMA, SIGNATURE_SCHEMA, ResultStatus

SUMMARY_SCHEMA = "inodefence-triage-summary-v1"
#: Where an exploration result folder keeps its triage: ``triage/<case_id>/triage.json`` per case
#: and the bundle summary beside them.
TRIAGE_DIR = "triage"
RECORD_NAME = "triage.json"
SUMMARY_NAME = "triage-summary.json"
USE_RESTRICTION = (
    "analysis output only; never a seed or corpus entry of any exploration, benchmark or "
    "comparison arm"
)
NONDETERMINISTIC_NOTE = "includes a nondeterministic target; its minimum is for reference only"


class TriageSummaryError(ValueError):
    """A triage record is not one this summary can read."""


def _record_case_id(record: Mapping[str, Any]) -> str:
    baseline = record.get("baseline")
    case_id = baseline.get("case_id") if isinstance(baseline, Mapping) else None
    if not isinstance(case_id, str) or not case_id:
        raise TriageSummaryError("triage record has no baseline case id")
    return case_id


def _rate(block: object) -> float | None:
    rate = block.get("rate") if isinstance(block, Mapping) else None
    return rate if isinstance(rate, int | float) and not isinstance(rate, bool) else None


def summarize(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The bundle summary of ``records`` (``inodefence-violation-triage-v2`` dicts).

    Bundles are ordered by case count (most first), then signature id; case ids within a bundle
    are sorted. The same records in any order give the same summary.
    """
    bundles: dict[str, dict[str, Any]] = {}
    not_a_result: list[str] = []
    seen: set[str] = set()
    for record in records:
        if record.get("schema") != RECORD_SCHEMA:
            raise TriageSummaryError(f"not a {RECORD_SCHEMA} record: {record.get('schema')!r}")
        case_id = _record_case_id(record)
        if case_id in seen:
            raise TriageSummaryError(f"case {case_id} appears in more than one triage record")
        seen.add(case_id)
        status = record.get("result_status")
        minimization = record.get("minimization")
        signature = minimization.get("signature") if isinstance(minimization, Mapping) else None
        if status == ResultStatus.NOT_A_RESULT.value or signature is None:
            not_a_result.append(case_id)
            continue
        if status not in (ResultStatus.RESULT.value, ResultStatus.REFERENCE_ONLY.value):
            raise TriageSummaryError(f"case {case_id}: unknown result_status {status!r}")
        if not isinstance(signature, Mapping) or signature.get("schema") != SIGNATURE_SCHEMA:
            raise TriageSummaryError(f"case {case_id}: signature is not {SIGNATURE_SCHEMA}")
        signature_id = signature.get("id")
        if not isinstance(signature_id, str) or not signature_id:
            raise TriageSummaryError(f"case {case_id}: signature has no id")
        assert isinstance(minimization, Mapping)  # narrowed by the signature lookup
        bundle = bundles.setdefault(
            signature_id,
            {
                "signature_id": signature_id,
                "contracts": list(signature.get("contracts", [])),
                "signature": {k: signature[k] for k in ("contracts", "entries") if k in signature},
                "cases": [],
                "status": {ResultStatus.RESULT.value: 0, ResultStatus.REFERENCE_ONLY.value: 0},
                "minimal_entries": [],
                "rates": [],
            },
        )
        bundle["cases"].append(case_id)
        bundle["status"][status] += 1
        minimal = minimization.get("minimal")
        entries = minimal.get("entries") if isinstance(minimal, Mapping) else None
        if isinstance(entries, int):
            bundle["minimal_entries"].append(entries)
        bundle["rates"].append(
            {
                "case_id": case_id,
                "status": status,
                "original": _rate(record.get("baseline")),
                "minimum": _rate(record.get("final")),
            }
        )
    out: list[dict[str, Any]] = []
    for bundle in bundles.values():
        sizes = bundle.pop("minimal_entries")
        reference = bundle["status"][ResultStatus.REFERENCE_ONLY.value]
        out.append(
            {
                **bundle,
                "cases": sorted(bundle["cases"]),
                "case_count": len(bundle["cases"]),
                "minimal_entries": {"min": min(sizes), "max": max(sizes)} if sizes else None,
                "nondeterministic": reference > 0,
                "note": NONDETERMINISTIC_NOTE if reference else None,
                "rates": sorted(bundle["rates"], key=lambda item: item["case_id"]),
            }
        )
    out.sort(key=lambda bundle: (-bundle["case_count"], bundle["signature_id"]))
    return {
        "schema": SUMMARY_SCHEMA,
        "use_restriction": USE_RESTRICTION,
        "records": len(seen),
        "bundles": out,
        "not_a_result": {"count": len(not_a_result), "cases": sorted(not_a_result)},
    }


def read_records(result_folder: Path) -> list[dict[str, Any]]:
    """Every ``triage/<case_id>/triage.json`` under an exploration result folder, by case id."""
    folder = result_folder / TRIAGE_DIR
    if not folder.is_dir():
        return []
    records = []
    for path in sorted(folder.glob(f"*/{RECORD_NAME}")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as error:
            raise TriageSummaryError(f"{path}: not readable ({error})") from error
    return records


def write_summary(result_folder: Path) -> Path:
    """Summarize the result folder's triage records into ``triage/triage-summary.json``."""
    records = read_records(result_folder)
    if not records:
        raise TriageSummaryError(f"no {TRIAGE_DIR}/*/{RECORD_NAME} under {result_folder}")
    path = result_folder / TRIAGE_DIR / SUMMARY_NAME
    path.write_text(json.dumps(summarize(records), indent=2, sort_keys=True) + "\n", "utf-8")
    return path


def load_summary(result_folder: Path) -> dict[str, Any] | None:
    """The folder's bundle summary, or ``None`` when there is none (or it is not this schema)."""
    path = result_folder / TRIAGE_DIR / SUMMARY_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("schema") == SUMMARY_SCHEMA else None


def summary_lines(summary: Mapping[str, Any]) -> list[str]:
    """Markdown lines of the bundle summary, one per bundle (for ``summary.md`` and people)."""
    lines = [
        f"원인 서명 묶음 {len(summary['bundles'])}개, triage 기록 {summary['records']}건"
        f"(재현되지 않아 결과가 아닌 것 {summary['not_a_result']['count']}건). "
        "분석 출력이며 어떤 탐색·비교의 seed나 코퍼스로도 쓰지 않는다.",
        "",
        "| 묶음(서명 id) | 계약 | 케이스 | 결과 / 참고용 | 최소 entry 수 | 비고 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for bundle in summary["bundles"]:
        sizes = bundle["minimal_entries"]
        size = "—" if sizes is None else f"{sizes['min']}–{sizes['max']}"
        status = bundle["status"]
        note = "비결정 포함, 최소화는 참고용" if bundle["nondeterministic"] else ""
        lines.append(
            f"| `{bundle['signature_id']}` | {', '.join(bundle['contracts'])} | "
            f"{bundle['case_count']} | {status[ResultStatus.RESULT.value]} / "
            f"{status[ResultStatus.REFERENCE_ONLY.value]} | {size} | {note} |"
        )
    return lines
