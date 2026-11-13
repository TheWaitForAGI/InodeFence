#!/usr/bin/env bash
# One command: fill the capstone report form → figures (one row each) → scrub preview streams →
# checks → rhwp 0.9.0 render → approximate PDF. Writes only under <outdir>.
#
# usage: build_report.sh <tooldir> <template.hwp> <sample-terms.json> <outdir> [fill_form.py fill options]
#   <tooldir>          made by setup_tools.sh (patched claw-hwp, @rhwp/core 0.9.0, venv)
#   <template.hwp>     the school form (not in this public repo; cell-map.json pins its sha256)
#   <sample-terms.json> the form's sample names/topics (not in this repo), for the leak check
#   extra options      passed to `fill_form.py fill`, e.g. --header-values <values.json> --final
#
# The approximate PDF uses rhwp's layout and substitute fonts, NOT Hancom's. Opening in Hancom,
# its page count and fonts, and the final PDF save remain a human step.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../../../.." && pwd)"
tools="$(realpath "$1")"; template="$(realpath "$2")"; terms="$(realpath "$3")"; out="$(realpath -m "$4")"
shift 4
fill="$repo/paper/deliverables/hwp/fill_form.py"
spec_in="$here/figures-spec.json"
mkdir -p "$out"
log="$out/build.log"; : > "$log"
step() { echo "== $*" | tee -a "$log"; }

step "inputs"
(cd "$repo" && echo "repo HEAD $(git rev-parse --short HEAD) dirty=$(git status --porcelain | wc -l)") | tee -a "$log"
cat "$tools/claw-hwp/VERSION" | tee -a "$log"
sha256sum "$template" "$repo/paper/deliverables/capstone-report-form-body.md" "$spec_in" | tee -a "$log"

# figure paths in the spec are repo-relative; resolve them and add the tool dir
python3 -I - "$spec_in" "$repo" "$tools/claw-hwp" "$out/figures-spec.json" <<'PY'
import json, sys
from pathlib import Path
spec = json.load(open(sys.argv[1], encoding="utf-8"))
repo = Path(sys.argv[2])
spec["tool"] = sys.argv[3]
for f in spec["figures"]:
    f["path"] = str((repo / f["path"]).resolve())
json.dump(spec, open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PY

step "1 fill"
nice -n 19 python3 "$fill" --scripts "$tools/claw-hwp/scripts" fill --template "$template" --out "$out/1-filled.hwp" "$@" 2>&1 | tee -a "$log"

step "2 figures"
nice -n 19 python3 -I "$here/figures_step.py" "$out/1-filled.hwp" "$out/report.hwp" "$out/figures-spec.json" | tee -a "$log"

step "3 paragraph dump, then scrub preview streams"
nice -n 19 python3 "$fill" check "$out/report.hwp" --sample-terms "$terms" --dump-text "$out/report-paras.md" > /dev/null 2>&1 || true
"$tools/venv/bin/python" -I "$here/scrub_preview.py" "$out/report.hwp" "$out/report-paras.md" | tee -a "$log"

step "4 form check (sample terms, gray/italic, placeholders)"
nice -n 19 python3 "$fill" check "$out/report.hwp" --sample-terms "$terms" --dump-text "$out/report-paras.md" 2>&1 | tee "$out/check-form.txt" | tee -a "$log" || true

step "5 structure check (independent olefile parser)"
n=$(python3 -I -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["figures"]))' "$out/figures-spec.json")
mapfile -t figs < <(python3 -I -c 'import json,sys; [print(f["path"]) for f in json.load(open(sys.argv[1]))["figures"]]' "$out/figures-spec.json")
"$tools/venv/bin/python" -I "$here/check_hwp.py" --cell-delta $((n - 1)) "$out/1-filled.hwp" "$out/report.hwp" "${figs[@]}" > "$out/check-structure.txt" || true
tail -1 "$out/check-structure.txt" | tee -a "$log"

step "6 render (rhwp 0.9.0) + approximate PDF"
"$here/render.sh" "$tools" "$out/report.hwp" "$out/render" | tee -a "$log"
cp "$out/render/approx.pdf" "$out/report-approx.pdf"
pdfinfo "$out/report-approx.pdf" | grep -E "^Pages" | tee -a "$log"
pdffonts "$out/report-approx.pdf" > "$out/pdffonts.txt"
awk 'NR>2 && $(NF-4)!="yes"{bad=1} END{print (bad?"FAIL":"PASS")" fonts embedded"}' "$out/pdffonts.txt" | tee -a "$log"
caps=$(for f in "$out"/render/svg/page-*.svg; do grep -o '>[^<]\{1,3\}<' "$f" | tr -d '<>\n'; echo; done | grep -o '그림[0-9]\.' | sort -u | wc -l)
echo "captions rendered: $caps / $n" | tee -a "$log"

step "summary"
sha256sum "$out/report.hwp" "$out/report-approx.pdf" | tee -a "$log"
grep -E "RESULT|sample terms|gray or italic|fonts embedded|captions rendered|^Pages" "$log" | sed 's/^/  /'
