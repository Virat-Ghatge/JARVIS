#!/usr/bin/env python3
"""
JARVIS Core Engine & Unified Input Gateway
Orchestrates hybrid voice + text command routing across fast deterministic local handlers,
skill macros, meeting automation, and 3-tier autonomous LLM dispatch.
"""

import json
import os
import random
import re
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

# Settings & Vault
from config.settings import (
    BASE_DIR,
    SKILLS_FILE,
    get_active_key,
    load_vault,
    is_internet_connected,
)

# Audio State Machine
from audio.tts_engine import TTSEngine, tts_engine as default_tts
from audio.voice_listener import VoiceListener, voice_listener as default_listener

# Core Adapters & Router
from core.adapters.base import ChatMessage
from core.context_manager import ContextManager, context_mgr
from core.llm_router import LLMRouter, router as default_router

# Local Handlers
from integrations.handlers.date_time import DateTimeHandler
from integrations.handlers.applications import ApplicationHandler
from integrations.handlers.music import MusicHandler
from integrations.handlers.web_search import WebSearchHandler
from integrations.handlers.alarm import AlarmHandler
from integrations.handlers.weather import WeatherHandler
from integrations.handlers.system_controls import SystemControls
from integrations.handlers.system_info import SystemInfoHandler
from automation.meeting_handler import MeetingHandler
from integrations.handlers.qa_handler import QAHandler
from integrations.skill_store import skill_store

VALID_INTENTS = {
    "general_qa",
    "workspace_rag",
    "tier1_code",
    "tier2_mcp",
    "tier3_vision_gui",
    "web_research",
}


