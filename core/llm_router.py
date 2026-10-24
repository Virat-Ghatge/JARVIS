#!/usr/bin/env python3
"""
Multi-Key LLM Router, Auto-Failover, Role Dispatcher & Token Telemetry
Coordinates model calls across Gemini, Groq, Anthropic, OpenRouter, Ollama, and Custom endpoints.
Automatically rotates keys upon 429 rate limit or authentication errors.
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from config.settings import (
    get_active_key,
    get_role_target,
    get_vault,
    is_internet_connected,
    rotate_provider_key,
)
from .adapters.base import BaseLLMAdapter, ChatMessage, LLMResponse
from .adapters.gemini_adapter import GeminiAdapter
from .adapters.groq_adapter import GroqAdapter
from .adapters.anthropic_adapter import AnthropicAdapter
from .adapters.openai_compat import OpenAICompatAdapter


class LLMRouter:
    """
    Central LLM router with multi-key rotation, role-based model dispatching,
    offline local fallback, and real-time token/latency telemetry tracking.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.total_session_tokens: int = 0
        self._telemetry_listeners: List[Callable[[Dict[str, Any]], None]] = []

    def register_telemetry_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for TOKEN_TELEMETRY events."""
        with self._lock:
            if callback not in self._telemetry_listeners:
                self._telemetry_listeners.append(callback)

    def _emit_telemetry(self, provider: str, model: str, latency_ms: int, prompt_tokens: int, completion_tokens: int):
        """Broadcast live token usage and latency metrics."""
        with self._lock:
            self.total_session_tokens += (prompt_tokens + completion_tokens)
            total = self.total_session_tokens
            listeners = list(self._telemetry_listeners)

        payload = {
            "provider": provider,
            "model": model,
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_session_tokens": total,
        }

        for cb in listeners:
            try:
                cb(payload)
            except Exception as e:
                print(f"[LLMRouter] Telemetry listener error: {e}")

    # Default model map for each known provider
    DEFAULT_MODELS: Dict[str, str] = {
        "gemini": "gemini-2.5-flash",
        "groq": "llama-3.3-70b-versatile",
        "anthropic": "claude-3-5-sonnet-latest",
        "openrouter": "openai/gpt-4o-mini",
        "ollama": "qwen2.5:7b",
    }

    def _resolve_model(self, provider: str, model: str) -> str:
        """Resolve empty or 'default' model to a concrete model name."""
        if model and model != "default":
            return model
        vault = get_vault()
        prov_models = vault.get("providers", {}).get(provider, {})
        if isinstance(prov_models, dict):
            models_list = prov_models.get("models", [])
            if models_list and isinstance(models_list, list) and len(models_list) > 0:
                return models_list[0]
        return self.DEFAULT_MODELS.get(provider, "gpt-4o-mini")

    def get_adapter_for_provider(
        self,
        provider: str,
        model: str,
        api_key: Optional[str] = None,
    ) -> BaseLLMAdapter:
        """Instantiate the appropriate adapter for a given provider and model."""
        vault = get_vault()
        prov_key = api_key if api_key is not None else get_active_key(provider)
        resolved_model = self._resolve_model(provider, model)

        if provider == "gemini":
            return GeminiAdapter(api_key=prov_key or "", model=resolved_model)
        elif provider == "groq":
            return GroqAdapter(api_key=prov_key or "", model=resolved_model)
        elif provider == "anthropic":
            return AnthropicAdapter(api_key=prov_key or "", model=resolved_model)
        elif provider == "openrouter":
            base_url = vault.get("providers", {}).get("openrouter", {}).get("base_url", "https://openrouter.ai/api/v1")
            return OpenAICompatAdapter(base_url=base_url, api_key=prov_key or "", model=resolved_model, provider_name="openrouter")
        elif provider == "ollama":
            base_url = vault.get("providers", {}).get("ollama", {}).get("base_url", "http://127.0.0.1:11434/v1")
            return OpenAICompatAdapter(base_url=base_url, api_key=prov_key or "ollama", model=resolved_model, provider_name="ollama")

        # Check custom endpoints
        custom_endpoints = vault.get("providers", {}).get("custom_endpoints", [])
        for ep in custom_endpoints:
            if ep.get("id") == provider or ep.get("name") == provider:
                ep_model = resolved_model if (model and model != "default") else (ep.get("model") or "gpt-4o-mini")
                return OpenAICompatAdapter(
                    base_url=ep.get("base_url", "https://api.openai.com/v1"),
                    api_key=ep.get("api_key", ""),
                    model=ep_model,
                    provider_name=ep.get("name", "custom"),
                )

        # Generic OpenAI fallback
        return OpenAICompatAdapter(
            base_url="https://api.openai.com/v1",
            api_key=prov_key or "",
            model=resolved_model,
            provider_name=provider,
        )

    def is_retryable_error(self, error_str: Optional[str]) -> bool:
        """Check if an error indicates rate limiting (429), quota exhaustion, or invalid auth."""
        if not error_str:
            return False
        err_lower = error_str.lower()
        retry_signatures = [
            "429",
            "rate limit",
            "quota",
            "resource_exhausted",
            "too many requests",
            "unauthorized",
            "invalid api key",
            "authentication",
            "401",
        ]
        return any(sig in err_lower for sig in retry_signatures)

    def generate_with_failover(
        self,
        provider: str,
        model: str,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Executes generation with automatic multi-key rotation upon rate limit / quota exhaustion.
        """
        vault = get_vault()
        prov_data = vault.get("providers", {}).get(provider, {})
        keys = prov_data.get("keys", [])

        # If provider has multiple keys, retry up to number of keys
        max_attempts = max(1, len(keys))
        last_response = None

        for attempt in range(max_attempts):
            adapter = self.get_adapter_for_provider(provider, model)
            response = adapter.generate(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            last_response = response

            if not response.error:
                # Successful call
                self._emit_telemetry(
                    provider=provider,
                    model=model,
                    latency_ms=response.latency_ms,
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                )
                return response

            # Check if error qualifies for key rotation
            if self.is_retryable_error(response.error) and len(keys) > 1 and attempt < max_attempts - 1:
                new_key = rotate_provider_key(provider)
                print(f"[LLMRouter] Rate limit/auth error on {provider} (Key #{attempt + 1}). Rotated to next key: {new_key[:6]}...")
                continue
            else:
                break

        # Emit telemetry even on error so latency is captured
        if last_response:
            self._emit_telemetry(
                provider=provider,
                model=model,
                latency_ms=last_response.latency_ms,
                prompt_tokens=last_response.prompt_tokens,
                completion_tokens=last_response.completion_tokens,
            )
            return last_response

        return LLMResponse(text="", error="Unknown generation failure", provider=provider, model=model)

    def is_network_error(self, error_str: Optional[str]) -> bool:
        """Check if an error represents a network connection failure or offline condition."""
        if not error_str:
            return False
        err_lower = error_str.lower()
        net_signatures = [
            "connection",
            "connect",
            "network",
            "timeout",
            "timed out",
            "unreachable",
            "connection refused",
            "name resolution",
            "getaddrinfo",
            "dns",
            "failed to establish a new connection",
            "offline",
            "max retries exceeded",
        ]
        return any(sig in err_lower for sig in net_signatures)

    def dispatch_role(
        self,
        role: str,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Routes the request to the provider & model configured for the specified role.
        Always attempts user's configured provider first.
        Only falls back to offline_fallback if generate_with_failover returns a network/connection
        error and provider != offline_provider.
        """
        # Always attempt the user's configured (provider, model) first
        provider, model = get_role_target(role)

        resp = self.generate_with_failover(
            provider=provider,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

        # Only fall back to offline_fallback if actual network/connection error occurred
        if resp.error and self.is_network_error(resp.error):
            offline_provider, offline_model = get_role_target("offline_fallback")
            if provider != offline_provider:
                print(
                    f"[LLMRouter] Network error on configured provider '{provider}': {resp.error}. "
                    f"Falling back to offline_fallback ({offline_provider}/{offline_model})."
                )
                return self.generate_with_failover(
                    provider=offline_provider,
                    model=offline_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )

        return resp

    def query_text(self, role: str, prompt: str, system_prompt: str = "") -> str:
        """Quick convenience method for text-to-text generation."""
        messages = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=prompt))

        resp = self.dispatch_role(role, messages)
        return resp.text

    def query_json(self, role: str, prompt: str, system_prompt: str = "") -> Optional[Dict[str, Any]]:
        """Quick convenience method for structured JSON generation."""
        messages = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=prompt))

        resp = self.dispatch_role(role, messages, json_mode=True)
        return resp.raw_json


# Global router singleton
router = LLMRouter()
