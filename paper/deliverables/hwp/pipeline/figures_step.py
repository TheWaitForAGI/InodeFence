"""Put the report figures into the filled capstone form, one table row per figure.

usage: figures_step.py <filled.hwp> <out.hwp> <spec.json>

spec.json: {"table_para": 9, "row": 29, "last_col": 15,
            "width_mm": 150, "cell_width_hwpunit": 48054, "caption_allowance_mm": 13,
            "figures": [{"path": "...png", "caption": "그림 1. ..."}, ...]}

(build_report.sh adds "tool" and resolves the figure paths.)

Works on a copy (the input is never written). Steps, all with the locally patched claw-hwp
(`LOCAL-PATCH.diff`, see the hwp-image-test-20261113 README):
  1. insert len(figures) blank rows below the caption row, merge each across the table width,
     set its width to the caption row's width and a white background (the clone source is
     shaded), then remove the original caption row so every caption has the same cell style
     (it had a list bullet);
  2. one caption per row, plain black (the cloned cell is bold);
  3. insert each figure above its caption, treated as a character, at width_mm;
  4. set each row's height to picture + caption allowance (rhwp 0.9.0 otherwise clips the caption).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path


def png_aspect(path: Path) -> float:
    """Height / width of a PNG, read from its IHDR chunk."""
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"not a PNG: {path}")
    w, h = int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    return h / w


def run_ops(tool: Path, path: Path, ops: list[dict]) -> None:
    payload = json.dumps({"path": str(path), "operations": ops}, ensure_ascii=False)
    res = subprocess.run(
        ["node", "create.js"],
        cwd=tool / "scripts",
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )
    if res.returncode != 0 or '"status":"success"' not in res.stdout:
        raise SystemExit(f"claw-hwp failed: {res.stdout[-400:]} {res.stderr[-400:]}")


def main() -> None:
    src, out, spec_path = (Path(a).resolve() for a in sys.argv[1:4])
    if src == out:
        raise SystemExit("input and output must differ")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    tool = Path(spec["tool"]).resolve()
    figs = spec["figures"]
    tp, r0, n = spec["table_para"], spec["row"], len(figs)
    cell = {"section": 0, "para": tp, "control": 0}
    shutil.copyfile(src, out)

    new_rows = [r0 + 1 + k for k in range(n)]
    run_ops(
        tool,
        out,
        [dict(type="insert_table_row", row=r0, position="below", **cell) for _ in range(n)],
    )
    last_col = spec.get("last_col", 15)
    run_ops(
        tool,
        out,
        [
            dict(type="merge_cells", from_row=r, from_col=0, to_row=r, to_col=last_col, **cell)
            for r in new_rows
        ],
    )
    width_mm = (spec["cell_width_hwpunit"] + 0.5) * 25.4 / 7200  # rounds back to the exact unit
    run_ops(
        tool,
        out,
        [dict(type="set_cell_property", row=r, col=0, width_mm=width_mm, **cell) for r in new_rows]
        + [
            dict(type="set_cell_background", row=r, col=0, background_color="#FFFFFF", **cell)
            for r in new_rows
        ],
    )
    run_ops(tool, out, [dict(type="delete_table_row", row=r0, **cell)])
    rows = [r0 + k for k in range(n)]
    run_ops(
        tool,
        out,
        [
            dict(type="set_cell_text", row=r, col=0, text=f["caption"], **cell)
            for r, f in zip(rows, figs, strict=False)
        ],
    )
    run_ops(
        tool,
        out,
        [
            {
                "type": "apply_text_style",
                "target": f["caption"],
                "bold": False,
                "italic": False,
                "color": "#000000",
            }
            for f in figs
        ],
    )
    fig_w = spec.get("width_mm", 150)
    run_ops(
        tool,
        out,
        [
            {
                "type": "insert_image",
                "path": str(Path(f["path"]).resolve()),
                "width_mm": fig_w,
                "cell": {"row": r, "col": 0, "para": tp, "control": 0, "before_para": 0},
            }
            for r, f in zip(rows, figs, strict=False)
        ],
    )
    # rhwp 0.9.0 sizes a row by the picture paragraph and leaves the caption line out; Hancom
    # treats cell height as a minimum, so declaring picture + caption height is safe for both.
    extra = spec.get("caption_allowance_mm", 13.0)
    run_ops(
        tool,
        out,
        [
            dict(
                type="set_cell_property",
                row=r,
                col=0,
                height_mm=round(fig_w * png_aspect(Path(f["path"])) + extra, 2),
                **cell,
            )
            for r, f in zip(rows, figs, strict=False)
        ],
    )
    print(f"figures: {n} rows from row {r0} → {out}")


if __name__ == "__main__":
    main()
