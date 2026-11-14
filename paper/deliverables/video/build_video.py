"""Build the capstone intro video from the recording script, recorded takes and verified slides.

One block of the recording script = one segment of the video, in the order of the storyboard
``paper/deliverables/demo-video-script.md`` (stage B, 2026-11-14; blocks s01..s10 and end).
For each block the builder looks for a take named ``<block>-t<n>.<ext>`` in ``--incoming``
(highest n wins unless ``--takes`` pins one). A face block takes a camera clip (mp4/mov/m4v with
sound); a voice block takes audio (wav/m4a/mp3/flac) laid over the block's slides or terminal
replay. Leading and trailing silence is trimmed with ffmpeg ``silencedetect``.

A block with no take is rendered SILENT at its target length (the 11/17 draft is built this way),
with captions spread over the block by sentence length and a "무음 초안" corner note. A recorded
block gets caption times from local speech recognition (``asr_align.py`` in its own venv, passed
as ``--asr-python``); caption TEXT is always the script sentence.

Scenes 6 and 9 are result slots: their screen shows only ``RESULT_SLOT`` until the unseal. Before
the unseal (values status 미해제) scene 9 is a card like scene 6: the slot phrase, no narration.
With ``--s09-running`` (ORCH's call, submission before the unseal) it reads the d12 running
sentence (block ``s09-대기``). Any other status uses ``s09-결과`` with the spoken d12 sentence.
Narration and captions carry no values.

Outputs in ``--out``: video.mp4 (1920x1080, 30 fps, H.264 + AAC 48 kHz, loudness -16 LUFS when any
take exists), video.srt, video.ass (burned in) and build.json (blocks, takes with SHA-256, trims,
ASR similarity, warnings). Never opens sealed experiment outputs. Run at low priority, e.g.

    nice -n 19 python3 paper/deliverables/video/build_video.py \\
        --script <recording-script-v2.md> \\
        --values <values.json> --d12 <d12-conclusions.md> --out <dir> [--incoming <dir>]
"""

import argparse
import codecs
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1920, 1080
FPS = 15  # rendered slides and replays; segments are normalised to OUT_FPS
OUT_FPS = 30
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
# Screen columns per recording, wide enough that one run is one screen line (storyboard v2).
REPLAY_COLUMNS = {"scene4-take1": 152, "scene5-take1": 140}
SGR_COLORS = {"34": "#7AA7FF", "32": "#8BD17C", "90": "#8A8F98", "39": TERM_FG}
REPLAY_LABEL = "실행 기록 재생(2026-11-07)"
TITLE = "InodeFence: TAR 추출 경계위반 탐색 프로토타입"
# Arm names as in the claim list C-DESIGN and the storyboard s07b.
ARMS = (
    ("R", "무작위 재시작"),
    ("D", "구조 커버리지"),
    ("S-u", "상태 피드백"),
)
# Scope and limit lines under the design slide: exp2-v1 section 6 scope wording (C-DESIGN) and
# C-LIM1, C-LIM2, the same text as the storyboard s07b screen note.
DESIGN_NOTES = (
    "D: 구조 커버리지 유도 퍼징의 대리. 출력 구조 키 기반이며 코드 커버리지 기준선이 아니다.",
    "S-u: 파일시스템 identity·effect 상태 변화와, 추출 루트를 벗어나는 하드링크 대상의 모양을"
    " 보존 키로 쓰는 탐색. boundary 키는 특정 패턴·경로를 담지 않지만"
    " 결함 계열 수준의 사전 지식이다.",
    "한계: 위반 입력은 seed에서 변이 1회 거리. 확증 범위는 node-tar 한 계보, 하드링크 identity"
    " 공유 계열.",
)
# Reading hints in the script, e.g. "7.5.2(칠 점 오 점 이)", are spoken only.
READING_HINT = re.compile(r"\((?:[영공일이삼사오육칠팔구십 ]+점)+[영공일이삼사오육칠팔구십 ]+\)")
# Spoken spellings in the script and how captions show them.
DISPLAY = {"씨제로": "C0", "씨원": "C1", "씨투": "C2", "아이노드": "inode"}
AUDIO_EXT = (".wav", ".m4a", ".mp3", ".flac")
VIDEO_EXT = (".mp4", ".mov", ".m4v")
PAGE_CHARS = 64  # one caption page = at most two lines in the band

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FIGURES = REPO / "paper/figures"


@dataclass(frozen=True)
class Block:
    """One recorded block: script id, face or voice, target seconds, visual, evidence label."""

    block: str
    mode: str  # "face" | "voice" | "card"
    target: float
    visual: str
    label: str = ""


PLAN = (
    Block("s01", "face", 20, "face-title"),
    Block("s02", "voice", 25, "problem+contracts"),
    Block("s02b", "voice", 10, "slide:s02b", "판정기 검증 · node-tar 결과 아님"),
    Block("s03", "voice", 20, "slide:s03", "측정 사슬 점검 · 탐색 성능 아님"),
    Block("s04", "voice", 30, "replay4+demo", "demo run · 동작 확인, 탐색 성능 아님"),
    Block(
        "s05", "voice", 30, "replay5+m2", "통제 재현 · 사람이 만든 고정 입력, 퍼저의 탐색 결과 아님"
    ),
    Block("s05b", "voice", 20, "slide:s05b", "오라클·어댑터 수준"),
    Block("s06", "card", 5, "result-slot"),
    Block("s07a", "face", 5, "face"),
    Block("s07b", "voice", 30, "design"),
    Block("s07c", "voice", 5, "design"),
    Block("s07d", "voice", 20, "slide:s07d", "측정 사슬 점검 · 탐색 성능 아님"),
    Block("s08", "voice", 35, "slide:s08", "합산값 · arm별 값은 봉인"),
    Block("s09", "voice", 10, "result-slot"),
    Block("s10", "face", 20, "face"),
    Block("end", "card", 4, "end"),
)

