"""PR-F: the operating-stop check counts cells, shows no cell, and stops nothing."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from scripts import exp_operating_check as check
from scripts.exp_operating_check import CellFiles, check_window, main

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
BUDGET = 3
SECRET = "CASE-SECRET-ORACLE"
INSIDE = NOW - timedelta(hours=1)
FORBIDDEN = (SECRET, "cell-", '"R"', '"D"', '"S-u"', "s9001", "t_first", "oracle")


class Run:
    """A run directory with the launcher's files, and an oracle value in every step and report."""

    def __init__(self, root: Path) -> None:
        self.output = root / "run"
        self.output.mkdir()
        self.cells: dict[str, CellFiles] = {}
        self.lines: list[dict[str, Any]] = []

    def _files(self, name: str) -> CellFiles:
        files = CellFiles(self.output / f"{name}.json", self.output / f"{name}.steps.jsonl", BUDGET)
        self.cells[name] = files
        return files

    def _step_lines(self, files: CellFiles, count: int, tail: str = "") -> None:
        steps = [
            {"index": i, "case_id": SECRET, "oracle": {"verdict": SECRET}} for i in range(count)
        ]
        body = "".join(json.dumps(step) + "\n" for step in steps) + tail
        files.steps.write_text(body, encoding="utf-8")

    def _attempt(
        self, name: str, number: int, when: datetime | None, returncode: int, watchdog: bool
    ) -> None:
        stamp = {"clocks": {"realtime": (when or NOW).timestamp()}}
        self.lines.append({"event": "start", "run_id": name, "attempt": number, **stamp})
        if when is not None:
            end = {"returncode": returncode, "watchdog_fired": watchdog, **stamp}
            self.lines.append({"event": "end", "run_id": name, "attempt": number, **end})

    def complete(self, when: datetime = INSIDE) -> None:
        name = f"cell-{len(self.cells)}"
        files = self._files(name)
        self._step_lines(files, BUDGET)
        files.report.write_text("report contents must not be read", encoding="utf-8")
        self._attempt(name, 1, when, 0, False)

    def aborted(self, when: datetime = INSIDE, reason: str = f"broker {SECRET}") -> None:
        name = f"cell-{len(self.cells)}"
        files = self._files(name)
        self._step_lines(files, 1)
        stub = {"step_index": 1, "reason": reason, "case_id": SECRET}
        files.report.write_text(json.dumps({"aborted": stub}), encoding="utf-8")
        self._attempt(name, 1, when, 1, False)

    def watchdog(self, when: datetime = INSIDE) -> None:
        name = f"cell-{len(self.cells)}"
        self._step_lines(self._files(name), 2, tail='{"index": 2, "cut')
        self._attempt(name, 1, when, -15, True)

    def inconsistent(self, when: datetime = INSIDE) -> None:
        name = f"cell-{len(self.cells)}"
        files = self._files(name)
        self._step_lines(files, 1)  # exit 0 with too few steps
        files.report.write_text("report contents must not be read", encoding="utf-8")
        self._attempt(name, 1, when, 0, False)

    def no_record(self, when: datetime = INSIDE) -> None:
        name = f"cell-{len(self.cells)}"
        self._files(name)
        self._attempt(name, 1, when, 1, False)
        self._attempt(name, 2, when, 1, False)

    def awaiting_retry(self, when: datetime = INSIDE) -> None:
        name = f"cell-{len(self.cells)}"
        self._files(name)
        self._attempt(name, 1, when, 1, False)

    def running(self) -> None:
        name = f"cell-{len(self.cells)}"
        self._step_lines(self._files(name), 1)
        self._attempt(name, 1, None, 0, False)

    def stop(self, kind: str = "stop") -> None:
        clocks = {"realtime": INSIDE.timestamp()}
        self.lines.append({"event": f"infrastructure-{kind}", "reason": SECRET, "clocks": clocks})

    def result(self, **options: Any) -> dict[str, Any]:
        (self.output / "cell-results.jsonl").write_text(
            "".join(json.dumps(line) + "\n" for line in self.lines), encoding="utf-8"
        )
        return check_window(self.output, self.cells, NOW, **options)


@pytest.fixture
def run(tmp_path: Path) -> Run:
    return Run(tmp_path)


@pytest.mark.parametrize(
    ("ended", "failed", "enough", "reached"),
    [
        (19, 19, False, False),  # every cell failed, but too few to read
        (20, 11, True, False),
        (20, 12, True, True),
        (100, 59, True, False),  # .59
        (100, 60, True, True),  # .60 itself
    ],
)
def test_the_rule_needs_twenty_cells_and_point_six(
    run: Run, ended: int, failed: int, enough: bool, reached: bool
) -> None:
    for _ in range(failed):
        run.aborted()
    for _ in range(ended - failed):
        run.complete()
    result = run.result()
    assert result["ended_cells"] == ended
    assert result["infrastructure_failure_rate"] == pytest.approx(failed / ended)
    assert result["min_ended_cells_met"] is enough
    assert result["stop_rate_reached"] is reached


