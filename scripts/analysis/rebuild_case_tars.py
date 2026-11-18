"""Rebuild the input TAR of chosen steps from an exploration's step journal (no target run).

Decision IF-ORCH D-269; method and limits in Drive ``02-엔진(…)/``, file
``20261118-HOST4-D260-결정성-tar재구성.md``.
A step record keeps every entry's path, type and link target, but not regular-file content or
mode. It does keep the step's ``case_id`` (SHA-256 of the whole logical case, content and mode
included) and its ``parent_case_id``. So each case is rebuilt along its lineage, starting from
the policy's seed corpus:

* the child's entries that match the (already rebuilt) parent keep the parent's content and
  mode;
* the other values are drawn from the v2 grammar's pinned sets plus the seed corpus's values;
* when the parent has several entries of one shape (path, type, link target) that differ only in
  content or mode, a reorder or a duplicate can make the alignment pair the wrong ones; a plan
  where each entry may take the values of any same-shape parent entry covers that (D-324);
* a candidate is accepted **only** when its ``case_id`` equals the recorded one. That match is
  the sole criterion -- the tool imports the current engine's builder and grammar, which it
  cannot itself prove equal to the cell's engine, so nothing leaves without it. ``build_tar``
  is a pure function of the case (fixed zero/empty metadata), so a matching ``case_id`` means
  the same TAR bytes.

Steps that cannot be rebuilt are listed with their reason, never dropped silently.

Refused (exit 2):
* the run's recorded engine commit is missing or differs from ``--expected-engine``;
* the journal is incomplete: step indices not 0..n-1, or n differs from the recorded budget, or
  no budget is recorded;
* ``--mutation-policy`` is not a v2 grammar policy (v1/M1 contents are random bytes, not a
  pinned set), or differs from the policy the run records (``result.json`` campaign, or the
  ``vocab_mode`` in ``progress.json`` that explore derives from it one-to-one). A run with
  neither record is not checked against a recorded policy; the ``case_id`` match is then the
  only guarantee;
* ``--out`` inside the repository or a Drive mount, or an existing folder;
* ``--target``/``--version``/``--image-id`` differing from what the run records, or a
  ``--run-settings-missing`` key differing from the recorded value.

Run settings come from the run itself: node-tar exploration writes ``run_settings`` (sentinel
count and seed, observer-integrity policy, profile) into the live ``progress.json`` through
``LiveRunMeta`` (``scripts/run_effect_demo.py`` builds them; ``live_exploration.py`` snapshots
them). Only keys the record lacks may come from ``--run-settings-missing``; the summary and
each ``case.json`` say which keys came from where. The target's own ``replay_check`` reads each
written folder back, so incomplete settings fail there and are listed.

Which steps to rebuild is an input (``--steps-list``: one step index per line); no selection
rule lives in this tool. Output, on the run host's local disk only: ``step-NNNNNN/`` with
``input.tar`` and ``case.json`` (the live-violation schema, read back with the replay loader),
``failures.json`` (step index and reason; a "parent not rebuilt" step also names, as
``blocked_by_step`` and ``blocked_by_reason``, the ancestor step that failed first along its
lineage, which may be outside the requested list), and a summary of counts on stdout (no paths,
no entry content). Exit codes: 0 every requested step verified, 1 some failed, 2 a precondition
failed.
"""

from __future__ import annotations

import argparse
import difflib
import gzip
import itertools
import json
import sys
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any

from inodefence.builder import build_tar
from inodefence.case_replay import (
    CASE_FILE,
    CASE_SCHEMA,
    CASE_TAR,
    CaseReplayError,
    load_replay_request,
)
from inodefence.drivers.run_target import load_adapter
from inodefence.effect_campaign import bound_seed_cases
from inodefence.evaluation.rds import VOCABULARY_MUTATION_POLICY
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.mutator.policy import V2_GRAMMAR_POLICIES, MutationPolicy
from inodefence.mutator.v2_freeze3 import FINAL_UNIFORM

REPO_ROOT = Path(__file__).resolve().parents[2]
#: Drive mount names refused for --out (the input bytes stay on the run host's local disk).
DRIVE_PARTS = frozenset({"Drive", "My Drive", "GoogleDrive", "Google Drive"})
#: Upper bound of candidates tried per step (cost guard; a step above it is a reported failure).
SEARCH_LIMIT = 200_000
#: Symlinks the v2 grammar adds carry mode 0o777 (``mutator/v2_freeze3.py`` add_symlink).
SYMLINK_MODE = 0o777