#: The result-slot wording shared by the report, the paper and this video (claim list, stage B).
RESULT_SLOT = "본실험 결과 자리(봉인 해제 뒤 기입)"

#: Slide text of the storyboard scenes that have no recording: (heading, lines). Every line comes
#: from the storyboard screen notes, which cite the claim IDs; values only from the claim list.
SLIDES: dict[str, tuple[str, tuple[str, ...]]] = {
    "s02b": (
        "판정기 대조 (통제용 테스트 추출기)",
        (
            "경계 검사 없이 entry를 그대로 따르는 통제용 테스트 추출기, 일회용 샌드박스 안",
            "정상 입력 → 위반 없음",
            "추출 루트를 벗어나는 경로의 파일 → C0",
            "sentinel을 가리키는 하드링크 → C1 · C2",
            "symlink를 만든 뒤 그 경로에 쓰기 → C2",
            "판정기 검증이며 node-tar 결과가 아님",
        ),
    ),
    "s04demo": (
        "현재 main 데모 (main ff83fbe, seed 123, 실행 20)",
        (
            "node-tar 7.5.22 · 20 step (성공 18, 거부 2) · 위반 0",
            "고유 effect 키 25 · 보상 step 3회 · 코퍼스 4 → 7",
            "비교 방식이 없는 seed 1개 데모: 탐색 성능이나 방식 비교의 수치가 아님",
            "위반 0은 이 예산에서 관찰되지 않았다는 뜻: node-tar 7.5.22가 안전하다는 근거가 아님",
            "앞의 화면은 2026-11-07 실행 기록의 재생",
        ),
    ),
    "s03": (
        "고정 입력 점검",
        (
            "make regression TAR_VERSION=<x>",
            "알려진 경계 고정 입력이 그 릴리스에서 아직 C1/C2를 내는지 확인",
            "holdout 후보 7.0.1 · 7.1.0 · 7.2.0 · 7.3.0 · 7.4.4",
            "하드링크 입력 2개 위반 · symlink 입력 3개 통과 · 오류 0 (다섯 후보 모두)",
            "이 입력으로는 후보를 구분할 수 없어, 가장 높은 버전 규칙으로 7.4.4 선정",
        ),
    ),
    "s05b": (
        "다른 추출기 적용",
        (
            "python-tarfile: 추출 필터 설정 fully_trusted 대 data (설정 토글 비교)",
            "oras-go: v2.6.1 대 v2.6.2 (릴리스 비교)",
            "decompress: 4.2.1 대 유지보수 포크 11.1.4 (릴리스 비교)",
            "세 경우 모두 영향 쪽 위반 · 대조 쪽 비위반",
            "oras-go · decompress: 실제 추출기 동작은 프로브 기록, 오라클 판정은 그 사후 상태를"
            " 일회용 샌드박스에서 재현한 것",
            "Rust tar 0.4.35 · 0.4.36: 같은 방식의 고정 입력 프로브 적용",
            "퍼저 탐색의 일반성이나 효과에 대한 주장이 아님",
        ),
    ),
    "s07d": (
        "측정 사슬 점검",
        (
            "EXP-0 (등록, 인프라 측정): 15셀 모두 유효 · abort 0 · 사건 0",
            "양성 대조 (캠페인 경로): 7.5.2 S-u 1셀, 두 호스트 모두 위반 사건 기록"
            " (첫 사건 step 685, C2)",
            "위험도 파일럿 (비등록, 40 캠페인): 표본 수 산정 · R 변형 선택 · 예측 개정에 사용,"
            " arm 순서 말하지 않음",
        ),
    ),
    "s08": (
        "진행 판정 (GO) 과 운영 기록",
        (
            "첫 C1∨C2 캠페인 (세 arm 합산) 31  ·  기준 1 이상",
            "처리 용량 554  ·  기준 76 이상",
            "인프라 실패 비율 .033  ·  기준 .45 이하",
            "판정 시각 2026-11-13 23:37 KST",
            "train 중 HOST2 정지 1회 → 원인 기록 → 재개",
            "holdout 중 HOST2 정지 1회 → 원인 기록 → 재개 승인",
        ),
    ),
}


# ---------------------------------------------------------------- script and values


def parse_script(markdown: str) -> dict[str, str]:
    """Spoken text per block id: the ``>`` lines under ``### sNN`` or a ``- **sNN-x**`` bullet."""
    blocks: dict[str, list[str]] = {}
    current = None
    for line in markdown.splitlines():
        head = re.match(r"^### (s\d+[a-z]?)\b", line)
        bullet = re.match(r"^- \*\*(s\d+[a-z]?-[가-힣]+)\*\*", line)
        if head:
            current = head.group(1)
        elif bullet:
            current = bullet.group(1)
        elif line.startswith("## "):
            current = None
        quote = re.match(r"^\s*> ?(.*)$", line)
        if current and quote and quote.group(1).strip():
            blocks.setdefault(current, []).append(quote.group(1).strip())
    return {k: " ".join(v) for k, v in blocks.items()}


