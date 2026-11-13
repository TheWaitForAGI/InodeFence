# ruff: noqa: E501  (W1-verified strings are kept verbatim)
"""Scene 8 slides: stop -> cause record -> approval -> resume, re-typeset from W1's verified strings.

Source of every quoted string: ~/capstone-work/team-review-20261111/W1-demo-stop-resume.md, table A
(W1 verified against the original record). No evidence file is opened here. A changed or shortened
string must go back to W1 (see STRINGS_CHANGED below, kept empty unless W1 re-verified).

    nice -n 19 python3 render_scene8.py --out <dir>
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1920, 1080
FONT_DIR = Path("/mnt/c/Windows/Fonts")
NAVY = "#2B2D63"
ACCENT = "#D55E00"
INK = "#1F2328"
MUTED = "#5F6670"
CARD = "#F3F4FA"
TERM_BG = "#14161A"
TERM_FG = "#E6E6E6"
OK = "#8BD17C"
WARN = "#FFD479"

# W1 table A, verbatim.
INJECT = "HISTORICAL_IMAGE=inodefence-node-tar-effect:does-not-exist"
STOP_EVENT = (
    '{"event": "infrastructure-stop", "reason": "3 consecutive cells left no record; '
    'infrastructure suspected, no new cell started", …}'
)
REFUSAL = (
    "infrastructure stop in effect: no new cell starts. Find the cause, then resume with "
    "--resume-after-stop <approval reference>"
)
CAUSE_COMMIT = "e195511"
APPROVAL_REF = "D042-smoke-1-B-20261111-2136"
RESUME_EVENT = (
    '{"event": "infrastructure-resume", "approval_ref": "D042-smoke-1-B-20261111-2136", …}'
)
TIMELINE = (
    ("21:12:18", "이상 주입"),
    ("21:12:32", "스스로 정지"),
    ("21:14:34", "원인 기록"),
    ("21:36", "사람 승인"),
    ("21:37:09", "재개"),
    ("21:39:39", "완료"),
)
STRINGS_CHANGED: dict[str, str] = {}  # original -> shown; must be empty unless W1 re-verified
FOOTER = "점검 기록(D042 정지 경로 점검, 2026-11-11) · 실험 결과 아님 · 원본 화면이 아니라 검증된 문자열을 다시 조판함"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def wrap(text: str, fnt: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Break at spaces (or anywhere if a token is too long) so each line fits ``width`` pixels."""
    lines: list[str] = []
    line = ""
    for token in text.split(" "):
        candidate = token if not line else f"{line} {token}"
        if fnt.getlength(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = token
        while fnt.getlength(line) > width:
            cut = len(line)
            while fnt.getlength(line[:cut]) > width:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
    if line:
        lines.append(line)
    return lines


def base(heading: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 96), fill=NAVY)
    draw.text((70, 48), heading, font=font("malgunbd.ttf", 42), fill="white", anchor="lm")
    draw.text((70, 1040), FOOTER, font=font("malgun.ttf", 24), fill=MUTED, anchor="lm")
    return image, draw


def code_block(draw: ImageDraw.ImageDraw, top: int, label: str, text: str, color: str) -> int:
    """A labelled dark block holding ``text`` verbatim; returns the next free y."""
    mono = font("consola.ttf", 30)
    draw.text((110, top), label, font=font("malgunbd.ttf", 32), fill=INK, anchor="ls")
    lines = wrap(text, mono, WIDTH - 300)
    height = 30 + 42 * len(lines)
    draw.rounded_rectangle((100, top + 18, WIDTH - 100, top + 18 + height), radius=12, fill=TERM_BG)
    for i, line in enumerate(lines):
        draw.text((130, top + 38 + 42 * i), line, font=mono, fill=color)
    return top + 18 + height + 70


def slide_stop() -> Image.Image:
    image, draw = base("정지: 인프라 이상을 결과로 섞지 않는다")
    y = 190
    y = code_block(draw, y, "① 일부러 없는 이미지를 지정(셀 프로세스에만)", INJECT, TERM_FG)
    y = code_block(
        draw, y, "② 기록 없이 끝난 셀이 세 개 이어지자 런처가 스스로 멈춤", STOP_EVENT, WARN
    )
    code_block(draw, y, "③ 승인 참조 없이 다시 호출하면 아무것도 시작하지 않음", REFUSAL, WARN)
    return image


def slide_resume() -> Image.Image:
    image, draw = base("재개: 원인 기록 → 사람 승인 → 남은 셀만")
    body = font("malgun.ttf", 34)
    bold = font("malgunbd.ttf", 34)
    mono = font("consola.ttf", 32)
    draw.text((110, 200), "④ 원인 기록", font=bold, fill=INK, anchor="ls")
    draw.text(
        (420, 200), f"LOG 커밋 {CAUSE_COMMIT} (21:14:34 KST)", font=body, fill=INK, anchor="ls"
    )
    draw.text((110, 270), "⑤ 사람 승인", font=bold, fill=INK, anchor="ls")
    draw.text((420, 270), "참조", font=body, fill=INK, anchor="ls")
    draw.text((500, 270), APPROVAL_REF, font=mono, fill=ACCENT, anchor="ls")
    draw.text(
        (500 + mono.getlength(APPROVAL_REF) + 20, 270),
        "(21:36 KST)",
        font=body,
        fill=INK,
        anchor="ls",
    )
    y = code_block(
        draw,
        340,
        "⑥ 승인 참조를 넣어야 재개, 남은 8셀만 시작(기록 없는 4셀은 다시 돌지 않음)",
        RESUME_EVENT,
        OK,
    )
    timeline(draw, y + 40)
    return image


def timeline(draw: ImageDraw.ImageDraw, top: int) -> None:
    left, right = 180, WIDTH - 180
    draw.line((left, top + 60, right, top + 60), fill=NAVY, width=6)
    step = (right - left) / (len(TIMELINE) - 1)
    for i, (clock, label) in enumerate(TIMELINE):
        x = left + step * i
        color = WARN if label == "스스로 정지" else ACCENT if label == "사람 승인" else NAVY
        draw.ellipse((x - 18, top + 42, x + 18, top + 78), fill=color, outline=NAVY, width=3)
        draw.text((x, top + 20), clock, font=font("consola.ttf", 30), fill=INK, anchor="ms")
        draw.text((x, top + 125), label, font=font("malgunbd.ttf", 32), fill=INK, anchor="ms")
    draw.text(
        (WIDTH // 2, top + 200),
        "원인 기록이 승인보다, 승인이 재개보다 앞선다(커밋 시각과 이벤트 실시간 기준)",
        font=font("malgun.ttf", 30),
        fill=MUTED,
        anchor="ms",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if STRINGS_CHANGED:
        raise SystemExit("changed strings need W1 re-verification first")
    args.out.mkdir(parents=True, exist_ok=True)
    for name, render in (("scene8-1-stop.png", slide_stop), ("scene8-2-resume.png", slide_resume)):
        render().save(args.out / name, optimize=False)
        print(args.out / name)


if __name__ == "__main__":
    main()