NO_PARENT = "parent not rebuilt"
NOT_SEED = "seed case_id not in the policy's seed corpus"
NO_MATCH = "no candidate matches the recorded case_id"
TOO_LARGE = "candidate space above the search limit"
BUILD_INVALID = "build-invalid step (no executed input)"
NOT_IN_JOURNAL = "step index not in the journal"
REPLAY_REFUSED = "replay loader refused the written folder"


class Precondition(Exception):
    """A precondition failed (exit 2)."""


# -- inputs ----------------------------------------------------------------------------------------


def _lines(path: Path) -> Iterator[str]:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:  # type: ignore[operator]
        yield from stream


def run_records(run_dir: Path) -> dict[str, Any]:
    """What the run records beside the journal: live ``progress.json`` (``engine_commit``,
    ``budget``, ``target``, ``version``, ``image_id``, ``run_settings`` -- ``LiveRunMeta``) and
    ``result.json`` (``provenance.engine_sha``/``engine_dirty``, ``campaign.budget`` /
    ``mutation_policy``). Two records of one key that disagree are a precondition failure."""
    keys = (
        "engine_commit",
        "budget",
        "mutation_policy",
        "target",
        "version",
        "image_id",
        "vocab_mode",
    )
    found: dict[str, set[Any]] = {key: set() for key in keys}
    settings: set[str] = set()
    for path in sorted(run_dir.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if path.name == "progress.json":
            if data.get("engine_commit") not in (None, "unknown"):
                found["engine_commit"].add(data["engine_commit"])
            if isinstance(data.get("budget"), int):
                found["budget"].add(data["budget"])
            for key in ("target", "version", "image_id", "vocab_mode"):
                if isinstance(data.get(key), str) and data[key]:
                    found[key].add(data[key])
            if isinstance(data.get("run_settings"), dict):
                settings.add(json.dumps(data["run_settings"], sort_keys=True))
        elif path.name == "result.json":
            provenance = data.get("provenance") or {}
            if provenance.get("engine_sha"):
                dirty = "-dirty" if provenance.get("engine_dirty") else ""
                found["engine_commit"].add(f"{provenance['engine_sha']}{dirty}")
            campaign = data.get("campaign") or {}
            if isinstance(campaign.get("budget"), int):
                found["budget"].add(campaign["budget"])
            if campaign.get("mutation_policy"):
                found["mutation_policy"].add(campaign["mutation_policy"])
    for key, values in found.items():
        if len(values) > 1:
            raise Precondition(f"the run's records disagree on {key}: {sorted(map(str, values))}")
    if len(settings) > 1:
        raise Precondition("the run's records disagree on run_settings")
    out: dict[str, Any] = {key: next(iter(v)) if v else None for key, v in found.items()}
    out["run_settings"] = json.loads(next(iter(settings))) if settings else None
    return out


def merge_run_settings(
    recorded: Mapping[str, Any] | None, given: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str], list[str]]:
    """(settings, keys from the record, keys from the argument). A given key the record also
    holds must carry the same value (else a precondition failure); only absent keys are filled."""
    merged = dict(recorded or {})
    for key, value in given.items():
        if key in merged and merged[key] != value:
            raise Precondition(
                f"run_settings[{key!r}] differs from the run's record; only keys the record "
                "lacks may be given"
            )
    from_argument = sorted(key for key in given if key not in merged)
    for key in from_argument:
        merged[key] = given[key]
    return merged, sorted(recorded or {}), from_argument


def check_out(out: Path) -> Path:
    out = out.resolve()
    if out == REPO_ROOT or out.is_relative_to(REPO_ROOT):
        raise Precondition("--out must be outside the repository")
    if out.is_relative_to(Path.home() / "Drive") or DRIVE_PARTS & set(out.parts):
        raise Precondition("--out must not be on a Drive mount (input bytes stay on local disk)")
    if out.exists():
        raise Precondition(f"{out.name} exists; nothing is overwritten")
    return out


def read_steps_list(path: Path) -> list[int]:
    wanted: list[int] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text:
            continue
        if not text.isdigit():
            raise Precondition(f"--steps-list line {number}: not a step index")
        wanted.append(int(text))
    if not wanted:
        raise Precondition("--steps-list is empty")
    return wanted


# -- rebuilding ------------------------------------------------------------------------------------


Shape = tuple[str, str, str | None]


