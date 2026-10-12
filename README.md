# JARVIS Voice Assistant

> **Just A Rather Very Intelligent System**

A Python-based voice assistant inspired by Tony Stark's AI companion from Iron Man. JARVIS listens to your voice commands, manages scheduled meetings, controls system settings, and assists with daily tasks using a hybrid offline-first and AI-powered engine.

---

## Features

| Feature | Description |
|---------|-------------|
| **Meeting Attendant** | Automatically joins, monitors, and leaves Google Meet & Microsoft Teams calls |
| **Meeting Dashboard** | Modern web interface (`http://localhost:5050`) to view, add, and manage meeting schedules |
| **Hybrid AI Routing** | Instant execution for local commands; Gemini & Groq LLMs for natural language queries |
| **Offline Fallback** | Core functions (time, apps, system controls, meetings) work seamlessly without internet |
| **System Controls** | Voice control for system volume, brightness, and audio mute/unmute |
| **System Info** | Real-time monitoring of battery percentage, charging state, and CPU load |
| **Knowledge & Q&A** | High-speed answers powered by Groq (Llama 3.1) and Gemini with local caching |
| **Time & Date** | Current time, date, day of week, and time zone inquiries |
| **Weather** | Real-time weather forecasts and conditions via OpenWeatherMap |
| **Music Playback** | Voice-controlled playback on YouTube, Spotify, or local audio files |
| **Web Search** | Hands-free Google searches with summarized results |
| **Applications** | Launch, switch, and close system desktop applications |
| **Alarms & Reminders**| Set voice alarms, timers, and scheduled notifications |

---

## Quick Start

### Prerequisites

- **Python 3.8+** (Required by Playwright)
- **Google Chrome** installed (used for meeting automation)
- Microphone and speakers/headphones
- Internet connection (for AI features, speech recognition, and web features)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/jarvis-assistant.git
   cd jarvis-assistant
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

   *Platform note for PyAudio (if not installed automatically):*
   - **Windows:** `pip install pipwin && pipwin install pyaudio`
   - **macOS:** `brew install portaudio && pip install pyaudio`
   - **Linux:** `sudo apt-get install python3-pyaudio`

3. **Install Playwright browser binaries**
   ```bash
   python -m playwright install chromium
   ```

4. **One-Time Meeting Account Setup (Recommended)**
   To enable seamless auto-join for Google Meet and Microsoft Teams without repeated 2FA or login prompts:
   ```bash
   python -m modules.meeting_bot --setup
   ```
   This launches Chrome using JARVIS's persistent profile (`.browser_profile/`). Sign into your Google and Microsoft accounts once and close the browser. All sessions and cookies are saved locally.

