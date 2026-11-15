"""Case replay: TAR reader round trip, request checks, record/rates, input line, driver, status."""

from __future__ import annotations

import base64
import io
import json
import random
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import scripts.run_target_replay as driver
from scripts.effect_replay import node_tar_conditions, run_rounds
from scripts.run_effect_demo import NativeDemoAborted

from inodefence import cli
from inodefence.builder import build_tar
from inodefence.case_replay import (
    REPLAY_SCHEMA,
    CaseReplayError,
    ReplayRun,
    build_replay_record,
    load_replay_request,
    normalize_round,
    parse_replay_input,
    publish_replay,
    read_replays,
    replay_brief,
    replay_input_line,
    summarize_rounds,
)
from inodefence.generator.minimal import minimal_seed_corpus
from inodefence.live_exploration import (
    REPLAY_COMMAND_TEMPLATE,
    LiveRecorder,
    LiveRunMeta,
    LiveStep,
    render_live_status,
)
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.mutator import MutationOperatorId, MutationPolicy, apply_operator
from inodefence.runtime import SentinelSpec
from inodefence.tar_reader import MAX_ENTRIES, TarReadError, read_builder_tar

IMAGE = "sha256:" + "c" * 64
SETTINGS = {
    "sentinel_count": None,
    "sentinel_seed": None,
    "observer_integrity_policy": "stop",
    "profile": "full",
}
NOW = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)


# -- TAR reader --------------------------------------------------------------------------------


def _grown_cases(count: int = 400) -> list[ArchiveCase]:
    """Inputs grown by the real mutator: duplicates, links, odd modes, directories."""
    rng = random.Random(7)
    pool = list(minimal_seed_corpus())
    out: list[ArchiveCase] = []
    while len(out) < count:
        case = rng.choice(pool)
        operator = rng.choice(list(MutationOperatorId))
        try:
            child = apply_operator(case, rng, MutationPolicy.M1, operator).child_case
            build_tar(child)
        except (ValueError, KeyError):
            continue
        pool.append(child)
        out.append(child)
    return out


def test_reader_inverts_the_builder_byte_for_byte() -> None:
    edge = ArchiveCase(
        (
            ArchiveEntry("dir/", EntryType.DIRECTORY, mode=0o755),  # trailing slash kept raw
            ArchiveEntry("dir/a", EntryType.REGULAR, b"", mode=0o4755),
            ArchiveEntry("dir/a", EntryType.REGULAR, b"dup"),  # duplicate path, order matters
            ArchiveEntry("h", EntryType.HARDLINK, link_target="dir/a"),
            ArchiveEntry("s", EntryType.SYMLINK, link_target="../outside/x"),
            ArchiveEntry("p" * 120 + "/" + "n" * 90, EntryType.REGULAR, b"x" * 1000),
        )
    )
    for case in [edge, *minimal_seed_corpus(), *_grown_cases()]:
        data = build_tar(case)
        back = read_builder_tar(data, expected_case_id=case.case_id)
        assert back == case and build_tar(back) == data


