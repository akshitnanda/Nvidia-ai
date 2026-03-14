from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ModelRecord(BaseModel):
    label: str
    provider: str = "nvidia"
    endpoint: str = "serverless"
    free_access: bool = True
    availability: str | None = None
    capabilities: list[str] = Field(default_factory=list)


class ModelProfile(BaseModel):
    primary: str
    fallbacks: list[str] = Field(default_factory=list)
    temperature: float = 0.2
    top_p: float = 0.95
    max_tokens: int = 4096
    timeout_seconds: int = 90
    extra_body: dict[str, Any] = Field(default_factory=dict)


class ModelsConfig(BaseModel):
    defaults: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, ModelRecord] = Field(default_factory=dict)
    profiles: dict[str, ModelProfile] = Field(default_factory=dict)


class AgentDefinition(BaseModel):
    role: str
    goal: str
    model_profile: str
    system_prompt_file: str
    allowed_tools: list[str] = Field(default_factory=list)
    approval_required: bool = False


class AgentsConfig(BaseModel):
    agents: dict[str, AgentDefinition] = Field(default_factory=dict)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return data


def load_models_config(config_dir: Path) -> ModelsConfig:
    return ModelsConfig.model_validate(load_yaml(config_dir / "models.yaml"))


def load_agents_config(config_dir: Path) -> AgentsConfig:
    return AgentsConfig.model_validate(load_yaml(config_dir / "agents.yaml"))

