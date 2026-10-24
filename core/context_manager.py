#!/usr/bin/env python3
"""
Conversation Memory & Context Window Manager for JARVIS 2.0
Maintains conversation history, trims context windows, and formats messages for adapters.
"""

from datetime import datetime
import threading
from typing import List, Optional
from core.adapters.base import ChatMessage


class ContextManager:
    """Manages short-term conversation context for multi-turn dialogues."""

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self._history: List[ChatMessage] = []
        self._system_prompt: Optional[str] = (
            "You are J.A.R.V.I.S., an advanced AI assistant and operating system companion. "
            "Respond concisely, politely, and precisely. Always prioritize actionable solutions."
        )
        self._lock = threading.Lock()

    def set_system_prompt(self, prompt: str) -> None:
        """Update global system instructions."""
        with self._lock:
            self._system_prompt = prompt

    def add_user_message(self, text: str, image_b64: Optional[str] = None) -> None:
        """Append user query to history."""
        with self._lock:
            self._history.append(ChatMessage(role="user", content=text, image_b64=image_b64))
            self._trim()

    def add_assistant_message(self, text: str) -> None:
        """Append assistant response to history."""
        with self._lock:
            self._history.append(ChatMessage(role="assistant", content=text))
            self._trim()

    def get_messages(self) -> List[ChatMessage]:
        """Return full message list including system instruction."""
        with self._lock:
            messages = []
            if self._system_prompt:
                now_dt = datetime.now()
                dynamic_sys = (
                    f"{self._system_prompt}\n"
                    f"Current System Date & Time: {now_dt.strftime('%A, %B %d, %Y at %I:%M %p')} (Current Year: {now_dt.year}).\n"
                    "CRITICAL RULE: Never say 'Let me check that for you' or 'I can help with that' without actually providing the full answer in the same message."
                )
                messages.append(ChatMessage(role="system", content=dynamic_sys))
            messages.extend(list(self._history))
            return messages

    def clear(self) -> None:
        """Reset conversation memory."""
        with self._lock:
            self._history.clear()

    def _trim(self) -> None:
        """Trim messages exceeding max_turns while preserving pairs."""
        if len(self._history) > self.max_turns * 2:
            self._history = self._history[-(self.max_turns * 2):]


# Singleton instance
context_mgr = ContextManager()