def test_reader_refuses_what_the_builder_did_not_write() -> None:
    case = minimal_seed_corpus()[0]
    data = build_tar(case)
    with pytest.raises(TarReadError, match="multiple of 512"):
        read_builder_tar(data[:-1])
    with pytest.raises(TarReadError, match="same bytes"):
        read_builder_tar(data + bytes(10240))  # extra padding after the archive
    other = io.BytesIO()  # a normal tarfile archive: real mtime/uid, not this builder
    with tarfile.open(fileobj=other, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        info = tarfile.TarInfo("a")
        info.mtime, info.size = 1_700_000_000, 1
        archive.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(TarReadError, match="same bytes"):
        read_builder_tar(other.getvalue())
    device = bytearray(data)
    device[156:157] = b"3"  # character device: never produced by the builder
    with pytest.raises(TarReadError, match="unsupported entry type"):
        read_builder_tar(bytes(device))


def test_changed_content_is_a_different_input_not_the_expected_one() -> None:
    case = ArchiveCase((ArchiveEntry("a", EntryType.REGULAR, b"hello"),))
    data = bytearray(build_tar(case))
    data[512] = ord("j")  # same length, other bytes: a valid builder TAR of another case
    with pytest.raises(TarReadError, match="differs from the expected"):
        read_builder_tar(bytes(data), expected_case_id=case.case_id)


def test_reader_bounds_entries() -> None:
    many = ArchiveCase(
        tuple(ArchiveEntry(f"f{i}", EntryType.REGULAR, b"") for i in range(MAX_ENTRIES + 1))
    )
    with pytest.raises(TarReadError, match="more than"):
        read_builder_tar(build_tar(many))


# -- request / record ----------------------------------------------------------------------------


def _case_folder(tmp_path: Path, *, settings=SETTINGS, image=IMAGE, fps=("C1-aa",)) -> Path:
    meta = LiveRunMeta(
        target="node-tar",
        version="7.5.1",
        seed=1,
        budget=10,
        image_id=image,
        engine_commit="e" * 40,
        replay_template=REPLAY_COMMAND_TEMPLATE,
        run_settings=settings,
    )
    case = minimal_seed_corpus()[1]
    rec = LiveRecorder(tmp_path / "out" / "live", meta)
    rec.on_step(
        LiveStep(
            index=4,
            case_id=case.case_id,
            status="success",
            c1=True,
            c0=False,
            fingerprints=fps,
            tar_bytes=build_tar(case),
            observation_complete=True,
        )
    )
    return tmp_path / "out" / "live" / "violations" / "run-000005"


def test_case_record_carries_the_replay_command_and_settings(tmp_path: Path) -> None:
    folder = _case_folder(tmp_path)
    record = json.loads((folder / "case.json").read_text())
    assert record["replay"] == "inodefence replay violations/run-000005"
    assert record["replay_cwd"] == "live folder" and record["run_settings"] == SETTINGS


def test_request_checks_input_image_and_settings(tmp_path: Path) -> None:
    request = load_replay_request(_case_folder(tmp_path), rounds=2)
    assert request.case == minimal_seed_corpus()[1] and request.rounds == 2
    assert request.original["c1"] is True and request.original["fingerprints"] == ["C1-aa"]

    tampered = _case_folder(tmp_path / "t")
    (tampered / "input.tar").write_bytes(b"\0" * 1024)
    with pytest.raises(CaseReplayError, match="sha256"):
        load_replay_request(tampered)
    with pytest.raises(CaseReplayError, match="run_settings"):
        load_replay_request(_case_folder(tmp_path / "s", settings=None))
    with pytest.raises(CaseReplayError, match="exact image id"):
        load_replay_request(_case_folder(tmp_path / "i", image="inodefence-node-tar:7.5.1"))
    with pytest.raises(CaseReplayError, match="rounds"):
        load_replay_request(_case_folder(tmp_path / "r"), rounds=0)
    with pytest.raises(CaseReplayError, match="not a violation case folder"):
        load_replay_request(tmp_path)


def _round(outcome="judged", c1=True, fps=("C1-aa",), **kw) -> dict:
    base = {"outcome": outcome, "termination": "success", "c0": False, "c1": c1, "c2": None}
    if outcome == "run_error":
        base.update(c0=None, c1=None, termination=None)
    return {**base, "fingerprints": list(fps), "observation_complete": True, **kw}


def test_rates_are_over_judged_rounds_and_kept_separate() -> None:
    original = {"c0": False, "c1": True, "c2": None, "fingerprints": ["C1-aa"]}
    rounds = [
        _round(),  # same contract, same fingerprint
        _round(fps=("C1-bb",)),  # same contract, other fingerprint
        _round(c1=False, fps=()),  # judged, did not violate
        _round("run_error", fps=()),  # not evaluated: counted, not "did not reproduce"
    ]
    summary = summarize_rounds(original, [normalize_round(r, i + 1) for i, r in enumerate(rounds)])
    assert (summary["judged"], summary["unjudged"]) == (3, 1)
    assert (summary["same_contracts"], summary["same_fingerprints"]) == (2, 1)
    assert summary["same_contracts_rate"] == 0.666667
    assert summary["fingerprint_match_rate"] == 0.333333


def test_record_is_published_beside_the_case_and_never_overwrites(tmp_path: Path) -> None:
    folder = _case_folder(tmp_path)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    request = load_replay_request(folder, rounds=3)
    run = ReplayRun(rounds=(_round(), _round()), complete=False, stop_reason="controller died")
    record = build_replay_record(request, run, started_at=NOW, finished_at=NOW)
    assert record["schema"] == REPLAY_SCHEMA
    assert record["replay"]["complete"] is False  # 2 of 3 -> incomplete, never "not reproduced"
    assert record["replay"]["stop_reason"] == "controller died"
    published = publish_replay(folder, record, moment=NOW)
    assert published.name == "run-000005.replay-20261115T120000Z"
    assert published.parent == folder.parent
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before  # case untouched
    with pytest.raises(CaseReplayError, match="already exists"):
        publish_replay(folder, record, moment=NOW)
    (latest,) = read_replays(folder)
    assert replay_brief(latest) == "replay INCOMPLETE 2/3: same contracts 2/2, fingerprints 2/2"


def test_engine_difference_is_flagged_not_blocked(tmp_path: Path) -> None:
    request = load_replay_request(_case_folder(tmp_path), rounds=1)
    run = ReplayRun(rounds=(_round(),), complete=True, engine_commit="f" * 40)
    record = build_replay_record(request, run, started_at=NOW, finished_at=NOW)
    assert record["replay"]["engine_differs"] is True
    assert replay_brief(record).endswith("(engine commit differs)")


# -- host -> controller input line ---------------------------------------------------------------


def test_input_line_round_trips_and_the_controller_rechecks(tmp_path: Path) -> None:
    request = load_replay_request(_case_folder(tmp_path), rounds=3)
    line = replay_input_line(request)
    assert line.endswith("\n") and line.count("\n") == 1
    parsed = parse_replay_input(line)
    assert parsed.case == request.case and parsed.rounds == 3 and parsed.run_settings == SETTINGS
    data = json.loads(line)
    for key, bad, match in (
        ("tar_sha256", "0" * 64, "host's"),
        ("case_id", "0" * 64, "differs from the expected"),
        ("tar_b64", "!!", "base64"),
        ("rounds", 99, "rounds"),
    ):
        with pytest.raises(CaseReplayError, match=match):
            parse_replay_input(json.dumps({**data, key: bad}))
    with pytest.raises(CaseReplayError, match="keys"):
        parse_replay_input(json.dumps({**data, "extra": 1}))
    other = base64.b64encode(build_tar(minimal_seed_corpus()[0])).decode()
    with pytest.raises(CaseReplayError, match="host's"):
        parse_replay_input(json.dumps({**data, "tar_b64": other}))


# -- node-tar in-controller helpers (fake target; no Docker) ------------------------------------


def test_node_tar_conditions_reproduce_exploration_settings() -> None:
    sentinels, cont, profile = node_tar_conditions(SETTINGS)
    assert sentinels == (SentinelSpec(),) and cont is False and profile.value == "full"
    gen = {
        **SETTINGS,
        "sentinel_count": 3,
        "sentinel_seed": 9,
        "observer_integrity_policy": "invalid-continue",
    }
    sentinels, cont, _ = node_tar_conditions(gen)
    assert len(sentinels) == 3 and cont is True
    for bad, match in (
        ({**SETTINGS, "sentinel_count": 2}, "together"),
        ({**SETTINGS, "observer_integrity_policy": "maybe"}, "observer_integrity_policy"),
        ({**SETTINGS, "profile": "turbo"}, "profile"),
        ({k: v for k, v in SETTINGS.items() if k != "profile"}, "missing"),
    ):
        with pytest.raises(CaseReplayError, match=match):
            node_tar_conditions(bad)


def test_run_rounds_keeps_going_after_an_untrusted_round() -> None:
    case = minimal_seed_corpus()[0]
    good = SimpleNamespace(
        base_result=SimpleNamespace(
            case=case, execution=SimpleNamespace(status="timed_out"), violations=()
        ),
        trace=SimpleNamespace(integrity_valid=False),
    )
    calls = iter([good, NativeDemoAborted(1, case.case_id, "evidence integrity failed"), good])

    def produce(_case):
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item

    seen: list[dict] = []
    records = run_rounds(produce, case, 3, round_sink=seen.append)
    assert [r["outcome"] for r in records] == ["judged", "run_error", "judged"]
    assert records[0]["termination"] == "timed_out" and records[0]["observation_complete"] is False
    assert records[1]["reason"] == "evidence integrity failed" and seen == records


# -- driver ------------------------------------------------------------------------------------


def _docker(present: str | None):
    def run(argv, **kw):
        assert argv[:3] == ["docker", "image", "inspect"]
        if present is None:
            return subprocess.CompletedProcess(argv, 1, "", "No such image")
        return subprocess.CompletedProcess(argv, 0, present + "\n", "")

    return run


def _adapter(monkeypatch, hook) -> None:
    monkeypatch.setattr(driver, "load_adapter", lambda target: SimpleNamespace(replay=hook))


def test_driver_stops_when_the_image_is_absent_and_never_prepares(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    called: list = []
    _adapter(monkeypatch, lambda req, work: called.append(req))
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker(None)) == 3
    assert not called and "not on this host" in capsys.readouterr().err
    assert driver.main([str(folder)], runner=_docker("sha256:" + "d" * 64)) == 3  # other image
    assert not list(folder.parent.glob("*.replay-*"))


def test_driver_reports_unsupported_targets(tmp_path: Path, monkeypatch, capsys) -> None:
    _adapter(monkeypatch, None)
    assert driver.main([str(_case_folder(tmp_path))], runner=_docker(IMAGE)) == 4
    assert "no replay hook" in capsys.readouterr().err


def test_driver_runs_records_and_status_shows_it(tmp_path: Path, monkeypatch, capsys) -> None:
    def hook(request, work: Path) -> ReplayRun:
        assert work.is_dir() and request.image_id == IMAGE
        return ReplayRun(rounds=(_round(), _round(), _round()), complete=True)

    _adapter(monkeypatch, hook)
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder), "--dry-run"], runner=_docker(IMAGE)) == 0
    assert not list(folder.parent.glob("*.replay-*"))  # dry-run writes nothing
    capsys.readouterr()
    assert driver.main([str(folder)], runner=_docker(IMAGE)) == 0
    out = capsys.readouterr().out
    assert out.startswith("replayed 3/3: same contracts 3/3, fingerprints 3/3")
    (record,) = read_replays(folder)
    assert record["replay"]["complete"] is True and record["replay"]["engine_commit"]
    status = render_live_status(folder.parent.parent, display="live")
    assert "replayed 3/3: same contracts 3/3" in status


