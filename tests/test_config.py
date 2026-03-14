from pathlib import Path

from app.models.config import load_agents_config, load_models_config


def test_config_files_load() -> None:
    root = Path(__file__).resolve().parents[1]
    models = load_models_config(root / "config")
    agents = load_agents_config(root / "config")

    assert "planner" in models.profiles
    assert "coder" in agents.agents
    assert models.profiles["planner"].primary in models.models

