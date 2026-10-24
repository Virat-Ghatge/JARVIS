#!/usr/bin/env python3
"""
Universal OpenAI-Compatible Adapter
Connects to OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any custom /v1 endpoint.
Includes dynamic model fetching via GET /v1/models and fast connection verification.
"""

import json
import time
from typing import Any, Dict, List, Optional
import requests

from .base import BaseLLMAdapter, ChatMessage, LLMResponse, extract_json_from_text


def fetch_models(base_url: str, api_key: str = "") -> List[str]:
    """
    Queries GET {base_url}/models and returns a list of discovered model ID strings.
    Handles trailing slashes, auth headers, and common OpenAI/Ollama model list structures.
    """
    clean_url = base_url.rstrip("/")
    if not clean_url.endswith("/models"):
        clean_url = f"{clean_url}/models"

    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    try:
        resp = requests.get(clean_url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            models_list: List[str] = []
            if isinstance(data, dict):
                # Standard OpenAI format: {"data": [{"id": "..."}, ...]}
                if "data" in data and isinstance(data["data"], list):
                    for item in data["data"]:
                        if isinstance(item, dict) and "id" in item:
                            models_list.append(item["id"])
                        elif isinstance(item, str):
                            models_list.append(item)
                # Ollama format: {"models": [{"name": "..."}, ...]}
                elif "models" in data and isinstance(data["models"], list):
                    for item in data["models"]:
                        if isinstance(item, dict) and "name" in item:
                            models_list.append(item["name"])
                        elif isinstance(item, str):
                            models_list.append(item)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "id" in item:
                        models_list.append(item["id"])
                    elif isinstance(item, str):
                        models_list.append(item)
            return sorted(list(set(models_list))) if models_list else []
    except Exception as e:
        print(f"[OpenAICompat] fetch_models error: {e}")

    return []


class OpenAICompatAdapter(BaseLLMAdapter):
    """Universal adapter for any OpenAI-compatible API endpoint."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        provider_name: str = "openai_compat",
    ):
        super().__init__(api_key=api_key, model=model)
        self.base_url = base_url.rstrip("/")
        self.provider = provider_name

    def generate(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        start_time = time.time()

        formatted_messages = []
        for msg in messages:
            formatted_messages.append({"role": msg.role, "content": msg.content})

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        endpoint_url = f"{self.base_url}/chat/completions"

        try:
            resp = requests.post(endpoint_url, headers=headers, json=body, timeout=45)

            # If json_mode=True and request returns HTTP != 200 or empty choices,
            # immediately retry the request without response_format!
            if json_mode:
                need_retry = False
                if resp.status_code != 200:
                    need_retry = True
                else:
                    try:
                        d = resp.json()
                        c = d.get("choices", [])
                        if not c or not c[0].get("message", {}).get("content"):
                            need_retry = True
                    except Exception:
                        need_retry = True

                if need_retry:
                    retry_body = {
                        "model": self.model,
                        "messages": formatted_messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    try:
                        retry_resp = requests.post(endpoint_url, headers=headers, json=retry_body, timeout=45)
                        if retry_resp.status_code == 200:
                            resp = retry_resp
                    except Exception:
                        pass

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
            choices = data.get("choices", [])
            text_out = ""
            if choices and isinstance(choices, list):
                msg_obj = choices[0].get("message", {})
                text_out = msg_obj.get("content", "") or ""

            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0) if usage else 0
            completion_tokens = usage.get("completion_tokens", 0) if usage else 0

            # Always use extract_json_from_text(text_out) to populate raw_json
            raw_json = extract_json_from_text(text_out) if text_out else None

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
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"

        endpoint_url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }

        try:
            resp = requests.post(endpoint_url, headers=headers, json=body, timeout=3)
            latency = int((time.time() - start_time) * 1000)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return {"ok": True, "latency_ms": latency, "error": None}
                return {"ok": False, "latency_ms": latency, "error": "No completion choices returned"}
            return {"ok": False, "latency_ms": latency, "error": f"HTTP {resp.status_code}: {resp.text}"}
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            return {"ok": False, "latency_ms": latency, "error": str(e)}