def test_driver_keeps_rounds_when_the_hook_fails(tmp_path: Path, monkeypatch, capsys) -> None:
    def boom(request, work):
        raise RuntimeError("controller vanished")

    _adapter(monkeypatch, boom)
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker(IMAGE)) == 1
    (record,) = read_replays(folder)
    assert record["replay"]["complete"] is False
    assert "controller vanished" in record["replay"]["stop_reason"]
    assert "REPLAY INCOMPLETE" in capsys.readouterr().err


def test_driver_refuses_a_case_inside_the_repository(monkeypatch, tmp_path: Path, capsys) -> None:
    _adapter(monkeypatch, lambda req, work: None)
    monkeypatch.setattr(driver, "REPO_ROOT", tmp_path)
    assert driver.main([str(_case_folder(tmp_path))], runner=_docker(IMAGE)) == 3
    assert "inside the repository" in capsys.readouterr().err


def test_cli_resolves_the_case_folder_before_forwarding(monkeypatch, tmp_path: Path) -> None:
    calls: list = []
    monkeypatch.setattr(cli, "repo_root", lambda: Path("/repo"))
    monkeypatch.setattr(cli, "run_driver", lambda root, d, argv: calls.append((d, argv)) or 0)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["replay", "violations/run-000005", "--dry-run"]) == 0
    ((d, argv),) = calls
    assert d == cli.REPLAY_DRIVER
    assert argv == [str(tmp_path / "violations" / "run-000005"), "--rounds", "3", "--dry-run"]


