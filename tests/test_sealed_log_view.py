"""#520 D1: the sealed log viewer shows infrastructure lines only. Synthetic lines, no run data."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sealed_log_view", ROOT / "scripts/sealed_log_view.py"
)
assert SPEC is not None and SPEC.loader is not None
slv = importlib.util.module_from_spec(SPEC)
sys.modules["sealed_log_view"] = slv
SPEC.loader.exec_module(slv)

# The shape of a campaign step line (effect_demo._render_step), with made-up values.
STEP_LINE = (
    "step 1329/2000  escape-hardlink  complete  events  3  nlink>1 0  "
    "C0 ok C1 ok C2 VIOLATED  new-keys 1  reward 0.5  corpus 7->8"
)
ABORT_LINE = "aborted: step 41 case 3fa9c1d2e4b5"


def test_step_line_is_hidden():
    assert not slv.shown(STEP_LINE)


def test_abort_line_is_shown():
    assert slv.shown(ABORT_LINE)


def test_infra_lines_are_shown():
    for line in (
        "==> [cell s9041 R]",
        'inodefence-infra-reexecution {"schema": "inodefence-infra-reexecution-v1"}',
        'inodefence-docker-call {"call": "inspect", "seconds": 10.0}',
        "FAILED at step: run-campaign (exit 125)",
        "start gate: not acknowledged: cleanup UNKNOWN",
        "Traceback (most recent call last):",
        '  File "/work/scripts/run_exp0.py", line 120, in main',
        "docker.errors.BackendError: daemon not responding",
        "evidence: /var/tmp/x/evidence/block-1.json",
    ):
        assert slv.shown(line), line


def test_deny_pass_inside_allowed_lines():
    for line in (
        'inodefence-docker-call {"oracle": {"C1": true}}',
        "evidence: C1 internal/sentinel path pairs",
        "==> [C2 violated]",
        "FAILED at step: reward check",
        "start gate: first hit at step 685",
    ):
        assert not slv.shown(line), line


def test_other_lines_are_hidden_and_collapsed():
    out, read, hidden = slv.view(["==> [a]", "x", "y", STEP_LINE, ABORT_LINE, "z"])
    assert out == ["==> [a]", "[가림] 3줄", ABORT_LINE, "[가림] 1줄"]
    assert (read, hidden) == (6, 4)


def test_every_call_is_audited(tmp_path, capsys):
    log = tmp_path / "launcher.log"
    log.write_text("==> [start]\n" + STEP_LINE + "\n", encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    assert slv.main([str(log), "--audit", str(audit)]) == 0
    assert slv.main([str(log), "--audit", str(audit), "--tail", "1"]) == 0
    records = [json.loads(x) for x in audit.read_text(encoding="utf-8").splitlines()]
    assert [r["lines_hidden"] for r in records] == [1, 1]
    assert records[1]["tail"] == 1 and records[0]["tool"] == "sealed_log_view"
    printed = capsys.readouterr().out
    assert "VIOLATED" not in printed and "reward" not in printed


# Line shapes from the registered run's logs (W4, after the unseal), values redacted.
REAL_STEP = (
    "step 1329/2000  remove_entry                success   events 15  nlink>1 2  "
    "C0 ok C1 ok C2 ok  new-keys 0  reward 0  corpus 42->42"
)
REAL_INFRA = (
    "effect-demo-historical aborted: step 1330 case " + "a" * 64 + ": "
    "inodefence.execution.base.BackendError: container runtime cleanup inspect failed",
    '  |   File "/work/scripts/container_host.py", line 1034, in <module>',
    "    | inodefence.execution.base.BackendError: container runtime cleanup inspect failed: ",
    "  + Exception Group Traceback (most recent call last):",
    "  | ExceptionGroup: host target cleanup failed (7 sub-exceptions)",
    "INODEFENCE_CLEANUP_UNKNOWN: host target cleanup failed: BackendError: inspect timed out",
    "start gate: verdict not recorded: RuntimeError: node-tar-holdout-S-u-s9048: "
    "UNKNOWN verdict is final",
    'inodefence-infra-reexecution {"absence": {}, "action": "abort_case_bound", '
    '"anomalous_calls": []}',
    'inodefence-docker-call {"absent": false, "container": "inodefence-x", '
    '"op": "container inspect", "returncode": -9}',
    "FAILED at step: effect-demo-historical (exit 1)",
)


def test_real_infra_shapes_are_shown():
    for line in REAL_INFRA:
        assert slv.shown(line), line


def test_real_step_line_is_masked():
    assert not slv.shown(REAL_STEP)
    # even behind a gutter or a label that an allow pattern could accept
    assert not slv.shown("  | " + REAL_STEP)
    assert not slv.shown("effect-demo-historical " + REAL_STEP)
    assert not slv.shown("evidence: " + REAL_STEP)