def spoken_to_display(text: str) -> str:
    text = READING_HINT.sub("", text)
    for spoken, shown in DISPLAY.items():
        text = text.replace(spoken, shown)
    return text


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.?!])\s+", " ".join(text.split()))
    return [p for p in parts if p.strip()]


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_submission", HERE.parent / "check_submission.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- drawing


class Fonts:
    def __init__(self, font_dir: Path) -> None:
        self.font_dir = font_dir
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def get(self, name: str, size: int) -> ImageFont.FreeTypeFont:
        if (name, size) not in self._cache:
            self._cache[(name, size)] = ImageFont.truetype(str(self.font_dir / name), size)
        return self._cache[(name, size)]

    def body(self, size: int) -> ImageFont.FreeTypeFont:
        return self.get("malgun.ttf", size)

    def bold(self, size: int) -> ImageFont.FreeTypeFont:
        return self.get("malgunbd.ttf", size)


def wrap_pixels(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if font.getlength(candidate) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


@dataclass(frozen=True)
class Grid:
    """Character grid for one replay: cell size follows the column count."""

    columns: int

    @property
    def cell_w(self) -> int:
        return (WIDTH - 80) // self.columns

    @property
    def cell_h(self) -> int:
        return round(self.cell_w * 2.15)

    @property
    def rows(self) -> int:
        return (CONTENT_BOTTOM - 76) // self.cell_h

    @property
    def font_size(self) -> int:
        return round(self.cell_w / 0.55)


@dataclass
class Terminal:
    """Minimal emulator: the recordings only use CR, LF and SGR color codes."""

    columns: int = 100
    lines: list[list[tuple[str, str]]] = field(default_factory=lambda: [[]])
    column: int = 0
    color: str = TERM_FG
    pending: str = ""

    def _newline(self) -> None:
        self.lines.append([])
        self.column = 0

    def _put(self, char: str) -> None:
        width = 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if self.column + width > self.columns:
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
                    self.color = TERM_FG
                    for code in match.group(1).split(";"):
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
    """(delay, bytes) chunks of a ``script`` recording, skipping the typescript header line."""
    data = stem.with_suffix(".typescript").read_bytes()
    offset = data.index(b"\n") + 1
    chunks: list[tuple[float, bytes]] = []
    for row in stem.with_suffix(".timing").read_text().splitlines():
        delay, count = row.split()
        chunks.append((float(delay), data[offset : offset + int(count)]))
        offset += int(count)
    return chunks


class Canvas:
    """Slides and terminal screens. The bottom band stays empty: captions are burned in later."""

    def __init__(self, fonts: Fonts, draft_note: str, end_note: str = "") -> None:
        self.fonts = fonts
        self.draft_note = draft_note
        self.end_note = end_note  # funding line, supplied from outside the public repository

    def base(
        self, heading: str | None = None, label: str = ""
    ) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        image = Image.new("RGB", (WIDTH, HEIGHT), "white")
        draw = ImageDraw.Draw(image)
        if heading:
            draw.rectangle((0, 0, WIDTH, 96), fill=NAVY)
            draw.text((70, 48), heading, font=self.fonts.bold(42), fill="white", anchor="lm")
            if label:
                draw.text(
                    (WIDTH - 60, 48), label, font=self.fonts.body(26), fill="#D5D7E8", anchor="rm"
                )
        return image, draw

    def finish(self, image: Image.Image, band: bool = True) -> Image.Image:
        draw = ImageDraw.Draw(image)
        if band:
            draw.rectangle((0, CONTENT_BOTTOM, WIDTH, HEIGHT), fill=BAND)
        if self.draft_note:
            draw.text(
                (WIDTH - 20, 104),
                self.draft_note,
                font=self.fonts.body(22),
                fill=ACCENT,
                anchor="ra",
            )
        return image

    def above_band(self, slide: Image.Image) -> Image.Image:
        """A full-frame slide (W1 scene 8, footer included) shrunk to sit above the band."""
        scale = CONTENT_BOTTOM / HEIGHT
        small = slide.resize((round(WIDTH * scale), CONTENT_BOTTOM), Image.LANCZOS)
        image = Image.new("RGB", (WIDTH, HEIGHT), "white")
        image.paste(small, ((WIDTH - small.width) // 2, 0))
        return self.finish(image)

    def figure(self, image: Image.Image, path: Path, box: tuple[int, int, int, int]) -> None:
        fig = Image.open(path).convert("RGB")
        left, top, right, bottom = box
        scale = min((right - left) / fig.width, (bottom - top) / fig.height)
        fig = fig.resize((round(fig.width * scale), round(fig.height * scale)), Image.LANCZOS)
        image.paste(
            fig, (left + (right - left - fig.width) // 2, top + (bottom - top - fig.height) // 2)
        )

    def face_placeholder(self, block: str, title: bool) -> Image.Image:
        image = Image.new("RGB", (WIDTH, HEIGHT), "#3A3D45")
        draw = ImageDraw.Draw(image)
        draw.text(
            (WIDTH / 2, 420), "얼굴 컷 자리", font=self.fonts.bold(80), fill="white", anchor="mm"
        )
        draw.text(
            (WIDTH / 2, 520),
            f"{block} · 촬영 전",
            font=self.fonts.body(44),
            fill="#C9CCD6",
            anchor="mm",
        )
        if title:
            self.title_overlay(image)
        return self.finish(image, band=False)

    def title_overlay(self, image: Image.Image) -> None:
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rectangle((0, 700, WIDTH, 810), fill=(43, 45, 99, 220))
        draw.text((80, 755), TITLE, font=self.fonts.bold(50), fill="white", anchor="lm")

    def title_png(self) -> Image.Image:
        """Transparent lower-third laid over the s01 camera clip."""
        image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        self.title_overlay(image)
        return image

    def problem(self) -> Image.Image:
        image, draw = self.base("문제: 경로만 보면 놓치는 관계", "예시")
        for xy, label, path in (
            ((230, 200, 850, 390), "추출 폴더 안", "extract/alias"),
            ((1070, 200, 1690, 390), "추출 폴더 밖 (보호 대상)", "outside/sentinel.txt"),
        ):
            draw.rounded_rectangle(xy, radius=16, fill=CARD, outline=NAVY, width=3)
            draw.text(
                (xy[0] + 310, xy[1] + 62), label, font=self.fonts.body(34), fill=MUTED, anchor="mm"
            )
            draw.text(
                (xy[0] + 310, xy[1] + 128), path, font=self.fonts.bold(44), fill=INK, anchor="mm"
            )
        draw.rounded_rectangle(
            (690, 540, 1230, 680), radius=16, fill="#FBE9DD", outline=ACCENT, width=4
        )
        draw.text(
            (960, 610),
            "같은 inode (st_dev, st_ino)",
            font=self.fonts.bold(40),
            fill=ACCENT,
            anchor="mm",
        )
        for start in ((540, 390), (1380, 390)):
            draw.line((start, (800 if start[0] < 960 else 1120, 540)), fill=ACCENT, width=6)
        draw.text(
            (960, 780),
            "TAR의 하드링크 하나로 생길 수 있는 관계. 경로 문자열만 보면 놓치기 쉽다.",
            font=self.fonts.body(38),
            fill=INK,
            anchor="mm",
        )
        return self.finish(image)

    def contracts(self) -> Image.Image:
        image, draw = self.base("판정 기준: 일반 규칙 세 개")
        cards = (
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
        )
        for index, (cid, name, rule, detail) in enumerate(cards):
            top = 130 + index * 230
            draw.rounded_rectangle(
                (90, top, 1830, top + 200), radius=16, fill=CARD, outline=NAVY, width=2
            )
            draw.text((200, top + 100), cid, font=self.fonts.bold(76), fill=NAVY, anchor="mm")
            draw.text((330, top + 45), name, font=self.fonts.body(28), fill=MUTED, anchor="lm")
            draw.text((330, top + 100), rule, font=self.fonts.bold(42), fill=INK, anchor="lm")
            draw.text((330, top + 155), detail, font=self.fonts.body(30), fill=MUTED, anchor="lm")
        draw.text(
            (WIDTH / 2, 860),
            "판정 조건에 CVE 번호도, 릴리스 번호도 없다",
            font=self.fonts.bold(34),
            fill=ACCENT,
            anchor="mm",
        )
        return self.finish(image)

    def m2(self, label: str) -> Image.Image:
        image, _ = self.base("통제 재현: 릴리스별 판정", label)
        self.figure(
            image,
            FIGURES / "m2-cross-release-evidence.png",
            (60, 120, WIDTH - 60, CONTENT_BOTTOM - 20),
        )
        return self.finish(image)

    def design(self) -> Image.Image:
        image, draw = self.base("핵심 질문의 검정 설계")
        draw.text(
            (90, 165), "같은 어휘 · 같은 예산", font=self.fonts.bold(36), fill=NAVY, anchor="ls"
        )
        y = 200
        for arm, text in ARMS:
            draw.rounded_rectangle(
                (90, y, 760, y + 120), radius=14, fill=CARD, outline=NAVY, width=2
            )
            draw.text((150, y + 60), arm, font=self.fonts.bold(48), fill=NAVY, anchor="mm")
            lines = wrap_pixels(text, self.fonts.body(28), 520)
            ty = y + 60 - (len(lines) - 1) * 19
            for line in lines:
                draw.text((220, ty), line, font=self.fonts.body(28), fill=INK, anchor="lm")
                ty += 38
            y += 140
        stages = (
            ("train", "7.5.2", "탐색 실험"),
            ("진행 조건", "GO", "미리 정한 규칙"),
            ("holdout", "7.4.4", "확증 실험"),
        )
        for index, (role, version, what) in enumerate(stages):
            left = 840 + index * 330
            draw.rounded_rectangle(
                (left, 220, left + 270, 420),
                radius=14,
                fill="#FBE9DD" if index == 1 else CARD,
                outline=NAVY,
                width=3,
            )
            draw.text((left + 135, 260), role, font=self.fonts.body(30), fill=MUTED, anchor="mm")
            draw.text((left + 135, 325), version, font=self.fonts.bold(56), fill=NAVY, anchor="mm")
            draw.text((left + 135, 385), what, font=self.fonts.body(28), fill=INK, anchor="mm")
            if index < 2:
                draw.polygon(((left + 300, 320), (left + 280, 302), (left + 280, 338)), fill=NAVY)
        fixed_text = "가설 · 분석 · 판정표: 결과 전 Git 동결 (2026-11-13)"
        draw.rounded_rectangle((840, 470, 1830, 560), radius=14, outline=ACCENT, width=3)
        draw.text((1335, 515), fixed_text, font=self.fonts.bold(34), fill=ACCENT, anchor="mm")
        draw.text((90, 610), "범위와 한계", font=self.fonts.bold(28), fill=MUTED, anchor="ls")
        y = 630
        for note in DESIGN_NOTES:
            for line in wrap_pixels(note, self.fonts.body(27), WIDTH - 180):
                draw.text((90, y), line, font=self.fonts.body(27), fill=MUTED)
                y += 38
        return self.finish(image)

    def text_slide(self, heading: str, label: str, lines: tuple[str, ...]) -> Image.Image:
        image, draw = self.base(heading, label)
        y = 170
        for text in lines:
            for line in wrap_pixels(text, self.fonts.body(34), WIDTH - 200):
                draw.text((100, y), line, font=self.fonts.body(34), fill=INK)
                y += 50
            y += 18
        return self.finish(image)

    def result_slot(self) -> Image.Image:
        image, draw = self.base("핵심 질문의 판정")
        draw.text(
            (WIDTH / 2, CONTENT_BOTTOM / 2 + 40),
            RESULT_SLOT,
            font=self.fonts.bold(64),
            fill=NAVY,
            anchor="mm",
        )
        return self.finish(image)

    def end_card(self) -> Image.Image:
        image, draw = self.base()
        draw.rectangle((0, 0, 40, HEIGHT), fill=NAVY)
        draw.text((WIDTH / 2, 430), "InodeFence", font=self.fonts.bold(110), fill=NAVY, anchor="mm")
        draw.text(
            (WIDTH / 2, 560),
            "TAR 추출 경계위반 탐색 프로토타입",
            font=self.fonts.body(52),
            fill=INK,
            anchor="mm",
        )
        draw.text(
            (WIDTH / 2, 760), self.end_note, font=self.fonts.body(34), fill=MUTED, anchor="mm"
        )
        return self.finish(image, band=False)

    def terminal(
        self, rows: list[list[tuple[str, str]]], label: str, sublabel: str, grid: Grid
    ) -> Image.Image:
        image = Image.new("RGB", (WIDTH, HEIGHT), TERM_BG)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, WIDTH, 56), fill=NAVY)
        draw.text((40, 28), label, font=self.fonts.bold(30), fill="white", anchor="lm")
        draw.text((WIDTH - 40, 28), sublabel, font=self.fonts.body(26), fill="#D5D7E8", anchor="rm")
        ascii_font = self.fonts.get("consola.ttf", grid.font_size)
        wide_font = self.fonts.body(grid.font_size - 1)
        x0, y0 = (WIDTH - grid.columns * grid.cell_w) // 2, 66
        for row_index, row in enumerate(rows):
            x = x0
            y = y0 + row_index * grid.cell_h
            for char, color in row:
                wide = unicodedata.east_asian_width(char) in "WF"
                if char != " ":
                    target = wide_font if ord(char) > 127 else ascii_font
                    draw.text(
                        (x, y + round(grid.cell_h * 0.75)),
                        char,
                        font=target,
                        fill=color,
                        anchor="ls",
                    )
                x += grid.cell_w * (2 if wide else 1)
        return self.finish(image)


# ---------------------------------------------------------------- frames


class Encoder:
    """Pipes raw frames to ffmpeg at FPS, writing a silent intermediate clip."""

    def __init__(self, out_path: Path) -> None:
        self.process = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24"]
            + ["-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-", "-c:v", "libx264"]
            + ["-preset", "veryfast", "-crf", "18", "-threads", "2", "-pix_fmt", "yuv420p"]
            + [str(out_path)],
            stdin=subprocess.PIPE,
        )
        self.frames = 0

    def hold(self, image: Image.Image, seconds: float) -> None:
        frame = image.tobytes()
        count = max(1, round(seconds * FPS))
        assert self.process.stdin is not None
        for _ in range(count):
            self.process.stdin.write(frame)
        self.frames += count

    def close(self) -> None:
        assert self.process.stdin is not None
        self.process.stdin.close()
        if self.process.wait() != 0:
            raise RuntimeError("ffmpeg failed while encoding frames")


def emit_replay(
    encoder: Encoder, canvas: Canvas, stem: Path, length: float, label: str, pan: bool
) -> str:
    """Replay a recording in real time (faster only if it cannot fit), then scroll and hold."""
    chunks = load_replay(stem)
    raw = sum(delay for delay, _ in chunks)
    tail = min(4.0, length * 0.2)
    speed = max(1.0, raw / max(0.1, length - tail - 1.0))
    sublabel = REPLAY_LABEL if speed == 1.0 else f"{REPLAY_LABEL} · {speed:.1f}배속"
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    arrivals: list[tuple[float, str]] = []
    clock = 0.8
    for delay, payload in chunks:
        clock += delay / speed
        arrivals.append((clock, decoder.decode(payload)))
    replay_end = clock + 0.2
    grid = Grid(REPLAY_COLUMNS.get(stem.name, 100))
    terminal = Terminal(columns=grid.columns)
    frames = round(length * FPS)
    nxt = 0
    cache: tuple[object, bytes] | None = None
    finished: list[list[tuple[str, str]]] = []
    assert encoder.process.stdin is not None
    for index in range(frames):
        now = index / FPS
        while nxt < len(arrivals) and arrivals[nxt][0] <= now:
            terminal.feed(arrivals[nxt][1])
            nxt += 1
        lines = terminal.lines[:-1] if not terminal.lines[-1] else terminal.lines[:]
        if now < replay_end or not pan:
            rows = lines[-grid.rows :]
            key: object = ("live", nxt)
        else:
            finished = finished or lines
            span = max(0, len(finished) - grid.rows)
            frac = min(
                1.0, max(0.0, (now - replay_end - 1.0) / max(0.1, length - tail - replay_end - 1.0))
            )
            top = round(span * frac)
            rows = finished[top : top + grid.rows]
            key = ("pan", top)
        if cache is None or cache[0] != key:
            cache = (key, canvas.terminal(rows, label, sublabel, grid).tobytes())
        encoder.process.stdin.write(cache[1])
        encoder.frames += 1
    return sublabel


# ---------------------------------------------------------------- audio, takes, captions


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def find_take(incoming: Path | None, block: str, pinned: dict[str, str]) -> Path | None:
    if incoming is None:
        return None
    if block in pinned:
        path = incoming / pinned[block]
        if not path.is_file():
            raise SystemExit(f"--takes names a missing file for {block}")
        return path
    best: tuple[int, Path] | None = None
    for path in incoming.iterdir():
        match = re.fullmatch(rf"{re.escape(block)}-t(\d+)(\.[A-Za-z0-9]+)", path.name)
        if match and match.group(2).lower() in AUDIO_EXT + VIDEO_EXT:
            if best is None or int(match.group(1)) > best[0]:
                best = (int(match.group(1)), path)
    return best[1] if best else None


def duration(path: Path) -> float:
    out = run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    )
    return float(out.stdout.strip())


