"""Offline tests for the local-LLM deployment config.

No network access: these only exercise the provider-selection helpers under
LLM_PROVIDER=openai and confirm the smoke script imports and exposes `main`.
Mirrors the sys.path / monkeypatch pattern in test_llm_service_provider.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import llm_service  # noqa: E402


# ── provider_info / llm_enabled under the local (openai) provider ────────────


def test_openai_disabled_without_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setenv("LLM_MODEL", "google/gemma-3-27b-it")
    assert llm_service.llm_enabled() is False
    info = llm_service.provider_info()
    assert info["provider"] == "openai"
    assert info["enabled"] is False


def test_openai_disabled_without_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "http://host.docker.internal:1234/v1")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("HAIKU_MODEL", raising=False)
    assert llm_service.llm_enabled() is False
    assert llm_service.provider_info()["enabled"] is False


def test_openai_enabled_and_reported(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "http://host.docker.internal:1234/v1")
    monkeypatch.setenv("LLM_MODEL", "google/gemma-3-27b-it")
    assert llm_service.llm_enabled() is True
    info = llm_service.provider_info()
    assert info["provider"] == "openai"
    assert info["model"] == "google/gemma-3-27b-it"
    assert info["base_url"] == "http://host.docker.internal:1234/v1"
    assert info["enabled"] is True


def test_openai_model_falls_back_to_haiku_model_for_enabled(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("HAIKU_MODEL", "local-fallback")
    # enabled() accepts LLM_MODEL or HAIKU_MODEL as the model signal.
    assert llm_service.llm_enabled() is True


# ── smoke script importability ───────────────────────────────────────────────


def test_smoke_script_imports_and_exposes_main():
    scripts_dir = os.path.join(os.path.dirname(__file__), "..", "scripts")
    sys.path.insert(0, os.path.abspath(scripts_dir))
    import llm_smoke  # noqa: E402

    assert callable(llm_smoke.main)
    assert isinstance(llm_smoke.ECHO_TOOL, dict)
    assert llm_smoke.ECHO_TOOL["name"] == "echo_check"
    assert "ok" in llm_smoke.ECHO_TOOL["input_schema"]["properties"]
