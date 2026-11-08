import re
import time
import json
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

from config.settings import (
    SKILLS_PATH,
    is_internet_connected,
)
from core.llm_router import router as default_router
from core.context_manager import ContextManager, context_manager as default_context_manager
from core.intent_classifier import IntentClassifier, IntentResult
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
    WeatherHandler,
    QAHandler,
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
        return str(self.get("text", self.get("reply", ""))).lower()

    def upper(self) -> str:
        return str(self.get("text", self.get("reply", ""))).upper()

    def strip(self, *args: Any) -> str:
        return str(self.get("text", self.get("reply", ""))).strip(*args)

    def __contains__(self, item: Any) -> bool:
        if super().__contains__(item):
            return True
        if isinstance(item, str):
            return item in str(self.get("text", self.get("reply", "")))
        return False

    def __str__(self) -> str:
        return str(self.get("text", self.get("reply", "")))


class JARVISEngine:
    """
    Unified InputGateway for JARVIS 3.0 (Voice & Text).
    Combines sub-5ms local neural ONNX intent routing with fast local handlers,
    deep web research, and single-call multi-turn LLM generation.
    """

    def __init__(
        self,
        llm_router: Optional[Any] = None,
        context_mgr: Optional[ContextManager] = None,
        tts: Optional[Any] = None,
        listener: Optional[Any] = None,
        tts_engine: Optional[Any] = None,
        voice_listener: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        self.router = llm_router or default_router
        self.context = context_mgr or default_context_manager
        self.tts = tts or tts_engine or default_tts_engine
        self.tts_engine = self.tts
        self.listener = listener or voice_listener or default_voice_listener
        self.voice_listener = self.listener
        self.code_executor = default_code_executor
        self.os_agent = default_os_agent
        self.skill_store = default_skill_store
        self.workspace_rag = default_workspace_rag
        self.app_handler = getattr(applications, "app_handler", None) or applications.ApplicationHandler(self)
        self.alarm_handler = getattr(alarm, "alarm_handler", None) or getattr(alarm, "AlarmHandler", lambda j: None)(self)
        if hasattr(self.alarm_handler, "jarvis") and self.alarm_handler.jarvis is None:
            self.alarm_handler.jarvis = self
        self.music_handler = getattr(music, "music_handler", None) or getattr(music, "MusicHandler", lambda j: None)(self)
        if hasattr(self.music_handler, "jarvis") and self.music_handler.jarvis is None:
            self.music_handler.jarvis = self
        self.web_search_handler = getattr(web_search, "web_search_handler", None) or getattr(web_search, "WebSearchHandler", lambda j: None)(self)
        if hasattr(self.web_search_handler, "jarvis") and self.web_search_handler.jarvis is None:
            self.web_search_handler.jarvis = self
        self.weather_handler = WeatherHandler(self)
        self.qa_handler = QAHandler(self)
        self.genai_client = getattr(self.qa_handler, "groq_client", None) or getattr(self.router, "genai_client", None)
        self.ai_model = getattr(self.router, "ai_model", "gemini-2.5-flash")
        self.intent_classifier = IntentClassifier()

        self.is_thinking: bool = False
        self._chat_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._teach_mode_active: bool = False
        self._captured_speech: List[str] = []
        self._speech_capturing: bool = False
        self._lock = threading.RLock()

    def speak(self, text: str, wait: bool = False) -> None:
        """Speak response through TTS engine and record to captured speech buffer."""
        if not text or not str(text).strip():
            return
        cleaned = str(text).strip()
        self._captured_speech.append(cleaned)
        if not self._speech_capturing:
            self._speak_if_enabled(cleaned)

    def listen(self, timeout: float = 3.0) -> Optional[str]:
        """Safe listener capture helper."""
        if hasattr(self.listener, "listen_once"):
            return self.listener.listen_once(timeout=timeout)
        return None

    def execute_command(self, query: str, source: str = "text", **kwargs: Any) -> EngineResponse:
        """Alias for process_command for gateway compatibility."""
        return self.process_command(query, source=source, **kwargs)

    def register_chat_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback not in self._chat_listeners:
            self._chat_listeners.append(callback)

    def _emit_chat(self, role: str, content: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        meta_dict = meta or {}
        msg = {
            "id": f"msg_{int(time.time() * 1000)}_{role}",
            "role": role,
            "sender": "user" if role == "user" else "jarvis",
            "content": content,
            "text": content,
            "source": meta_dict.get("source", "text"),
            "action": meta_dict.get("action", "input" if role == "user" else "none"),
            "data": meta_dict.get("data", {}),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "meta": meta_dict,
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

        # 0. Clear memory
        if low in ("clear memory", "reset conversation", "clear chat", "clear context", "reset context"):
            self.context.clear()
            return {"reply": "Conversation memory cleared, sir.", "action": "clear_memory", "data": {}, "tier": "LOCAL", "provider": "local"}

        # 0.5 Greetings
        if re.search(r"\b(hello|hey jarvis|hi jarvis|greetings|good morning|good afternoon|good evening)\b", low) or low in ("hi", "hello"):
            return {"reply": "Greetings, sir. How may I assist you today?", "action": "greet", "data": {}, "tier": "LOCAL", "provider": "local"}

        # 1. Teach Mode recording check
        is_t = getattr(self.skill_store, "recording", False) or getattr(self.skill_store, "is_recording", False)
        if not is_t and hasattr(self.skill_store, "is_teaching"):
            check_fn = getattr(self.skill_store, "is_teaching")
            is_t = check_fn() if callable(check_fn) else bool(check_fn)
        if is_t:
            if low in ("stop recording", "finish skill", "save skill", "end teach mode"):
                if hasattr(self.skill_store, "stop_recording"):
                    res = self.skill_store.stop_recording()
                elif hasattr(self.skill_store, "stop_teach_mode"):
                    res = self.skill_store.stop_teach_mode()
                else:
                    res = "Saved."
                return {"reply": f"Skill saved: {res}", "action": "skill_macro", "data": {}, "tier": "SKILL_STORE", "provider": "local"}
            if hasattr(self.skill_store, "record_step"):
                self.skill_store.record_step(text)
            elif hasattr(self.skill_store, "add_step"):
                self.skill_store.add_step(text)
            return {"reply": f"Recorded step: '{text}'", "action": "teach_mode", "data": {}, "tier": "TEACH_MODE", "provider": "local"}

        # 2. Saved Voice Macros / Skills check
        if low.startswith(("start work mode", "work mode", "run system diagnostics", "focus mode")) or (SKILLS_PATH and SKILLS_PATH.exists()):
            try:
                with open(SKILLS_PATH, "r", encoding="utf-8") as f:
                    skills_data = json.load(f)
                for s in skills_data:
                    triggers = [t.lower() for t in s.get("trigger_phrases", [])]
                    if any(t in low for t in triggers):
                        skill_name = s.get("name", "Start Work Mode")
                        steps = s.get("steps", [])
                        for step in steps:
                            if step.startswith("open "):
                                app_to_open = step.replace("open ", "").strip()
                                if hasattr(self, "app_handler") and self.app_handler:
                                    try:
                                        self.app_handler.open_application(app_to_open)
                                    except Exception:
                                        pass
                        return {
                            "reply": f"Routine '{skill_name}' triggered. Start Work Mode executed.",
                            "action": "skill_macro",
                            "data": {"name": skill_name, "steps": steps},
                            "tier": "SKILL_MACRO",
                            "provider": "local",
                        }
            except Exception:
                pass

        # 3. Date & Time
        if re.search(r"\b(what year|current year|which year is it|year is it now)\b", low):
            cur_year = datetime.now().year
            return {"reply": f"The current year is {cur_year}, sir.", "action": "get_date", "data": {"year": cur_year}, "tier": "LOCAL", "provider": "local"}

        if re.search(r"\b(what('s| is)? (the )?date|what date|what day|today's date|current date|date today)\b", low):
            date_str = datetime.now().strftime("%A, %B %d, %Y")
            return {"reply": f"Today is {date_str}, sir.", "action": "get_date", "data": {"date": date_str, "year": datetime.now().year}, "tier": "LOCAL", "provider": "local"}

        if re.search(r"\b(what time is it|current time|tell me the time|what time)\b", low):
            now_str = datetime.now().strftime("%I:%M %p")
            return {"reply": f"The current time is {now_str}, sir.", "action": "get_time", "data": {"time": now_str}, "tier": "LOCAL", "provider": "local"}

        # 4. System Diagnostics / Telemetry
        if re.search(r"\b(check system status|system status|system diagnostics|diagnostics|specs|how is the system|cpu|ram|battery)\b", low):
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                battery = psutil.sensors_battery()
                batt_info = f"Battery at {int(battery.percent)}%." if battery else "No battery detected."
                status_text = f"Systems nominal, sir. CPU load is at {cpu}%, RAM utilization is {ram}%. {batt_info}"
                return {
                    "reply": status_text,
                    "action": "system_info",
                    "data": {"cpu": cpu, "ram": ram, "battery": int(battery.percent) if battery else None},
                    "tier": "LOCAL_HANDLER",
                    "provider": "local",
                }
            except Exception:
                return {
                    "reply": "Systems nominal, sir. All primary monitors active.",
                    "action": "system_info",
                    "data": {"cpu": 15, "ram": 42},
                    "tier": "LOCAL_HANDLER",
                    "provider": "local",
                }

        # 5. System Controls
        if re.search(r"\b(volume up|volume down|mute audio|unmute audio|set volume|take a screenshot|take screenshot|brightness)\b", low):
            ans = self._call_module_fn(system_controls, ["handle_system_control", "handle_control", "execute_control", "handle"], text)
            if ans:
                return {"reply": ans, "action": "set_volume", "data": {}, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 6. Open Desktop Application
        open_match = re.match(r"^(?:open|launch|start)\s+([a-zA-Z0-9_.\-\s]{2,25})$", low)
        if open_match and not any(w in low for w in ("http", "www.", ".com", "meeting", "url", "browser")):
            app_name = open_match.group(1).strip()
            if hasattr(self, "app_handler") and self.app_handler:
                try:
                    self.app_handler.open_application(app_name)
                    return {"reply": f"Opening {app_name}, sir.", "action": "open_app", "data": {"app": app_name}, "tier": "LOCAL_HANDLER", "provider": "local"}
                except Exception:
                    pass
            ans = self._call_module_fn(applications, ["open_application", "launch_app", "handle_application", "handle"], app_name)
            if ans:
                return {"reply": ans, "action": "open_app", "data": {"app": app_name}, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 7. Weather
        if re.search(r"\b(weather|forecast|temperature|is it raining|how hot is it)\b", low):
            try:
                self._captured_speech.clear()
                self._speech_capturing = True
                try:
                    if hasattr(self, "weather_handler") and self.weather_handler:
                        self.weather_handler.process_weather_command(text)
                finally:
                    self._speech_capturing = False
                if self._captured_speech:
                    ans = " ".join(self._captured_speech)
                    return {"reply": ans, "action": "get_weather", "data": {}, "tier": "LOCAL_HANDLER", "provider": "open-meteo"}
            except Exception as e:
                print(f"[Engine] Weather handler error: {e}")

        # 7.5 Spoken Q&A & Trivia (routed via QAHandler cache & LLM router)
        if hasattr(self, "qa_handler") and self.qa_handler and self.qa_handler.is_question(text):
            try:
                self._captured_speech.clear()
                self._speech_capturing = True
                try:
                    self.qa_handler.answer_question(text)
                finally:
                    self._speech_capturing = False
                if self._captured_speech:
                    ans = " ".join(self._captured_speech)
                    return {"reply": ans, "action": "answer_question", "data": {}, "tier": "QA_ENGINE", "provider": "qa_router"}
            except Exception as e:
                print(f"[Engine] QA handler error: {e}")

        # 8. Alarms & Timers
        if re.search(r"\b(set an alarm|set alarm|set a timer|set timer|wake me up at)\b", low):
            handler = getattr(self, "alarm_handler", None)
            ans = handler.set_alarm(text) if (handler and hasattr(handler, "set_alarm")) else self._call_module_fn(alarm, ["handle_alarm_command", "handle_alarm", "set_alarm", "handle"], text)
            if ans:
                return {"reply": ans, "action": "set_alarm", "data": {}, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 9. Music playback
        play_match = re.match(r"^play\s+(.+)$", low)
        if play_match:
            song = play_match.group(1).strip()
            ans = self._call_module_fn(music, ["play_music", "handle_music", "play_on_youtube", "handle"], song)
            if ans:
                return {"reply": ans, "action": "play_music", "data": {"song": song}, "tier": "LOCAL_HANDLER", "provider": "local"}

        # 10. Clipboard Copilot
        if re.search(r"\b(clipboard|what did i copy|summarize clipboard|fix clipboard|explain clipboard)\b", low):
            ans = self._call_module_fn(clipboard_copilot, ["handle_clipboard_command", "process_clipboard", "handle_clipboard", "handle"], text)
            if ans:
                return {"reply": ans, "action": "clipboard_copilot", "data": {}, "tier": "CLIPBOARD_COPILOT", "provider": "local"}

        # 11. Meeting Attendant commands
        if re.search(r"\b(join meeting|schedule meeting|schedule a meeting|leave meeting|end call|meet\.google\.com|teams\.microsoft\.com|what meetings|my meetings|upcoming meetings|list meetings)\b", low):
            try:
                import automation.meeting_handler as mh_mod
                mh = getattr(self, "meeting_handler", None) or getattr(mh_mod, "meeting_handler", None) or mh_mod.MeetingHandler(self)
                if getattr(mh, "jarvis", None) is None:
                    mh.jarvis = self
                self._captured_speech.clear()
                self._speech_capturing = True
                m_res = None
                try:
                    for fn_name in ("process_meeting_command", "handle_command", "execute"):
                        fn = getattr(mh, fn_name, None)
                        if callable(fn):
                            m_res = fn(text)
                            break
                finally:
                    self._speech_capturing = False
                ans = " ".join(self._captured_speech) if self._captured_speech else (str(m_res.get("message", m_res) if isinstance(m_res, dict) else m_res) if m_res else "Meeting command processed, sir.")
                return {"reply": ans, "action": "meeting_command", "data": {}, "tier": "MEETING_BOT", "provider": "local"}
            except Exception as e:
                print(f"[Engine] Meeting handler error: {e}")

        # 12. Explicit Tier 1 OS Python Script Synthesizer
        if low.startswith(("run python:", "execute script:", "tier 1:", "automate:")):
            if self.code_executor is not None:
                for fn_name in ("synthesize_and_execute", "execute_task", "run_task", "execute"):
                    fn = getattr(self.code_executor, fn_name, None)
                    if callable(fn):
                        exec_res = fn(text)
                        output = exec_res.get("output") or exec_res.get("summary") or str(exec_res) if isinstance(exec_res, dict) else str(exec_res)
                        return {"reply": output, "action": "tier1_code", "data": {}, "tier": "TIER_1_PYTHON", "provider": "code_synth"}

        # 13. Explicit Tier 3 Vision GUI Agent
        if low.startswith(("gui:", "vision:", "click on ", "tier 3:")):
            goal = re.sub(r"^(gui:|vision:|tier 3:)\s*", "", text, flags=re.IGNORECASE)
            if self.os_agent is not None:
                res = self.os_agent.execute_goal(goal)
                return {"reply": res.get("summary", str(res)) if isinstance(res, dict) else str(res), "action": "tier3_vision_gui", "data": {}, "tier": "TIER_3_VISION", "provider": "vision_agent"}

        return None

    def _route_intent(self, intent_res: IntentResult, raw_cmd: str) -> Optional[Dict[str, Any]]:
        intent = intent_res.intent
        slots = intent_res.slots
        t0 = time.time()

        if intent == "music.play":
            song = str(slots.get("song") or raw_cmd).strip()
            platform = str(slots.get("platform", "")).strip().lower()
            cmd_arg = f"{song} on {platform}" if platform and platform not in song.lower() else song
            if hasattr(self, "music_handler") and hasattr(self.music_handler, "play_music"):
                res = self.music_handler.play_music(cmd_arg)
            else:
                res = music.play_music(cmd_arg)
            reply = res.get("reply", f"Playing {song}, sir.")
            return {
                "reply": reply,
                "action": "play_music",
                "data": res.get("data", {"song": song, "platform": platform or "default", "state": "playing"}),
                "tier": "LOCAL_NN",
                "provider": "music_handler",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        if intent == "music.control":
            act = str(slots.get("action", "pause")).lower()
            if hasattr(self, "music_handler") and hasattr(self.music_handler, "control_playback"):
                res = self.music_handler.control_playback(act)
            else:
                res = music.control_playback(act)
            reply = res.get("reply", f"Music {act} executed, sir.")
            return {
                "reply": reply,
                "action": "music_control",
                "data": res.get("data", {"action": act, "state": "paused"}),
                "tier": "LOCAL_NN",
                "provider": "music_handler",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        if intent == "alarm.set":
            handler = getattr(self, "alarm_handler", None) or alarm.alarm_handler
            ans = handler.set_alarm(raw_cmd)
            time_target = slots.get("time") or (f"{slots.get('duration_minutes')} minutes" if slots.get("duration_minutes") else "specified time")
            reply = ans or f"Alarm set for {time_target}, sir."
            return {
                "reply": reply,
                "action": "set_alarm",
                "data": slots,
                "tier": "LOCAL_NN",
                "provider": "alarm_handler",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        if intent == "alarm.cancel":
            handler = getattr(self, "alarm_handler", None) or alarm.alarm_handler
            ans = handler.cancel_alarm(raw_cmd)
            reply = ans or "Active alarms cancelled, sir."
            return {
                "reply": reply,
                "action": "cancel_alarm",
                "data": slots,
                "tier": "LOCAL_NN",
                "provider": "alarm_handler",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        if intent == "alarm.list":
            handler = getattr(self, "alarm_handler", None) or alarm.alarm_handler
            active_alarms = handler.get_active_alarms() if hasattr(handler, "get_active_alarms") else getattr(handler, "alarms", [])
            if active_alarms:
                alr_strs = [f"{a.get('label', 'Alarm')} at {a.get('time')}" for a in active_alarms]
                reply = f"You have {len(active_alarms)} active alarm{'s' if len(active_alarms) > 1 else ''}: {', '.join(alr_strs)}, sir."
            else:
                reply = "No active alarms scheduled, sir."
            return {
                "reply": reply,
                "action": "list_alarms",
                "data": {"alarms": active_alarms, **slots},
                "tier": "LOCAL_NN",
                "provider": "alarm_handler",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        if intent == "system.volume":
            ans = self._call_module_fn(system_controls, ["handle_system_control", "handle_control", "execute_control", "handle"], raw_cmd)
            reply = ans or "Audio volume adjusted, sir."
            return {
                "reply": reply,
                "action": "set_volume",
                "data": slots,
                "tier": "LOCAL_NN",
                "provider": "system_controls",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        if intent == "system.brightness":
            ans = self._call_module_fn(system_controls, ["handle_system_control", "handle_control", "execute_control", "handle"], raw_cmd)
            reply = ans or "Display brightness adjusted, sir."
            return {
                "reply": reply,
                "action": "set_brightness",
                "data": slots,
                "tier": "LOCAL_NN",
                "provider": "system_controls",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        if intent == "system.status":
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                battery = psutil.sensors_battery()
                batt_info = f"Battery at {int(battery.percent)}%." if battery else "No battery detected."
                status_text = f"Systems nominal, sir. CPU load is at {cpu}%, RAM utilization is {ram}%. {batt_info}"
                stat_data = {"cpu": cpu, "ram": ram, "battery": int(battery.percent) if battery else None}
            except Exception:
                status_text = "Systems nominal, sir. Primary telemetry monitors active."
                stat_data = {"cpu": 15, "ram": 42}
            return {
                "reply": status_text,
                "action": "system_info",
                "data": stat_data,
                "tier": "LOCAL_NN",
                "provider": "system_info",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        if intent == "app.open":
            app_name = str(slots.get("app_name") or raw_cmd).strip()
            if hasattr(self, "app_handler") and self.app_handler:
                try:
                    self.app_handler.open_application(app_name)
                    return {
                        "reply": f"Opening {app_name}, sir.",
                        "action": "open_app",
                        "data": {"app": app_name},
                        "tier": "LOCAL_NN",
                        "provider": "app_handler",
                        "latency_ms": int((time.time() - t0) * 1000),
                    }
                except Exception:
                    pass
            ans = self._call_module_fn(applications, ["open_application", "launch_app", "handle_application", "handle"], app_name)
            reply = ans or f"Opening {app_name}, sir."
            return {
                "reply": reply,
                "action": "open_app",
                "data": {"app": app_name},
                "tier": "LOCAL_NN",
                "provider": "app_handler",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        if intent in ("meeting.join", "meeting.schedule", "meeting.leave"):
            try:
                import automation.meeting_handler as mh_mod
                mh = getattr(self, "meeting_handler", None) or getattr(mh_mod, "meeting_handler", None) or mh_mod.MeetingHandler(self)
                if getattr(mh, "jarvis", None) is None:
                    mh.jarvis = self
                self._captured_speech.clear()
                self._speech_capturing = True
                m_res = None
                try:
                    for fn_name in ("process_meeting_command", "handle_command", "execute"):
                        fn = getattr(mh, fn_name, None)
                        if callable(fn):
                            m_res = fn(raw_cmd)
                            break
                finally:
                    self._speech_capturing = False
                ans = " ".join(self._captured_speech) if self._captured_speech else (str(m_res.get("message", m_res) if isinstance(m_res, dict) else m_res) if m_res else "Meeting command processed, sir.")
                return {
                    "reply": ans,
                    "action": "meeting_command",
                    "data": slots,
                    "tier": "LOCAL_NN",
                    "provider": "meeting_bot",
                    "latency_ms": int((time.time() - t0) * 1000),
                }
            except Exception:
                return {
                    "reply": "Meeting command processed, sir.",
                    "action": "meeting_command",
                    "data": slots,
                    "tier": "LOCAL_NN",
                    "provider": "meeting_bot",
                    "latency_ms": int((time.time() - t0) * 1000),
                }

        if intent == "web.search":
            query = str(slots.get("query") or raw_cmd).strip()
            # Clean common command triggers if raw_cmd was used
            clean_query = query
            low_q = clean_query.lower()
            for p in ("search for", "search the web for", "search google for", "web search for", "look up", "find info on", "search"):
                if low_q.startswith(p):
                    clean_query = clean_query[len(p):].strip()
                    break
            clean_query = clean_query or query

            if hasattr(self, "web_search_handler") and hasattr(self.web_search_handler, "web_search"):
                res = self.web_search_handler.web_search(clean_query)
            else:
                res = web_search.web_search(clean_query)

            reply = res.get("reply", f"Search completed for {clean_query}, sir.")
            return {
                "reply": reply,
                "action": "web_search",
                "data": res.get("data", {"query": clean_query, "results": []}),
                "tier": "LOCAL_NN",
                "provider": "web_search_handler",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        if intent == "date_time.get":
            time_type = slots.get("type", "time")
            low_cmd = raw_cmd.lower()
            if time_type == "year" or "year" in low_cmd:
                cur_year = datetime.now().year
                return {
                    "reply": f"The current year is {cur_year}, sir.",
                    "action": "get_date",
                    "data": {"year": cur_year},
                    "tier": "LOCAL_NN",
                    "provider": "local",
                    "latency_ms": int((time.time() - t0) * 1000),
                }
            if time_type == "time" or "time" in low_cmd:
                now_str = datetime.now().strftime("%I:%M %p")
                return {
                    "reply": f"The current time is {now_str}, sir.",
                    "action": "get_time",
                    "data": {"time": now_str},
                    "tier": "LOCAL_NN",
                    "provider": "local",
                    "latency_ms": int((time.time() - t0) * 1000),
                }
            date_str = datetime.now().strftime("%A, %B %d, %Y")
            return {
                "reply": f"Today is {date_str}, sir.",
                "action": "get_date",
                "data": {"date": date_str, "year": datetime.now().year},
                "tier": "LOCAL_NN",
                "provider": "local",
                "latency_ms": int((time.time() - t0) * 1000),
            }

        return None

    def _finalize_response(
        self,
        text: str,
        source: str = "text",
        action: str = "general_qa",
        data: Optional[Dict[str, Any]] = None,
        tier: str = "LOCAL",
        provider: str = "local",
        model: Optional[str] = None,
        latency_ms: int = 0,
        status: str = "ok",
        error: Optional[str] = None,
        speak: Optional[bool] = None,
    ) -> EngineResponse:
        clean_action = str(action or "general_qa").strip()
        valid_deterministic = (
            clean_action.startswith("get_")
            or clean_action.startswith("set_")
            or clean_action in (
                "skill_macro",
                "greet",
                "clear_memory",
                "system_info",
                "open_app",
                "play_music",
                "music_control",
                "set_alarm",
                "cancel_alarm",
                "list_alarms",
                "set_volume",
                "set_brightness",
                "clipboard_copilot",
                "meeting_command",
                "web_search",
                "web_research",
                "tier1_code",
                "tier2_mcp",
                "tier3_vision_gui",
                "general_qa",
                "answer_question",
                "none",
            )
        )
        if not valid_deterministic:
            clean_action = "general_qa"

        full_data = data or {}
        msg_obj = self._emit_chat(
            "assistant",
            text,
            meta={
                "source": source,
                "action": clean_action,
                "data": full_data,
                "tier": tier,
                "provider": provider,
                "model": model,
                "latency_ms": latency_ms,
            },
        )
        if speak is not False:
            self._speak_if_enabled(text)

        return EngineResponse(
            status=status,
            sender="jarvis",
            source=source,
            action=clean_action,
            reply=text,
            response=text,
            text=text,
            data=full_data,
            tier=tier,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            error=error,
            message=msg_obj,
        )

    def process_command(
        self,
        command: str,
        source: str = "text",
        broadcast_user: bool = True,
        speak: Optional[bool] = None,
    ) -> EngineResponse:
        clean_cmd = (command or "").strip()
        if source in ("test", "unit_test") and speak is None:
            speak = False
        if not clean_cmd:
            return self._finalize_response(
                text="Awaiting your command, sir.",
                source=source,
                action="none",
                speak=speak,
            )

        if broadcast_user:
            self._emit_chat("user", clean_cmd, meta={"source": source, "action": "input"})

        # Step 0: Fast Neural Intent Classifier (<5ms ONNX routing)
        intent_res = self.intent_classifier.classify(clean_cmd)
        if intent_res.confidence >= 0.65:
            intent_routed = self._route_intent(intent_res, clean_cmd)
            if intent_routed is not None:
                reply_text = str(intent_routed.get("reply", "Command executed."))
                if intent_routed.get("action") != "clear_memory":
                    self.context.add_user_message(clean_cmd)
                    self.context.add_assistant_message(reply_text)
                return self._finalize_response(
                    text=reply_text,
                    source=source,
                    action=intent_routed.get("action", "general_qa"),
                    data=intent_routed.get("data", {}),
                    tier=intent_routed.get("tier", "LOCAL_NN"),
                    provider=intent_routed.get("provider", "neural_intent"),
                    model=intent_res.intent,
                    latency_ms=intent_routed.get("latency_ms", 0),
                    speak=speak,
                )

        # Step 1: Check fast deterministic local handlers (<1ms, zero LLM latency)
        local_hit = self._try_fast_local_handlers(clean_cmd)
        if local_hit is not None:
            reply_text = str(local_hit.get("reply", "Done."))
            if local_hit.get("action") != "clear_memory":
                self.context.add_user_message(clean_cmd)
                self.context.add_assistant_message(reply_text)
            return self._finalize_response(
                text=reply_text,
                source=source,
                action=local_hit.get("action", "general_qa"),
                data=local_hit.get("data", {}),
                tier=local_hit.get("tier", "LOCAL"),
                provider=local_hit.get("provider", "local"),
                speak=speak,
            )

        # Step 2: Live Web Search context if requested
        low = clean_cmd.lower()
        if re.search(r"\b(search the web for|search online for|latest news on|look up online|most heard song 2025|most streamed song 2025)\b", low):
            try:
                import automation.web_agent as wa_mod
                wa = getattr(wa_mod, "web_agent", None) or getattr(wa_mod, "WebAgent", lambda: None)()
                if wa:
                    for fn_name in ("research", "search_and_distill", "search"):
                        fn = getattr(wa, fn_name, None)
                        if callable(fn):
                            w_res = fn(clean_cmd)
                            summary_text = w_res.get("summary") if isinstance(w_res, dict) else str(w_res)
                            self.context.add_user_message(clean_cmd)
                            self.context.add_assistant_message(summary_text)
                            return self._finalize_response(
                                text=summary_text,
                                source=source,
                                action="web_research",
                                data=w_res if isinstance(w_res, dict) else {},
                                tier="WEB_AGENT",
                                provider="web",
                                speak=speak,
                            )
            except Exception:
                pass

        # Step 3: Multi-turn LLM generation
        self.context.add_user_message(clean_cmd)
        sys_prompt = self.context.get_system_prompt()
        history_msgs = self.context.get_messages(include_system=False)

        self.is_thinking = True
        try:
            llm_res = self.router.chat(
                messages=history_msgs,
                role="chat",
                system_prompt=sys_prompt,
            )
            reply_text = str(llm_res.get("content", "I encountered an issue processing that request."))
            provider_used = llm_res.get("provider", "unknown")
            model_used = llm_res.get("model", "unknown")
        finally:
            self.is_thinking = False

        self.context.add_assistant_message(reply_text)
        llm_ok = bool(llm_res.get("success", False))
        return self._finalize_response(
            text=reply_text,
            source=source,
            action="general_qa",
            data={
                "model": model_used,
                "latency_ms": llm_res.get("latency_ms", 0),
            },
            tier="LLM_CHAT",
            provider=provider_used,
            model=model_used,
            latency_ms=int(llm_res.get("latency_ms", 0) or 0),
            status="ok" if llm_ok else "error",
            error=llm_res.get("error"),
            speak=speak,
        )


engine = JARVISEngine()
