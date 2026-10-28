from __future__ import annotations

import json

from cherryquant_api.config import load_llm_config
from cherryquant_api.llm_provider import MockStrategyProvider, OpenAICompatibleStrategyProvider, get_strategy_provider


def test_default_config_uses_mock_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("CHERRYQUANT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("JACKBUDDY_API_KEY", raising=False)
    config = load_llm_config()
    assert config.effective_provider == "mock"
    assert config.api_key_configured is False
    assert config.public_summary()["api_key_configured"] is False
    assert isinstance(get_strategy_provider(), MockStrategyProvider)


def test_config_uses_compatible_provider_without_exposing_key(monkeypatch) -> None:
    monkeypatch.setenv("CHERRYQUANT_LLM_PROVIDER", "auto")
    monkeypatch.setenv("JACKBUDDY_BASE_URL", "https://example.test/v1/")
    monkeypatch.setenv("JACKBUDDY_API_KEY", "local-test-secret")
    monkeypatch.setenv("JACKBUDDY_MODEL", "test-model")
    monkeypatch.setenv("JACKBUDDY_TIMEOUT_SECONDS", "12")
    config = load_llm_config()
    assert config.effective_provider == "jackbuddy"
    assert config.base_url == "https://example.test/v1"
    assert config.timeout_seconds == 12
    summary = config.public_summary()
    assert "local-test-secret" not in str(summary)
    provider = get_strategy_provider()
    assert isinstance(provider, OpenAICompatibleStrategyProvider)
    assert provider.base_url == "https://example.test/v1"
    assert provider.api_key == "local-test-secret"


def test_compatible_provider_can_fill_server_generated_envelope_fields(monkeypatch) -> None:
    source = MockStrategyProvider().generate("站上均线后买入")
    payload = source.model_dump(mode="json")
    payload.pop("request_id")
    payload.pop("user_intent")
    provider = OpenAICompatibleStrategyProvider("https://example.test/v1", "local-test-secret", model="test-model")

    def fake_request(path, body=None):
        assert path == "chat/completions"
        return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}

    monkeypatch.setattr(provider, "_request", fake_request)
    draft = provider.generate("站上均线后买入")
    assert draft.request_id
    assert draft.user_intent == "站上均线后买入"
    assert draft.metadata["provider"] == "jackbuddy"
