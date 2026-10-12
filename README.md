# JARVIS Desktop AI Assistant

> **Just A Rather Very Intelligent System**  
> Standalone Desktop GUI Application with PySide6, Neural Voice, Dual Audio Interlocking, and Autonomous Meeting Attendant.

JARVIS is a Python desktop voice and text assistant inspired by Tony Stark's AI companion from Iron Man. Re-architected with a modular system design, a native PySide6 dark HUD desktop interface, unified InputGateway routing, independent dual audio state controls, and headed meeting automation for Google Meet and Microsoft Teams.

---

## Interface Overview

```
+-----------------------------------------------------------------------------------------+
| [J.A.R.V.I.S.] INTELLIGENT SYSTEM ARCHITECTURE       [ONLINE]  [MEETING DASHBOARD :5050] |
+-----------------------------------------------------------------------------------------+
| [MIC: MUTED / LISTENING]  [VOICE: ACTIVE / MUTED]  Status: Ready          [Clear Chat]  |
+-------------------------------------------------------------+---------------------------+
|                                                             |    SYSTEM TELEMETRY       |
|  YOU [TEXT]                                                 |                           |
|  "What time is it?"                                         |    [ CPU LOAD: 14.2% ]    |
|                                                             |    [ RAM USAGE: 42.1% ]   |
|  J.A.R.V.I.S. [TEXT]                                        |    [ BATTERY: 95% AC ]    |
|  "The current time is 02:35 PM, sir."                       |                           |
|                                                             |   NEXT SCHEDULED MEETING  |
|  YOU [VOICE]                                                |   "Team Sprint Sync"      |
|  "What meetings do I have today?"                           |   Today at 3:00 PM        |
|                                                             |   [ Join Now Button ]     |
|  J.A.R.V.I.S. [VOICE]                                       |                           |
|  "You have 1 upcoming meeting: Team Sprint Sync at 3:00 PM"|                           |
|                                                             |                           |
+-------------------------------------------------------------+---------------------------+
| [Type a command or query...                                          ]  [ EXECUTE ]     |
+-----------------------------------------------------------------------------------------+
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Native PySide6 Desktop GUI** | Sleek Iron Man-inspired dark HUD interface (`#0b0f19` slate, electric cyan accents) launched by default |
| **Independent Dual Audio Controls**| Discrete toggles for **Mic In** (voice listening) and **TTS Out** (spoken speech) |
| **Meeting-Aware Auto-Mute** | Automatically mutes microphone when joining meetings to prevent audio loops; supports manual override |
| **Unified InputGateway** | Uniform routing for text and voice commands through local handlers, meeting engines, and LLMs |
| **Automated Meeting Attendant** | Headed browser automation (Playwright/Chrome) auto-joins Google Meet & Teams with mic/cam muted and auto-leaves |
| **Meeting Web Dashboard** | Integrated web dashboard at `http://localhost:5050` with quick-add forms, timeline, and bulk import |
| **Hybrid LLM Intelligence** | Sub-second local execution for commands; Groq (Llama 3.1) and Gemini for natural language Q&A |
| **Live System Telemetry** | Real-time monitoring of CPU load, RAM usage, battery levels, and upcoming meeting notifications |
| **Cross-Platform Shortcut** | Built-in script to generate clickable desktop launchers for Windows, Linux, and macOS |
| **Offline-First Fallback** | Clock, app launching, audio volume, display brightness, alarms, and local meeting agendas work 100% offline |

---

## Quick Start

### 1. Prerequisites

- **Python 3.8+** (Python 3.10+ recommended)
- **Google Chrome** installed (for persistent-session meeting automation)
- Microphone and speakers/headphones

### 2. Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/yourusername/jarvis-assistant.git
cd jarvis-assistant

pip install -r requirements.txt
python -m playwright install chromium
```

*PyAudio setup notes (if needed):*
- **Windows:** Included in `requirements.txt` (or `pip install pipwin && pipwin install pyaudio`)
- **macOS:** `brew install portaudio && pip install pyaudio`
- **Linux:** `sudo apt-get install python3-pyaudio`

### 3. One-Time Browser Authentication (For Meetings)

To enable friction-free auto-join for Google Meet and Microsoft Teams without repeating 2FA:
```bash
python -m automation.meeting_bot --setup
```
Signs you into Google and Microsoft accounts within Chrome and saves your session locally into `.browser_profile/`.

### 4. Configure Environment Variables

```bash
cp .env.example .env
```
Edit `.env` to configure your API keys:
```env
WEATHER_API_KEY=your_weather_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here

