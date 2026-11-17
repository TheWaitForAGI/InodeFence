"""Input structure classifier ``input-structure-class-v1-freeze-1`` (analysis record only).

Definition: docs/research/design/input-structure-class-v1.md (signed draft 2, ladder level L4).
``classify`` is a pure function of the logical input alone: it never sees an extraction result,
observation, verdict, target, arm or configuration. The value is an analysis record (input of the
v2 secondary endpoint "unique violation kinds", kind = (contract, input structure class)); it does
not enter the oracle, feedback (retention, scheduling, reward) or mutation, and it is recorded the
same way for every arm and every step.

Frozen L4 definition (the document is authoritative; this docstring is a summary):
* N(s): split on "/", drop empty and "." components ("..": kept). abs(s): s starts with "/".
* reach(start, comps): steps above ``start`` reached by walking comps ("..": -1, name: +1).
* E (escape-relevant entries, fixpoint): (1) the path escapes lexically; (2) a link whose target
  is absolute or escapes from the base, or a symlink whose target escapes from its own
  directory; (3) an entry whose path passes through an earlier symlink in E; (4) a symlink whose
  lexical resolution is the path of a symlink in E; (5) a hardlink whose target is the path of an
  entry in E. E empty -> the class is "none".
* A2: the single strongest escape feature (reach {0, 1+} > role target > path > kind
  hardlink > symlink > directory > regular); A3: symlink chain length in E {0, 1, 2, 3+};
  A4: order flags over pairs in E -- O-1 earlier-symlink pass-through, O-4 same-path type
  change, O-5 hardlink forward reference; A5: strongest mode class in E
  {default, non-default, special}. A1 and the absolute/relative form are not part of L4.
No name, sentinel, target, version or CVE information enters the value: names are only compared
for equality, so the class is invariant under consistent renaming of name components.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from inodefence.model.archive import ArchiveCase, ArchiveEntry, EntryType

CLASSIFIER_ID = "input-structure-class-v1-freeze-1"
NONE = "none"

_KIND_RANK = {
    EntryType.REGULAR: 0,
    EntryType.DIRECTORY: 1,
    EntryType.SYMLINK: 2,
    EntryType.HARDLINK: 3,
}
_ROLE_RANK = {"path": 0, "target": 1}
_LINKS = (EntryType.HARDLINK, EntryType.SYMLINK)


def _n(text: str) -> tuple[str, ...]:
    return tuple(part for part in text.split("/") if part not in ("", "."))


def _abs(text: str) -> bool:
    return text.startswith("/")


def _reach(start: int, comps: tuple[str, ...]) -> int:
    depth = lowest = start
    for comp in comps:
        depth = depth - 1 if comp == ".." else depth + 1
        lowest = min(lowest, depth)
    return max(0, -lowest)


def _dir(path: tuple[str, ...]) -> tuple[str, ...]:
    return path[:-1]


def _resolve(entry: ArchiveEntry) -> tuple[str, ...] | None:
    """Lexical resolution of a symlink target (document, draft 1 section 5)."""
    assert entry.link_target is not None
    if _abs(entry.link_target):
        return _n(entry.link_target)
    out = list(_dir(_n(entry.path)))
    for comp in _n(entry.link_target):
        if comp == "..":
            if not out:
                return None
            out.pop()
        else:
            out.append(comp)
    return tuple(out)


def _path_escapes(entry: ArchiveEntry, path: tuple[str, ...]) -> bool:
    return _abs(entry.path) or _reach(0, path) > 0


def _target_escapes(entry: ArchiveEntry, path: tuple[str, ...]) -> bool:
    if entry.entry_type not in _LINKS or entry.link_target is None:
        return False
    target = _n(entry.link_target)
    if _abs(entry.link_target) or _reach(0, target) > 0:
        return True
    return entry.entry_type == EntryType.SYMLINK and _reach(len(_dir(path)), target) > 0


def _escape_set(entries: tuple[ArchiveEntry, ...], paths: list[tuple[str, ...]]) -> list[int]:
    escape = {
        i
        for i, entry in enumerate(entries)
        if _path_escapes(entry, paths[i]) or _target_escapes(entry, paths[i])
    }
    changed = True
    while changed:
        changed = False
        symlink_first: dict[tuple[str, ...], int] = {}
        symlink_paths: set[tuple[str, ...]] = set()
        all_paths: set[tuple[str, ...]] = set()
        for s in escape:
            all_paths.add(paths[s])
            if entries[s].entry_type == EntryType.SYMLINK:
                symlink_paths.add(paths[s])
                symlink_first[paths[s]] = min(symlink_first.get(paths[s], s), s)
        for i, entry in enumerate(entries):
            if i in escape:
                continue
            path = paths[i]
            hit = any(symlink_first.get(path[:k], len(entries)) < i for k in range(1, len(path)))
            if not hit and entry.entry_type == EntryType.SYMLINK:
                resolved = _resolve(entry)
                hit = resolved is not None and resolved in symlink_paths
            if not hit and entry.entry_type == EntryType.HARDLINK and entry.link_target is not None:
                hit = _n(entry.link_target) in all_paths
            if hit:
                escape.add(i)
                changed = True
    return sorted(escape)


def _chain_length(entries: tuple[ArchiveEntry, ...], paths, members: list[int]) -> int:
    symlinks = [i for i in members if entries[i].entry_type == EntryType.SYMLINK]
    if not symlinks:
        return 0
    by_path: dict[tuple[str, ...], list[int]] = {}
    for i in symlinks:
        by_path.setdefault(paths[i], []).append(i)
    successors = {}
    for i in symlinks:
        resolved = _resolve(entries[i])
        successors[i] = [j for j in by_path.get(resolved, ()) if j != i] if resolved else []
    best = 1
    for a in symlinks:
        for b in successors[a]:
            best = max(best, 2)
            if any(c != a for c in successors[b]):
                return 3
    return best


def _order_flags(entries, paths, members: list[int]) -> tuple[bool, bool, bool]:
    groups: dict[tuple[str, ...], list[int]] = {}
    symlink_first: dict[tuple[str, ...], int] = {}
    first_at: dict[tuple[str, ...], int] = {}
    for i in members:
        groups.setdefault(paths[i], []).append(i)
        first_at.setdefault(paths[i], i)
        if entries[i].entry_type == EntryType.SYMLINK:
            symlink_first.setdefault(paths[i], i)
    o4 = any(len({entries[i].entry_type for i in g}) > 1 for g in groups.values())
    o1 = o5 = False
    for i in members:
        path = paths[i]
        if not o1 and any(
            symlink_first.get(path[:k], len(entries)) < i for k in range(1, len(path))
        ):
            o1 = True
        entry = entries[i]
        if not o5 and entry.entry_type == EntryType.HARDLINK and entry.link_target is not None:
            first = first_at.get(_n(entry.link_target))
            if first is not None and first > i:
                o5 = True
    return o1, o4, o5


def _default_mode(entry: ArchiveEntry) -> int:
    return 0o777 if entry.entry_type == EntryType.SYMLINK else 0o644


def _mode_class(entries, members: list[int]) -> str:
    strongest = "default"
    for i in members:
        mode = entries[i].mode
        if mode & 0o7000:
            return "special"
        if mode != _default_mode(entries[i]):
            strongest = "non-default"
    return strongest


@dataclass(frozen=True, slots=True)
class InputStructureClass:
    """The L4 value of ``input-structure-class-v1-freeze-1`` (E nonempty)."""

    reach: str  # "0" or "1+"
    role: str  # "path" or "target"
    kind: str  # entry type value
    chain: str  # "0", "1", "2" or "3+"
    pass_through_prior_symlink: bool  # O-1
    same_path_type_change: bool  # O-4
    hardlink_forward_reference: bool  # O-5
    mode: str  # "default", "non-default" or "special"

    def as_record(self) -> dict[str, object]:
        return {
            "a2": {"reach": self.reach, "role": self.role, "kind": self.kind},
            "a3": self.chain,
            "a4": {
                "o1": self.pass_through_prior_symlink,
                "o4": self.same_path_type_change,
                "o5": self.hardlink_forward_reference,
            },
            "a5": self.mode,
        }


def classify(case: ArchiveCase) -> InputStructureClass | None:
    """L4 class of ``case``; ``None`` means the class "none" (no escape-relevant entry)."""
    if not isinstance(case, ArchiveCase):
        raise ValueError("classify requires an ArchiveCase")
    entries = case.entries
    paths = [_n(entry.path) for entry in entries]
    members = _escape_set(entries, paths)
    if not members:
        return None
    features = []
    for i in members:
        entry = entries[i]
        if _path_escapes(entry, paths[i]):
            reach = 0 if _abs(entry.path) else _reach(0, paths[i])
            features.append((min(reach, 1), _ROLE_RANK["path"], _KIND_RANK[entry.entry_type]))
        if _target_escapes(entry, paths[i]):
            assert entry.link_target is not None
            target = _n(entry.link_target)
            reach = 0 if _abs(entry.link_target) else _reach(0, target)
            features.append((min(reach, 1), _ROLE_RANK["target"], _KIND_RANK[entry.entry_type]))
    reach, role, kind = max(features)
    chain = _chain_length(entries, paths, members)
    o1, o4, o5 = _order_flags(entries, paths, members)
    return InputStructureClass(
        reach="1+" if reach else "0",
        role=next(name for name, rank in _ROLE_RANK.items() if rank == role),
        kind=next(t.value for t, rank in _KIND_RANK.items() if rank == kind),
        chain="3+" if chain >= 3 else str(chain),
        pass_through_prior_symlink=o1,
        same_path_type_change=o4,
        hardlink_forward_reference=o5,
        mode=_mode_class(entries, members),
    )


def class_record(case: ArchiveCase) -> dict[str, object]:
    """The step-record form: classifier id, value (or "none") and a short canonical id."""
    value = classify(case)
    payload: object = NONE if value is None else value.as_record()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "classifier": CLASSIFIER_ID,
        "value": payload,
        "class_id": sha256(canonical.encode("ascii")).hexdigest()[:16],
    }
