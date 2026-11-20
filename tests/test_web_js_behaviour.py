"""The dashboard's own rendering of runs, run details and findings, run in Node against the real
``app.js`` and real ``/api`` answers for synthetic folders (QA's four items, ORCH's labels).

Nothing is mocked in the page code: a minimal DOM stands in for the browser, ``fetch`` returns the
API's answers from FastAPI's test client, and the text the page would show is checked. Requires
the ``web`` extra and ``node``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests import app_synthetic as syn  # noqa: E402

from inodefence.app import runs as runs_app  # noqa: E402
from inodefence.ui import web  # noqa: E402

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
APP_JS = Path(web.__file__).parent / "static" / "app.js"

#: A browser-less stand-in: enough DOM for el()/empty()/cardLabeled() and the page's top level.
HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const [appPath, dataPath] = process.argv.slice(2);
const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));
class Node_ {
  constructor(tag, text) {
    this.tag = tag; this.children = []; this.attrs = {}; this._text = text;
    this.style = {}; this.className = "";
  }
  appendChild(c) { this.children.push(c); return c; }
  prepend(c) { this.children.unshift(c); }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener() {}
  set textContent(v) { this._text = v; this.children = []; }
  get textContent() {
    return (this._text || "") + this.children.map((c) => c.textContent).join(" ");
  }
  set innerHTML(v) { this.children = []; this._text = ""; }
  get firstChild() { return this.children[0] || new Node_("svg"); }
}
const document = {
  createElement: (t) => new Node_(t), createTextNode: (t) => new Node_("#text", t),
  querySelector: () => null, querySelectorAll: () => [],
};
const window = { addEventListener() {} };
const fetch = async (path) => {
  const key = Object.keys(data.api).find((k) => path.startsWith(k));
  return { ok: true, json: async () => data.api[key] };
};
const ctx = { document, window, fetch, location: { hash: "" }, console, setTimeout, setInterval,
              EventSource: function () {} };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(appPath, "utf8") + `
;globalThis.__api = { renderRunsTable, runDetailCards, renderFindings,
  candCount: typeof candCount === "function" ? candCount : () => "missing" };`, ctx);
(async () => {
  const api = ctx.__api, out = {};
  out.table = api.renderRunsTable(data.runs).textContent;
  out.launcherCand = api.candCount(data.launcherStatus);
  const text = (cards) => cards.map((c) => c.textContent).join(" | ");
  out.launcherDetail = text(api.runDetailCards(data.launcherDetail));
  out.verifyDetail = text(api.runDetailCards(data.verifyDetail));
  const view = new Node_("div");
  await api.renderFindings(view);
  out.findings = view.textContent;
  process.stdout.write(JSON.stringify(out));
})();
"""


def _payloads(tmp_path: Path) -> dict:
    root = tmp_path / "out"
    launch = root / "launch-out"
    log = launch / runs_app.RUNTIME_DIR / "explore-launcher-20261120T021743Z-4242.log"
    log.parent.mkdir(parents=True)
    log.write_text("==> [python-tarfile-effect-campaign]\n", encoding="utf-8")
    cases = [syn.case("toplevel_hardlink", True, termination=None),
             syn.case("dir_symlink_write", False, termination=None)]  # fmt: skip
    syn.write_result(root / "verify" / "node-tar-7.5.2",
                     syn.result(mode=syn.ResultMode.FIXTURE_REGRESSION, cases=cases))  # fmt: skip
    client = TestClient(web.create_app(roots=[root]))
    runs = client.get("/api/runs").json()["runs"]
    launcher = next(r for r in runs if r["run_id"] is None)
    verify = next(r for r in runs if r["kind"] == "verify")
    return {
        "runs": runs,
        "launcherStatus": launcher["status"],
        "launcherDetail": client.get(f"/api/runs/{launcher['id']}").json(),
        "verifyDetail": client.get(f"/api/runs/{verify['id']}").json(),
        "api": {
            "/api/findings": client.get("/api/findings?limit=500").json(),
            "/api/replays": client.get("/api/replays?limit=500").json(),
        },
    }


def _render(tmp_path: Path) -> dict:
    data = tmp_path / "data.json"
    data.write_text(json.dumps(_payloads(tmp_path)), encoding="utf-8")
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    done = subprocess.run(
        [NODE or "node", str(harness), str(APP_JS), str(data)],
        capture_output=True, text=True, timeout=60, check=True, env={**os.environ},
    )  # fmt: skip
    return json.loads(done.stdout)


def test_the_pages_say_what_the_files_say(tmp_path: Path) -> None:
    out = _render(tmp_path)
    # (1) a launcher-only run's candidates are unknown, in the table and in the detail
    assert out["launcherCand"] is None
    assert "EST. LIVE" in out["table"]  # (3) the TUI's short label, upper-cased as a chip
    # (2) the detail states the same estimate, with where it comes from
    assert "launching/running (from launcher log, last write" in out["launcherDetail"]
    assert "candidates —" in out["launcherDetail"].replace("  ", " ")
    # (4) a verify cell's detail lists its violated known fixtures apart from candidates
    assert "fixtures violated (verify) 1" in out["verifyDetail"].replace("  ", " ")
    assert "toplevel_hardlink" in out["verifyDetail"] and "FIXTURE" in out["verifyDetail"]
    assert "candidates 0" in out["verifyDetail"].replace("  ", " ")
    # (3) no candidates and no filter: "no candidates yet", never "no findings match"
    assert "no candidates yet" in out["findings"] and "no findings match" not in out["findings"]
    assert "known fixtures violated (verify)" in out["findings"]
