from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.agents.prompts import PromptLoader
from app.models.config import AgentDefinition, ModelsConfig
from app.models.runtime import AgentResult, ChatMessage, CompletionRequest
from app.providers.factory import ProviderRegistry


@dataclass(slots=True)
class Agent:
    name: str
    definition: AgentDefinition
    models_config: ModelsConfig
    provider_registry: ProviderRegistry
    prompt_loader: PromptLoader

    def run(self, task: str, context: dict[str, Any]) -> AgentResult:
        profile = self.models_config.profiles[self.definition.model_profile]
        system_prompt = self.prompt_loader.load(self.definition.system_prompt_file)
        user_prompt = self._build_user_prompt(task=task, context=context)
        response = self.provider_registry.complete(
            CompletionRequest(
                profile_name=self.definition.model_profile,
                model=profile.primary,
                temperature=profile.temperature,
                top_p=profile.top_p,
                max_tokens=profile.max_tokens,
                timeout_seconds=profile.timeout_seconds,
                extra_body=profile.extra_body,
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_prompt),
                ],
                metadata={"agent": self.name},
            )
        )
        return AgentResult(agent=self.name, model=response.model, output=response.content)

    def _build_user_prompt(self, task: str, context: dict[str, Any]) -> str:
        return (
            f"Task:\n{task}\n\n"
            f"Agent Role:\n{self.definition.role}\n\n"
            f"Agent Goal:\n{self.definition.goal}\n\n"
            f"Allowed Tools:\n{', '.join(self.definition.allowed_tools)}\n\n"
            f"Context JSON:\n{json.dumps(context, indent=2, ensure_ascii=False)}\n"
        )