5. **Configure Environment Variables**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to configure your keys and preferences:
   ```env
   # Weather (optional, for weather forecasts)
   WEATHER_API_KEY=your_weather_api_key_here

   # Gemini AI (optional, for AI-powered intent routing)
   GEMINI_API_KEY=your_gemini_api_key_here

   # Groq API (optional, for ultra-fast Q&A with Llama 3.1)
   GROQ_API_KEY=your_groq_api_key_here

   # Meeting Schedule Web Dashboard
   MEETING_DASHBOARD_PORT=5050
   MEETING_DASHBOARD_HOST=127.0.0.1
   ```
   - [Get Weather API key](https://openweathermap.org/api)
   - [Get Gemini API key (free)](https://aistudio.google.com/app/apikey)
   - [Get Groq API key (free)](https://console.groq.com)

6. **Run JARVIS**
   ```bash
   python main.py
   ```

---

## Automated Meeting Attendant

JARVIS includes a fully automated meeting attendant for **Google Meet** and **Microsoft Teams**.

### How It Works

```
Schedule Stored (config/meetings.json)
       ↓
APScheduler triggers ~60s before start time
       ↓
Playwright launches Chrome with persistent profile (.browser_profile)
       ↓
Navigates to Meet / Teams link
       ↓
Auto-mutes microphone & disables camera
       ↓
Clicks "Join Now" / "Ask to Join"
       ↓
Monitors call status (participant count & scheduled end time)
       ↓
Leaves call automatically when meeting concludes or room empties
```

### Features

- **Mic & Camera Auto-Off**: Always turns off camera and mutes microphone before entering.
- **Headless & Headed Safety**: Runs headed in Chrome with persistent session state so you can observe the call.
- **Smart Exit**: Automatically clicks the "Leave" button when the scheduled end time is reached or when other participants leave.
- **Web Dashboard**: An integrated dashboard served at `http://localhost:5050` featuring:
  - Live timeline of upcoming and past meetings
  - Quick-add form with natural language time parsing
  - Bulk JSON import and export
  - Instant manual "Join" and "Cancel" buttons

---

## Voice Commands

### Meeting Commands

| Command | Action |
|---------|--------|
| *"Schedule meeting Project Sync at 3 PM https://meet.google.com/xxx-yyyy-zzz"* | Schedules a meeting with auto-join |
| *"What meetings do I have today?"* / *"List my meetings"* | Reads out upcoming scheduled meetings |
| *"Cancel meeting Project Sync"* | Cancels a scheduled meeting |
| *"Join meeting Project Sync"* | Immediately joins a meeting by title |
| *"Join meeting https://teams.microsoft.com/..."* | Immediately joins a meeting by URL |
| *"Leave meeting"* | Disconnects and leaves the active meeting |
| *"Open meeting dashboard"* | Opens the web dashboard in your browser |

### Quick Local Commands (Instant - No AI Latency)

| Command | What It Does |
|---------|--------------|
| *"What time is it?"* | Speaks the current time |
| *"What is today's date?"* | Speaks today's date |
| *"Set volume to 50%"* / *"Mute volume"* | Adjusts system audio |
| *"Set brightness to 80%"* | Adjusts display brightness |
| *"Check battery"* / *"System status"* | Reports battery percentage & CPU load |
| *"Open Chrome"* / *"Open Spotify"* | Launches applications |
| *"What's the weather in London?"* | Real-time weather update |
| *"Play some music"* / *"Play lo-fi on YouTube"* | Starts music streaming |
| *"Search for Python tutorials"* | Conducts Google search |
| *"Set alarm for 7 AM"* | Sets an alarm |
| *"Hello"* / *"How are you?"* | Speaks greeting |
| *"Goodbye"* / *"Exit"* | Shuts down JARVIS |

### Natural Language (AI-Powered)

Any complex request not matched locally is analyzed by Gemini / Groq:

| Example | Action Taken |
|---------|--------------|
| *"I have a team standup tomorrow at 10 AM on Google Meet, link is..."* | AI schedules the meeting |
| *"I'm feeling tired, play something relaxing"* | AI selects music query |
| *"Explain quantum computing in simple terms"* | AI answers via Groq/Gemini |
| *"Who directed Interstellar?"* | AI answers question directly |

---

## Project Structure

```
jarvis-assistant/
├── main.py                     # Entry point - initializes and starts JARVIS
├── core.py                     # Central assistant engine & intent routing
├── meeting_handler.py          # Voice command handler for meetings
├── system_controls.py          # System volume & display brightness controls
├── system_info.py              # Battery status and CPU monitoring
├── qa_handler.py               # Groq & Gemini knowledge Q&A engine
├── date_time.py                # Time & date handler
├── applications.py             # Application launcher
├── music.py                    # Music player (YouTube, Spotify, local files)
├── web_search.py               # Google web search handler
├── alarm.py                    # Alarm & reminder handler
├── weather.py                  # OpenWeatherMap API integration
├── modules/
│   ├── __init__.py             # Modules package definition
│   ├── meeting_bot.py          # Playwright browser automation (Meet & Teams)
│   ├── meeting_scheduler.py    # APScheduler & JSON schedule persistence
│   └── schedule_interface.py   # FastAPI meeting dashboard & REST API
├── config/
│   └── meetings.json           # Persistent meeting schedules storage
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules (protects credentials & profile)
└── README.md                   # Project documentation
```

---

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `WEATHER_API_KEY` | Optional | - | OpenWeatherMap API key for weather data |
| `GEMINI_API_KEY` | Optional | - | Google Gemini API key for smart intent parsing |
| `GROQ_API_KEY` | Optional | - | Groq API key for ultra-fast Llama 3.1 Q&A responses |
| `MEETING_DASHBOARD_PORT` | Optional | `5050` | Port for the local meeting web interface |
| `MEETING_DASHBOARD_HOST` | Optional | `127.0.0.1` | Host address for the meeting web interface |
| `JARVIS_FORCE_ONLINE` | Optional | `false` | Force online mode if internet check gives false negatives |

### Customization

You can customize JARVIS settings in `core.py`:

- **Voice & Speech Engine:** Configure `edge-tts` voice (e.g., `en-GB-RyanNeural` or `en-US-GuyNeural`) or fallback `pyttsx3`
- **Speech Rate:** Adjust speech properties in `core.py`
- **Listening Timeout:** Modify `timeout` and `phrase_time_limit` parameters in `listen()`

---

## Technologies Used

| Technology | Purpose | Free Tier / License |
|------------|---------|---------------------|
| **Python 3.8+** | Core programming language | Open Source |
| **Playwright** | Browser automation for Meet & Teams | Open Source |
| **APScheduler** | Robust in-process background scheduling | Open Source |
| **FastAPI & Uvicorn** | Meeting dashboard web app and REST API | Open Source |
| **Google Gemini** | Natural language intent classification | 1,500 req/day |
| **Groq (Llama 3.1)** | Low-latency conversational Q&A | 14,400 req/day |
| **edge-tts / pyttsx3** | High-quality neural and offline speech synthesis | Free / Open Source |
| **SpeechRecognition** | Voice command recognition (Google Speech API) | Free |
| **OpenWeatherMap** | Real-time weather data | 1,000 calls/day |

---

## Security & Privacy

- **Protected Credentials**: Never commit your `.env` file or `.browser_profile/` directory. Both are listed in `.gitignore`.
- **Local Storage**: Meeting details and browser cookies are stored exclusively on your local machine (`config/meetings.json` and `.browser_profile/`).

---

## Contributing

Contributions are welcome! Feel free to:
- Report bugs and edge cases
- Suggest new integrations or voice commands
- Submit pull requests

---

## License

This project is open source and available under the [MIT License](LICENSE).

---

## Acknowledgments

Inspired by J.A.R.V.I.S. from Marvel's Iron Man.
