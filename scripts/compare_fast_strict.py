"""Compare a FAST execution against STRICT for the #536 acceptance test (host-side, no Docker).

Design: Drive ``Research/02-엔진(…)/20261118-HOST1-536-FAST-동등성-시험-설계.md`` §1, §4(b), §7
(W3, method review W4 PASS). The rules and numbers below come from that document and are not
tuned here. This tool never runs a target; it reads evidence two runs already wrote.

``--mode trajectory`` (deterministic targets, node-tar): each folder holds one or more campaign
reports (``demo_report_schema`` 5: the product exploration's engine record
``inodefence-effect-explore-<run>.json`` or a run_exp0 cell report), with the per-step journal
``<report>.steps.jsonl`` beside it when the report streams. Reports pair by file name (or the
single report of each side). Per step, in order:

* ``case_sequence`` -- the same ``case_id`` at each step, the same number of steps
  (a shorter side is "incomplete" and diverges where it stops);
* ``step_input_hash`` -- ``(case_id, archive_format)``: ``case_id`` is the SHA-256 of the
  case's canonical form (``model.archive.ArchiveCase.case_id``) and the archive format fixes
  how it becomes TAR bytes, so the pair determines the input bytes;
* ``oracle_and_feedback`` -- C0/C1/C2 and the fed-back keys (new effect keys, new violation
  fingerprints);
* ``outcome_class`` -- outcome, validity, trace termination;
* ``corpus`` -- the corpus after each step (initial IDs plus every retained case so far);
* ``snapshots`` and ``isolation_and_reset`` -- from each report's ``parity_subject``
  (``inodefence.evaluation.execution_parity``, imported unchanged; G1's schema-5 comparison
  stays byte-identical).

Allowed to differ (never read): timing, container ids, log order, ``sandbox_root``, raw
``st_dev``/``st_ino``/``mtime_ns``/``ctime_ns`` (execution_parity keeps only the inode-sharing
partition).

Which dimensions decide depends on whether the FAST option shares state (design §8), given as
``--fast-kind``:

* ``isolated`` (no shared state, e.g. option 1: a fresh container and sandbox per case): the
  report-backed dimensions above are acceptance-sufficient. Isolation and reset are the same
  by construction, and the identity signal C1/C2 depend on is carried by the oracle and the
  feedback keys of the same input. ``parity_subject`` is also compared when both reports carry
  it.
* ``shared`` (one container or a reused sandbox): snapshots and isolation/reset are required,
  so both reports must carry ``parity_subject``; without it the verdict is *input
  insufficient* (exit 2), never "equivalent". The current exploration path does not write
  ``parity_subject``.

``identity_partition`` is descriptive only (never part of the verdict): per step, which paths
of the recorded effect events share one ``(st_dev, st_ino)`` after the event, raw numbers
dropped.

``--mode replay`` (non-deterministic targets): each folder holds ``replay.json`` records
(``inodefence-case-replay-v1``, from ``inodefence replay``) or ``*.verdicts.jsonl`` lines
``{"input_id", "run_index", "violated"}``. ``--inputs`` lists the fixed inputs
(``[{"input_id", "case"}]``, ``case`` = a case_id or TAR SHA-256). A round counts as a
violation when any of C0/C1/C2 is true; rounds with no verdict make the input's count short
(input error). Rules (§4(b), fixed before any run):

* (i) deterministic input (STRICT k = 0 or k = n): FAST must have exactly the same k;
* (ii) stochastic inputs (0 < k < n), pooled: TOST on the pooled violation-rate difference
  FAST − STRICT, margin ±0.10, α = 0.05 for each one-sided test, standard error from an
  input-level sign-flip permutation (fixed seed); with fewer than 5 stochastic inputs those
  inputs need n = 20.

Fisher's exact test (Holm-adjusted) and |Δk| per input are descriptive only.

A run that did not finish as a valid campaign is not comparable: verdict ``invalid``, exit 2
(design §8.1 (b), fail-closed). A failed FAST end check (the image identity changed) leaves no
new marker; it is read from what the run leaves (:func:`invalid_reasons`): node-tar raises
inside the loop (``live/progress.json`` state ``failed``, no engine report), python-tarfile
raises before its report, decompress and oras-go write an ``aborted`` report; in every target
the product driver then publishes no ``result.json`` (ERROR, exit 2).

Trajectory mode reads ``demo_report_schema`` 5 reports: node-tar and python-tarfile exploration
and run_exp0 cells. decompress and oras-go reports have another format (per-step feedback
counts, not keys) and are not read; those targets go through ``--mode replay`` (design §4).

Exit codes: 0 equivalent, 1 not equivalent (a divergence, a rule (i) mismatch or a TOST
failure), 2 input error or invalid run (missing/unreadable/unpaired evidence, a shared FAST
without ``parity_subject``, too few rounds, or an invalid run).

Usage::

    python3 scripts/compare_fast_strict.py --mode trajectory --fast-kind isolated \
        --strict A --fast B [--stop-first]
    python3 scripts/compare_fast_strict.py --mode replay --strict A --fast B --inputs set.json \
        [--n 10] [--tost-margin 0.10] [--alpha 0.05]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist, pstdev
from typing import Any

from inodefence.evaluation.execution_parity import compare_subjects, parity_subject_from_dict

EQUIVALENT, DIVERGENT, INPUT_ERROR = 0, 1, 2

#: Dimension order: also the tie-break when two dimensions first differ at the same step.
TRAJECTORY_DIMENSIONS = (
    "isolation_and_reset",  # campaign-wide records sort first (step_index None)
    "case_sequence",
    "step_input_hash",
    "oracle_and_feedback",
    "outcome_class",
    "corpus",
    "snapshots",
)
#: Dimensions a report without ``parity_subject`` cannot judge.
PARITY_ONLY_DIMENSIONS = ("snapshots", "isolation_and_reset")

REPORT_SCHEMA = 5
REPLAY_SCHEMA = "inodefence-case-replay-v1"
CONTRACTS = ("C0", "C1", "C2")

# §4(b) constants (design document; not tuned here).
DEFAULT_N = 10
STOCHASTIC_MIN_INPUTS = 5
STOCHASTIC_SMALL_N = 20
DEFAULT_MARGIN = 0.10
DEFAULT_ALPHA = 0.05
PERMUTATION_SEED = 536
PERMUTATION_EXACT_MAX = 16  # inputs; above this, PERMUTATION_DRAWS random sign flips
PERMUTATION_DRAWS = 20000

_STEP_RE = re.compile(r"^step (\d+)")


class InputError(Exception):
    """Evidence missing, unreadable, unpaired or insufficient (exit 2)."""


class InvalidCampaign(InputError):
    """A run that did not finish as a valid campaign; not comparable (exit 2, verdict invalid)."""


RESULT_SCHEMA = "inodefence-target-result-v1"
RUNTIME_DIR = "runtime"  # the product exploration always writes <out>/runtime/, also on failure


def invalid_reasons(folder: Path) -> list[str]:
    """Why ``folder`` is not a valid finished campaign (empty when it is), from what the runs
    actually leave behind (design §8.1 (b); FAST end check of research/b-engine-fast-w5):

    * a ``live/progress.json`` whose state is ``failed`` (node-tar: the loop raised);
    * a report carrying ``aborted`` (decompress / oras-go controller abort record);
    * a product exploration folder (it has ``runtime/`` or a ``result.json``) whose run wrote no
      ``result.json``, or one whose verdict is ``ERROR`` (every target: a controller failure or
      abort is ERROR, exit 2, and no result is published).
    """
    reasons: list[str] = []
    for path in sorted(folder.rglob("progress.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8")).get("state")
        except (OSError, ValueError, AttributeError):
            continue
        if state == "failed":
            reasons.append(f"{path.relative_to(folder)}: live state failed")
    results: list[Path] = []
    for path in sorted(folder.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if "aborted" in data:
            reasons.append(f"{path.relative_to(folder)}: report aborted ({data['aborted']})")
        if data.get("schema") == RESULT_SCHEMA:
            results.append(path)
            if data.get("verdict") == "ERROR":
                reasons.append(f"{path.relative_to(folder)}: verdict ERROR")
    product = (folder / RUNTIME_DIR).is_dir() or bool(results)
    if product and not results:
        reasons.append("no result.json (the exploration did not publish a result)")
    return reasons


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# -- reading campaign reports ------------------------------------------------------------------


@dataclass(frozen=True)
class Campaign:
    name: str
    report: dict[str, Any]
    steps: list[dict[str, Any]]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputError(f"{path}: cannot read JSON ({error})") from error


def _steps_for(report_path: Path, report: Mapping[str, Any]) -> list[dict[str, Any]]:
    journal = report_path.with_name(report_path.stem + ".steps.jsonl")
    if journal.exists():
        steps = []
        for number, line in enumerate(journal.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    steps.append(json.loads(line))
                except ValueError as error:
                    raise InputError(f"{journal}:{number}: not JSON ({error})") from error
        return steps
    steps = report.get("steps")
    if isinstance(steps, list):
        return list(steps)
    raise InputError(f"{report_path}: no steps (neither {journal.name} nor a steps array)")


def load_campaigns(folder: Path) -> dict[str, Campaign]:
    """Every schema-5 campaign report under ``folder``, keyed by file name."""
    if not folder.is_dir():
        raise InputError(f"{folder}: not a folder")
    found: dict[str, Campaign] = {}
    for path in sorted(folder.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # other JSON files (result.json, progress.json, ...) are not reports
        if not isinstance(data, dict) or data.get("demo_report_schema") != REPORT_SCHEMA:
            continue
        if path.name in found:
            raise InputError(f"{folder}: two reports named {path.name}")
        found[path.name] = Campaign(path.name, data, _steps_for(path, data))
    if not found:
        raise InputError(f"{folder}: no campaign report (demo_report_schema {REPORT_SCHEMA})")
    return found


def pair_campaigns(
    strict: Mapping[str, Campaign], fast: Mapping[str, Campaign]
) -> list[tuple[Campaign, Campaign]]:
    if len(strict) == 1 and len(fast) == 1:
        return [(next(iter(strict.values())), next(iter(fast.values())))]
    missing = sorted(set(strict) ^ set(fast))
    if missing:
        raise InputError(f"reports without a partner on the other side: {missing}")
    return [(strict[name], fast[name]) for name in sorted(strict)]


# -- trajectory comparison ---------------------------------------------------------------------


@dataclass(frozen=True)
class Divergence:
    dimension: str
    step_index: int | None
    case_id: str | None
    field: str
    strict: object
    fast: object

    def as_dict(self, campaign: str) -> dict[str, object]:
        return {
            "campaign": campaign,
            "dimension": self.dimension,
            "step_index": self.step_index,
            "case_id": self.case_id,
            "field": self.field,
            "strict": self.strict,
            "fast": self.fast,
        }

    def order(self) -> tuple[int, int]:
        step = -1 if self.step_index is None else self.step_index
        return step, TRAJECTORY_DIMENSIONS.index(self.dimension)


def _oracle(step: Mapping[str, Any]) -> dict[str, object]:
    oracle = step.get("oracle") or {}
    return {contract: oracle.get(contract) for contract in sorted(oracle)}


def _violated_contracts(step: Mapping[str, Any]) -> str:
    flagged = [contract for contract, value in sorted(_oracle(step).items()) if value]
    return "+".join(flagged) if flagged else "none"


def _feedback_keys(step: Mapping[str, Any]) -> list[str]:
    feedback = step.get("feedback") or {}
    keys = [_canonical(key) for key in feedback.get("new_effect_keys") or []]
    keys += [_canonical(item) for item in feedback.get("new_violation_fingerprints") or []]
    return keys


def _outcome_class(step: Mapping[str, Any]) -> dict[str, object]:
    feedback = step.get("feedback") or {}
    return {
        "outcome": step.get("outcome"),
        "validity": step.get("validity"),
        "trace_termination": feedback.get("trace_termination"),
    }


def _corpus_after_steps(campaign: Campaign) -> list[list[str]]:
    corpus = set(campaign.report.get("initial_case_ids") or [])
    out = []
    for step in campaign.steps:
        if (step.get("feedback") or {}).get("retained") and step.get("case_id"):
            corpus.add(step["case_id"])
        out.append(sorted(corpus))
    return out


def _step_divergences(strict: Campaign, fast: Campaign) -> list[Divergence]:
    found: list[Divergence] = []
    count = min(len(strict.steps), len(fast.steps))
    if len(strict.steps) != len(fast.steps):
        index = count
        longer = strict.steps if len(strict.steps) > count else fast.steps
        found.append(
            Divergence(
                "case_sequence",
                index,
                longer[index].get("case_id"),
                "step_count (one side incomplete)",
                len(strict.steps),
                len(fast.steps),
            )
        )
    corpus_s, corpus_f = _corpus_after_steps(strict), _corpus_after_steps(fast)
    for index in range(count):
        left, right = strict.steps[index], fast.steps[index]
        case_id = left.get("case_id")
        checks = (
            ("case_sequence", "case_id", left.get("case_id"), right.get("case_id")),
            (
                "step_input_hash",
                "case_id+archive_format",
                [left.get("case_id"), left.get("archive_format")],
                [right.get("case_id"), right.get("archive_format")],
            ),
            (
                "oracle_and_feedback",
                "oracle",
                _violated_contracts(left),
                _violated_contracts(right),
            ),
            ("oracle_and_feedback", "oracle_detail", _oracle(left), _oracle(right)),
            ("oracle_and_feedback", "feedback_keys", _feedback_keys(left), _feedback_keys(right)),
            ("outcome_class", "outcome_class", _outcome_class(left), _outcome_class(right)),
            ("corpus", "corpus_after_step", corpus_s[index], corpus_f[index]),
        )
        for dimension, field, value_s, value_f in checks:
            if value_s != value_f:
                found.append(Divergence(dimension, index, case_id, field, value_s, value_f))
    return found


def _parity_divergences(strict: Campaign, fast: Campaign) -> list[Divergence]:
    subject_s = parity_subject_from_dict(strict.report["parity_subject"])
    subject_f = parity_subject_from_dict(fast.report["parity_subject"])
    report = compare_subjects(subject_s, subject_f)
    found: list[Divergence] = []
    for dimension in report.dimensions:
        if dimension.name not in PARITY_ONLY_DIMENSIONS:
            continue  # case_sequence / oracle+feedback are judged from the step records
        for line in dimension.detail:
            match = _STEP_RE.match(line)
            index = int(match.group(1)) if match else None
            case_id = None
            if index is not None and index < len(subject_s.steps):
                case_id = subject_s.steps[index].case_id
            found.append(Divergence(dimension.name, index, case_id, line, "strict", "fast"))
    for verdict in report.retried_steps:
        if not verdict.matches_retry_free:
            found.append(
                Divergence(
                    "snapshots",
                    verdict.index,
                    verdict.case_id,
                    "retried step does not match the retry-free run: " + "; ".join(verdict.detail),
                    verdict.baseline_retries,
                    verdict.candidate_retries,
                )
            )
    return found


def _identity_partition(step: Mapping[str, Any]) -> list[list[str]]:
    """Paths of the step's recorded effect events grouped by post-event ``(st_dev, st_ino)``:
    only groups of two or more (the sharing structure), raw numbers dropped."""
    groups: dict[tuple[object, object], set[str]] = defaultdict(set)
    for event in (step.get("trace") or {}).get("effect_events") or []:
        for item in event.get("paths") or []:
            after = item.get("after") if isinstance(item, dict) else None
            if isinstance(after, dict) and after.get("st_ino") is not None:
                groups[(after.get("st_dev"), after["st_ino"])].add(str(item.get("path")))
    return sorted(sorted(paths) for paths in groups.values() if len(paths) > 1)


def _identity_partition_differences(strict: Campaign, fast: Campaign) -> list[int]:
    count = min(len(strict.steps), len(fast.steps))
    return [
        index
        for index in range(count)
        if _identity_partition(strict.steps[index]) != _identity_partition(fast.steps[index])
    ]


FAST_KINDS = ("isolated", "shared")


def compare_trajectory(
    strict_dir: Path, fast_dir: Path, *, stop_first: bool, fast_kind: str
) -> tuple[int, dict[str, object]]:
    if fast_kind not in FAST_KINDS:
        raise InputError(f"--fast-kind must be one of {FAST_KINDS}")
    invalid = [
        f"{side}: {reason}"
        for side, folder in (("strict", strict_dir), ("fast", fast_dir))
        if folder.is_dir()
        for reason in invalid_reasons(folder)
    ]
    if invalid:
        raise InvalidCampaign("run not a valid finished campaign: " + "; ".join(invalid))
    pairs = pair_campaigns(load_campaigns(strict_dir), load_campaigns(fast_dir))
    lacking = [
        f"{side}:{campaign.name}"
        for strict, fast in pairs
        for side, campaign in (("strict", strict), ("fast", fast))
        if not isinstance(campaign.report.get("parity_subject"), dict)
    ]
    if lacking and fast_kind == "shared":
        raise InputError(
            "no parity_subject in " + ", ".join(lacking) + ": a state-sharing FAST needs the "
            "snapshot and isolation/reset dimensions, which only parity_subject carries, so "
            "equivalence cannot be shown (design §8)"
        )
    judged = [d for d in TRAJECTORY_DIMENSIONS if not (lacking and d in PARITY_ONLY_DIMENSIONS)]
    campaigns: list[dict[str, object]] = []
    first: tuple[tuple[int, int], dict[str, object]] | None = None
    for strict, fast in pairs:
        found = _step_divergences(strict, fast)
        if not lacking:
            found += _parity_divergences(strict, fast)
        found.sort(key=Divergence.order)
        per_dimension = {name: sum(1 for d in found if d.dimension == name) for name in judged}
        campaigns.append(
            {
                "strict": strict.name,
                "fast": fast.name,
                "steps": [len(strict.steps), len(fast.steps)],
                "divergences_per_dimension": per_dimension,
                "first_divergence": found[0].as_dict(strict.name) if found else None,
                "descriptive": {
                    "identity_partition_differing_steps": _identity_partition_differences(
                        strict, fast
                    )
                },
            }
        )
        if found and (first is None or found[0].order() < first[0]):
            first = (found[0].order(), found[0].as_dict(strict.name))
    verdict = "divergent" if first else "equivalent"
    output: dict[str, object] = {
        "mode": "trajectory",
        "fast_kind": fast_kind,
        "verdict": verdict,
        "dimensions_judged": judged,
    }
    if lacking:
        output["scope"] = (
            "snapshots and isolation_and_reset not judged (no parity_subject); sufficient for "
            "an isolated FAST only (design §8)"
        )
    if first:
        output["first_divergence"] = first[1]
    if not stop_first:
        output["campaigns"] = campaigns
    return (DIVERGENT if first else EQUIVALENT), output


# -- replay comparison -------------------------------------------------------------------------


def _round_violated(entry: Mapping[str, Any]) -> bool | None:
    values = [entry.get(key) for key in ("c0", "c1", "c2")]
    if all(value is None for value in values):
        return None  # no verdict (unjudged / infrastructure failure)
    return any(value is True for value in values)


def load_replay_counts(folder: Path) -> dict[str, list[bool | None]]:
    """Per input key (case_id and TAR SHA-256 both map to the same list) the round verdicts."""
    if not folder.is_dir():
        raise InputError(f"{folder}: not a folder")
    rounds: dict[str, list[bool | None]] = {}
    for path in sorted(folder.rglob("replay.json")):
        data = _read_json(path)
        if not isinstance(data, dict) or data.get("schema") != REPLAY_SCHEMA:
            continue
        original = data.get("original") or {}
        verdicts = [_round_violated(entry) for entry in data.get("rounds") or []]
        keys = {original.get("case_id"), original.get("tar_sha256")}
        for key in sorted(str(key) for key in keys if key is not None):
            rounds.setdefault(key, []).extend(verdicts)
    for path in sorted(folder.rglob("*.verdicts.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                key, violated = record["input_id"], record["violated"]
            except (ValueError, KeyError, TypeError) as error:
                raise InputError(f"{path}:{number}: bad verdict line ({error})") from error
            if violated is not None and type(violated) is not bool:
                raise InputError(f"{path}:{number}: violated must be true/false/null")
            rounds.setdefault(str(key), []).append(violated)
    if not rounds:
        raise InputError(f"{folder}: no replay.json or *.verdicts.jsonl records")
    return rounds


def _load_inputs(path: Path) -> list[tuple[str, str]]:
    data = _read_json(path)
    if not isinstance(data, list) or not data:
        raise InputError(f"{path}: expected a nonempty list of {{input_id, case}}")
    out = []
    for item in data:
        if not isinstance(item, dict) or "input_id" not in item or "case" not in item:
            raise InputError(f"{path}: every entry needs input_id and case")
        out.append((str(item["input_id"]), str(item["case"])))
    return out


def _count(
    rounds: Mapping[str, list[bool | None]], case: str, side: str, input_id: str, n: int
) -> int:
    verdicts = rounds.get(case)
    if verdicts is None:
        raise InputError(f"{side}: no rounds for input {input_id} ({case})")
    judged = [v for v in verdicts if v is not None]
    if len(judged) < n:
        raise InputError(
            f"{side}: input {input_id} has {len(judged)} judged rounds, {n} needed "
            f"({len(verdicts) - len(judged)} without a verdict)"
        )
    return sum(judged[:n])


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]] (descriptive output only)."""
    row1, col1, total = a + b, a + c, a + b + c + d

    def prob(x: int) -> float:
        return math.comb(col1, x) * math.comb(total - col1, row1 - x) / math.comb(total, row1)

    observed = prob(a)
    low, high = max(0, row1 + col1 - total), min(row1, col1)
    return min(1.0, sum(p for x in range(low, high + 1) if (p := prob(x)) <= observed * (1 + 1e-9)))


