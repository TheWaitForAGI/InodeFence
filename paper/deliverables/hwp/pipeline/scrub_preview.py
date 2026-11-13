"""Overwrite the HWP preview streams so the form's sample text and thumbnail do not ship.

usage: scrub_preview.py <file.hwp> <paragraphs.md>

PrvText (UTF-16LE, uncompressed) keeps the template's sample paragraphs until Hancom re-saves the
file, and PrvImage keeps a thumbnail of the sample page. olefile can only rewrite a stream at its
current size, so:
  - PrvText becomes the start of our own body text (from `fill_form.py check --dump-text`),
    padded with spaces to the same byte length;
  - PrvImage becomes a 1x1 white PNG followed by zero padding (PNG readers stop at IEND).
Edits the file in place: run it on the pipeline's own output only.
"""

import struct
import sys
import zlib
from pathlib import Path

import olefile


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\xff\xff")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def main() -> None:
    path, paras = Path(sys.argv[1]), Path(sys.argv[2])
    text = " ".join(
        line.strip() for line in paras.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    ole = olefile.OleFileIO(str(path), write_mode=True)
    try:
        size = ole.get_size("PrvText")
        body = text.encode("utf-16le")[: size - size % 2]
        body = body[: len(body) - len(body) % 2]
        body += " ".encode("utf-16le") * ((size - len(body)) // 2)
        ole.write_stream("PrvText", body + b"\x00" * (size - len(body)))
        if ole.exists("PrvImage"):
            isize = ole.get_size("PrvImage")
            png = tiny_png()
            if isize < len(png):
                raise SystemExit("PrvImage smaller than a 1x1 PNG")
            ole.write_stream("PrvImage", png + b"\x00" * (isize - len(png)))
    finally:
        ole.close()
    print(f"preview scrubbed: PrvText {size} B, PrvImage replaced")


if __name__ == "__main__":
    main()
