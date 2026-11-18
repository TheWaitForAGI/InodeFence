"""FS-resolution routing model for #517 cells (exploratory; counts and booleans only, no run).

Definition: W3's gap analysis in Drive ``03-대규모 탐색·인프라(…)/``
(``20261118-엔진레인-갭분석-…``, sha256 ``09a68d1a…``) §부기, and W3's nine answers and two
follow-ups (가)·(나) copied verbatim in Drive ``02-엔진(…)/``, file
``20261118-HOST4-517-FS해석-라우팅판정-가능성.md``, §5. Nothing here goes beyond them.

What it computes, per step of the shell population (an archive with >= 2 symlink entries and
>= 1 hardlink entry), from the step journal alone:

* ``fs_routes`` [inferred] -- a hardlink's link target, resolved the way the extractor calls
  link() (answer 5: first lexical ``path.resolve(cwd, linkpath)``, then component by component
  following symlinks on the virtual disk; the last component is not followed, as link() does
  not), passes through an archive symlink that occupied its path at link() time, chains included
  (answer 1c). The occupant of a path is the last entry with a succeeded event on it before the
  hardlink's ``link`` event (answers 1a, 3, 4 and follow-up (나)); it is a symlink only when that
  last entry's event there was a succeeded ``symlink``. Without a ``link`` event the declared
  order stands in (answer 2);
* ``fs_escape_zone`` [inferred] -- where that resolution ends: EXTRACTION / HARNESS / EXTERNAL
  (answer 7, the ``path_region`` zones; above the sandbox root is EXTERNAL);
* ``dest`` [inferred] -- the hardlink's own destination path through on-disk symlinks, a
  separate column (answer 1b): the destination is first normalised by the policy's lexical rules
  (answer 6, follow-up (가)); an entry those rules skip reads ``skipped``;
* ``unresolvable`` -- ``loop``, ``limit`` (more than 40 symlinks followed, answer 9) or
  ``dangling`` (a followed symlink leads to a missing intermediate component inside the
  extraction root), each counted apart and never folded into a route or escape;
* ``target_missing`` [inferred] -- a route whose final object (what link() names) is missing:
  link() would fail, but the attempt went through the symlink, so it stays a route (answer 4:
  a refused hardlink is still judged), marked apart;
* ``order`` -- whether the step's observed event order differs from the archive order; the
  hardlink's own order basis (``events`` or the ``entry_index`` fallback, answer 2);
* oracle C0/C1/C2 [observed], copied from the step record. The additive detectors W3 asked for
  (answer 8) are computed from the AFTER snapshot, which the step record does not carry, so that
  column reads ``not recorded`` -- never 0.

A step whose effect events were truncated (the 64-event cap) is ``판정 불가`` (answer 4); its
[inferred] columns are ``null``, never false or zero.

[inferred] means: POSIX resolution rules applied, in the recorded order, to the declared
entries and the recorded symlink creations. It is a model, not the extractor's actual
resolution. Everything happens in an in-memory tree: the tool never creates, links or resolves
anything on the host filesystem.

Extractor-specific rules live in a named policy, given without default (``--policy``); a cell
whose report names another target or version than the policy is exit 2.

Input: a #517 cell folder (``seed-*/target-explore/*.steps.jsonl[.gz]``, each with its engine
report ``<name>.json[.gz]`` beside it for the target version). Steps are read one at a time and
dropped. Output: counts and booleans only -- no path strings, bytes or sentinel names.

Exit codes: 0 counts written, 2 input error (no steps, missing report, policy mismatch).
"""

from __future__ import annotations

import argparse
import gzip
import json
import posixpath
import sys
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXTRACTION, HARNESS, EXTERNAL = "EXTRACTION", "HARNESS", "EXTERNAL"
SYMLINK_LIMIT = 40  # answer 9 ("상한 정하기, 예 40"); Linux MAXSYMLINKS
SUCCEEDED = "succeeded"
NOT_RECORDED = "not recorded"
INFERRED = (
    "[inferred]: POSIX resolution applied in the recorded order to the declared entries and the "
    "recorded symlink creations; a model, not the extractor's actual resolution"
)
OBSERVED = "[observed]: copied from the step record (oracle C0/C1/C2)"
JUDGEMENT_IMPOSSIBLE = "판정 불가"


