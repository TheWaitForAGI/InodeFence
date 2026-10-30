"""Validate the committed boundary-attempt observation frame against the v1 interface spec.

The entry-completion feasibility probe (``decompress_entry_effect_feasibility.py``) runs real
decompress fs-wrapped and records an ``inodefence-boundary-attempt-v1`` frame -- the
minimal, feasible SET-based boundary-attempt signal proposed for the transition/boundary-attempt
gradient (the full ordered, entry-correlated entry-completion boundary is NOT feasible; see that
probe's docstring). This test pins the v1 frame schema and the observed boundary attempts so the
interface the Observation lane wires to does not drift. It reads only committed evidence -- no
Docker -- so it runs in ``make check``. No oracle/model/feedback change; purely additive.
"""

import json
from pathlib import Path

_FRAME = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "experiments"
        / "repro"
        / "evidence"
        / "decompress_entry_effect_feasibility.json"
    ).read_text(encoding="utf-8")
)["frame"]

_ATTEMPT_FIELDS = {
    "operation",
    "created_path",
    "created_region",
    "target_raw",
    "target_resolved_absolute",
    "target_region",
    "aliases_external_object",
    "outcome",
}
_OPERATIONS = {"hardlink", "symlink", "regular", "dir"}
_REGIONS = {"extraction", "external", "harness"}
_OUTCOMES = {"created", "refused", "io_error"}


def _is_boundary_attempt(attempt: dict) -> bool:
    """The gradient's set-based predicate: an op that points an extract/ object outside extract/."""
    return (
        attempt["target_region"] not in (None, "extraction", "n/a")
        or attempt["created_region"] != "extraction"
        or attempt["aliases_external_object"]
    )


def test_v1_frame_conforms_to_the_spec_schema() -> None:
    assert _FRAME["format"] == "inodefence-boundary-attempt-v1"
    assert _FRAME["schema_version"] == 1
    assert isinstance(_FRAME["extractor"], str) and "@" in _FRAME["extractor"]
    assert isinstance(_FRAME["extraction_root_absolute"], str)
    assert isinstance(_FRAME["attempts"], list) and _FRAME["attempts"]
    for attempt in _FRAME["attempts"]:
        assert set(attempt) == _ATTEMPT_FIELDS
        assert attempt["operation"] in _OPERATIONS
        assert attempt["created_region"] in _REGIONS
        assert attempt["target_region"] in _REGIONS | {"n/a"}
        assert attempt["outcome"] in _OUTCOMES
        assert isinstance(attempt["aliases_external_object"], bool)
        assert isinstance(attempt["created_path"], str)
        if attempt["operation"] in {"hardlink", "symlink"}:
            assert isinstance(attempt["target_raw"], str)
        else:
            assert attempt["target_raw"] is None and attempt["target_region"] == "n/a"


def test_the_external_hardlink_and_symlink_are_boundary_attempts() -> None:
    by_op = {a["operation"]: a for a in _FRAME["attempts"]}

    # Hardlink escaping to an external object: target resolves outside extract/, and (the strongest
    # signal) the created extract/ object shares a non-extraction object's inode.
    hardlink = by_op["hardlink"]
    assert hardlink["created_region"] == "extraction"
    assert hardlink["target_region"] == "external"
    assert hardlink["aliases_external_object"] is True
    assert _is_boundary_attempt(hardlink)

    # Symlink whose referent leaves the extraction root: external target, own inode (no aliasing).
    symlink = by_op["symlink"]
    assert symlink["created_region"] == "extraction"
    assert symlink["target_region"] == "external"
    assert symlink["aliases_external_object"] is False
    assert _is_boundary_attempt(symlink)


def test_benign_regular_write_is_not_a_boundary_attempt() -> None:
    regular = next(a for a in _FRAME["attempts"] if a["operation"] == "regular")
    assert regular["created_region"] == "extraction"
    assert regular["target_region"] == "n/a"
    assert regular["aliases_external_object"] is False
    assert not _is_boundary_attempt(regular)


def test_attempt_set_covers_exactly_two_boundary_attempts() -> None:
    boundary = [a for a in _FRAME["attempts"] if _is_boundary_attempt(a)]
    assert len(boundary) == 2
    assert {a["operation"] for a in boundary} == {"hardlink", "symlink"}
