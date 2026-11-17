"""input-structure-class-v1-freeze-1 (docs/research/design/input-structure-class-v1.md).

The examples of the document are the cases here; the expected values of the family inputs are the
L4 labels computed by the out-of-repository calibration implementation (same definition, separate
code), so this file also cross-checks the two implementations.
"""

import ast
import os
import random
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.model.archive import ArchiveCase, ArchiveEntry, EntryType
from inodefence.mutator import MutationPolicy, apply_operator, operator_ids
from inodefence.structure_class import CLASSIFIER_ID, NONE, class_record, classify

REG, DIR, HARD, SYM = EntryType.REGULAR, EntryType.DIRECTORY, EntryType.HARDLINK, EntryType.SYMLINK
SRC = Path(__file__).resolve().parents[1] / "src" / "inodefence"


def case(*items: tuple) -> ArchiveCase:
    entries = []
    for kind, path, target in items:
        content = b"" if kind == REG else None
        mode = 0o777 if kind == SYM else 0o644
        entries.append(ArchiveEntry(path, kind, content=content, link_target=target, mode=mode))
    return ArchiveCase(tuple(entries))


def label(value: ArchiveCase) -> Any:
    return class_record(value)["value"]


def l4(reach, role, kind, chain, o1=False, o4=False, o5=False, mode="default"):
    return {
        "a2": {"reach": reach, "role": role, "kind": kind},
        "a3": chain,
        "a4": {"o1": o1, "o4": o4, "o5": o5},
        "a5": mode,
    }


# Family inputs (#509 predicates, disjoint version) with the calibration implementation's L4 labels.
FAMILY_CASES = {
    "L1-escape": [
        (
            case((REG, "a.txt", None), (HARD, "b.txt", "../outside/s.dat")),
            l4("1+", "target", "hardlink", "0"),
        ),
        (
            case((REG, "a.txt", None), (HARD, "b.txt", "/outside/s.dat")),
            l4("0", "target", "hardlink", "0"),
        ),
    ],
    "L1-escape-sym": [
        (
            case((REG, "a.txt", None), (SYM, "b.txt", "../outside/s.dat")),
            l4("1+", "target", "symlink", "1"),
        ),
    ],
    "L1-cwd": [
        (case((REG, "a.txt", None), (HARD, "b.txt", "outside/s.dat")), NONE),
    ],
    "L2-chain": [
        (
            case((SYM, "l1", "l2"), (SYM, "l2", "../outside"), (REG, "l1/x", None)),
            l4("1+", "target", "symlink", "2", o1=True),
        ),
    ],
    "L2-typeswap": [
        (
            case((DIR, "d", None), (SYM, "d", "../outside"), (REG, "d/x", None)),
            l4("1+", "target", "symlink", "1", o1=True),
        ),
    ],
    "O1-order": [
        (
            case((SYM, "d", "../outside"), (REG, "d/x", None)),
            l4("1+", "target", "symlink", "1", o1=True),
        ),
    ],
}


@pytest.mark.parametrize(
    ("family", "index"),
    [(family, i) for family, items in FAMILY_CASES.items() for i in range(len(items))],
)
def test_family_inputs_match_the_calibration_labels(family: str, index: int) -> None:
    value, expected = FAMILY_CASES[family][index]
    assert label(value) == expected


def test_pairwise_family_separation_and_the_preannounced_pair() -> None:
    labels = {
        family: {repr(label(value)) for value, _ in items} for family, items in FAMILY_CASES.items()
    }
    distinct = ["L1-escape", "L1-escape-sym", "L1-cwd", "L2-chain", "O1-order"]
    for i, a in enumerate(distinct):
        for b in distinct[i + 1 :]:
            assert not labels[a] & labels[b], (a, b)
    # Pre-announced condition of the frozen document: typeswap and O1-order share a class under
    # freeze-1 (rule 6 would separate them and is a separate classifier id).
    assert labels["L2-typeswap"] == labels["O1-order"]


def test_document_order_pattern_examples() -> None:
    # O-1 pass-through of an earlier symlink, O-4 same-path type change, O-5 forward reference,
    # each inside an escaping structure so that E contains both entries.
    o1 = label(case((SYM, "d", "../t"), (REG, "d/f", None)))
    assert o1 != NONE and o1["a4"] == {"o1": True, "o4": False, "o5": False}
    o4 = label(case((REG, "../a", None), (SYM, "../a", "../t")))
    assert o4 != NONE and o4["a4"]["o4"] is True
    o5 = label(case((HARD, "h", "../b"), (REG, "../b", None)))
    assert o5 != NONE and o5["a4"]["o5"] is True
    # O-2 and O-3 are not part of L4: a duplicate path or a child before its parent adds nothing.
    plain = label(case((SYM, "d", "../t"), (REG, "d/f", None)))
    duplicate = label(case((SYM, "d", "../t"), (REG, "d/f", None), (REG, "d/f", None)))
    assert duplicate == plain


def test_document_link_form_examples() -> None:
    # Draft 1 section 4 examples, at L4: path "a/l" -> "../x" escapes from the root lexically?
    # No: reach(0, ["..","x"]) = 1 -> escaping target; "l" -> "x/y" is not an escape; "/x" is.
    assert label(case((SYM, "a/l", "../x")))["a2"] == {
        "reach": "1+",
        "role": "target",
        "kind": "symlink",
    }
    assert label(case((SYM, "l", "x/y"))) == NONE
    assert label(case((SYM, "l", "/x")))["a2"] == {
        "reach": "0",
        "role": "target",
        "kind": "symlink",
    }