class InputError(Exception):
    """Missing or inconsistent input (exit 2)."""


@dataclass(frozen=True)
class Policy:
    """Extractor-specific rules, kept out of the general model (W3 answers 3 and 6)."""

    name: str
    target: str
    version: str
    #: answer 3 + follow-up (나): who occupies a path at link() time.
    occupant_rule: str
    #: answer 6 + follow-up (가): lexical destination rules, applied in order.
    destination_rules: tuple[str, ...]


OCCUPANT_LAST_SUCCEEDED = "last-succeeded-before-link"
STRIP_ABSOLUTE = "strip-absolute-prefix"  # leading "/", a drive "X:", a UNC "//host/share/"
NORMALIZE = "lexical-normalize"  # drop ".", fold ".."
SKIP_OUTSIDE_ROOT = "skip-if-outside-root"  # a result that is ".." or starts with "../"
OCCUPANT_RULES = (OCCUPANT_LAST_SUCCEEDED,)
DESTINATION_RULES = (STRIP_ABSOLUTE, NORMALIZE, SKIP_OUTSIDE_ROOT)

#: Named policies (W3: this cell is node-tar 7.5.7, answer 3; values from follow-ups (가)·(나)).
POLICIES: dict[str, Policy] = {
    "node-tar-7.5.7": Policy(
        "node-tar-7.5.7",
        "node-tar",
        "7.5.7",
        occupant_rule=OCCUPANT_LAST_SUCCEEDED,
        destination_rules=(STRIP_ABSOLUTE, NORMALIZE, SKIP_OUTSIDE_ROOT),
    ),
}


# -- reading ---------------------------------------------------------------------------------------


def _open_text(path: Path) -> Iterator[str]:
    if path.name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            yield from stream
    else:
        with path.open(encoding="utf-8") as stream:
            yield from stream


def _report_for(steps: Path) -> Path:
    name = steps.name
    for suffix in (".steps.jsonl.gz", ".steps.jsonl"):
        if name.endswith(suffix):
            stem = name[: -len(suffix)]
            for candidate in (f"{stem}.json", f"{stem}.json.gz"):
                if (steps.parent / candidate).is_file():
                    return steps.parent / candidate
    raise InputError(f"{steps}: no engine report beside it (needed for the target version)")


def check_policy(report_path: Path, policy: Policy) -> None:
    """The cell's report must name the policy's target and version, else exit 2."""
    data = json.loads("".join(_open_text(report_path)))
    version = data.get("node_tar_version") if isinstance(data, dict) else None
    target = "node-tar" if version is not None else None
    if (target, version) != (policy.target, policy.version):
        raise InputError(
            f"{report_path.name}: records {target} {version}, policy {policy.name} is for "
            f"{policy.target} {policy.version}"
        )


def step_files(cell: Path) -> list[Path]:
    found = sorted(cell.glob("seed-*/target-explore/*.steps.jsonl.gz")) + sorted(
        cell.glob("seed-*/target-explore/*.steps.jsonl")
    )
    if not found:
        raise InputError(f"{cell}: no seed-*/target-explore/*.steps.jsonl[.gz]")
    return found


# -- the virtual tree ------------------------------------------------------------------------------

Position = tuple[str, ...]  # components from the sandbox root


@dataclass(frozen=True)
class Resolution:
    position: Position
    above: bool  # left the sandbox root (container path): EXTERNAL
    followed: tuple[Position, ...]
    failure: str | None  # "loop" | "limit" | "dangling"
    #: after a symlink, the last component (the object link() names) is missing under extract/.
    #: link() then fails, but the attempt went through the symlink: a route, marked apart.
    target_missing: bool = False


def zone(position: Position, above: bool) -> str:
    """``path_region`` zones (answer 7): extract/ is EXTRACTION, the sandbox root and archive/
    are HARNESS, everything else (outside/, above the sandbox) is EXTERNAL."""
    if above:
        return EXTERNAL
    if not position or position[0] == "archive":
        return HARNESS
    return EXTRACTION if position[0] == "extract" else EXTERNAL


