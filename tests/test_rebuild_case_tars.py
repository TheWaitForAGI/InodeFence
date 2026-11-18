"""Rebuild step TARs from a step journal (D-269) on synthetic v2 campaigns (no target run).

The journal is the report builder's own step records (``effect_campaign_report``), the same
records an exploration streams, from a campaign driven by the structure-dependent synthetic
producer of the v2 seed-corpus golden.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from scripts.analysis import rebuild_case_tars as rct
from tests.test_seed_corpus_golden_v21 import _run as run_cell

from inodefence.builder import build_tar
from inodefence.case_replay import load_replay_request
from inodefence.effect_demo import effect_campaign_report

ENGINE = "e" * 40
IMAGE = "sha256:" + "a" * 64
SETTINGS = {
    "sentinel_count": None,
    "sentinel_seed": None,
    "observer_integrity_policy": "stop",
    "profile": "full",
}


#: What node-tar exploration writes into live/progress.json (LiveRunMeta.as_dict()).
def _progress(steps: int, **change: object) -> dict:
    meta = {
        "state": "finished",
        "target": "node-tar",
        "version": "7.5.7",
        "seed": 5,
        "budget": steps,
        "image_id": IMAGE,
        "engine_commit": ENGINE,
        "run_settings": dict(SETTINGS),
    }
    meta.update(change)
    return {k: v for k, v in meta.items() if v is not None}


_CACHE: dict[str, tuple] = {}


def _campaign(cell: str):  # type: ignore[no-untyped-def]
    if cell not in _CACHE:
        result = run_cell(cell)
        records = effect_campaign_report(result, "synthetic")["steps"]
        truth = {s.index: s.result.base_result.case for s in result.steps}
        _CACHE[cell] = (result.config.mutation_policy.value, records, truth)
    return _CACHE[cell]


def _setup(
    tmp_path: Path,
    cell: str = "v2:R:5:64",
    *,
    records=None,
    progress: dict | None = None,
    steps: list[int] | None = None,
):  # type: ignore[no-untyped-def]
    policy, base_records, truth = _campaign(cell)
    records = base_records if records is None else records
    run = tmp_path / "run"
    (run / "live").mkdir(parents=True)
    journal = run / "inodefence-effect-explore-run.steps.jsonl.gz"
    with gzip.open(journal, "wt", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record) + "\n")
    meta = _progress(len(base_records)) if progress is None else progress
    (run / "live" / "progress.json").write_text(json.dumps(meta))
    settings = None
    listing = tmp_path / "steps.txt"
    chosen = steps if steps is not None else sorted(truth)[4:24]
    listing.write_text("".join(f"{i}\n" for i in chosen), encoding="utf-8")
    return policy, journal, run, settings, listing, truth


def _args(policy, journal, run, settings, listing, out, **change):  # type: ignore[no-untyped-def]
    values = {
        "--journal": str(journal),
        "--run-dir": str(run),
        "--expected-engine": ENGINE,
        "--mutation-policy": policy,
        "--steps-list": str(listing),
        "--target": "node-tar",
        "--version": "7.5.7",
        "--image-id": IMAGE,
        "--out": str(out),
    }
    values.update(change)
    return [part for pair in values.items() for part in pair]


def _main(capsys, *argv: str) -> tuple[int, dict]:
    code = rct.main(list(argv))
    lines = capsys.readouterr().out.strip().splitlines()
    return code, json.loads(lines[-1]) if lines else {}


@pytest.mark.parametrize("cell", ["v2:R:5:64", "v2:S-u:5:64"])
def test_requested_steps_are_rebuilt_byte_identical(tmp_path: Path, capsys, cell: str) -> None:
    policy, journal, run, settings, listing, truth = _setup(tmp_path, cell)
    out = tmp_path / "out"
    code, summary = _main(capsys, *_args(policy, journal, run, settings, listing, out))
    assert code == 0, summary
    chosen = sorted(truth)[4:24]
    assert summary == {
        "criterion": "case_id match only",
        "failed": 0,
        "failed_by_reason": {},
        "requested": len(chosen),
        "run_settings_from_argument": [],
        "run_settings_from_record": sorted(SETTINGS),
        "verified": len(chosen),
    }
    for index in chosen:
        folder = out / f"step-{index:06d}"
        tar = (folder / "input.tar").read_bytes()
        assert tar == build_tar(truth[index])  # byte-identical to the original input
        request = load_replay_request(folder)  # the replay loader reads it back
        assert request.case_id == truth[index].case_id
        assert request.run_settings == SETTINGS  # the run's own record
        record = json.loads((folder / "case.json").read_text())
        assert record["run_settings_source"] == {"record": sorted(SETTINGS), "argument": []}
    assert json.loads((out / "failures.json").read_text()) == []


def test_a_case_id_that_matches_no_candidate_is_reported_not_written(
    tmp_path: Path, capsys
) -> None:
    """Nothing leaves without the case_id match: a tampered id is a listed failure."""
    policy, records, truth = _campaign("v2:R:5:64")
    index = sorted(truth)[-1]  # the last step: no later step uses it as a parent
    tampered = json.loads(json.dumps(records))
    tampered[index]["case_id"] = "0" * 64
    policy, journal, run, settings, listing, _ = _setup(
        tmp_path, records=tampered, steps=[index, sorted(truth)[5]]
    )
    out = tmp_path / "out"
    code, summary = _main(capsys, *_args(policy, journal, run, settings, listing, out))
    assert code == 1
    assert summary["verified"] == 1 and summary["failed"] == 1
    assert summary["failed_by_reason"] == {rct.NO_MATCH: 1}
    assert not (out / f"step-{index:06d}").exists()
    failures = json.loads((out / "failures.json").read_text())
    assert failures == [{"step": index, "reason": rct.NO_MATCH}]


def test_build_invalid_and_missing_steps_are_listed(tmp_path: Path, capsys) -> None:
    policy, records, truth = _campaign("v2:R:5:64")
    last = sorted(truth)[-1]
    changed = json.loads(json.dumps(records))
    changed[last] = {
        "index": last,
        "outcome": "build-invalid",
        "origin": "mutation",
        "case_id": changed[last]["case_id"],
        "trace": {},
    }
    policy, journal, run, settings, listing, _ = _setup(
        tmp_path, records=changed, steps=[last, 9999]
    )
    code, summary = _main(capsys, *_args(policy, journal, run, settings, listing, tmp_path / "o"))
    assert code == 1
    assert summary["failed_by_reason"] == {rct.BUILD_INVALID: 1, rct.NOT_IN_JOURNAL: 1}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"--expected-engine": "d" * 40}, "!= --expected-engine"),
        ({"--mutation-policy": "uniform-generic-m1-v1"}, "not a v2 grammar policy"),
        ({"--mutation-policy": "no-such-policy"}, "unknown mutation policy"),
        ({"--version": "7.5.11"}, "--version 7.5.11 != the run's record"),
        ({"--target": "python-tarfile"}, "--target python-tarfile != the run's record"),
        ({"--image-id": "sha256:" + "b" * 64}, "--image-id"),
        ({"--run-settings-missing": '{"profile": "fast"}'}, "differs from the run's record"),
        ({"--run-settings-missing": "[1]"}, "must be a JSON object"),
    ],
)
def test_preconditions_are_exit_2(tmp_path: Path, capsys, change: dict, message: str) -> None:
    policy, journal, run, settings, listing, _ = _setup(tmp_path)
    out = tmp_path / "out"
    code, payload = _main(capsys, *_args(policy, journal, run, settings, listing, out, **change))
    assert code == 2 and message in payload["error"]
    assert not out.exists()


@pytest.mark.parametrize(
    ("progress", "message"),
    [
        (_progress(64, engine_commit=None), "no engine commit"),
        (_progress(64, budget=None), "no budget"),
        (_progress(65), "journal incomplete"),
    ],
)
def test_run_records_are_required(tmp_path: Path, capsys, progress: dict, message: str) -> None:
    policy, journal, run, settings, listing, _ = _setup(tmp_path, progress=progress)
    code, payload = _main(capsys, *_args(policy, journal, run, settings, listing, tmp_path / "out"))
    assert code == 2 and message in payload["error"]


def test_a_gap_in_the_journal_is_exit_2(tmp_path: Path, capsys) -> None:
    policy, records, _ = _campaign("v2:R:5:64")
    gapped = [r for r in records if r["index"] != 10]
    policy, journal, run, settings, listing, _ = _setup(tmp_path, records=gapped)
    code, payload = _main(capsys, *_args(policy, journal, run, settings, listing, tmp_path / "out"))
    assert code == 2 and "journal incomplete" in payload["error"]


@pytest.mark.parametrize("where", ["repo", "drive", "existing"])
def test_out_must_be_new_local_disk(tmp_path: Path, capsys, where: str) -> None:
    policy, journal, run, settings, listing, _ = _setup(tmp_path)
    out = {
        "repo": rct.REPO_ROOT / "build" / "rebuild-test",
        "drive": tmp_path / "Drive" / "x",
        "existing": tmp_path / "run",
    }[where]
    code, payload = _main(capsys, *_args(policy, journal, run, settings, listing, out))
    assert code == 2
    assert not (rct.REPO_ROOT / "build" / "rebuild-test").exists()


def test_the_summary_carries_no_paths_or_content(tmp_path: Path, capsys) -> None:
    """Counts only: the summary's keys are fixed and its values are numbers or reasons."""
    policy, journal, run, settings, listing, _ = _setup(tmp_path)
    code, summary = _main(capsys, *_args(policy, journal, run, settings, listing, tmp_path / "out"))
    assert set(summary) == {
        "criterion",
        "failed",
        "failed_by_reason",
        "requested",
        "run_settings_from_argument",
        "run_settings_from_record",
        "verified",
    }
    assert all(isinstance(summary[k], int) for k in ("failed", "requested", "verified"))


