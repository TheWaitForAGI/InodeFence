"""python-tarfile exploration hook: prepare producer -> controller mode -> common campaign result.

No docker. The controller run is replaced by a runner that produces the loop report exactly as the
controller mode would (``python_tarfile_exploration_report`` over the local fake backend that runs
the real worker), and writes it where the launcher script would put it.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

import pytest
import scripts.python_tarfile_explore as pte
import scripts.run_python_tarfile_target as rpt
import scripts.run_target_explore as rte
from scripts.python_tarfile_producer import ProducerImage
from scripts.run_target import ExploreOptions, PreparedTargetImage
from tests.test_python_tarfile_contained import IMAGE, _LocalBackend

from inodefence.python_tarfile_explore import python_tarfile_exploration_report
from inodefence.target_result import ResultMode, Verdict, load_target_result

RUNTIME = platform.python_version()
PREPARED = PreparedTargetImage(
    "python-tarfile", "latest", RUNTIME, f"python:{RUNTIME}-slim", "sha256:" + "a" * 64, False
)
MADE = ProducerImage(
    f"inodefence-python-tarfile-effect:{RUNTIME}",
    IMAGE,
    RUNTIME,
    "b" * 64,
    "e" * 64,
    "built, checked",
)


def _ensure(*_: Any, **__: Any) -> ProducerImage:
    return MADE


def _controller(mutate: dict[str, Any] | None = None, *, backend: Any = None):
    calls: list[dict[str, str]] = []

    def runner(cmd: list[str], *, env: dict[str, str], cwd: str) -> Any:
        assert cmd == ["bash", str(pte.LAUNCHER)]
        calls.append(env)
        try:  # what the controller mode does: an exception becomes an aborted report
            report = python_tarfile_exploration_report(
                backend or _LocalBackend(),
                IMAGE,
                env["EXTRACTION_FILTER"],
                env["RUNTIME_VERSION"],
                seed=int(env["DEMO_SEED"]),
                budget=int(env["DEMO_BUDGET"]),
            )
        except Exception as error:  # noqa: BLE001
            report = {"aborted": {"reason": str(error)}}
        report.update(mutate or {})
        path = pte.report_path(Path(env["INODEFENCE_EVIDENCE_DIR"]), env["RUN_ID"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")

        class Done:
            returncode = 0

        return Done()

    return runner, calls


def _options(tmp_path: Path, **kw: Any) -> ExploreOptions:
    base: dict[str, Any] = {
        "budget": pte.MIN_BUDGET + 1,
        "seed": 5,
        "out": tmp_path,
        "extraction_filter": "data",
    }
    base.update(kw)
    return ExploreOptions(**base)


def test_hook_writes_a_common_campaign_result_for_one_runtime_and_one_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(rpt._RESOLVED, RUNTIME, ("latest", "2026-11-15T00:00:00Z", "a", "b"))
    runner, calls = _controller()
    outcome = pte.explore(PREPARED, _options(tmp_path), runner=runner, ensure=_ensure)
    (env,) = calls
    assert env["EXPLORE_IMAGE"] == MADE.image_ref
    assert (env["RUNTIME_VERSION"], env["EXTRACTION_FILTER"]) == (RUNTIME, "data")
    result = load_target_result(outcome.result_path)
    assert result.mode is ResultMode.CAMPAIGN
    assert result.axes.runtime_version == RUNTIME and result.axes.extraction_filter == "data"
    assert result.axes.target_version is None
    assert result.executed == outcome.runs == pte.MIN_BUDGET + 1
    assert result.campaign is not None and result.campaign.seed == 5
    assert result.preparation is not None
    assert result.preparation.method == "official-image"
    assert result.preparation.requested_spec == "latest"
    assert result.preparation.producer_check == "built, checked"
    assert result.provenance.image_id == IMAGE
    assert outcome.verdict == result.verdict.value
    assert (outcome.result_path.parent / "summary.md").is_file()


@pytest.mark.parametrize(
    ("kw", "message"),
    [
        ({"extraction_filter": None}, "needs one --extraction-filter"),
        ({"extraction_filter": "fully_trusted"}, "held until approved"),
        ({"budget": 1}, "budget must be"),
    ],
)
def test_hook_refuses_before_preparing_anything(
    tmp_path: Path, kw: dict[str, Any], message: str
) -> None:
    def no_ensure(*_: Any, **__: Any) -> ProducerImage:
        raise AssertionError("must not prepare")

    with pytest.raises(ValueError, match=message):
        pte.explore(PREPARED, _options(tmp_path, **kw), ensure=no_ensure)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        ({"aborted": {"reason": "backend gone"}}, "aborted: backend gone"),
        ({"all_undetermined": True}, "undetermined"),
        ({"extraction_filter": "fully_trusted"}, "different runtime or filter"),
    ],
)
def test_untrustworthy_reports_give_no_result(
    tmp_path: Path, mutate: dict[str, Any], message: str
) -> None:
    runner, _ = _controller(mutate)
    with pytest.raises(ValueError, match=message):
        pte.explore(PREPARED, _options(tmp_path), runner=runner, ensure=_ensure)
    assert not list(tmp_path.rglob("result.json"))


def test_steps_without_verdict_make_the_result_error_not_pass(tmp_path: Path) -> None:
    runner, _ = _controller(backend=_LocalBackend(crash=True))
    with pytest.raises(ValueError, match="aborted|undetermined"):
        pte.explore(PREPARED, _options(tmp_path), runner=runner, ensure=_ensure)


def test_driver_reaches_the_hook_with_the_one_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, Any] = {}

    def fake_prepare(adapter: Any, target: str, spec: str, **kw: Any) -> PreparedTargetImage:
        seen["filter"] = kw["extraction_filter"]
        return PREPARED

    runner, _ = _controller()
    monkeypatch.setattr(rte, "prepare_target_image", fake_prepare)
    monkeypatch.setattr(pte.producer, "ensure_producer_image", _ensure)
    original = pte.run_controller
    monkeypatch.setattr(
        pte, "run_controller", lambda *a, **k: original(*a, **{**k, "runner": runner})
    )
    argv = ["--target", "python-tarfile", "--version", "latest", "--auto-prepare"]
    argv += ["--extraction-filter", "data", "--budget", str(pte.MIN_BUDGET), "--out", str(tmp_path)]
    assert rte.main(argv) in (0, 1)
    assert seen["filter"] == "data"
    out = capsys.readouterr().out
    assert f"TARGET-EXPLORE {Verdict.PASS.value}" in out or "TARGET-EXPLORE FAIL" in out


def test_python_adapter_registers_the_hook_and_keeps_axes_separate() -> None:
    assert rpt.ADAPTER.explore is not None
    with pytest.raises(ValueError):
        rpt.ADAPTER.cells(["3.14.10"], [])  # the filter axis is required, never defaulted
