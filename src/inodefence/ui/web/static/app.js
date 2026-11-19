"use strict";
/* InodeFence dashboard. Reads the GET /api endpoints and draws them. No external code.

   Display rules it must keep (research rules):
   - a missing value is "—"/"?", never 0; no bar/graph is drawn for an absent value (empty state);
   - termination, oracle violation (a candidate), unjudged, harness error and replay stay separate;
   - a flagged violation is only ever labelled a candidate (or one that needs a reproduction check),
     never escalated to a stronger word; a replay reports a conclusion with n/judged (denominator =
     judged rounds, never rounds_done; no ratio when judged is 0);
   - a result the strict reader refused is shown "as stored (not validated)";
   - file contents and entry names are never shown (paths and hashes only). */

const EM_DASH = "—";
const TONE = { // mirrors inodefence.ui.theme.STATUS_TONE (words not listed are muted)
  OK: "ok", PASS: "ok", REPRODUCED: "ok", COMPLETE: "ok", YES: "ok", SAME: "ok",
  WARN: "warn", UNKNOWN: "warn", UNJUDGED: "warn", INDETERMINATE: "warn", STALLED: "warn",
  CANDIDATE: "warn", "AS STORED": "warn", "CANDIDATE NEEDS REPRO CHECK": "warn",
  FAIL: "bad", ERROR: "bad", "RUN ERROR": "bad", NOT_REPRODUCED: "bad",
};
const SYMBOL = { ok: "✓", warn: "!", bad: "✗", info: "i", muted: "·", accent: "›" };

function tone(word) {
  if (word === null || word === undefined) return "muted";
  return TONE[String(word).toUpperCase().replace(/_/g, " ")] || "muted";
}

/* -- small helpers -- */
const $ = (sel, root) => (root || document).querySelector(sel);
function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v; // only ever used with strings we build, never API text
    else node.setAttribute(k, v);
  }
  for (const child of children || []) if (child) node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  return node;
}
function dash(v) { return (v === null || v === undefined) ? EM_DASH : String(v); }
function num(v) { return (v === null || v === undefined) ? EM_DASH : Number(v).toLocaleString(); }
function chip(word, extra) {
  const t = tone(word);
  const label = word === null || word === undefined ? EM_DASH : String(word).toUpperCase().replace(/_/g, " ");
  return el("span", { class: `chip chip-${t}`, title: extra || "" }, [`${SYMBOL[t]} ${label}`]);
}

