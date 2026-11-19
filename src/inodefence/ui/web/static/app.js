"use strict";
/* InodeFence dashboard. Reads the GET /api endpoints and draws them. No external code.

   Display rules it must keep (research rules):
   - a missing value is "—"/"?", never 0; no bar/graph is drawn for an absent value (empty state);
   - termination, oracle violation (a candidate), unjudged, harness error and replay stay separate;
   - a flagged violation is only ever labelled a candidate (or one that needs a reproduction check),
     never escalated to a stronger word; a replay reports a conclusion with n/judged (denominator =
     judged rounds, never rounds_done; no ratio when judged is 0);
   - a result the strict reader refused is shown "as stored (not validated)" as a visible mark;
   - a run whose result could not be read is not counted as zero (it is reported as not read);
   - file contents and entry names are never shown (paths and hashes only). */

const EM_DASH = "—";
const SYMBOL = { ok: "✓", warn: "!", bad: "✗", info: "i", muted: "·", accent: "›" };
const TONE = {
  OK: "ok", PASS: "ok", REPRODUCED: "ok", COMPLETE: "ok", YES: "ok", SAME: "ok",
  WARN: "warn", UNKNOWN: "warn", UNJUDGED: "warn", STALLED: "warn", RUNNING: "info",
  CANDIDATE: "warn", "AS STORED": "warn", "CANDIDATE NEEDS REPRO CHECK": "warn",
  FAIL: "bad", ERROR: "bad", "RUN ERROR": "bad",
};
// A fixed colour per known target, so node-tar reads the same everywhere.
const TARGET_COLOR = { "node-tar": "--if-series-1", "python-tarfile": "--if-series-2", decompress: "--if-series-3", "oras-go": "--if-series-4" };
function targetColor(name) {
  if (TARGET_COLOR[name]) return TARGET_COLOR[name];
  let h = 0; for (const c of String(name || "")) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return `--if-series-${(h % 6) + 1}`;
}
// Termination is a separate axis from the verdict: success is neutral, the rest carry a tone.
const TERM_COLOR = { success: "--if-muted", rejected: "--if-warn", failed: "--if-bad", timed_out: "--if-bad", build_invalid: "--if-warn", unknown: "--if-muted" };
const REPLAY_LABEL = {
  reproduced_violation: "reproduced", partially_reproduced: "partially", not_reproduced: "not reproduced",
  no_violation: "no violation", new_violation: "new violation", unjudged: "unjudged",
  infrastructure_failure: "infra failure", no_rounds: "no rounds",
};
// Inline SVG icons (no external icon font). viewBox 0 0 24 24, stroke = currentColor.
const ICONS = {
  overview: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
  targets: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
  experiments: '<path d="M9 3h6M10 3v6l-5 8.5A2 2 0 0 0 7 21h10a2 2 0 0 0 2-3.5L14 9V3"/>',
  findings: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  replay: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
  artifacts: '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/>',
  runs: '<path d="M3 12h4l3 8 4-16 3 8h4"/>',
  candidates: '<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
  brand: '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M12 7v10M7 9.5l10 5M17 9.5l-10 5"/>',
};

function tone(word) { return word == null ? "muted" : (TONE[String(word).toUpperCase().replace(/_/g, " ")] || "muted"); }

const $ = (sel, root) => (root || document).querySelector(sel);
function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v; // only ever constant markup we build, never API text
    else if (k === "style") node.setAttribute("style", v);
    else node.setAttribute(k, v);
  }
  for (const c of children || []) if (c != null) node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return node;
}
function svgIcon(name, cls) {
  const wrap = document.createElement("span");
  wrap.innerHTML = `<svg class="icon ${cls || ""}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;
  return wrap.firstChild;
}
function dash(v) { return v == null ? EM_DASH : String(v); }
function num(v) { return v == null ? EM_DASH : Number(v).toLocaleString(); }
function chip(word, cls, title) {
  const t = tone(word);
  const label = word == null ? EM_DASH : String(word).toUpperCase().replace(/_/g, " ");
  return el("span", { class: `chip ${cls || "chip-" + t}`, title: title || "" }, [`${SYMBOL[t]} ${label}`]);
}
function kindChip(kind) { return el("span", { class: `chip chip-sm chip-kind-${kind}` }, [dash(kind)]); }

async function api(path) {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}
function empty(title, lines, where) {
  return el("div", { class: "empty" }, [
    el("div", { class: "title" }, [title]),
    ...(lines || []).map((l) => el("div", {}, Array.isArray(l) ? l : [l])),
    where ? el("div", { class: "where mono" }, [where]) : null,
  ]);
}
function cardLabeled(label, body, span2) {
  return el("div", { class: "labeled" + (span2 ? " span-2" : "") }, [
    el("div", { class: "card-label" }, [label]),
    el("div", { class: "card" }, [body]),
  ]);
}

/* bars: rows [{name, value, color, title}] */
function barChart(rows) {
  const withVal = rows.filter((r) => r.value != null);
  if (withVal.length === 0) return empty("no data yet", ["no value for this in the scanned runs"]);
  const max = Math.max(1, ...withVal.map((r) => r.value));
  const box = el("div", { class: "bars" }, []);
  for (const r of rows) {
    const pct = r.value == null ? 0 : Math.round((r.value / max) * 100);
    const fill = el("div", { class: "bar-fill" }, []);
    fill.style.width = `${pct}%`;
    fill.style.background = `var(${r.color || "--if-series-1"})`;
    box.appendChild(el("div", { class: "bar-row" }, [
      el("div", { class: "name", title: r.title || r.name }, [r.name]),
      el("div", { class: "bar-track" }, [fill]),
      el("div", { class: "val num" }, [num(r.value)]),
    ]));
  }
  return box;
}

/* area graph of observed runs over time for one active run (axes as HTML so text never distorts) */
function areaGraph(points, budget, since) {
  if (!points || points.length < 2) return null;
  const W = 600, H = 170, pad = 6;
  const t0 = points[0].t, t1 = points[points.length - 1].t;
  const span = Math.max(1e-6, t1 - t0);
  const ymax = Math.max(budget || 0, ...points.map((p) => p.runs || 0), 1);
  const x = (p) => pad + ((p.t - t0) / span) * (W - 2 * pad);
  const y = (v) => H - pad - ((v || 0) / ymax) * (H - 2 * pad);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(p).toFixed(1)} ${y(p.runs).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const area = `${line} L${x(last).toFixed(1)} ${H - pad} L${x(points[0]).toFixed(1)} ${H - pad} Z`;
  const budgetLine = budget
    ? `<line x1="${pad}" y1="${y(budget).toFixed(1)}" x2="${W - pad}" y2="${y(budget).toFixed(1)}" stroke="var(--if-muted)" stroke-width="1" stroke-dasharray="4 4" opacity="0.6"/>`
    : "";
  const svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    ${budgetLine}
    <path d="${area}" fill="var(--if-accent)" fill-opacity="0.14" stroke="none"/>
    <path d="${line}" fill="none" stroke="var(--if-accent)" stroke-width="2"/>
    <circle cx="${x(last).toFixed(1)}" cy="${y(last.runs).toFixed(1)}" r="3" fill="var(--if-accent)"/></svg>`;
  const nowStr = new Date(t1 * 1000).toLocaleTimeString();
  const wrap = el("div", { class: "area-wrap" }, [
    el("div", { class: "area-head" }, [
      el("span", { class: "muted" }, ["runs / budget"]),
      el("span", { class: "num", style: "color:var(--if-accent);font-weight:600" }, [`${num(last.runs)} / ${budget == null ? EM_DASH : num(budget)}`]),
    ]),
  ]);
  const plot = el("div", { class: "area-plot" }, []);
  const holder = el("div", { class: "area" }, []); holder.innerHTML = svg;
  plot.appendChild(holder);
  if (budget) {
    const pct = (v) => `${((y(v) / H) * 100).toFixed(0)}%`;
    plot.appendChild(el("span", { class: "ytick", style: `top:${pct(budget)}` }, [num(budget)]));
    plot.appendChild(el("span", { class: "ytick", style: `top:${pct(budget / 2)}` }, [num(Math.round(budget / 2))]));
    plot.appendChild(el("span", { class: "ytick", style: `top:${pct(0)}` }, ["0"]));
  }
  wrap.appendChild(plot);
  wrap.appendChild(el("div", { class: "area-foot" }, [
    el("span", {}, [`since ${since}`]),
    el("span", {}, [`now ${nowStr}`]),
  ]));
  return wrap;
}

