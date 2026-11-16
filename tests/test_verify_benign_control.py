"""`inodefence verify` benign-input control: same image, same invocation, no PASS when it fails.

No Docker: each target's run program is replaced by a recorder (unit tests, not native runs).
"""

from __future__ import annotations

import base64
import io
import json
import tarfile
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

import inodefence.drivers.decompress.adapter as dc
import inodefence.drivers.image_prepare as ip
import inodefence.drivers.node_tar.adapter as nt
import inodefence.drivers.oras_go.adapter as og
import inodefence.drivers.python_tarfile.adapter as pt
import inodefence.drivers.regression_check as rc
import inodefence.drivers.run_target as rt
from inodefence.drivers.oras_go.registry_prepare import BENIGN as ORAS_BENIGN
from inodefence.target_result import (
    BenignControl,
    CampaignInfo,
    CaseVerdict,
    Provenance,
    ResultMode,
    TargetAxes,
    TargetResult,
    TargetResultError,
    Verdict,
    from_json_dict,
    load_target_result,
)
from inodefence.target_result_summary import render_summary

REFERENCE = {"ino": "5", "nlink": 1, "size": 10, "type": "reg"}
DECLINED = {
    "declined": {"code": "TAR_ENTRY_ERROR", "message": "linkpath escapes extraction directory"},
    "extract_tree": {},
    "shared_identity": [],
    "reference_before": REFERENCE,
    "reference_after": REFERENCE,
}
SHARED = {
    **DECLINED,
    "declined": None,
    "shared_identity": ["extract/link"],
    "reference_after": {**REFERENCE, "nlink": 2},
}
EXTRACTED = {**DECLINED, "declined": None, "extract_tree": {"ok.txt": {"type": "reg", "size": 3}}}
BENIGN_B64 = base64.b64encode(rt.benign_archive()).decode()


@pytest.fixture(autouse=True)
def _no_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt, "docker_problem", lambda: None)
    monkeypatch.setattr(ip, "check", lambda argv, runner=None: 0)
    monkeypatch.setattr(rt, "image_id", lambda ref: f"sha256:{ref}")
    monkeypatch.setattr(
        rt, "engine_provenance", lambda image: Provenance("b" * 40, False, image, "sha256:abc")
    )


def _node_run_one(fixtures: dict[str, Any], benign: dict[str, Any], seen: list | None = None):
    def run_one(release: str, tar_b64: str, image: str | None = None, **kw) -> dict[str, Any]:
        if seen is not None:
            seen.append((tar_b64 == BENIGN_B64, image))
        return benign if tar_b64 == BENIGN_B64 else fixtures

    return run_one


def _control(extracted: bool = True) -> BenignControl:
    return BenignControl(extracted, "ok.txt", rt.BENIGN_TAR_PATH, "a" * 64, "ok.txt extracted")


def _result(*, c1: bool = False, outcome: str = "declined", control=None) -> TargetResult:
    errored = outcome == "run_error"
    return TargetResult(
        target="node-tar",
        axes=TargetAxes(target_version="7.5.23"),
        mode=ResultMode.FIXTURE_REGRESSION,
        observed_contracts=("C1", "C2"),
        cases=(
            CaseVerdict(
                "nested_hardlink",
                outcome,
                None,
                None if errored else c1,
                None if errored else False,
            ),
        ),
        repro_inputs=(),
        provenance=Provenance(None, False, "img:tag", "sha256:" + "c" * 64),
        benign_control=control,
    )


# -- the control archive is product-only ---------------------------------------------------------


def test_the_benign_archive_is_one_regular_file_and_deterministic() -> None:
    data = rt.benign_archive()
    assert data == rt.benign_archive()
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        (member,) = archive.getmembers()
        assert (member.name, member.isreg(), member.size) == ("ok.txt", True, 3)
        assert archive.extractfile(member).read() == b"ok\n"  # type: ignore[union-attr]


def test_the_regression_fixtures_are_unchanged_by_the_control() -> None:
    """`make regression` and its shared fixtures hold no benign case; the control is not one."""
    fixtures = rc.build_fixtures()
    assert len(fixtures) == 5 and {fixture.kind for fixture in fixtures} == {
        "hand-hardlink",
        "fn-symlink",
    }
    assert rt.benign_archive() not in {fixture.tar for fixture in fixtures}
    assert all(fixture.kind != "benign" for fixture in fixtures)


@pytest.mark.parametrize(
    ("raw", "extracted", "words"),
    [
        (EXTRACTED, True, "ok.txt extracted, nothing declined"),
        (DECLINED, False, "declined the benign archive (linkpath escapes"),
        ({**EXTRACTED, "extract_tree": {}}, False, "ok.txt was not extracted"),
        (
            {"_run_error": True, "_reason": "TimeoutExpired"},
            False,
            "no observation (TimeoutExpired",
        ),
        ({"_run_error": True, "_rc": 125}, False, "no observation (exit 125"),
        (None, False, "no observation"),
    ],
)
def test_a_control_is_extracted_only_when_the_file_is_there_and_nothing_declined(
    raw, extracted, words
) -> None:
    run = rt.benign_from_raw(rt.benign_archive(), raw, "ok.txt")
    assert run.control.extracted is extracted and words in run.control.detail
    assert run.control.tar_sha256 == sha256(rt.benign_archive()).hexdigest()
    assert run.control.tar_path == rt.BENIGN_TAR_PATH