def _fake_bound(monkeypatch, results) -> None:
    import scripts.effect_replay as er

    calls = iter(results)

    def fake_producer(target, sentinels, recovery, **kw):
        def produce(case):
            item = next(calls)
            if isinstance(item, Exception):
                raise item
            return item

        return produce

    monkeypatch.setattr(er, "_native_effect_producer", fake_producer)
    monkeypatch.setattr(
        er.NodeTarEffectTarget,
        "bind",
        classmethod(lambda cls, backend, image, **kw: SimpleNamespace(tar_version="7.5.1")),
    )


def _result(status: str = "success"):
    case = minimal_seed_corpus()[0]
    return SimpleNamespace(
        base_result=SimpleNamespace(
            case=case, execution=SimpleNamespace(status=status), violations=()
        ),
        trace=SimpleNamespace(integrity_valid=True),
    )


def test_controller_entry_journals_every_round(tmp_path: Path, monkeypatch) -> None:
    from scripts.effect_replay import replay_rounds_path, run_case_replay

    request = load_replay_request(_case_folder(tmp_path), rounds=3)
    replay_input = parse_replay_input(replay_input_line(request))
    _fake_bound(monkeypatch, [_result(), _result("rejected"), _result()])
    evidence = tmp_path / "ctrl" / "inodefence-replay-x.json"
    evidence.parent.mkdir()
    assert run_case_replay(object(), IMAGE, evidence, replay_input, None) == 0
    report = json.loads(evidence.read_text())
    assert report["complete"] is True and len(report["rounds"]) == 3
    assert report["rounds"][1]["termination"] == "rejected"
    lines = replay_rounds_path(evidence).read_text().splitlines()
    assert replay_rounds_path(evidence).name == "inodefence-replay-x.steps.jsonl"
    assert [json.loads(line)["round"] for line in lines] == [1, 2, 3]