def candidate_values(seeds: Sequence[ArchiveCase]) -> tuple[tuple[bytes, ...], tuple[int, ...]]:
    contents = set(FINAL_UNIFORM.contents)
    modes = set(FINAL_UNIFORM.modes) | {ArchiveEntry("x", EntryType.DIRECTORY).mode, SYMLINK_MODE}
    for case in seeds:
        for entry in case.entries:
            modes.add(entry.mode)
            if entry.content is not None:
                contents.add(entry.content)
    return tuple(sorted(contents)), tuple(sorted(modes))


def matches(candidate: ArchiveCase, recorded_case_id: str) -> bool:
    """The only acceptance test (D-269): the rebuilt case's id equals the recorded one."""
    return candidate.case_id == recorded_case_id


def rebuild(
    parent: ArchiveCase,
    shapes: Sequence[Shape],
    recorded_case_id: str,
    contents: Sequence[bytes],
    modes: Sequence[int],
) -> tuple[ArchiveCase | None, str | None]:
    """(case, None) when a candidate matches, else (None, reason)."""
    if not shapes:
        empty = ArchiveCase(())
        return (empty, None) if matches(empty, recorded_case_id) else (None, NO_MATCH)
    kinds = [EntryType(shape[1]) for shape in shapes]
    parent_shapes = [(e.path, e.entry_type.value, e.link_target) for e in parent.entries]
    copied: list[tuple[bytes | None, int] | None] = [None] * len(shapes)
    matcher = difflib.SequenceMatcher(a=parent_shapes, b=list(shapes), autojunk=False)
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            entry = parent.entries[a + k]
            copied[b + k] = (entry.content, entry.mode)

    def options(i: int) -> list[tuple[bytes | None, int]]:
        if kinds[i] == EntryType.REGULAR:
            return [(c, m) for c in contents for m in modes]
        return [(None, m) for m in modes]

    def same_shape(i: int) -> list[tuple[bytes | None, int]]:
        """The values of every parent entry with entry ``i``'s shape (path, type, link target).

        The alignment above pairs equal shapes by position. When the parent has several entries
        of one shape that differ only in content or mode, a reorder or a duplicate can pair the
        child with the wrong one; this pool lets each entry take any of them (D-324)."""
        values = {
            (entry.content, entry.mode)
            for entry, shape in zip(parent.entries, parent_shapes, strict=True)
            if shape == tuple(shapes[i])
        }
        return sorted(values, key=repr) if values else options(i)

    unmatched = [i for i, value in enumerate(copied) if value is None]
    plans: list[list[int]] = [unmatched]
    plans += [[*unmatched, i] for i in range(len(shapes)) if i not in unmatched]
    plans.append(list(range(len(shapes))))
    pool_plans: list[list[list[Any]]] = [
        [options(i) if i in vary else [copied[i]] for i in range(len(shapes))] for vary in plans
    ]
    # Before the full space: every entry from its same-shape parent values (D-324).
    pool_plans.insert(-1, [same_shape(i) for i in range(len(shapes))])
    too_large = False
    for pools in pool_plans:
        size = 1
        for pool in pools:
            size *= len(pool)
        if size > SEARCH_LIMIT:
            too_large = True
            continue
        for choice in itertools.product(*pools):
            candidate = ArchiveCase(
                tuple(
                    ArchiveEntry(
                        shape[0],
                        kinds[i],
                        content=choice[i][0],  # type: ignore[index]
                        link_target=shape[2],
                        mode=choice[i][1],  # type: ignore[index]
                    )
                    for i, shape in enumerate(shapes)
                )
            )
            if matches(candidate, recorded_case_id):
                return candidate, None
    return None, TOO_LARGE if too_large else NO_MATCH


def _shapes(record: Mapping[str, Any]) -> list[Shape]:
    return [
        (str(e.get("path")), str(e.get("type")), e.get("link_target"))
        for e in (record.get("trace") or {}).get("entries") or []
    ]


#: Where a "parent not rebuilt" failure comes from: the ancestor step (requested or not) whose
#: own rebuild failed, and its reason. ``None`` step: the parent case_id is not earlier in the
#: journal (D-324).
Blocker = tuple[int | None, str]
NO_PARENT_IN_JOURNAL = "parent case_id not earlier in the journal"


