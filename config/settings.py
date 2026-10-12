#!/usr/bin/env python3
"""
Configuration and Environment Settings for JARVIS
Loads environment variables and defines paths and system parameters.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Root Directory of the Project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from root
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)

# Directory Paths
CONFIG_DIR = BASE_DIR / "config"
MEETINGS_FILE = CONFIG_DIR / "meetings.json"
BROWSER_PROFILE_DIR = BASE_DIR / ".browser_profile"
UI_DIR = BASE_DIR / "ui"
ASSETS_DIR = UI_DIR / "assets"
STYLES_FILE = UI_DIR / "styles.qss"
QA_CACHE_FILE = BASE_DIR / "qa_cache.json"

# API Keys & LLM Models
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

# Meeting Attendant & Web Dashboard
MEETING_DASHBOARD_PORT = int(os.getenv("MEETING_DASHBOARD_PORT", "5050"))
MEETING_DASHBOARD_HOST = os.getenv("MEETING_DASHBOARD_HOST", "127.0.0.1")

# Connection & Network Overrides
JARVIS_FORCE_ONLINE = os.getenv("JARVIS_FORCE_ONLINE", "false").lower() == "true"

# Speech & TTS Settings
TTS_NEURAL_VOICE = os.getenv("JARVIS_VOICE", "en-GB-RyanNeural")
TTS_FALLBACK_RATE = int(os.getenv("JARVIS_TTS_RATE", "175"))
MIC_PHRASE_TIME_LIMIT = 5
MIC_TIMEOUT = 5
