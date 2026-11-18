"""FS-resolution routing model on synthetic step records (no run, no host filesystem use).

Each fixture is a general structure (no route, a route inside the root, a chained route that
leaves it, reversed order, an overwrite, a failed symlink, a truncated step, a loop, a growing
chain, a dangling link), not any advisory's paths or template.
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pytest
from scripts.analysis import fs_routing_model as fsm

POLICY = fsm.POLICIES["node-tar-7.5.7"]


def _entry(path: str, kind: str, target: str | None = None) -> dict:
    return {"entry_index": 0, "path": path, "type": kind, "link_target": target}


def _event(index: int, op: str, start: int, path: str, *, outcome: str = "succeeded") -> dict:
    return {
        "entry_index": index,
        "start_sequence": start,
        "completion_sequence": start + 1,
        "operation": op,
        "outcome": outcome,
        "paths": [{"path": path}],
    }


def _step(entries: list[dict], events: list[dict], *, truncated: bool = False, oracle=None):
    for index, entry in enumerate(entries):
        entry["entry_index"] = index
    return {
        "outcome": "executed",
        "feedback": {"trace_termination": "success"},
        "oracle": oracle or {"C0": False, "C1": False, "C2": False},
        "trace": {
            "entries": entries,
            "effect_events": events,
            "effect_events_truncated": truncated,
        },
    }


def _model(step: dict) -> fsm.StepModel:
    return fsm.model_step(step, POLICY)


# Two symlinks and one hardlink: the shell population.
def _chain_escape(order=(10, 20, 30), sym_outcome="succeeded") -> dict:
    """l1 -> ..  (extract/l1 points at the sandbox root); l2 -> l1/outside; hardlink h -> l2/obj.
    Resolution: extract/l2 -> extract/l1/outside/obj -> (l1 is "..") -> outside/obj: EXTERNAL."""
    entries = [
        _entry("l1", "symlink", ".."),
        _entry("l2", "symlink", "l1/outside"),
        _entry("h", "hardlink", "l2/obj"),
    ]
    events = [
        _event(0, "symlink", order[0], "extract/l1", outcome=sym_outcome),
        _event(1, "symlink", order[1], "extract/l2"),
        _event(2, "link", order[2], "extract/h"),
    ]
    return _step(entries, events)


def test_no_symlink_on_the_path_is_no_route() -> None:
    step = _step(
        [
            _entry("f", "file"),
            _entry("s1", "symlink", "f"),
            _entry("s2", "symlink", "f"),
            _entry("h", "hardlink", "f"),
        ],
        [
            _event(0, "open", 1, "extract/f"),
            _event(1, "symlink", 3, "extract/s1"),
            _event(2, "symlink", 5, "extract/s2"),
            _event(3, "link", 7, "extract/h"),
        ],
    )
    result = _model(step)
    assert (result.shell, result.routes, result.escape_zone) == (True, False, "none")


def test_a_route_that_stays_inside_the_root() -> None:
    step = _step(
        [
            _entry("d/f", "file"),
            _entry("s", "symlink", "d"),
            _entry("t", "symlink", "d"),
            _entry("h", "hardlink", "s/f"),
        ],
        [
            _event(0, "open", 1, "extract/d/f"),
            _event(1, "symlink", 3, "extract/s"),
            _event(2, "symlink", 5, "extract/t"),
            _event(3, "link", 7, "extract/h"),
        ],
    )
    result = _model(step)
    assert (result.routes, result.escape_zone, result.unresolvable) == (True, "none", ())


def test_a_chained_route_that_leaves_the_root_is_external() -> None:
    result = _model(_chain_escape())
    assert (result.routes, result.escape_zone, result.order_basis) == (True, "EXTERNAL", "events")


def test_dotdot_in_the_link_target_folds_lexically_before_symlinks() -> None:
    """Answer 5: path.resolve() folds "s/../x" to "x" before the disk is consulted, so s is never
    followed. A purely physical walk would follow s and land elsewhere."""
    step = _step(
        [
            _entry("deep/dir/f", "file"),
            _entry("deep/x", "file"),
            _entry("x", "file"),
            _entry("s", "symlink", "deep/dir"),
            _entry("t", "symlink", "deep"),
            _entry("h", "hardlink", "s/../x"),
        ],
        [
            _event(0, "open", 1, "extract/deep/dir/f"),
            _event(1, "open", 3, "extract/deep/x"),
            _event(2, "open", 5, "extract/x"),
            _event(3, "symlink", 7, "extract/s"),
            _event(4, "symlink", 9, "extract/t"),
            _event(5, "link", 11, "extract/h"),
        ],
    )
    assert _model(step).routes is False


def test_a_route_to_the_sandbox_root_is_harness() -> None:
    step = _step(
        [
            _entry("up", "symlink", ".."),
            _entry("x", "symlink", "up"),
            _entry("h", "hardlink", "up/archive/obj"),
        ],
        [
            _event(0, "symlink", 1, "extract/up"),
            _event(1, "symlink", 3, "extract/x"),
            _event(2, "link", 5, "extract/h"),
        ],
    )
    assert _model(step).escape_zone == "HARNESS"


def test_a_symlink_created_after_the_link_is_not_a_route() -> None:
    result = _model(_chain_escape(order=(10, 40, 30)))  # l2 created after the link
    assert (result.routes, result.order_mismatch) == (False, True)


def test_a_failed_symlink_is_not_on_disk() -> None:
    """l1's creation failed, so following l2 lands on a missing extract/l1: dangling, never an
    escape (answer 4: only symlinks with a succeeded creation are on disk)."""
    result = _model(_chain_escape(sym_outcome="access_denied"))
    assert result.unresolvable == ("dangling",)
    assert (result.routes, result.escape_zone) == (False, "none")


def test_without_a_link_event_the_declared_order_stands_in() -> None:
    step = _chain_escape()
    step["trace"]["effect_events"] = step["trace"]["effect_events"][:2]  # the link was refused
    result = _model(step)
    assert (result.routes, result.escape_zone, result.order_basis) == (
        True,
        "EXTERNAL",
        "entry_index",
    )


def test_a_later_entry_on_the_same_path_takes_its_place() -> None:
    """Follow-up (나): the occupant is the last succeeded entry there before the link."""
    step = _chain_escape()
    entries = step["trace"]["entries"]
    entries.insert(2, {"entry_index": 2, "path": "l2", "type": "file", "link_target": None})
    entries[3]["entry_index"] = 3
    step["trace"]["effect_events"] = [
        _event(0, "symlink", 10, "extract/l1"),
        _event(1, "symlink", 20, "extract/l2"),
        _event(2, "open", 25, "extract/l2"),  # a regular file replaces l2
        _event(3, "link", 30, "extract/h"),
    ]
    assert _model(step).routes is False


def test_a_symlink_over_a_symlink_routes_through_the_newer_one() -> None:
    """Follow-up (나): symlink over symlink -- the replacement occupies the path."""
    step = _step(
        [
            _entry("l1", "symlink", ".."),
            _entry("l2", "symlink", "inside"),
            _entry("l2", "symlink", "l1/outside"),
            _entry("inside/obj", "file"),
            _entry("h", "hardlink", "l2/obj"),
        ],
        [
            _event(3, "open", 1, "extract/inside/obj"),
            _event(0, "symlink", 3, "extract/l1"),
            _event(1, "symlink", 5, "extract/l2"),
            _event(2, "symlink", 7, "extract/l2"),
            _event(4, "link", 9, "extract/h"),
        ],
    )
    assert _model(step).escape_zone == "EXTERNAL"


def test_a_truncated_step_is_judgement_impossible_not_zero() -> None:
    step = _chain_escape()
    step["trace"]["effect_events_truncated"] = True
    result = _model(step)
    assert (result.shell, result.judgeable) == (True, False)


@pytest.mark.parametrize(
    ("targets", "kind"),
    [
        (("b", "a"), "loop"),  # a -> b, b -> a
        (("a/x", "a/y"), "limit"),  # a -> a/x keeps growing
    ],
)
def test_loops_and_limits_are_counted_apart(targets: tuple[str, str], kind: str) -> None:
    step = _step(
        [
            _entry("a", "symlink", targets[0]),
            _entry("b", "symlink", targets[1]),
            _entry("h", "hardlink", "a/f"),
        ],
        [
            _event(0, "symlink", 1, "extract/a"),
            _event(1, "symlink", 3, "extract/b"),
            _event(2, "link", 5, "extract/h"),
        ],
    )
    result = _model(step)
    assert result.unresolvable == (kind,)
    assert (result.routes, result.escape_zone) == (False, "none")


def test_a_dangling_link_is_counted_apart() -> None:
    step = _step(
        [
            _entry("d", "symlink", "missing"),
            _entry("e", "symlink", "d"),
            _entry("h", "hardlink", "d/f"),
        ],
        [
            _event(0, "symlink", 1, "extract/d"),
            _event(1, "symlink", 3, "extract/e"),
            _event(2, "link", 5, "extract/h"),
        ],
    )
    assert _model(step).unresolvable == ("dangling",)


def test_not_a_shell_step() -> None:
    step = _step([_entry("s", "symlink", "x"), _entry("h", "hardlink", "s")], [])
    assert _model(step).shell is False


# -- destination (follow-up (가)) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a/../b", ("b",)),  # folded inside the root: applied
        ("/abs/x", ("abs", "x")),  # leading "/" stripped
        ("C:x/y", ("x", "y")),  # a drive stripped
        ("//host/share/z", ("z",)),  # a UNC prefix stripped
        ("../x", None),  # leaves the root: skipped
        ("a/../../x", None),
    ],
)
def test_destination_rules(path: str, expected) -> None:
    assert fsm.destination(path, POLICY.destination_rules) == expected


def test_the_destination_through_a_symlink_is_its_own_column() -> None:
    step = _step(
        [
            _entry("up", "symlink", ".."),
            _entry("x", "symlink", "up"),
            _entry("f", "file"),
            _entry("up/outside/new", "hardlink", "f"),
        ],
        [
            _event(2, "open", 1, "extract/f"),
            _event(0, "symlink", 3, "extract/up"),
            _event(1, "symlink", 5, "extract/x"),
            _event(3, "link", 7, "extract/up/outside/new"),
        ],
    )
    result = _model(step)
    assert (result.routes, result.dest) == (False, "routes:EXTERNAL")


# -- the cell ------------------------------------------------------------------------------------


def _cell(tmp_path: Path, steps: list[dict], *, version: str = "7.5.7") -> Path:
    folder = tmp_path / "cell" / "seed-1" / "target-explore"
    folder.mkdir(parents=True)
    name = "inodefence-effect-explore-run"
    with gzip.open(folder / f"{name}.steps.jsonl.gz", "wt", encoding="utf-8") as stream:
        for step in steps:
            stream.write(json.dumps(step) + "\n")
    (folder / f"{name}.json").write_text(json.dumps({"node_tar_version": version}))
    return tmp_path / "cell"


def _run(capsys, *argv: str) -> tuple[int, dict]:
    code = fsm.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def test_cell_counts_with_inferred_and_observed_columns(tmp_path: Path, capsys) -> None:
    escape = _chain_escape()
    escape["oracle"] = {"C0": False, "C1": True, "C2": False}
    truncated = _chain_escape()
    truncated["trace"]["effect_events_truncated"] = True
    plain = _step([_entry("f", "file")], [])
    code, out = _run(
        capsys, str(_cell(tmp_path, [escape, truncated, plain])), "--policy", "node-tar-7.5.7"
    )
    assert code == 0
    assert out["totals"] == {"steps": 3, "shell": 2, "판정 불가": 1}
    assert out["additive_detectors"] == "not recorded"
    assert out["inferred"].startswith("[inferred]")
    assert out["columns"]["observed"] == ["outcome", "oracle_C0", "oracle_C1", "oracle_C2"]
    row = next(r for r in out["rows"] if r["fs_routes"])
    assert (row["fs_escape_zone"], row["oracle_C1"], row["steps"]) == ("EXTERNAL", True, 1)
    assert next(r for r in out["rows"] if not r["judgeable"])["steps"] == 1


def test_no_path_string_reaches_the_output(tmp_path: Path, capsys) -> None:
    code, out = _run(capsys, str(_cell(tmp_path, [_chain_escape()])), "--policy", "node-tar-7.5.7")
    text = json.dumps(out)
    for fragment in ("l1/outside", "l2/obj", "extract/l1", "outside/obj"):
        assert fragment not in text


def test_a_cell_of_another_version_is_refused(tmp_path: Path, capsys) -> None:
    cell = _cell(tmp_path, [_chain_escape()], version="7.5.11")
    code, out = _run(capsys, str(cell), "--policy", "node-tar-7.5.7")
    assert code == 2 and "policy node-tar-7.5.7 is for node-tar 7.5.7" in out["error"]


def test_the_policy_has_no_default(tmp_path: Path, capsys) -> None:
    assert fsm.main([str(_cell(tmp_path, [_chain_escape()]))]) == 2


def test_a_cell_without_its_report_is_refused(tmp_path: Path, capsys) -> None:
    cell = _cell(tmp_path, [_chain_escape()])
    next(cell.rglob("*.json")).unlink()
    code, out = _run(capsys, str(cell), "--policy", "node-tar-7.5.7")
    assert code == 2 and "no engine report" in out["error"]


def test_the_model_touches_no_host_filesystem(tmp_path: Path, capsys, monkeypatch) -> None:
    """Only an in-memory tree: no symlink, link, readlink or realpath on the host."""
    cell = _cell(tmp_path, [_chain_escape()])

    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("the model used the host filesystem")

    for name in ("symlink", "link", "readlink", "unlink", "rename", "mkdir"):
        monkeypatch.setattr(os, name, forbidden)
    monkeypatch.setattr(os.path, "realpath", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(Path, "symlink_to", forbidden)
    monkeypatch.setattr(Path, "hardlink_to", forbidden)
    code, out = _run(capsys, str(cell), "--policy", "node-tar-7.5.7")
    assert code == 0 and out["totals"]["shell"] == 1