def rebuild_journal(
    journal: Path, policy: MutationPolicy, wanted: set[int]
) -> tuple[dict[int, tuple[ArchiveCase, dict[str, Any]]], dict[int, str], int, dict[int, Blocker]]:
    """Walk the journal once in order, rebuilding every executed case (parents are needed);
    keep the wanted ones. Returns (rebuilt wanted, failures by index, steps seen, and for each
    wanted "parent not rebuilt" failure the ancestor step that failed first and its reason)."""
    seeds = bound_seed_cases(minimal_seed_corpus(), policy)
    seed_by_id = {case.case_id: case for case in seeds}
    contents, modes = candidate_values(seeds)
    known: dict[str, ArchiveCase] = {}
    rebuilt: dict[int, tuple[ArchiveCase, dict[str, Any]]] = {}
    failures: dict[int, str] = {}
    # Every failed case_id (requested or not) -> the first failing ancestor along its lineage.
    failed_root: dict[str, Blocker] = {}
    blocked: dict[int, Blocker] = {}
    expected = 0
    for line in _lines(journal):
        if not line.strip():
            continue
        record = json.loads(line)
        index = record.get("index")
        if index != expected:
            raise Precondition(f"journal incomplete: step {expected} expected, found {index}")
        expected += 1
        if record.get("outcome") == "build-invalid":
            if index in wanted:
                failures[index] = BUILD_INVALID
            continue
        case_id = str(record.get("case_id"))
        case: ArchiveCase | None
        root: Blocker | None = None
        if record.get("origin") == "seed":
            case = seed_by_id.get(case_id)
            reason = None if case is not None else NOT_SEED
        else:
            parent_id = str(record.get("parent_case_id"))
            parent = known.get(parent_id)
            if parent is None:
                case, reason = None, NO_PARENT
                root = failed_root.get(parent_id, (None, NO_PARENT_IN_JOURNAL))
            else:
                case, reason = rebuild(parent, _shapes(record), case_id, contents, modes)
        if case is not None:
            known[case_id] = case
            if index in wanted:
                summary = {
                    "oracle": record.get("oracle") or {},
                    "trace_termination": (record.get("feedback") or {}).get("trace_termination"),
                }
                rebuilt[index] = (case, summary)
            continue
        if root is None:
            root = (index, str(reason))
        failed_root.setdefault(case_id, root)
        if index in wanted:
            failures[index] = str(reason)
            if reason == NO_PARENT:
                blocked[index] = root
    return rebuilt, failures, expected, blocked


# -- output ----------------------------------------------------------------------------------------


def failure_item(step: int, reason: str, blocker: Blocker | None) -> dict[str, Any]:
    """One ``failures.json`` item. A "parent not rebuilt" step also names the ancestor step that
    failed first along its lineage (possibly outside the requested list) and that step's reason."""
    item: dict[str, Any] = {"step": step, "reason": reason}
    if blocker is not None:
        item["blocked_by_step"], item["blocked_by_reason"] = blocker
    return item


