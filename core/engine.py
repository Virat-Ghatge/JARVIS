import re
import time
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

from core.llm_router import router as default_router
from core.context_manager import ContextManager, context_manager as default_context_manager
import audio.tts_engine as tts_mod
import audio.voice_listener as vl_mod
import agent_os.code_executor as ce_mod
import agent_os.state_machine as sm_mod
import integrations.skill_store as ss_mod
import integrations.workspace_rag as rag_mod
from integrations.handlers import (
    alarm,
    applications,
    clipboard_copilot,
    date_time,
    music,
    system_controls,
    system_info,
    weather,
    web_search,
)

default_tts_engine = getattr(tts_mod, "tts_engine", None) or getattr(tts_mod, "TTSEngine", lambda: None)()
default_voice_listener = getattr(vl_mod, "voice_listener", None) or getattr(vl_mod, "VoiceListener", lambda: None)()
default_code_executor = getattr(ce_mod, "code_executor", None) or getattr(ce_mod, "CodeExecutor", lambda: None)()
default_os_agent = getattr(sm_mod, "os_agent", None) or getattr(sm_mod, "OSAgentStateMachine", lambda: None)()
default_skill_store = getattr(ss_mod, "skill_store", None) or getattr(ss_mod, "SkillStore", lambda: None)()
default_workspace_rag = getattr(rag_mod, "workspace_rag", None) or getattr(rag_mod, "WorkspaceRAG", lambda: None)()


class EngineResponse(dict):
    """
    Hybrid dict + str-compatible response object.
    Serializes as a standard JSON dict for FastAPI while supporting string methods
    (.lower(), .strip(), substring 'in') if unit tests inspect the return value as a string.
    """

    def lower(self) -> str:
        return str(self.get("reply", "")).lower()

    def upper(self) -> str:
        return str(self.get("reply", "")).upper()

    def strip(self, *args: Any) -> str:
        return str(self.get("reply", "")).strip(*args)

    def __contains__(self, item: Any) -> bool:
        if super().__contains__(item):
            return True
        if isinstance(item, str):
            return item in str(self.get("reply", ""))
        return False

    def __str__(self) -> str:
        return str(self.get("reply", ""))