MEETING_DASHBOARD_PORT=5050
MEETING_DASHBOARD_HOST=127.0.0.1
```
- [Get Weather API key](https://openweathermap.org/api)
- [Get Gemini API key (free)](https://aistudio.google.com/app/apikey)
- [Get Groq API key (free)](https://console.groq.com)

---

## Launch Modes

### Default: Desktop GUI Mode

Simply run `main.py` without flags:
```bash
python main.py
```
Launches the full PySide6 desktop HUD application with asynchronous command processing.

### Fallback: CLI / Terminal Mode

To run in headless or terminal-only environments:
```bash
python main.py --cli
```
Optional silent flag (suppresses spoken voice output):
```bash
python main.py --cli --silent
```

---

## Generating Desktop Application Icon

To generate a clickable desktop shortcut/launcher on your desktop:

```bash
python scripts/create_desktop_icon.py
```

- **Windows:** Creates `JARVIS Assistant.lnk` and `Launch JARVIS.bat` on your Desktop with the custom icon.
- **Linux:** Creates `jarvis.desktop` on your Desktop and installs it into `~/.local/share/applications/`.
- **macOS:** Creates `JARVIS.command` on your Desktop with executable permissions.

---

## Dual Audio State Machine & Interlocking

JARVIS separates audio ingestion from audio synthesis:

1. **Microphone Toggle (`MIC`)**:
   - `MIC: MUTED` (Gray): Background speech listener is paused. No microphone data is processed.
   - `MIC: LISTENING` (Cyan): Background listener active, processing speech through Groq Whisper / Google STT.
2. **TTS Output Toggle (`VOICE`)**:
   - `VOICE: ACTIVE` (Cyan): Responses are spoken aloud via `edge-tts` (neural British voice) or `pyttsx3`.
   - `VOICE: MUTED` (Gray): Silent mode. JARVIS responds exclusively via text bubbles in the Chat Feed.
3. **Meeting-Aware Audio Interlocking**:
   - When a Google Meet or Teams call is joined, the microphone is **automatically muted** to prevent room audio from triggering commands.
   - **Manual Override**: The user can click the `MIC` button at any time during an active call to unmute.
   - When the meeting ends, the microphone automatically restores to its previous active state unless overridden.

---

## GUI Shortcuts & Controls

- **Enter**: Submit query from input field.
- **Up Arrow**: Recall previous command from history.
- **Down Arrow**: Navigate forward in command history.
- **Clear Chat**: Clears message history from the screen.
- **Meeting Dashboard**: Opens `http://localhost:5050` in your default browser.
- **Join Now**: Joins the next scheduled meeting immediately from the Telemetry dock.

---

## Commands Reference

Both text queries and voice commands are accepted:

### Meeting Commands
- `schedule meeting Project Sync at 3 PM https://meet.google.com/abc-defg-hij`
- `what meetings do i have today` / `list meetings`
- `cancel meeting Project Sync`
- `join meeting https://teams.microsoft.com/...`
- `leave meeting`
- `open meeting dashboard`

### System Controls & Hardware
- `set volume to 50%` / `mute volume` / `volume up`
- `set brightness to 80%`
- `system status` / `check battery` / `cpu usage`
- `set timer for 5 minutes` / `stopwatch`

### Daily Utilities & General Knowledge
- `what time is it` / `what is the date`
- `open Chrome` / `open Spotify` / `open Notepad`
- `play lo-fi hip hop on youtube` / `pause music` / `skip song`
- `weather in New York` / `forecast for London`
- `search for quantum computing`
- `who directed Interstellar?` (answered via Groq Llama 3.1)

---

## Project Structure

```
jarvis-assistant/
├── main.py                     # Entry point (launches PySide6 GUI by default; --cli fallback)
├── config/
│   ├── __init__.py
│   ├── settings.py             # Config, environment loader, and path definitions
│   └── meetings.json           # Persistent meeting schedules storage
├── core/
│   ├── __init__.py
│   ├── engine.py               # Core orchestrator & InputGateway
│   ├── voice_listener.py       # Thread-safe SpeechRecognition worker & audio interlock
│   └── tts_engine.py           # Unified edge-tts neural voice & pyttsx3 synthesis engine
├── handlers/                   # Consolidated command execution modules
│   ├── __init__.py
│   ├── system_controls.py      # Volume and brightness adjustments
│   ├── system_info.py          # Battery and CPU load monitoring
│   ├── applications.py         # System application launcher
│   ├── music.py                # YouTube and Spotify playback controller
│   ├── web_search.py           # Google search handler
│   ├── weather.py              # OpenWeatherMap API integration
│   ├── date_time.py            # Clock and calendar handler
│   ├── alarm.py                # Alarms and reminders
│   └── qa_handler.py           # Groq (Llama 3.1) and Gemini knowledge engine
├── automation/
│   ├── __init__.py
│   ├── meeting_bot.py          # Playwright browser driver (Google Meet & Teams)
│   ├── meeting_scheduler.py    # APScheduler background runner & JSON storage
│   ├── schedule_interface.py  # FastAPI meeting dashboard at :5050
│   └── meeting_handler.py      # High-level meeting management adapter
├── ui/
│   ├── __init__.py
│   ├── app_window.py           # PySide6 MainWindow layout, signals, & QThreadPool
│   ├── styles.qss              # Dark JARVIS HUD theme (slate/cyan palette)
│   ├── components/             # Reusable UI widgets
│   │   ├── __init__.py
│   │   ├── chat_feed.py        # Responsive message bubbles with auto-scroll
│   │   ├── stat_cards.py       # Live telemetry mini-cards and meeting banner
│   │   └── input_bar.py        # Text input field with command history recall
│   └── assets/                 # Custom Arc Reactor icons (PNG, ICO)
├── scripts/
│   └── create_desktop_icon.py  # Cross-platform desktop shortcut generator
├── tests/
│   ├── test_gateway.py         # Loop 1 verification (InputGateway offline routing)
│   ├── test_audio_state.py     # Loop 2 verification (Audio state machine & interlocking)
│   └── test_ui_window.py       # Loop 3 & 4 verification (PySide6 GUI & async signals)
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules (protects credentials & browser profile)
└── README.md                   # Project documentation
```

---

## Verification Test Suites

Run the automated verification test suites across all loops:

```bash
# Verify Loop 1: InputGateway & Modular Handlers
python tests/test_gateway.py

# Verify Loop 2: Concurrency & Audio State Machine
python tests/test_audio_state.py

# Verify Loop 3 & 4: PySide6 GUI & Async Wiring
python tests/test_ui_window.py

# Verify Loop 5: Desktop Icon Generation
python scripts/create_desktop_icon.py
```

---

## License

This project is open source and available under the [MIT License](LICENSE).
