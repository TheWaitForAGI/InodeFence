"""#552: a result.json with a wrong-shaped value is refused, never a traceback.

The strict reader (`target_result.from_json_dict` / `load_target_result`) either returns a result
or raises `TargetResultError` -- no `TypeError`, `AttributeError`, `KeyError`, ... escapes -- for
every variant made by replacing one value of a real result with a string, a number, an array,
null or an object (each top-level key, and each key one level inside the nested records). The CLI
commands that read results (`status`, `summary`, `compare`) then end with exit 0 or 2 and print no
traceback. A valid result reads exactly as before.
"""

from __future__ import annotations

import copy
import io
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from inodefence import cli
from inodefence.target_result import TargetResultError, from_json_dict, load_target_result

FIXTURES = Path(__file__).parent / "fixtures" / "result-contract-v1"
SAMPLES = ("fixture-regression.json", "campaign.json")  # a verify cell and an exploration
WRONG: tuple[Any, ...] = ("x", 7, [], None, {})
NESTED = ("campaign", "axes", "provenance", "preparation", "benign_control")


def _base(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _variants(data: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """``(where, variant)``: one value replaced by each wrong-shaped value."""
    for key in list(data):
        for value in WRONG:
            variant = copy.deepcopy(data)
            variant[key] = value
            yield f"{key}={value!r}", variant
    for section in NESTED:
        if isinstance(data.get(section), dict):
            for key in list(data[section]):
                for value in WRONG:
                    variant = copy.deepcopy(data)
                    variant[section][key] = value
                    yield f"{section}.{key}={value!r}", variant
    for listed in ("cases", "repro_inputs"):
        items = data.get(listed)
        if isinstance(items, list) and items and isinstance(items[0], dict):
            for key in list(items[0]):
                for value in WRONG:
                    variant = copy.deepcopy(data)
                    variant[listed][0][key] = value
                    yield f"{listed}[0].{key}={value!r}", variant


def _all_variants() -> list[tuple[str, str, dict[str, Any]]]:
    return [(name, where, v) for name in SAMPLES for where, v in _variants(_base(name))]


@pytest.mark.parametrize("name", SAMPLES)
def test_a_valid_result_reads_as_before(name: str) -> None:
    data = _base(name)
    result = from_json_dict(data)
    stored = {k: data[k] for k in ("label", "runs", "verdict", "violating_cases")}
    derived = result.to_json_dict()
    assert {k: derived[k] for k in stored} == stored  # the derived fields still match


def test_every_wrong_shape_is_a_refusal_or_a_result_never_another_error() -> None:
    leaked = []
    for name, where, variant in _all_variants():
        try:
            from_json_dict(variant)
        except TargetResultError:
            pass
        except Exception as error:  # noqa: BLE001 - the point of the test
            leaked.append(f"{name} {where}: {type(error).__name__}: {error}")
    assert leaked == []


def test_the_case_in_552_is_now_a_named_refusal() -> None:
    data = _base("fixture-regression.json")
    for value in (7, None):
        data["observed_contracts"] = value
        with pytest.raises(TargetResultError, match="malformed result: TypeError"):
            from_json_dict(data)


def test_a_non_string_input_path_is_refused_when_inputs_are_verified(tmp_path: Path) -> None:
    data = _base("fixture-regression.json")
    if not data["repro_inputs"]:
        pytest.skip("the fixture saves no input")
    data["repro_inputs"][0]["tar_path"] = 7
    path = tmp_path / "result.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TargetResultError):
        load_target_result(path, verify_inputs=True)


def _run(argv: list[str]) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    real = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = cli.main(argv)
    finally:
        sys.stdout, sys.stderr = real
    return code, out.getvalue() + err.getvalue()


def test_status_summary_and_compare_never_raise_on_a_wrong_shape(tmp_path: Path) -> None:
    failures = []
    for index, (name, where, variant) in enumerate(_all_variants()):
        cell = tmp_path / f"v{index}" / "cell"
        cell.mkdir(parents=True)
        result = cell / "result.json"
        result.write_text(json.dumps(variant), encoding="utf-8")
        for argv in (
            ["status", str(cell.parent), "--plain"],
            ["summary", str(result), "--no-verify-inputs", "--plain"],
            ["compare", str(result), str(result)],
        ):
            try:
                code, text = _run(argv)
            except Exception as error:  # noqa: BLE001 - the point of the test
                failures.append(f"{argv[0]} {name} {where}: raised {type(error).__name__}: {error}")
                continue
            if code not in (0, 2) or "Traceback" in text:
                failures.append(f"{argv[0]} {name} {where}: exit {code}")
    assert failures == []


def test_status_and_summary_on_the_552_case_say_unreadable_and_exit_2(tmp_path: Path) -> None:
    data = _base("fixture-regression.json")
    data["observed_contracts"] = 7
    cell = tmp_path / "cell"
    cell.mkdir()
    (cell / "result.json").write_text(json.dumps(data), encoding="utf-8")
    code, text = _run(["status", str(tmp_path), "--plain"])
    assert code == 2 and "unreadable (malformed result: TypeError" in text
    code, text = _run(["summary", str(cell / "result.json"), "--no-verify-inputs", "--plain"])
    assert code == 2 and text.startswith("error: malformed result: TypeError")
