"""Tests for the provider-agnostic LLM layer in llm_service.

These cover the new local (openai/LM Studio) provider path and the
provider-selection helpers without any network access: the Anthropic and
OpenAI clients are monkeypatched with fakes. The goal is to prove that
`call_haiku` returns the same dict shape under both providers and that the
local path builds a structured-output request and parses noisy JSON robustly.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import llm_service  # noqa: E402


TOOL = {
    "name": "demo_tool",
    "input_schema": {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    },
}


# ── Provider selection ───────────────────────────────────────────────────────


def test_default_provider_is_anthropic(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert llm_service._provider() == "anthropic"


def test_llm_enabled_anthropic(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_service.llm_enabled() is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert llm_service.llm_enabled() is True


def test_llm_enabled_openai_requires_base_url_and_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("HAIKU_MODEL", raising=False)
    assert llm_service.llm_enabled() is False
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:1234/v1")
    assert llm_service.llm_enabled() is False  # still no model
    monkeypatch.setenv("LLM_MODEL", "local-model")
    assert llm_service.llm_enabled() is True


def test_provider_info_shape(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LLM_MODEL", "gemma-local")
    info = llm_service.provider_info()
    assert info["provider"] == "openai"
    assert info["model"] == "gemma-local"
    assert info["base_url"] == "http://localhost:1234/v1"
    assert info["enabled"] is True


# ── JSON parsing ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"answer": "ok"}', {"answer": "ok"}),
        ('```json\n{"answer": "ok"}\n```', {"answer": "ok"}),
        ('Here you go: {"answer": "ok"} thanks', {"answer": "ok"}),
    ],
)
def test_parse_json_object_variants(raw, expected):
    assert llm_service._parse_json_object(raw) == expected


def test_parse_json_object_empty_raises():
    with pytest.raises(ValueError):
        llm_service._parse_json_object("   ")


def test_parse_json_object_garbage_raises():
    with pytest.raises(ValueError):
        llm_service._parse_json_object("no json here")


# ── Block flattening (PDF → text happens here for local models) ──────────────


def test_blocks_to_text_string_passthrough():
    assert llm_service._blocks_to_text("hello") == "hello"


def test_blocks_to_text_joins_text_blocks():
    blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    assert llm_service._blocks_to_text(blocks) == "a\n\nb"


def test_blocks_to_text_converts_pdf_document(monkeypatch):
    monkeypatch.setattr(llm_service, "_extract_pdf_text", lambda data: "PDF_TEXT")
    blocks = [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": "xxx"},
        },
        {"type": "text", "text": "instruction"},
    ]
    out = llm_service._blocks_to_text(blocks)
    assert "PDF_TEXT" in out
    assert "instruction" in out


# ── call_haiku dispatch: local (openai) provider ─────────────────────────────


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, captured, content):
        self._captured = captured
        self._content = content

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return _FakeResponse(self._content)


class _FakeOpenAIClient:
    def __init__(self, captured, content):
        self.chat = type("C", (), {"completions": _FakeCompletions(captured, content)})()


def test_call_haiku_openai_returns_parsed_dict(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "local-model")
    captured: dict = {}
    monkeypatch.setattr(
        llm_service,
        "_openai_client",
        lambda: _FakeOpenAIClient(captured, '{"answer": "42"}'),
    )

    out = llm_service.call_haiku(
        system_prompt="SYS",
        tool=TOOL,
        user_message="what is the answer?",
        max_tokens=128,
    )
    assert out == {"answer": "42"}
    # First attempt must use a json_schema structured-output request built from
    # the tool's input_schema, and target the configured local model.
    assert captured["model"] == "local-model"
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["name"] == "demo_tool"
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["system", "user"]


def test_call_haiku_openai_missing_model_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("HAIKU_MODEL", raising=False)
    monkeypatch.setattr(
        llm_service, "_openai_client", lambda: _FakeOpenAIClient({}, "{}")
    )
    with pytest.raises(llm_service.LLMUnavailable):
        llm_service.call_haiku(
            system_prompt="SYS", tool=TOOL, user_message="hi"
        )


# ── call_haiku dispatch: anthropic provider (unchanged behaviour) ────────────


class _ToolUseBlock:
    def __init__(self, name, inp):
        self.type = "tool_use"
        self.name = name
        self.input = inp


class _FakeAnthropicMessages:
    def __init__(self, block):
        self._block = block

    def create(self, **kwargs):
        return type("R", (), {"content": [self._block]})()


class _FakeAnthropicClient:
    def __init__(self, block):
        self.messages = _FakeAnthropicMessages(block)


def test_call_haiku_anthropic_returns_tool_input(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    block = _ToolUseBlock("demo_tool", {"answer": "from-claude"})
    monkeypatch.setattr(llm_service, "_anthropic_client", lambda: _FakeAnthropicClient(block))

    out = llm_service.call_haiku(
        system_prompt="SYS",
        tool=TOOL,
        user_message="hello",
    )
    assert out == {"answer": "from-claude"}
