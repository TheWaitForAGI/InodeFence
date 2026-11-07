"""Render the capstone intro video from slides and recorded terminal sessions.

Terminal scenes replay W2's ``script`` recordings byte for byte: output is never edited and the
typescript header line is skipped. Time is filled by holding and scrolling the finished screen.
Narration text and the scene 7 caption are read from ``paper/deliverables/demo-video-script.md``,
so the video and the script cannot drift apart. Audio is muxed separately once narration exists.

Run (host; needs Pillow and ffmpeg, writes outside the repository):
    python3 paper/deliverables/video/build_video.py --out ~/capstone-work/video/draft.mp4
"""

import argparse
import codecs
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1920, 1080
FPS = 15
CONTENT_BOTTOM = 905
NAVY = "#2B2D63"
ACCENT = "#D55E00"
INK = "#1F2328"
MUTED = "#5F6670"
CARD = "#F3F4FA"
TERM_BG = "#14161A"
TERM_FG = "#E6E6E6"
BAND = "#101218"
NOTE = "#FFD479"
COLUMNS = 100
ROWS = 26
CELL_W = 16
CELL_H = 32
REPLAY_LABEL = "실행 기록 재생(2026-11-07)"
LEDGER_QUOTE = (
    "이름 획득 조건의 관찰(피드백 인과 미입증): "
    "외부 객체 이름을 어휘에 획득한 조건에서 자율 C1 관찰 "
    "(A3 21 vs A1 0 vs identity-blind 0); 어휘 미통제라 retention·effect 피드백 인과는 미입증"
)
FUNDING = "본 결과물은 상명대학교 대학혁신지원사업비의 지원을 받아 제작되었습니다."
SGR_COLORS = {"34": "#7AA7FF", "32": "#8BD17C", "90": "#8A8F98", "39": TERM_FG}

REPO = Path(__file__).resolve().parents[3]
SCRIPT_MD = REPO / "paper/deliverables/demo-video-script.md"
ARCHITECTURE = REPO / "paper/figures/system-architecture.png"
M2_FIGURE = REPO / "paper/figures/m2-cross-release-evidence.png"
M3_FIGURE = REPO / "paper/figures/m3-blind-ablation.png"


class Fonts:
    """Named fonts loaded from one directory, cached by file and size."""

    def __init__(self, font_dir: Path) -> None:
        self.font_dir = font_dir
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def get(self, name: str, size: int) -> ImageFont.FreeTypeFont:
        key = (name, size)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(str(self.font_dir / name), size)
        return self._cache[key]

    def body(self, size: int) -> ImageFont.FreeTypeFont:
        return self.get("malgun.ttf", size)

    def bold(self, size: int) -> ImageFont.FreeTypeFont:
        return self.get("malgunbd.ttf", size)


