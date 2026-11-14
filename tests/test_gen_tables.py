"""The M2 table generator reproduces the committed table byte-identically from summary.json."""

import json
from pathlib import Path

from scripts import gen_table_m2

REPO = Path(__file__).resolve().parents[1]


def test_m2_render_byte_identical_to_committed() -> None:
    committed = (REPO / "paper/tables/m2-cross-release-evidence.md").read_text(encoding="utf-8")
    assert gen_table_m2.render() == committed


def test_m2_check_modes(tmp_path: Path) -> None:
    good = REPO / "paper/tables/m2-cross-release-evidence.md"
    assert gen_table_m2.main(["--check", str(good)]) == 0
    tampered = tmp_path / "t.md"
    tampered.write_text(good.read_text(encoding="utf-8") + "x", encoding="utf-8")
    assert gen_table_m2.main(["--check", str(tampered)]) == 1


def test_m2_grid_is_bound_to_summary_json() -> None:
    # Flipping a rejected cell to shared must change the rendered grid (genuine binding).
    summary = json.loads(gen_table_m2.summary_path().read_text(encoding="utf-8"))
    base = gen_table_m2.build(summary)
    summary["toplevel_hardlink"]["per_release_shared"]["7.5.3"] = True
    assert gen_table_m2.build(summary) != base
