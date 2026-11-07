"""Render the last screen of the recorded ``make demo`` run as a report figure.

The text comes byte for byte from W2's 2026-11-07 ``script`` recording. Nothing is executed and
no output is edited. The recording's first line (session header) and its closing line are not
part of the screen. The width only decides where long lines wrap: each step fits on one row.

Run (host; needs Pillow, outside the development dependencies):
    python3 paper/figures/render_make_demo_screen.py
"""

import argparse
import hashlib
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COLUMNS = 156
ROWS = 32
CELL_W, CELL_H = 12, 26
MARGIN = 24
HEADER = 56
BACKGROUND = "#14161A"
FOREGROUND = "#E6E6E6"
NAVY = "#2B2D63"
LABEL = "make demo · node-tar 7.5.22, seed 123, budget 20 · demo run"
SUBLABEL = "실행 기록 재생(2026-11-07)"
RECORDING = Path.home() / "inodefence-evidence/demo-recordings-20261107/scene4-take1"


def screen_text(recording: Path) -> str:
    """Return the replayed bytes: what the timing file covers, without the header line."""
    data = recording.with_suffix(".typescript").read_bytes()
    start = data.index(b"\n") + 1
    timing = recording.with_suffix(".timing").read_text().splitlines()
    length = sum(int(row.split()[1]) for row in timing)
    return data[start : start + length].decode("utf-8").replace("\r\n", "\n")


def wrapped_rows(text: str) -> list[str]:
    rows: list[str] = []
    for line in text.rstrip("\n").split("\n"):
        current = ""
        width = 0
        for char in line:
            cells = 2 if unicodedata.east_asian_width(char) in "WF" else 1
            if width + cells > COLUMNS:
                rows.append(current)
                current, width = "", 0
            current += char
            width += cells
        rows.append(current)
    return rows


def render(recording: Path, font_dir: Path, out_path: Path) -> None:
    rows = wrapped_rows(screen_text(recording))[-ROWS:]
    width = COLUMNS * CELL_W + 2 * MARGIN
    height = HEADER + len(rows) * CELL_H + 2 * MARGIN
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, HEADER), fill=NAVY)
    label_font = ImageFont.truetype(str(font_dir / "malgunbd.ttf"), 26)
    sublabel_font = ImageFont.truetype(str(font_dir / "malgun.ttf"), 24)
    draw.text((MARGIN, HEADER / 2), LABEL, font=label_font, fill="white", anchor="lm")
    draw.text((width - MARGIN, HEADER / 2), SUBLABEL, font=sublabel_font, fill="white", anchor="rm")
    ascii_font = ImageFont.truetype(str(font_dir / "consola.ttf"), 22)
    wide_font = ImageFont.truetype(str(font_dir / "malgun.ttf"), 21)
    for row_index, row in enumerate(rows):
        x = MARGIN
        y = HEADER + MARGIN + row_index * CELL_H + 20
        for char in row:
            if char != " ":
                target = wide_font if ord(char) > 127 else ascii_font
                draw.text((x, y), char, font=target, fill=FOREGROUND, anchor="ls")
            x += CELL_W * (2 if unicodedata.east_asian_width(char) in "WF" else 1)
    image.save(out_path, optimize=True)
    source = hashlib.sha256(recording.with_suffix(".typescript").read_bytes()).hexdigest()
    print(f"source sha256 {source}, rows {len(rows)}")
    print(f"figure sha256 {hashlib.sha256(out_path.read_bytes()).hexdigest()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, default=RECORDING)
    parser.add_argument("--font-dir", type=Path, default=Path("/mnt/c/Windows/Fonts"))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "make-demo-screen.png",
    )
    args = parser.parse_args()
    render(args.recording, args.font_dir, args.out)


if __name__ == "__main__":
    main()