def speech_span(path: Path, total: float) -> tuple[float, float]:
    """Start and end of speech: first and last non-silent moment, with small margins."""
    out = run(
        ["nice", "-n", "19", "ffmpeg", "-nostdin", "-hide_banner", "-threads", "2", "-i", str(path)]
        + ["-vn", "-af", "silencedetect=noise=-40dB:d=0.35", "-f", "null", "-"]
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    begin, finish = 0.0, total
    if starts and starts[0] <= 0.05 and ends:
        begin = ends[0]
    if starts and (len(ends) < len(starts) or ends[-1] >= total - 0.05):
        finish = starts[-1]
    if finish - begin < 0.5:
        return 0.0, total
    return max(0.0, begin - 0.25), min(total, finish + 0.4)


@dataclass
class Cue:
    start: float
    end: float
    text: str


def spread_cues(texts: list[str], begin: float, end: float) -> list[Cue]:
    weights = [max(1, len(t.replace(" ", ""))) for t in texts]
    total = sum(weights)
    cues, clock = [], begin
    for text, weight in zip(texts, weights, strict=True):
        step = (end - begin) * weight / total
        cues.append(Cue(clock, clock + step, text))
        clock += step
    return cues


def pages(cue: Cue) -> list[Cue]:
    """Split a long sentence into band-sized pages at spaces; time by length."""
    count = math.ceil(len(cue.text) / PAGE_CHARS)
    if count <= 1:
        return [cue]
    words = cue.text.split(" ")
    target = len(cue.text) / count
    parts, current = [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > target * 1.15 and len(parts) < count - 1:
            parts.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    parts.append(current)
    return spread_cues(parts, cue.start, cue.end)


def align_cues(display: list[str], located: list[dict], begin: float, end: float) -> list[Cue]:
    """Sentence cues from ASR times; sentences ASR could not place share the gap around them."""
    times: dict[int, tuple[float, float]] = {c["index"]: (c["start"], c["end"]) for c in located}
    cues: list[Cue] = []
    index = 0
    while index < len(display):
        if index in times:
            cues.append(Cue(*times[index], display[index]))
            index += 1
            continue
        run_end = index
        while run_end < len(display) and run_end not in times:
            run_end += 1
        gap_start = cues[-1].end if cues else begin
        gap_end = times[run_end][0] if run_end in times else end
        cues.extend(spread_cues(display[index:run_end], gap_start, max(gap_start + 0.5, gap_end)))
        index = run_end
    for a, b in zip(cues, cues[1:], strict=False):  # keep cues ordered and non-overlapping
        if b.start < a.end:
            b.start = a.end
        b.end = max(b.end, b.start + 0.3)
    return cues


def ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_captions(cues: list[Cue], out: Path) -> None:
    srt = [
        f"{i}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}\n" for i, c in enumerate(cues, 1)
    ]
    (out / "video.srt").write_text("\n".join(srt), encoding="utf-8")
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, "
        "Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Malgun Gothic,46,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,"
        "100,100,0,0,1,3,0,2,120,120,38,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    events = [
        f"Dialogue: 0,{ass_time(c.start)},{ass_time(c.end)},Default,,0,0,0,,{c.text}" for c in cues
    ]
    (out / "video.ass").write_text(head + "\n".join(events) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- segments


def normalise(
    video_in: list[str],
    audio_in: list[str],
    length: float,
    out: Path,
    pad: str,
    overlay: Path | None = None,
) -> None:
    """One segment: 1920x1080, OUT_FPS, H.264 + AAC 48 kHz stereo, exactly ``length`` seconds."""
    chain = (
        f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:{pad},setsar=1,fps={OUT_FPS}"
    )
    inputs = video_in + audio_in
    if overlay is not None:
        inputs += ["-i", str(overlay)]
        chain += "[base];[base][2:v]overlay=0:0"
    chain += ",format=yuv420p[v];[1:a]apad[a]"  # pad short speech so A/V stay equal
    result = run(
        ["nice", "-n", "19", "ffmpeg", "-y", "-nostdin", "-v", "error"]
        + inputs
        + ["-filter_complex", chain, "-map", "[v]", "-map", "[a]", "-t", f"{length:.3f}"]
        + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", "2"]
        + ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out)]
    )
    if result.returncode != 0:
        raise RuntimeError(f"segment {out.name}: {result.stderr[-400:]}")