def test_each_kind_of_failure_is_in_the_rate_and_named_apart(run: Run) -> None:
    run.complete()
    run.aborted()
    run.watchdog()
    run.no_record()
    run.inconsistent()
    result = run.result()
    assert result["ended_cells"] == 5 and result["complete"] == 1
    assert result["abort"] == 3  # stub, watchdog and no record
    assert result["abort_watchdog"] == 1 and result["no_record"] == 1
    assert result["record_inconsistent"] == 1
    assert result["infrastructure_failure_rate"] == pytest.approx(4 / 5)


def test_only_the_window_counts(run: Run) -> None:
    run.complete(NOW - timedelta(hours=24))  # the edge is inside
    run.aborted(NOW - timedelta(hours=24, seconds=1))
    run.aborted(NOW + timedelta(seconds=1))
    result = run.result()
    assert result["ended_cells"] == 1 and result["complete"] == 1 and result["abort"] == 0
    assert result["window_start"] == (NOW - timedelta(hours=24)).isoformat()


def test_running_and_retrying_cells_have_not_ended(run: Run) -> None:
    run.complete()
    run.running()
    run.awaiting_retry()
    result = run.result()
    assert result["ended_cells"] == 1 and result["infrastructure_failure_rate"] == 0
    assert result["running_cells"] == 1 and result["awaiting_retry"] == 1


def test_no_ended_cell_has_no_rate(run: Run) -> None:
    run.running()
    result = run.result()
    assert result["infrastructure_failure_rate"] is None
    assert result["stop_rate_reached"] is False


def test_a_cell_that_exited_zero_is_read_only_by_its_step_indexes(run: Run) -> None:
    run.complete()
    files = next(iter(run.cells.values()))
    files.report.write_text("this is not read", encoding="utf-8")
    assert run.result()["complete"] == 1


def test_exit_zero_with_all_steps_but_no_report_is_record_inconsistent(run: Run) -> None:
    run.complete()
    files = next(iter(run.cells.values()))
    files.report.unlink()
    result = run.result()
    assert result["ended_cells"] == 1
    assert result["complete"] == 0
    assert result["record_inconsistent"] == 1
    assert result["infrastructure_failure_rate"] == 1


def test_a_stop_in_the_record_is_shown(run: Run) -> None:
    run.complete()
    run.stop()
    assert run.result()["infrastructure_stopped"] is True
    run.stop("resume")
    assert run.result()["infrastructure_stopped"] is False


@pytest.mark.parametrize("after_stop", [False, True])
def test_no_cell_name_or_outcome_reaches_the_output(run: Run, after_stop: bool) -> None:
    run.complete()
    run.aborted(reason=f"container runtime cleanup inspect failed {SECRET}")
    run.watchdog()
    run.no_record()
    run.inconsistent()
    run.running()
    run.stop()
    text = json.dumps(run.result(after_stop=after_stop))
    for word in FORBIDDEN:
        assert word not in text, word


def test_reason_categories_appear_only_after_a_stop(run: Run) -> None:
    run.aborted(reason="container runtime cleanup inspect failed")
    run.aborted(
        when=INSIDE - timedelta(minutes=20), reason="container runtime cleanup inspect failed"
    )
    run.aborted(reason="something unrecognised")
    run.watchdog()
    run.no_record()
    run.inconsistent()
    assert "after_stop" not in run.result()
    result = run.result(after_stop=True)["after_stop"]
    assert {key: value["total"] for key, value in result.items()} == {
        "cleanup_inspect": 2,
        "other": 1,
        "watchdog": 1,
        "no-record": 1,
        "record-inconsistent": 1,
    }
    assert result["other"] == {
        "total": 1,
        "first_end_time": INSIDE.isoformat(),
        "last_end_time": INSIDE.isoformat(),
    }
    assert result["cleanup_inspect"] == {
        "total": 2,
        "first_end_time": (INSIDE - timedelta(minutes=20)).isoformat(),
        "last_end_time": INSIDE.isoformat(),
    }
    assert "end_times" not in json.dumps(result)


def test_a_cached_cell_is_not_read_again_until_its_files_change(run: Run, monkeypatch) -> None:
    run.complete()
    cache: dict[str, Any] = {}
    calls: list[str] = []
    inner = check._classify

    def counted(files: CellFiles, attempts: Any) -> Any:
        calls.append(files.steps.name)
        return inner(files, attempts)

    monkeypatch.setattr(check, "_classify", counted)
    assert run.result(cache=cache)["complete"] == 1
    assert run.result(cache=cache)["complete"] == 1
    assert len(calls) == 1
    files = next(iter(run.cells.values()))
    files.steps.write_text('{"index": 0}\n', encoding="utf-8")
    assert run.result(cache=cache)["record_inconsistent"] == 1
    assert len(calls) == 2