async function api(path) {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

function empty(title, lines) {
  return el("div", { class: "empty" }, [
    el("div", { class: "title" }, [title]),
    ...(lines || []).map((l) => el("div", {}, [l])),
  ]);
}

function cardLabeled(label, body) {
  return el("div", {}, [el("div", { class: "card-label" }, [label]), el("div", { class: "card" }, [body])]);
}

/* horizontal bars from [{name, value, color}]; empty state when nothing has a value */
function barChart(rows, colorVar) {
  const withVal = rows.filter((r) => r.value !== null && r.value !== undefined);
  if (withVal.length === 0) return empty("no data yet", ["no runs with this value in the scanned set"]);
  const max = Math.max(1, ...withVal.map((r) => r.value));
  const box = el("div", { class: "bars" }, []);
  for (const r of rows) {
    const pct = (r.value === null || r.value === undefined) ? 0 : Math.round((r.value / max) * 100);
    const fill = el("div", { class: "bar-fill" }, []);
    fill.style.width = `${pct}%`;
    fill.style.background = `var(${r.color || colorVar || "--if-series-1"})`;
    box.appendChild(el("div", { class: "bar-row" }, [
      el("div", { class: "name", title: r.name }, [r.name]),
      el("div", { class: "bar-track" }, [fill]),
      el("div", { class: "val" }, [num(r.value)]),
    ]));
  }
  return box;
}

/* -- state -- */
const state = { runs: null, findings: null, replays: null, filter: "" };

/* -- Overview -- */
function targetOf(run) {
  const t = run.target || (run.status && run.status.target) || null;
  const v = run.version || null;
  return t ? (v ? `${t}@${v}` : t) : EM_DASH;
}

function renderOverview(view) {
  const runsData = state.runs, findingsData = state.findings, replaysData = state.replays;
  const runs = (runsData && runsData.runs) || [];
  const scanned = runs.filter((r) => r.status);
  const truncatedNote = runsData && runsData.truncated
    ? `most recent ${runsData.runs_scanned} of ${runsData.runs_total} runs`
    : (runsData ? `${runsData.runs_total} runs` : EM_DASH);

  // big numbers (missing stays —, never 0)
  const targetsCount = state.targetsCount; // set by engine/targets fetch; may be null
  const active = scanned.filter((r) => r.status.state === "running").length;
  const finished = scanned.filter((r) => r.status.verdict !== null && r.status.verdict !== undefined).length;
  const candidates = scanned.reduce((a, r) => a + (r.status.candidates || 0), 0);
  const needsRepro = scanned.reduce((a, r) => a + (r.status.candidates_needs_repro || 0), 0);
  const replays = (replaysData && replaysData.replays) || [];
  const judgedReplays = replays.filter((r) => r.replay.judged !== null && r.replay.judged > 0);
  const reproduced = replays.filter((r) => r.replay.conclusion === "reproduced_violation").length;

  const statCard = (label, big, sub) => el("div", { class: "stat card" }, [
    el("div", { class: "card-label" }, [label]),
    el("div", { class: "big" }, [big]),
    el("div", { class: "sub", html: sub }),
  ]);

  const statRow = el("div", { class: "stat-row" }, [
    statCard("targets", targetsCount === null || targetsCount === undefined ? EM_DASH : String(targetsCount),
      "registered drivers"),
    statCard("runs", runsData ? String(runsData.runs_total) : EM_DASH,
      `<strong>${active}</strong> active · <strong>${finished}</strong> finished`),
    statCard("violation candidates", String(candidates),
      `<strong>${needsRepro}</strong> need a reproduction check`),
    statCard("replays", judgedReplays.length === 0 ? EM_DASH : `${reproduced}/${judgedReplays.length}`,
      judgedReplays.length === 0 ? "none judged yet" : "reproduced / judged"),
  ]);

  // per-target runs & candidates
  const byTarget = {};
  for (const r of scanned) {
    const key = r.target || "(unknown)";
    byTarget[key] = byTarget[key] || { runs: 0, candidates: 0 };
    byTarget[key].runs += 1;
    byTarget[key].candidates += (r.status.candidates || 0) + (r.status.candidates_needs_repro || 0);
  }
  const targetRows = Object.entries(byTarget).map(([name, v]) => ({ name, value: v.runs, color: "--if-series-1" }));
  const candRows = Object.entries(byTarget).map(([name, v]) => ({ name, value: v.candidates, color: "--if-warn" }));

  // verdict distribution (PASS/FAIL/ERROR) — kept separate from termination
  const verdicts = { PASS: 0, FAIL: 0, ERROR: 0 };
  for (const r of scanned) { const v = r.status.verdict; if (v && verdicts[v] !== undefined) verdicts[v] += 1; }
  const verdictRows = [
    { name: "PASS", value: verdicts.PASS, color: "--if-ok" },
    { name: "FAIL", value: verdicts.FAIL, color: "--if-bad" },
    { name: "ERROR", value: verdicts.ERROR, color: "--if-warn" },
  ];

  // termination distribution (separate axis)
  const terms = {};
  for (const r of scanned) for (const [k, n] of Object.entries(r.status.terminations || {})) {
    if (n === null || n === undefined) continue; terms[k] = (terms[k] || 0) + n;
  }
  const termRows = Object.entries(terms).map(([name, value], i) => ({ name, value, color: `--if-series-${(i % 6) + 1}` }));

  // replay by conclusion
  const concl = {};
  for (const r of replays) { const c = r.replay.conclusion || "(none)"; concl[c] = (concl[c] || 0) + 1; }
  const conclRows = Object.entries(concl).map(([name, value], i) => ({ name, value, color: `--if-series-${(i % 6) + 1}` }));

  const grid = el("div", { class: "grid-3" }, [
    cardLabeled("runs by target", barChart(targetRows)),
    cardLabeled("candidates by target", barChart(candRows)),
    cardLabeled("campaign verdicts", scanned.length ? barChart(verdictRows) : empty("no runs found", [truncatedNote])),
    cardLabeled("termination of extractor", termRows.length ? barChart(termRows) : empty("no live data", ["only node-tar writes termination counts while running"])),
    cardLabeled("replays by conclusion", replays.length ? barChart(conclRows) : empty("no replays yet", ["run `inodefence replay <case-folder>`"])),
    cardLabeled("recent candidates", renderRecentCandidates(findingsData)),
  ]);

  view.appendChild(statRow);
  if (runsData && runsData.truncated) view.appendChild(el("div", { class: "note" }, [`showing ${truncatedNote}; raise with ?limit=`]));
  view.appendChild(grid);
  view.appendChild(cardLabeled("runs", renderRunsTable(runs)));
}

function renderRecentCandidates(findingsData) {
  if (!findingsData) return empty("loading…", []);
  const items = findingsData.findings.filter((f) => f.case.finding);
  if (items.length === 0) return empty("no candidates", ["no oracle-flagged cases in the scanned runs"]);
  const list = el("div", { class: "rank-list" }, []);
  for (const f of items.slice(0, 12)) {
    const c = f.case;
    const contracts = ["c0", "c1", "c2"].map((k) => c[k] === true ? el("span", { class: "chip chip-bad" }, [k.toUpperCase()]) : null).filter(Boolean);
    list.appendChild(el("div", { class: "rank-item" }, [
      el("div", {}, [
        el("div", { class: "mono" }, [dash(c.case_id)]),
        el("div", { class: "meta" }, [`${f.target || EM_DASH}${f.version ? "@" + f.version : ""}`]),
      ]),
      el("div", { class: "row-flex" }, [...contracts, chip(c.finding)]),
    ]));
  }
  return list;
}

function renderRunsTable(runs) {
  const f = state.filter.trim().toLowerCase();
  const rows = runs.filter((r) => !f || JSON.stringify([r.target, r.version, r.kind, r.run_id]).toLowerCase().includes(f));
  if (rows.length === 0) return empty(runs.length ? "no runs match the filter" : "no runs found",
    runs.length ? [] : ["scanned the default output folders; start one with `inodefence explore <target>`"]);
  const head = el("tr", {}, ["kind", "target", "version", "budget", "progress", "state", "verdict", "updated"].map((h) => el("th", {}, [h])));
  const body = el("tbody", {}, []);
  for (const r of rows) {
    const s = r.status;
    const runsN = s ? s.runs : null, budget = s ? s.budget : null;
    const pct = (s && runsN !== null && budget) ? Math.min(100, Math.round((runsN / budget) * 100)) : null;
    const prog = pct === null ? el("span", { class: "dash" }, [EM_DASH]) : (() => {
      const fill = el("div", { class: "prog-fill" }, []); fill.style.width = `${pct}%`;
      return el("div", { class: "row-flex" }, [el("div", { class: "prog" }, [fill]), el("span", { class: "muted" }, [`${num(runsN)}/${num(budget)}`])]);
    })();
    const verdictCell = s && s.verdict ? chip(s.verdict, s.validated === false ? "as stored (not validated)" : "")
      : (s && s.read_state === "unvalidated" ? chip("AS STORED") : el("span", { class: "dash" }, [EM_DASH]));
    body.appendChild(el("tr", {}, [
      el("td", {}, [chip(r.kind)]),
      el("td", {}, [dash(r.target)]),
      el("td", { class: "mono" }, [dash(r.version)]),
      el("td", {}, [s ? num(budget) : el("span", { class: "dash" }, [EM_DASH])]),
      el("td", {}, [prog]),
      el("td", {}, [s && s.state ? chip(s.state) : el("span", { class: "dash" }, [EM_DASH])]),
      el("td", {}, [verdictCell]),
      el("td", { class: "muted" }, [s && s.progress_age_seconds !== null && s.progress_age_seconds !== undefined ? `${Math.round(s.progress_age_seconds)}s ago` : EM_DASH]),
    ]));
  }
  return el("div", { class: "table-wrap" }, [el("table", { class: "runs" }, [el("thead", {}, [head]), body])]);
}

/* -- other pages (full views land in later pushes) -- */
function placeholder(view, title) {
  view.appendChild(el("h2", { class: "page" }, [title]));
  view.appendChild(el("div", { class: "card" }, [empty("coming in a later push", ["this view is being built; the Overview is live"])]));
}

/* -- routing -- */
const ROUTES = {
  overview: { title: "Overview", render: renderOverview },
  targets: { title: "Targets", render: (v) => placeholder(v, "Targets") },
  experiments: { title: "Experiments", render: (v) => placeholder(v, "Experiments") },
  findings: { title: "Findings", render: (v) => placeholder(v, "Findings") },
  replay: { title: "Replay", render: (v) => placeholder(v, "Replay") },
  artifacts: { title: "Artifacts", render: (v) => placeholder(v, "Artifacts") },
};

function currentRoute() { return (location.hash.replace(/^#\//, "") || "overview").split("?")[0]; }

async function loadOverviewData() {
  try {
    const [runs, findings, replays] = await Promise.all([api("/api/runs"), api("/api/findings"), api("/api/replays")]);
    state.runs = runs; state.findings = findings; state.replays = replays;
  } catch (err) {
    state.loadError = String(err);
  }
}

async function render() {
  const route = ROUTES[currentRoute()] || ROUTES.overview;
  $("#page-title").textContent = route.title;
  for (const a of document.querySelectorAll("#sidenav a")) a.classList.toggle("active", a.dataset.nav === currentRoute());
  const view = $("#view");
  if (route === ROUTES.overview) {
    view.innerHTML = "";
    if (!state.runs) view.appendChild(empty("loading…", []));
    await loadOverviewData();
    view.innerHTML = "";
    if (state.loadError) { view.appendChild(empty("could not load runs", [state.loadError])); return; }
    renderOverview(view);
  } else {
    view.innerHTML = "";
    route.render(view);
  }
}

/* -- engine health chip (polls the TTL-cached endpoint) -- */
async function pollHealth() {
  try {
    const h = await api("/api/health");
    const el2 = $("#chip-engine");
    if (h.state === "checking") { el2.className = "chip chip-muted"; el2.textContent = `${SYMBOL.muted} checking…`; }
    else {
      const t = h.failed ? "bad" : (h.unknown ? "warn" : "ok");
      const age = h.age_seconds === null || h.age_seconds === undefined ? "" : ` (${Math.round(h.age_seconds)}s ago)`;
      el2.className = `chip chip-${t}`;
      el2.textContent = `${SYMBOL[t]} engine${age}`;
      el2.title = (h.summary || "") + age;
    }
  } catch (err) {
    const el2 = $("#chip-engine"); el2.className = "chip chip-bad"; el2.textContent = `${SYMBOL.bad} engine`; el2.title = String(err);
  }
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
      if (currentRoute() === "overview") { state.runs = null; scheduleRefresh(); }
    };
    es.onerror = () => {
      chipEl.className = "chip chip-warn"; chipEl.textContent = `${SYMBOL.warn} reconnecting…`;
      es.close(); setTimeout(open, 3000);
    };
  };
  open();
}

let refreshTimer = null;
function scheduleRefresh() {
  if (refreshTimer) return;
  refreshTimer = setTimeout(() => { refreshTimer = null; if (currentRoute() === "overview") render(); }, 800);
}

window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", async () => {
  await pollTargets();
  render();
  pollHealth();
  setInterval(pollHealth, 15000);
  connectEvents();
  $("#search").addEventListener("input", (e) => {
    state.filter = e.target.value;
    if (currentRoute() === "overview" && state.runs) { const v = $("#view"); v.innerHTML = ""; renderOverview(v); }
  });
});
