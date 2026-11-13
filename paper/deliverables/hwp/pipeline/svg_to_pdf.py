"""Approximate PDF from rhwp page SVGs (NOT Hancom's layout).

usage: svg_to_pdf.py <svgdir> <out.pdf>
"""

import glob
import os
import subprocess
import sys
import tempfile

import cairosvg

svgdir, out = sys.argv[1], sys.argv[2]
pages = sorted(glob.glob(os.path.join(svgdir, "page-*.svg")))
with tempfile.TemporaryDirectory() as t:
    parts = []
    for i, p in enumerate(pages):
        q = os.path.join(t, f"{i:03d}.pdf")
        cairosvg.svg2pdf(url=p, write_to=q)
        parts.append(q)
    subprocess.run(["pdfunite", *parts, out], check=True)
print(out, len(pages), "pages")
