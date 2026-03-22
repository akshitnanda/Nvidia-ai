from pathlib import Path

from app.api.dashboard import create_app
from app.models.config import load_models_config
from app.models.runtime import ChatMessage, CompletionRequest
from app.models.settings import Settings
from app.providers.factory import ProviderRegistry
from app.utils.logging import RunLogger
from fastapi.testclient import TestClient


def test_demo_provider_returns_structured_planner_output(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    settings = Settings(nvidia_provider_mode="demo")
    registry = ProviderRegistry(
        settings=settings,
        models_config=load_models_config(root / "config"),
        run_logger=RunLogger(tmp_path / "data"),
    )

    response = registry.complete(
        CompletionRequest(
            profile_name="planner",
            model="nvidia/nemotron-3-super-120b-a12b",
            messages=[
                ChatMessage(role="system", content="planner"),
                ChatMessage(role="user", content="Task:\nDemo the repository\n\nAgent Role:\nplanner\n"),
            ],
            metadata={"agent": "planner"},
        )
    )

    assert response.model == "demo/local-scripted"
    assert "1. Objective" in response.content
    assert "2. Recommended Steps" in response.content


def test_dashboard_root_renders_recent_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "data" / "runs" / "demo-run"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.txt").write_text("hello", encoding="utf-8")

    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "NVIDIA Local Swarm" in response.text
    assert "swarm demo" in response.text

    runs_response = client.get("/runs")
    assert runs_response.status_code == 200
    assert runs_response.json() == [{"run_id": "demo-run"}]
