from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from app.models.config import ModelRecord
from app.models.runtime import CompletionRequest
from app.models.settings import Settings
from app.providers.nvidia import NvidiaProvider, ProviderError
from app.utils.logging import RunLogger


def provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, handler, mode="serverless"):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("app.providers.nvidia.httpx.Client", lambda **_: client)
    sleep = Mock()
    monkeypatch.setattr("app.providers.nvidia.time.sleep", sleep)
    settings = Settings(_env_file=None, nvidia_provider_mode=mode, nvidia_api_key=None if mode == "local_nim" else "test")
    return NvidiaProvider(settings, RunLogger(tmp_path)), sleep


REQUEST = CompletionRequest(profile_name="coder", model="test", messages=[])
MODEL = ModelRecord(label="test")
SUCCESS = {"choices": [{"message": {"content": "hello"}}]}


def test_local_nim_override_needs_no_cloud_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request):
        assert str(request.url) == "http://localhost:8000/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer EMPTY"
        return httpx.Response(200, json=SUCCESS)
    api, _ = provider(tmp_path, monkeypatch, handler, "local_nim")
    assert api.complete(REQUEST, MODEL).content == "hello"


def test_auth_failure_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = Mock(return_value=httpx.Response(401))
    api, sleep = provider(tmp_path, monkeypatch, handler)
    with pytest.raises(ProviderError, match="401"):
        api.complete(REQUEST, MODEL)
    assert handler.call_count == 1
    sleep.assert_not_called()


def test_rate_limit_uses_retry_after_then_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = Mock(side_effect=[httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json=SUCCESS)])
    api, sleep = provider(tmp_path, monkeypatch, handler)
    assert api.complete(REQUEST, MODEL).content == "hello"
    assert handler.call_count == 2
    sleep.assert_called_once_with(2.0)


def test_no_sleep_after_final_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = Mock(return_value=httpx.Response(503))
    api, sleep = provider(tmp_path, monkeypatch, handler)
    with pytest.raises(ProviderError):
        api.complete(REQUEST, MODEL)
    assert handler.call_count == 3
    assert sleep.call_count == 2


@pytest.mark.parametrize("payload", [{"choices": []}, {"choices": [{"message": {"content": None}}]}, []])
def test_malformed_response_is_provider_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload) -> None:
    api, sleep = provider(tmp_path, monkeypatch, lambda _: httpx.Response(200, json=payload))
    with pytest.raises(ProviderError, match="invalid completion"):
        api.complete(REQUEST, MODEL)
    sleep.assert_not_called()