const state = { runs: null, findings: null, replays: null, filter: "", series: {}, targetsCount: null, version: null, roots: [], selectedProgressKey: null };

function runKey(r) { return `${r.kind}:${r.root}:${r.run_id || ""}`; }
function fmtAge(s) { return s == null ? EM_DASH : (s < 90 ? `${Math.round(s)}s ago` : s < 5400 ? `${Math.round(s / 60)}m ago` : `${(s / 3600).toFixed(1)}h ago`); }
function toneChip(label, t, title) { return el("span", { class: `chip chip-${t} chip-sm`, title: title || "" }, [`${SYMBOL[t]} ${String(label).toUpperCase()}`]); }

// The stall decision (and its threshold) is the server's: `stalled` is true/false/null in status.
function runState(s) {
  if (s && s.source === "live" && s.state === "running") {
    if (s.stalled === true) return { label: "stalled", tone: "warn", active: false, age: s.progress_age_seconds };
    if (s.stalled === false) return { label: "running", tone: "info", active: true };
    return { label: "running (age ?)", tone: "warn", active: false }; // stalled null = age unknown
  }
  if (s && s.state) return { label: s.state, tone: tone(s.state), active: false };
  return null;
}
function tailId(id, n) { id = id || ""; n = n || 12; return id.length > n ? "…" + id.slice(-n) : id || EM_DASH; }

// Contracts use the same legend as the TUI / CLI / compare: V violated, - judged-not-violated, ? not judged.
function contractMark(v) { const t = v === true ? "bad" : v === false ? "muted" : "warn"; const s = v === true ? "V" : v === false ? "-" : "?"; return el("span", { class: `chip chip-sm chip-${t}` }, [s]); }
function contractCell(c) { return el("div", { class: "row-flex" }, ["c0", "c1", "c2"].map((k) => el("span", { class: "row-flex", style: "gap:3px" }, [el("span", { class: "muted", style: "font-size:11px" }, [k.toUpperCase()]), contractMark(c[k])]))); }
function contractLegend() { return el("div", { class: "note", style: "margin:6px 0 0" }, ["V violated · - judged, not violated · ? not judged / not observed"]); }
const CONCLUSION_TONE = { reproduced_violation: "ok", partially_reproduced: "warn", not_reproduced: "muted", no_violation: "muted", new_violation: "warn", unjudged: "warn", infrastructure_failure: "warn", no_rounds: "muted" };
function conclusionChip(conc) { const t = CONCLUSION_TONE[conc] || "muted"; return el("span", { class: `chip chip-sm chip-${t}`, title: conc || "" }, [REPLAY_LABEL[conc] || conc || "no rounds"]); }