def test_controller_entry_keeps_finished_rounds_when_it_dies(tmp_path: Path, monkeypatch) -> None:
    from scripts.effect_replay import replay_rounds_path, run_case_replay

    request = load_replay_request(_case_folder(tmp_path), rounds=3)
    replay_input = parse_replay_input(replay_input_line(request))
    _fake_bound(monkeypatch, [_result(), RuntimeError("docker daemon went away")])
    evidence = tmp_path / "ctrl" / "inodefence-replay-y.json"
    evidence.parent.mkdir()
    assert run_case_replay(object(), IMAGE, evidence, replay_input, None) == 1
    report = json.loads(evidence.read_text())
    assert report["complete"] is False and len(report["rounds"]) == 1
    assert "docker daemon went away" in report["stop_reason"]
    assert len(replay_rounds_path(evidence).read_text().splitlines()) == 1


# -- node-tar hook (fake smoke runner; no Docker) ----------------------------------------------


def _fake_smoke(
    rounds: list[dict], *, complete: bool, report: bool = True, rc: int = 0, **override
):
    seen: dict = {}

    def run(argv, env, cwd):
        import re

        from scripts.node_tar_replay import report_paths

        seen.update(argv=argv, env=env, cwd=cwd)
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", env["RUN_ID"])
        line = Path(env["REPLAY_INPUT"]).read_text()
        parsed = parse_replay_input(line)  # the controller would accept exactly this
        report_path, journal = report_paths(Path(env["INODEFENCE_EVIDENCE_DIR"]), env["RUN_ID"])
        report_path.parent.mkdir(parents=True)
        journal.write_text("".join(json.dumps(r) + "\n" for r in rounds))
        if report:
            report_path.write_text(
                json.dumps(
                    {
                        "case_id": parsed.case.case_id,
                        "tar_sha256": parsed.tar_sha256,
                        "image_id": env["REPLAY_IMAGE"],
                        "rounds": rounds,
                        "complete": complete,
                        "node_tar_version": "7.5.1",
                        **override,
                    }
                )
            )
        return subprocess.CompletedProcess(argv, rc)

    return run, seen


