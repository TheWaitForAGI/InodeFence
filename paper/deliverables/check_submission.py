"""Check the final submission files in one command and list what still needs a human eye.

usage:
    python3 paper/deliverables/check_submission.py --hwp report.hwp --pdf report.pdf \
        --mp4 video.mp4 --srt video.srt --values values.json --d12 d12-conclusions.md \
        --sample-terms terms.json [--final] [--max-pages 6] [--max-seconds 300]

Every file argument is optional; missing ones are reported as "not checked". Exit 0 when nothing
FAILs. Checks:
  - integrity: sha256 of every file (printed for the submission record);
  - HWP: `fill_form.py check` (sample terms in BodyText and PrvText, gray/italic, placeholders);
  - PDF: pages, all fonts embedded, Korean text extractable, sample terms 0, placeholders 0;
  - result sentence: from the values file (W3 submission-values-v1). When it is unsealed or
    synthetic, the d12 abstract of the proposed cell with its <...> places filled must be in the
    PDF and HWP text, and the same sentence with the value parentheses removed in the captions.
    When it is 미해제 (sealed), the d12 "제출 시점에 실행 중" lines must be there instead;
  - MP4: H.264 + AAC, 1920x1080, duration limit, full decode without error, loudness;
  - captions (SRT): parse, monotonic times, inside the video duration.
The values file's status "synthetic" makes this a dry run: it FAILs with --final.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILL = HERE / "hwp" / "fill_form.py"
BRACKET = re.compile(r"\[(?:사람|대기|갱신)[^\]]*\]")
PLACEHOLDER = re.compile(r"<[^<>\s]{1,20}>")  # d12 value places, only inside the result sentence
RUNNING_SPOKEN = (
    "확증 실험은 제출 시점에 진행 중이며, 판정은 미리 등록한 규칙에 따라 실험이 끝난 뒤에 냅니다."
)
RUNNING_WRITTEN = (
    "확증 실험은 제출 시점에 진행 중이며, 판정은 미리 등록한 규칙에 따라 실험이 끝난 뒤에 낸다."
)

results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"{status:5} {name}" + (f" — {detail}" if detail else ""))


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def nows(text: str) -> str:
    # whitespace and the middle dot: PDF line wraps split words, and the approximate PDF drops "·"
    return re.sub(r"[\s·]+", "", text)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hwp_text(path: Path, terms: Path | None, final: bool, out_dir: Path) -> str:
    dump = out_dir / f"{path.stem}-paras.md"
    cmd = [sys.executable, str(FILL), "check", str(path), "--dump-text", str(dump)]
    if terms:
        cmd += ["--sample-terms", str(terms)]
    res = run(cmd)
    out = res.stdout + res.stderr
    for line in out.splitlines():
        if line.startswith(("BodyText: sample terms", "PrvText: sample terms")):
            clean = line.endswith("0건")
            record(
                "PASS" if clean else "FAIL",
                f"HWP {line.split(':')[0]} sample terms",
                line.split(":", 1)[1].strip(),
            )
        if line.startswith("gray or italic paragraphs"):
            n = int(line.rsplit(":", 1)[1])
            record("PASS" if n == 0 else "FAIL", "HWP gray/italic paragraphs", str(n))
        if line.startswith("BodyText: placeholders"):
            empty = line.rstrip().endswith("[]")
            record(
                "PASS" if empty else ("FAIL" if final else "WARN"),
                "HWP placeholders",
                line.split(":", 1)[1].strip()[:200],
            )
    if not terms:
        record("WARN", "HWP sample terms", "no --sample-terms given")
    return dump.read_text(encoding="utf-8") if dump.exists() else ""


def pdf_text(path: Path, terms: list[str], final: bool, max_pages: int) -> str:
    info = run(["pdfinfo", str(path)]).stdout
    pages = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1)) if "Pages:" in info else -1
    record(
        "PASS" if 0 < pages <= max_pages else "WARN",
        "PDF pages",
        f"{pages} (limit {max_pages}, '5장 내외')",
    )
    fonts = run(["pdffonts", str(path)]).stdout.splitlines()[2:]
    not_emb = [f for f in fonts if f.split()[-5:-4] != ["yes"]]
    record(
        "PASS" if fonts and not not_emb else "FAIL",
        "PDF fonts embedded",
        f"{len(fonts)} fonts, {len(not_emb)} not embedded",
    )
    text = run(["pdftotext", str(path), "-"]).stdout
    hangul = sum("가" <= c <= "힣" for c in text)
    record(
        "PASS" if hangul > 500 else "FAIL",
        "PDF Korean text extractable",
        f"{hangul} Hangul characters",
    )
    hits = [t for t in terms if t in text]
    record("PASS" if not hits else "FAIL", "PDF sample terms", f"{len(hits)} found")
    ph = sorted(set(BRACKET.findall(flat(text))))
    record(
        "PASS" if not ph else ("FAIL" if final else "WARN"), "PDF placeholders", ", ".join(ph)[:200]
    )
    return text


def d12_abstract(d12: str, cell: str) -> str | None:
    """The abstract sentence under the d12 heading whose text starts with `cell`."""
    blocks = re.split(r"^## ", d12, flags=re.M)
    for block in blocks:
        head = block.splitlines()[0] if block else ""
        if cell.replace("칸 ", "") in head:
            m = re.search(r"abstract(?:\(공통\))?: 「([^」]*)」", block)
            return m.group(1) if m else None
    return None


def result_sentences(values: dict, d12: str) -> tuple[str, str, str] | None:
    """(status, written sentence, spoken sentence) the deliverables must carry."""
    status = values.get("status")
    if status == "미해제":
        return status, RUNNING_WRITTEN, RUNNING_SPOKEN
    cell = values["d12"]["cell_proposed"]
    abstract = d12_abstract(d12, cell)
    if abstract is None:
        record("FAIL", "result sentence", f"no d12 abstract for {cell!r}")
        return None
    filled = abstract
    for place, shown in values["d12"]["placeholders"].items():
        filled = filled.replace(place, str(shown))
    left = PLACEHOLDER.findall(filled)
    if left:
        record("FAIL", "result sentence placeholders", ", ".join(left))
    spoken = re.sub(r"\((?:[^()]*<[^()]*>[^()]*)\)", "", abstract)
    return status, filled, flat(spoken)


def check_result(
    values_path: Path, d12_path: Path, texts: dict[str, str], srt_text: str, final: bool
) -> None:
    values = json.loads(values_path.read_text(encoding="utf-8"))
    status = values.get("status")
    record(
        "FAIL"
        if final and status == "synthetic"
        else ("WARN" if status == "synthetic" else "PASS"),
        "values file status",
        f"{status} ({values_path.name})",
    )
    if final and status != "미해제":
        signed = "서명" in json.dumps(values.get("d12", {}).get("sign_off", ""), ensure_ascii=False)
        record("WARN" if not signed else "PASS", "values sign-off", "check W3·W4 signatures by eye")
    got = result_sentences(values, d12_path.read_text(encoding="utf-8"))
    if not got:
        return
    _, written, spoken = got
    for name, text in texts.items():
        if text:
            ok = nows(written) in nows(text)  # PDF line wraps split words
            record(
                "PASS" if ok else "FAIL", f"{name} carries the result sentence", written[:60] + "…"
            )
    if srt_text:
        ok = nows(spoken) in nows(srt_text)
        record(
            "PASS" if ok else "FAIL", "captions carry the spoken result sentence", spoken[:60] + "…"
        )


def srt_check(path: Path, duration: float | None) -> str:
    raw = path.read_text(encoding="utf-8-sig")
    cues = re.findall(
        r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})\n(.*?)(?:\n\n|\Z)",
        raw,
        re.S,
    )
    times = [
        (
            int(a) * 3600 + int(b) * 60 + int(c) + int(d) / 1000,
            int(e) * 3600 + int(f) * 60 + int(g) + int(h) / 1000,
        )
        for a, b, c, d, e, f, g, h, _ in cues
    ]
    mono = all(s < e for s, e in times) and all(
        times[i][1] <= times[i + 1][0] + 1e-6 for i in range(len(times) - 1)
    )
    record(
        "PASS" if cues and mono else "FAIL",
        "captions parse and times are monotonic",
        f"{len(cues)} cues",
    )
    if duration and times:
        record(
            "PASS" if times[-1][1] <= duration + 0.5 else "FAIL",
            "captions inside the video",
            f"last {times[-1][1]:.1f}s / {duration:.1f}s",
        )
    return " ".join(t for *_, t in cues)


def mp4_check(path: Path, max_seconds: float) -> float | None:
    probe = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,width,height:format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    meta = json.loads(probe.stdout or "{}")
    streams = meta.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    dur = float(meta.get("format", {}).get("duration", 0))
    record(
        "PASS"
        if video.get("codec_name") == "h264" and audio.get("codec_name") == "aac"
        else "FAIL",
        "MP4 codecs",
        f"{video.get('codec_name')} + {audio.get('codec_name')}",
    )
    record(
        "PASS" if (video.get("width"), video.get("height")) == (1920, 1080) else "WARN",
        "MP4 1920x1080",
        f"{video.get('width')}x{video.get('height')}",
    )
    record(
        "PASS" if 0 < dur <= max_seconds else "FAIL",
        "MP4 duration",
        f"{dur:.1f}s (limit {max_seconds:.0f}s)",
    )
    dec = run(
        [
            "nice",
            "-n",
            "19",
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-threads",
            "2",
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ]
    )
    record(
        "PASS" if dec.returncode == 0 and not dec.stderr.strip() else "FAIL",
        "MP4 decodes end to end",
        dec.stderr.strip()[:200],
    )
    loud = run(
        [
            "nice",
            "-n",
            "19",
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-threads",
            "2",
            "-i",
            str(path),
            "-vn",
            "-af",
            "ebur128",
            "-f",
            "null",
            "-",
        ]
    ).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", loud)
    if m:
        lufs = float(m[-1])
        record(
            "PASS" if -23 <= lufs <= -12 else "WARN",
            "MP4 integrated loudness",
            f"{lufs} LUFS (aim -16)",
        )
    return dur


def main() -> None:
    ap = argparse.ArgumentParser()
    for name in ("hwp", "pdf", "mp4", "srt", "values", "d12", "sample-terms", "work"):
        ap.add_argument(f"--{name}", type=Path)
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--max-pages", type=int, default=6)
    ap.add_argument("--max-seconds", type=float, default=300)
    a = ap.parse_args()
    work = a.work or Path("/tmp")
    work.mkdir(parents=True, exist_ok=True)
    terms = (
        json.loads(a.sample_terms.read_text(encoding="utf-8"))["sample_terms"]
        if a.sample_terms
        else []
    )

    for label, path in (
        ("HWP", a.hwp),
        ("PDF", a.pdf),
        ("MP4", a.mp4),
        ("SRT", a.srt),
        ("values", a.values),
    ):
        if path is None:
            record("SKIP", f"{label} not checked")
        elif not path.exists():
            record("FAIL", f"{label} missing", str(path))
        else:
            record("INFO", f"{label} sha256", f"{sha256(path)}  {path.name}")

    texts: dict[str, str] = {}
    if a.hwp and a.hwp.exists():
        texts["HWP"] = hwp_text(a.hwp, a.sample_terms, a.final, work)
    if a.pdf and a.pdf.exists():
        texts["PDF"] = pdf_text(a.pdf, terms, a.final, a.max_pages)
    duration = mp4_check(a.mp4, a.max_seconds) if a.mp4 and a.mp4.exists() else None
    srt_text = srt_check(a.srt, duration) if a.srt and a.srt.exists() else ""
    if a.values and a.values.exists() and a.d12:
        check_result(a.values, a.d12, texts, srt_text, a.final)

    print("\nNEEDS A HUMAN EYE (not automated):")
    for item in (
        "HWP opens in Hancom; Hancom page count and original fonts",
        "figures and captions look right in the Hancom-saved PDF",
        "video: picture, sound and captions in sync on a real player; no personal info on screen",
        "signature, date and participant-number file names (11/23 notice)",
    ):
        print("  -", item)
    fails = [r for r in results if r[0] == "FAIL"]
    print(f"\nSUMMARY: {len(fails)} FAIL, {sum(r[0] == 'WARN' for r in results)} WARN")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
