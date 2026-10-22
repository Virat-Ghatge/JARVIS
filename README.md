# JARVIS 2.0 — Autonomous OS Agent & Holographic HUD

> **Just A Rather Very Intelligent System**  
> Autonomous AI Agent with Marvel Arc-Cyan Holographic HUD, FastAPI + WebSocket Engine, Multi-Key Dynamic Vault, 3-Tier OS Actuator, and Playwright Meeting Attendant.

JARVIS 2.0 is an autonomous desktop OS agent and voice/text companion inspired by Tony Stark's AI assistant from Iron Man. Featuring a React + Vite + Tailwind CSS tactical HUD served inside a native PyWebView desktop container, sub-second local deterministic triage, autonomous 3-tier OS action engine, Model Context Protocol (MCP) tool integration, live meeting captions with AI summaries, and multi-provider LLM failover routing.

---

## Interface Overview

```
+-----------------------------------------------------------------------------------------+
| [J.A.R.V.I.S. 2.0] HOLOGRAPHIC TACTICAL HUD            [ONLINE]  [CORE STATUS: OPTIMAL] |
+-----------------------------------------------------------------------------------------+
| [MIC: MUTED / ACTIVE]  [TTS: ACTIVE / SILENT]  [TRUST MODE: ON/OFF]   [MINI-HUD GHOST]  |
+-------------------------------------------------------------+---------------------------+
| TABS: [CHAT STREAM] [OS AGENT] [MEETINGS] [API VAULT]       |    ARC TELEMETRY GAUGES   |
|       [SKILLS & MCP] [SYSTEM & ALARMS]                      |                           |
|                                                             |    ( CPU LOAD: 14.2% )    |
|  YOU [TEXT / VOICE]                                         |    ( RAM USAGE: 42.1% )   |
|  "Open Chrome and navigate to GitHub"                       |    ( BATTERY: 95% AC )    |
|                                                             |                           |
|  J.A.R.V.I.S. [TIER 1/3 ACTUATOR]                           |   NEXT SCHEDULED MEETING  |
|  "Launching Chrome and navigating to repository, sir."      |   "Team Sprint Sync"      |
|                                                             |   Today at 3:00 PM        |
|  [SET-OF-MARK VISION PREVIEW: Active Arc Cyan Tags]         |   [ Join Now Button ]     |
|                                                             |                           |
+-------------------------------------------------------------+---------------------------+
| [Type a command, query, or script...                                 ]  [ EXECUTE ]     |
+-----------------------------------------------------------------------------------------+
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Marvel Holographic HUD** | Pure geometric Arc Cyan (`#00E5FF`) and Reactor Gold HUD built with React, Vite, and Tailwind CSS |
| **Native PyWebView Container** | Frameless, modern native desktop window with browser fallback at `http://127.0.0.1:5050` |
| **FastAPI + WebSocket Engine** | Real-time bi-directional telemetry and command streaming on port 5050 |
| **Multi-Key API Vault** | Hot-swappable key rotation across Gemini, Groq, Anthropic, OpenRouter, and Ollama with custom OpenAI endpoints |
| **3-Tier Dynamic OS Agent** | Tier 1 Safe Sandboxed Python, Tier 2 MCP Tools, and Tier 3 Set-of-Mark (SoM) Vision Actuator |
| **Safety Interceptor** | Cryptographic confirmation prompts with countdown timer for potentially destructive OS actions |
| **Automated Meeting Attendant** | Headed Playwright browser attendant with live caption feed, auto-mute interlock, and AI post-meeting summaries |
| **Workspace RAG & Copilot** | Local codebase indexing, semantic search, and clipboard summarization/bug fixing |
| **Custom Voice Skills & MCP** | Interactive "Teach Mode" voice macro recorder and dynamic MCP server registry |
| **Cross-Platform Shortcut** | One-click desktop launcher generator for Windows (.lnk & .bat), Linux (.desktop), and macOS |

---

## Quick Start

### 1. Prerequisites

- **Python 3.10+**
- **Node.js 18+** & npm (for UI compilation)
- **Google Chrome** installed (for meeting automation)
- Microphone and speakers/headphones

### 2. Installation

```bash
git clone https://github.com/yourusername/JARVIS.git
cd JARVIS

# Python dependencies
pip install -r requirements.txt
python -m playwright install chromium

# Frontend HUD build
cd ui
npm install
npm run build
cd ..
```

### 3. Launch Modes

#### Default: Native Desktop Holographic HUD
```bash
python main.py
```
Launches the FastAPI backend and opens the native PyWebView frameless window (1360x860) with auto-fallback to `http://127.0.0.1:5050`.

#### Headless / Terminal CLI Mode
```bash
python main.py --cli
```
Runs in terminal-only mode for command-line operators (type commands, `exit` to quit).

---

## Generating Desktop Application Icon & Shortcut

To programmatically generate the geometric Arc-Cyan HUD icon (`jarvis.png` / `jarvis.ico`) and install native desktop launchers:

```bash
python scripts/create_desktop_icon.py
```

- **Arc-Cyan HUD Icon:** Programmatically rendered via Pillow at 1024x1024 supersampling with concentric segmented arcs, tick-marks, and central reactor core (`ui/assets/jarvis.ico` and `ui/assets/jarvis.png`).
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
