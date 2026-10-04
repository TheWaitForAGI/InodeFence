"""Phase-4B acceptance witnesses; encode in memory or use the trusted reference.

Run explicitly with PYTHONPATH=src python -m pytest -q <this file>. These are
current-code acceptance checks, unlike the frozen Phase-1 defect witnesses.
"""

import random
from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.builder import build_tar
from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.feedback import Corpus, state_signature, violation_fingerprints
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ChangeField,
    EntryType,
    ObjectSnapshot,
    ObjectType,
    SnapshotPhase,
    StateChange,
    StateSnapshot,
)
from inodefence.mutator import mutate
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts
from inodefence.targets import PythonTarfileTarget


@pytest.mark.parametrize("kind", tuple(EntryType))
def test_raw_ustar_boundary_matrix_is_lossless_or_explicitly_rejected(kind: EntryType) -> None:
    # Adjacent byte lengths, multibyte code points and raw slash spellings. No
    # tarfile reader is used: readers can themselves strip directory suffixes.
    paths = {"/", "//", "a//b", "./a", "a/../b", "dir//"}
    for unit in ("a", "é", "한"):
        for size in range(32, 104):
            name = unit * size
            paths.update((name, "/" + name, "//" + name, "dir/" + name, name + "//"))
    for prefix_size in (0, 1, 99, 100, 154, 155, 156):
        for name_size in (0, 1, 99, 100, 101):
            paths.add("p" * prefix_size + "/" + "n" * name_size)
            paths.add("p" * prefix_size + "//" + "n" * name_size)
    encoded: dict[bytes, str] = {}
    for path in sorted(paths):
        case = ArchiveCase(
            (
                ArchiveEntry(
                    path,
                    kind,
                    content=b"inert" if kind == EntryType.REGULAR else None,
                    link_target="normal"
                    if kind in (EntryType.HARDLINK, EntryType.SYMLINK)
                    else None,
                ),
            )
        )
        try:
            archive = build_tar(case)
        except ValueError as error:
            assert str(error).startswith("entry 0 cannot be represented in USTAR:")
            continue
        name = archive[:100].split(b"\0", 1)[0]
        prefix = archive[345:500].split(b"\0", 1)[0]
        assert (prefix + b"/" + name if prefix else name) == path.encode("utf-8")
        assert archive not in encoded or encoded[archive] == path
        encoded[archive] = path
    # Success coverage is mandatory as well as explicit rejection coverage.
    assert "/" in encoded.values() and "a//b" in encoded.values()
    assert "p" * 155 + "/" + "n" * 100 in encoded.values()


def regular() -> ObjectSnapshot:
    return ObjectSnapshot(
        "outside/sentinel.txt",
        ObjectType.REGULAR,
        1,
        10,
        1,
        0o600,
        4,
        1000,
        1000,
        10,
        10,
        content_digest=sha256(b"same").hexdigest(),
    )


@pytest.mark.parametrize(
    ("updates", "labels"),
    [
        ({"st_dev": 2}, (ChangeField.IDENTITY,)),
        ({"st_ino": 11}, (ChangeField.IDENTITY,)),
        ({"st_nlink": 2}, (ChangeField.NLINK,)),
        ({"mode": 0o640}, (ChangeField.MODE,)),
        ({"size": 5}, (ChangeField.SIZE,)),
        ({"uid": 1001}, (ChangeField.UID,)),
        ({"gid": 1001}, (ChangeField.GID,)),
        ({"mtime_ns": 11}, (ChangeField.MTIME,)),
        ({"ctime_ns": 11}, (ChangeField.CTIME,)),
        ({"content_digest": sha256(b"diff").hexdigest()}, (ChangeField.CONTENT,)),
        (
            {"object_type": ObjectType.DIRECTORY, "content_digest": None},
            (ChangeField.OBJECT_TYPE, ChangeField.CONTENT),
        ),
        (
            {"size": 5, "mode": 0o640, "uid": 1001, "ctime_ns": 11},
            (ChangeField.MODE, ChangeField.SIZE, ChangeField.UID, ChangeField.CTIME),
        ),
    ],
)
def test_all_raw_differences_have_exact_labels(
    updates: dict[str, object], labels: tuple[ChangeField, ...]
) -> None:
    previous = regular()
    current = replace(previous, **updates)
    exact = StateChange(previous.path, previous, current, labels)
    before = StateSnapshot(
        "/var/lib/inodefence/witness", SnapshotPhase.BEFORE, (previous,), (previous.path,)
    )
    after = replace(before, phase=SnapshotPhase.AFTER, objects=(current,))
    assert compare_states(before, after) == (exact,)
    assert evaluate_contracts(before, after)[2].evidence == (exact,)
    # False labels and omissions must fail, including a validly typed tuple.
    incorrect = (ChangeField.EXISTENCE,) if len(labels) == 1 else labels[:-1]
    with pytest.raises(ValueError):
        replace(exact, fields=incorrect)


def test_symlink_text_and_existence_differences_are_exact() -> None:
    previous = replace(
        regular(),
        object_type=ObjectType.SYMLINK,
        content_digest=None,
        symlink_target="../outside/a",
    )
    current = replace(previous, symlink_target="../outside/b")
    before = StateSnapshot(
        "/var/lib/inodefence/witness", SnapshotPhase.BEFORE, (previous,), (previous.path,)
    )
    after = replace(before, phase=SnapshotPhase.AFTER, objects=(current,))
    assert compare_states(before, after) == (
        StateChange(previous.path, previous, current, (ChangeField.SYMLINK_TARGET,)),
    )
    for old, new in ((None, previous), (previous, None)):
        change = StateChange(previous.path, old, new, (ChangeField.EXISTENCE,))
        assert compare_states(
            replace(before, objects=() if old is None else (old,)),
            replace(after, objects=() if new is None else (new,)),
        ) == (change,)


def test_complete_reference_search_trace() -> None:
    seeds = minimal_seed_corpus()
    config = CampaignConfig(random_seed=20261004, execution_budget=6)
    result = run_campaign(seeds, PythonTarfileTarget(), config)
    corpus = Corpus()
    rng = random.Random(config.random_seed)
    for index, step in enumerate(result.steps):
        if index < len(seeds):
            expected = seeds[index]
            assert step.parent_case_id is None
        else:
            parent = corpus.select_case(rng)
            assert step.parent_case_id == parent.case_id
            expected = mutate(parent, rng)
        run = step.result
        assert run.case == expected
        assert run.archive_sha256 == sha256(build_tar(expected)).hexdigest()
        assert run.before.phase == SnapshotPhase.BEFORE
        assert run.after.phase == SnapshotPhase.AFTER
        assert run.changes == compare_states(run.before, run.after)
        assert run.violations == evaluate_contracts(run.before, run.after)
        assert run.signature == state_signature(run.before, run.after)
        assert run.signature.schema_version == 3
        assert all(not verdict.violated for verdict in run.violations)
        assert violation_fingerprints(run.violations) == ()
        assert corpus.consider(run) == step.feedback
    assert corpus.stats == result.final_corpus_stats
    assert tuple(entry.case.case_id for entry in corpus.entries) == result.retained_case_ids