/* -- Overview -- */
function renderOverview(view) {
  const runsData = state.runs, findingsData = state.findings, replaysData = state.replays;
  const runs = (runsData && runsData.runs) || [];
  const campaigns = runs.filter((r) => r.kind !== "replay");           // explore + verify only
  const scanned = campaigns.filter((r) => r.status);
  const notRead = scanned.filter((r) => ["not_ready", "unreadable"].includes(r.status.read_state));
  const readable = scanned.filter((r) => !notRead.includes(r));
  const campaignsTotal = campaigns.length;
  const active = scanned.filter((r) => runState(r.status)?.active).length;
  const stalledN = scanned.filter((r) => r.status.stalled === true).length;
  const finished = scanned.filter((r) => r.status.verdict != null).length;
  const candSum = readable.reduce((a, r) => a + (r.status.candidates || 0), 0);
  const needsRepro = readable.reduce((a, r) => a + (r.status.candidates_needs_repro || 0), 0);
  const replays = (replaysData && replaysData.replays) || [];
  const reproduced = replays.filter((r) => r.replay.conclusion === "reproduced_violation").length;

  // stat cards
  const stat = (label, big, sub, strip, icon) => {
    const card = el("div", { class: "stat card" }, [
      el("div", { class: "strip", style: `background:var(${strip})` }, []),
      svgIcon(icon, "sym"),
      el("div", { class: "card-label" }, [label]),
      el("div", { class: "big" }, [big]),
      el("div", { class: "substr" }, sub),
    ]);
    return card;
  };
  const statRow = el("div", { class: "stat-row" }, [
    stat("targets", state.targetsCount == null ? EM_DASH : String(state.targetsCount),
      [el("span", { class: "chip chip-sm chip-muted" }, ["registered drivers"])], "--if-accent", "targets"),
    stat("runs", String(campaignsTotal),
      [el("span", { class: "chip chip-sm chip-info" }, [`${active} active`]),
       stalledN ? el("span", { class: "chip chip-sm chip-warn" }, [`${stalledN} stalled`]) : null,
       el("span", { class: "chip chip-sm chip-muted" }, [`${finished} finished`])].filter(Boolean),
      "--if-info", "runs"),
    stat("violation candidates", readable.length === 0 ? EM_DASH : String(candSum),
      [el("span", { class: "chip chip-sm chip-warn" }, [`${needsRepro} need repro check`]), notRead.length ? el("span", { class: "chip chip-sm chip-muted" }, [`${notRead.length} not read`]) : null].filter(Boolean),
      candSum > 0 ? "--if-bad" : "--if-muted", "candidates"),
    stat("replays", String(replays.length),
      [replays.length ? el("span", { class: "chip chip-sm chip-ok" }, [`${reproduced} reproduced`]) : el("span", { class: "chip chip-sm chip-muted" }, ["none yet"])],
      "--if-ok", "replay"),
  ]);
  view.appendChild(statRow);

  // campaign progress (wide) + first chart row
  const activeRuns = scanned.filter((r) => runState(r.status)?.active);
  let progressBody = null, progressNote = null;
  const withSeries = activeRuns.map((r) => ({ r, key: runKey(r), pts: state.series[runKey(r)] || [] })).filter((x) => x.pts.length >= 2);
  if (withSeries.length) {
    const chosen = withSeries.find((x) => x.key === state.selectedProgressKey)
      || withSeries.slice().sort((a, b) => b.pts.length - a.pts.length)[0];
    const since = new Date(chosen.pts[0].t * 1000).toLocaleTimeString();
    const graph = areaGraph(chosen.pts, chosen.pts[chosen.pts.length - 1].budget, since);
    progressNote = `${chosen.r.target || EM_DASH} ${(chosen.r.run_id || "").slice(-16)}`;
    if (withSeries.length > 1) {
      const sel = el("div", { class: "selector" }, withSeries.map((x) => {
        const btn = el("button", { class: "selbtn" + (x.key === chosen.key ? " on" : ""), title: x.r.run_id || "" }, [`${x.r.target || "?"} ${tailId(x.r.run_id, 8)}`]);
        btn.addEventListener("click", () => { state.selectedProgressKey = x.key; const v = $("#view"); v.innerHTML = ""; renderOverview(v); });
        return btn;
      }));
      progressBody = el("div", {}, [sel, graph]);
    } else progressBody = graph;
  } else if (activeRuns.length) {
    progressBody = empty("no observed values yet", ["values appear while an active run reports (node-tar writes live numbers; the others do not)"]);
  } else {
    const rows = readable.filter((r) => r.status.runs != null && r.status.budget).slice(0, 8)
      .map((r) => ({ name: `${r.target || EM_DASH} ${(r.run_id || "").slice(-8)}`, value: r.status.runs, color: targetColor(r.target), title: `${num(r.status.runs)}/${num(r.status.budget)}` }));
    progressBody = rows.length ? barChart(rows) : empty("no active run", [["open this page while ", el("code", {}, ["inodefence explore --target node-tar --version latest"]), " runs to watch runs/budget climb"]]);
  }
  const progressCard = cardLabeled(progressNote ? `campaign progress · ${progressNote}` : "campaign progress", progressBody, true);

  // by-target (fixed colours)
  const byTarget = {};
  for (const r of readable) { if (!r.target) continue; const b = byTarget[r.target] || (byTarget[r.target] = { runs: 0, cand: 0 }); b.runs += 1; b.cand += (r.status.candidates || 0) + (r.status.candidates_needs_repro || 0); }
  const targetRunRows = Object.entries(byTarget).map(([name, v]) => ({ name, value: v.runs, color: targetColor(name) }));
  const targetCandRows = Object.entries(byTarget).map(([name, v]) => ({ name, value: v.cand, color: targetColor(name) }));

  const verdicts = { PASS: 0, FAIL: 0, ERROR: 0 };
  for (const r of scanned) { const v = r.status.verdict; if (v && verdicts[v] != null) verdicts[v] += 1; }
  const asStored = scanned.filter((r) => r.status.read_state === "unvalidated").length;
  const noResult = scanned.filter((r) => r.status.verdict == null && !["ok", "unvalidated"].includes(r.status.read_state)).length;
  const verdictRows = [
    { name: "PASS", value: verdicts.PASS, color: "--if-ok" },
    { name: "FAIL", value: verdicts.FAIL, color: "--if-bad" },
    { name: "ERROR", value: verdicts.ERROR, color: "--if-warn" },
    { name: "as stored", value: asStored, color: "--if-warn", title: "results the strict reader refused (shown as stored)" },
    { name: "no result yet", value: noResult, color: "--if-muted" },
  ];

  const terms = {};
  for (const r of scanned) for (const [k, n] of Object.entries(r.status.terminations || {})) { if (n == null) continue; terms[k] = (terms[k] || 0) + n; }
  const termRows = Object.entries(terms).map(([name, value]) => ({ name, value, color: TERM_COLOR[name] || "--if-muted" }));

  const concl = {};
  for (const r of replays) { const c = r.replay.conclusion || "none"; concl[c] = (concl[c] || 0) + 1; }
  const conclRows = Object.entries(concl).map(([name, value], i) => ({ name: REPLAY_LABEL[name] || name, title: name, value, color: `--if-series-${(i % 6) + 1}` }));

  const row1 = el("div", { class: "grid-3" }, [
    progressCard,
    cardLabeled("campaign verdicts", scanned.length ? barChart(verdictRows) : empty("no runs found", ["no explore or verify runs in the scanned folders"])),
  ]);
  const row2 = el("div", { class: "grid-3 auto" }, [
    cardLabeled("runs by target", targetRunRows.length ? barChart(targetRunRows) : empty("no runs found", [])),
    cardLabeled("candidates by target", targetCandRows.some((r) => r.value) ? barChart(targetCandRows) : empty("no candidates", ["no oracle-flagged cases in the scanned runs"])),
    cardLabeled("recent candidates", renderRecentCandidates(findingsData)),
  ]);
  const row3 = el("div", { class: "grid-3" }, [
    cardLabeled("termination of extractor", termRows.length ? barChart(termRows) : empty("no termination counts", ["no termination counts in the scanned results (live mid-run numbers are node-tar only)"])),
    cardLabeled("replays by conclusion", replays.length ? barChart(conclRows) : empty("no replays yet", [["run ", el("code", {}, ["inodefence replay <run-NNNNNN folder>"])]])),
  ]);
  view.appendChild(row1);
  view.appendChild(row2);
  view.appendChild(row3);
  view.appendChild(cardLabeled("runs", renderRunsTable(campaigns)));
}

