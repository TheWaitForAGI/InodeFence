"""Versioned protected-component vocabulary and constructive reachability."""

import io
import random
import tarfile
from hashlib import sha256

from inodefence.builder import build_tar
from inodefence.generator import minimal_seed_corpus
from inodefence.model import EntryType
from inodefence.mutator import MutationOperatorId, MutationPolicy, apply_operator, m1_addressing


class ScriptedRandom(random.Random):
    """Consume an exact mutation draw script without retries or hidden choices."""

    def __init__(self, choices=(), ranges=()):
        super().__init__(0)
        self._scripted_choices = iter(choices)
        self._scripted_ranges = iter(ranges)

    def choice(self, seq):
        value = next(self._scripted_choices)
        assert value in seq
        return value

    def randrange(self, start, stop=None, step=1):
        value = next(self._scripted_ranges)
        assert value in range(0, start) if stop is None else value in range(start, stop, step)
        return value


def test_original_benign_hardlink_seed_constructively_reaches_default_sentinel_address():
    parent = minimal_seed_corpus()[2]
    rng = ScriptedRandom(
        choices=(1, False, False, "../", "/", "outside", "sentinel.txt"),
        ranges=(2,),
    )

    attempt = apply_operator(
        parent,
        rng,
        MutationPolicy.M1_PROTECTED_COMPONENTS,
        MutationOperatorId.MUTATE_LINK_TARGET,
    )

    assert attempt.applied
    assert attempt.parent_case_id == parent.case_id
    assert attempt.mutation_policy == MutationPolicy.M1_PROTECTED_COMPONENTS
    hardlinks = tuple(
        entry for entry in attempt.child_case.entries if entry.entry_type == EntryType.HARDLINK
    )
    assert len(hardlinks) == 1
    assert hardlinks[0].link_target == "../outside/sentinel.txt"
    archive = build_tar(attempt.child_case)
    assert sha256(archive).hexdigest() == (
        "2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6"
    )
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as opened:
        assert opened.getmembers()[1].linkname == "../outside/sentinel.txt"


def test_addressing_policy_is_bounded_deterministic_and_builder_compatible():
    for seed in range(32):
        first_rng = random.Random(seed)
        second_rng = random.Random(seed)
        first = minimal_seed_corpus()[seed % 4]
        second = first
        for _ in range(64):
            first = m1_addressing.mutate(first, first_rng)
            second = m1_addressing.mutate(second, second_rng)
            assert first == second
            assert first_rng.getstate() == second_rng.getstate()
            build_tar(first)


def test_escape_hardlink_slot_targets_outside_root_and_reaches_sentinel_name_generically():
    """The escape hardlink slot always escapes extract/ and can reach controlled names.

    Every generated hardlink target begins with a parent-traversal step, so it
    leaves the extraction root. Across seeds the target is assembled from the
    finite controlled vocabulary, so the default sentinel name becomes reachable
    without hardcoding the exact `../outside/sentinel.txt` PoC string.
    """
    parent = minimal_seed_corpus()[2]
    existing_hardlink_targets = {
        entry.link_target for entry in parent.entries if entry.entry_type == EntryType.HARDLINK
    }
    reached_sentinel_name = False
    for seed in range(256):
        attempt = apply_operator(
            parent,
            random.Random(seed),
            MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK,
            MutationOperatorId.ADD_HARDLINK,
        )
        assert attempt.applied
        added = tuple(
            entry
            for entry in attempt.child_case.entries
            if entry.entry_type == EntryType.HARDLINK
            and entry.link_target not in existing_hardlink_targets
        )
        assert added, "the escape slot must insert a new hardlink"
        for entry in added:
            target = entry.link_target
            assert target is not None
            assert target.startswith(".."), "escape target must leave extract/"
            if "sentinel.txt" in target.split("/"):
                reached_sentinel_name = True
    assert reached_sentinel_name


def test_addressing_vocabulary_is_finite_cve_and_target_independent():
    assert m1_addressing.COMPONENTS == (
        "a",
        "b",
        "dir",
        "file",
        "item",
        ".",
        "..",
        "outside",
        "sentinel.txt",
    )
    assert all("cve" not in component.lower() for component in m1_addressing.COMPONENTS)
