#!/usr/bin/env python3
"""
JARVIS Core - Simplified Hybrid Architecture
Direct matching first, fallback to LLM
"""

import os
import asyncio
import tempfile
import speech_recognition as sr
import pyttsx3
import time
import threading
import random
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try to import edge-tts (neural TTS — primary voice engine)
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    print("Note: edge-tts not installed. Using pyttsx3 for speech.")

# Try to import pygame for audio playback
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("Note: pygame not installed. Audio playback may be unavailable.")

# Try to import noisereduce for pre-Whisper audio cleanup
try:
    import noisereduce as nr
    import numpy as np
    NOISEREDUCE_AVAILABLE = True
except ImportError:
    NOISEREDUCE_AVAILABLE = False

# Import handlers
from date_time import DateTimeHandler
from applications import ApplicationHandler
from music import MusicHandler
from web_search import WebSearchHandler
from alarm import AlarmHandler
from weather import WeatherHandler
from system_controls import SystemControls
from system_info import SystemInfoHandler
from qa_handler import QAHandler

# Try to import Gemini (new SDK)
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Note: google-genai not installed. AI features disabled.")


class JARVIS:
    """JARVIS Assistant - Simplified Hybrid Mode"""

    # List of all available commands for LLM
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
9. sleep - Put JARVIS into sleep/standby mode (user says 'sleep', 'stand by', 'go to sleep', 'stand down')
10. conversation - General chat/greeting (no action needed)
11. set_volume - Set system volume (0-100) or mute/unmute
12. set_brightness - Set screen brightness (0-100)
13. set_timer - Set a countdown timer (pass "cancel" in params to stop/cancel timers)
14. stopwatch - Start/stop a stopwatch
15. get_system_info - Get system diagnostics (battery, CPU, RAM, temperature, internet speed, disk space)
16. answer_question - Answer a factual/conversational question directly (who is X, what is Y, define Z, explain Z, why X). Put the ACTUAL ANSWER in the RESPONSE field — do not say "let me find that". Answer concisely in 1-2 sentences, addressing the user as sir.

Respond in this exact format:
COMMAND: <command_name>
PARAMS: <parameters if any>
RESPONSE: <what JARVIS should say>

Examples:
User: "What's the time?"
COMMAND: get_time
PARAMS: none
RESPONSE: The current time is 3:45 PM, sir.

User: "Open Chrome"
COMMAND: open_app
PARAMS: chrome
RESPONSE: Opening Chrome, sir.

User: "What's the weather in London?"
COMMAND: get_weather
PARAMS: London
RESPONSE: Let me check the weather in London for you, sir.

User: "Who is the CEO of Google?"
COMMAND: answer_question
PARAMS: none
RESPONSE: The CEO of Google is Sundar Pichai, sir.

User: "Thank you JARVIS."
COMMAND: conversation
PARAMS: none
RESPONSE: You are very welcome, sir. Always at your service.

User: "What is quantum computing?"
COMMAND: answer_question
PARAMS: none
RESPONSE: Quantum computing uses quantum mechanical phenomena such as superposition to perform computations far faster than classical computers, sir.

User: "Play Attention on Spotify"
COMMAND: play_music
PARAMS: Attention on spotify
RESPONSE: Playing Attention on Spotify, sir.

User: "Pause the music"
COMMAND: play_music
PARAMS: pause
RESPONSE: Pausing music, sir.

User: "Skip this song"
COMMAND: play_music
PARAMS: next
RESPONSE: Skipping to next track, sir.