def holm(pvalues: Sequence[float]) -> list[float]:
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted = [0.0] * len(pvalues)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def _sign_flip_se(differences: Sequence[float]) -> float:
    """SE of the mean per-input difference from input-level sign flips (fixed seed)."""
    m = len(differences)
    if m <= PERMUTATION_EXACT_MAX:
        signs: Iterable[tuple[int, ...]] = (
            tuple(1 if (mask >> i) & 1 else -1 for i in range(m)) for mask in range(2**m)
        )
    else:
        rng = random.Random(PERMUTATION_SEED)
        signs = (tuple(rng.choice((1, -1)) for _ in range(m)) for _ in range(PERMUTATION_DRAWS))
    means = [sum(s * d for s, d in zip(flip, differences, strict=True)) / m for flip in signs]
    return pstdev(means)


def tost(
    k_strict: Sequence[int], k_fast: Sequence[int], n: int, margin: float, alpha: float
) -> dict[str, object]:
    """Pooled FAST − STRICT violation-rate difference, TOST at ±margin (α per one-sided test)."""
    m = len(k_strict)
    diff = (sum(k_fast) - sum(k_strict)) / (m * n)  # equal n per input: pooled = mean of d_i
    differences = [(f - s) / n for s, f in zip(k_strict, k_fast, strict=True)]
    se = _sign_flip_se(differences)
    z = NormalDist().inv_cdf(1 - alpha)
    low, high = diff - z * se, diff + z * se
    return {
        "inputs": m,
        "n": n,
        "diff": diff,
        "se": se,
        "ci": [low, high],
        "ci_level": 1 - 2 * alpha,
        "margin": margin,
        "alpha_one_sided": alpha,
        "se_method": f"input-level sign-flip permutation (seed {PERMUTATION_SEED})",
        "pass": low > -margin and high < margin,
    }


