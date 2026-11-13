#!/usr/bin/env bash
# rhwp 0.9.0 page render + approximate PDF (NOT Hancom's layout or fonts).
# usage: render.sh <tooldir> <file.hwp> <outdir>     env: FONT_DIR (default /mnt/c/Windows/Fonts)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tools="$(realpath "$1")"; in="$(realpath "$2")"; outdir="$(realpath -m "$3")"
rm -rf "$outdir"; mkdir -p "$outdir"
(cd "$here" && RHWP_DIR="$tools/rhwp/core" nice -n 19 node render_pages.mjs "$in" "$outdir/svg") | tee "$outdir/render.json"
mkdir -p "$tools/fontcache"
sed -e "s#@FONTDIR@#${FONT_DIR:-/mnt/c/Windows/Fonts}#" -e "s#@CACHEDIR@#$tools/fontcache#" "$here/fonts.conf.in" > "$outdir/fonts.conf"
FONTCONFIG_FILE="$outdir/fonts.conf" nice -n 19 "$tools/venv/bin/python" -I "$here/svg_to_pdf.py" "$outdir/svg" "$outdir/approx.pdf"
nice -n 19 pdftoppm -r 60 -png "$outdir/approx.pdf" "$outdir/page"
