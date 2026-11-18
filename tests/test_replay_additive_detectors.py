"""D-258: the record-only ``additive_detectors`` column on node-tar replay rounds.

Series ``additive-detectors-v1 (record-only)``. Off by default; ``inodefence replay
--additive-detectors`` switches it on for node-tar only. Gates checked here:

* off: the input line, the rounds and the replay record are exactly as before, and the AFTER
  snapshot is not read (the existing round fake without one still works);
* on: judged rounds carry the column, run_error rounds never do, a missing AFTER snapshot is an
  error (not hidden), and C0/C1/C2, fingerprints and observation lines are unchanged;
* the per-detector summary counts rounds with a candidate signal (count > 0), never one scalar;
* the step records and the registered golden step serialization carry no new key;
* ``evidence_sha256`` uses sandbox-relative paths and no device/inode numbers.

Synthetic runs only (the controlled in-sandbox extractor of the oracle fixtures); no target runs.
A count above zero is a candidate signal, not a verdict.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from scripts.effect_replay import run_rounds
from scripts.oracle_fixture_check import ORACLE_FIXTURES, UncheckedControlledExtractor

import inodefence.drivers.run_target_replay as rtr
from inodefence import additive_detectors as ad
from inodefence import case_replay as cr
from inodefence.effect_campaign import EffectCampaignStep
from inodefence.generator import minimal_seed_corpus
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType
from inodefence.pipeline import run_case

FIXTURES = {fixture.name: fixture for fixture in ORACLE_FIXTURES}
REFERENT_CASE = FIXTURES["c2"].case  # an extraction symlink whose referent is outside extract/
IDENTITY_CASE = ArchiveCase(
    (ArchiveEntry("shared", EntryType.HARDLINK, link_target="../archive/input.tar"),)
)
BENIGN_CASE = ArchiveCase((ArchiveEntry("inner", EntryType.REGULAR, content=b"x"),))


def _effect_like(case: ArchiveCase) -> SimpleNamespace:
    """A run result shaped like an ``EffectRunResult`` from a real synthetic run."""
    base = run_case(case, UncheckedControlledExtractor())
    return SimpleNamespace(base_result=base, trace=SimpleNamespace(integrity_valid=True))


# -- the helper ---------------------------------------------------------------------------------


def test_fields_report_counts_regions_basis_and_no_path() -> None:
    fields = ad.additive_detector_fields(_effect_like(REFERENT_CASE).base_result.after)
    assert ad.check_fields(fields) is fields
    assert fields["symlink_referent"] == {
        "count": 1,
        "referent_regions": ["external"],
        "basis": "lexical",
    }
    assert fields["generalized_identity"]["basis"] == "physical"
    text = json.dumps(fields)
    assert "extract/" not in text and "outside" not in text  # no path in the column
    identity = ad.additive_detector_fields(_effect_like(IDENTITY_CASE).base_result.after)
    assert identity["generalized_identity"] == {
        "count": 1,
        "external_regions": ["harness"],
        "basis": "physical",
    }


def test_evidence_digest_has_no_device_or_inode_and_no_absolute_path() -> None:
    # Two runs of the same case get different inodes; the digest is the same.
    first = _effect_like(IDENTITY_CASE).base_result.after
    second = _effect_like(IDENTITY_CASE).base_result.after
    assert ad.evidence_digest(first) == ad.evidence_digest(second)
    assert ad.IDENTITY_FIELDS == ("internal_path", "external_path")
    assert ad.REFERENT_FIELDS == ("internal_path", "referent_target", "referent_region")
    for item in (*first.objects, *second.objects):
        assert not item.path.startswith("/")  # the snapshot's paths are sandbox-relative


def test_benign_run_has_zero_counts() -> None:
    fields = ad.additive_detector_fields(_effect_like(BENIGN_CASE).base_result.after)
    assert fields["generalized_identity"]["count"] == 0
    assert fields["symlink_referent"]["count"] == 0


# -- rounds: off is unchanged, on adds the column -----------------------------------------------


def _rounds(results: list[Any], *, on: bool) -> list[dict[str, Any]]:
    calls = iter(results)
    return run_rounds(lambda _case: next(calls), minimal_seed_corpus()[0], len(results),
                      additive_detectors=on)  # fmt: skip


def test_off_rounds_do_not_read_the_after_snapshot() -> None:
    # The existing fake (no AFTER snapshot at all) still works when the switch is off.
    fake = SimpleNamespace(
        base_result=SimpleNamespace(execution=SimpleNamespace(status="success"), violations=()),
        trace=SimpleNamespace(integrity_valid=True),
    )
    (record,) = _rounds([fake], on=False)
    assert cr.ADDITIVE_KEY not in record


def test_on_rounds_carry_the_column_and_keep_the_verdict_fields() -> None:
    result = _effect_like(REFERENT_CASE)
    (off,) = _rounds([result], on=False)
    (on,) = _rounds([result], on=True)
    column = on.pop(cr.ADDITIVE_KEY)
    assert on == off  # c0/c1/c2, fingerprints, observation, termination unchanged
    assert column["symlink_referent"]["count"] == 1


def test_on_without_an_after_snapshot_is_an_error_not_a_silent_omission() -> None:
    fake = SimpleNamespace(
        base_result=SimpleNamespace(execution=SimpleNamespace(status="success"), violations=()),
        trace=SimpleNamespace(integrity_valid=True),
    )
    with pytest.raises(AttributeError):
        _rounds([fake], on=True)


# -- normalize_round and the summary ------------------------------------------------------------


def _raw(**extra: Any) -> dict[str, Any]:
    return {"outcome": "judged", "termination": "success", "c0": False, "c1": False,
            "c2": False, "observation_complete": True, "fingerprints": [], **extra}  # fmt: skip


def test_normalize_round_keeps_its_fixed_keys_and_passes_the_column_only_when_present() -> None:
    plain = cr.normalize_round(_raw(), 1)
    assert set(plain) == {
        "round", "outcome", "termination", "c0", "c1", "c2",
        "observation_complete", "fingerprints", "observation", "reason",
    }  # fmt: skip
    column = ad.additive_detector_fields(_effect_like(BENIGN_CASE).base_result.after)
    carried = cr.normalize_round(_raw(additive_detectors=column), 1)
    assert carried.pop(cr.ADDITIVE_KEY) == column and carried == plain
    with pytest.raises(cr.CaseReplayError, match="additive_detectors"):
        cr.normalize_round(_raw(additive_detectors={"schema": "other"}), 1)


def test_a_run_error_round_never_carries_the_column() -> None:
    column = ad.additive_detector_fields(_effect_like(BENIGN_CASE).base_result.after)
    raw = {"outcome": "run_error", "reason": "x", "additive_detectors": column}
    with pytest.raises(cr.CaseReplayError, match="only a judged round"):
        cr.normalize_round(raw, 1)


def test_summary_counts_candidate_signal_rounds_per_detector_only_when_present() -> None:
    plain = [cr.normalize_round(_raw(), 1)]
    assert "additive_candidate_signal_rounds" not in cr.summarize_rounds({}, plain)
    positive = ad.additive_detector_fields(_effect_like(REFERENT_CASE).base_result.after)
    zero = ad.additive_detector_fields(_effect_like(BENIGN_CASE).base_result.after)
    rounds = [
        cr.normalize_round(_raw(additive_detectors=positive), 1),
        cr.normalize_round(_raw(additive_detectors=zero), 2),
    ]
    summary = cr.summarize_rounds({}, rounds)
    assert summary["additive_candidate_signal_rounds"] == {
        "generalized_identity": 0,
        "symlink_referent": 1,
    }


# -- the input line and the record --------------------------------------------------------------


def _request(**changes: Any) -> cr.ReplayRequest:
    case = minimal_seed_corpus()[0]
    from inodefence.builder import build_tar

    tar = build_tar(case)
    from hashlib import sha256

    base = cr.ReplayRequest(
        case_dir=Path("/tmp/case"), case=case, tar_bytes=tar, tar_sha256=sha256(tar).hexdigest(),
        case_id=case.case_id, target="node-tar", version="7.5.23", image_id="sha256:" + "a" * 64,
        engine_commit=None,
        run_settings={"sentinel_count": None, "sentinel_seed": None,
                      "observer_integrity_policy": "stop", "profile": "full"},
        original={"run": "step-1", "c0": True, "c1": False, "c2": False, "fingerprints": []},
        rounds=1,
    )  # fmt: skip
    return dataclasses.replace(base, **changes)


def test_off_input_line_is_unchanged_and_on_carries_the_option_beside_the_settings() -> None:
    off = _request()
    assert json.loads(cr.replay_input_line(off))["run_settings"] == off.run_settings
    on = dataclasses.replace(off, additive_detectors=True)
    parsed = cr.parse_replay_input(cr.replay_input_line(on))
    assert parsed.run_settings == off.run_settings  # the exploration settings, untouched
    assert parsed.options == {"additive_detectors": True}
    assert cr.parse_replay_input(cr.replay_input_line(off)).options == {}


def test_an_unknown_replay_option_is_refused() -> None:
    line = json.loads(cr.replay_input_line(_request()))
    line["run_settings"]["replay_options"] = {"something_else": True}
    with pytest.raises(cr.CaseReplayError, match="replay_options"):
        cr.parse_replay_input(json.dumps(line))


def test_the_record_names_the_option_only_when_on() -> None:
    from datetime import UTC, datetime

    run = cr.ReplayRun(rounds=(_raw(),), complete=True)
    moment = datetime(2026, 11, 18, tzinfo=UTC)
    off = cr.build_replay_record(_request(), run, started_at=moment, finished_at=moment)
    assert "options" not in off["replay"]
    on = cr.build_replay_record(
        _request(additive_detectors=True), run, started_at=moment, finished_at=moment
    )
    assert on["replay"]["options"] == {"additive_detectors": True}
    assert on["original"]["run_settings"] == off["original"]["run_settings"]


# -- the driver: node-tar only ------------------------------------------------------------------


def test_the_driver_refuses_the_switch_for_other_targets(monkeypatch, capsys, tmp_path) -> None:
    request = _request(target="python-tarfile", case_dir=tmp_path / "case")
    monkeypatch.setattr(rtr, "load_request", lambda *a, **k: request)
    monkeypatch.setattr(rtr, "load_adapter", lambda target: pytest.fail("adapter loaded"))
    assert rtr.main([str(tmp_path / "case"), "--additive-detectors"]) == 3
    assert "node-tar replay only" in capsys.readouterr().err


# -- step records and the registered golden -----------------------------------------------------


def test_step_records_and_the_golden_step_serialization_carry_no_new_key() -> None:
    names = {field.name for field in dataclasses.fields(EffectCampaignStep)}
    assert cr.ADDITIVE_KEY not in names  # the golden digest serializes these fields only
    from tests.test_python_tarfile_contained import IMAGE, RUNTIME, _LocalBackend

    from inodefence.python_tarfile_explore import python_tarfile_exploration_report

    lines: list[dict[str, Any]] = []
    python_tarfile_exploration_report(
        _LocalBackend(), IMAGE, "data", RUNTIME, seed=1, budget=6, step_sink=lines.append
    )
    assert lines and all(cr.ADDITIVE_KEY not in line for line in lines)
