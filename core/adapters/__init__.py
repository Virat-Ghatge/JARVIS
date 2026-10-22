"""
LLM Adapters package for JARVIS 2.0.
Provides unified interface across Google Gemini, Groq, Anthropic, and OpenAI-compatible endpoints.
"""

from .base import BaseLLMAdapter, ChatMessage, LLMResponse
from .gemini_adapter import GeminiAdapter
from .groq_adapter import GroqAdapter
from .anthropic_adapter import AnthropicAdapter
from .openai_compat import OpenAICompatAdapter, fetch_models

__all__ = [
    "BaseLLMAdapter",
    "ChatMessage",
    "LLMResponse",
    "GeminiAdapter",
    "GroqAdapter",
    "AnthropicAdapter",
    "OpenAICompatAdapter",
    "fetch_models",
]
