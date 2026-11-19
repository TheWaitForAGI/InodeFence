"""Result screens: verify (after the driver) and ``inodefence compare``.

Built from the stored contract fixture (tests/fixtures/result-contract-v1), nothing is run.
Off a terminal nothing is added after verify's driver lines (byte-identical, same exit code);
``compare`` prints plain lines there. Values the file does not hold are ``?``, never invented;
"same input" only when both recorded SHA-256 values are equal.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from inodefence import cli
from inodefence.app import runs
from inodefence.ui import console

FIXTURE = Path(__file__).parent / "fixtures" / "result-contract-v1" / "fixture-regression.json"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _visible(text: str) -> str:
    plain = _ANSI.sub("", text)
    for ch in "│╭╮╰╯─":
        plain = plain.replace(ch, " ")
    return " ".join(plain.split())


def _cell(root: Path, name: str, data: dict[str, Any]) -> Path:
    cell = root / name
    (cell / "inputs").mkdir(parents=True)
    for item in data["repro_inputs"]:
        (cell / item["tar_path"]).write_bytes(b"x")
    (cell / "result.json").write_text(json.dumps(data), encoding="utf-8")
    return cell / "result.json"


def _fixed(data: dict[str, Any]) -> dict[str, Any]:
    """A consistent PASS copy of the fixture (same inputs): no case violated."""
    fixed = copy.deepcopy(data)
    fixed["axes"]["target_version"] = "7.5.3"
    fixed["verdict"] = "PASS"
    fixed["violating_cases"] = []
    for case in fixed["cases"]:
        case["c1"] = case["c2"] = False
    return fixed


@pytest.fixture
def two_results(tmp_path: Path) -> tuple[Path, Path]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return _cell(tmp_path, "node-tar-7.5.2", data), _cell(tmp_path, "node-tar-7.5.3", _fixed(data))


def _rich_terminal(monkeypatch) -> None:
    pytest.importorskip("rich")
    monkeypatch.setattr(console, "interactive", lambda stream, environ=None: True)


def test_verify_adds_nothing_off_a_terminal(monkeypatch, capsys, tmp_path, two_results) -> None:
    def driver(driver: str, argv: list[str], command: str) -> int:
        print("TARGET-RUN FAIL target=node-tar version=7.5.2 violating=1/2")
        return 1

    monkeypatch.setattr(cli, "_forward", driver)
    monkeypatch.setattr(cli, "_resolve_out", lambda args, name: two_results[0].parents[1])
    code = cli.main(["verify", "--version", "7.5.2"])
    assert code == 1  # the driver's code
    assert (
        capsys.readouterr().out == "TARGET-RUN FAIL target=node-tar version=7.5.2 violating=1/2\n"
    )


def test_verify_on_a_rich_terminal_shows_this_runs_cells_after_the_driver_lines(
    monkeypatch, capsys, tmp_path
) -> None:
    _rich_terminal(monkeypatch)
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out = tmp_path / "out"
    old = _cell(out, "node-tar-7.5.3", _fixed(data))
    __import__("os").utime(old, (1, 1))  # written by an earlier run: not shown

    def driver(driver: str, argv: list[str], command: str) -> int:
        print("TARGET-RUN FAIL target=node-tar version=7.5.2 violating=1/2")
        _cell(out, "node-tar-7.5.2", data)
        return 1

    monkeypatch.setattr(cli, "_forward", driver)
    monkeypatch.setattr(cli, "_resolve_out", lambda args, name: out)
    assert cli.main(["verify", "--version", "7.5.2"]) == 1
    printed = capsys.readouterr().out
    assert printed.startswith("TARGET-RUN FAIL target=node-tar version=7.5.2 violating=1/2\n")
    seen = _visible(printed)
    assert "› verify" in seen and "cell node-tar-7.5.2" in seen and "node-tar-7.5.3" not in seen
    assert "✗ FAIL" in seen and "FAIL 1/2 0 C1 C2 verdict violating errored contracts" in seen
    assert "toplevel_hardlink 1ed8b2e2d328… resolved ? V V" in seen  # C0 not judged: ?
    assert "nested_hardlink ? declined" in seen  # no saved input: ?, not invented
    assert "1 of 2 cases violated a contract" in seen


def test_verify_dry_run_draws_nothing(monkeypatch, capsys, tmp_path) -> None:
    _rich_terminal(monkeypatch)
    monkeypatch.setattr(cli, "_forward", lambda *a: 0)
    monkeypatch.setattr(cli, "_resolve_out", lambda args, name: tmp_path)
    assert cli.main(["verify", "--version", "7.5.2", "--dry-run"]) == 0
    assert capsys.readouterr().out == ""


def test_compare_plain_lists_each_case_and_says_same_only_for_equal_hashes(
    capsys, two_results
) -> None:
    a, b = two_results
    assert cli.main(["compare", str(a), str(b)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "\x1b" not in "\n".join(out)
    assert "verdict: A FAIL  B PASS" in out
    toplevel = next(line for line in out if line.startswith("toplevel_hardlink"))
    nested = next(line for line in out if line.startswith("nested_hardlink"))
    assert "✓ same" in toplevel and "same" not in nested.split()[1]
    assert "unknown" in nested  # no recorded SHA-256 on either side


def test_compare_marks_a_different_input(capsys, tmp_path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    other = _fixed(data)
    other["repro_inputs"][0]["tar_sha256"] = "0" * 64
    a, b = _cell(tmp_path, "a", data), _cell(tmp_path, "b", other)
    rows = runs.compare_results(runs.read_result(a), runs.read_result(b))
    assert [row.same_input for row in rows] == [False, None]
    cli.main(["compare", str(a), str(b)])
    assert "✗ different" in capsys.readouterr().out


def test_compare_on_a_rich_terminal(monkeypatch, capsys, two_results) -> None:
    _rich_terminal(monkeypatch)
    a, b = two_results
    assert cli.main(["compare", str(a), str(b)]) == 0
    seen = _visible(capsys.readouterr().out)
    assert "› compare" in seen and "1/2 0 0 1 same input" in seen
    assert "1 of 2 cases ran the same input" in seen and "unknown" in seen
    assert "A ✗ FAIL B ✓ PASS" in seen


def test_compare_an_unreadable_result_is_exit_2(capsys, tmp_path, two_results) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert cli.main(["compare", str(two_results[0]), str(broken)]) == 2
    assert "B: result" in capsys.readouterr().out


def test_an_as_stored_result_is_marked_not_shown_as_validated(
    monkeypatch, capsys, tmp_path
) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["verdict"] = "PASS"  # inconsistent with the cases: the strict reader refuses it
    a = _cell(tmp_path, "a", data)
    assert runs.read_result(a).read_state is runs.ReadState.UNVALIDATED
    cli.main(["compare", str(a), str(a)])
    assert "A: as stored, not validated:" in capsys.readouterr().out
    _rich_terminal(monkeypatch)
    cli.main(["compare", str(a), str(a)])
    assert "! AS STORED not validated" in _visible(capsys.readouterr().out)
