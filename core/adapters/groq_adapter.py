#!/usr/bin/env python3
"""
Groq Adapter using official groq SDK
High-speed inference adapter for Llama 3 models.
"""

import json
import time
from typing import Any, Dict, List, Optional

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

from .base import BaseLLMAdapter, ChatMessage, LLMResponse


class GroqAdapter(BaseLLMAdapter):
    """Adapter for Groq cloud API."""

    def __init__(self, api_key: str = "", model: str = "llama-3.3-70b-versatile"):
        super().__init__(api_key=api_key, model=model)
        self.provider = "groq"
        self._client = None
        if GROQ_AVAILABLE and self.api_key:
            try:
                self._client = Groq(api_key=self.api_key)
            except Exception as e:
                print(f"[GroqAdapter] Client init warning: {e}")

    def generate(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        start_time = time.time()
        if not GROQ_AVAILABLE:
            return LLMResponse(
                text="",
                provider=self.provider,
                model=self.model,
                latency_ms=0,
                error="groq package is not installed",
            )

        if not self.api_key:
            return LLMResponse(
                text="",
                provider=self.provider,
                model=self.model,
                latency_ms=0,
                error="No API key configured for Groq",
            )

        try:
            client = self._client or Groq(api_key=self.api_key)

            formatted_messages = []
            for msg in messages:
                formatted_messages.append({"role": msg.role, "content": msg.content})

            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": formatted_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            completion = client.chat.completions.create(**kwargs)
            latency_ms = int((time.time() - start_time) * 1000)

            choice = completion.choices[0]
            text_out = choice.message.content or ""

            prompt_tokens = 0
            completion_tokens = 0
            if hasattr(completion, "usage") and completion.usage:
                prompt_tokens = getattr(completion.usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(completion.usage, "completion_tokens", 0) or 0

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
        if not GROQ_AVAILABLE:
            return {"ok": False, "latency_ms": 0, "error": "groq package not installed"}
        if not self.api_key:
            return {"ok": False, "latency_ms": 0, "error": "API key is missing"}

        try:
            client = self._client or Groq(api_key=self.api_key)
            completion = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            latency = int((time.time() - start_time) * 1000)
            if completion.choices and completion.choices[0].message.content:
                return {"ok": True, "latency_ms": latency, "error": None}
            return {"ok": False, "latency_ms": latency, "error": "Empty response received"}
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            return {"ok": False, "latency_ms": latency, "error": str(e)}