def compare_replay(
    strict_dir: Path, fast_dir: Path, inputs_path: Path, *, n: int, margin: float, alpha: float
) -> tuple[int, dict[str, object]]:
    inputs = _load_inputs(inputs_path)
    strict_rounds, fast_rounds = load_replay_counts(strict_dir), load_replay_counts(fast_dir)
    per_input: list[dict[str, object]] = []
    stochastic: list[tuple[str, str]] = []
    for input_id, case in inputs:
        k_s = _count(strict_rounds, case, "strict", input_id, n)
        if 0 < k_s < n:
            stochastic.append((input_id, case))
            continue
        k_f = _count(fast_rounds, case, "fast", input_id, n)
        per_input.append(
            {
                "input_id": input_id,
                "case": case,
                "n": n,
                "k_strict": k_s,
                "k_fast": k_f,
                "rule": "(i)deterministic",
                "pass": k_f == k_s,
            }
        )
    tost_result: dict[str, object] | None = None
    if stochastic:
        n_stochastic = n if len(stochastic) >= STOCHASTIC_MIN_INPUTS else STOCHASTIC_SMALL_N
        ks = [_count(strict_rounds, c, "strict", i, n_stochastic) for i, c in stochastic]
        kf = [_count(fast_rounds, c, "fast", i, n_stochastic) for i, c in stochastic]
        tost_result = tost(ks, kf, n_stochastic, margin, alpha)
        for (input_id, case), k_s, k_f in zip(stochastic, ks, kf, strict=True):
            per_input.append(
                {
                    "input_id": input_id,
                    "case": case,
                    "n": n_stochastic,
                    "k_strict": k_s,
                    "k_fast": k_f,
                    "rule": "(ii)stochastic-pooled",
                    "pass": None,  # judged jointly by the TOST
                }
            )
    pvalues = [
        fisher_exact(
            int(row["k_strict"]),  # type: ignore[call-overload]
            int(row["n"]) - int(row["k_strict"]),  # type: ignore[call-overload]
            int(row["k_fast"]),  # type: ignore[call-overload]
            int(row["n"]) - int(row["k_fast"]),  # type: ignore[call-overload]
        )
        for row in per_input
    ]
    descriptive = [
        {
            "input_id": row["input_id"],
            "abs_delta_k": abs(int(row["k_fast"]) - int(row["k_strict"])),  # type: ignore[call-overload]
            "fisher_p": p,
            "fisher_p_holm": q,
        }
        for row, p, q in zip(per_input, pvalues, holm(pvalues), strict=True)
    ]
    deterministic_ok = all(row["pass"] for row in per_input if row["rule"] == "(i)deterministic")
    tost_ok = tost_result is None or bool(tost_result["pass"])
    equivalent = deterministic_ok and tost_ok
    output: dict[str, object] = {
        "mode": "replay",
        "verdict": "equivalent" if equivalent else "non_equivalent",
        "per_input": per_input,
        "tost": tost_result,
        "descriptive": descriptive,
    }
    return (EQUIVALENT if equivalent else DIVERGENT), output


