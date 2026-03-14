from __future__ import annotations

from pathlib import Path

from app.agents.base import Agent
from app.agents.prompts import PromptLoader
from app.models.config import AgentsConfig, ModelsConfig
from app.providers.factory import ProviderRegistry


class AgentRegistry:
    def __init__(
        self,
        config_dir: Path,
        agents_config: AgentsConfig,
        models_config: ModelsConfig,
        provider_registry: ProviderRegistry,
    ) -> None:
        self.prompt_loader = PromptLoader(config_dir)
        self.agents = {
            name: Agent(
                name=name,
                definition=definition,
                models_config=models_config,
                provider_registry=provider_registry,
                prompt_loader=self.prompt_loader,
            )
            for name, definition in agents_config.agents.items()
        }

    def get(self, name: str) -> Agent:
        return self.agents[name]