function renderRecentCandidates(findingsData) {
  if (!findingsData) return empty("loading…", []);
  const items = findingsData.findings.filter((f) => f.case.finding);
  if (items.length === 0) return empty("no candidates", ["no oracle-flagged cases in the scanned runs"]);
  const list = el("div", { class: "rank-list" }, []);
  for (const f of items.slice(0, 10)) {
    const c = f.case;
    const marks = ["c0", "c1", "c2"].map((k) => c[k] === true ? el("span", { class: "chip chip-bad chip-sm" }, [k.toUpperCase()]) : null).filter(Boolean);
    marks.push(chip(c.finding, null, c.finding));
    if (f.validated === false) marks.push(chip("as stored", "chip-warn chip-sm", "result not validated by the strict reader"));
    list.appendChild(el("div", { class: "rank-item" }, [
      el("div", { style: "min-width:0" }, [el("div", { class: "mono", style: "overflow:hidden;text-overflow:ellipsis" }, [dash(c.case_id)]), el("div", { class: "meta" }, [`${f.target || EM_DASH}${f.version ? "@" + f.version : ""}`])]),
      el("div", { class: "row-flex wrap" }, marks),
    ]));
  }
  if (findingsData.truncated) list.appendChild(el("div", { class: "note", style: "margin:8px 0 0" }, [`from the most recent ${findingsData.runs_scanned} of ${findingsData.runs_total} runs`]));
  return list;
}

function renderRunsTable(campaigns) {
  const f = state.filter.trim().toLowerCase();
  const rows = campaigns.filter((r) => !f || JSON.stringify([r.target, r.version, r.kind, r.run_id]).toLowerCase().includes(f));
  if (rows.length === 0) {
    return empty(campaigns.length ? "no runs match the filter" : "no runs found",
      campaigns.length ? [] : [["start one with ", el("code", {}, ["inodefence explore --target node-tar --version latest"])]],
      campaigns.length ? null : `scanned: ${(state.roots || []).join("  ")}`);
  }
  const cols = ["kind", "run id", "target", "version", "budget", "progress", "cand", "state", "verdict", "updated", ""];
  const head = el("tr", {}, cols.map((h, i) => el("th", { class: [4, 5, 6, 9].includes(i) ? "r" : "" }, [h])));
  const body = el("tbody", {}, []);
  for (const r of rows) {
    const s = r.status;
    const runsN = s ? s.runs : null, budget = s ? s.budget : null;
    const pct = (s && runsN != null && budget) ? Math.min(100, Math.round((runsN / budget) * 100)) : null;
    let progCell;
    if (pct == null) progCell = el("span", { class: "dash" }, [EM_DASH]);
    else { const fill = el("div", { class: "prog-fill" }, []); fill.style.width = `${pct}%`; progCell = el("div", { class: "row-flex", style: "justify-content:flex-end" }, [el("span", { class: "muted num", style: "margin-right:6px" }, [`${num(runsN)}/${num(budget)}`]), el("div", { class: "prog" }, [fill])]); }
    const rs = runState(s);
    const stateCell = rs
      ? toneChip(rs.label, rs.tone, rs.age != null ? fmtAge(rs.age) : "")
      : (s && !s.verdict && r.target && r.target !== "node-tar"
          ? el("span", { class: "chip chip-sm chip-muted" }, ["no live data"])
          : el("span", { class: "dash" }, [EM_DASH]));
    const verdictCell = el("div", { class: "row-flex" }, [
      s && s.verdict ? chip(s.verdict) : el("span", { class: "dash" }, [EM_DASH]),
      s && s.read_state === "unvalidated" ? chip("as stored", "chip-warn chip-sm", "result not validated by the strict reader") : null,
    ]);
    const cand = s ? ((s.candidates || 0) + (s.candidates_needs_repro || 0)) : null;
    const fullId = r.run_id || r.id || "";
    const idTail = fullId.length > 12 ? "…" + fullId.slice(-12) : fullId || EM_DASH;
    body.appendChild(el("tr", {}, [
      el("td", {}, [kindChip(r.kind)]),
      el("td", { class: "mono", title: r.run_id || r.id }, [dash(idTail)]),
      el("td", {}, [dash(r.target)]),
      el("td", { class: "mono" }, [dash(r.version)]),
      el("td", { class: "r num" }, [s ? num(budget) : el("span", { class: "dash" }, [EM_DASH])]),
      el("td", { class: "r" }, [progCell]),
      el("td", { class: "r num" }, [cand == null ? el("span", { class: "dash" }, [EM_DASH]) : String(cand)]),
      el("td", {}, [stateCell]),
      el("td", {}, [verdictCell]),
      el("td", { class: "r muted" }, [s ? fmtAge(s.progress_age_seconds) : EM_DASH]),
      el("td", {}, [el("a", { class: "go", href: `#/run/${r.id}`, title: "details" }, [SYMBOL.accent])]),
    ]));
  }
  return el("div", { class: "table-wrap" }, [el("table", { class: "runs" }, [el("thead", {}, [head]), body])]);
}

/* -- run detail (minimal) -- */
async function renderRunDetail(view, id) {
  view.appendChild(el("h2", { class: "page" }, ["Run"]));
  let data;
  try { data = await api(`/api/runs/${encodeURIComponent(id)}`); }
  catch (err) { view.appendChild(el("div", { class: "card" }, [empty("run not found", [String(err)])])); return; }
  const snap = data.snapshot;
  const s = snap.summary || {};
  const p = snap.progress || {};
  const terms = Object.entries(s.terminations || {}).filter(([, n]) => n != null).map(([k, n]) => `${k} ${n}`).join(", ") || null;
  const findings = (snap.findings || []).filter((f) => f.finding);
  const rows = [
    ["kind", snap.ref.kind], ["target", snap.ref.target], ["version", snap.ref.version],
    ["state", p.state], ["runs / budget", (p.runs == null && p.budget == null) ? null : `${p.runs == null ? EM_DASH : p.runs} / ${p.budget == null ? EM_DASH : p.budget}`],
    ["verdict", s.verdict],
    ["validated", s.validated == null ? null : (s.validated === false ? "as stored (not validated)" : "validated")],
    ["executed", s.executed], ["unjudged steps", s.unjudged_steps],
    ["terminations", terms], ["candidates", (snap.findings || []).length ? findings.length : null],
    ["result", s.result_path],
  ];
  const dl = el("div", { class: "rank-list" }, rows.map(([k, v]) => el("div", { class: "rank-item" }, [el("div", { class: "meta" }, [k]), el("div", { class: "mono" }, [v == null ? EM_DASH : String(v)])])));
  view.appendChild(cardLabeled("summary", dl));
  if (findings.length) {
    const list = el("div", { class: "rank-list" }, findings.map((f) => el("div", { class: "rank-item" }, [
      el("div", { class: "mono", style: "overflow:hidden;text-overflow:ellipsis" }, [dash(f.case_id)]),
      el("div", { class: "row-flex" }, [...["c0", "c1", "c2"].map((k) => f[k] === true ? el("span", { class: "chip chip-bad chip-sm" }, [k.toUpperCase()]) : null).filter(Boolean), chip(f.finding, null, f.finding)]),
    ])));
    view.appendChild(cardLabeled("candidates", list));
  }
  view.appendChild(el("div", { class: "note" }, [el("a", { class: "go", href: "#/overview" }, ["‹ back to overview"])]));
}