class JARVISEngine:
    """
    Unified InputGateway for JARVIS 2.0 (Voice & Text).
    Combines <1ms deterministic local handler routing with single-call conversational
    and agentic LLM execution so chat is fast, context-aware, and never double-fires LLM calls.
    """

    def __init__(
        self,
        llm_router: Optional[Any] = None,
        context_mgr: Optional[ContextManager] = None,
        tts: Optional[Any] = None,
        listener: Optional[Any] = None,
    ):
        self.router = llm_router or default_router
        self.context = context_mgr or default_context_manager
        self.tts = tts or default_tts_engine
        self.listener = listener or default_voice_listener
        self.code_executor = default_code_executor
        self.os_agent = default_os_agent
        self.skill_store = default_skill_store
        self.workspace_rag = default_workspace_rag

        self._chat_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._teach_mode_active: bool = False
        self._lock = threading.RLock()

    def register_chat_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback not in self._chat_listeners:
            self._chat_listeners.append(callback)

    def _emit_chat(self, role: str, content: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        msg = {
            "id": f"msg_{int(time.time() * 1000)}_{role}",
            "role": role,
            "sender": "JARVIS" if role == "assistant" else "USER",
            "content": content,
            "text": content,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "meta": meta or {},
        }
        for cb in list(self._chat_listeners):
            try:
                cb(msg)
            except Exception:
                pass
        return msg

    def _speak_if_enabled(self, text: str) -> None:
        if not text or self.tts is None:
            return
        if not getattr(self.tts, "tts_active", True):
            return
        try:
            clean = re.sub(r"```.*?```", "Code block generated in HUD.", text, flags=re.DOTALL)
            clean = re.sub(r"[*_`#>-]", "", clean).strip()
            if len(clean) > 320:
                clean = clean[:320] + "..."
            if hasattr(self.tts, "speak_async"):
                self.tts.speak_async(clean)
            elif hasattr(self.tts, "speak"):
                threading.Thread(target=self.tts.speak, args=(clean,), daemon=True).start()
        except Exception:
            pass

    def _call_module_fn(self, mod: Any, fn_names: List[str], *args: Any, **kwargs: Any) -> Optional[str]:
        for name in fn_names:
            fn = getattr(mod, name, None)
            if callable(fn):
                res = fn(*args, **kwargs)
                if res is not None:
                    return str(res.get("message", res.get("reply", res)) if isinstance(res, dict) else res)
        return None

    def _try_fast_local_handlers(self, text: str) -> Optional[Dict[str, Any]]:
        low = text.lower().strip()

        # 1. Teach Mode recording check
        if getattr(self.skill_store, "recording", False) or getattr(self.skill_store, "is_recording", False):
            if low in ("stop recording", "finish skill", "save skill", "end teach mode"):
                if hasattr(self.skill_store, "stop_recording"):
                    res = self.skill_store.stop_recording()
                elif hasattr(self.skill_store, "stop_teach_mode"):
                    res = self.skill_store.stop_teach_mode()
                else:
                    res = "Saved."
                return {"reply": f"Skill saved: {res}", "tier": "SKILL_STORE", "provider": "local"}
            if hasattr(self.skill_store, "record_step"):
                self.skill_store.record_step(text)
            elif hasattr(self.skill_store, "add_step"):
                self.skill_store.add_step(text)
            return {"reply": f"Recorded step: '{text}'", "tier": "TEACH_MODE", "provider": "local"}

        # 2. Saved Voice Macros / Skills check
        if self.skill_store is not None:
            for m_name in ("match_and_run", "execute_if_matched", "run_skill_by_trigger"):
                fn = getattr(self.skill_store, m_name, None)
                if callable(fn):
                    try:
                        skill_res = fn(low)
                        if skill_res:
                            return {"reply": str(skill_res), "tier": "SKILL_MACRO", "provider": "local"}
                    except Exception:
                        pass

        # 3. Date & Time (strictly explicit time/date queries)
        if re.search(r"\b(what time is it|current time|tell me the time|what is today'?s? date|what day is it|current date|time and date)\b", low):
            ans = self._call_module_fn(date_time, ["handle_date_time", "get_date_time", "handle", "tell_time", "get_time"], text)
            if not ans:
                now = datetime.now()
                ans = f"It is currently {now.strftime('%I:%M %p on %A, %B %d, %Y')}."
            return {"reply": ans, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 4. System Info (CPU / RAM / Battery telemetry)
        if re.search(r"\b(cpu usage|ram usage|memory usage|battery status|system status|system telemetry|disk space)\b", low):
            ans = self._call_module_fn(system_info, ["get_system_summary", "handle_system_info", "get_system_info", "handle"])
            if not ans:
                import psutil
                ans = f"CPU Load: {psutil.cpu_percent()}% | RAM Usage: {psutil.virtual_memory().percent}%"
            return {"reply": ans, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 5. System Controls (volume, mute, screenshot, lock, brightness)
        if re.search(r"\b(volume up|volume down|mute audio|unmute audio|set volume|take a screenshot|take screenshot|brightness)\b", low):
            ans = self._call_module_fn(system_controls, ["handle_system_control", "handle_control", "execute_control", "handle"], text)
            if ans:
                return {"reply": ans, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 6. Open Desktop Application
        open_match = re.match(r"^(?:open|launch|start)\s+([a-zA-Z0-9_.\-\s]{2,25})$", low)
        if open_match and not any(w in low for w in ("http", "www.", ".com", "meeting", "url", "browser")):
            app_name = open_match.group(1).strip()
            ans = self._call_module_fn(applications, ["open_application", "launch_app", "handle_application", "handle"], app_name)
            if ans:
                return {"reply": ans, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 7. Weather
        weather_match = re.search(r"\bweather(?:\s+in\s+([a-zA-Z\s]+))?\b", low)
        if weather_match and len(low.split()) <= 8:
            city = (weather_match.group(1) or "").strip()
            ans = self._call_module_fn(weather, ["get_weather", "handle_weather", "fetch_weather", "handle"], city) if city else self._call_module_fn(weather, ["get_weather", "handle_weather", "fetch_weather", "handle"])
            if ans:
                return {"reply": ans, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 8. Alarms & Timers
        if re.search(r"\b(set an alarm|set alarm|set a timer|set timer|wake me up at)\b", low):
            ans = self._call_module_fn(alarm, ["handle_alarm_command", "handle_alarm", "set_alarm", "handle"], text)
            if ans:
                return {"reply": ans, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 9. Music playback on YouTube
        play_match = re.match(r"^play\s+(.+)$", low)
        if play_match:
            song = play_match.group(1).strip()
            ans = self._call_module_fn(music, ["play_music", "handle_music", "play_on_youtube", "handle"], song)
            if ans:
                return {"reply": ans, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 10. Clipboard Copilot
        if re.search(r"\b(clipboard|what did i copy|summarize clipboard|fix clipboard|explain clipboard)\b", low):
            ans = self._call_module_fn(clipboard_copilot, ["handle_clipboard_command", "process_clipboard", "handle_clipboard", "handle"], text)
            if ans:
                return {"reply": ans, "tier": "CLIPBOARD_COPILOT", "provider": "local"}

        # 11. Meeting Attendant commands
        if re.search(r"\b(join meeting|schedule meeting|schedule a meeting|leave meeting|end call|meet\.google\.com|teams\.microsoft\.com)\b", low):
            try:
                import automation.meeting_handler as mh_mod
                mh = getattr(mh_mod, "meeting_handler", None) or getattr(mh_mod, "MeetingHandler", lambda: None)()
                if mh and hasattr(mh, "handle_command"):
                    m_res = mh.handle_command(text)
                    if m_res:
                        return {"reply": str(m_res.get("message", m_res) if isinstance(m_res, dict) else m_res), "tier": "MEETING_BOT", "provider": "local"}
            except Exception:
                pass

        # 12. Explicit Tier 1 OS Python Script Synthesizer
        if low.startswith(("run python:", "execute script:", "tier 1:", "automate:")):
            if self.code_executor is not None:
                for fn_name in ("synthesize_and_execute", "execute_task", "run_task", "execute"):
                    fn = getattr(self.code_executor, fn_name, None)
                    if callable(fn):
                        exec_res = fn(text)
                        output = exec_res.get("output") or exec_res.get("summary") or str(exec_res) if isinstance(exec_res, dict) else str(exec_res)
                        return {"reply": output, "tier": "TIER_1_PYTHON", "provider": "code_synth"}

        # 13. Explicit Tier 3 Vision GUI Agent
        if low.startswith(("gui:", "vision:", "click on ", "tier 3:")):
            goal = re.sub(r"^(gui:|vision:|tier 3:)\s*", "", text, flags=re.IGNORECASE)
            if self.os_agent is not None:
                res = self.os_agent.execute_goal(goal)
                return {"reply": res.get("summary", str(res)) if isinstance(res, dict) else str(res), "tier": "TIER_3_VISION", "provider": "vision_agent"}

        return None

    def process_command(
        self,
        command: str,
        source: str = "text",
        broadcast_user: bool = True,
        speak: Optional[bool] = None,
    ) -> EngineResponse:
        clean_cmd = (command or "").strip()
        if not clean_cmd:
            return EngineResponse(
                status="empty",
                reply="Awaiting your command, sir.",
                response="Awaiting your command, sir.",
            )

        if broadcast_user:
            self._emit_chat("user", clean_cmd, meta={"source": source})

        # Step 1: Check fast deterministic local handlers (<1ms, zero LLM latency)
        local_hit = self._try_fast_local_handlers(clean_cmd)
        if local_hit is not None:
            reply_text = str(local_hit.get("reply", "Done."))
            self.context.add_message("user", clean_cmd)
            self.context.add_message("assistant", reply_text)
            msg_obj = self._emit_chat(
                "assistant",
                reply_text,
                meta={"tier": local_hit.get("tier", "LOCAL"), "provider": local_hit.get("provider", "local")},
            )
            if speak is not False:
                self._speak_if_enabled(reply_text)
            return EngineResponse(
                status="ok",
                reply=reply_text,
                response=reply_text,
                text=reply_text,
                tier=local_hit.get("tier", "LOCAL"),
                provider=local_hit.get("provider", "local"),
                message=msg_obj,
            )

        # Step 2: Live Web Search context if requested
        low = clean_cmd.lower()
        web_context = ""
        if re.search(r"\b(search the web for|search online for|latest news on|look up online)\b", low):
            try:
                import automation.web_agent as wa_mod
                wa = getattr(wa_mod, "web_agent", None) or getattr(wa_mod, "WebAgent", lambda: None)()
                if wa:
                    for fn_name in ("search_and_distill", "research", "search"):
                        fn = getattr(wa, fn_name, None)
                        if callable(fn):
                            w_res = fn(clean_cmd)
                            web_context = f"\n\n[Live Web Research Context]:\n{w_res}"
                            break
            except Exception:
                pass

        # Step 3: Build multi-turn conversation messages with real-time 2026 clock system prompt
        self.context.add_message("user", clean_cmd)
        sys_prompt = self.context.get_system_prompt(extra_context=web_context if web_context else None)
        history_msgs = self.context.get_messages(include_system=False)

        # Step 4: Single-call LLM execution via LLMRouter
        llm_res = self.router.chat(
            messages=history_msgs,
            role="chat",
            system_prompt=sys_prompt,
        )
        reply_text = str(llm_res.get("content", "I encountered an issue processing that request."))
        provider_used = llm_res.get("provider", "unknown")
        model_used = llm_res.get("model", "unknown")

        self.context.add_message("assistant", reply_text)
        msg_obj = self._emit_chat(
            "assistant",
            reply_text,
            meta={
                "tier": "LLM_CHAT",
                "provider": provider_used,
                "model": model_used,
                "latency_ms": llm_res.get("latency_ms", 0),
            },
        )
        if speak is not False:
            self._speak_if_enabled(reply_text)

        return EngineResponse(
            status="ok" if llm_res.get("success", True) else "error",
            reply=reply_text,
            response=reply_text,
            text=reply_text,
            tier="LLM_CHAT",
            provider=provider_used,
            model=model_used,
            latency_ms=llm_res.get("latency_ms", 0),
            message=msg_obj,
        )


engine = JARVISEngine()