def silence(length: float) -> list[str]:
    return ["-f", "lavfi", "-t", f"{length:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]


def render_visual(block: Block, canvas: Canvas, ctx: dict, length: float, out: Path) -> dict:
    """Silent clip of the block's slides or replay; returns extra facts for build.json."""
    facts: dict = {}
    encoder = Encoder(out)
    recordings: Path = ctx["recordings"]
    if block.visual == "problem+contracts":
        encoder.hold(canvas.problem(), length * 0.45)
        encoder.hold(canvas.contracts(), length - length * 0.45)
    elif block.visual == "replay4+demo":
        first = length * 0.7
        facts["replay"] = emit_replay(
            encoder, canvas, recordings / "scene4-take1", first, block.label, False
        )
        heading, lines = SLIDES["s04demo"]
        encoder.hold(canvas.text_slide(heading, block.label, lines), length - first)
    elif block.visual == "replay5+m2":
        first = length * 0.55
        facts["replay"] = emit_replay(
            encoder, canvas, recordings / "scene5-take1", first, block.label, True
        )
        encoder.hold(canvas.m2("통제 재현"), length - first)
    elif block.visual == "design":
        encoder.hold(canvas.design(), length)
    elif block.visual.startswith("slide:"):
        heading, lines = SLIDES[block.visual.removeprefix("slide:")]
        encoder.hold(canvas.text_slide(heading, block.label, lines), length)
    elif block.visual == "result-slot":
        encoder.hold(canvas.result_slot(), length)
    elif block.visual == "end":
        encoder.hold(canvas.end_card(), length)
    else:
        encoder.hold(canvas.face_placeholder(block.block, block.visual == "face-title"), length)
    encoder.close()
    return facts


def build(args: argparse.Namespace) -> None:
    out: Path = args.out
    work = out / "segments"
    work.mkdir(parents=True, exist_ok=True)
    markdown = args.script.read_text(encoding="utf-8")
    script = parse_script(markdown)
    checker = load_checker()
    values = json.loads(args.values.read_text(encoding="utf-8"))
    got = checker.result_sentences(values, args.d12.read_text(encoding="utf-8"))
    if not got:
        raise SystemExit("no result sentence for this values file")
    status, _written, spoken = got
    plan = PLAN
    if status == "미해제" and not args.s09_running:
        # Result slot: a card with the slot phrase only and no narration (claim list slot rule).
        s09_id, s09_text = "s09", ""
        plan = tuple(replace(b, mode="card") if b.block == "s09" else b for b in PLAN)
    elif status == "미해제":
        # Fallback chosen by ORCH when submission comes before the unseal.
        s09_id, s09_text = "s09-대기", script["s09-대기"]
        if checker.nows(s09_text) != checker.nows(checker.RUNNING_SPOKEN):
            raise SystemExit("script s09-대기 differs from the d12 running sentence")
    else:
        s09_id, s09_text = "s09-결과", spoken
    texts = {b.block: script.get(b.block, "") for b in plan if b.mode != "card"}
    texts["s09"] = s09_text
    take_ids = {b.block: b.block for b in plan}
    take_ids["s09"] = s09_id
    pinned = json.loads(args.takes.read_text(encoding="utf-8")) if args.takes else {}

    fonts = Fonts(args.font_dir)
    any_take = any(
        find_take(args.incoming, take_ids[b.block], pinned) for b in plan if b.mode != "card"
    )
    canvas = Canvas(fonts, args.draft_note, args.end_note)
    ctx = {
        "recordings": args.recordings,
    }
    title_png = work / "title.png"
    canvas.title_png().save(title_png)

    report: dict = {
        "script_sha256": sha256(args.script),
        "values": args.values.name,
        "status": status,
        "blocks": [],
        "warnings": [],
    }
    all_cues: list[Cue] = []
    segments: list[Path] = []
    clock = 0.0
    for block in plan:
        take = (
            find_take(args.incoming, take_ids[block.block], pinned)
            if block.mode != "card"
            else None
        )
        spoken_text = texts.get(block.block, "")
        display = [spoken_to_display(s) for s in sentences(spoken_text)]
        entry: dict = {"block": take_ids[block.block], "mode": block.mode, "target": block.target}
        seg = work / f"{len(segments):02d}-{block.block}.mp4"
        if take is None:
            length = block.target
            cues = spread_cues(display, 0.3, length - 0.5) if display else []
            entry["take"] = None
        else:
            total = duration(take)
            begin, finish = speech_span(take, total)
            length = finish - begin + 0.3
            clip = work / f"{block.block}-speech.wav"
            cut = run(
                [
                    "nice",
                    "-n",
                    "19",
                    "ffmpeg",
                    "-y",
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    f"{begin:.3f}",
                ]
                + [
                    "-to",
                    f"{finish:.3f}",
                    "-i",
                    str(take),
                    "-vn",
                    "-ac",
                    "2",
                    "-ar",
                    "48000",
                    str(clip),
                ]
            )
            if cut.returncode != 0:
                raise RuntimeError(f"{take.name}: {cut.stderr[-300:]}")
            entry.update(
                take=take.name, take_sha256=sha256(take), trim=[round(begin, 2), round(finish, 2)]
            )
            cues = spread_cues(display, 0.2, length - 0.4)
            if args.asr_python:
                (work / f"{block.block}.txt").write_text(spoken_text, encoding="utf-8")
                prefix = work / block.block
                asr = run(
                    [
                        "nice",
                        "-n",
                        "19",
                        str(args.asr_python),
                        str(HERE / "asr_align.py"),
                        str(clip),
                    ]
                    + [str(work / f"{block.block}.txt"), str(prefix), "--model", args.asr_model]
                )
                if asr.returncode != 0:
                    report["warnings"].append(
                        f"{block.block}: ASR failed, captions spread by length"
                    )
                else:
                    check = json.loads(
                        prefix.with_suffix(".check.json").read_text(encoding="utf-8")
                    )
                    located = json.loads(
                        prefix.with_suffix(".cues.json").read_text(encoding="utf-8")
                    )
                    entry["asr_similarity"] = check["similarity"]
                    entry["asr_unplaced"] = check["unplaced"]
                    if check["similarity"] < args.min_similarity or check["unplaced"]:
                        report["warnings"].append(
                            f"{block.block}: similarity {check['similarity']}, "
                            f"unplaced {check['unplaced']}; listen, retake if misread"
                        )
                    cues = align_cues(display, located, 0.2, length - 0.4)
            else:
                report["warnings"].append(
                    f"{block.block}: no --asr-python, captions spread by length"
                )
        if take is not None and take.suffix.lower() in VIDEO_EXT:
            normalise(
                ["-ss", f"{begin:.3f}", "-t", f"{length:.3f}", "-i", str(take)],
                ["-i", str(clip)],
                length,
                seg,
                "black",
                title_png if block.visual == "face-title" else None,
            )
        else:
            if block.mode == "face" and take is not None:
                report["warnings"].append(
                    f"{block.block}: face block has audio only, placeholder picture"
                )
            raw = work / f"{block.block}-visual.mp4"
            # every block still without a take is marked, even in a partly recorded build
            canvas.draft_note = args.draft_note or (
                "무음 초안 · 낭독 미녹음" if take is None and block.mode != "card" else ""
            )
            entry.update(render_visual(block, canvas, ctx, length, raw))
            normalise(
                ["-i", str(raw)],
                ["-i", str(clip)] if take is not None else silence(length),
                length,
                seg,
                "white",
            )
        entry["length"] = round(length, 2)
        entry["start"] = round(clock, 2)
        report["blocks"].append(entry)
        for cue in cues:
            for page in pages(cue):
                all_cues.append(Cue(page.start + clock, page.end + clock, page.text))
        segments.append(seg)
        clock += duration(seg)
        print(f"{entry['block']}: {length:.1f}s take={entry['take']}", flush=True)

    write_captions(all_cues, out)
    (work / "concat.txt").write_text(
        "".join(f"file '{p.name}'\n" for p in segments), encoding="utf-8"
    )
    joined = work / "joined.mp4"
    cat = run(
        [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "concat.txt",
            "-c",
            "copy",
            joined.name,
        ],
        cwd=work,
    )
    if cat.returncode != 0:
        raise RuntimeError(cat.stderr[-400:])
    shutil.copy(out / "video.ass", work / "video.ass")
    audio_filter = ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000"] if any_take else []
    final = run(
        ["nice", "-n", "19", "ffmpeg", "-y", "-nostdin", "-v", "error", "-i", joined.name]
        + [
            "-vf",
            f"subtitles=video.ass:fontsdir={args.font_dir}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
        ]
        + ["-crf", "20", "-threads", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
        + audio_filter
        + ["-movflags", "+faststart", str((out / "video.mp4").resolve())],
        cwd=work,
    )
    if final.returncode != 0:
        raise RuntimeError(final.stderr[-400:])
    report["duration"] = round(duration(out / "video.mp4"), 2)
    report["video_sha256"] = sha256(out / "video.mp4")
    (out / "build.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    if not args.keep:
        shutil.rmtree(work)
    print(
        json.dumps(
            {k: report[k] for k in ("status", "duration", "warnings")}, ensure_ascii=False, indent=1
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--script", type=Path, required=True, help="recording script (v1.1 or later)"
    )
    parser.add_argument("--values", type=Path, required=True, help="W3 submission values file")
    parser.add_argument("--d12", type=Path, required=True, help="d12-conclusions.md")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--incoming", type=Path, help="folder of recorded takes <block>-t<n>.<ext>")
    parser.add_argument("--takes", type=Path, help='JSON {"s03": "s03-t2.wav"} to pin takes')
    parser.add_argument(
        "--s09-running",
        action="store_true",
        help="before the unseal, read the d12 running sentence instead of the slot (ORCH call)",
    )
    parser.add_argument("--asr-python", type=Path, help="python of the faster-whisper venv")
    parser.add_argument("--asr-model", default="small")
    parser.add_argument("--min-similarity", type=float, default=0.9)
    parser.add_argument(
        "--recordings",
        type=Path,
        default=Path.home() / "inodefence-evidence/demo-recordings-20261107",
    )
    parser.add_argument("--font-dir", type=Path, default=Path("/mnt/c/Windows/Fonts"))
    parser.add_argument(
        "--draft-note",
        default="",
        help="corner note on rendered blocks; blocks without a take default to 무음 초안",
    )
    parser.add_argument("--end-note", default="", help="funding sentence for the end card")
    parser.add_argument("--keep", action="store_true", help="keep intermediate segments")
    args = parser.parse_args()
    os.nice(19)
    build(args)


if __name__ == "__main__":
    main()
