#!/usr/bin/env python3
"""
Base Adapter Interface & Standardized LLM Response
Provides common data structures and abstract class for all LLM providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