/* -- shared helpers for the secondary pages -- */
function kv(label, node) { return el("div", { class: "rank-item" }, [el("div", { class: "meta" }, [label]), typeof node === "string" || node == null ? el("div", { class: "mono" }, [node == null ? EM_DASH : node]) : node]); }
function fmtBytes(n) { if (n == null) return EM_DASH; if (n < 1024) return `${n} B`; const u = ["KB", "MB", "GB", "TB"]; let v = n, i = -1; do { v /= 1024; i++; } while (v >= 1024 && i < 3); return `${v.toFixed(1)} ${u[i]}`; }
function fmtTime(epoch) { return epoch == null ? EM_DASH : new Date(epoch * 1000).toLocaleString(); }
function selectEl(opts, value, onChange) {
  const s = el("select", { class: "filt" }, opts.map((o) => { const op = el("option", { value: o.value }, [o.label]); if (o.value === value) op.setAttribute("selected", "selected"); return op; }));
  s.addEventListener("change", (e) => onChange(e.target.value));
  return s;
}
function truncNote(d) { return d && d.truncated ? el("div", { class: "note" }, [`most recent ${d.runs_scanned} of ${d.runs_total} runs`]) : null; }

/* -- Targets -- */
async function renderTargets(view) {
  view.appendChild(el("h2", { class: "page" }, ["Targets"]));
  let td, runsD, health;
  try { [td, runsD, health] = await Promise.all([api("/api/targets"), api("/api/runs"), api("/api/health")]); }
  catch (err) { view.appendChild(el("div", { class: "card" }, [empty("could not load targets", [String(err)])])); return; }
  const reg = td.state === "ok" ? (td.targets || {}) : {};
  const groups = (health && health.image_groups) || {};
  const agg = {};
  for (const r of runsD.runs || []) {
    if (r.kind === "replay" || !r.target) continue;
    const a = agg[r.target] || (agg[r.target] = { runs: 0, cand: 0, lastVerify: null, verdicts: { PASS: 0, FAIL: 0, ERROR: 0 } });
    a.runs += 1;
    if (r.status) {
      a.cand += (r.status.candidates || 0) + (r.status.candidates_needs_repro || 0);
      if (r.status.verdict && a.verdicts[r.status.verdict] != null) a.verdicts[r.status.verdict] += 1;
      if (r.kind === "verify" && r.status.verdict) a.lastVerify = { verdict: r.status.verdict, age: r.status.progress_age_seconds, updated_at: r.status.updated_at, version: r.version };
    }
  }
  const names = Object.keys(reg).length ? Object.keys(reg) : Object.keys(agg);
  if (names.length === 0) { view.appendChild(el("div", { class: "card" }, [empty("target registry not readable", td.state !== "ok" ? [td.reason || "no repository root configured"] : ["no targets registered"])])); return; }
  const cards = el("div", { class: "grid-4" }, names.map((name) => {
    const a = agg[name] || { runs: 0, cand: 0 };
    const lv = a.lastVerify;
    const dot = el("span", { class: "dot", style: `background:var(${targetColor(name)})` }, []);
    const whenStr = lv ? (lv.updated_at != null ? fmtTime(lv.updated_at) : fmtAge(lv.age)) : null;
    const lastVerify = lv
      ? el("div", { class: "row-flex", style: "flex-wrap:wrap;gap:6px" }, [lv.version ? el("span", { class: "mono muted", style: "font-size:11px" }, [lv.version]) : null, chip(lv.verdict), el("span", { class: "muted", style: "font-size:11px" }, [whenStr])])
      : el("span", { class: "muted" }, ["no verify yet"]);
    return el("div", { class: "card tcard" }, [
      el("div", { class: "row-flex", style: "margin-bottom:10px" }, [dot, el("span", { style: "font-weight:600" }, [name])]),
      el("div", { class: "tnums" }, [
        el("div", {}, [el("div", { class: "big2" }, [String(a.runs)]), el("div", { class: "card-label" }, ["runs"])]),
        el("div", {}, [el("div", { class: "big2", style: a.cand > 0 ? "color:var(--if-bad)" : "" }, [String(a.cand)]), el("div", { class: "card-label" }, ["candidates"])]),
      ]),
      el("div", { class: "rank-list", style: "margin-top:10px" }, [kv("last verify", lastVerify), kv("prepared images", groups[name] == null ? EM_DASH : String(groups[name]))]),
    ]);
  }));
  view.appendChild(cardLabeled("targets", cards));
  // registry table
  if (Object.keys(reg).length) {
    const head = el("tr", {}, ["target", "regression", "auto-prepare", "explore", "replay", "options"].map((h) => el("th", {}, [h])));
    const body = el("tbody", {}, Object.entries(reg).map(([name, f]) => {
      const opts = (f.options || []).map((o) => `--${o.name}${o.required ? "" : "?"}`).join(", ") || EM_DASH;
      const yn = (v) => v ? chip("YES", "chip-ok chip-sm") : chip("NO", "chip-muted chip-sm");
      return el("tr", {}, [
        el("td", {}, [name]), el("td", {}, [yn(f.regression !== false)]), el("td", {}, [yn(f.auto_prepare !== false)]),
        el("td", {}, [f.explore ? chip("YES", "chip-ok chip-sm") : el("span", { class: "chip chip-muted chip-sm", title: f.explore_reason || "" }, [`no`])]),
        el("td", {}, [yn(f.replay)]), el("td", { class: "mono muted" }, [opts]),
      ]);
    }));
    view.appendChild(cardLabeled("registry", el("div", { class: "table-wrap" }, [el("table", { class: "runs" }, [el("thead", {}, [head]), body])])));
  }
  // target comparison (not a dup of Overview's single-metric bars)
  const chead = el("tr", {}, ["target", "runs", "candidates", "PASS", "FAIL", "ERROR"].map((h, i) => el("th", { class: i >= 1 ? "r" : "" }, [h])));
  const cbody = el("tbody", {}, names.map((n) => {
    const a = agg[n] || { runs: 0, cand: 0, verdicts: {} };
    const v = a.verdicts || {};
    return el("tr", {}, [
      el("td", {}, [el("span", { class: "row-flex", style: "gap:6px" }, [el("span", { class: "dot", style: `background:var(${targetColor(n)})` }, []), n])]),
      el("td", { class: "r num" }, [String(a.runs || 0)]), el("td", { class: "r num" }, [String(a.cand || 0)]),
      el("td", { class: "r num" }, [String(v.PASS || 0)]), el("td", { class: "r num" }, [String(v.FAIL || 0)]), el("td", { class: "r num" }, [String(v.ERROR || 0)]),
    ]);
  }));
  view.appendChild(cardLabeled("target comparison", el("div", { class: "table-wrap" }, [el("table", { class: "runs" }, [el("thead", {}, [chead]), cbody])])));
}

