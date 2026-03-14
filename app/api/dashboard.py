from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException


def create_app(root: Path | None = None) -> FastAPI:
    root_path = (root or Path.cwd()).resolve()
    runs_dir = root_path / "data" / "runs"

    app = FastAPI(title="NVIDIA Local Swarm Dashboard", version="0.1.0")

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

