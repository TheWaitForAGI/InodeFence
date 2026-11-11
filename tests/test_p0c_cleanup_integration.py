"""Synthetic integration of P0-B shell status and the #297 targets-form launcher."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as launcher

from test_local_node_tar_smoke import run_fake_docker
from test_run_exp0 import (
    BEFORE,
    TARGET_IMAGES,
    VICTIM,
    _cell,
    _deadline_setup,
    _fake_runner,
    _index,
    _result_lines,
)
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine

pytestmark = pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")


@pytest.mark.parametrize(
    ("scenario", "controller", "volume", "host", "exit_code", "state", "attempts"),
    [
        ("complete", 0, 0, 0, 0, "complete", 1),
        ("complete", 41, 0, 0, 41, "record-inconsistent", 1),
        ("complete", 0, 42, 0, 42, "record-inconsistent", 1),
        ("complete", 41, 42, 0, 41, "record-inconsistent", 1),
        ("abort", 41, 42, 37, 37, "abort-final", 1),
        ("missing", 41, 0, 0, 41, "no-record", 2),
        ("bad", 41, 0, 0, 41, "record-inconsistent", 1),
        ("watchdog", 41, 0, 0, 41, "abort-final", 1),
    ],
)
def test_shell_exit_and_launcher_classification(
    tmp_path: Path,
    monkeypatch,
    scenario: str,
    controller: int,
    volume: int,
    host: int,
    exit_code: int,
    state: str,
    attempts: int,
) -> None:
    shell_dir = tmp_path / "shell"
    shell_dir.mkdir()
    shell, calls = run_fake_docker(shell_dir, controller, volume, host)
    assert shell.returncode == exit_code
    if controller:
        assert "FAILED cleanup: controller" in shell.stderr
    if volume:
        assert "FAILED cleanup: volume" in shell.stderr
    # H1 cleanup order (#317-#329): controller removed by id, then confirmed absent; then the
    # volume's owner checked, removed, confirmed absent. Removal stays the last mutating calls.
    assert [call.split(" {{")[0].rsplit(" ", 1)[0] for call in calls[-5:]] == [
        "rm -f",
        "container inspect",
        "volume inspect",
        "volume rm",
        "volume inspect",
    ]
    assert calls[-4] == "container inspect inodefence-local-controller-test"
    assert calls[-3].startswith("volume inspect --format ")
    assert calls[-1] == "volume inspect inodefence-local-runtime-test"
    assert calls[-5] == f"rm -f {'a' * 64}"
    assert calls[-2] == "volume rm inodefence-local-runtime-test"

    out, args, _clock = _deadline_setup(tmp_path, monkeypatch, BEFORE, jobs="1")
    behavior: dict[str, Any] = dict(TARGET_IMAGES)
    if scenario == "abort":
        behavior["abort"] = {VICTIM}
    inner = _fake_runner(behavior)

    def runner(cell, output, env, bash, **limits):
        result = inner(cell, output, env, bash, **limits)
        if cell.run_id != VICTIM:
            return result
        paths = _cell(args, VICTIM, output)
        if scenario == "missing":
            paths["report"].unlink()
            paths["steps_jsonl"].unlink()
        elif scenario == "bad":
            paths["steps_jsonl"].write_text('{"index": 9}\n', encoding="utf-8")
        elif scenario == "watchdog":
            paths["report"].unlink()
            lines = paths["steps_jsonl"].read_text(encoding="utf-8").splitlines()
            paths["steps_jsonl"].write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")
            # #297 substitutes its watchdog return code for the shell's exit status.
            return replace(
                result,
                returncode=launcher.WATCHDOG_RETURNCODE,
                watchdog_fired=True,
                evidence_exists=False,
            )
        return replace(result, returncode=shell.returncode)

    monkeypatch.setattr(launcher, "run_cell_with_watchdog", runner)
    launcher.main(args)
    index = _index(out)
    assert index["interim"]["cell_states"][VICTIM] == state
    assert inner.calls.count(VICTIM) == attempts
    summary = index["cell_completeness"]
    assert summary["record_inconsistent"] == int(state == "record-inconsistent")
    assert summary["aborts"] == int(state in ("abort-final", "no-record"))
    if scenario == "complete" and exit_code:
        assert summary["inconsistent_checks"][VICTIM] == ["complete-report-with-a-nonzero-exit"]
    if scenario == "watchdog":
        end = next(
            r for r in _result_lines(out) if r.get("run_id") == VICTIM and r["event"] == "end"
        )
        assert end["watchdog_fired"] is True and end["returncode"] == launcher.WATCHDOG_RETURNCODE
        assert summary["watchdog"] == 1
    restart = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(launcher, "run_cell_with_watchdog", restart)
    launcher.main(args)
    assert VICTIM not in restart.calls