/* -- Findings -- */
let findingsFilter = { target: "", contract: "", klass: "", conclusion: "" };
let findingsSelected = null;
async function renderFindings(view) {
  view.appendChild(el("h2", { class: "page" }, ["Findings"]));
  let fd, rd;
  try { [fd, rd] = await Promise.all([api("/api/findings?limit=500"), api("/api/replays?limit=500")]); }
  catch (err) { view.appendChild(el("div", { class: "card" }, [empty("could not load findings", [String(err)])])); return; }
  const byCase = {};
  for (const r of rd.replays || []) { const c = r.replay.original_case_id; if (c) byCase[c] = r.replay; }
  let items = (fd.findings || []).filter((f) => f.case.finding);
  const search = state.filter.trim().toLowerCase();
  const uniq = (arr) => [...new Set(arr.filter(Boolean))];
  const targets = uniq(items.map((f) => f.target));
  const apply = (list) => list.filter((f) => {
    if (findingsFilter.target && f.target !== findingsFilter.target) return false;
    if (findingsFilter.contract && f.case[findingsFilter.contract] !== true) return false;
    if (findingsFilter.klass && f.case.finding !== findingsFilter.klass) return false;
    if (findingsFilter.conclusion) { const rp = byCase[f.case.case_id]; if (!rp || rp.conclusion !== findingsFilter.conclusion) return false; }
    if (search && !JSON.stringify([f.case.case_id, f.target, f.version]).toLowerCase().includes(search)) return false;
    return true;
  });
  const shown = apply(items);
  const anyFilter = !!(findingsFilter.target || findingsFilter.contract || findingsFilter.klass || findingsFilter.conclusion || search);
  function rerender() { const v = $("#view"); v.innerHTML = ""; renderFindings(v); }
  const clearBtn = el("button", { class: "selbtn" }, ["clear filters"]);
  clearBtn.addEventListener("click", () => { findingsFilter = { target: "", contract: "", klass: "", conclusion: "" }; const s = $("#search"); if (s) s.value = ""; state.filter = ""; rerender(); });
  const filters = el("div", { class: "filters" }, [
    selectEl([{ value: "", label: "all targets" }, ...targets.map((t) => ({ value: t, label: t }))], findingsFilter.target, (v) => { findingsFilter.target = v; rerender(); }),
    selectEl([{ value: "", label: "any contract" }, ...["c0", "c1", "c2"].map((c) => ({ value: c, label: c.toUpperCase() }))], findingsFilter.contract, (v) => { findingsFilter.contract = v; rerender(); }),
    selectEl([{ value: "", label: "any class" }, { value: "candidate", label: "candidate" }, { value: "candidate_needs_repro_check", label: "needs repro check" }], findingsFilter.klass, (v) => { findingsFilter.klass = v; rerender(); }),
    selectEl([{ value: "", label: "any replay" }, ...Object.keys(REPLAY_LABEL).map((k) => ({ value: k, label: REPLAY_LABEL[k] }))], findingsFilter.conclusion, (v) => { findingsFilter.conclusion = v; rerender(); }),
    anyFilter ? clearBtn : null,
  ]);
  const list = el("div", { class: "rank-list" }, shown.slice(0, 300).map((f) => {
    const c = f.case;
    const rp = byCase[c.case_id];
    const marks = ["c0", "c1", "c2"].map((k) => c[k] === true ? el("span", { class: "chip chip-bad chip-sm" }, [k.toUpperCase()]) : null).filter(Boolean);
    marks.push(chip(c.finding, null, c.finding));
    if (f.validated === false) marks.push(chip("as stored", "chip-warn chip-sm"));
    if (rp) { marks.push(conclusionChip(rp.conclusion)); if (rp.judged != null && rp.judged > 0) marks.push(el("span", { class: "chip chip-muted chip-sm" }, [`${rp.same_contracts == null ? EM_DASH : rp.same_contracts}/${rp.judged}`])); }
    const sha = c.tar_sha256 ? el("span", { class: "mono", style: "font-size:11px" }, [c.tar_sha256.slice(0, 12) + "…"]) : null;
    const item = el("div", { class: "rank-item sel", style: "cursor:pointer" }, [
      el("div", { style: "min-width:0" }, [el("div", { class: "mono", style: "overflow:hidden;text-overflow:ellipsis" }, [dash(c.case_id)]), el("div", { class: "meta" }, [`${f.target || EM_DASH}${f.version ? "@" + f.version : ""} `, sha])]),
      el("div", { class: "row-flex wrap" }, marks),
    ]);
    item.addEventListener("click", () => { findingsSelected = { f, replay: rp || null }; rerender(); });
    return item;
  }));
  const left = el("div", {}, [filters, shown.length ? list : empty("no findings match", []), truncNote(fd)]);
  const right = findingsSelected ? findingDetail(findingsSelected.f, findingsSelected.replay) : el("div", { class: "card" }, [empty("select a finding", ["pick a candidate to see its contracts, input hash and replay rounds"])]);
  const label = anyFilter ? `candidates (${shown.length} of ${items.length}) · filtered` : `candidates (${shown.length})`;
  view.appendChild(el("div", { class: "grid-2" }, [cardLabeled(label, left), cardLabeled("detail", right)]));
}
function findingDetail(f, replay) {
  const c = f.case;
  const rows = [
    kv("case", el("div", { class: "mono" }, [dash(c.case_id)])),
    kv("target", `${f.target || EM_DASH}${f.version ? "@" + f.version : ""}`),
    kv("contracts", contractCell(c)),
    kv("class", chip(c.finding)),
    kv("input SHA-256", el("div", { class: "mono", style: "word-break:break-all" }, [dash(c.tar_sha256)])),
    kv("input path", el("div", { class: "mono", style: "word-break:break-all" }, [dash(c.input_path)])),
    kv("termination", dash(c.termination)),
  ];
  const body = el("div", {}, [el("div", { class: "rank-list" }, rows), contractLegend()]);
  if (replay) {
    const denom = replay.judged;
    const rate = denom == null || denom === 0 ? EM_DASH : `${replay.same_contracts == null ? EM_DASH : replay.same_contracts}/${denom}`;
    body.appendChild(el("div", { style: "margin-top:10px" }, [
      el("div", { class: "card-label" }, ["replay"]),
      el("div", { class: "row-flex", style: "margin-bottom:6px" }, [conclusionChip(replay.conclusion), el("span", { class: "muted" }, [`same contracts ${rate} · judged ${dash(replay.judged)} of ${dash(replay.rounds_done)} rounds`])]),
      replayRoundsTable(replay),
    ]));
  } else body.appendChild(el("div", { class: "note" }, ["no replay for this case (contents are never shown)"]));
  return body;
}
function replayRoundsTable(rp) {
  const head = el("tr", {}, ["round", "classification", "termination", "c0", "c1", "c2"].map((h) => el("th", {}, [h])));
  const rows = (rp.rounds || []).map((r) => {
    const judged = r.outcome === "judged" || r.classification;
    return el("tr", { class: judged ? "" : "muted" }, [
      el("td", { class: "num" }, [dash(r.round)]),
      el("td", {}, [r.classification ? chip(r.classification, null, r.classification) : el("span", { class: "chip chip-muted chip-sm", title: "the oracle did not judge this round" }, ["not counted"])]),
      el("td", {}, [dash(r.termination)]),
      ...["c0", "c1", "c2"].map((k) => el("td", {}, [contractMark(r[k])])),
    ]);
  });
  return el("div", {}, [
    el("div", { class: "table-wrap" }, [el("table", { class: "runs" }, [el("thead", {}, [head]), el("tbody", {}, rows)])]),
    contractLegend(),
  ]);
}

