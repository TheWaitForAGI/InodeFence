"""Render the InodeFence system architecture diagram (explanatory, no measured values).

The boxes follow the pipeline in ``AGENTS.md`` (Seed Generator -> Structure Mutator ->
TAR Builder -> Target Adapter -> State Observer -> Security Oracle -> Feedback / Corpus ->
next mutation). This is a concept figure, not an experiment result.

Run (host, Pillow available; Windows fonts read-only through WSL by default):
    python3 paper/figures/render_system_architecture.py
    python3 paper/figures/render_system_architecture.py --font-dir /path/to/fonts
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1600, 810
NAVY = "#2B2D63"
ACCENT = "#D55E00"
INK = "#1F2328"
MUTED = "#5F6670"
BOX_FILL = "#F3F4FA"
SANDBOX_FILL = "#FFF8E8"
SANDBOX_LINE = "#C9A227"


def font(font_dir: Path, name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_dir / name), size)


def centered(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    lines: list[tuple[str, ImageFont.FreeTypeFont, str]],
    gap: int = 8,
) -> None:
    heights = [line_font.getbbox(text)[3] for text, line_font, _ in lines]
    y = center[1] - (sum(heights) + gap * (len(lines) - 1)) / 2
    for (text, line_font, color), line_height in zip(lines, heights, strict=True):
        draw.text((center[0], y), text, font=line_font, fill=color, anchor="ma")
        y += line_height + gap


def arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    color: str = NAVY,
    width: int = 5,
) -> None:
    draw.line(points, fill=color, width=width, joint="curve")
    (x0, y0), (x1, y1) = points[-2], points[-1]
    size = 15
    if x1 == x0:
        direction = 1 if y1 > y0 else -1
        head = [
            (x1, y1),
            (x1 - size, y1 - direction * 2 * size),
            (x1 + size, y1 - direction * 2 * size),
        ]
    else:
        direction = 1 if x1 > x0 else -1
        head = [
            (x1, y1),
            (x1 - direction * 2 * size, y1 - size),
            (x1 - direction * 2 * size, y1 + size),
        ]
    draw.polygon(head, fill=color)


def box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    title: str,
    detail: str,
    title_font: ImageFont.FreeTypeFont,
    detail_font: ImageFont.FreeTypeFont,
    outline: str = NAVY,
) -> None:
    draw.rounded_rectangle(xy, radius=14, fill=BOX_FILL, outline=outline, width=3)
    center = ((xy[0] + xy[2]) / 2, (xy[1] + xy[3]) / 2)
    centered(draw, center, [(title, title_font, INK), (detail, detail_font, MUTED)])


def render(font_dir: Path, out_path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    heading = font(font_dir, "malgunbd.ttf", 44)
    title = font(font_dir, "malgunbd.ttf", 31)
    detail = font(font_dir, "malgun.ttf", 23)
    note = font(font_dir, "malgun.ttf", 25)

    draw.text((WIDTH / 2, 40), "InodeFence 탐색 루프", font=heading, fill=NAVY, anchor="ma")

    box_w, box_h = 310, 130
    top, bottom = 165, 490
    xs = [60, 445, 830, 1215]

    # Sandbox band around the two steps that touch the real filesystem.
    draw.rounded_rectangle(
        (xs[3] - 30, top - 40, xs[3] + box_w + 30, bottom + box_h + 30),
        radius=20,
        fill=SANDBOX_FILL,
        outline=SANDBOX_LINE,
        width=3,
    )
    draw.text(
        (xs[3] + box_w / 2, top - 32),
        "격리 컨테이너 · 일회용 sentinel",
        font=detail,
        fill=MUTED,
        anchor="ma",
    )

    upper = [
        ("입력 생성", "초기 TAR 구조"),
        ("구조 변형", "경로·링크·종류·순서"),
        ("TAR 생성", "변형을 파일로 빌드"),
        ("실제 extractor 실행", "adapter로 대상 분리"),
    ]
    lower = [
        ("다음 변형 선택", "가중치 · 입력 보관"),
        ("피드백", "새 상태 키 → 보상"),
        ("판정", "C0 · C1 · C2"),
        ("중간 상태 관찰", "entry별 inode · nlink"),
    ]
    for x, (name, info) in zip(xs, upper, strict=True):
        box(draw, (x, top, x + box_w, top + box_h), name, info, title, detail)
    for x, (name, info) in zip(xs, lower, strict=True):
        box(draw, (x, bottom, x + box_w, bottom + box_h), name, info, title, detail)

    upper_y = top + box_h // 2
    lower_y = bottom + box_h // 2
    for left, right in zip(xs, xs[1:], strict=False):
        arrow(draw, [(left + box_w + 8, upper_y), (right - 8, upper_y)])
        arrow(draw, [(right - 8, lower_y), (left + box_w + 8, lower_y)])
    arrow(draw, [(xs[3] + box_w // 2, top + box_h + 8), (xs[3] + box_w // 2, bottom - 8)])
    # The loop closes from next-mutation selection back to structure mutation.
    back_x = xs[0] + box_w // 2
    arrow(
        draw,
        [
            (back_x, bottom - 8),
            (back_x, (top + box_h + bottom) // 2),
            (xs[1] + box_w // 2, (top + box_h + bottom) // 2),
            (xs[1] + box_w // 2, top + box_h + 8),
        ],
        color=ACCENT,
    )
    draw.text(
        ((back_x + xs[1] + box_w // 2) / 2, (top + box_h + bottom) // 2 - 40),
        "다음 입력",
        font=detail,
        fill=ACCENT,
        anchor="ma",
    )

    footer_y = bottom + box_h + 62
    centered(
        draw,
        (WIDTH / 2, footer_y + 40),
        [
            ("adapter 적용 대상: node-tar · python-tarfile · oras-go · decompress", note, INK),
            (
                "CVE 식별자·PoC·고정 공격 패턴·대상 경로·sentinel 이름을 "
                "oracle·feedback에 넣지 않는다",
                note,
                INK,
            ),
        ],
        gap=14,
    )
    image.save(out_path, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, default=Path("/mnt/c/Windows/Fonts"))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "system-architecture.png",
    )
    args = parser.parse_args()
    render(args.font_dir, args.out)


if __name__ == "__main__":
    main()
