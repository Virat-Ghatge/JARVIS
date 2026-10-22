#!/usr/bin/env python3
"""
Google Gemini Adapter using google-genai SDK
Supports text, multimodal vision, structured JSON responses, and connection testing.
"""

import base64
import json
import time
from typing import Any, Dict, List, Optional

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from .base import BaseLLMAdapter, ChatMessage, LLMResponse


class GeminiAdapter(BaseLLMAdapter):
    """Adapter for Google Gemini models via google-genai SDK."""

    def __init__(self, api_key: str = "", model: str = "gemini-2.5-flash"):
        super().__init__(api_key=api_key, model=model)
        self.provider = "gemini"
        self._client = None
        if GEMINI_AVAILABLE and self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[GeminiAdapter] Client init warning: {e}")

    def generate(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        start_time = time.time()
        if not GEMINI_AVAILABLE:
            return LLMResponse(
                text="",
                provider=self.provider,
                model=self.model,
                latency_ms=0,
                error="google-genai library is not installed",
            )

        if not self.api_key:
            return LLMResponse(
                text="",
                provider=self.provider,
                model=self.model,
                latency_ms=0,
                error="No API key configured for Gemini",
            )

        try:
            client = self._client or genai.Client(api_key=self.api_key)

            # Separate system prompt and build contents
            system_instruction = None
            contents: List[Any] = []

            for msg in messages:
                if msg.role == "system":
                    system_instruction = msg.content
                elif msg.role in ("user", "assistant"):
                    parts: List[Any] = []
                    if msg.image_b64:
                        try:
                            img_data = base64.b64decode(msg.image_b64)
                            parts.append(types.Part.from_bytes(data=img_data, mime_type="image/png"))
                        except Exception as img_err:
                            print(f"[GeminiAdapter] Image decode error: {img_err}")
                    if msg.content:
                        parts.append(msg.content)
                    if parts:
                        contents.extend(parts)

            config_kwargs: Dict[str, Any] = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            if system_instruction:
                config_kwargs["system_instruction"] = system_instruction
            if json_mode:
                config_kwargs["response_mime_type"] = "application/json"

            config = types.GenerateContentConfig(**config_kwargs)

            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            text_out = response.text or ""

            prompt_tokens = 0
            completion_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                completion_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

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
            err_msg = str(e)
            return LLMResponse(
                text="",
                latency_ms=latency_ms,
                provider=self.provider,
                model=self.model,
                error=err_msg,
            )

    def test_connection(self) -> Dict[str, Any]:
        start_time = time.time()
        if not GEMINI_AVAILABLE:
            return {"ok": False, "latency_ms": 0, "error": "google-genai package not installed"}
        if not self.api_key:
            return {"ok": False, "latency_ms": 0, "error": "API key is missing"}

        try:
            client = self._client or genai.Client(api_key=self.api_key)
            resp = client.models.generate_content(
                model=self.model,
                contents="ping",
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            latency = int((time.time() - start_time) * 1000)
            if resp.text:
                return {"ok": True, "latency_ms": latency, "error": None}
            return {"ok": False, "latency_ms": latency, "error": "Empty response received"}
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            return {"ok": False, "latency_ms": latency, "error": str(e)}
