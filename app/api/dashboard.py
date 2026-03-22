from __future__ import annotations

import html
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse


def create_app(root: Path | None = None) -> FastAPI:
    root_path = (root or Path.cwd()).resolve()
    runs_dir = root_path / "data" / "runs"

    app = FastAPI(title="NVIDIA Local Swarm Dashboard", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        root_label = html.escape(str(root_path))
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
        max-width: 900px;
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
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <span class="eyebrow">Local Demo</span>
        <h1>NVIDIA Local Swarm</h1>
        <p>Runs are stored under <code>{root_label}\\data\\runs</code>. Start with <code>swarm demo</code> for a no-key walkthrough, or switch back to <code>NVIDIA_PROVIDER_MODE=serverless</code> for live NVIDIA calls.</p>
      </section>
      <section class="grid">
        <article class="panel">
          <h2>Quick Start</h2>
          <p><code>powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1</code></p>
          <p><code>swarm demo --mode plan</code></p>
          <p><a href="/docs">Open API docs</a></p>
        </article>
        <article class="panel">
          <h2>Recent Runs</h2>
          <ul id="runs"><li>Loading...</li></ul>
        </article>
      </section>
    </main>
    <script>
      async function loadRuns() {{
        const target = document.getElementById("runs");
        const response = await fetch("/runs");
        const runs = await response.json();
        if (!runs.length) {{
          target.innerHTML = "<li>No runs yet. Trigger a CLI command first.</li>";
          return;
        }}
        target.innerHTML = runs
          .map((run) => `<li><a href="/runs/${{run.run_id}}">${{run.run_id}}</a></li>`)
          .join("");
      }}
      loadRuns().catch(() => {{
        document.getElementById("runs").innerHTML = "<li>Unable to load runs.</li>";
      }});
    </script>
  </body>
</html>
"""

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/runs")
    def list_runs() -> list[dict[str, str]]:
        if not runs_dir.exists():
            return []
        results = []
        for run_dir in sorted(runs_dir.iterdir(), reverse=True):
            if run_dir.is_dir():
                results.append({"run_id": run_dir.name})
        return results[:50]

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        run_dir = runs_dir / run_id
        if not run_dir.exists():
            raise HTTPException(status_code=404, detail="Run not found")
        payload: dict[str, object] = {"run_id": run_id, "artifacts": {}}
        for artifact in run_dir.iterdir():
            if artifact.suffix == ".json":
                payload["artifacts"][artifact.name] = json.loads(artifact.read_text(encoding="utf-8"))
            else:
                payload["artifacts"][artifact.name] = artifact.read_text(encoding="utf-8")
        return payload

    return app
