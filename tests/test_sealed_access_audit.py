"""#520 D2: the running access audit counts sealed reads from both sides (synthetic data)."""

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sealed_access_audit", ROOT / "scripts/sealed_access_audit.py"
)
assert SPEC is not None and SPEC.loader is not None
saa = importlib.util.module_from_spec(SPEC)
sys.modules["sealed_access_audit"] = saa
SPEC.loader.exec_module(saa)

SEALED = "/runs/exp2-holdout/"


def tool_use(time, name, tool_input):
    return {
        "timestamp": time,
        "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]},
    }


def tool_result(time, text):
    return {
        "timestamp": time,
        "message": {
            "content": [{"type": "tool_result", "content": [{"type": "text", "text": text}]}]
        },
    }


def write_session(directory: Path, name: str, records: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    (directory / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_both_sides_counted(tmp_path):
    sessions = tmp_path / "sessions"
    write_session(
        sessions,
        "a.jsonl",
        [
            tool_use(
                "2026-11-16T00:40:00Z",
                "Bash",
                {"command": f"python scripts/sealed_log_view.py {SEALED}s1/launcher.log"},
            ),
            tool_use("2026-11-16T00:44:00Z", "Bash", {"command": f"tail -n 50 {SEALED}s2/out.log"}),
            tool_use("2026-11-16T00:45:00Z", "Read", {"file_path": f"{SEALED}s3/report.json"}),
            tool_use("2026-11-16T00:46:00Z", "Bash", {"command": "ls /tmp"}),
            # path built in a variable: the command side cannot see it, the output side does
            tool_use("2026-11-16T00:47:00Z", "Bash", {"command": 'tail "$D/out.log"'}),
            tool_result(
                "2026-11-16T00:47:01Z",
                "step 1329/2000  op  complete  C0 ok C1 ok C2 VIOLATED  reward 1",
            ),
            tool_result("2026-11-16T00:48:00Z", "==> [cell] docker inspect timeout"),
        ],
    )
    # subagent transcripts sit in subfolders
    write_session(
        sessions / "sub", "b.jsonl", [tool_result("2026-11-16T01:00:00Z", '{"violated": true}')]
    )
    history = tmp_path / "bash_history"
    history.write_text(f"cat {SEALED}s4/report.json\nls\n", encoding="utf-8")

    report = saa.audit([SEALED], [sessions], [history]).as_json()
    assert report["command_side"]["allowed"] == 1
    assert report["command_side"]["점검 필요"] == 3
    assert report["output_side"]["점검 필요"] == 2
    # counts and times only: no command text, result text or path in the output
    text = json.dumps(report, ensure_ascii=False)
    assert SEALED not in text and "VIOLATED" not in text and "tail" not in text


def test_since_window(tmp_path):
    sessions = tmp_path / "s"
    write_session(
        sessions,
        "a.jsonl",
        [
            tool_use("2026-11-15T00:00:00Z", "Bash", {"command": f"cat {SEALED}x"}),
            tool_use("2026-11-16T00:00:00Z", "Bash", {"command": f"cat {SEALED}y"}),
        ],
    )
    since = datetime(2026, 11, 15, 12, tzinfo=UTC)
    report = saa.audit([SEALED], [sessions], [], since).as_json()
    assert report["command_side"]["점검 필요"] == 1
    assert report["command_side"]["점검 필요 시각"] == ["2026-11-16T00:00:00Z"]
