from __future__ import annotations

from app.models.config import ModelsConfig
from app.models.runtime import CompletionRequest, CompletionResponse
from app.models.settings import Settings
from app.providers.nvidia import NvidiaProvider, ProviderError
from app.utils.logging import RunLogger


class ProviderRegistry:
    """Routes profile requests across configured NVIDIA model fallbacks."""

    def __init__(self, settings: Settings, models_config: ModelsConfig, run_logger: RunLogger) -> None:
        self.settings = settings
        self.models_config = models_config
        self.nvidia = NvidiaProvider(settings=settings, run_logger=run_logger)

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        profile = self.models_config.profiles[request.profile_name]
        chain = [profile.primary, *profile.fallbacks]
        errors: list[str] = []

        for model_name in chain:
            model_record = self.models_config.models[model_name]
            candidate = request.model_copy(update={"model": model_name})
            try:
                return self.nvidia.complete(candidate, model_record=model_record)
            except ProviderError as exc:
                errors.append(f"{model_name}: {exc}")

        raise ProviderError("All configured NVIDIA model fallbacks failed:\n" + "\n".join(errors))

