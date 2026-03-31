#!/usr/bin/env python3
"""
JARVIS Core Module
Handles speech recognition, text-to-speech, and the main JARVIS class
"""

import os
import speech_recognition as sr
import pyttsx3
import threading
import time
from datetime import datetime

from date_time import DateTimeHandler
from applications import ApplicationHandler
from music import MusicHandler
from web_search import WebSearchHandler
from alarm import AlarmHandler
from weather import WeatherHandler

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, will use environment variables directly

# Configuration - Get API key from environment variable
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
if not WEATHER_API_KEY:
    print("Warning: WEATHER_API_KEY not set. Weather functionality will not work.")
    print("Please set the WEATHER_API_KEY environment variable or create a .env file.")


class JARVIS:
    """Main JARVIS Assistant Class"""

    def __init__(self):
        # Initialize speech recognizer
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

        # Initialize text-to-speech engine
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 175)
        self.engine.setProperty('volume', 1.0)

        # Try to set a more JARVIS-like voice
        voices = self.engine.getProperty('voices')
        for voice in voices:
            if 'male' in voice.name.lower() or 'david' in voice.name.lower():
                self.engine.setProperty('voice', voice.id)
                break

        # Initialize handlers
        self.datetime_handler = DateTimeHandler(self)
        self.app_handler = ApplicationHandler(self)
        self.music_handler = MusicHandler(self)
        self.web_handler = WebSearchHandler(self)
        self.alarm_handler = AlarmHandler(self)
        self.weather_handler = WeatherHandler(self, WEATHER_API_KEY)

        # Greeting flag
        self.first_run = True

    def speak(self, text):
        """Convert text to speech"""
        print(f"JARVIS: {text}")
        self.engine.say(text)
        self.engine.runAndWait()

    def listen(self):
        """Listen for voice input and convert to text"""
        with self.microphone as source:
            print("Listening...")
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=5)
                print("Processing...")
                command = self.recognizer.recognize_google(audio).lower()
                print(f"You said: {command}")
                return command
            except sr.WaitTimeoutError:
                return None
            except sr.UnknownValueError:
                return None
            except sr.RequestError:
                self.speak("I'm having trouble connecting to the speech service.")
                return None

    def wish_me(self):
        """Greet based on time of day"""
        self.datetime_handler.wish_me()

    def process_command(self, command):
        """Process the voice command"""
        if not command:
            return True

        # Exit commands
        if any(word in command for word in ['exit', 'quit', 'goodbye', 'bye', 'shutdown', 'sleep']):
            self.speak("Goodbye, sir. JARVIS going offline.")
            return False

        # Time commands
        if 'time' in command:
            self.datetime_handler.tell_time()

        # Date commands
        elif 'date' in command or 'day' in command or 'today' in command:
            self.datetime_handler.tell_date()

        # Open application commands
        elif 'open' in command:
            self.app_handler.open_application(command)

        # Music commands
        elif 'play' in command and ('music' in command or 'song' in command):
            self.music_handler.play_music(command)

        # Web search commands
        elif any(word in command for word in ['search', 'google', 'look up', 'find']):
            self.web_handler.web_search(command)

        # Alarm commands
        elif 'alarm' in command or 'remind' in command:
            self.alarm_handler.set_alarm(command)

        # Weather commands
        elif any(word in command for word in ['weather', 'temperature', 'forecast']):
            self.weather_handler.process_weather_command(command)

        # Greeting responses
        elif any(word in command for word in ['hello', 'hi', 'hey', 'jarvis']):
            self.speak("Hello, sir. How can I help you today?")

        # Status check
        elif any(word in command for word in ['how are you', 'status', 'systems']):
            self.speak("All systems are operational and running at optimal efficiency, sir.")

        # Help
        elif 'help' in command:
            self.speak("I can help you with: telling the time and date, opening applications, playing music, searching the web, checking the weather, and setting alarms. Just say the command.")

        else:
            self.speak("I'm not sure I understood that command, sir. Could you please repeat?")

        return True

    def run(self):
        """Main loop"""
        if self.first_run:
            self.wish_me()
            self.speak("How can I help you today?")
            self.first_run = False

        running = True
        while running:
            command = self.listen()
            if command:
                running = self.process_command(command)
            time.sleep(0.5)
