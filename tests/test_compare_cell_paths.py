"""compare_cell_paths (D047 section 7): judgement hashes, terminations, m_x, explanation, sealed."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from scripts import compare_cell_paths
from scripts.run_effect_demo import synthetic_demo_report

from inodefence.feedback import EffectSearchPolicy
from inodefence.mutator import MutationPolicy

POLICY = EffectSearchPolicy("structure-coverage-v1-uniform-mutation-v1")
MUTATION = MutationPolicy("uniform-generic-m1-state-aware-escape-hardlink-fixed-baseline-v1")


def steps(seed: int = 9001, budget: int = 6) -> list[dict[str, Any]]:
    report: dict[str, Any] = synthetic_demo_report(seed, budget, POLICY, MUTATION)
    return copy.deepcopy(list(report["steps"]))


def write(
    tmp_path: Path, name: str, records: list[dict[str, Any]], reexecutions: int | None = None
) -> Path:
    path = tmp_path / f"{name}.steps.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    if reexecutions is not None:
        report = {"infra_reexecutions": [{}] * reexecutions, "oracle_summary": {"c1": 1}}
        (tmp_path / f"{name}.json").write_text(json.dumps(report), encoding="utf-8")
    return path


def flip_judgement(records: list[dict[str, Any]], index: int) -> list[dict[str, Any]]:
    """Same case ids and terminations; only the oracle judgement of one step differs."""
    changed = copy.deepcopy(records)
    oracle = changed[index]["oracle"]
    for contract in oracle.values():
        if isinstance(contract, dict) and "violated" in contract:
            contract["violated"] = not contract["violated"]
            break
    else:
        changed[index]["oracle"] = {**oracle, "C1": {"violated": True}}
    return changed


def test_a_difference_in_judgement_only_is_a_difference(tmp_path: Path) -> None:
    base = steps()
    same = write(tmp_path, "a", base), write(tmp_path, "b", base)
    judgement = write(tmp_path, "c", base), write(tmp_path, "d", flip_judgement(base, 2))
    result = compare_cell_paths.compare_pairs({"same": same, "judgement": judgement})
    assert result["cells"]["same"]["differs"] is False
    cell = result["cells"]["judgement"]
    assert cell["differs"] is True
    assert cell["case_sequence_same"] is True and cell["judgements_same"] is False
    assert result["summary"]["m_x"] == 1 and result["differing_cells"] == ["judgement"]


def test_one_sided_congestion_and_incomparable_are_counted(tmp_path: Path) -> None:
    base = steps()
    timed = copy.deepcopy(base)
    timed[3]["feedback"]["trace_termination"] = "timed_out"
    pairs = {
        "congested": (write(tmp_path, "a", base), write(tmp_path, "b", timed)),
        "gone": (write(tmp_path, "c", base), tmp_path / "missing.steps.jsonl"),
        "reexec": (write(tmp_path, "e", base, 2), write(tmp_path, "f", flip_judgement(base, 1), 0)),
    }
    summary = compare_cell_paths.compare_pairs(pairs)["summary"]
    assert summary["m_x"] == 2 and summary["incomparable"] == 1
    assert summary["one_sided_congestion"] == 1
    assert summary["with_reexecutions"] == ["reexec"]
    assert summary["differing_with_reexecutions"] == ["reexec"]
    assert summary["needs_explanation"] is True


def test_the_explanation_names_which_host_is_nondeterministic(tmp_path: Path) -> None:
    base, other = steps(), flip_judgement(steps(), 2)
    cross = {
        label: (write(tmp_path, f"{label}-h1", base), write(tmp_path, f"{label}-h2", other))
        for label in ("h2only", "h1only", "unexplained", "norerun")
    }
    compared = compare_cell_paths.compare_pairs(cross)
    reruns = {
        "HOST1": {
            "h2only": (cross["h2only"][0], write(tmp_path, "h2only-h1r", base)),
            "h1only": (cross["h1only"][0], write(tmp_path, "h1only-h1r", flip_judgement(base, 4))),
            "unexplained": (cross["unexplained"][0], write(tmp_path, "un-h1r", base)),
        },
        "HOST2": {
            "h2only": (cross["h2only"][1], write(tmp_path, "h2only-h2r", base)),
            "h1only": (cross["h1only"][1], write(tmp_path, "h1only-h2r", other)),
            "unexplained": (cross["unexplained"][1], write(tmp_path, "un-h2r", other)),
        },
    }
    explanation = compare_cell_paths.explain(compared, reruns)
    cells = explanation["cells"]
    assert cells["h2only"]["status"] == "explained by nondeterminism"
    assert cells["h1only"]["status"] == "explained by nondeterminism"
    assert cells["unexplained"]["status"] == "unexplained host-dependent"
    assert cells["norerun"]["status"] == "not re-run"
    assert explanation["host1_only_nondeterminism"] == 1
    assert explanation["host2_only_nondeterminism"] == 1
    assert explanation["unexplained_host_dependent"] == 1
    assert explanation["serious_difference"] is False


def test_the_output_holds_no_case_id_hash_or_oracle_value(tmp_path: Path) -> None:
    base = steps()
    left, right = write(tmp_path, "a", base, 1), write(tmp_path, "b", flip_judgement(base, 2))
    out = tmp_path / "c.json"
    argv = [
        "--pair",
        f"cell={left},{right}",
        "--rerun",
        f"HOST1:cell={left},{left}",
        "--out",
        str(out),
    ]
    assert compare_cell_paths.main(argv) == 0
    text = out.read_text()
    for record in base:
        assert record["case_id"] not in text
    for word in ("violated", "contract", "C1", "C2", "oracle_summary", "fingerprint"):
        assert word not in text


@pytest.mark.parametrize("bad", ["cell=a", "HOST3:cell=a,b"])
def test_malformed_pairs_are_refused(bad: str) -> None:
    flag = "--rerun" if bad.startswith("HOST") else "--pair"
    with pytest.raises(SystemExit):
        compare_cell_paths.main(["--pair", "x=a,b", flag, bad, "--out", "/dev/null"])