def test_strength_order_picks_the_single_strongest_feature() -> None:
    # reach first: a path escape with reach 1 beats an absolute target (reach 0).
    value = label(case((SYM, "l", "/x"), (REG, "../p", None)))
    assert value["a2"] == {"reach": "1+", "role": "path", "kind": "regular"}
    # role next: target beats path at the same reach.
    value = label(case((REG, "../p", None), (SYM, "l", "../x")))
    assert value["a2"]["role"] == "target"
    # kind last: hardlink beats symlink at the same reach and role.
    value = label(case((SYM, "l", "../x"), (HARD, "h", "../y")))
    assert value["a2"]["kind"] == "hardlink"


def test_mode_axis_has_three_values() -> None:
    base = case((SYM, "d", "../t"), (REG, "d/f", None))
    entries = base.entries
    nondefault = ArchiveCase((entries[0], replace(entries[1], mode=0o600)))
    special = ArchiveCase((entries[0], replace(entries[1], mode=0o4755)))
    assert label(base)["a5"] == "default"
    assert label(nondefault)["a5"] == "non-default"
    assert label(special)["a5"] == "special"


def _random_cases(count: int, seed: int) -> list[ArchiveCase]:
    rng = random.Random(seed)
    policy = MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE
    seeds = minimal_seed_corpus()
    out = []
    for _ in range(count):
        current = rng.choice(seeds)
        for _ in range(rng.randint(1, 6)):
            op = rng.choice(operator_ids(policy))
            current = apply_operator(
                current, rng, policy, op, extra_components=("outside", "sentinel")
            ).child_case
        out.append(current)
    return out


def _rename(value: ArchiveCase, mapping: dict[str, str]) -> ArchiveCase:
    def ren(text: str | None) -> str | None:
        if text is None:
            return None
        return "/".join(mapping.get(part, part) for part in text.split("/"))

    return ArchiveCase(
        tuple(replace(e, path=ren(e.path), link_target=ren(e.link_target)) for e in value.entries)
    )


def test_invariant_under_consistent_renaming() -> None:
    rng = random.Random(4242)
    for value in _random_cases(200, 777):
        names = sorted(
            {
                part
                for e in value.entries
                for text in (e.path, e.link_target or "")
                for part in text.split("/")
                if part not in ("", ".", "..")
            }
        )
        for _ in range(5):
            fresh = [f"n{rng.randrange(10**9)}x{i}" for i in range(len(names))]
            assert class_record(
                _rename(value, dict(zip(names, fresh, strict=True)))
            ) == class_record(value)


def test_invariant_under_unrelated_entries() -> None:
    rng = random.Random(5)
    checked = 0
    for value in _random_cases(200, 31):
        if classify(value) is None:
            continue
        kind = rng.choice((REG, DIR))
        extra = ArchiveEntry(
            f"zz{rng.randrange(10**6)}/unrelated",
            kind,
            content=b"x" if kind == REG else None,
        )
        position = rng.randrange(len(value.entries) + 1)
        grown = ArchiveCase(value.entries[:position] + (extra,) + value.entries[position:])
        assert class_record(grown) == class_record(value)
        checked += 1
    assert checked > 20


def test_content_does_not_matter() -> None:
    value = case((SYM, "d", "../t"), (REG, "d/f", None))
    changed = ArchiveCase((value.entries[0], replace(value.entries[1], content=b"other")))
    assert class_record(changed) == class_record(value)


def test_record_form_and_none() -> None:
    record = class_record(case((REG, "a", None)))
    assert record["classifier"] == CLASSIFIER_ID == "input-structure-class-v1-freeze-1"
    assert record["value"] == NONE and len(str(record["class_id"])) == 16


def test_class_id_is_independent_of_hash_seed() -> None:
    code = (
        "from inodefence.structure_class import class_record\n"
        "from inodefence.model.archive import ArchiveCase, ArchiveEntry, EntryType\n"
        "c = ArchiveCase((ArchiveEntry('d', EntryType.SYMLINK, link_target='../t', mode=0o777),"
        " ArchiveEntry('d/f', EntryType.REGULAR, content=b'')))\n"
        "print(class_record(c)['class_id'])\n"
    )
    outputs = set()
    for hash_seed in ("0", "17"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed)
        done = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
        )
        outputs.add(done.stdout.strip())
    assert len(outputs) == 1


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_classifier_imports_only_the_archive_model() -> None:
    inodefence = {
        name for name in _imports(SRC / "structure_class.py") if name.startswith("inodefence")
    }
    assert inodefence == {"inodefence.model.archive"}


def test_no_search_judgement_or_mutation_module_imports_the_classifier() -> None:
    forbidden_dirs = ("oracle", "feedback", "mutator", "observer", "targets", "evaluation")
    offenders = []
    for directory in forbidden_dirs:
        for path in (SRC / directory).rglob("*.py"):
            if any("structure_class" in name for name in _imports(path)):
                offenders.append(str(path))
    for name in ("effect_campaign.py", "effect_scheduler.py", "mutation_scheduler.py"):
        if any("structure_class" in imported for imported in _imports(SRC / name)):
            offenders.append(name)
    assert offenders == []