def lexical(link_target: str) -> tuple[Position, bool]:
    """``path.resolve(extraction root, link_target)`` as components from the sandbox root
    (answer 5, first stage): join and fold ``..`` lexically. An absolute target or one that folds
    above the sandbox root is a container path (above)."""
    if link_target.startswith("/"):
        return (), True
    parts: list[str] = ["extract"]
    for part in link_target.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return (), True
            parts.pop()
        else:
            parts.append(part)
    return tuple(parts), False


def resolve(
    start: Position,
    symlinks: Mapping[Position, str],
    existing: frozenset[Position],
    *,
    follow_last: bool,
) -> Resolution:
    """Component-by-component physical resolution on the virtual tree (answer 5, second stage).

    ``symlinks`` are the archive symlinks present at that moment (sandbox position -> declared
    target text); only positions under extract/ can hold one. A relative target is read from the
    symlink's directory, ``..`` after a symlink applies to where the symlink led (physical). A
    revisited (symlink, remaining path) state is a loop; more than SYMLINK_LIMIT follows is the
    limit; after a symlink, a missing *intermediate* component under extract/ is dangling (a
    symlink that leads nowhere). A missing *last* component is not dangling: the resolution
    reached the directory through the symlink, so it routes, with ``target_missing`` set.
    Positions outside extract/ are not modelled and count as present.
    """
    pending: list[str] = list(start)
    current: list[str] = []
    above = False
    followed: list[Position] = []
    seen: set[tuple[Position, tuple[str, ...]]] = set()
    while pending:
        part = pending.pop(0)
        if part in ("", "."):
            continue
        if part == "..":
            if above or not current:
                above, current = True, []
            else:
                current.pop()
            continue
        if above:
            current.append(part)
            continue
        candidate = (*current, part)
        last = all(p in ("", ".") for p in pending)
        if candidate in symlinks and (follow_last or not last):
            state = (candidate, tuple(pending))
            if state in seen:
                return Resolution(tuple(current), above, tuple(followed), "loop")
            if len(followed) >= SYMLINK_LIMIT:
                return Resolution(tuple(current), above, tuple(followed), "limit")
            seen.add(state)
            followed.append(candidate)
            target = symlinks[candidate]
            if target.startswith("/"):
                above, current = True, []
            pending = [p for p in target.split("/")] + pending
            continue
        if followed and candidate[0] == "extract" and candidate not in existing:
            if not last:
                return Resolution(candidate, above, tuple(followed), "dangling")
            return Resolution(candidate, above, tuple(followed), None, target_missing=True)
        current.append(part)
    return Resolution(tuple(current), above, tuple(followed), None)


# -- one step -------------------------------------------------------------------------------------


def _components(path: str) -> Position:
    return tuple(p for p in path.split("/") if p not in ("", "."))


@dataclass(frozen=True)
class StepModel:
    """One step. On a 판정 불가 step (``judgeable`` false) every [inferred] field is ``None`` --
    never false, "none" or zero (answer 4)."""

    shell: bool
    judgeable: bool
    routes: bool | None
    escape_zone: str | None  # "none" | HARNESS | EXTERNAL
    unresolvable: tuple[str, ...] | None
    target_missing: bool | None  # a route whose final object was missing (link() would fail)
    dest: str | None  # "none" | "skipped" | "routes:<zone>" | "unresolvable:<kind>"
    order_mismatch: bool | None
    order_basis: str | None  # "events" | "entry_index" | "mixed"