User: "Tell me a joke"
COMMAND: conversation
PARAMS: none
RESPONSE: Why did the programmer quit his job? Because he didn't get arrays!
"""

    def __init__(self):
        print("=" * 50)
        print("J.A.R.V.I.S. - Just A Rather Very Intelligent System")
        print("=" * 50)
        print("Initializing...\n")

        # Initialize speech recognition
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

        # Noise hardening: disable dynamic threshold so mic doesn't become
        # hypersensitive in quiet rooms. Set a fixed floor high enough to
        # ignore fans, keyboard clicks, and background hum.
        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.energy_threshold = 3500   # tune up if still noisy
        self.recognizer.pause_threshold = 0.8     # wait 0.8s of silence before stopping

        # Initialize pyttsx3 as fallback TTS
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 175)
        self.engine.setProperty('volume', 1.0)
        voices = self.engine.getProperty('voices')
        for voice in voices:
            if 'male' in voice.name.lower() or 'david' in voice.name.lower():
                self.engine.setProperty('voice', voice.id)
                break

        # Initialize pygame mixer for edge-tts audio playback
        if EDGE_TTS_AVAILABLE and PYGAME_AVAILABLE:
            try:
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
                print("[✓] Neural TTS ready (edge-tts / en-GB-RyanNeural)")
            except Exception as e:
                print(f"[!] Pygame mixer init failed: {e} — using pyttsx3")
        elif EDGE_TTS_AVAILABLE:
            print("[!] edge-tts available but pygame missing — install pygame for audio playback")
        else:
            print("[✓] TTS ready (pyttsx3 fallback)")

        # Initialize handlers
        self.datetime_handler = DateTimeHandler(self)
        self.app_handler = ApplicationHandler(self)
        self.music_handler = MusicHandler(self)
        self.web_handler = WebSearchHandler(self)
        self.alarm_handler = AlarmHandler(self)
        self.weather_handler = WeatherHandler(self, os.getenv('WEATHER_API_KEY'))
        self.system_controls = SystemControls(self)
        self.system_info_handler = SystemInfoHandler(self)
        self.qa_handler = QAHandler(self)

        # Initialize AI
        self.ai_model = None
        self._init_ai()

        # Initialize Groq Whisper STT
        self.whisper_client = None
        self._init_whisper()

        # Wake word detection
        self.is_sleeping = False
        self.last_activity_time = time.time()
        self.sleep_timeout = 300  # 5 minutes in seconds

        # Wake word variations (handle different pronunciations)
        self.wake_words = [
            'jarvis',
            'jarvis wake up',
            'wake up jarvis',
            'hey jarvis',
            'hi jarvis',
            'hello jarvis',
            'jarvis are you there',
            'jarvis online',
            'jarvis activate',
        ]

        # Conversation memory (last 50 messages)
        self.conversation_memory = []
        self.max_memory = 50

        # JARVIS-specific acknowledgment phrases
        self.ack_phrases = [
            "Right away, sir.",
            "Consider it done.",
            "I shall handle it immediately.",
            "Processing your request now, sir.",
            "Certainly, sir.",
            "Of course."
        ]

        # Session tracking
        self.session_start_time = time.time()
        self.last_session_alert_hours = 0
        
        # System Warning State Trackers
        self.battery_warned_20 = False
        self.battery_warned_10 = False
        self.battery_warned_5 = False
        self.cpu_warned = False
        self.ram_warned = False
        self.temp_warned = False
        
        self._start_proactive_monitor()

        # Simple command mappings (fast lookup for single words)
        self.simple_commands = {
            'exit': self._cmd_exit,
            'quit': self._cmd_exit,
            'goodbye': self._cmd_exit,
            'bye': self._cmd_exit,
            'shutdown': self._cmd_exit,
            'hello': self._cmd_greet,
            'hi': self._cmd_greet,
            'hey': self._cmd_greet,
            'help': self._cmd_help,
        }

        print(f"\nReady! Mode: {'Hybrid (Local + AI)' if self.ai_model else 'Local Only'}")
        print("Say 'exit' to shutdown\n")

    def _init_ai(self):
        """Initialize Gemini AI"""
        api_key = os.getenv('GEMINI_API_KEY')
        if not GEMINI_AVAILABLE or not api_key:
            return

        try:
            # New SDK: Create client and model
            self.genai_client = genai.Client(api_key=api_key)
            self.ai_model = 'gemini-2.0-flash'  # 1,500 req/day free, supported by v1beta API
            print("[✓] AI Engine ready (gemini-2.0-flash)")
        except Exception as e:
            print(f"[✗] AI Engine failed: {e}")

    def _init_whisper(self):
        """Initialize Groq Whisper-large-v3 for speech-to-text."""
        api_key = os.getenv('GROQ_API_KEY')
        if not api_key:
            print("[!] GROQ_API_KEY not set — using Google STT")
            return
        try:
            from groq import Groq as _Groq
            self.whisper_client = _Groq(api_key=api_key)
            self.whisper_rate_limited_until = 0  # epoch time; 0 = not rate-limited
            print("[✓] Whisper STT ready (groq/whisper-large-v3)")
        except Exception as e:
            print(f"[!] Whisper init failed: {e} — falling back to Google STT")

    def _transcribe_audio(self, audio):
        """
        Transcribe AudioData using Groq Whisper-large-v3 (primary).
        Falls back to Google STT when Whisper hits its rate limit (persists for 1 hour)
        or on any other failure.
        """
        WHISPER_COOLDOWN = 3600  # seconds to stay on Google STT after a 429

        if self.whisper_client:
            # Check if we're still in a rate-limit cooldown
            if hasattr(self, 'whisper_rate_limited_until') and time.time() < self.whisper_rate_limited_until:
                remaining = int(self.whisper_rate_limited_until - time.time())
                print(f"[Whisper] Rate-limited — using Google STT ({remaining}s cooldown remaining)")
            else:
                try:
                    wav_bytes = audio.get_wav_data()
                    sample_rate = audio.sample_rate

                    # Spectral noise reduction (if available) before sending to Whisper
                    if NOISEREDUCE_AVAILABLE:
                        try:
                            audio_np = np.frombuffer(wav_bytes, dtype=np.int16).astype(np.float32)
                            reduced_np = nr.reduce_noise(
                                y=audio_np,
                                sr=sample_rate,
                                stationary=True,   # good for constant hum/fan noise
                                prop_decrease=0.75 # reduce noise by 75%, keep speech natural
                            )
                            wav_bytes = reduced_np.astype(np.int16).tobytes()
                        except Exception:
                            pass  # silently fall through to original audio

                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                        f.write(wav_bytes)
                        tmp_path = f.name
                    try:
                        with open(tmp_path, 'rb') as f:
                            result = self.whisper_client.audio.transcriptions.create(
                                model='whisper-large-v3',
                                file=('audio.wav', f, 'audio/wav'),
                                response_format='text',
                                language='en',
                            )
                        text = result.strip() if isinstance(result, str) else result.text.strip()
                        text_lower = text.lower()
                        
                        # Filter Whisper hallucinations (common noise artefacts)
                        hallucinations = {
                            'thank you.', 'thank you', 'thanks.', 'thanks',
                            'thanks for watching.', 'thanks for watching',
                            'you', 'you.', '.', '..', '...',
                            'subtitles by', 'amara.org',
                            'bye.', 'bye', 'okay.', 'okay', 'ok.', 'ok',
                            'um', 'um.', 'uh', 'uh.', 'hmm', 'hmm.',
                            'please subscribe.', 'subscribe.',
                            'like and subscribe.', 'see you next time.',
                        }
                        if text_lower in hallucinations:
                            return ""
                        # Minimum word guard: single-word results are almost
                        # always noise artefacts — require at least 2 words
                        if len(text_lower.split()) < 2:
                            return ""
                        return text_lower
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass

                except Exception as e:
                    err = str(e).lower()
                    if any(k in err for k in ('429', 'rate limit', 'rate_limit', 'quota')):
                        self.whisper_rate_limited_until = time.time() + WHISPER_COOLDOWN
                        print(f"[Whisper] Rate limit hit — switching to Google STT for {WHISPER_COOLDOWN // 60} minutes")
                    else:
                        print(f"[Whisper] Error: {e} — falling back to Google STT")

        # Google STT fallback
        return self.recognizer.recognize_google(audio).lower()

    def speak(self, text):
        """Speak text — edge-tts neural voice with pyttsx3 fallback"""
        print(f"JARVIS: {text}")

        if EDGE_TTS_AVAILABLE and PYGAME_AVAILABLE:
            try:
                asyncio.run(self._speak_edge_tts(text))
            except Exception as e:
                print(f"[Edge TTS Error] {e} — falling back to pyttsx3")
                self.engine.say(text)
                self.engine.runAndWait()
        else:
            self.engine.say(text)
            self.engine.runAndWait()

        # Add to memory (but not for system messages)
        if text and not any(skip in text.lower() for skip in ['listening', 'processing', "couldn't understand"]):
            self.add_to_memory('assistant', text)

    async def _speak_edge_tts(self, text):
        """Synthesize speech via edge-tts and play through pygame."""
        communicate = edge_tts.Communicate(
            text,
            voice="en-GB-RyanNeural",
            rate="+25%",   # Increased rate as requested
            pitch="-5Hz",  # Slightly lower for authority
        )

        # Stream audio to a temp file then play
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmpfile = f.name

        try:
            await communicate.save(tmpfile)
            pygame.mixer.music.load(tmpfile)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.05)
        finally:
            try:
                os.unlink(tmpfile)
            except OSError:
                pass

    def listen(self):
        """
        Listen for voice input.
        Transcribes via Groq Whisper-large-v3 (primary) or Google STT (fallback).
        """
        with self.microphone as source:
            # Calibrate once per listen cycle against current ambient noise
            self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
            # Clamp: never let calibration drop threshold below our floor
            if self.recognizer.energy_threshold < 3500:
                self.recognizer.energy_threshold = 3500

            try:
                audio = self.recognizer.listen(
                    source,
                    timeout=10,
                    phrase_time_limit=10
                )
                command = self._transcribe_audio(audio)
                if command:
                    print(f"You said: '{command}'")
                return command

            except sr.WaitTimeoutError:
                return None
            except sr.UnknownValueError:
                print("Couldn't understand that, sir.")
                return None
            except sr.RequestError as e:
                print(f"Speech service error: {e}")
                return None

    def process_command(self, command):
        """Process the command - local first, then AI"""
        if not command:
            return True

        # Add user message to memory
        self.add_to_memory('user', command)

        # Check for exit first
        if any(word in command for word in [
                'exit', 'quit', 'goodbye', 'bye', 'shutdown',
                'shut down', 'power off', 'turn yourself off']):
            return self._cmd_exit()

        # Check simple command keywords (word-boundary match to avoid false triggers)
        import re as _re
        for keyword, handler in self.simple_commands.items():
            if _re.search(r'\b' + _re.escape(keyword) + r'\b', command):
                return handler()

        # Check for specific patterns (must START with action words)
        if command.startswith('open'):
            return self._cmd_open_app(command)
        # Music control commands (pause, next, previous)
        if any(word in command for word in ['pause', 'resume', 'continue', 'stop']):
            return self._cmd_music_control(command)
        if any(word in command for word in ['next', 'skip', 'forward']) and 'song' in command:
            return self._cmd_music_control(command)
        if any(word in command for word in ['previous', 'back']) and 'song' in command:
            return self._cmd_music_control(command)

        # Music play commands
        if command.startswith('play'):
            return self._cmd_play_music(command)
        if command.startswith(('weather', "what's the weather", 'how is the weather', 'whats the weather', 'what is the weather', 'what\'s the weather')):
            return self._cmd_weather(command)
        if command.startswith(('search', 'look up', 'find')):
            return self._cmd_search(command)
        if command.startswith(('alarm', 'remind', 'set alarm', 'set a reminder')):
            return self._cmd_alarm(command)

        # System control commands
        if any(word in command for word in ['volume', 'mute', 'unmute']):
            return self._cmd_volume(command)
        if any(word in command for word in ['brightness', 'dim', 'bright']):
            return self._cmd_brightness(command)
        if 'timer' in command:
            return self._cmd_timer(command)
        if any(word in command for word in ['stopwatch', 'stop watch']):
            return self._cmd_stopwatch(command)

        # Factual/conversational questions → Groq via QA handler
        if self.qa_handler.is_question(command):
            return self.qa_handler.answer_question(command)

        # No local match - try Gemini for NLP classification
        if self.ai_model:
            return self._process_with_ai(command)
        else:
            self.speak("I'm not sure how to help with that, sir. Try asking for the time, date, weather, or to open an application.")
            return True

    def _process_with_ai(self, command):
        """NLP classification: Groq primary (14,400/day), Gemini fallback on rate limit."""

        # Try Groq first
        groq_result = self._process_with_groq(command)
        if groq_result is not None:
            return groq_result

        # Groq rate-limited or unavailable — try Gemini
        print("[AI] Groq NLP unavailable — trying Gemini")
        return self._process_with_gemini(command)

    def _process_with_groq(self, command):
        """
        NLP classification via Groq (Llama). Primary NLP engine.
        Returns True on success, None on rate-limit/unavailable (so caller can try Gemini).
        """
        if not hasattr(self, 'qa_handler') or not self.qa_handler.groq_client:
            return None

        try:
            memory_context = self.get_memory_context()
            prompt = f"""{self.AVAILABLE_COMMANDS}{memory_context}