def test_cache_keys_hide_run_ids_and_reject_legacy_plaintext_keys(run: Run, tmp_path: Path) -> None:
    run.complete()
    run.aborted()
    cache: dict[str, Any] = {}
    run.result(cache=cache)
    serialized = json.dumps(cache)
    assert len(cache) == 2
    assert all(key.startswith("sha256:") and len(key) == 71 for key in cache)
    assert "cell-0" not in serialized and "cell-1" not in serialized
    assert SECRET not in serialized

    old = tmp_path / "old-cache.json"
    old.write_text(json.dumps({"cell-0": {"key": "old"}, **cache}), encoding="utf-8")
    loaded = check._load_cache(old)
    assert loaded == cache
    assert "cell-0" not in json.dumps(loaded)


def test_a_cell_the_registration_does_not_plan_is_refused_without_its_name(run: Run) -> None:
    run.complete()
    run.cells.clear()
    with pytest.raises(ValueError) as error:
        run.result()
    assert "cell-0" not in str(error.value)


# ---- command line ------------------------------------------------------------------------------

PREREGISTRATION = """```preregistration
engine_sha = 0123456789abcdef0123456789abcdef01234567
targets.node-tar-7.5.2.extractor = node-tar
targets.node-tar-7.5.2.version = 7.5.2
targets.node-tar-7.5.2.image_digest = sha256:{digest}
targets.node-tar-7.5.2.role = train
targets.node-tar-7.5.2.hypothesis = H-A
targets.node-tar-7.5.2.exposure = pre-exposed
targets.node-tar-7.5.2.exposure_ref = node-tar@7.5.2
exposure_ledger = exposure-ledger.md
exposure_ledger_sha256 = {ledger}
seeds = 9001, 9002
budget = 3
vocabulary = observed-names
arm.R = unretained-walk-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = 9001
sentinel_count = 3
observer_integrity_policy = invalid-continue
hit_definition = c1-or-c2-and-contract-violated
c0_counts_as_hit = false
denominator = all-cells-including-abort
abort_reporting = right-censored
rule_of_three_unit = campaign
```
"""


@pytest.fixture
def cli(tmp_path: Path, monkeypatch) -> tuple[list[str], Path]:
    file = tmp_path / "exp3.md"
    file.write_text(
        PREREGISTRATION.format(digest="ab" * 32, ledger="cd" * 32),
        encoding="utf-8",
    )
    output = tmp_path / "run"
    output.mkdir()
    (output / "cell-results.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(check.os, "nice", lambda increment: 0)
    monkeypatch.setenv("HOME", str(tmp_path))
    return ["--preregistration", str(file), "--output", str(output)], tmp_path


def test_the_command_line_prints_counts_and_lowers_its_priority(
    cli: tuple[list[str], Path], monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args, tmp_path = cli
    calls: list[int] = []
    monkeypatch.setattr(check.os, "nice", calls.append)
    out, cache = tmp_path / "result.json", tmp_path / "cache.json"
    assert main([*args, "--out", str(out), "--cache", str(cache)]) == 0
    assert calls == [19]
    printed = json.loads(capsys.readouterr().out)
    assert printed["ended_cells"] == 0 and printed["stop_rate_reached"] is False
    assert json.loads(out.read_text(encoding="utf-8")) == printed
    assert json.loads(cache.read_text(encoding="utf-8")) == {}


@pytest.mark.parametrize("option", ["--out", "--cache"])
@pytest.mark.parametrize(
    "where", ["inodefence-evidence/check.json", "run/check.json", "repository"]
)
def test_nothing_is_written_inside_the_evidence_or_the_repository(
    cli: tuple[list[str], Path], option: str, where: str, capsys: pytest.CaptureFixture[str]
) -> None:
    args, tmp_path = cli
    target = (
        Path(check.__file__).resolve().parents[1] / "check-should-not-exist.json"
        if where == "repository"
        else tmp_path / where
    )
    assert main([*args, option, str(target)]) == 2
    assert not target.exists()
    assert "outside" in capsys.readouterr().err


def test_a_single_key_registration_is_refused(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(check.os, "nice", lambda increment: 0)
    output = tmp_path / "run"
    output.mkdir()
    file = tmp_path / "exp0.md"
    lines = PREREGISTRATION.format(digest="ab" * 32, ledger="cd" * 32).splitlines(keepends=True)
    kept = [line for line in lines if not line.startswith(("targets.", "exposure_ledger"))]
    kept.insert(1, f"image_digest = sha256:{'ab' * 32}\n")
    file.write_text("".join(kept), encoding="utf-8")
    assert main(["--preregistration", str(file), "--output", str(output)]) == 2
    assert "targets.<id>" in capsys.readouterr().err