def model_step(step: Mapping[str, Any], policy: Policy) -> StepModel:
    trace = step.get("trace") or {}
    entries = list(trace.get("entries") or [])
    types = [e.get("type") for e in entries]
    shell = types.count("symlink") >= 2 and types.count("hardlink") >= 1
    if policy.occupant_rule not in OCCUPANT_RULES:
        raise ValueError(f"policy {policy.name}: unknown occupant rule {policy.occupant_rule!r}")
    if not shell:
        return StepModel(False, False, None, None, None, None, None, None, None)
    if trace.get("effect_events_truncated"):
        return StepModel(True, False, None, None, None, None, None, None, None)
    events = list(trace.get("effect_events") or [])

    # Order: the first event of each entry, by start sequence, against entry_index (answer 2).
    first_start: dict[int, int] = {}
    for event in events:
        index, start = event.get("entry_index"), event.get("start_sequence")
        if isinstance(index, int) and isinstance(start, int):
            first_start[index] = min(start, first_start.get(index, start))
    by_events = sorted(first_start, key=lambda i: first_start[i])
    order_mismatch = by_events != sorted(by_events)

    # Succeeded events per path (answer 4): (start sequence, entry_index, operation).
    touched: dict[Position, list[tuple[int, int, str]]] = {}
    applied: set[Position] = set()
    for event in events:
        index, start = event.get("entry_index"), event.get("start_sequence")
        done = event.get("completion_sequence")
        if event.get("outcome") != SUCCEEDED or not isinstance(index, int):
            continue
        for item in event.get("paths") or []:
            position = _components(str(item.get("path") or ""))
            if not position:
                continue
            applied.add(position)
            for depth in range(1, len(position)):
                applied.add(position[:depth])
            # follow-up (나): an event counts from its completion (start when not recorded)
            order = done if isinstance(done, int) else start if isinstance(start, int) else -1
            touched.setdefault(position, []).append((order, index, str(event.get("operation"))))
    existing = frozenset(applied | {("extract",), ("archive",), ("outside",)})

    routes, worst, failures, bases, dests, missing = False, "none", [], set(), [], False
    for index, entry in enumerate(entries):
        if entry.get("type") != "hardlink":
            continue
        link_events = [
            e
            for e in events
            if e.get("entry_index") == index
            and e.get("operation") == "link"
            and isinstance(e.get("start_sequence"), int)
        ]
        link_time = min((e["start_sequence"] for e in link_events), default=None)
        bases.add("events" if link_time is not None else "entry_index")
        present = _occupying_symlinks(touched, entries, index, link_time)
        start, above = lexical(str(entry.get("link_target") or ""))
        result = (
            Resolution((), True, (), None)
            if above
            else resolve(start, present, existing, follow_last=False)
        )
        # answer 1b: the destination is its own vector, computed whatever the target gives.
        dests.append(_destination(entry, present, existing, policy))
        if result.failure is not None:
            failures.append(result.failure)
            continue
        if result.followed:
            routes = True
            missing = missing or result.target_missing
            where = zone(result.position, result.above)
            if where != EXTRACTION and (worst == "none" or where == EXTERNAL):
                worst = where
    basis = bases.pop() if len(bases) == 1 else ("mixed" if bases else "none")
    dest = next((d for d in dests if d.startswith("routes:")), None) or next(
        (d for d in dests if d != "none"), "none"
    )
    return StepModel(
        True, True, routes, worst, tuple(sorted(failures)), missing, dest, order_mismatch, basis
    )


def _occupying_symlinks(
    touched: Mapping[Position, Sequence[tuple[int, int, str]]],
    entries: Sequence[Mapping[str, Any]],
    hardlink: int,
    link_time: int | None,
) -> dict[Position, str]:
    """Follow-up (나): per path, the occupant at link() time is the last entry with a succeeded
    event there before the link (by event order; without a link event, by declared order). The
    path holds a symlink only when that last entry's event there was a succeeded ``symlink``; its
    target is that entry's declared link text. The hardlink's own events are not counted."""
    present: dict[Position, str] = {}
    for position, hits in touched.items():
        if link_time is not None:
            earlier = [h for h in hits if h[1] != hardlink and 0 <= h[0] < link_time]
            last = max(earlier, default=None)
        else:
            earlier = [h for h in hits if h[1] < hardlink]
            last = max(earlier, key=lambda h: (h[1], h[0]), default=None)
        if last is None or last[2] != "symlink":
            continue
        occupant = last[1]
        target = entries[occupant].get("link_target") if occupant < len(entries) else None
        if entries[occupant].get("type") == "symlink" and isinstance(target, str):
            present[position] = target
    return present


def destination(path: str, rules: Sequence[str]) -> Position | None:
    """Follow-up (가): node-tar 7.5.7's lexical destination rules, in order. ``None`` = the entry
    is skipped (its normalised path leaves the root)."""
    for rule in rules:
        if rule not in DESTINATION_RULES:
            raise ValueError(f"unknown destination rule {rule!r}")
    if STRIP_ABSOLUTE in rules:
        while True:
            if path.startswith("//"):  # UNC //host/share/...
                rest = path.lstrip("/").split("/", 2)
                path = rest[2] if len(rest) > 2 else ""
            elif len(path) >= 2 and path[1] == ":" and path[0].isalpha():
                path = path[2:]
            elif path.startswith("/"):
                path = path.lstrip("/")
            else:
                break
    if NORMALIZE in rules:
        path = posixpath.normpath(path) if path else "."
    if SKIP_OUTSIDE_ROOT in rules and (path == ".." or path.startswith("../")):
        return None
    return _components(path)


