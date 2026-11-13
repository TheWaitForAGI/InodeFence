"""Independent structural check of an HWP 5 file after image insertion (olefile + zlib only).

Written by the orchestrator session (2026-11-13), --cell-delta added by W5.

usage: check_hwp.py [--cell-delta N] <before.hwp> <after.hwp> <image>...

W5 copy (2026-11-13) of the ORCH verifier: --cell-delta allows the figure step's row change
(n new full-width rows minus the removed caption row = n-1 cells).
"""

import difflib
import hashlib
import struct
import sys
import zlib

import olefile

TAGS = {
    16: "DOCUMENT_PROPERTIES",
    17: "ID_MAPPINGS",
    18: "BIN_DATA",
    66: "PARA_HEADER",
    67: "PARA_TEXT",
    71: "CTRL_HEADER",
    72: "LIST_HEADER",
    76: "SHAPE_COMPONENT",
    85: "SHAPE_COMPONENT_PICTURE",
    77: "TABLE",
}


def records(raw):
    off = 0
    out = []
    while off < len(raw):
        (h,) = struct.unpack_from("<I", raw, off)
        tag, level, size = h & 0x3FF, (h >> 10) & 0x3FF, h >> 20
        off += 4
        if size == 0xFFF:
            (size,) = struct.unpack_from("<I", raw, off)
            off += 4
        out.append((tag, level, off, size))
        off += size
    assert off == len(raw), f"record walk ended at {off}, stream is {len(raw)}"
    return out


def load(path):
    ole = olefile.OleFileIO(path)
    hdr = ole.openstream("FileHeader").read()
    assert hdr[:17] == b"HWP Document File", "bad signature"
    compressed = bool(struct.unpack_from("<I", hdr, 36)[0] & 1)

    def stream(name):
        data = ole.openstream(name).read()
        return zlib.decompress(data, -15) if compressed else data

    info = {"ole": ole, "compressed": compressed, "streams": ["/".join(s) for s in ole.listdir()]}
    info["docinfo"] = stream("DocInfo")
    info["section0"] = stream("BodyText/Section0")
    info["stream"] = stream
    return info


def text_of(raw, recs):
    """All PARA_TEXT content as text, control chars dropped, in stream order."""
    parts = []
    for tag, _level, off, size in recs:
        if tag != 67:
            continue
        ws = struct.unpack_from(f"<{size // 2}H", raw, off)
        i, s = 0, []
        while i < len(ws):
            c = ws[i]
            if c < 32:
                if c in (0, 10, 13) or 24 <= c <= 31:
                    s.append("\n" if c in (10, 13) else "")
                    i += 1
                else:
                    i += 8  # inline/extended control occupies 8 wchars
                continue
            s.append(chr(c))
            i += 1
        parts.append("".join(s))
    return parts


def summarize(label, d):
    di, s0 = records(d["docinfo"]), records(d["section0"])
    bin_defs = [r for r in di if r[0] == 18]
    idm = next(r for r in di if r[0] == 17)
    bin_count = struct.unpack_from("<i", d["docinfo"], idm[2])[0]
    pics = [r for r in s0 if r[0] == 85]
    top_paras = [r for r in s0 if r[0] == 66 and r[1] == 0]
    tables = [r for r in s0 if r[0] == 77]
    cells = [r for r in s0 if r[0] == 72 and r[1] == 2]
    bins = sorted(s for s in d["streams"] if s.startswith("BinData/"))
    print(f"[{label}] compressed={d['compressed']} streams={len(d['streams'])} BinData={bins}")
    print(
        f"[{label}] DocInfo: BIN_DATA defs={len(bin_defs)} ID_MAPPINGS.binData={bin_count} | "
        f"Section0: top paragraphs={len(top_paras)} tables={len(tables)} cells={len(cells)} "
        f"pictures={len(pics)} records={len(s0)}"
    )
    return dict(
        bin_defs=len(bin_defs),
        bin_count=bin_count,
        pics=pics,
        top=len(top_paras),
        tables=len(tables),
        cells=len(cells),
        bins=bins,
        s0=s0,
        di=di,
    )


args = sys.argv[1:]
cell_delta = 0
if args[:1] == ["--cell-delta"]:
    cell_delta, args = int(args[1]), args[2:]
before, after, images = load(args[0]), load(args[1]), args[2:]
b, a = summarize("before", before), summarize("after", after)
ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail else ""))


n = len(images)
check(
    "BIN_DATA defs grew by image count",
    a["bin_defs"] == b["bin_defs"] + n,
    f"{b['bin_defs']} → {a['bin_defs']}",
)
check(
    "ID_MAPPINGS binData count matches defs", a["bin_count"] == a["bin_defs"], f"{a['bin_count']}"
)
check(
    "picture controls grew by image count",
    len(a["pics"]) == len(b["pics"]) + n,
    f"{len(b['pics'])} → {len(a['pics'])}",
)
check("top-level paragraphs unchanged", a["top"] == b["top"], f"{a['top']}")
check(
    f"table count unchanged, cells +{cell_delta}",
    (a["tables"], a["cells"]) == (b["tables"], b["cells"] + cell_delta),
    f"{a['tables']} tables, {a['cells']} cells",
)
new_bins = [s for s in a["bins"] if s not in b["bins"]]
check("new BinData streams = image count", len(new_bins) == n, str(new_bins))
want = {hashlib.sha256(open(p, "rb").read()).hexdigest(): p.split("/")[-1] for p in images}
got = {}
for s in new_bins:
    data = after["stream"](s)
    got[hashlib.sha256(data).hexdigest()] = (s, len(data), after["ole"].get_size(s))
check(
    "stored image bytes equal the source files (sha256 after inflate)",
    set(got) == set(want),
    "; ".join(f"{want.get(h, '?')} ↔ {v[0]} {v[1]} B (stored {v[2]} B)" for h, v in got.items()),
)
check(
    "every new image stream is >= 4096 B stored (regular FAT range)",
    all(v[2] >= 4096 for v in got.values()),
)
old_same = all(before["stream"](s) == after["stream"](s) for s in b["bins"])
check("pre-existing BinData streams byte-identical", old_same)
# picture → BinData id references
ids = [
    struct.unpack_from("<H", after["section0"], off + 71)[0]
    for _, _, off, size in a["pics"]
    if size >= 73
]
print("picture binData ids (after):", ids)
check("each picture references a defined BinData id", all(1 <= i <= a["bin_defs"] for i in ids))
tb, ta = text_of(before["section0"], b["s0"]), text_of(after["section0"], a["s0"])
jb, ja = "\n".join(t for t in tb if t.strip()), "\n".join(t for t in ta if t.strip())
diff = [
    ln
    for ln in difflib.unified_diff(jb.split("\n"), ja.split("\n"), lineterm="", n=0)
    if ln[:1] in "+-" and ln[:3] not in ("+++", "---")
]
print(f"text paragraphs: before {len(tb)}, after {len(ta)}; changed text lines: {len(diff)}")
for ln in diff[:12]:
    print("   ", ln[:150])
check(
    "no body text lost (every non-empty line before is still present)",
    all(ln in ja for ln in jb.split("\n") if ln.strip()),
)
print("RESULT", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
