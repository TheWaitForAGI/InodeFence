"""Tests for the worker-pool planner CLI: planning + dry-run, no Docker."""

import json

import pytest
from scripts.run_worker_pool import main, plan_bringups


class _Args:
    def __init__(self, **kw: object) -> None:
        self.mode = "demo"
        self.versions: list[str] = []
        self.seeds = ["123", "456"]
        self.arms: list[str] = ["default"]
        self.budget = 50
        self.dry_run = True
        self.__dict__.update(kw)


def test_plan_bringups_one_dedicated_worker_per_cell() -> None:
    plans = plan_bringups(_Args())  # type: ignore[arg-type]
    run_ids = [plan["run_id"] for plan in plans]
    assert run_ids == ["s3wp-native-default-s123", "s3wp-native-default-s456"]
    # Each worker owns a distinct controller and volume (no shared writable path).
    controllers = {str(plan["controller"]) for plan in plans}
    volumes = {str(plan["volume"]) for plan in plans}
    assert len(controllers) == len(volumes) == 2


def test_dry_run_prints_plan_and_launches_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["--mode", "demo", "--seeds", "123,456", "--arm", "default", "--budget", "50", "--dry-run"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "workers=2" in out
    lines = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    assert {line["run_id"] for line in lines} == {
        "s3wp-native-default-s123",
        "s3wp-native-default-s456",
    }
    seeds = {line["env"]["DEMO_SEED"] for line in lines}
    assert seeds == {"123", "456"}


def test_launch_without_slot_refuses() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--mode", "demo", "--seeds", "123", "--arm", "default", "--budget", "50"])
    assert "Docker slot" in str(excinfo.value)


def test_demo_rejects_versions() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "demo", "--versions", "7.5.2", "--seeds", "123", "--dry-run"])
