"""Time each script sentence of one recorded block from local speech recognition.

usage: asr_align.py <audio> <script_text.txt> <out_prefix> [--model small]

Caption TEXT is always the script sentence, never the recognised words; only the TIMES come from
the recognised words. Writes:
  <out_prefix>.cues.json   [{"index", "start", "end"}] for every sentence that could be located
  <out_prefix>.asr.json    the recognised words with times
  <out_prefix>.check.json  similarity (script vs recognition), sentences that could not be located
A low similarity means a misread or skipped sentence: the take is flagged for a retake, not fixed.
CPU only (int8), local model, two threads; the audio is never sent anywhere. Runs in its own venv
(faster-whisper 1.1.1); audio is decoded with the system ffmpeg because the PyAV call in that
version fails on this host.
"""

import argparse
import difflib
import json
import re
import subprocess
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel


def norm(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text).lower()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.?!])\s+", " ".join(text.split()))
    return [p for p in parts if p.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("script")
    ap.add_argument("out_prefix")
    ap.add_argument("--model", default="small")
    a = ap.parse_args()

    model = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=2)
    pcm = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", a.audio, "-ac", "1", "-ar", "16000"]
        + ["-f", "s16le", "-"],
        capture_output=True,
        check=True,
    ).stdout
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    segs, info = model.transcribe(
        audio, language="ko", word_timestamps=True, beam_size=5, vad_filter=True
    )
    words = [{"w": w.word, "start": w.start, "end": w.end} for s in segs for w in (s.words or [])]

    rec_chars: list[str] = []
    rec_times: list[tuple[float, float]] = []
    for w in words:
        chars = norm(w["w"])
        span = (w["end"] - w["start"]) / max(len(chars), 1)
        for k, ch in enumerate(chars):
            rec_chars.append(ch)
            rec_times.append((w["start"] + span * k, w["start"] + span * (k + 1)))
    rec = "".join(rec_chars)

    sents = sentences(Path(a.script).read_text(encoding="utf-8"))
    ref = "".join(norm(s) for s in sents)
    matcher = difflib.SequenceMatcher(None, ref, rec, autojunk=False)
    ref2rec = {}
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            ref2rec[block.a + k] = block.b + k

    cues, unplaced, pos = [], [], 0
    for index, sentence in enumerate(sents):
        n = len(norm(sentence))
        hits = [ref2rec[i] for i in range(pos, pos + n) if i in ref2rec]
        pos += n
        if len(hits) < max(2, n // 3):
            unplaced.append(index)
            continue
        cues.append(
            {"index": index, "start": rec_times[min(hits)][0], "end": rec_times[max(hits)][1]}
        )

    out = Path(a.out_prefix)
    out.with_suffix(".cues.json").write_text(json.dumps(cues, indent=1), encoding="utf-8")
    out.with_suffix(".asr.json").write_text(
        json.dumps(
            {"language": info.language, "duration": info.duration, "words": words},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    report = {
        "model": a.model,
        "similarity": round(matcher.ratio(), 4),
        "script_sentences": len(sents),
        "located": len(cues),
        "unplaced": unplaced,
        "recognised_text": "".join(w["w"] for w in words).strip(),
    }
    out.with_suffix(".check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in ("similarity", "script_sentences", "located")}))


if __name__ == "__main__":
    main()
