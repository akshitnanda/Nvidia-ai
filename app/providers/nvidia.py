from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.models.config import ModelRecord
from app.models.runtime import CompletionRequest, CompletionResponse, ProviderUsage
from app.models.settings import Settings
from app.utils.logging import RunLogger

LOGGER = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """Raised when a provider request fails."""


class NvidiaProvider:
    """OpenAI-compatible NVIDIA API client with local NIM support."""

    def __init__(self, settings: Settings, run_logger: RunLogger) -> None:
        self.settings = settings
        self.run_logger = run_logger

    def _base_url(self, model_record: ModelRecord) -> str:
        if self.settings.nvidia_provider_mode == "local_nim" or model_record.endpoint == "local_nim":
            return self.settings.nvidia_local_nim_base_url.rstrip("/")
        return self.settings.nvidia_base_url.rstrip("/")

    def complete(self, request: CompletionRequest, model_record: ModelRecord) -> CompletionResponse:
        url = f"{self._base_url(model_record)}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if model_record.endpoint != "local_nim":
            if not self.settings.nvidia_api_key:
                raise ProviderError("NVIDIA_API_KEY is required for serverless NVIDIA API calls.")
            headers["Authorization"] = f"Bearer {self.settings.nvidia_api_key}"
        else:
            headers["Authorization"] = "Bearer EMPTY"

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.extra_body:
            payload.update(request.extra_body)

        last_error: Exception | None = None
        for attempt in range(1, 4):
            started = time.perf_counter()
            try:
                with httpx.Client(timeout=request.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                duration = time.perf_counter() - started
                usage_payload = data.get("usage", {}) or {}
                completion = CompletionResponse(
                    model=data.get("model", request.model),
                    content=data["choices"][0]["message"]["content"],
                    usage=ProviderUsage(
                        prompt_tokens=usage_payload.get("prompt_tokens", 0),
                        completion_tokens=usage_payload.get("completion_tokens", 0),
                        total_tokens=usage_payload.get("total_tokens", 0),
                    ),
                    raw_response=data,
                )
                self.run_logger.append_usage(
                    {
                        "model": completion.model,
                        "profile": request.profile_name,
                        "metadata": request.metadata,
                        "duration_seconds": round(duration, 3),
                        "usage": completion.usage.model_dump(),
                    }
                )
                return completion
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last_error = exc
                LOGGER.warning("NVIDIA request failed on attempt %s: %s", attempt, exc)
                time.sleep(min(attempt, 3))
        raise ProviderError(f"NVIDIA completion failed after retries: {last_error}") from last_error

