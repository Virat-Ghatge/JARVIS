#!/usr/bin/env python3
"""
Anthropic Claude Adapter
Supports Anthropic Claude 3.5 Sonnet and other models via SDK or REST fallback.
"""

import json
import time
from typing import Any, Dict, List, Optional
import requests

from .base import BaseLLMAdapter, ChatMessage, LLMResponse

try:
    import anthropic
    ANTHROPIC_SDK_AVAILABLE = True
except ImportError:
    ANTHROPIC_SDK_AVAILABLE = False


class AnthropicAdapter(BaseLLMAdapter):
    """Adapter for Anthropic Claude models."""

    def __init__(self, api_key: str = "", model: str = "claude-3-5-sonnet-latest"):
        super().__init__(api_key=api_key, model=model)
        self.provider = "anthropic"
        self._client = None
        if ANTHROPIC_SDK_AVAILABLE and self.api_key:
            try:
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                print(f"[AnthropicAdapter] SDK init warning: {e}")

    def generate(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        start_time = time.time()
        if not self.api_key:
            return LLMResponse(
                text="",
                provider=self.provider,
                model=self.model,
                latency_ms=0,
                error="No API key configured for Anthropic",
            )

        # Extract system prompt if present
        system_prompt = ""
        user_assistant_messages = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                user_assistant_messages.append({"role": msg.role, "content": msg.content})

        if not user_assistant_messages:
            user_assistant_messages = [{"role": "user", "content": "Hello"}]

        # Try Anthropic SDK first if available
        if ANTHROPIC_SDK_AVAILABLE and self._client:
            try:
                kwargs: Dict[str, Any] = {
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": user_assistant_messages,
                }
                if system_prompt:
                    kwargs["system"] = system_prompt

                resp = self._client.messages.create(**kwargs)
                latency_ms = int((time.time() - start_time) * 1000)

                text_out = ""
                for block in resp.content:
                    if getattr(block, "type", "") == "text":
                        text_out += getattr(block, "text", "")

                prompt_tokens = getattr(resp.usage, "input_tokens", 0) if resp.usage else 0
                completion_tokens = getattr(resp.usage, "output_tokens", 0) if resp.usage else 0

                raw_json = None
                if json_mode and text_out:
                    try:
                        raw_json = json.loads(text_out)
                    except Exception:
                        pass

                return LLMResponse(
                    text=text_out,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    latency_ms=latency_ms,
                    provider=self.provider,
                    model=self.model,
                    raw_json=raw_json,
                )
            except Exception as e:
                # Fall back to REST if SDK fails or return error
                pass

        # Direct REST API fallback
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            body: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": user_assistant_messages,
            }
            if system_prompt:
                body["system"] = system_prompt

            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
                timeout=30,
            )
            latency_ms = int((time.time() - start_time) * 1000)

            if resp.status_code != 200:
                return LLMResponse(
                    text="",
                    latency_ms=latency_ms,
                    provider=self.provider,
                    model=self.model,
                    error=f"HTTP {resp.status_code}: {resp.text}",
                )

            data = resp.json()
            text_out = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text_out += block.get("text", "")

            usage = data.get("usage", {})
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)

            raw_json = None
            if json_mode and text_out:
                try:
                    raw_json = json.loads(text_out)
                except Exception:
                    pass

            return LLMResponse(
                text=text_out,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=latency_ms,
                provider=self.provider,
                model=self.model,
                raw_json=raw_json,
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return LLMResponse(
                text="",
                latency_ms=latency_ms,
                provider=self.provider,
                model=self.model,
                error=str(e),
            )

    def test_connection(self) -> Dict[str, Any]:
        start_time = time.time()
        if not self.api_key:
            return {"ok": False, "latency_ms": 0, "error": "API key is missing"}

        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            body = {
                "model": self.model,
                "max_tokens": 5,
                "messages": [{"role": "user", "content": "ping"}],
            }
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
                timeout=10,
            )
            latency = int((time.time() - start_time) * 1000)
            if resp.status_code == 200:
                return {"ok": True, "latency_ms": latency, "error": None}
            return {"ok": False, "latency_ms": latency, "error": f"HTTP {resp.status_code}: {resp.text}"}
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            return {"ok": False, "latency_ms": latency, "error": str(e)}