/* -- Replay -- */
async function renderReplay(view) {
  view.appendChild(el("h2", { class: "page" }, ["Replay"]));
  let rd;
  try { rd = await api("/api/replays?limit=500"); } catch (err) { view.appendChild(el("div", { class: "card" }, [empty("could not load replays", [String(err)])])); return; }
  const reps = rd.replays || [];
  if (reps.length === 0) {
    view.appendChild(el("div", { class: "card" }, [empty("no replays yet", [["run ", el("code", {}, ["inodefence replay <run-NNNNNN folder>"])]])]));
    const tn = truncNote(rd); if (tn) view.appendChild(tn);
    return;
  }
  const cards = reps.map((r) => {
    const rp = r.replay; const denom = rp.judged;
    const rate = denom == null || denom === 0 ? EM_DASH : `${rp.same_contracts == null ? EM_DASH : rp.same_contracts}/${denom}`;
    const tv = `${r.target || EM_DASH}${r.version ? "@" + r.version : ""}`;
    const head = el("div", { class: "row-flex", style: "justify-content:space-between;flex-wrap:wrap;gap:8px" }, [
      el("div", { class: "row-flex", style: "gap:8px;min-width:0" }, [el("span", { class: "mono" }, [dash(rp.original_case_id)]), el("span", { class: "meta" }, [tv])]),
      el("div", { class: "row-flex" }, [conclusionChip(rp.conclusion), el("span", { class: "muted" }, [`same contracts ${rate} · judged ${dash(rp.judged)} of ${dash(rp.rounds_done)} rounds`])]),
    ]);
    const prov = el("div", { class: "note", style: "margin:6px 0" }, [
      `input SHA-256 `, el("span", { class: "mono", title: rp.original_tar_sha256 || "" }, [rp.original_tar_sha256 ? rp.original_tar_sha256.slice(0, 12) + "…" : EM_DASH]),
      `  ·  folder `, el("span", { class: "mono" }, [dash(rp.path)]),
    ]);
    return el("div", { class: "card", style: "margin-bottom:10px" }, [head, prov, replayRoundsTable(rp)]);
  });
  view.appendChild(el("div", {}, cards));
  const tn = truncNote(rd); if (tn) view.appendChild(tn);
}

/* -- Experiments -- */
async function renderExperiments(view) {
  view.appendChild(el("h2", { class: "page" }, ["Experiments"]));
  if (!state.runs) { try { state.runs = await api("/api/runs"); state.roots = state.runs.roots || []; } catch (err) { view.appendChild(el("div", { class: "card" }, [empty("could not load runs", [String(err)])])); return; } }
  const campaigns = (state.runs.runs || []).filter((r) => r.kind !== "replay");
  view.appendChild(cardLabeled(`campaigns (${campaigns.length})`, renderRunsTable(campaigns)));
  const tn = truncNote(state.runs);
  if (tn) view.appendChild(tn);
}

/* -- Artifacts -- */
let artifactsRun = null;
async function renderArtifacts(view) {
  view.appendChild(el("h2", { class: "page" }, ["Artifacts"]));
  if (!state.runs) { try { state.runs = await api("/api/runs"); } catch (err) { view.appendChild(el("div", { class: "card" }, [empty("could not load runs", [String(err)])])); return; } }
  const runs = (state.runs.runs || []);
  if (runs.length === 0) { view.appendChild(el("div", { class: "card" }, [empty("no runs found", [], `scanned: ${(state.roots || []).join("  ")}`)])); return; }
  const hashId = currentHash().split("/")[1];
  const chosenId = hashId || artifactsRun || runs[0].id;
  const picker = el("div", { class: "selector" }, runs.slice(0, 50).map((r) => {
    const b = el("button", { class: "selbtn" + (r.id === chosenId ? " on" : ""), title: r.run_id || r.id }, [`${r.kind} ${r.target || "?"} ${tailId(r.run_id, 8)}`]);
    b.addEventListener("click", () => { artifactsRun = r.id; location.hash = `#/artifacts/${r.id}`; });
    return b;
  }));
  view.appendChild(picker);
  let ad;
  try { ad = await api(`/api/artifacts/${encodeURIComponent(chosenId)}`); } catch (err) { view.appendChild(el("div", { class: "card" }, [empty("run not found", [String(err)])])); return; }
  const head = el("tr", {}, ["kind", "path", "read_state", "size", "mtime", "sha / case"].map((h) => el("th", { class: [3].includes(["kind", "path", "read_state", "size", "mtime", "sha / case"].indexOf(h)) ? "r" : "" }, [h])));
  const body = el("tbody", {}, (ad.artifacts || []).map((a) => {
    const readCell = a.symlink ? chip("link — not followed", "chip-warn chip-sm", a.read_state || "") : (a.read_state ? chip(a.read_state, a.read_state === "ok" ? "chip-ok chip-sm" : a.read_state === "missing" ? "chip-muted chip-sm" : "chip-warn chip-sm") : el("span", { class: "dash" }, [EM_DASH]));
    const shaCase = a.tar_sha256 ? el("span", { class: "mono muted", title: a.case_id || "" }, [a.tar_sha256.slice(0, 16) + "…"]) : (a.case_id ? el("span", { class: "mono muted" }, [a.case_id]) : el("span", { class: "dash" }, [EM_DASH]));
    return el("tr", {}, [
      el("td", {}, [el("span", { class: "chip chip-sm chip-muted" }, [dash(a.kind)])]),
      el("td", { class: "mono", style: "word-break:break-all;max-width:420px" }, [dash(a.path)]),
      el("td", {}, [readCell]),
      el("td", { class: "r num" }, [fmtBytes(a.size)]),
      el("td", { class: "muted" }, [fmtTime(a.mtime)]),
      el("td", {}, [shaCase]),
    ]);
  }));
  view.appendChild(cardLabeled(`artifacts of ${ad.kind} run`, el("div", { class: "table-wrap" }, [el("table", { class: "runs" }, [el("thead", {}, [head]), body])])));
  view.appendChild(el("div", { class: "note" }, [ad.note]));
}

