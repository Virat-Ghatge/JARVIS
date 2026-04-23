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

# Import handlers
from date_time import DateTimeHandler
from applications import ApplicationHandler
from music import MusicHandler
from web_search import WebSearchHandler
from alarm import AlarmHandler
from weather import WeatherHandler
from system_controls import SystemControls

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
6. set_alarm - Set an alarm/reminder
7. get_weather - Get weather for a city
8. exit - Shutdown JARVIS
9. conversation - General chat/greeting (no action needed)
10. set_volume - Set system volume (0-100) or mute/unmute
11. set_brightness - Set screen brightness (0-100)
12. set_timer - Set a countdown timer (e.g., "5 minutes")
13. stopwatch - Start/stop a stopwatch

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
COMMAND: web_search
PARAMS: CEO of Google
RESPONSE: Let me search for that information, sir.

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

        # Initialize speech
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

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

        # Initialize AI
        self.ai_model = None
        self._init_ai()

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

        # Simple command mappings (fast lookup)
        self.simple_commands = {
            'time': self._cmd_time,
            'date': self._cmd_date,
            'day': self._cmd_date,
            'exit': self._cmd_exit,
            'quit': self._cmd_exit,
            'goodbye': self._cmd_exit,
            'bye': self._cmd_exit,
            'shutdown': self._cmd_exit,
            'hello': self._cmd_greet,
            'hi': self._cmd_greet,
            'hey': self._cmd_greet,
            'help': self._cmd_help,
            'status': self._cmd_status,
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
            self.ai_model = 'gemini-2.5-flash'  # Model name for new SDK
            print("[✓] AI Engine ready")
        except Exception as e:
            print(f"[✗] AI Engine failed: {e}")

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
            rate="+8%",    # Crisp and efficient — JARVIS never dawdles
            pitch="-3Hz",  # Slightly lower for authority
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
        Listen for voice input with pause handling.
        Uses longer timeout to allow for pauses in speech.
        """
        with self.microphone as source:
            # Adjust for ambient noise
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

            try:
                # Listen with longer timeout and phrase time
                # timeout: max seconds to wait for speech to start
                # phrase_time_limit: max seconds of speech to capture
                audio = self.recognizer.listen(
                    source,
                    timeout=10,        # Wait up to 10s for user to start speaking
                    phrase_time_limit=10  # Capture up to 10s of speech (allows pauses)
                )

                print("Processing...")
                command = self.recognizer.recognize_google(audio).lower()
                print(f"You said: '{command}'")
                return command

            except sr.WaitTimeoutError:
                # No speech detected within timeout
                return None
            except sr.UnknownValueError:
                # Couldn't understand audio
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
        if any(word in command for word in ['exit', 'quit', 'goodbye', 'bye', 'shutdown']):
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
        if command.startswith(('weather', "what's the weather", 'how is the weather', 'whats the weather')):
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

        # No local match - try AI if available
        if self.ai_model:
            return self._process_with_ai(command)
        else:
            self.speak("I'm not sure how to help with that, sir. Try asking for the time, date, weather, or to open an application.")
            return True

    def _process_with_ai(self, command):
        """Process command using Gemini AI"""
        print("[AI] Processing...")

        try:
            # Build prompt — include recent conversation memory for context
            memory_context = self.get_memory_context()
            prompt = f"""{self.AVAILABLE_COMMANDS}{memory_context}

User: {command}
"""

            # Get AI response using new SDK
            response = self.genai_client.models.generate_content(
                model=self.ai_model,
                contents=prompt,
                config={'temperature': 0.3, 'max_output_tokens': 150}
            )

            # Parse response
            text = response.text.strip()
            print(f"[AI] Raw response: {text}")

            # Extract command, params, and response
            cmd = None
            params = ""
            resp = ""

            for line in text.split('\n'):
                line = line.strip()
                if line.startswith('COMMAND:'):
                    cmd = line.replace('COMMAND:', '').strip()
                elif line.startswith('PARAMS:'):
                    params = line.replace('PARAMS:', '').strip()
                elif line.startswith('RESPONSE:'):
                    resp = line.replace('RESPONSE:', '').strip()

            # Speak the response
            if resp:
                self.speak(resp)

            # Execute the command
            if cmd and cmd != 'conversation':
                self._execute_ai_command(cmd, params)

            return True

        except Exception as e:
            print(f"[AI Error] {e}")
            self.speak("My apologies, sir. I'm having trouble with my AI systems right now.")
            return True

    def _execute_ai_command(self, cmd, params):
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
                self.alarm_handler.set_alarm(f"set alarm for {params}")
            elif cmd == 'get_weather':
                if params and params != 'none':
                    self.weather_handler.get_current_weather(f"weather in {params}")
                else:
                    self.weather_handler.process_weather_command("weather")
            elif cmd == 'set_volume':
                self.system_controls.set_volume(params)
            elif cmd == 'set_brightness':
                self.system_controls.set_brightness(params)
            elif cmd == 'set_timer':
                self.system_controls.set_timer(params)
            elif cmd == 'stopwatch':
                if 'stop' in params.lower():
                    self.system_controls.stop_stopwatch()
                else:
                    self.system_controls.start_stopwatch()
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
                command = self.recognizer.recognize_google(audio).lower()
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

    def _go_to_sleep(self):
        """Enter sleep mode"""
        self.is_sleeping = True
        print("\n💤 JARVIS going to sleep (5 minutes of inactivity)")
        # Don't speak when going to sleep to avoid disturbing

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


if __name__ == "__main__":
    try:
        jarvis = JARVIS()
        jarvis.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