# -- result format: additive, optional, and no PASS without the control --------------------------


def test_a_result_without_a_control_serializes_exactly_as_before() -> None:
    data = _result().to_json_dict()
    assert "benign_control" not in data
    assert from_json_dict(data) == _result()


def test_the_control_round_trips_and_decides_the_verdict() -> None:
    assert _result(control=_control()).verdict is Verdict.PASS
    failed = _result(control=_control(False))
    assert failed.verdict is Verdict.ERROR  # declined attack inputs prove nothing here
    assert _result(c1=True, outcome="resolved", control=_control(False)).verdict is Verdict.FAIL
    assert _result(outcome="run_error", control=_control()).verdict is Verdict.ERROR
    for result in (_result(control=_control()), failed):
        data = json.loads(result.dumps())
        assert data["benign_control"]["extracted"] is result.benign_control.extracted  # type: ignore[union-attr]
        assert from_json_dict(data) == result
    stale = json.loads(failed.dumps())
    stale["verdict"] = "PASS"  # a hand-edited PASS over a failed control does not read
    with pytest.raises(TargetResultError, match="verdict"):
        from_json_dict(stale)


def test_a_control_is_refused_on_a_campaign_result_and_when_malformed() -> None:
    with pytest.raises(TargetResultError, match="only valid when mode is fixture-regression"):
        TargetResult(
            target="node-tar",
            axes=TargetAxes(target_version="7.5.23"),
            mode=ResultMode.CAMPAIGN,
            observed_contracts=("C0", "C1", "C2"),
            cases=(),
            repro_inputs=(),
            provenance=Provenance(None, False, "img:tag", None),
            campaign=CampaignInfo(seed=1, budget=None, runs_to_first_violation=None),
            benign_control=_control(),
        )
    with pytest.raises(TargetResultError, match="tar_sha256"):
        _result(control=BenignControl(True, "ok.txt", rt.BENIGN_TAR_PATH, "xyz", "d"))
    with pytest.raises(TargetResultError, match="relative and inside"):
        _result(control=BenignControl(True, "ok.txt", "../x.tar", "a" * 64, "d"))


def test_the_summary_states_the_control_and_never_headlines_pass_when_it_failed() -> None:
    ok = render_summary(
        _result(control=_control()), source_name="result.json", inputs_verified=True
    )
    assert "정상 입력 대조군: 추출됨" in ok and "**PASS**" in ok
    bad = render_summary(
        _result(control=_control(False)), source_name="result.json", inputs_verified=True
    )
    assert "**ERROR** — 정상 입력 대조군이 추출되지 않았다" in bad and "**PASS**" not in bad
    old = render_summary(_result(), source_name="result.json", inputs_verified=True)
    assert "정상 입력 대조군: 기록 없음" in old


# -- the command: one line, the record, the files, the exit code ---------------------------------


def test_verify_runs_the_control_on_the_cell_image_and_records_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list = []
    monkeypatch.setattr(nt.cri, "run_one", _node_run_one(DECLINED, EXTRACTED, seen))
    assert rt.main(["--target", "node-tar", "--version", "7.5.3", "--out", str(tmp_path)]) == 0
    image = "inodefence-node-tar-effect:7.5.3"
    assert seen[0] == (True, image)  # the control runs first, on the cell's image
    assert [benign for benign, _ in seen].count(True) == 1 and len(seen) == 1 + len(
        rc.build_fixtures()
    )
    out = capsys.readouterr().out
    assert f"BENIGN-CONTROL ok node-tar-7.5.3: ok.txt extracted, nothing declined on {image}" in out
    assert "TARGET-RUN PASS" in out and "benign=ok" in out
    cell = tmp_path / "node-tar-7.5.3"
    result = load_target_result(cell / "result.json")
    assert result.verdict is Verdict.PASS and result.benign_control is not None
    assert result.benign_control.extracted is True
    saved = (cell / result.benign_control.tar_path).read_bytes()
    assert saved == rt.benign_archive()
    assert sha256(saved).hexdigest() == result.benign_control.tar_sha256
    assert json.loads((cell / rt.BENIGN_RAW_PATH).read_text()) == EXTRACTED
    # The control is not a case: the fixture list and inputs/ are what they were.
    assert [case.case_id for case in result.cases] == [f.name for f in rc.build_fixtures()]
    assert sorted(p.name for p in (cell / "inputs").iterdir()) == sorted(
        f"{f.name}.tar" for f in rc.build_fixtures()
    )
    assert "정상 입력 대조군: 추출됨" in (cell / "summary.md").read_text()