User: {command}
"""
            response = self.qa_handler.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are a command classifier for JARVIS. Follow the exact output format specified."},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.2,
                max_tokens=200,
            )
            return self._handle_ai_response(response.choices[0].message.content, command)

        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ('429', 'rate limit', 'rate_limit', 'quota')):
                print(f"[AI] Groq rate limit hit — will try Gemini")
                return None  # Signal caller to fall back
            print(f"[Groq NLP Error] {e}")
            return None  # Any other error — also let Gemini try

    def _process_with_gemini(self, command):
        """NLP classification via Gemini. Fallback when Groq is rate-limited."""
        if not self.ai_model:
            self.speak("I'm sorry, sir. Both AI systems are currently unavailable.")
            return True

        try:
            memory_context = self.get_memory_context()
            prompt = f"""{self.AVAILABLE_COMMANDS}{memory_context}

User: {command}
"""
            response = self.genai_client.models.generate_content(
                model=self.ai_model,
                contents=prompt,
                config={'temperature': 0.3, 'max_output_tokens': 200}
            )
            return self._handle_ai_response(response.text, command)

        except Exception as e:
            print(f"[Gemini NLP Error] {e}")
            self.speak("My apologies, sir. I'm having trouble processing that right now.")
            return True

    def _handle_ai_response(self, text, command):
        """Parse COMMAND/PARAMS/RESPONSE from AI output and execute."""
        text = text.strip()

        cmd, params, resp = None, "", ""

        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('COMMAND:'):
                cmd = line.replace('COMMAND:', '').strip()
            elif line.startswith('PARAMS:'):
                params = line.replace('PARAMS:', '').strip()
            elif line.startswith('RESPONSE:'):
                resp = line.replace('RESPONSE:', '').strip()

        # Exit command — return False to stop the main loop
        if cmd == 'exit':
            self.speak(resp or "Goodbye, sir. JARVIS going offline.")
            return False

        # Sleep command — enter standby mode
        if cmd == 'sleep':
            self.speak(resp or "Going to standby mode, sir. Say 'JARVIS' when you need me.")
            self._go_to_sleep(voiced=True)
            return True

        # Speak response (skip for answer_question — qa_handler speaks the actual answer)
        if resp and cmd != 'answer_question':
            # Occasionally use a JARVIS-specific acknowledgment if it's a simple command
            if cmd in ['open_app', 'play_music', 'set_alarm', 'set_timer'] and random.random() < 0.4:
                resp = random.choice(self.ack_phrases) + " " + resp
            self.speak(resp)

        if cmd and cmd != 'conversation':
            self._execute_ai_command(cmd, params, original_command=command)

        return True

    def _execute_ai_command(self, cmd, params, original_command=''):
        """Execute command from AI"""
        try:
            if cmd == 'get_time':
                self.datetime_handler.tell_time()
            elif cmd == 'get_date':
                self.datetime_handler.tell_date()
            elif cmd == 'open_app':
                self.app_handler.open_application(f"open {params}")
            elif cmd == 'play_music':
                # Check if it's a control command (pause, next, previous, etc.)
                control_words = ['pause', 'resume', 'continue', 'stop', 'next', 'previous', 'prev', 'skip', 'back']
                if any(word in params.lower() for word in control_words):
                    self.music_handler.process_control_command(params)
                else:
                    self.music_handler.play_music(f"play {params}")
            elif cmd == 'web_search':
                self.web_handler.web_search(f"search {params}")
            elif cmd == 'set_alarm':
                if params and any(w in params.lower() for w in ['cancel', 'stop', 'off']):
                    self.alarm_handler.cancel_alarm()
                else:
                    self.alarm_handler.set_alarm(f"set alarm for {params}")
            elif cmd == 'get_weather':
                is_forecast = 'forecast' in original_command.lower() or 'tomorrow' in original_command.lower()
                
                if params and params != 'none':
                    if is_forecast:
                        self.weather_handler.get_forecast(f"forecast for {params}")
                    else:
                        self.weather_handler.get_current_weather(f"weather in {params}")
                else:
                    self.weather_handler.process_weather_command(original_command)
            elif cmd == 'set_volume':
                low = params.lower()
                if any(w in low for w in ['down', 'decrease', 'lower', 'quieter', 'softer', 'reduce']):
                    self.system_controls.set_volume('volume down')
                elif any(w in low for w in ['up', 'increase', 'louder', 'higher', 'raise']):
                    self.system_controls.set_volume('volume up')
                else:
                    self.system_controls.set_volume(params)
            elif cmd == 'set_brightness':
                self.system_controls.set_brightness(params)
            elif cmd == 'set_timer':
                if params and any(w in params.lower() for w in ['cancel', 'stop', 'off']):
                    self.system_controls.cancel_timer()
                else:
                    self.system_controls.set_timer(params)
            elif cmd == 'stopwatch':
                if 'stop' in params.lower():
                    self.system_controls.stop_stopwatch()
                else:
                    self.system_controls.start_stopwatch()
            elif cmd == 'get_system_info':
                # Run the full diagnostic in a separate thread so it doesn't block the main loop completely
                threading.Thread(target=self.system_info_handler.get_full_report, daemon=True).start()
            elif cmd == 'answer_question':
                # params may be 'none' for conversational questions — use original command
                query = params if params and params.lower() != 'none' else original_command
                self.qa_handler.answer_question(query)
            # conversation and exit need no action here
        except Exception as e:
            print(f"[Execution Error] {e}")

    # Local command handlers
    def _cmd_time(self):
        self.datetime_handler.tell_time()
        return True

    def _cmd_date(self):
        self.datetime_handler.tell_date()
        return True

    def _cmd_greet(self):
        """JARVIS-style greeting with Iron Man flair"""
        hour = datetime.now().hour

        # JARVIS-style greetings
        if 5 <= hour < 12:
            greetings = [
                "Good morning, sir.",
                "Morning, sir. Ready to save the world?",
                "Good morning, sir. All systems are online.",
                "Morning, sir. The lab is ready for you.",
            ]
        elif 12 <= hour < 17:
            greetings = [
                "Good afternoon, sir.",
                "Afternoon, sir. How can I assist?",
                "Good afternoon, sir. All systems operational.",
                "Sir, the afternoon briefing is ready.",
            ]
        elif 17 <= hour < 21:
            greetings = [
                "Good evening, sir.",
                "Evening, sir. Ready for tonight's operations?",
                "Good evening, sir. At your service.",
                "Evening, sir. The suit is charged and ready.",
            ]
        else:  # 21:00 - 05:00 (night/late night)
            greetings = [
                "Good evening, sir. Working late again?",
                "Evening, sir. The lab is quiet tonight.",
                "Sir, it's late. I'm here if you need me.",
                "Evening, sir. All systems standing by.",
            ]

        import random
        greeting = random.choice(greetings)
        self.speak(greeting)
        return True

    def _cmd_open_app(self, command):
        self.app_handler.open_application(command)
        return True

    def _cmd_play_music(self, command):
        self.music_handler.play_music(command)
        return True

    def _cmd_music_control(self, command):
        """Handle music control commands (pause, next, previous)"""
        success = self.music_handler.process_control_command(command)
        if not success:
            self.speak("I'm unable to control the music right now, sir.")
        return True

    def _cmd_weather(self, command):
        self.weather_handler.process_weather_command(command)
        return True

    def _cmd_search(self, command):
        self.web_handler.web_search(command)
        return True

    def _cmd_alarm(self, command):
        self.alarm_handler.set_alarm(command)
        return True

    def _cmd_volume(self, command):
        """Handle volume commands"""
        if 'mute' in command:
            if 'unmute' in command:
                self.system_controls.unmute()
            else:
                self.system_controls.mute()
        else:
            self.system_controls.set_volume(command)
        return True

    def _cmd_brightness(self, command):
        """Handle brightness commands"""
        if 'increase' in command or 'up' in command:
            self.system_controls.increase_brightness()
        elif 'decrease' in command or 'down' in command or 'dim' in command:
            self.system_controls.decrease_brightness()
        else:
            self.system_controls.set_brightness(command)
        return True

    def _cmd_timer(self, command):
        """Handle timer commands"""
        if 'cancel' in command or 'stop' in command:
            self.system_controls.cancel_timer()
        else:
            self.system_controls.set_timer(command)
        return True

    def _cmd_stopwatch(self, command):
        """Handle stopwatch commands"""
        if 'start' in command:
            self.system_controls.start_stopwatch()
        elif 'stop' in command or 'end' in command:
            self.system_controls.stop_stopwatch()
        elif 'lap' in command:
            self.system_controls.lap_stopwatch()
        elif 'reset' in command:
            self.system_controls.reset_stopwatch()
        else:
            # Default: start if not running, stop if running
            if self.system_controls.stopwatch_running:
                self.system_controls.stop_stopwatch()
            else:
                self.system_controls.start_stopwatch()
        return True

    def _cmd_help(self):
        self.speak("I can tell you the time and date, open applications, check the weather, play music, search the web, or set alarms. I also understand natural language when my AI is active.")
        return True

    def _cmd_status(self):
        mode = "AI-enabled" if self.ai_model else "Local only"
        self.speak(f"All systems operational, sir. Running in {mode} mode.")
        return True

    def _cmd_exit(self):
        self.speak("Goodbye, sir. JARVIS going offline.")
        return False

    def run(self):
        """Main loop"""
        # Greeting
        self._cmd_greet()

        running = True
        while running:
            # Check if should go to sleep
            if not self.is_sleeping and time.time() - self.last_activity_time > self.sleep_timeout:
                self._go_to_sleep()

            # Listen for input
            if self.is_sleeping:
                # In sleep mode - only listen for wake word
                command = self._listen_for_wake_word()
            else:
                # Normal mode - listen for commands
                command = self.listen()

            if command:
                if self.is_sleeping:
                    # Check if it's a wake word
                    if self._is_wake_word(command):
                        self._wake_up()
                    # Ignore other commands while sleeping
                else:
                    # Process command normally
                    self._update_activity()
                    running = self.process_command(command)

            time.sleep(0.5)

    def _listen_for_wake_word(self):
        """Listen specifically for wake word when sleeping"""
        with self.microphone as source:
            print("\n💤 Sleeping... Say 'Jarvis' to wake me")
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

            try:
                # Listen continuously for wake word
                audio = self.recognizer.listen(
                    source,
                    timeout=30,  # Check every 30 seconds
                    phrase_time_limit=5
                )
                command = self._transcribe_audio(audio)
                print(f"Heard: '{command}'")
                return command
            except sr.WaitTimeoutError:
                return None
            except sr.UnknownValueError:
                return None
            except sr.RequestError:
                return None

    def _is_wake_word(self, command):
        """Check if command contains wake word"""
        if not command:
            return False

        # Check for exact matches
        for wake_word in self.wake_words:
            if wake_word in command:
                return True

        # Fuzzy matching for different pronunciations
        # Remove common variations and check similarity
        cleaned = command.replace(' ', '').replace('-', '').replace('_', '')

        # Check for "jarvis" in various forms (deduplicated)
        jarvis_variations = [
            'jarvis',
            'jarviss',
            'jarvus',
            'jarvish',
        ]

        for variation in jarvis_variations:
            if variation in cleaned:
                return True

        return False

    def _wake_up(self):
        """Wake up from sleep mode"""
        self.is_sleeping = False
        self._update_activity()
        self.speak("I'm here, sir. How can I help you?")

    def _go_to_sleep(self, voiced=False):
        """Enter sleep mode"""
        self.is_sleeping = True
        if not voiced:
            # Auto-sleep from inactivity — silent
            print("\n💤 JARVIS going to sleep (5 minutes of inactivity)")

    def _update_activity(self):
        """Update last activity time"""
        self.last_activity_time = time.time()

    # ==================== CONVERSATION MEMORY ====================

    def add_to_memory(self, role, content):
        """Add message to conversation memory"""
        self.conversation_memory.append({
            'role': role,
            'content': content,
            'timestamp': time.time()
        })

        # Keep only last 50 messages
        if len(self.conversation_memory) > self.max_memory:
            self.conversation_memory = self.conversation_memory[-self.max_memory:]

    def get_memory_context(self):
        """Get formatted conversation memory for AI context"""
        if not self.conversation_memory:
            return ""

        context = "\n\nRecent conversation:\n"
        for msg in self.conversation_memory[-10:]:  # Last 10 for context
            role = "User" if msg['role'] == 'user' else "JARVIS"
            context += f"{role}: {msg['content']}\n"

        return context

    def clear_memory(self):
        """Clear conversation memory"""
        self.conversation_memory.clear()
        print("Conversation memory cleared")

    # ==================== PROACTIVE MONITORING ====================

    def _start_proactive_monitor(self):
        """Start the background thread that occasionally volunteers information."""
        self.monitor_thread = threading.Thread(target=self._proactive_monitor, daemon=True)
        self.monitor_thread.start()

    def _proactive_monitor(self):
        """Background loop that checks for session length and system alerts."""
        while True:
            time.sleep(60)  # Check every 60 seconds
            
            # 1. Session tracking (warn every 2 hours)
            elapsed_hours = (time.time() - self.session_start_time) / 3600
            if elapsed_hours >= self.last_session_alert_hours + 2:
                self.last_session_alert_hours += 2
                self.speak(f"Pardon the interruption, sir, but you have been working for {self.last_session_alert_hours} hours. I recommend stepping away from the screen momentarily.")

            # 2. Hardware Monitoring
            if hasattr(self, 'system_info_handler'):
                stats = self.system_info_handler.get_quick_stats()
                
                # CPU Warning (>80%)
                if stats['cpu'] > 80:
                    if not self.cpu_warned:
                        self.speak(f"Sir, CPU usage has exceeded 80 percent. Currently at {stats['cpu']} percent.")
                        self.cpu_warned = True
                else:
                    self.cpu_warned = False  # Reset when it drops

                # RAM Warning (>85%)
                if stats['ram'] > 85:
                    if not self.ram_warned:
                        self.speak(f"Warning, sir. Memory usage is critical at {stats['ram']} percent.")
                        self.ram_warned = True
                else:
                    self.ram_warned = False

                # Temperature Warning (>75C)
                if stats['temp'] and stats['temp'] > 75:
                    if not self.temp_warned:
                        self.speak(f"Sir, CPU temperature is elevated. Currently at {stats['temp']:.1f} degrees.")
                        self.temp_warned = True
                else:
                    self.temp_warned = False

                # Battery Warnings (20%, 10%, 5%)
                battery = stats.get('battery')
                plugged_in = stats.get('plugged_in')
                if battery is not None and not plugged_in:
                    if battery <= 5 and not self.battery_warned_5:
                        self.speak(f"Critical battery warning, sir. Power levels are at {battery} percent. Shut down is imminent.")
                        self.battery_warned_5 = True
                    elif battery <= 10 and not self.battery_warned_10:
                        self.speak(f"Sir, battery has dropped to {battery} percent. Please connect to a power source.")
                        self.battery_warned_10 = True
                    elif battery <= 20 and not self.battery_warned_20:
                        self.speak(f"Sir, battery is at {battery} percent.")
                        self.battery_warned_20 = True
                elif plugged_in:
                    # Reset battery warnings when plugged back in
                    self.battery_warned_20 = False
                    self.battery_warned_10 = False
                    self.battery_warned_5 = False




if __name__ == "__main__":
    try:
        jarvis = JARVIS()
        jarvis.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
