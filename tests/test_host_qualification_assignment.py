"""replicate-v1 and participants: host qualification runs and one-host participation."""

import json
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0
from scripts import make_seed_assignment, merge_host_indexes

from inodefence.evaluation.rds_preregistration import (
    PreregistrationFormatError,
    load_preregistration,
)
from inodefence.evaluation.seed_assignment import (
    RULE_ALTERNATE,
    RULE_REPLICATE,
    RULE_RH_PROPORTIONAL,
    SeedAssignmentError,
    assignment_bytes,
    parse_seed_assignment,
    rule_problems,
    split_alternate,
    split_by_rate,
    split_replicate,
)
from test_run_exp0 import BEFORE, TARGET_IMAGES, _deadline_setup, _fake_runner, _index
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine
from test_two_host_split import SEEDS, _host_args, _host_keys, _two_host_file

ORACLE_SENTINELS = ("contract_violated", "oracle", "c1_identity", "hit", "t_first")


# ---- documents ------------------------------------------------------------------------------


def test_replicate_gives_every_participant_every_seed() -> None:
    document = split_replicate(SEEDS)
    assert document["hosts"] == {"HOST1": list(SEEDS), "HOST2": list(SEEDS)}
    parsed = parse_seed_assignment(assignment_bytes(document), SEEDS)
    assert parsed.replicated and parsed.all_seeds() == SEEDS
    with pytest.raises(SeedAssignmentError, match="every participant"):
        bad = {**document, "hosts": {"HOST1": list(SEEDS), "HOST2": list(SEEDS[:2])}}
        parse_seed_assignment(assignment_bytes(bad), SEEDS)
    # Overlap is still refused for the splitting rules.
    with pytest.raises(SeedAssignmentError, match="assigned to HOST1 and HOST2"):
        parse_seed_assignment(assignment_bytes({**document, "rule": RULE_ALTERNATE}), SEEDS)


def test_omitted_participants_keep_the_two_host_bytes() -> None:
    assert "participants" not in split_alternate(SEEDS)
    assert "participants" not in split_by_rate(SEEDS, 4, {"HOST1": "1", "HOST2": "1"})
    assert parse_seed_assignment(assignment_bytes(split_alternate(SEEDS)), SEEDS).participants == (
        "HOST1",
        "HOST2",
    )


@pytest.mark.parametrize("host", ["HOST1", "HOST2"])
def test_one_participant_gets_every_seed(host: str) -> None:
    other = "HOST2" if host == "HOST1" else "HOST1"
    for document in (
        split_alternate(SEEDS, [host]),
        split_by_rate(SEEDS, 4, {host: "123.5"}, [host]),
        split_replicate(SEEDS, [host]),
    ):
        assert document["hosts"] == {host: list(SEEDS), other: []}
        assert document["participants"] == [host]
        parsed = parse_seed_assignment(assignment_bytes(document), SEEDS)
        assert parsed.participants == (host,) and parsed.seeds_for(other) == ()


def test_participants_are_checked() -> None:
    with pytest.raises(SeedAssignmentError, match="ordered subset"):
        split_alternate(SEEDS, ["HOST3"])
    with pytest.raises(SeedAssignmentError, match="ordered subset"):
        split_alternate(SEEDS, ["HOST2", "HOST1"])
    doc = split_alternate(SEEDS, ["HOST1"])
    doc["hosts"]["HOST2"] = [9002]
    with pytest.raises(SeedAssignmentError, match="does not take part"):
        parse_seed_assignment(assignment_bytes(doc), SEEDS)
    with pytest.raises(SeedAssignmentError, match="rates are needed for exactly"):
        split_by_rate(SEEDS, 4, {"HOST1": "1", "HOST2": "1"}, ["HOST1"])


def test_rule_problems_regenerate_with_participants() -> None:
    one = assignment_bytes(split_alternate(SEEDS, ["HOST2"]))
    sha = parse_seed_assignment(one, SEEDS).sha256
    ok: dict[str, Any] = {"registered_seeds": SEEDS, "go_decision": None}
    assert rule_problems(one, rule=RULE_ALTERNATE, registered_sha256=sha, **ok) == []
    rep = assignment_bytes(split_replicate(SEEDS))
    rep_sha = parse_seed_assignment(rep, SEEDS).sha256
    assert rule_problems(rep, rule=RULE_REPLICATE, registered_sha256=rep_sha, **ok) == []
    assert rule_problems(rep, rule=RULE_REPLICATE, registered_sha256=sha, **ok)
    holdout = assignment_bytes(split_by_rate(SEEDS, 4, {"HOST1": "50"}, ["HOST1"]))
    go = {"participants": ["HOST1"], "rates_exec_per_hour": {"HOST1": "50"}}
    kwargs: dict[str, Any] = {
        "rule": RULE_RH_PROPORTIONAL,
        "registered_seeds": SEEDS,
        "registered_sha256": None,
    }
    assert rule_problems(holdout, go_decision=go, **kwargs) == []
    # Without the participants field the GO file means both hosts, and HOST2's rate is missing.
    assert rule_problems(holdout, go_decision={"rates_exec_per_hour": {"HOST1": "50"}}, **kwargs)


# ---- registration --------------------------------------------------------------------------


def _train_only(prereg: Path) -> None:
    lines = prereg.read_text(encoding="utf-8").splitlines(keepends=True)
    keep = [
        line
        for line in lines
        if "node-tar-7.9.9" not in line and not line.startswith(("confirmatory_", "multiplicity"))
    ]
    prereg.write_text("".join(keep), encoding="utf-8")