def _destination(
    entry: Mapping[str, Any],
    present: Mapping[Position, str],
    existing: frozenset[Position],
    policy: Policy,
) -> str:
    """Answer 1b: the hardlink's own destination, normalised by the policy's lexical rules
    (follow-up (가)), then resolved through on-disk symlinks (the last component is the new name,
    not followed). A separate vector from the link target; never mixed into ``fs_routes``."""
    components = destination(str(entry.get("path") or ""), policy.destination_rules)
    if components is None:
        return "skipped"
    result = resolve(("extract", *components), present, existing, follow_last=False)
    if result.failure is not None:
        return f"unresolvable:{result.failure}"
    if not result.followed:
        return "none"
    return f"routes:{zone(result.position, result.above)}"


# -- the cell --------------------------------------------------------------------------------------


def outcome_of(step: Mapping[str, Any]) -> str:
    if step.get("outcome") == "build-invalid":
        return "build-invalid"
    return str((step.get("feedback") or {}).get("trace_termination") or "-")


def oracle_of(step: Mapping[str, Any]) -> tuple[bool | None, bool | None, bool | None]:
    oracle = step.get("oracle") or {}
    return (oracle.get("C0"), oracle.get("C1"), oracle.get("C2"))


def model_cell(cell: Path, policy: Policy) -> dict[str, Any]:
    files = step_files(cell)
    for steps in files:
        check_policy(_report_for(steps), policy)
    rows: Counter[tuple[Any, ...]] = Counter()
    totals: Counter[str] = Counter()
    for steps in files:
        for line in _open_text(steps):
            if not line.strip():
                continue
            step = json.loads(line)
            totals["steps"] += 1
            result = model_step(step, policy)
            if not result.shell:
                continue
            totals["shell"] += 1
            if not result.judgeable:
                totals[JUDGEMENT_IMPOSSIBLE] += 1
            c0, c1, c2 = oracle_of(step)
            rows[
                (
                    result.judgeable,
                    result.routes,
                    result.escape_zone,
                    result.unresolvable,
                    result.target_missing,
                    result.dest,
                    result.order_mismatch,
                    result.order_basis,
                    outcome_of(step),
                    c0,
                    c1,
                    c2,
                )
            ] += 1
            del step
    keys = (
        "judgeable",
        "fs_routes",
        "fs_escape_zone",
        "unresolvable",
        "target_missing",
        "dest",
        "order_mismatch",
        "order_basis",
        "outcome",
        "oracle_C0",
        "oracle_C1",
        "oracle_C2",
    )
    return {
        "label": "exploratory",
        "inferred": INFERRED,
        "observed": OBSERVED,
        "policy": {
            "name": policy.name,
            "occupant_rule": policy.occupant_rule,
            "destination_rules": list(policy.destination_rules),
            "symlink_limit": SYMLINK_LIMIT,
        },
        "columns": {
            "inferred": [
                "fs_routes",
                "fs_escape_zone",
                "unresolvable",
                "target_missing",
                "dest",
                "order_mismatch",
                "order_basis",
            ],
            "observed": ["outcome", "oracle_C0", "oracle_C1", "oracle_C2"],
        },
        "additive_detectors": NOT_RECORDED,
        "totals": dict(totals),
        "rows": [
            {
                **{
                    key: list(value) if isinstance(value, tuple) else value
                    for key, value in zip(keys, k, strict=True)
                },
                "steps": n,
            }
            for k, n in sorted(rows.items(), key=lambda kv: (-kv[1], repr(kv[0])))
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("cell", type=Path, help="a #517 cell folder (seed-*/target-explore/)")
    parser.add_argument("--policy", required=True, choices=sorted(POLICIES))
    parser.add_argument("--json", type=Path, help="write the counts here too")
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return 2 if error.code else 0
    try:
        output = model_cell(args.cell, POLICIES[args.policy])
    except (InputError, ValueError) as error:
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