def test_keys_the_record_lacks_come_from_the_argument(tmp_path: Path, capsys) -> None:
    partial = {k: v for k, v in SETTINGS.items() if k != "profile"}
    policy, journal, run, settings, listing, truth = _setup(
        tmp_path, progress=_progress(64, run_settings=partial)
    )
    out = tmp_path / "out"
    argv = _args(
        policy,
        journal,
        run,
        settings,
        listing,
        out,
        **{"--run-settings-missing": '{"profile": "full"}'},
    )
    code, summary = _main(capsys, *argv)
    assert code == 0
    assert summary["run_settings_from_record"] == sorted(partial)
    assert summary["run_settings_from_argument"] == ["profile"]
    index = sorted(truth)[4]
    record = json.loads((out / f"step-{index:06d}" / "case.json").read_text())
    assert record["run_settings"] == SETTINGS
    assert record["run_settings_source"]["argument"] == ["profile"]


def test_settings_the_replay_check_refuses_are_listed_failures(tmp_path: Path, capsys) -> None:
    """No run_settings recorded and none given: every written folder fails the target's replay
    check and is listed (exit 1), never silently kept."""
    policy, journal, run, settings, listing, truth = _setup(
        tmp_path, progress=_progress(64, run_settings=None)
    )
    out = tmp_path / "out"
    code, summary = _main(capsys, *_args(policy, journal, run, settings, listing, out))
    assert code == 1
    assert summary["verified"] == 0
    assert summary["failed_by_reason"] == {rct.REPLAY_REFUSED: summary["requested"]}
    assert not any(p.name.startswith("step-") for p in out.iterdir())


