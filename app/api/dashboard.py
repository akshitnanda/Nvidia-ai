from __future__ import annotations

import html
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from app.memory.runs import RunStore
from app.models.settings import Settings


def create_app(root: Path | None = None, settings: Settings | None = None) -> FastAPI:
    root_path = (root or Path.cwd()).resolve()
    settings = settings or Settings()
    data_dir = (root_path / settings.swarm_data_dir).resolve()
    store = RunStore(data_dir)

    app = FastAPI(title="NVIDIA Local Swarm Dashboard", version="0.1.2")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        root_label = html.escape(str(store.runs_dir))
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>NVIDIA Local Swarm Dashboard</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f5f7fb;
        --panel: #ffffff;
        --text: #172033;
        --muted: #5b667d;
        --accent: #76b900;
        --border: #dbe3f0;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "Segoe UI", Tahoma, sans-serif;
        background:
          radial-gradient(circle at top right, rgba(118, 185, 0, 0.14), transparent 30%),
          linear-gradient(180deg, #f9fbff 0%, var(--bg) 100%);
        color: var(--text);
      }}
      main {{
        max-width: 1200px;
        margin: 0 auto;
        padding: 48px 20px 64px;
      }}
      .hero, .panel {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 18px;
        box-shadow: 0 20px 50px rgba(23, 32, 51, 0.08);
      }}
      .hero {{
        padding: 28px;
        margin-bottom: 20px;
      }}
      .eyebrow {{
        display: inline-block;
        font-size: 12px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--accent);
        font-weight: 700;
      }}
      h1 {{
        margin: 12px 0 8px;
        font-size: clamp(32px, 5vw, 48px);
      }}
      p {{
        color: var(--muted);
        line-height: 1.6;
      }}
      code {{
        font-family: Consolas, "Courier New", monospace;
        background: #eef3e2;
        padding: 2px 6px;
        border-radius: 6px;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 20px;
      }}
      .panel {{
        padding: 22px;
      }}
      ul {{
        padding-left: 18px;
      }}
      a {{
        color: #1a4fb6;
        text-decoration: none;
      }}
      a:hover {{
        text-decoration: underline;
      }}
      #runs li {{
        margin-bottom: 8px;
      }}
      .toolbar {{ display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 18px 0; }}
      button, input, select {{ font: inherit; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; background: white; color: var(--text); }}
      button {{ cursor: pointer; }}
      button:hover, button[aria-current="true"] {{ border-color: #548400; background: #f0f7e5; }}
      button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible {{ outline: 3px solid #548400; outline-offset: 3px; }}
      #runs {{ list-style: none; padding: 0; max-height: 620px; overflow: auto; }}
      #runs button {{ width: 100%; text-align: left; overflow-wrap: anywhere; }}
      .run-title {{ display: block; font-weight: 600; margin-bottom: 6px; }}
      .meta {{ display: block; font-size: 12px; color: var(--muted); }}
      .workspace {{ display: grid; grid-template-columns: minmax(240px, 1fr) minmax(0, 2fr); gap: 20px; }}
      .panel {{ min-width: 0; }}
      pre {{ white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; line-height: 1.6; background: #f5f7fb; padding: 16px; border-radius: 8px; max-height: 600px; overflow: auto; }}
      #detail-status {{ overflow-wrap: anywhere; }}
      #artifact-select {{ max-width: 100%; }}
      .metrics {{ display: flex; flex-wrap: wrap; gap: 24px; border-top: 1px solid var(--border); margin-top: 20px; padding-top: 18px; }}
      .metrics strong {{ display: block; font-size: 24px; }}
      .metrics span {{ font-size: 12px; color: var(--muted); }}
      code {{ overflow-wrap: anywhere; }}
      @media (max-width: 720px) {{ .workspace {{ grid-template-columns: 1fr; }} main {{ padding: 20px 14px; }} .hero {{ padding: 22px; }} h1 {{ font-size: 32px; }} #runs {{ max-height: 320px; }} }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <span class="eyebrow">Workflow observatory</span>
        <h1>NVIDIA Local Swarm</h1>
        <p>Inspect plans, proposed changes, agent activity, and validation results. Run <code>swarm demo</code> for a no-key walkthrough.</p>
        <p>Artifacts: <code>{root_label}</code></p>
        <div class="metrics" aria-live="polite"><div><strong id="run-count">0</strong><span>Recent runs loaded</span></div><div><strong id="failed-count">0</strong><span>Failed runs</span></div><div><strong id="token-count">0</strong><span>Tokens · demo usage is estimated</span></div></div>
      </section>
      <div class="toolbar"><label for="search">Find a run</label><input id="search" type="search" placeholder="Task, mode, or run ID"><button id="refresh" type="button">Refresh runs</button><a href="/docs">API docs</a><span id="refresh-status" role="status"></span></div>
      <section class="workspace">
        <article class="panel">
          <h2>Recent runs</h2>
          <ul id="runs"><li>Loading...</li></ul>
        </article>
        <article class="panel">
          <h2 id="detail-title">Run details</h2>
          <p id="detail-status" role="status">Select a run to explore its artifacts and execution trace.</p>
          <div id="artifact-controls" hidden><label for="artifact-select">Artifact</label> <select id="artifact-select"></select></div>
          <pre id="artifact-content" tabindex="0">Plans, diffs, agent events, token usage, and validation output appear here.</pre>
        </article>
      </section>
    </main>
    <script>
      const el = (id) => document.getElementById(id);
      let runs = [], selected = null, artifacts = {{}}, requestNumber = 0;
      function renderRuns() {{
        const query = el("search").value.toLowerCase();
        const visible = runs.filter(run => [run.task, run.mode, run.run_id, run.status].join(" ").toLowerCase().includes(query));
        el("runs").replaceChildren();
        if (!visible.length) {{
          const item = document.createElement("li");
          item.textContent = runs.length ? "No matching runs." : "No runs yet. Start with swarm demo.";
          el("runs").append(item);
        }}
        visible.forEach(run => {{
          const item = document.createElement("li"), button = document.createElement("button");
          button.type = "button";
          button.setAttribute("aria-current", String(run.run_id === selected));
          const title = document.createElement("span"), meta = document.createElement("span");
          title.className = "run-title"; meta.className = "meta";
          title.textContent = run.task || run.run_id;
          meta.textContent = `${{run.mode}} · ${{run.status}} · ${{run.provider || "legacy"}}`;
          button.append(title, meta); button.addEventListener("click", () => selectRun(run.run_id));
          item.append(button); el("runs").append(item);
        }});
      }}
      function showArtifact() {{
        const value = artifacts[el("artifact-select").value];
        el("artifact-content").textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2) || "No readable artifacts.";
      }}
      async function selectRun(id) {{
        const request = ++requestNumber;
        selected = id; renderRuns(); el("detail-title").textContent = id;
        el("detail-status").textContent = "Loading run…";
        el("artifact-controls").hidden = true; el("artifact-content").textContent = "";
        try {{
          const response = await fetch(`/runs/${{encodeURIComponent(id)}}`);
          if (!response.ok) throw new Error("Run is unavailable. Refresh the list and try again.");
          const data = await response.json();
          if (request !== requestNumber) return;
          const summary = data.summary;
          const errors = Object.keys(data.artifact_errors || {{}}).length;
          el("detail-status").textContent = `${{summary.status}} · ${{summary.provider || "legacy run"}} · Validation: ${{summary.validation_status || "not recorded"}} · ${{summary.model_calls}} model calls · ${{summary.total_tokens.toLocaleString()}} tokens${{errors ? ` · ${{errors}} unreadable artifact(s)` : ""}}`;
          artifacts = data.artifacts;
          el("artifact-select").replaceChildren();
          Object.keys(artifacts).forEach(name => {{ const option = document.createElement("option"); option.value = name; option.textContent = name; el("artifact-select").append(option); }});
          if ("result.json" in artifacts) el("artifact-select").value = "result.json";
          el("artifact-controls").hidden = !Object.keys(artifacts).length; showArtifact();
        }} catch (error) {{ if (request === requestNumber) el("detail-status").textContent = error.message; }}
      }}
      async function loadRuns() {{
        el("refresh").disabled = true; el("refresh-status").textContent = "Refreshing…";
        try {{
          const response = await fetch("/runs?details=true");
          if (!response.ok) throw new Error("Unable to load runs.");
          runs = await response.json(); renderRuns();
          el("run-count").textContent = runs.length;
          el("failed-count").textContent = runs.filter(run => run.status === "failed").length;
          el("token-count").textContent = runs.reduce((sum, run) => sum + run.total_tokens, 0).toLocaleString();
          el("refresh-status").textContent = "Updated " + new Date().toLocaleTimeString();
          if (selected && runs.some(run => run.run_id === selected)) await selectRun(selected);
        }} catch (error) {{ el("refresh-status").textContent = error.message; }}
        finally {{ el("refresh").disabled = false; }}
      }}
      el("search").addEventListener("input", renderRuns);
      el("refresh").addEventListener("click", loadRuns);
      el("artifact-select").addEventListener("change", showArtifact);
      loadRuns();
    </script>
  </body>
</html>
"""

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/runs")
    def list_runs(details: bool = False, limit: int = Query(50, ge=1, le=100),
                  offset: int = Query(0, ge=0)) -> list[dict[str, object]]:
        results = store.list(limit=limit, offset=offset)
        return results if details else [{"run_id": row["run_id"]} for row in results]

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        try:
            return store.get(run_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Run not found") from None

    return app