def _replicate_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, train_only: bool = True
) -> tuple[Path, list[str], Path]:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    prereg = Path(args[args.index("--preregistration") + 1])
    if train_only:
        _train_only(prereg)
    data = assignment_bytes(split_replicate(SEEDS))
    _two_host_file(prereg, _host_keys(RULE_REPLICATE, parse_seed_assignment(data, SEEDS).sha256))
    assignment = tmp_path / "replicate.json"
    assignment.write_bytes(data)
    monkeypatch.setattr(run_exp0, "docker_engine_version", lambda context: "29.8.0")
    return out, args, assignment


def test_replicate_is_refused_in_an_exp_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, args, _ = _replicate_setup(tmp_path, monkeypatch, train_only=False)
    with pytest.raises(PreregistrationFormatError, match="replicate-v1 is for host qualification"):
        load_preregistration(Path(args[args.index("--preregistration") + 1]))


def test_replicate_needs_a_registered_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    prereg = Path(args[args.index("--preregistration") + 1])
    _train_only(prereg)
    _two_host_file(prereg, _host_keys(RULE_REPLICATE, None))
    with pytest.raises(PreregistrationFormatError, match="needs seed_assignment_sha256"):
        load_preregistration(prereg)


# ---- launcher and merge --------------------------------------------------------------------


def _run(
    args: list[str], out: Path, host: str, assignment: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    assert run_exp0.main(
        _host_args(args, out, host, assignment, "2" if host == "HOST1" else "1")
    ) in (0, 1)
    return out.parent / f"{out.name}-{host}"


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_both_hosts_run_every_seed_and_are_compared_never_pooled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, assignment = _replicate_setup(tmp_path, monkeypatch)
    prereg = Path(args[args.index("--preregistration") + 1])
    host1 = _run(args, out, "HOST1", assignment, monkeypatch)
    host2 = _run(args, out, "HOST2", assignment, monkeypatch)
    for host_dir in (host1, host2):
        assert sorted({c["seed"] for c in _index(host_dir)["cells"]}) == list(SEEDS)
    base = [
        "--preregistration",
        str(prereg),
        "--seed-assignment",
        str(assignment),
        "--host",
        f"HOST1={host1}",
        "--host",
        f"HOST2={host2}",
        "--output",
        str(tmp_path / "m"),
    ]
    assert merge_host_indexes.main(base) == 2  # pooling refused
    assert not (tmp_path / "m" / "summaries" / "index.json").exists()
    assert merge_host_indexes.main([*base, "--compare"]) == 0
    text = (tmp_path / "m" / "compare.json").read_text(encoding="utf-8")
    report = json.loads(text)
    assert report["all_identical"] is True
    assert set(report["cells"]) == {c["run_id"] for c in _index(host1)["cells"]}
    for word in ORACLE_SENTINELS:
        assert word not in text
    for case_id in {
        json.loads(line)["case_id"]
        for line in next(host1.rglob("*.steps.jsonl")).read_text().splitlines()
    }:
        assert case_id not in text  # no input identifier leaves the steps files either


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_compare_is_only_for_replicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_two_host_split import _setup

    out, args, assignment = _setup(tmp_path, monkeypatch)
    prereg = Path(args[args.index("--preregistration") + 1])
    host1 = _run(args, out, "HOST1", assignment, monkeypatch)
    argv = [
        "--preregistration",
        str(prereg),
        "--seed-assignment",
        str(assignment),
        "--host",
        f"HOST1={host1}",
        "--output",
        str(tmp_path / "m"),
        "--compare",
    ]
    assert merge_host_indexes.main(argv) == 2


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_one_participant_runs_alone_and_the_other_host_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    prereg = Path(args[args.index("--preregistration") + 1])
    data = assignment_bytes(split_alternate(SEEDS, ["HOST1"]))
    _two_host_file(prereg, _host_keys(RULE_ALTERNATE, parse_seed_assignment(data, SEEDS).sha256))
    assignment = tmp_path / "one.json"
    assignment.write_bytes(data)
    monkeypatch.setattr(run_exp0, "docker_engine_version", lambda context: "29.8.0")
    assert run_exp0.main([*_host_args(args, out, "HOST2", assignment, "1"), "--dry-run"]) == 2
    assert "takes no part in this assignment" in capsys.readouterr().out
    host1 = _run(args, out, "HOST1", assignment, monkeypatch)
    assert sorted({c["seed"] for c in _index(host1)["cells"]}) == list(SEEDS)
    merged = tmp_path / "m"
    argv = [
        "--preregistration",
        str(prereg),
        "--seed-assignment",
        str(assignment),
        "--host",
        f"HOST1={host1}",
        "--output",
        str(merged),
    ]
    assert merge_host_indexes.main(argv) == 0
    assert _index(merged)["merge"]["complete"] is True


def test_holdout_generator_needs_an_explicit_rate_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_two_host_split import _setup

    _, args, _ = _setup(tmp_path, monkeypatch, rule=RULE_RH_PROPORTIONAL)
    prereg = Path(args[args.index("--preregistration") + 1])
    go = tmp_path / "go1.json"
    go.write_text(json.dumps({"rates_exec_per_hour": {"HOST1": "42"}}), encoding="utf-8")
    out = tmp_path / "a.json"
    base = [
        "--preregistration",
        str(prereg),
        "--rule",
        RULE_RH_PROPORTIONAL,
        "--go-decision",
        str(go),
        "--participants",
        "HOST1",
        "--out",
        str(out),
    ]
    assert make_seed_assignment.main(base) == 2  # no --rate-source
    assert (
        make_seed_assignment.main(
            [*base, "--rate-source", "HOST1=qualification-throughput", "--record-in-go-decision"]
        )
        == 0
    )
    recorded = json.loads(go.read_text())
    assert recorded["participants"] == ["HOST1"]
    assert recorded["rate_sources"] == {"HOST1": "qualification-throughput"}
    assert json.loads(out.read_text())["hosts"]["HOST2"] == []
