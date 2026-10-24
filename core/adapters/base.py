#!/usr/bin/env python3
"""
Base Adapter Interface & Standardized LLM Response
Provides common data structures and abstract class for all LLM providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import re
from typing import Any, Dict, List, Optional


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    r"""
    Robust JSON extractor:
    1. Strips ```json and ``` fences.
    2. Tries json.loads(cleaned).
    3. If that fails, uses regex re.search(r"\{.*\}", cleaned, re.DOTALL) to extract the first JSON object and parse it.
    """
    if not text:
        return None
    cleaned = text.strip()
    # 1. Strips ```json and ``` fences
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    # 2. Tries json.loads(cleaned)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 3. Regex search for first JSON object
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


@dataclass
class ChatMessage:
    role: str  # "system", "user", "assistant"
    content: str
    image_b64: Optional[str] = None  # Base64 encoded PNG/JPEG for multimodal vision


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    provider: str = ""
    model: str = ""
    raw_json: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BaseLLMAdapter(ABC):
    """Abstract interface for all LLM backend adapters."""

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def generate(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate response from the LLM."""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """
        Send a lightweight ping to verify credentials and connectivity.
        Returns: {"ok": bool, "latency_ms": int, "error": str | None}
        """
        pass