def test_node_tar_hook_runs_the_smoke_replay_and_reads_the_report(tmp_path: Path) -> None:
    from scripts.node_tar_replay import replay

    request = load_replay_request(_case_folder(tmp_path), rounds=2)
    work = tmp_path / "work"
    work.mkdir()
    run, seen = _fake_smoke([_round(round=1), _round(round=2)], complete=True)
    result = replay(request, work, runner=run)
    assert seen["argv"][-1] == "replay" and seen["argv"][1].endswith("local_node_tar_smoke.sh")
    assert seen["env"]["REPLAY_IMAGE"] == IMAGE
    assert Path(seen["env"]["REPLAY_INPUT"]).is_absolute()
    assert Path(seen["env"]["INODEFENCE_EVIDENCE_DIR"]).is_relative_to(work)
    assert result.complete and len(result.rounds) == 2
    assert result.runner["node_tar_version"] == "7.5.1"


def test_node_tar_hook_keeps_journal_rounds_when_the_controller_died(tmp_path: Path) -> None:
    from scripts.node_tar_replay import replay

    request = load_replay_request(_case_folder(tmp_path), rounds=3)
    (tmp_path / "work").mkdir()
    run, _ = _fake_smoke([_round(round=1)], complete=False, report=False, rc=1)
    result = replay(request, tmp_path / "work", runner=run)
    assert not result.complete and len(result.rounds) == 1
    assert "1 finished round(s) read from the journal" in (result.stop_reason or "")


def test_node_tar_hook_refuses_a_report_about_another_case(tmp_path: Path) -> None:
    from scripts.node_tar_replay import replay

    request = load_replay_request(_case_folder(tmp_path), rounds=1)
    (tmp_path / "work").mkdir()
    run, _ = _fake_smoke([_round()], complete=True, image_id="sha256:" + "d" * 64)
    with pytest.raises(CaseReplayError, match="image_id"):
        replay(request, tmp_path / "work", runner=run)


def test_node_tar_adapter_replays_end_to_end_through_the_driver(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    import scripts.node_tar_replay as ntr

    real = ntr.replay
    run, _ = _fake_smoke([_round(round=i) for i in (1, 2, 3)], complete=True)
    monkeypatch.setattr(ntr, "replay", lambda request, work: real(request, work, runner=run))
    folder = _case_folder(tmp_path)
    assert driver.main([str(folder)], runner=_docker(IMAGE)) == 0  # the real node-tar adapter
    (record,) = read_replays(folder)
    assert record["replay"]["complete"] is True
    assert record["summary"]["same_contracts"] == 3
    assert record["replay"]["runner"]["path"].endswith("effect-replay-case")
    assert "replayed 3/3" in capsys.readouterr().out
