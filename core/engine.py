#!/usr/bin/env python3
"""
JARVIS Core Engine & Unified Input Gateway
Orchestrates command processing across local rules, scheduled meeting automation,
Gemini NLP classification, and Groq conversational Q&A.
"""

import os
import random
import re
import socket
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

# Configuration
from config.settings import (
    WEATHER_API_KEY,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    GROQ_MODEL,
    GEMINI_MODEL,
    JARVIS_FORCE_ONLINE,
)

# TTS Engine
from core.tts_engine import TTSEngine

# Handlers
from handlers.date_time import DateTimeHandler
from handlers.applications import ApplicationHandler
from handlers.music import MusicHandler
from handlers.web_search import WebSearchHandler
from handlers.alarm import AlarmHandler
from handlers.weather import WeatherHandler
from handlers.system_controls import SystemControls
from handlers.system_info import SystemInfoHandler
from handlers.qa_handler import QAHandler

# Automation
from automation.meeting_handler import MeetingHandler

# Optional Gemini
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class JARVISEngine:
    """
    Central JARVIS Assistant Orchestrator.
    Implements the InputGateway pattern for unified text and voice command routing.
    """

    AVAILABLE_COMMANDS = """
Available commands:
1. get_time - Tell current time
2. get_date - Tell today's date
3. open_app - Open an application (chrome, notepad, spotify, etc.)
4. play_music - Play/control music. Play: "song name on spotify/youtube". Control: "pause", "next", "previous"
5. web_search - Search Google for information (facts, people, news, etc.)
6. set_alarm - Set an alarm/reminder (pass "cancel" in params to stop/cancel alarms)
7. get_weather - Get weather for a city
8. exit - Shutdown JARVIS completely
9. sleep - Put JARVIS into sleep/standby mode
10. conversation - General chat/greeting
11. set_volume - Set system volume (0-100) or mute/unmute
12. set_brightness - Set screen brightness (0-100)
13. set_timer - Set a countdown timer
14. stopwatch - Start/stop a stopwatch
15. get_system_info - Get system diagnostics (battery, CPU, RAM)
16. answer_question - Answer factual/conversational questions
17. meeting_command - Meeting management: schedule/list/cancel/join/leave meetings, open meeting dashboard. Params: user command text.

Respond in this exact format:
COMMAND: <command_name>
PARAMS: <parameters if any>
RESPONSE: <what JARVIS should say>
"""

    def __init__(self, tts_engine: Optional[TTSEngine] = None):
        self.tts_engine = tts_engine or TTSEngine(enabled=True)
        self.weather_api_key = WEATHER_API_KEY
        self.gemini_api_key = GEMINI_API_KEY
        self.groq_api_key = GROQ_API_KEY

        # State flags
        self.is_sleeping = False
        self.running = True

        # Thread-local storage for capturing spoken response during execution
        self._execution_lock = threading.Lock()
        self._current_responses: List[str] = []

        # Conversation memory
        self.conversation_memory: List[Dict[str, str]] = []
        self.max_memory = 6

        # Iron Man flair acknowledgments
        self.ack_phrases = [
            "Right away, sir.",
            "Consider it done, sir.",
            "Working on it, sir.",
            "As you wish, sir.",
            "At once, sir.",
            "Right on it, sir.",
        ]

        # Initialize AI Client if available
        self.genai_client = None
        self.ai_model = None
        self._init_ai()

        # Initialize Handlers
        self.datetime_handler = DateTimeHandler(self)
        self.app_handler = ApplicationHandler(self)
        self.music_handler = MusicHandler(self)
        self.web_handler = WebSearchHandler(self)
        self.alarm_handler = AlarmHandler(self)
        self.weather_handler = WeatherHandler(self, self.weather_api_key)
        self.system_controls = SystemControls(self)
        self.system_info_handler = SystemInfoHandler(self)
        self.qa_handler = QAHandler(self)
        self.meeting_handler = MeetingHandler(self)

    # ── AI Client Init ────────────────────────────────────────────────
    def _init_ai(self):
        if not GEMINI_AVAILABLE:
            return
        if not self.gemini_api_key:
            return
        try:
            self.genai_client = genai.Client(api_key=self.gemini_api_key)
            self.ai_model = GEMINI_MODEL or "gemini-2.5-flash"
        except Exception as e:
            print(f"[Engine] Gemini init error: {e}")

    # ── Speech Output & Response Interception ────────────────────────
    def speak(self, text: str, wait: bool = False):
        """
        Output speech through TTSEngine and record it into the active execution transaction.
        """
        if not text:
            return

        print(f"JARVIS: {text}")
        # Capture into current execution accumulator
        self._current_responses.append(text)

        # Forward to TTSEngine
        if self.tts_engine:
            self.tts_engine.speak(text, wait=wait)

        # Add to conversational memory
        if not any(skip in text.lower() for skip in ['listening', 'processing', "couldn't understand"]):
            self.add_to_memory('assistant', text)

    def add_to_memory(self, role: str, content: str):
        self.conversation_memory.append({'role': role, 'content': content})
        if len(self.conversation_memory) > self.max_memory * 2:
            self.conversation_memory = self.conversation_memory[-self.max_memory * 2:]

    def get_memory_context(self) -> str:
        if not self.conversation_memory:
            return ""
        lines = ["\nRecent conversation:"]
        for msg in self.conversation_memory[-4:]:
            role = "User" if msg['role'] == 'user' else "JARVIS"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)

    def is_online(self) -> bool:
        """Fast connectivity check."""
        if JARVIS_FORCE_ONLINE:
            return True
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=1.5)
            return True
        except (socket.timeout, OSError):
            return False

    # ── Unified InputGateway ──────────────────────────────────────────
    def execute_command(self, query: str, source: str = "text") -> Dict[str, Any]:
        """
        Single ingestion entry point for both text and voice commands.
        Processes in strict priority order:
          1. Local regex / keywords
          2. Scheduled meeting intents
          3. Gemini / Groq intent classification
          4. Groq general Q&A
        Returns structured dict:
          {"status": "ok"|"error", "query": query, "response": str, "source": source, "action": str}
        """
        if not query or not query.strip():
            return {
                "status": "ok",
                "query": query,
                "response": "How can I assist you, sir?",
                "source": source,
                "action": "empty",
            }

        cleaned = query.strip()
        command = cleaned.lower()
        self.add_to_memory('user', cleaned)

        with self._execution_lock:
            self._current_responses = []
            action = "unknown"
            status = "ok"

            try:
                # ── STEP 1: Local Regex / Keywords ────────────────────
                matched_local, action_name = self._match_local_command(command, cleaned)
                if matched_local:
                    action = action_name
                else:
                    # ── STEP 2: Scheduled Meeting Intents ──────────────
                    matched_meeting, action_name = self._match_meeting_command(command, cleaned)
                    if matched_meeting:
                        action = action_name
                    else:
                        # ── STEP 3: Gemini / Groq Intent Classification ─
                        matched_ai, action_name = self._match_ai_classification(command, cleaned)
                        if matched_ai:
                            action = action_name
                        else:
                            # ── STEP 4: Groq General Q&A ───────────────
                            matched_qa, action_name = self._match_qa(command, cleaned)
                            if matched_qa:
                                action = action_name
                            else:
                                self.speak("I'm not sure how to help with that, sir. Try asking for the time, date, weather, or to open an application.")
                                action = "unknown"

            except Exception as e:
                status = "error"
                action = "error"
                print(f"[InputGateway Error] {e}")
                self.speak(f"My apologies, sir. An error occurred while processing that request: {e}")

            # Assemble response string from accumulated spoken sentences
            if self._current_responses:
                response_text = " ".join(self._current_responses)
            else:
                response_text = "Command executed, sir."

            return {
                "status": status,
                "query": cleaned,
                "response": response_text,
                "source": source,
                "action": action,
            }

    # ── Step 1: Local Command Matcher ─────────────────────────────────
    def _match_local_command(self, command: str, original: str) -> tuple[bool, str]:
        # Exit
        if any(command == w for w in ['exit', 'quit', 'shutdown', 'goodbye']):
            self.speak("Goodbye, sir. JARVIS shutting down.")
            self.running = False
            return True, "exit"

        # Sleep
        if any(w in command for w in ['sleep', 'stand by', 'stand down', 'go to sleep']):
            self.is_sleeping = True
            self.speak("Standing down, sir. Let me know when you need me.")
            return True, "sleep"

        # Wakeup / Greeting
        if any(command == w for w in ['wake up', 'jarvis', 'hello', 'hi', 'hey', 'how are you']):
            self.is_sleeping = False
            self._cmd_greet()
            return True, "greet"

        # Time
        if any(p in command for p in ['what time is it', "what's the time", 'current time', 'tell me the time', 'time please']) or command == 'time':
            self._cmd_time()
            return True, "get_time"

        # Date
        if any(p in command for p in ["what's the date", 'what is the date', "today's date", 'what day is it', 'tell me the date']) or command == 'date':
            self._cmd_date()
            return True, "get_date"

        # Open Application
        if command.startswith('open '):
            self._cmd_open_app(command)
            return True, "open_app"

        # Music Controls
        if any(word in command for word in ['pause', 'resume', 'continue', 'stop']) and any(m in command for m in ['music', 'song', 'playback']):
            self._cmd_music_control(command)
            return True, "music_control"
        if any(word in command for word in ['next song', 'skip song', 'previous song', 'back song']):
            self._cmd_music_control(command)
            return True, "music_control"

        # Play Music
        if command.startswith('play '):
            self._cmd_play_music(command)
            return True, "play_music"

        # Weather
        if command.startswith(('weather', "what's the weather", 'how is the weather', 'whats the weather', 'what is the weather')):
            self._cmd_weather(command)
            return True, "get_weather"

        # Web Search
        if command.startswith(('search ', 'look up ', 'find ')):
            self._cmd_search(command)
            return True, "web_search"

        # Alarm
        if command.startswith(('alarm', 'remind', 'set alarm', 'set a reminder')):
            self._cmd_alarm(command)
            return True, "set_alarm"

        # Volume
        if any(word in command for word in ['volume', 'mute', 'unmute']):
            self._cmd_volume(command)
            return True, "set_volume"

        # Brightness
        if any(word in command for word in ['brightness', 'dim screen', 'brighten screen']):
            self._cmd_brightness(command)
            return True, "set_brightness"

        # Timer
        if 'timer' in command:
            self._cmd_timer(command)
            return True, "set_timer"

        # Stopwatch
        if any(word in command for word in ['stopwatch', 'stop watch']):
            self._cmd_stopwatch(command)
            return True, "stopwatch"

        # System info / diagnostics
        if any(w in command for w in ['system status', 'system info', 'diagnostics', 'battery', 'cpu usage']):
            self._cmd_system_info(command)
            return True, "get_system_info"

        return False, ""

    # ── Step 2: Meeting Commands Matcher ──────────────────────────────
    def _match_meeting_command(self, command: str, original: str) -> tuple[bool, str]:
        meeting_keywords = [
            'schedule meeting', 'schedule a meeting', 'schedule team',
            'meetings today', 'what meetings do i have', 'list my meetings', 'list meetings',
            'cancel meeting', 'cancel my next meeting',
            'join meeting', 'join the meeting', 'leave meeting', 'leave the meeting',
            'open schedule', 'open dashboard', 'meeting dashboard',
            'meet.google.com', 'teams.microsoft.com'
        ]
        if any(kw in command for kw in meeting_keywords) or (('meeting' in command or 'meetings' in command) and any(w in command for w in ['schedule', 'join', 'leave', 'cancel', 'list', 'show'])):
            self._cmd_meeting(original)
            return True, "meeting_command"
        return False, ""

    # ── Step 3: AI NLP Intent Classification ──────────────────────────
    def _match_ai_classification(self, command: str, original: str) -> tuple[bool, str]:
        # Try Groq classification first, then Gemini
        success, cmd_name = self._process_with_ai(original)
        if success:
            return True, cmd_name or "ai_classified"
        return False, ""

    # ── Step 4: Groq / Gemini Q&A Matcher ─────────────────────────────
    def _match_qa(self, command: str, original: str) -> tuple[bool, str]:
        if self.qa_handler.is_question(command):
            self.qa_handler.answer_question(original)
            return True, "answer_question"
        return False, ""

    # ── Local Action Execution Helpers ────────────────────────────────
    def _cmd_time(self):
        self.datetime_handler.tell_time()

    def _cmd_date(self):
        self.datetime_handler.tell_date()

    def _cmd_greet(self):
        hour = datetime.now().hour
        if 5 <= hour < 12:
            greet = "Good morning, sir. All systems are online."
        elif 12 <= hour < 17:
            greet = "Good afternoon, sir. How can I assist?"
        elif 17 <= hour < 22:
            greet = "Good evening, sir. Ready when you are."
        else:
            greet = "Working late, sir? Systems operational."
        self.speak(greet)

    def _cmd_open_app(self, command: str):
        self.app_handler.open_application(command)

    def _cmd_play_music(self, command: str):
        self.music_handler.play_music(command)

    def _cmd_music_control(self, command: str):
        self.music_handler.process_control_command(command)

    def _cmd_weather(self, command: str):
        self.weather_handler.process_weather_command(command)

    def _cmd_search(self, command: str):
        self.web_handler.web_search(command)

    def _cmd_alarm(self, command: str):
        self.alarm_handler.set_alarm(command)

    def _cmd_volume(self, command: str):
        self.system_controls.set_volume(command)

    def _cmd_brightness(self, command: str):
        self.system_controls.set_brightness(command)

    def _cmd_timer(self, command: str):
        self.system_controls.set_timer(command)

    def _cmd_stopwatch(self, command: str):
        if 'stop' in command:
            self.system_controls.stop_stopwatch()
        else:
            self.system_controls.start_stopwatch()

    def _cmd_system_info(self, command: str):
        stats = self.system_info_handler.get_quick_stats()
        parts = [f"CPU is at {stats['cpu']} percent."]
        if stats.get('battery') is not None:
            plugged = "plugged in" if stats.get('plugged_in') else "on battery"
            parts.append(f"Battery is at {stats['battery']} percent and {plugged}.")
        self.speak(" ".join(parts))

    def _cmd_meeting(self, command: str):
        self.meeting_handler.process_meeting_command(command)

    # ── AI Processing ─────────────────────────────────────────────────
    def _process_with_ai(self, command: str) -> tuple[bool, str]:
        """Attempt Groq classification; fallback to Gemini."""
        if hasattr(self, 'qa_handler') and self.qa_handler.groq_client:
            success, cmd = self._process_with_groq(command)
            if success:
                return True, cmd

        if self.ai_model and self.genai_client:
            return self._process_with_gemini(command)
        return False, ""

    def _process_with_groq(self, command: str) -> tuple[bool, str]:
        prompt = f"{self.AVAILABLE_COMMANDS}{self.get_memory_context()}\nUser: {command}\n"
        candidate_models = [GROQ_MODEL, "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "allam-2-7b"]
        for m in candidate_models:
            try:
                response = self.qa_handler.groq_client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": "You are a command classifier for JARVIS. Follow the exact output format specified."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=200,
                )
                return self._handle_ai_response(response.choices[0].message.content, command)
            except Exception as e:
                err_str = str(e).lower()
                if "model_not_found" in err_str or "does not exist" in err_str:
                    continue
                return False, ""
        return False, ""

    def _process_with_gemini(self, command: str) -> tuple[bool, str]:
        prompt = f"{self.AVAILABLE_COMMANDS}{self.get_memory_context()}\nUser: {command}\n"
        gemini_candidates = [self.ai_model, "gemini-2.5-flash", "gemini-3.8-flash", "gemini-flash-latest"]
        for g_model in [m for m in gemini_candidates if m]:
            try:
                response = self.genai_client.models.generate_content(
                    model=g_model,
                    contents=prompt,
                    config={'temperature': 0.3, 'max_output_tokens': 200}
                )
                return self._handle_ai_response(response.text, command)
            except Exception as e:
                err_str = str(e).lower()
                if "not found" in err_str or "404" in err_str:
                    continue
                return False, ""
        return False, ""

    def _handle_ai_response(self, text: str, command: str) -> tuple[bool, str]:
        cmd, params, resp = None, "", ""
        for line in text.strip().split('\n'):
            line = line.strip()
            if line.startswith('COMMAND:'):
                cmd = line.replace('COMMAND:', '').strip()
            elif line.startswith('PARAMS:'):
                params = line.replace('PARAMS:', '').strip()
            elif line.startswith('RESPONSE:'):
                resp = line.replace('RESPONSE:', '').strip()

        if not cmd:
            return False, ""

        if resp and cmd != 'answer_question':
            if cmd in ['open_app', 'play_music', 'set_alarm', 'set_timer'] and random.random() < 0.4:
                resp = random.choice(self.ack_phrases) + " " + resp
            self.speak(resp)

        if cmd and cmd != 'conversation':
            self._execute_ai_command(cmd, params, command)

        return True, cmd

    def _execute_ai_command(self, cmd: str, params: str, original_command: str):
        try:
            if cmd == 'get_time':
                self.datetime_handler.tell_time()
            elif cmd == 'get_date':
                self.datetime_handler.tell_date()
            elif cmd == 'open_app':
                self.app_handler.open_application(f"open {params}")
            elif cmd == 'play_music':
                self.music_handler.play_music(f"play {params}")
            elif cmd == 'web_search':
                self.web_handler.web_search(f"search {params}")
            elif cmd == 'set_alarm':
                self.alarm_handler.set_alarm(f"set alarm for {params}")
            elif cmd == 'get_weather':
                self.weather_handler.process_weather_command(original_command)
            elif cmd == 'set_volume':
                self.system_controls.set_volume(params)
            elif cmd == 'set_brightness':
                self.system_controls.set_brightness(params)
            elif cmd == 'set_timer':
                self.system_controls.set_timer(params)
            elif cmd == 'stopwatch':
                self.system_controls.start_stopwatch()
            elif cmd == 'get_system_info':
                self._cmd_system_info(original_command)
            elif cmd == 'meeting_command':
                self.meeting_handler.process_meeting_command(original_command)
            elif cmd == 'answer_question':
                self.qa_handler.answer_question(original_command)
        except Exception as e:
            print(f"[AI Exec Error] {e}")