@pytest.mark.parametrize("shape", ["swapped", "duplicated"])
def test_out_of_order_indices_are_exit_2(tmp_path: Path, capsys, shape: str) -> None:
    """Same step count as the budget, so only the index check can catch these."""
    policy, records, _ = _campaign("v2:R:5:64")
    changed = json.loads(json.dumps(records))
    if shape == "swapped":
        changed[10], changed[11] = changed[11], changed[10]
    else:
        changed[11] = json.loads(json.dumps(changed[10]))  # step 10 twice, step 11 gone
    policy, journal, run, settings, listing, _ = _setup(tmp_path, records=changed)
    code, payload = _main(capsys, *_args(policy, journal, run, settings, listing, tmp_path / "out"))
    assert code == 2 and "journal incomplete" in payload["error"]


def test_a_policy_other_than_the_recorded_one_is_exit_2(tmp_path: Path, capsys) -> None:
    policy, journal, run, settings, listing, _ = _setup(tmp_path)
    other = next(p.value for p in rct.V2_GRAMMAR_POLICIES if p.value != policy)
    (run / "result.json").write_text(json.dumps({"campaign": {"mutation_policy": other}}))
    code, payload = _main(capsys, *_args(policy, journal, run, settings, listing, tmp_path / "out"))
    assert code == 2 and "the run records mutation policy" in payload["error"]
