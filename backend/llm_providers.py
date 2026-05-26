"""
Provider-neutral LLM access for HITL features.

The public surface is intentionally small: callers build an LLMRequest, pass it
to an LLMProvider, and receive an LLMResponse. Provider setup is driven by env
vars so existing Anthropic/Haiku behavior stays the default while local
OpenAI-compatible endpoints such as Ollama can be selected without touching
call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import json
import os
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError


DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3.1"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
_RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504, 529)


class LLMUnavailable(RuntimeError):
    """Raised when the selected provider cannot serve a request."""


@dataclass(frozen=True)
class ProviderMetadata:
    name: str
    model: str
    base_url: Optional[str] = None
    requires_api_key: bool = False
    api_key_configured: bool = False


@dataclass(frozen=True)
class LLMHealth:
    provider: str
    available: bool
    message: str
    metadata: ProviderMetadata


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@dataclass(frozen=True)
class LLMOptions:
    max_tokens: int = 1024
    max_retries: int = 2
    timeout: float = 60.0
    cache_system: bool = True


@dataclass(frozen=True)
class LLMRequest:
    system_prompt: str
    user_message: Any
    tool: Optional[Dict[str, Any]] = None
    model_env: Optional[str] = None
    extra_system_blocks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class LLMResponse:
    provider: str
    model: str
    text: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    raw: Any = None


class LLMProvider(Protocol):
    @property
    def metadata(self) -> ProviderMetadata:
        ...

    def healthcheck(self) -> LLMHealth:
        ...

    def complete(self, request: LLMRequest, options: Optional[LLMOptions] = None) -> LLMResponse:
        ...


def load_provider_config(
    *,
    model_env: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> LLMProviderConfig:
    env = env or os.environ
    provider = (env.get("LLM_PROVIDER") or "anthropic").strip().lower()
    if provider in {"claude", "haiku"}:
        provider = "anthropic"
    if provider in {"openai_compatible", "compatible"}:
        provider = "openai-compatible"

    default_model = _default_model(provider)
    model = (
        (env.get(model_env) if model_env else None)
        or env.get("LLM_MODEL")
        or default_model
    )

    api_key = env.get("LLM_API_KEY")
    if provider == "anthropic":
        api_key = api_key or env.get("ANTHROPIC_API_KEY")
    elif provider == "openai":
        api_key = api_key or env.get("OPENAI_API_KEY")

    base_url = env.get("LLM_BASE_URL") or _default_base_url(provider)
    return LLMProviderConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


def create_provider(
    config: Optional[LLMProviderConfig] = None,
    *,
    model_env: Optional[str] = None,
) -> LLMProvider:
    config = config or load_provider_config(model_env=model_env)
    if config.provider == "anthropic":
        return AnthropicProvider(config)
    if config.provider in {"openai", "openai-compatible", "ollama"}:
        return OpenAICompatibleProvider(config)
    return UnavailableProvider(
        config,
        f"Unsupported LLM_PROVIDER '{config.provider}'. Use anthropic, openai, openai-compatible, or ollama.",
    )


class AnthropicProvider:
    def __init__(
        self,
        config: LLMProviderConfig,
        *,
        client_factory: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.config = config
        self._client_factory = client_factory

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name="anthropic",
            model=self.config.model,
            requires_api_key=True,
            api_key_configured=bool(self.config.api_key),
        )

    def healthcheck(self) -> LLMHealth:
        if not self.config.api_key:
            return LLMHealth(
                "anthropic",
                False,
                "ANTHROPIC_API_KEY or LLM_API_KEY is not configured.",
                self.metadata,
            )
        if self._client_factory is None and importlib.util.find_spec("anthropic") is None:
            return LLMHealth(
                "anthropic",
                False,
                "The 'anthropic' package is not installed.",
                self.metadata,
            )
        return LLMHealth("anthropic", True, "Anthropic provider is configured.", self.metadata)

    def complete(self, request: LLMRequest, options: Optional[LLMOptions] = None) -> LLMResponse:
        options = options or LLMOptions()
        health = self.healthcheck()
        if not health.available:
            raise LLMUnavailable(health.message)
        if not request.tool:
            raise LLMUnavailable("Anthropic provider currently requires a tool schema.")

        client = self._client()
        system_blocks = _anthropic_system_blocks(
            request.system_prompt,
            request.extra_system_blocks,
            cache_system=options.cache_system,
        )
        user_content = request.user_message

        last_err: Optional[Exception] = None
        for attempt in range(options.max_retries + 1):
            try:
                resp = client.messages.create(
                    model=self.config.model,
                    max_tokens=options.max_tokens,
                    system=system_blocks,
                    tools=[request.tool],
                    tool_choice={"type": "tool", "name": request.tool["name"]},
                    messages=[{"role": "user", "content": user_content}],
                )
                tool_input = _extract_anthropic_tool_input(resp, request.tool["name"])
                return LLMResponse(
                    provider="anthropic",
                    model=self.config.model,
                    tool_input=tool_input,
                    raw=resp,
                )
            except LLMUnavailable:
                raise
            except Exception as exc:
                last_err = exc
                if _should_retry(exc, attempt, options.max_retries):
                    _sleep_before_retry(exc, attempt)
                    continue
                break
        raise LLMUnavailable(f"Haiku call failed: {last_err}")

    def _client(self) -> Any:
        if not self.config.api_key:
            raise LLMUnavailable("ANTHROPIC_API_KEY or LLM_API_KEY is not configured.")
        if self._client_factory is not None:
            return self._client_factory(self.config.api_key)
        anthropic = importlib.import_module("anthropic")
        return anthropic.Anthropic(api_key=self.config.api_key)


class OpenAICompatibleProvider:
    def __init__(
        self,
        config: LLMProviderConfig,
        *,
        urlopen: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config
        self._urlopen = urlopen or urllib_request.urlopen

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name=self.config.provider,
            model=self.config.model,
            base_url=self.config.base_url,
            requires_api_key=self.config.provider == "openai",
            api_key_configured=bool(self.config.api_key),
        )

    def healthcheck(self) -> LLMHealth:
        if self.config.provider == "openai" and not self.config.api_key:
            return LLMHealth(
                "openai",
                False,
                "OPENAI_API_KEY or LLM_API_KEY is not configured.",
                self.metadata,
            )
        if not self.config.base_url:
            return LLMHealth(
                self.config.provider,
                False,
                "LLM_BASE_URL is not configured.",
                self.metadata,
            )
        return LLMHealth(
            self.config.provider,
            True,
            f"{self.config.provider} provider is configured.",
            self.metadata,
        )

    def complete(self, request: LLMRequest, options: Optional[LLMOptions] = None) -> LLMResponse:
        options = options or LLMOptions()
        health = self.healthcheck()
        if not health.available:
            raise LLMUnavailable(health.message)

        payload = self._payload(request, options)
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        last_err: Optional[Exception] = None
        for attempt in range(options.max_retries + 1):
            try:
                raw = self._post_json(url, payload, options.timeout)
                text, tool_input = _extract_openai_content(raw, request.tool)
                return LLMResponse(
                    provider=self.config.provider,
                    model=self.config.model,
                    text=text,
                    tool_input=tool_input,
                    raw=raw,
                )
            except LLMUnavailable:
                raise
            except Exception as exc:
                last_err = exc
                if _should_retry(exc, attempt, options.max_retries):
                    _sleep_before_retry(exc, attempt)
                    continue
                break
        raise LLMUnavailable(f"{self.config.provider} call failed: {last_err}")

    def _payload(self, request: LLMRequest, options: LLMOptions) -> Dict[str, Any]:
        messages = [{"role": "system", "content": _system_text(request)}]
        messages.append({"role": "user", "content": _openai_user_content(request.user_message)})
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": options.max_tokens,
        }
        if request.tool:
            payload["tools"] = [_openai_tool(request.tool)]
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": request.tool["name"]},
            }
        return payload

    def _post_json(self, url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(url, data=data, headers=headers, method="POST")
        try:
            with self._urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
        except HTTPError as exc:
            exc.status_code = exc.code
            raise exc
        except URLError as exc:
            raise exc
        return json.loads(body)


class UnavailableProvider:
    def __init__(self, config: LLMProviderConfig, message: str) -> None:
        self.config = config
        self.message = message

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name=self.config.provider,
            model=self.config.model,
            base_url=self.config.base_url,
            api_key_configured=bool(self.config.api_key),
        )

    def healthcheck(self) -> LLMHealth:
        return LLMHealth(self.config.provider, False, self.message, self.metadata)

    def complete(self, request: LLMRequest, options: Optional[LLMOptions] = None) -> LLMResponse:
        raise LLMUnavailable(self.message)


def _default_model(provider: str) -> str:
    if provider == "ollama":
        return DEFAULT_OLLAMA_MODEL
    if provider in {"openai", "openai-compatible"}:
        return DEFAULT_OPENAI_MODEL
    return DEFAULT_ANTHROPIC_MODEL


def _default_base_url(provider: str) -> Optional[str]:
    if provider == "ollama":
        return DEFAULT_OLLAMA_BASE_URL
    if provider == "openai":
        return DEFAULT_OPENAI_BASE_URL
    return None


def _anthropic_system_blocks(
    system_prompt: str,
    extra_system_blocks: List[Dict[str, Any]],
    *,
    cache_system: bool,
) -> List[Dict[str, Any]]:
    system_blocks: List[Dict[str, Any]] = [{"type": "text", "text": system_prompt}]
    if cache_system:
        system_blocks[0]["cache_control"] = {"type": "ephemeral"}
    for extra in extra_system_blocks or []:
        if not isinstance(extra, dict) or "text" not in extra:
            continue
        block = {"type": "text", "text": extra["text"]}
        if cache_system:
            block["cache_control"] = {"type": "ephemeral"}
        system_blocks.append(block)
    return system_blocks


def _system_text(request: LLMRequest) -> str:
    parts = [request.system_prompt]
    parts.extend(
        str(extra["text"])
        for extra in request.extra_system_blocks or []
        if isinstance(extra, dict) and "text" in extra
    )
    return "\n\n".join(parts)


def _openai_user_content(user_message: Any) -> str:
    if isinstance(user_message, str):
        return user_message
    return json.dumps(user_message, ensure_ascii=True, default=str)


def _openai_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema") or tool.get("parameters") or {},
        },
    }


def _extract_anthropic_tool_input(resp: Any, tool_name: str) -> Dict[str, Any]:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return dict(getattr(block, "input", None) or {})
    raise LLMUnavailable("Model returned no tool_use block.")


def _extract_openai_content(
    raw: Dict[str, Any],
    tool: Optional[Dict[str, Any]],
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    choices = raw.get("choices") or []
    if not choices:
        raise LLMUnavailable("Model returned no choices.")
    message = choices[0].get("message") or {}
    text = message.get("content")
    if not tool:
        return text, None

    for tool_call in message.get("tool_calls") or []:
        fn = tool_call.get("function") or {}
        if fn.get("name") != tool["name"]:
            continue
        args = fn.get("arguments") or "{}"
        try:
            parsed = json.loads(args) if isinstance(args, str) else args
        except json.JSONDecodeError as exc:
            raise LLMUnavailable("Model returned invalid tool arguments.") from exc
        return text, dict(parsed or {})
    raise LLMUnavailable("Model returned no tool call.")


def _should_retry(exc: Exception, attempt: int, max_retries: int) -> bool:
    if attempt >= max_retries:
        return False
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return status is None or status in _RETRYABLE_STATUS


def _sleep_before_retry(exc: Exception, attempt: int) -> None:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    delay = 5 * (2 ** attempt) if status == 529 else 0.5 * (2 ** attempt)
    time.sleep(delay)
