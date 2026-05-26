import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import llm_service
from llm_providers import (
    AnthropicProvider,
    LLMOptions,
    LLMProviderConfig,
    LLMRequest,
    LLMUnavailable,
    OpenAICompatibleProvider,
    create_provider,
    load_provider_config,
)


TOOL = {
    "name": "emit_result",
    "description": "Return a structured result.",
    "input_schema": {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    },
}


def test_config_defaults_to_anthropic_and_supports_task_model_override(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("LLM_MODEL", "global-model")
    monkeypatch.setenv("HAIKU_MODEL", "task-model")

    config = load_provider_config(model_env="HAIKU_MODEL")

    assert config.provider == "anthropic"
    assert config.api_key == "anthropic-key"
    assert config.model == "task-model"


def test_anthropic_healthcheck_is_safe_when_key_missing(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    health = create_provider().healthcheck()

    assert health.provider == "anthropic"
    assert health.available is False
    assert "API_KEY" in health.message


def test_anthropic_provider_preserves_forced_tool_call_shape():
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            block = SimpleNamespace(type="tool_use", name="emit_result", input={"answer": "ok"})
            return SimpleNamespace(content=[block])

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(
        LLMProviderConfig(provider="anthropic", model="claude-test", api_key="key"),
        client_factory=lambda api_key: FakeClient(),
    )

    resp = provider.complete(
        LLMRequest(
            system_prompt="system",
            user_message="hello",
            tool=TOOL,
            extra_system_blocks=[{"type": "text", "text": "vocab"}],
        ),
        LLMOptions(max_tokens=77, cache_system=True, max_retries=0),
    )

    assert resp.tool_input == {"answer": "ok"}
    assert calls[0]["model"] == "claude-test"
    assert calls[0]["max_tokens"] == 77
    assert calls[0]["tools"] == [TOOL]
    assert calls[0]["tool_choice"] == {"type": "tool", "name": "emit_result"}
    assert calls[0]["messages"] == [{"role": "user", "content": "hello"}]
    assert calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert calls[0]["system"][1]["text"] == "vocab"


def test_ollama_provider_is_configured_without_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    provider = create_provider()
    health = provider.healthcheck()

    assert health.available is True
    assert health.metadata.name == "ollama"
    assert health.metadata.base_url == "http://localhost:11434/v1"
    assert health.metadata.requires_api_key is False


def test_openai_compatible_provider_uses_base_url_without_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    provider = create_provider()
    health = provider.healthcheck()

    assert health.available is True
    assert health.metadata.name == "openai-compatible"
    assert health.metadata.base_url == "http://localhost:8000/v1"
    assert health.metadata.requires_api_key is False


def test_openai_compatible_provider_posts_tool_request_and_parses_tool_args():
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "emit_result",
                                        "arguments": json.dumps({"answer": "local"}),
                                    }
                                }
                            ],
                        }
                    }
                ]
            }).encode("utf-8")

    def fake_urlopen(req, timeout):
        requests.append((req, timeout))
        return FakeResponse()

    provider = OpenAICompatibleProvider(
        LLMProviderConfig(
            provider="ollama",
            model="llama-test",
            base_url="http://localhost:11434/v1",
        ),
        urlopen=fake_urlopen,
    )

    resp = provider.complete(
        LLMRequest(
            system_prompt="system",
            user_message=[{"type": "text", "text": "hello"}],
            tool=TOOL,
            extra_system_blocks=[{"text": "extra"}],
        ),
        LLMOptions(max_tokens=33, timeout=12, max_retries=0),
    )

    req, timeout = requests[0]
    payload = json.loads(req.data.decode("utf-8"))
    assert req.full_url == "http://localhost:11434/v1/chat/completions"
    assert timeout == 12
    assert payload["model"] == "llama-test"
    assert payload["messages"][0] == {"role": "system", "content": "system\n\nextra"}
    assert json.loads(payload["messages"][1]["content"]) == [{"type": "text", "text": "hello"}]
    assert payload["tools"][0]["type"] == "function"
    assert payload["tool_choice"] == {"type": "function", "function": {"name": "emit_result"}}
    assert resp.tool_input == {"answer": "local"}


def test_openai_provider_healthcheck_requires_api_key():
    provider = OpenAICompatibleProvider(
        LLMProviderConfig(
            provider="openai",
            model="gpt-test",
            base_url="https://api.openai.com/v1",
        ),
        urlopen=lambda req, timeout: None,
    )

    health = provider.healthcheck()

    assert health.available is False
    assert "API_KEY" in health.message


def test_call_haiku_compatibility_bridge_returns_tool_input(monkeypatch):
    class FakeProvider:
        def complete(self, request, options):
            assert request.model_env == "TASK_MODEL"
            assert request.tool == TOOL
            assert options.max_tokens == 55
            return SimpleNamespace(tool_input={"answer": "bridge"})

    monkeypatch.setattr(llm_service, "create_provider", lambda model_env=None: FakeProvider())

    result = llm_service.call_haiku(
        system_prompt="system",
        user_message="hello",
        tool=TOOL,
        model_env="TASK_MODEL",
        max_tokens=55,
        max_retries=0,
    )

    assert result == {"answer": "bridge"}


def test_openai_provider_raises_unavailable_for_missing_tool_call():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "no tool"}}]}).encode("utf-8")

    provider = OpenAICompatibleProvider(
        LLMProviderConfig(
            provider="ollama",
            model="llama-test",
            base_url="http://localhost:11434/v1",
        ),
        urlopen=lambda req, timeout: FakeResponse(),
    )

    with pytest.raises(LLMUnavailable, match="no tool"):
        provider.complete(
            LLMRequest(system_prompt="system", user_message="hello", tool=TOOL),
            LLMOptions(max_retries=0),
        )