def case_record(
    index: int,
    case: ArchiveCase,
    tar_bytes: bytes,
    summary: Mapping[str, Any],
    *,
    target: str,
    version: str,
    image_id: str,
    run_settings: Mapping[str, Any],
    settings_source: Mapping[str, Sequence[str]],
    engine_commit: str,
) -> dict[str, Any]:
    oracle = summary.get("oracle") or {}
    return {
        "schema": CASE_SCHEMA,
        "origin": "rebuilt-from-journal",
        "step": index,
        "case_id": case.case_id,
        "target": target,
        "version": version,
        "image_id": image_id,
        "run_settings": dict(run_settings),
        "run_settings_source": {key: list(value) for key, value in settings_source.items()},
        "engine_commit": engine_commit,
        "status": None,
        "c0": oracle.get("C0"),
        "c1": oracle.get("C1"),
        "c2": oracle.get("C2"),
        "fingerprints": [],
        "observation_complete": None,
        "tar": CASE_TAR,
        "tar_sha256": sha256(tar_bytes).hexdigest(),
        "tar_bytes": len(tar_bytes),
        "rebuild": "byte-identical, verified by case_id",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--journal", type=Path, required=True, help="<run>.steps.jsonl[.gz]")
    parser.add_argument(
        "--run-dir", type=Path, required=True, help="the run folder (progress/result records)"
    )
    parser.add_argument("--expected-engine", required=True, help="the cell's engine commit")
    parser.add_argument("--mutation-policy", required=True, help="a v2 grammar policy id")
    parser.add_argument("--steps-list", type=Path, required=True, help="one step index per line")
    parser.add_argument("--target", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--image-id", required=True, help="exact sha256:<64 hex> (ledger value)")
    parser.add_argument(
        "--run-settings-missing",
        default="{}",
        help="JSON object: only run_settings keys the run's record lacks (default none)",
    )
    parser.add_argument("--out", type=Path, required=True, help="local disk, outside the repo")
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return 2 if error.code else 0
    try:
        return _main(args)
    except (Precondition, ValueError) as error:
        print(json.dumps({"verdict": "precondition", "error": str(error)}))
        print(f"refused: {error}", file=sys.stderr)
        return 2


def _main(args: argparse.Namespace) -> int:
    try:
        policy = MutationPolicy(args.mutation_policy)
    except ValueError as error:
        raise Precondition(f"unknown mutation policy {args.mutation_policy!r}") from error
    if policy not in V2_GRAMMAR_POLICIES:
        raise Precondition(
            f"{policy.value} is not a v2 grammar policy: its contents are not a pinned set"
        )
    records = run_records(args.run_dir)
    if records["engine_commit"] is None:
        raise Precondition("the run records no engine commit; it cannot be checked")
    if records["engine_commit"] != args.expected_engine:
        raise Precondition(
            f"the run's engine commit {records['engine_commit']} != --expected-engine "
            f"{args.expected_engine}"
        )
    if records["mutation_policy"] is not None and records["mutation_policy"] != policy.value:
        raise Precondition(f"the run records mutation policy {records['mutation_policy']}")
    if records["vocab_mode"] is not None:
        # progress.json records the vocabulary mode explore derives from the mutation policy
        # (one-to-one, ``evaluation.rds.VOCABULARY_MUTATION_POLICY``): a run without result.json
        # (stopped) is still checked against its record.
        modes = {mode.value: p for mode, p in VOCABULARY_MUTATION_POLICY.items()}
        if modes.get(records["vocab_mode"]) != policy:
            raise Precondition(
                f"the run records vocab_mode {records['vocab_mode']}, which is not {policy.value}'s"
            )
    if records["budget"] is None:
        raise Precondition("the run records no budget; journal completeness cannot be checked")
    for key, given in (
        ("target", args.target),
        ("version", args.version),
        ("image_id", args.image_id),
    ):
        if records[key] is not None and records[key] != given:
            raise Precondition(
                f"--{key.replace('_', '-')} {given} != the run's record {records[key]}"
            )
    try:
        extra = json.loads(args.run_settings_missing)
    except ValueError as error:
        raise Precondition(f"--run-settings-missing is not JSON: {error}") from error
    if not isinstance(extra, dict):
        raise Precondition("--run-settings-missing must be a JSON object")
    settings, from_record, from_argument = merge_run_settings(records["run_settings"], extra)
    source = {"record": from_record, "argument": from_argument}
    check = getattr(load_adapter(args.target), "replay_check", None)
    out = check_out(args.out)
    wanted = read_steps_list(args.steps_list)

    rebuilt, failures, seen, blocked = rebuild_journal(args.journal, policy, set(wanted))
    if seen != records["budget"]:
        raise Precondition(
            f"journal incomplete: {seen} steps, the run's budget is {records['budget']}"
        )
    for index in wanted:
        if index >= seen:
            failures[index] = NOT_IN_JOURNAL

    out.mkdir(parents=True)
    written = 0
    for index, (case, summary) in sorted(rebuilt.items()):
        tar_bytes = build_tar(case)
        folder = out / f"step-{index:06d}"
        folder.mkdir()
        (folder / CASE_TAR).write_bytes(tar_bytes)
        record = case_record(
            index,
            case,
            tar_bytes,
            summary,
            target=args.target,
            version=args.version,
            image_id=args.image_id,
            run_settings=settings,
            settings_source=source,
            engine_commit=str(records["engine_commit"]),
        )
        (folder / CASE_FILE).write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        try:
            request = load_replay_request(folder)
            if check is not None:
                check(request)  # the target's own settings check, as `inodefence replay` does
        except CaseReplayError as error:
            for item in folder.iterdir():
                item.unlink()
            folder.rmdir()
            failures[index] = f"{REPLAY_REFUSED}: {error}"
            continue
        written += 1
    (out / "failures.json").write_text(
        json.dumps(
            [failure_item(i, failures[i], blocked.get(i)) for i in sorted(failures)], indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    reasons = Counter(reason.split(":", 1)[0] for reason in failures.values())
    print(
        json.dumps(
            {
                "requested": len(set(wanted)),
                "verified": written,
                "failed": len(failures),
                "failed_by_reason": dict(sorted(reasons.items())),
                "criterion": "case_id match only",
                "run_settings_from_record": from_record,
                "run_settings_from_argument": from_argument,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