# -- CLI ---------------------------------------------------------------------------------------


def _summary(output: Mapping[str, Any]) -> str:
    verdict = output["verdict"]
    if output["mode"] == "trajectory":
        first = output.get("first_divergence")
        if first:
            return (
                f"{verdict}: first divergence {first['dimension']} at step {first['step_index']} "
                f"({first['field']}): strict={first['strict']!r} fast={first['fast']!r}"
            )
        return (
            f"{verdict} ({output['fast_kind']} FAST): no divergence in "
            f"{', '.join(output['dimensions_judged'])}"
        )
    failed = [row["input_id"] for row in output["per_input"] if row["pass"] is False]
    tost_part = ""
    if output["tost"] is not None:
        result = output["tost"]
        tost_part = (
            f"; TOST diff={result['diff']:+.3f} CI=[{result['ci'][0]:+.3f}, "
            f"{result['ci'][1]:+.3f}] {'pass' if result['pass'] else 'FAIL'}"
        )
    return f"{verdict}: rule (i) mismatches {failed or 'none'}{tost_part}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare a FAST run against STRICT (#536). trajectory: an isolated FAST "
        "(no shared state) is judged on the report dimensions; a shared-state FAST needs "
        "parity_subject in both reports (else exit 2).",
        epilog="exit codes: 0 equivalent, 1 not equivalent, 2 input error",
    )
    parser.add_argument("--mode", choices=("trajectory", "replay"), required=True)
    parser.add_argument("--strict", type=Path, required=True, help="STRICT run folder")
    parser.add_argument("--fast", type=Path, required=True, help="FAST run folder")
    parser.add_argument(
        "--stop-first", action="store_true", help="trajectory: first divergence only"
    )
    parser.add_argument(
        "--fast-kind",
        choices=FAST_KINDS,
        help="trajectory (required): isolated = no state shared between cases (option 1); "
        "shared = one container or a reused sandbox (needs parity_subject)",
    )
    parser.add_argument("--inputs", type=Path, help="replay: fixed input set [{input_id, case}]")
    parser.add_argument("--n", type=int, default=DEFAULT_N, help="replay: rounds per input")
    parser.add_argument("--tost-margin", type=float, default=DEFAULT_MARGIN)
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return INPUT_ERROR if error.code else EQUIVALENT
    try:
        if args.mode == "trajectory":
            if args.fast_kind is None:
                raise InputError("--mode trajectory needs --fast-kind isolated|shared")
            code, output = compare_trajectory(
                args.strict, args.fast, stop_first=args.stop_first, fast_kind=args.fast_kind
            )
        else:
            if args.inputs is None:
                raise InputError("--mode replay needs --inputs")
            if args.n < 1:
                raise InputError("--n must be positive")
            code, output = compare_replay(
                args.strict,
                args.fast,
                args.inputs,
                n=args.n,
                margin=args.tost_margin,
                alpha=args.alpha,
            )
    except InputError as error:
        verdict = "invalid" if isinstance(error, InvalidCampaign) else "input_error"
        print(json.dumps({"mode": args.mode, "verdict": verdict, "error": str(error)}))
        print(f"{verdict}: {error}", file=sys.stderr)
        return INPUT_ERROR
    print(json.dumps(output, indent=2, sort_keys=True))
    print(_summary(output), file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