class JARVISEngine:
    """
    Central JARVIS Assistant Orchestrator.
    Implements the Unified InputGateway pattern processing typed text and voice identically.
    """

    def __init__(
        self,
        tts: Optional[TTSEngine] = None,
        listener: Optional[VoiceListener] = None,
        llm_router: Optional[LLMRouter] = None,
        context_manager: Optional[ContextManager] = None,
        **kwargs,
    ):
        self.tts = tts or kwargs.get("tts_engine") or default_tts
        self.listener = listener or kwargs.get("voice_listener") or default_listener
        self.router = llm_router or default_router
        self.context = context_manager or context_mgr

        # Backward compatibility aliases & state flags
        self.running = True
        self.is_thinking: bool = False
        self.tts_engine = self.tts
        self.voice_listener = self.listener

        # Thread synchronization
        self._lock = threading.Lock()
        self._chat_listeners: List[Callable[[Dict[str, Any]], None]] = []

        # Handlers
        self.datetime_handler = DateTimeHandler(self)
        self.app_handler = ApplicationHandler(self)
        self.music_handler = MusicHandler(self)
        self.web_handler = WebSearchHandler(self)
        self.alarm_handler = AlarmHandler(self)
        self.weather_handler = WeatherHandler(self)
        self.system_controls = SystemControls(self)
        self.system_info = SystemInfoHandler(self)
        self.meeting_handler = MeetingHandler(self)
        self.qa_handler = QAHandler(self)

        # Temporary response capture buffer during handler execution
        self._captured_speech: List[str] = []

        # Wire voice listener callback into unified InputGateway
        if self.listener:
            self.listener.on_command = self._on_voice_input

        # Iron Man flair acknowledgments
        self.ack_phrases = [
            "Right away, sir.",
            "Consider it done, sir.",
            "Working on it, sir.",
            "As you wish, sir.",
            "At once, sir.",
            "Right on it, sir.",
        ]

    # ── Listener Registration for WebSockets ──────────────────────────
    def register_chat_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for CHAT_MESSAGE events."""
        with self._lock:
            if callback not in self._chat_listeners:
                self._chat_listeners.append(callback)

    def _broadcast_chat_message(self, message: Dict[str, Any]) -> None:
        """Broadcast chat events to all registered frontend listeners."""
        with self._lock:
            listeners = list(self._chat_listeners)
        for cb in listeners:
            try:
                cb(message)
            except Exception as e:
                print(f"[Engine] Chat broadcast error: {e}")

    # ── Audio State Convenience Methods ───────────────────────────────
    def set_mic_active(self, active: bool) -> None:
        if self.listener:
            self.listener.set_mic_active(active)

    def get_mic_active(self) -> bool:
        return self.listener.get_mic_active() if self.listener else False

    def toggle_mic(self) -> bool:
        return self.listener.toggle_mic() if self.listener else False

    def set_tts_active(self, active: bool) -> None:
        if self.tts:
            self.tts.set_tts_active(active)

    def get_tts_active(self) -> bool:
        return self.tts.get_tts_active() if self.tts else False

    def toggle_tts(self) -> bool:
        return self.tts.toggle_tts() if self.tts else False

    # ── Speech Output Capture ─────────────────────────────────────────
    def speak(self, text: str, wait: bool = False) -> None:
        """
        Synthesizes text through TTSEngine and logs to response buffer.
        Respects tts_active toggle (silent mode if False).
        """
        if not text or not text.strip():
            return
        cleaned = text.strip()
        self._captured_speech.append(cleaned)
        if self.tts:
            self.tts.speak(cleaned, wait=wait)

    def _on_voice_input(self, spoken_text: str) -> None:
        """Internal callback invoked when voice_listener transcribes a command."""
        self.process_command(query=spoken_text, source="voice")

    # ── Unified Input Gateway ─────────────────────────────────────────
    def _broadcast_audio_state(self) -> None:
        """Emit an immediate AUDIO_STATE broadcast so the HUD reacts instantly."""
        try:
            status = (
                "thinking" if self.is_thinking
                else ("speaking" if self.tts.is_speaking()
                      else ("listening" if self.get_mic_active() else "idle"))
            )
            payload = {
                "mic_active": self.get_mic_active(),
                "tts_active": self.get_tts_active(),
                "status": status,
                "meeting_auto_muted": getattr(self.listener, "meeting_auto_muted", False),
            }
            for cb in list(self._chat_listeners):
                try:
                    # Re-use chat listeners is not right — use the server broadcast directly
                    pass
                except Exception:
                    pass
            # Import lazily to avoid circular deps; server.broadcast_ws_sync handles it
            try:
                from automation.server import broadcast_ws_sync
                broadcast_ws_sync("AUDIO_STATE", payload)
            except Exception:
                pass
        except Exception:
            pass

    def process_command(self, query: str, source: str = "text") -> Dict[str, Any]:
        """
        Unified InputGateway method processing both typed text and spoken voice commands identically.
        Triage:
        1. Fast deterministic local handlers (time, date, volume, brightness, battery, alarms, apps, skills, etc.)
        2. LLM Intent Router (general_qa, workspace_rag, tier1_code, tier2_mcp, tier3_vision_gui, web_research)
        """
        if not query or not query.strip():
            return self._build_response("", source=source, action="none")

        clean_query = query.strip()
        timestamp = datetime.now().isoformat()
        msg_id = f"msg-{int(time.time() * 1000)}"

        # Broadcast incoming user message
        user_event = {
            "id": f"user-{int(time.time() * 1000)}",
            "sender": "user",
            "source": source,
            "text": clean_query,
            "timestamp": timestamp,
            "action": "input",
            "data": {},
        }
        self._broadcast_chat_message(user_event)

        # Set thinking state
        self.is_thinking = True
        self._broadcast_audio_state()

        try:
            return self._process_command_inner(clean_query, source)
        finally:
            self.is_thinking = False
            self._broadcast_audio_state()

    def _process_command_inner(self, clean_query: str, source: str) -> Dict[str, Any]:
        """Inner command processing logic, wrapped by process_command for is_thinking management."""
        # Clear captured speech buffer
        self._captured_speech.clear()

        # Teach Mode recording
        if skill_store.is_teaching() and source != "macro":
            stop_phrases = ["stop teaching", "stop recording", "end teach", "save routine", "cancel teach"]
            if not any(sp in clean_query.lower() for sp in stop_phrases):
                skill_store.record_step(clean_query)

        # Step 1: Check saved skill macros in skills.json
        skill_response = self._check_skills_macro(clean_query)
        if skill_response:
            return self._finalize_response(skill_response, source, action="skill_macro")

        # Step 2: Try fast deterministic handlers
        handled, response_text, action_type, extra_data = self._try_deterministic_handlers(clean_query)
        if handled:
            # If handler invoked self.speak, captured speech has priority
            if self._captured_speech:
                response_text = " ".join(self._captured_speech)
            return self._finalize_response(response_text, source, action=action_type, data=extra_data)

        # Step 3: LLM Intent Classification & Dynamic Routing
        llm_response = self._triage_llm(clean_query)
        return self._finalize_response(
            llm_response.get("text", ""),
            source,
            action=llm_response.get("action", "general_qa"),
            data=llm_response.get("data", {}),
        )

    def _finalize_response(
        self,
        text: str,
        source: str,
        action: str = "none",
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Formats and broadcasts final assistant response."""
        # Sanitize action if malformed or arbitrary string
        clean_action = action
        valid_deterministic = (
            action.startswith("get_")
            or action.startswith("set_")
            or action in (
                "skill_macro",
                "greet",
                "clear_memory",
                "system_info",
                "open_app",
                "play_music",
                "clipboard_copilot",
                "meeting_command",
                "none",
            )
        )
        if clean_action not in VALID_INTENTS and not valid_deterministic:
            clean_action = "general_qa"

        resp = self._build_response(text, source=source, action=clean_action, data=data or {})
        # Speak text if not already spoken during handler
        if not self._captured_speech and text:
            self.speak(text)
        self._broadcast_chat_message(resp)
        return resp

    def _build_response(
        self,
        text: str,
        source: str = "text",
        action: str = "none",
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Construct standard response dictionary contract."""
        return {
            "id": f"jarvis-{int(time.time() * 1000)}",
            "sender": "jarvis",
            "source": source,
            "text": text,
            "response": text,  # Backward compatibility alias
            "status": "ok",    # Backward compatibility alias
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "data": data or {},
        }

    def is_online(self) -> bool:
        """Check if internet connectivity is available."""
        return is_internet_connected()

    # Backward compatibility alias
    execute_command = process_command

    # ── Fast Deterministic Local Handlers ─────────────────────────────
    def _try_deterministic_handlers(self, query: str) -> Tuple[bool, str, str, Dict[str, Any]]:
        """
        Evaluates regex rules for local zero-latency handlers.
        Returns: (handled: bool, response: str, action: str, data: dict)
        """
        q = query.lower().strip()

        # 0. Clear conversation memory
        if q in ("clear memory", "reset conversation", "clear chat", "clear context"):
            self.context.clear()
            return True, "Conversation memory cleared, sir.", "clear_memory", {}

        # 1. Time
        if re.search(r"\b(what time|time is it|current time|tell me the time)\b", q):
            now_str = datetime.now().strftime("%I:%M %p")
            return True, f"The current time is {now_str}, sir.", "get_time", {"time": now_str}

        # 2. Date, Year & Month
        if re.search(r"\b(what year|current year|which year is it|year is it now)\b", q):
            return True, f"The current year is {datetime.now().year}, sir.", "get_date", {"year": datetime.now().year}

        if re.search(r"\b(what month|current month|which month is it)\b", q):
            return True, f"It is currently {datetime.now().strftime('%B %Y')}, sir.", "get_date", {}

        if re.search(r"\b(what('s| is)? (the )?date|what date|what day|today's date|current date|date today)\b", q):
            date_str = datetime.now().strftime("%A, %B %d, %Y")
            return True, f"Today is {date_str}, sir.", "get_date", {"date": date_str}

        # 2.5 Greeting
        if re.search(r"\b(hello|hey jarvis|hi jarvis|greetings|good morning|good afternoon|good evening)\b", q) or q in ("hi", "hello"):
            return True, "Greetings, sir. How may I assist you today?", "greet", {}

        # 3. System Diagnostics (Battery / CPU / RAM / Status)
        if re.search(r"\b(battery|cpu|system status|system diagnostics|diagnostics|specs|ram usage|how is the system)\b", q):
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                battery = psutil.sensors_battery()
                batt_info = f"Battery at {int(battery.percent)}%." if battery else "No battery detected."
                status_text = f"Systems nominal, sir. CPU load is at {cpu}%, RAM utilization is {ram}%. {batt_info}"
                return True, status_text, "system_info", {
                    "cpu": cpu,
                    "ram": ram,
                    "battery": int(battery.percent) if battery else None,
                }
            except Exception as e:
                return True, "All primary system monitors active.", "system_info", {"error": str(e)}

        # 4. Volume Controls
        if re.search(r"\b(mute volume|mute sound|mute audio)\b", q):
            try:
                self.system_controls.mute()
                return True, "Audio muted, sir.", "set_volume", {"volume": 0, "muted": True}
            except Exception:
                return True, "Audio muted.", "set_volume", {}

        if re.search(r"\b(unmute volume|unmute sound|unmute audio)\b", q):
            try:
                self.system_controls.unmute()
                return True, "Audio restored, sir.", "set_volume", {"muted": False}
            except Exception:
                return True, "Audio restored.", "set_volume", {}

        vol_match = re.search(r"\b(set volume to|volume to|set volume)\s+(\d+)\b", q)
        if vol_match:
            val = int(vol_match.group(2))
            try:
                self.system_controls.set_volume(str(val))
                return True, f"Volume adjusted to {val} percent, sir.", "set_volume", {"volume": val}
            except Exception:
                return True, f"Volume set to {val}%.", "set_volume", {"volume": val}

        # 5. Brightness Controls
        bright_match = re.search(r"\b(set brightness to|brightness to|set brightness)\s+(\d+)\b", q)
        if bright_match:
            val = int(bright_match.group(2))
            try:
                self.system_controls.set_brightness(str(val))
                return True, f"Display brightness set to {val} percent, sir.", "set_brightness", {"brightness": val}
            except Exception:
                return True, f"Brightness adjusted to {val}%.", "set_brightness", {"brightness": val}

        # 6. Alarms & Countdown Timers
        alarm_match = re.search(r"\bset alarm for\s+(.+)", q)
        if alarm_match:
            target = alarm_match.group(1).strip()
            res = self.alarm_handler.set_alarm(f"set alarm for {target}")
            return True, res or f"Alarm set for {target}, sir.", "set_alarm", {"time": target}

        timer_match = re.search(r"\bset timer for\s+(.+)", q)
        if timer_match:
            target = timer_match.group(1).strip()
            self.system_controls.set_timer(target)
            return True, f"Countdown timer initiated for {target}, sir.", "set_timer", {"duration": target}

        # 7. Weather
        if re.search(r"\b(weather|temperature|forecast|is it raining|how hot is it)\b", q):
            try:
                res = self.weather_handler.process_weather_command(query)
                return True, res or "Weather telemetry retrieved.", "get_weather", {}
            except Exception:
                pass

        # 8. Open Applications
        app_match = re.search(r"\b(open|launch|start)\s+([a-zA-Z0-9_\-\s]+)\b", q)
        if app_match and not any(k in q for k in ["mode", "meeting", "timer", "alarm", "file"]):
            app_name = app_match.group(2).strip()
            try:
                self.app_handler.open_application(f"open {app_name}")
                return True, f"Launching {app_name}, sir.", "open_app", {"app": app_name}
            except Exception:
                return True, f"Attempting to launch {app_name}.", "open_app", {"app": app_name}

        # 9. Music / Media
        if q.startswith("play ") or "play music" in q or "pause music" in q or "stop music" in q:
            try:
                self.music_handler.play_music(query)
                return True, f"Media playback updated, sir.", "play_music", {}
            except Exception:
                pass

        # 10. Clipboard Copilot Voice/Text Triggers
        if re.search(r"\b(summarize clipboard|summarize this|fix this code|explain this|explain selection|translate selection)\b", q):
            try:
                from integrations.handlers.clipboard_copilot import clipboard_copilot
                res = clipboard_copilot.act_on_clipboard(q)
                return True, res, "clipboard_copilot", {}
            except Exception as e:
                return True, f"Clipboard processing error: {e}", "clipboard_copilot", {}

        # 11. Meeting Commands & URLs
        meeting_phrases = [
            "schedule meeting", "add meeting", "what meetings", "my meetings",
            "list meetings", "upcoming meetings", "cancel meeting", "cancel next meeting",
            "join meeting", "leave meeting", "end the call",
        ]
        meeting_domains = ["meet.google.com", "teams.microsoft.com", "teams.live.com"]
        if any(p in q for p in meeting_phrases) or any(d in q for d in meeting_domains):
            self.meeting_handler.process_meeting_command(query)
            return True, "Meeting command processed, sir.", "meeting_command", {}

        return False, "", "none", {}

    # ── Check Skill Macros ────────────────────────────────────────────
    def _check_skills_macro(self, query: str) -> Optional[str]:
        """Checks if the query matches a saved routine in config/skills.json."""
        q = query.lower().strip()
        if not SKILLS_FILE.exists():
            return None

        try:
            skills = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
            for s in skills:
                triggers = s.get("trigger_phrases", [])
                if any(t.lower() == q or t.lower() in q for t in triggers):
                    steps = s.get("steps", [])
                    print(f"[SkillMacro] Triggered skill: '{s.get('name')}' ({len(steps)} steps)")
                    results = []
                    for step in steps:
                        res = self.process_command(step, source="macro")
                        if res.get("text"):
                            results.append(res["text"])
                    summary = f"Routine '{s.get('name')}' executed. " + " ".join(results)
                    return summary
        except Exception as e:
            print(f"[SkillMacro] Error reading skills: {e}")

        return None

    # ── LLM Dynamic Triage & Classification ───────────────────────────
    def _triage_llm(self, query: str) -> Dict[str, Any]:
        """
        Fast intent triage and direct single-call LLM response gateway.
        - Fast keyword/pattern routing for live web, code, vision, and RAG.
        - Direct single-call generation for general QA with automatic web search fallback on cutoff/refusal.
        - NEVER allows invalid strings to leak into action.
        """
        q_lower = query.lower().strip()

        # 1. Live Web / Current Events Detection
        web_pattern = r"\b(2025|2026|this year|latest|most heard|most streamed|top song|who won|current price|news about|search web|look up online|on spotify)\b"
        if re.search(web_pattern, q_lower):
            try:
                from automation.web_agent import web_agent
                result = web_agent.research(query)
                summary = result.get("summary") or "Web research completed, sir."
                self.context.add_user_message(query)
                self.context.add_assistant_message(summary)
                return {
                    "text": summary,
                    "action": "web_research",
                    "data": result,
                }
            except Exception as e:
                print(f"[Engine] Fast web research error: {e}")

        # 2. Explicit OS / Code / GUI / RAG Triggers
        code_pattern = r"\b(write a python script|run a script|create a file|zip folder|in my downloads|in my desktop)\b"
        if re.search(code_pattern, q_lower):
            try:
                from agent_os.code_executor import code_executor
                result = code_executor.execute_task(query)
                return {
                    "text": result.get("summary", "Code execution complete, sir."),
                    "action": "tier1_code",
                    "data": result,
                }
            except Exception as e:
                return {"text": f"Code execution notice: {e}", "action": "tier1_code", "data": {}}

        gui_pattern = r"\b(click on|type into|on my screen|visually operate)\b"
        if re.search(gui_pattern, q_lower):
            try:
                from agent_os.state_machine import os_agent
                result = os_agent.run_task(query)
                return {
                    "text": result.get("summary", "GUI operation finished, sir."),
                    "action": "tier3_vision_gui",
                    "data": result,
                }
            except Exception as e:
                return {"text": f"Vision agent notice: {e}", "action": "tier3_vision_gui", "data": {}}

        rag_pattern = r"\b(in my workspace|in my project files|search my documents)\b"
        if re.search(rag_pattern, q_lower):
            try:
                from integrations.workspace_rag import workspace_rag
                result = workspace_rag.query(query)
                return {
                    "text": result.get("answer", "Workspace search completed, sir."),
                    "action": "workspace_rag",
                    "data": result,
                }
            except Exception as e:
                return {"text": f"Workspace RAG notice: {e}", "action": "workspace_rag", "data": {}}

        # Check MCP trigger
        mcp_pattern = r"\b(mcp tool|use tool|call tool|list tools)\b"
        if re.search(mcp_pattern, q_lower):
            try:
                from integrations.mcp_client import mcp_client
                tools = mcp_client.list_tools()
                if tools:
                    tool_prompt = (
                        "You are the MCP tool selector for JARVIS 2.0. Analyze the user request and select the "
                        "appropriate server_name, tool_name, and arguments from the available tools list.\n"
                        f"Available tools: {json.dumps(tools)}\n"
                        "Return valid JSON:\n"
                        "{\n"
                        '  "server_name": "<server name>",\n'
                        '  "tool_name": "<tool name>",\n'
                        '  "arguments": {<extracted tool arguments>}\n'
                        "}"
                    )
                    decision = self.router.query_json("intent_router", query, system_prompt=tool_prompt)
                    if decision and isinstance(decision, dict):
                        s_name = decision.get("server_name")
                        t_name = decision.get("tool_name")
                        t_args = decision.get("arguments", {})
                        if s_name and t_name:
                            res = mcp_client.call_tool(s_name, t_name, t_args)
                            res_summary = res.get("output") or res.get("result") or ("Success" if res.get("ok") else res.get("error"))
                            return {
                                "text": f"MCP tool '{t_name}' executed on server '{s_name}'. Result: {res_summary}",
                                "action": "tier2_mcp",
                                "data": res,
                            }
            except Exception as e:
                return {"text": f"MCP execution notice: {e}", "action": "tier2_mcp", "data": {}}

        # 3. Direct single LLM call for all general questions & chat
        self.context.add_user_message(query)
        ctx_messages = self.context.get_messages()
        resp = self.router.dispatch_role("qa_chat", ctx_messages)
        text_out = (resp.text or "").strip() if resp else ""

        refusal_signatures = [
            "cannot predict the future",
            "can't predict the future",
            "not yet known",
            "cutoff",
            "knowledge cutoff",
            "training data ends",
            "as an ai",
            "i cannot provide real-time",
            "do not have access to real-time",
            "don't have access to real-time",
            "i do not have real-time",
            "i don't have real-time",
        ]
        placeholder_signatures = [
            "let me check that for you",
            "let me check",
            "i can help with that",
            "right away, sir",
            "working on it, sir",
            "as you wish, sir",
            "at once, sir",
        ]

        needs_web_fallback = False
        if not text_out:
            needs_web_fallback = True
        elif any(sig in text_out.lower() for sig in refusal_signatures):
            needs_web_fallback = True
        elif len(text_out) < 40 and any(ps in text_out.lower() for ps in placeholder_signatures):
            needs_web_fallback = True

        if needs_web_fallback:
            try:
                from automation.web_agent import web_agent
                result = web_agent.research(query)
                web_summary = result.get("summary")
                if web_summary and web_summary.strip():
                    self.context.add_assistant_message(web_summary)
                    return {
                        "text": web_summary,
                        "action": "web_research",
                        "data": result,
                    }
            except Exception as e:
                print(f"[Engine] Web agent fallback notice: {e}")

        final_text = text_out or "I am listening, sir. How may I assist you?"
        self.context.add_assistant_message(final_text)
        return {
            "text": final_text,
            "action": "general_qa",
            "data": {},
        }


# Singleton engine instance
engine = JARVISEngine()