def test_an_image_that_rejects_everything_gets_no_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The measured gap: every fixture declined used to be PASS even on a broken image."""
    monkeypatch.setattr(nt.cri, "run_one", _node_run_one(DECLINED, DECLINED))
    assert rt.main(["--target", "node-tar", "--version", "7.5.3", "--out", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert "TARGET-RUN BENIGN-CONTROL FAILED node-tar-7.5.3" in captured.err
    assert "cannot be PASS (ERROR)" in captured.err and "--auto-prepare" in captured.err
    assert "TARGET-RUN ERROR" in captured.out and "benign=FAILED" in captured.out
    assert "TARGET-RUN PASS" not in captured.out
    result = load_target_result(tmp_path / "node-tar-7.5.3" / "result.json")
    assert result.verdict is Verdict.ERROR and result.benign_control is not None
    assert result.benign_control.extracted is False
    assert all(case.outcome == "declined" for case in result.cases)  # the cases are still recorded


def test_a_violation_stays_fail_when_the_control_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(nt.cri, "run_one", _node_run_one(SHARED, DECLINED))
    assert rt.main(["--target", "node-tar", "--version", "7.5.2", "--out", str(tmp_path)]) == 1


def test_dry_run_says_the_control_will_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert rt.main(["--target", "node-tar", "--version", "7.5.3", "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["cells"]["node-tar-7.5.3"]["benign_control"] is True


# -- every target makes the control through its own run program ----------------------------------


@pytest.mark.parametrize("target", sorted(rt.TARGETS))
def test_every_target_has_a_benign_control(target: str) -> None:
    assert rt.load_adapter(target).benign is not None


def test_node_tar_registry_cells_run_the_control_offline_like_their_fixtures(monkeypatch) -> None:
    calls: list[dict] = []

    def run_one(release, tar_b64, image=None, **kw):
        calls.append({"image": image, **kw})
        return EXTRACTED

    monkeypatch.setattr(nt.cri, "run_one", run_one)
    cell = rt.RunCell("x", TargetAxes(target_version="7.5.23"), "img:registry", exploratory=True)
    assert nt.ADAPTER.benign(cell).control.extracted is True  # type: ignore[misc]
    assert calls == [{"image": "img:registry", "network_none": True}]


def test_python_tarfile_runs_the_control_under_the_cells_filter(monkeypatch) -> None:
    calls: list[tuple] = []

    def run_one(runtime, extraction_filter, tar_b64, *, image=None, **kw):
        calls.append((runtime, extraction_filter, tar_b64 == BENIGN_B64, image))
        return EXTRACTED

    monkeypatch.setattr(pt.pti, "run_one", run_one)
    (cell,) = pt.ADAPTER.cells(["3.12.16"], ["data"])
    run = pt.ADAPTER.benign(cell)  # type: ignore[misc]
    assert run.control.extracted is True and run.control.expected_path == "ok.txt"
    assert calls == [("3.12.16", "data", True, cell.image_ref)]


def test_decompress_runs_the_control_with_the_cells_package_and_version(monkeypatch) -> None:
    calls: list[tuple] = []

    def run_one(package, version, tar_b64, *, image=None, **kw):
        calls.append((package, version, tar_b64 == BENIGN_B64, image))
        return {**DECLINED, "declined": {"message": "broken"}}

    monkeypatch.setattr(dc, "run_one", run_one)
    cell = rt.RunCell("x", TargetAxes(target_version="@xhmikosr/decompress@11.1.4"), "img:dc")
    run = dc.ADAPTER.benign(cell)  # type: ignore[misc]
    assert calls == [("@xhmikosr/decompress", "11.1.4", True, "img:dc")]
    assert run.control.extracted is False and "broken" in run.control.detail


def test_oras_go_uses_its_existing_benign_archive_under_the_d_frame(monkeypatch) -> None:
    calls: list[tuple] = []

    def run_probe(version, tar_b64, sentinel_b64, image=None):
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(tar_b64))) as archive:
            calls.append((version, archive.getnames(), image))
        return {**DECLINED, "declined": None, "extract_tree": {"d": {}, "d/ok.txt": {}}}

    monkeypatch.setattr(og.ogh, "run_probe", run_probe)
    cell = rt.RunCell("x", TargetAxes(target_version="2.6.2"), "img:oras")
    run = og.ADAPTER.benign(cell)  # type: ignore[misc]
    assert calls == [("2.6.2", ["d/ok.txt"], "img:oras")]
    assert ORAS_BENIGN == [{"name": "d/ok.txt", "type": "reg", "content": b"ok\n"}]
    assert run.control.extracted is True and run.control.expected_path == "d/ok.txt"
    monkeypatch.setattr(og.ogh, "run_probe", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    assert og.ADAPTER.benign(cell).control.extracted is False  # type: ignore[misc]
