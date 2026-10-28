import time
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional


class ContextManager:
    """
    Multi-turn conversation memory manager with real-time 2026 clock & date
    system prompt injection to prevent LLM temporal hallucinations.
    """

    def __init__(
        self,
        max_turns: int = 12,
        max_messages: int = 24,
        system_prompt: Optional[str] = None,
    ):
        self.max_turns = max_turns
        self.max_messages = max_messages or (max_turns * 2)
        self._custom_system_prompt = system_prompt
        self.history: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def get_system_prompt(self, extra_context: Optional[str] = None) -> str:
        now = datetime.now()
        current_dt_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
        current_year = now.year

        base = self._custom_system_prompt or (
            "You are JARVIS 2.0, a highly capable, articulate, and responsive desktop AI assistant. "
            "Provide direct, accurate, and well-structured answers. "
            "When writing code, provide complete, runnable implementations."
        )
        temporal_anchor = (
            f"\n[REAL-TIME SYSTEM CLOCK]: Current Date & Time is {current_dt_str} (Year: {current_year}). "
            f"Never assume the year is 2024; always use {current_year} for current events and schedules."
        )
        full_prompt = f"{base}{temporal_anchor}"
        if extra_context:
            full_prompt += f"\n\n{extra_context}"
        return full_prompt

    def add_message(self, role: str, content: str, **meta: Any) -> Dict[str, Any]:
        norm_role = "assistant" if role in ("assistant", "model", "jarvis", "bot") else (
            "system" if role == "system" else "user"
        )
        entry: Dict[str, Any] = {
            "role": norm_role,
            "content": str(content),
            "timestamp": datetime.now().isoformat(),
        }
        if meta:
            entry.update(meta)
        with self._lock:
            self.history.append(entry)
            if len(self.history) > self.max_messages:
                self.history = self.history[-self.max_messages:]
        return entry

    def add_user_message(self, content: str) -> Dict[str, Any]:
        return self.add_message("user", content)

    def add_assistant_message(self, content: str) -> Dict[str, Any]:
        return self.add_message("assistant", content)

    def add_turn(self, user_input: str, assistant_reply: str) -> None:
        self.add_message("user", user_input)
        self.add_message("assistant", assistant_reply)

    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self.history)
        if limit is not None and limit > 0:
            return items[-limit:]
        return items

    def get_messages(self, include_system: bool = False, extra_context: Optional[str] = None) -> List[Dict[str, str]]:
        with self._lock:
            msgs = [{"role": m["role"], "content": str(m["content"])} for m in self.history]
        if include_system:
            return [{"role": "system", "content": self.get_system_prompt(extra_context=extra_context)}] + msgs
        return msgs

    def get_context(self) -> List[Dict[str, str]]:
        return self.get_messages(include_system=True)

    def build_messages(
        self,
        user_input: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        sys_content = system_prompt or self.get_system_prompt()
        if user_input:
            self.add_user_message(user_input)
        with self._lock:
            msgs = [{"role": m["role"], "content": str(m["content"])} for m in self.history]
        return [{"role": "system", "content": sys_content}] + msgs

    def clear(self) -> None:
        with self._lock:
            self.history.clear()

    def reset(self) -> None:
        self.clear()


# Module-level singleton export
context_manager = ContextManager()
