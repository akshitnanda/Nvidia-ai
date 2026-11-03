from __future__ import annotations

import html
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.memory.runs import RunStore
from app.models.settings import Settings


def create_app(root: Path | None = None, settings: Settings | None = None) -> FastAPI:
    root_path = (root or Path.cwd()).resolve()
    settings = settings or Settings()
    data_dir = (root_path / settings.swarm_data_dir).resolve()
    store = RunStore(data_dir)

    static_dir = Path(__file__).parent / "static"
    app = FastAPI(title="NVIDIA Local Swarm Dashboard", version="0.1.2")

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        root_label = html.escape(str(store.runs_dir))
        return (static_dir / "index.html").read_text(encoding="utf-8").replace("__RUNS_PATH__", root_label)

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
