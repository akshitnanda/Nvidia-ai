from __future__ import annotations

from typing import Protocol

from app.models.runtime import CompletionRequest, CompletionResponse


class Provider(Protocol):
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return a completion for the given request."""