def wrap_pixels(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if font.getlength(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def script_section(markdown: str, scene: int) -> str:
    match = re.search(rf"^### 장면 {scene} .*?(?=^### 장면 |^## )", markdown, re.M | re.S)
    if match is None:
        raise ValueError(f"scene {scene} not found in script")
    return match.group(0)


def script_field(section: str, name: str) -> str:
    match = re.search(rf"^- \*\*{name}:\*\* (.*?)(?=^- \*\*|^\*\*|\Z)", section, re.M | re.S)
    if match is None:
        raise ValueError(f"field {name} not found")
    text = re.sub(r"\s*\n\s*", " ", match.group(1)).strip()
    return text.replace("`", "").rstrip(".").strip('"')


def caption_pages(narration: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Split narration into at most two-line pages, sentence by sentence."""
    pages: list[str] = []
    for sentence in re.findall(r".+?[.?!](?:\s|$)", narration):
        lines = wrap_pixels(sentence.strip(), font, width)
        for index in range(0, len(lines), 2):
            pages.append("\n".join(lines[index : index + 2]))
    return pages


@dataclass
class Terminal:
    """Minimal emulator: the recordings only use CR, LF and SGR color codes."""

    lines: list[list[tuple[str, str]]] = field(default_factory=lambda: [[]])
    column: int = 0
    color: str = TERM_FG
    pending: str = ""

    def _newline(self) -> None:
        self.lines.append([])
        self.column = 0

    def _put(self, char: str) -> None:
        width = 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if self.column + width > COLUMNS:
            self._newline()
        self.lines[-1].append((char, self.color))
        self.column += width

    def feed(self, text: str) -> None:
        text = self.pending + text
        self.pending = ""
        index = 0
        while index < len(text):
            char = text[index]
            if char == "\x1b":
                match = re.match(r"\x1b\[([0-9;?]*)([a-zA-Z])", text[index:])
                if match is None:
                    self.pending = text[index:]
                    return
                if match.group(2) == "m":
                    codes = match.group(1).split(";")
                    self.color = TERM_FG
                    for code in codes:
                        self.color = SGR_COLORS.get(code, self.color)
                index += match.end()
                continue
            if char == "\n":
                self._newline()
            elif char == "\r":
                self.column = 0
            elif ord(char) >= 32:
                self._put(char)
            index += 1


def load_replay(stem: Path) -> list[tuple[float, bytes]]:
    """Return (delay, bytes) chunks, skipping the typescript header line."""
    data = stem.with_suffix(".typescript").read_bytes()
    offset = data.index(b"\n") + 1
    chunks: list[tuple[float, bytes]] = []
    for row in stem.with_suffix(".timing").read_text().splitlines():
        delay, count = row.split()
        chunks.append((float(delay), data[offset : offset + int(count)]))
        offset += int(count)
    return chunks


class Canvas:
    """Draws slides, terminal screens and the caption band."""

    def __init__(self, fonts: Fonts, draft_note: str | None) -> None:
        self.fonts = fonts
        self.draft_note = draft_note
        self.caption_font = fonts.body(36)

    def slide_base(self, heading: str | None = None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        image = Image.new("RGB", (WIDTH, HEIGHT), "white")
        draw = ImageDraw.Draw(image)
        if heading:
            draw.rectangle((0, 0, WIDTH, 96), fill=NAVY)
            draw.text((70, 48), heading, font=self.fonts.bold(42), fill="white", anchor="lm")
        return image, draw

    def title(self) -> Image.Image:
        image, draw = self.slide_base()
        draw.rectangle((0, 0, 40, HEIGHT), fill=NAVY)
        draw.text((150, 300), "InodeFence", font=self.fonts.bold(120), fill=NAVY, anchor="ls")
        draw.text(
            (150, 400),
            "TAR 추출 경계위반 탐색 프로토타입",
            font=self.fonts.body(58),
            fill=INK,
            anchor="ls",
        )
        draw.rounded_rectangle((150, 470, 860, 550), radius=12, outline=ACCENT, width=3)
        draw.text(
            (505, 510),
            "구현 시연 · 가설 검정 결과 아님",
            font=self.fonts.bold(38),
            fill=ACCENT,
            anchor="mm",
        )
        return image

    def problem(self) -> Image.Image:
        image, draw = self.slide_base("문제: 경로만 보면 놓치는 관계")
        boxes = [
            ((230, 240, 850, 430), "추출 폴더 안", "extract/alias"),
            ((1070, 240, 1690, 430), "추출 폴더 밖 (보호 대상)", "outside/sentinel.txt"),
        ]
        for xy, label, path in boxes:
            draw.rounded_rectangle(xy, radius=16, fill=CARD, outline=NAVY, width=3)
            draw.text(
                (xy[0] + 310, xy[1] + 62), label, font=self.fonts.body(34), fill=MUTED, anchor="mm"
            )
            draw.text(
                (xy[0] + 310, xy[1] + 128), path, font=self.fonts.bold(44), fill=INK, anchor="mm"
            )
        draw.rounded_rectangle(
            (690, 590, 1230, 730), radius=16, fill="#FBE9DD", outline=ACCENT, width=4
        )
        draw.text(
            (960, 660),
            "같은 inode (st_dev, st_ino)",
            font=self.fonts.bold(40),
            fill=ACCENT,
            anchor="mm",
        )
        for start in ((540, 430), (1380, 430)):
            end = (800 if start[0] < 960 else 1120, 590)
            draw.line((start, end), fill=ACCENT, width=6)
        draw.text(
            (960, 800),
            "TAR의 하드링크 하나로 생길 수 있는 관계. 경로 문자열만 보면 놓칠 수 있다.",
            font=self.fonts.body(38),
            fill=INK,
            anchor="mm",
        )
        return image

    def contracts(self) -> Image.Image:
        image, draw = self.slide_base("판정 기준: 일반 규칙 세 개")
        cards = [
            (
                "C0",
                "Path Boundary Confinement",
                "추출 폴더 밖의 경로 변화",
                "생성 · 삭제 · 다른 객체로 교체",
            ),
            (
                "C1",
                "Object Identity Confinement",
                "보호 대상과의 inode 공유",
                "같은 (st_dev, st_ino)",
            ),
            (
                "C2",
                "External Effect Noninterference",
                "보호 대상의 내용·메타데이터 변화",
                "내용 해시, 크기, mode, nlink 등",
            ),
        ]
        for index, (cid, name, rule, detail) in enumerate(cards):
            top = 150 + index * 215
            draw.rounded_rectangle(
                (90, top, 1830, top + 190), radius=16, fill=CARD, outline=NAVY, width=2
            )
            draw.text((200, top + 95), cid, font=self.fonts.bold(76), fill=NAVY, anchor="mm")
            draw.text((330, top + 42), name, font=self.fonts.body(28), fill=MUTED, anchor="lm")
            draw.text((330, top + 95), rule, font=self.fonts.bold(42), fill=INK, anchor="lm")
            draw.text((330, top + 148), detail, font=self.fonts.body(30), fill=MUTED, anchor="lm")
        return image

    def architecture(self) -> Image.Image:
        image, _ = self.slide_base("구성: 입력에서 다음 변형까지")
        figure = Image.open(ARCHITECTURE).convert("RGB")
        scale = min(1400 / figure.width, 800 / figure.height)
        figure = figure.resize(
            (round(figure.width * scale), round(figure.height * scale)), Image.LANCZOS
        )
        image.paste(figure, ((WIDTH - figure.width) // 2, 100))
        return image

    def m2(self) -> Image.Image:
        image, _ = self.slide_base("통제 재현: 릴리스별 판정 (M2)")
        figure = Image.open(M2_FIGURE).convert("RGB")
        scale = 1680 / figure.width
        figure = figure.resize((1680, round(figure.height * scale)), Image.LANCZOS)
        image.paste(figure, ((WIDTH - figure.width) // 2, 150))
        return image

    def m3(self) -> Image.Image:
        image, draw = self.slide_base("자력 발견의 현재 판정 (M3)")
        draw.text((70, 135), "Capability Ledger 인용", font=self.fonts.body(28), fill=MUTED)
        y = 185
        for line in wrap_pixels(LEDGER_QUOTE, self.fonts.bold(34), 660):
            draw.text((70, y), line, font=self.fonts.bold(34), fill=INK)
            y += 54
        draw.text(
            (70, y + 26), "docs/STATUS.md, main f36a1ce", font=self.fonts.body(24), fill=MUTED
        )
        figure = Image.open(M3_FIGURE).convert("RGB")
        scale = 1090 / figure.width
        figure = figure.resize((1090, round(figure.height * scale)), Image.LANCZOS)
        image.paste(figure, (790, 130))
        return image

    def closing(self) -> Image.Image:
        image, draw = self.slide_base("본실험: 최종 실험값 반영 대기")
        stages = [
            ((230, 230, 860, 480), "EXP-3", "탐색용 (train)"),
            ((1060, 230, 1690, 480), "EXP-2", "확증용 (holdout)"),
        ]
        for xy, name, role in stages:
            draw.rounded_rectangle(xy, radius=16, fill=CARD, outline=NAVY, width=3)
            draw.text(
                (xy[0] + 315, xy[1] + 90), name, font=self.fonts.bold(64), fill=NAVY, anchor="mm"
            )
            draw.text(
                (xy[0] + 315, xy[1] + 170), role, font=self.fonts.body(38), fill=INK, anchor="mm"
            )
        draw.line(((860, 355), (1040, 355)), fill=NAVY, width=6)
        draw.polygon(((1060, 355), (1030, 335), (1030, 375)), fill=NAVY)
        draw.text(
            (960, 590),
            "규칙과 분석 방법은 결과를 보기 전에 Git에 고정한다",
            font=self.fonts.body(40),
            fill=INK,
            anchor="mm",
        )
        draw.text((960, 800), FUNDING, font=self.fonts.body(30), fill=MUTED, anchor="mm")
        return image

    def terminal(self, rows: list[list[tuple[str, str]]], label: str, sublabel: str) -> Image.Image:
        image = Image.new("RGB", (WIDTH, HEIGHT), TERM_BG)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, WIDTH, 56), fill=NAVY)
        draw.text((40, 28), label, font=self.fonts.bold(30), fill="white", anchor="lm")
        draw.text((WIDTH - 40, 28), sublabel, font=self.fonts.body(26), fill="#D5D7E8", anchor="rm")
        ascii_font = self.fonts.get("consola.ttf", 29)
        wide_font = self.fonts.body(28)
        x0, y0 = (WIDTH - COLUMNS * CELL_W) // 2, 66
        for row_index, row in enumerate(rows):
            x = x0
            y = y0 + row_index * CELL_H
            for char, color in row:
                wide = unicodedata.east_asian_width(char) in "WF"
                if char != " ":
                    target = wide_font if ord(char) > 127 else ascii_font
                    draw.text((x, y + 24), char, font=target, fill=color, anchor="ls")
                x += CELL_W * (2 if wide else 1)
        return image

    def compose(self, base: Image.Image, caption: str | None, note: str | None) -> bytes:
        image = base.copy()
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, CONTENT_BOTTOM, WIDTH, HEIGHT), fill=BAND)
        y = CONTENT_BOTTOM + 10
        if note:
            for line in wrap_pixels(note, self.fonts.body(26), WIDTH - 120):
                draw.text((WIDTH / 2, y), line, font=self.fonts.body(26), fill=NOTE, anchor="ma")
                y += 34
        if caption:
            band_center = (y + HEIGHT) / 2
            draw.multiline_text(
                (WIDTH / 2, band_center),
                caption,
                font=self.caption_font,
                fill="white",
                anchor="mm",
                align="center",
                spacing=8,
            )
        if self.draft_note:
            draw.text(
                (WIDTH / 2, 6),
                self.draft_note,
                font=self.fonts.body(20),
                fill="#9AA0AA",
                anchor="ma",
            )
        return image.tobytes()


@dataclass
class Scene:
    number: int
    start: float
    length: float
    label: str = ""


class Encoder:
    """Pipes raw frames to ffmpeg, reusing bytes when a frame does not change."""

    def __init__(self, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{WIDTH}x{HEIGHT}",
            "-r",
            str(FPS),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-threads",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, preexec_fn=lambda: os.nice(19)
        )
        self.frames = 0

    def write(self, frame: bytes, count: int = 1) -> None:
        assert self.process.stdin is not None
        for _ in range(count):
            self.process.stdin.write(frame)
        self.frames += count

    def close(self) -> None:
        assert self.process.stdin is not None
        self.process.stdin.close()
        if self.process.wait() != 0:
            raise RuntimeError("ffmpeg failed")


class Timeline:
    """Maps scene-local time to the caption page shown at that moment."""

    def __init__(self, pages: list[str], length: float) -> None:
        total = sum(len(page) for page in pages) or 1
        self.marks: list[tuple[float, str]] = []
        clock = 0.3
        usable = length - 0.8
        for page in pages:
            self.marks.append((clock, page))
            clock += usable * len(page) / total

    def page(self, time: float) -> str | None:
        current = None
        for start, text in self.marks:
            if start <= time:
                current = text
        return current


def emit_static(
    encoder: Encoder,
    canvas: Canvas,
    base: Image.Image,
    timeline: Timeline,
    start: float,
    length: float,
    note: str | None,
) -> None:
    frames = round(length * FPS)
    previous: tuple[str | None, bytes] | None = None
    for index in range(frames):
        page = timeline.page(start + index / FPS)
        if previous is None or previous[0] != page:
            previous = (page, canvas.compose(base, page, note))
        encoder.write(previous[1])


def emit_replay(
    encoder: Encoder,
    canvas: Canvas,
    recording: Path,
    timeline: Timeline,
    scene_start: float,
    length: float,
    label: str,
    note: str | None,
    pan: bool,
    tail_hold: float,
) -> None:
    """Replay in real time, then scroll the finished output from its top and hold on the tail."""
    chunks = load_replay(recording)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    terminal = Terminal()
    arrivals: list[tuple[float, str]] = []
    clock = 0.8
    for delay, payload in chunks:
        clock += delay
        arrivals.append((clock, decoder.decode(payload)))
    replay_end = clock + 0.2
    if replay_end + tail_hold > length:
        raise ValueError(f"{recording.name}: scene too short for replay")

    def tail_rows() -> list[list[tuple[str, str]]]:
        visible = terminal.lines[:]
        if not visible[-1]:
            visible = visible[:-1]
        return visible[-ROWS:]

    frames = round(length * FPS)
    next_arrival = 0
    cache: tuple[object, bytes] | None = None
    finished_rows: list[list[tuple[str, str]]] = []
    for index in range(frames):
        now = index / FPS
        while next_arrival < len(arrivals) and arrivals[next_arrival][0] <= now:
            terminal.feed(arrivals[next_arrival][1])
            next_arrival += 1
        if now < replay_end or not pan:
            rows = tail_rows()
            position: object = ("live", next_arrival)
        else:
            if not finished_rows:
                finished_rows = terminal.lines[:-1] if not terminal.lines[-1] else terminal.lines[:]
            scroll_end = length - tail_hold
            span = max(0, len(finished_rows) - ROWS)
            lead = 1.0
            fraction = min(
                1.0, max(0.0, (now - replay_end - lead) / max(0.1, scroll_end - replay_end - lead))
            )
            top = round(span * fraction)
            rows = finished_rows[top : top + ROWS]
            position = ("pan", top)
        page = timeline.page(scene_start + now)
        key = (position, page)
        if cache is None or cache[0] != key:
            base = canvas.terminal(rows, label, REPLAY_LABEL)
            cache = (key, canvas.compose(base, page, note))
        encoder.write(cache[1])


def build(args: argparse.Namespace) -> None:
    markdown = SCRIPT_MD.read_text(encoding="utf-8")
    fonts = Fonts(args.font_dir)
    canvas = Canvas(fonts, args.draft_note or None)
    width = WIDTH - 200
    timelines: dict[int, Timeline] = {}
    lengths = {1: 25.0, 2: 35.0, 3: 35.0, 4: 70.0, 5: 50.0, 6: 30.0, 7: 35.0, 8: 15.0}
    notes = {}
    for scene, length in lengths.items():
        section = script_section(markdown, scene)
        narration = script_field(section, "내레이션")
        pages = caption_pages(narration, canvas.caption_font, width)
        timelines[scene] = Timeline(pages, length)
        rate = len(narration.replace(" ", "")) / length
        print(f"scene {scene}: {length:.0f}s, {len(narration)} chars, {rate:.1f} non-space chars/s")
    notes[7] = script_field(script_section(markdown, 7), "자막")

    encoder = Encoder(args.out)
    recordings = args.recordings
    emit_static(encoder, canvas, canvas.title(), timelines[1], 0.0, 25.0, None)
    emit_static(encoder, canvas, canvas.problem(), timelines[2], 0.0, 13.0, None)
    emit_static(encoder, canvas, canvas.contracts(), timelines[2], 13.0, 22.0, None)
    emit_replay(
        encoder,
        canvas,
        recordings / "scene3-take1",
        timelines[3],
        0.0,
        35.0,
        "Oracle 판정 확인 · 통제 extractor, node-tar 결과 아님",
        None,
        pan=True,
        tail_hold=6.0,
    )
    emit_static(encoder, canvas, canvas.architecture(), timelines[4], 0.0, 14.0, None)
    emit_replay(
        encoder,
        canvas,
        recordings / "scene4-take1",
        timelines[4],
        14.0,
        56.0,
        "demo run · node-tar 7.5.22, seed 123, budget 20",
        None,
        pan=False,
        tail_hold=15.0,
    )
    emit_replay(
        encoder,
        canvas,
        recordings / "scene5-take1",
        timelines[5],
        0.0,
        38.0,
        "통제 재현 · 손으로 만든 fixture, 퍼저 결과 아님",
        None,
        pan=True,
        tail_hold=5.0,
    )
    emit_static(encoder, canvas, canvas.m2(), timelines[5], 38.0, 12.0, None)
    emit_static(encoder, canvas, canvas.m3(), timelines[6], 0.0, 30.0, None)
    emit_replay(
        encoder,
        canvas,
        recordings / "scene7-take1",
        timelines[7],
        0.0,
        35.0,
        "EXP-0 인프라 측정 · 가설 검정 아님",
        notes[7],
        pan=True,
        tail_hold=20.0,
    )
    emit_static(encoder, canvas, canvas.closing(), timelines[8], 0.0, 15.0, None)
    encoder.close()
    print(f"frames {encoder.frames}, {encoder.frames / FPS:.1f}s -> {args.out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--recordings",
        type=Path,
        default=Path.home() / "inodefence-evidence/demo-recordings-20261107",
    )
    parser.add_argument("--font-dir", type=Path, default=Path("/mnt/c/Windows/Fonts"))
    parser.add_argument("--draft-note", default="", help="small corner note for review builds")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
