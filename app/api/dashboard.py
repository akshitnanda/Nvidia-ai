from __future__ import annotations

import html
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from app.memory.runs import RunStore
from app.models.settings import Settings
from app.models.jobs import JobRequest, ApprovalDecision
from app.orchestrator.jobs import JobManager


def create_app(root: Path | None = None, settings: Settings | None = None) -> FastAPI:
    root_path = (root or Path.cwd()).resolve()
    settings = settings or Settings()
    data_dir = (root_path / settings.swarm_data_dir).resolve()
    store = RunStore(data_dir)

    static_dir = Path(__file__).parent / "static"
    manager = None
    session_token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal manager
        manager = JobManager(root_path, settings)
        manager.start()
        try:
            yield
        finally:
            manager.close()

    app = FastAPI(title="NVIDIA Local Swarm Mission Control", version="0.1.2", lifespan=lifespan,
                  docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def local_access(request: Request, call_next):
        # Host allowlisting also prevents DNS-rebinding pages from reading the session token.
        test_client = request.client and request.client.host == "testclient"
        if request.url.hostname not in {"localhost", "127.0.0.1", "::1"} and not (test_client and request.url.hostname == "testserver"):
            return JSONResponse({"detail": "Use a loopback dashboard address."}, status_code=403)
        if request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"detail": "This dashboard accepts local connections only."}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            try:
                origin_ok = not origin or (urlsplit(origin).scheme, urlsplit(origin).netloc) == (request.url.scheme, request.url.netloc)
            except ValueError:
                origin_ok = False
            if not origin_ok:
                return JSONResponse({"detail": "Cross-origin control is not allowed."}, status_code=403)
            if not secrets.compare_digest(request.headers.get("x-swarm-token", "").encode("utf-8"), session_token.encode("ascii")):
                return JSONResponse({"detail": "Refresh the dashboard session before controlling jobs."}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "Control requests require JSON."}, status_code=415)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    def controller():
        if manager is None or manager.thread is None or not manager.thread.is_alive() or manager.error:
            raise HTTPException(status_code=503, detail="Job supervisor is unavailable; restart the dashboard.")
        return manager

    def job_action(action):
        try:
            return action()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Job not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @app.get("/control")
    def control_config():
        controller()
        return {"token": session_token, "root": str(root_path), "provider_mode": settings.nvidia_provider_mode,
                "live_available": settings.nvidia_provider_mode != "serverless" or bool(settings.nvidia_api_key),
                "max_seconds": settings.swarm_job_max_seconds, "max_model_calls": settings.swarm_job_max_calls,
                "max_total_tokens": settings.swarm_job_max_tokens, "concurrency": settings.swarm_job_concurrency}

    @app.get("/jobs")
    def list_jobs():
        return controller().store.list()

    @app.post("/jobs", status_code=202)
    def submit_job(request: JobRequest):
        return job_action(lambda: controller().submit(request))

    @app.post("/jobs/cancel-all")
    def cancel_all_jobs():
        return {"affected": controller().store.cancel_all()}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str):
        return job_action(lambda: controller().store.get(job_id))

    @app.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        return job_action(lambda: controller().store.cancel(job_id))

    @app.post("/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str):
        return job_action(lambda: controller().retry(job_id))

    @app.post("/jobs/{job_id}/approval")
    def approve_job(job_id: str, decision: ApprovalDecision):
        return job_action(lambda: controller().store.decide(job_id, decision.ticket, decision.approve))

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        root_label = html.escape(str(store.runs_dir))
        return (static_dir / "index.html").read_text(encoding="utf-8").replace("__RUNS_PATH__", root_label)

    @app.get("/health")
    def health():
        if manager is not None and (manager.error or manager.thread is None or not manager.thread.is_alive()):
            return JSONResponse({"status": "degraded", "supervisor": "unavailable"}, status_code=503)
        return {"status": "ok", "supervisor": "running" if manager else "not_started"}

    @app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    def api_reference():
        schema = html.escape(json.dumps(app.openapi(), indent=2))
        return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Local API reference</title><link rel="stylesheet" href="/static/dashboard.css"></head>'
                '<body><main><a href="/">← Mission control</a><h1>Local API reference</h1>'
                '<p>JSON control requests require the X-Swarm-Token header from GET /control. '
                'Use a loopback address and the same origin as the dashboard.</p>'
                '<p><a href="/openapi.json">OpenAPI schema</a></p><pre>' + schema + '</pre></main></body></html>')

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