const ROUTES = {
  overview: { title: "Overview" },
  targets: { title: "Targets" }, experiments: { title: "Experiments" },
  findings: { title: "Findings" }, replay: { title: "Replay" }, artifacts: { title: "Artifacts" },
};
function currentHash() { return (location.hash.replace(/^#\//, "") || "overview"); }
function currentRoute() { return currentHash().split("/")[0].split("?")[0]; }

async function loadOverviewData() {
  try {
    const [runs, findings, replays] = await Promise.all([api("/api/runs"), api("/api/findings"), api("/api/replays")]);
    state.runs = runs; state.findings = findings; state.replays = replays;
    state.roots = runs.roots || [];
    state.loadError = null;
  } catch (err) { state.loadError = String(err); }
}

async function render() {
  const route = currentRoute();
  $("#page-title").textContent = route === "run" ? "Run" : (ROUTES[route] || ROUTES.overview).title;
  for (const a of document.querySelectorAll("#sidenav a")) a.classList.toggle("active", a.dataset.nav === route);
  const view = $("#view");
  if (route === "overview") {
    if (!state.runs) { view.innerHTML = ""; view.appendChild(empty("loading…", [])); }
    await loadOverviewData();
    view.innerHTML = "";
    if (state.loadError) { view.appendChild(empty("could not load runs", [state.loadError])); return; }
    renderOverview(view);
  } else if (route === "run") {
    view.innerHTML = "";
    await renderRunDetail(view, currentHash().split("/")[1] || "");
  } else if (PAGES[route]) {
    view.innerHTML = "";
    await PAGES[route](view);
  } else {
    view.innerHTML = "";
    placeholder(view, (ROUTES[route] || ROUTES.overview).title);
  }
}

const PAGES = { targets: renderTargets, findings: renderFindings, replay: renderReplay, experiments: renderExperiments, artifacts: renderArtifacts };

/* -- engine health chip -- */
async function pollHealth() {
  const chipEl = $("#chip-engine");
  try {
    const h = await api("/api/health");
    const ver = document.querySelector(".nav-foot .ver");
    if (ver) ver.textContent = h.package_version ? `engine v${h.package_version}` : "engine (version unknown)";
    const scan = $("#chip-scan");
    if (scan && Array.isArray(h.roots)) { state.roots = h.roots; scan.textContent = h.roots.length ? `${h.roots.length} folders` : "— folders"; scan.title = h.roots.join("  "); }
    if (h.state === "checking") { chipEl.className = "chip chip-muted"; chipEl.textContent = `${SYMBOL.muted} engine checking…`; return; }
    const t = h.failed ? "bad" : (h.unknown ? "warn" : "ok");
    const word = h.failed ? "FAIL" : (h.unknown ? `WARN · ${h.unknown} unknown` : "OK");
    const age = h.age_seconds == null ? "" : ` · ${Math.round(h.age_seconds)}s`;
    chipEl.className = `chip chip-${t}`;
    chipEl.textContent = `${SYMBOL[t]} engine ${word}${age}`;
    chipEl.title = `${h.summary || ""}${h.checked_at ? ` — checked ${Math.round(h.age_seconds)}s ago` : ""}`;
  } catch (err) { chipEl.className = "chip chip-bad"; chipEl.textContent = `${SYMBOL.bad} engine`; chipEl.title = String(err); }
}
async function pollTargets() {
  try { const t = await api("/api/targets"); state.targetsCount = t.state === "ok" ? Object.keys(t.targets || {}).length : null; }
  catch { state.targetsCount = null; }
}

/* -- SSE live stream -- */
function connectEvents() {
  const chipEl = $("#chip-conn");
  let es;
  const open = () => {
    es = new EventSource("/api/events");
    es.onopen = () => { chipEl.className = "chip chip-ok"; chipEl.textContent = `${SYMBOL.ok} live`; };
    es.onmessage = (ev) => {
      chipEl.className = "chip chip-ok"; chipEl.textContent = `${SYMBOL.ok} live`;
      try {
        const e = JSON.parse(ev.data);
        if (e.kind === "progress" && e.progress_current != null) {
          const key = `${e.run_kind}:${e.run_root}:${e.run_id || ""}`;
          const arr = state.series[key] || (state.series[key] = []);
          arr.push({ t: Date.now() / 1000, runs: e.progress_current, budget: e.progress_total });
          if (arr.length > 500) arr.shift();
        }
      } catch { /* ignore a malformed line */ }
      if (currentRoute() === "overview") scheduleRefresh();
    };
    es.onerror = () => { chipEl.className = "chip chip-warn"; chipEl.textContent = `${SYMBOL.warn} reconnecting…`; es.close(); setTimeout(open, 3000); };
  };
  open();
}

let refreshTimer = null;
function scheduleRefresh() { if (refreshTimer) return; refreshTimer = setTimeout(() => { refreshTimer = null; if (currentRoute() === "overview") render(); }, 800); }

window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", async () => {
  // nav icons + brand
  const brand = $("#brand-ic"); if (brand) brand.appendChild(svgIcon("brand"));
  for (const a of document.querySelectorAll("#sidenav a")) a.prepend(svgIcon(a.dataset.nav));
  await pollTargets();
  await render();
  pollHealth();  // sets the scan-location chip and nav version on every page (roots come from /api/health)
  setInterval(pollHealth, 15000);
  connectEvents();
  $("#search").addEventListener("input", (e) => {
    state.filter = e.target.value;
    const r = currentRoute();
    if (r === "overview" && state.runs) { const v = $("#view"); v.innerHTML = ""; renderOverview(v); }
    else if (r === "findings" || r === "experiments") render();
  });
});
