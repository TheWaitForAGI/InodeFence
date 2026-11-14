"""run_target_explore: target-agnostic driver (no docker; adapter/hook faked)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import scripts.run_target_explore as rte
from scripts.run_target import ExploreOutcome, PreparedTargetImage, TargetAdapter

from inodefence.target_result import ResultMode


def test_unsupported_target_reports_and_exits_3(capsys: pytest.CaptureFixture[str]) -> None:
    # python-tarfile / decompress have no explore hook yet: a real adapter, explore=None.
    assert rte.main(["--target", "decompress", "--version", "decompress@4.2.1"]) == 3
    assert "exploration is not supported for decompress" in capsys.readouterr().err


def test_dry_run_prepares_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rte, "prepare_target_image", lambda *a, **k: pytest.fail("no prepare"))
    assert rte.main(["--target", "node-tar", "--version", "latest", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["note"].startswith("dry-run")


def test_real_run_requires_auto_prepare() -> None:
    with pytest.raises(SystemExit):
        rte.main(["--target", "node-tar", "--version", "latest"])  # no --auto-prepare


def _fake_adapter(outcome: ExploreOutcome) -> TargetAdapter:
    return TargetAdapter(
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cells=lambda v, f: [],
        plan=lambda c: [],
        run=lambda c: [],
        explore=lambda prepared, options: outcome,
    )


def test_driver_prepares_then_calls_the_targets_explore_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result_path = tmp_path / "result.json"
    outcome = ExploreOutcome(result_path=result_path, verdict="FAIL", runs=20, violations=3)
    seen: dict[str, Any] = {}

    def fake_prepare(
        adapter: Any, target: str, spec: str, *, image_tag_suffix: str, filters: Any = None
    ) -> Any:
        seen["prepared"] = (target, spec)
        return PreparedTargetImage(target, spec, "7.5.23", "img:ref", "sha256:" + "c" * 64, True)

    monkeypatch.setattr(rte, "load_adapter", lambda t: _fake_adapter(outcome))
    monkeypatch.setattr(rte, "prepare_target_image", fake_prepare)
    code = rte.main(
        [
            "--target",
            "node-tar",
            "--version",
            "latest",
            "--auto-prepare",
            "--budget",
            "20",
            "--seed",
            "1",
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 1  # a violation -> exit 1
    assert seen["prepared"] == ("node-tar", "latest")
    out = capsys.readouterr().out
    assert "TARGET-EXPLORE FAIL node-tar version=7.5.23" in out and "violations=3" in out


def test_setup_error_from_prepare_is_exit_3(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def bad_prepare(*a: Any, **k: Any) -> Any:
        raise ValueError("version not found on the registry")

    outcome = ExploreOutcome(Path("x"), "PASS", 0, 0)
    monkeypatch.setattr(rte, "load_adapter", lambda t: _fake_adapter(outcome))
    monkeypatch.setattr(rte, "prepare_target_image", bad_prepare)
    assert rte.main(["--target", "node-tar", "--version", "nope", "--auto-prepare"]) == 3
    assert "TARGET-EXPLORE SETUP: version not found" in capsys.readouterr().err


def _adapter_with_option() -> tuple[TargetAdapter, dict[str, Any]]:
    from scripts.run_target import TargetOption

    captured: dict[str, Any] = {}

    def cells(versions: list[str], filters: list[str]) -> list[Any]:
        captured["filters"] = filters
        raise ValueError("stop after cells")  # we only check what reaches cells

    return TargetAdapter(
        mode=ResultMode.CAMPAIGN,
        observed_contracts=("C0", "C1", "C2"),
        cells=cells,
        plan=lambda c: [],
        run=lambda c: [],
        resolve=lambda specs: specs,
        explore=lambda prepared, options: ExploreOutcome(Path("x"), "PASS", 0, 0),
        options=(
            TargetOption("extraction-filter", "the filter", required=True, choices=("a", "b")),
        ),
    ), captured


def test_declared_target_option_is_validated_and_passed_to_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, captured = _adapter_with_option()
    monkeypatch.setattr(rte, "load_adapter", lambda t: adapter)
    # a valid value reaches cells as the filters list
    rte.main(
        [
            "--target",
            "node-tar",
            "--version",
            "latest",
            "--auto-prepare",
            "--extraction-filter",
            "b",
        ]
    )
    assert captured["filters"] == ["b"]


def test_declared_option_rejects_missing_and_unknown_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, _ = _adapter_with_option()
    monkeypatch.setattr(rte, "load_adapter", lambda t: adapter)
    with pytest.raises(SystemExit):  # required option missing
        rte.main(["--target", "node-tar", "--version", "latest", "--auto-prepare"])
    with pytest.raises(SystemExit):  # value not in choices
        rte.main(
            [
                "--target",
                "node-tar",
                "--version",
                "latest",
                "--auto-prepare",
                "--extraction-filter",
                "zzz",
            ]
        )


def test_targets_without_declared_options_are_unaffected() -> None:
    from scripts.run_target import load_adapter

    assert load_adapter("node-tar").options == ()
    assert load_adapter("oras-go").options == ()
