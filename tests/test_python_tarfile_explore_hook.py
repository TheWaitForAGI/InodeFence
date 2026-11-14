"""python-tarfile exploration hook: prepare producer -> controller mode -> common campaign result.

No docker. The controller run is replaced by a runner that produces the loop report exactly as the
controller mode would (``python_tarfile_exploration_report`` over the local fake backend that runs
the real worker), and writes it where the launcher script would put it.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import scripts.python_tarfile_explore as pte
import scripts.run_python_tarfile_target as rpt
from scripts.python_tarfile_producer import ProducerImage
from scripts.run_target import ExploreOptions, PreparedTargetImage
from tests.test_python_tarfile_contained import IMAGE, _LocalBackend

from inodefence.python_tarfile_explore import python_tarfile_exploration_report
from inodefence.target_result import ResultMode, load_target_result

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


def _options(tmp_path: Path, target_options: Any = None, **kw: Any) -> Any:
    """ExploreOptions plus the target-option bundle the common driver is to carry."""
    base: dict[str, Any] = {"budget": pte.MIN_BUDGET + 1, "seed": 5, "out": tmp_path}
    base.update(kw)
    bundle = {"extraction_filter": "data"} if target_options is None else target_options
    return SimpleNamespace(**base, image_tag_suffix="", target_options=bundle)


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
    ("bundle", "kw", "message"),
    [
        ({}, {}, "needs --extraction-filter"),
        ({"extraction_filter": ["data", "fully_trusted"]}, {}, "one extraction_filter per"),
        ({"extraction_filter": "tar"}, {}, "must be one of"),
        ({"extraction_filter": "fully_trusted"}, {}, "not approved yet .D022"),
        ({"extraction_filter": ("data",)}, {"budget": 1}, "budget must be"),
    ],
)
def test_hook_refuses_before_preparing_anything(
    tmp_path: Path, bundle: dict[str, Any], kw: dict[str, Any], message: str
) -> None:
    def no_ensure(*_: Any, **__: Any) -> ProducerImage:
        raise AssertionError("must not prepare")

    with pytest.raises(ValueError, match=message):
        pte.explore(PREPARED, _options(tmp_path, bundle, **kw), ensure=no_ensure)


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


def test_options_without_a_target_option_bundle_are_refused_not_defaulted(
    tmp_path: Path,
) -> None:
    # Today's common ExploreOptions has no target-option bundle yet (IF-MAC-A adds it); the hook
    # must refuse rather than fall back to a default filter.
    options = ExploreOptions(budget=pte.MIN_BUDGET, seed=1, out=tmp_path)
    with pytest.raises(ValueError, match="needs --extraction-filter"):
        pte.explore(PREPARED, options, ensure=lambda *a, **k: pytest.fail("no prepare"))


def test_python_adapter_registers_the_hook_and_declares_its_filter_option() -> None:
    assert rpt.ADAPTER.explore is not None
    (option,) = rpt.TARGET_OPTIONS
    assert option.name == "extraction_filter" and option.required
    assert option.choices == ("fully_trusted", "data")
    assert option.explore_choices == ("data",) and option.explore_single
    assert "D022" in option.explore_held
    with pytest.raises(ValueError):
        rpt.ADAPTER.cells(["3.14.10"], [])  # the filter axis is required, never defaulted
    with pytest.raises(ValueError, match="one of"):  # regression reads the same declaration
        rpt.ADAPTER.cells(["3.14.10"], ["tar"])
