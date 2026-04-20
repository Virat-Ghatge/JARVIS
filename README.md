# JARVIS Voice Assistant

> **Just A Rather Very Intelligent System**

A Python-based voice assistant inspired by Tony Stark's AI companion from Iron Man. JARVIS listens to your voice commands and helps you with daily tasks.

---

## Features

| Feature | Description |
|---------|-------------|
| **Hybrid AI Mode** | Smart commands use AI, simple ones use fast local handlers |
| **Offline Fallback** | Works without internet using local handlers |
| **Time & Date** | Ask for current time, date, or day |
| **Weather** | Get real-time weather updates for any city |
| **Music** | Play music from YouTube, Spotify, or local files |
| **Web Search** | Search Google with voice commands |
| **Applications** | Open system applications hands-free |
| **Alarms** | Set reminders and alarms |
| **Natural Language** | Talk naturally - "I'm bored, play something upbeat" |

---

## Quick Start

### Prerequisites

- Python 3.7 or higher
- Microphone for voice input
- Internet connection (for speech recognition and web features)

### Installation

1. **Clone the repository**
   \`\`\`bash
   git clone https://github.com/yourusername/jarvis-assistant.git
   cd jarvis-assistant
   \`\`\`

2. **Install dependencies**
   \`\`\`bash
   pip install -r requirements.txt
   \`\`\`

   **Note:** PyAudio may require additional setup:
   - **Windows:** \`pip install pipwin && pipwin install pyaudio\`
   - **macOS:** \`brew install portaudio && pip install pyaudio\`
   - **Linux:** \`sudo apt-get install python3-pyaudio\`

3. **Configure API Keys**
   \`\`\`bash
   cp .env.example .env
   \`\`\`
   Edit \`.env\` and add your API keys:
   \`\`\`
   # Weather (optional, for weather feature)
   WEATHER_API_KEY=your_weather_api_key_here

   # Gemini AI (optional, for AI-powered responses)
   GEMINI_API_KEY=your_gemini_api_key_here
   \`\`\`
   - [Get Weather API key](https://openweathermap.org/api)
   - [Get Gemini API key (free)](https://aistudio.google.com/app/apikey)

4. **Run JARVIS**
   \`\`\`bash
   python main.py
   \`\`\`

---

## Voice Commands

### Quick Commands (Instant - No AI needed)

| Command | What It Does |
|---------|--------------|
| "What time is it?" | Tells current time |
| "What's the date?" | Tells today's date |
| "Open Chrome" / "Open Spotify" | Opens applications |
| "What's the weather in London?" | Weather update |
| "Play some music" | Starts music |
| "Search for Python tutorials" | Google search |
| "Set alarm for 7 AM" | Sets alarm |
| "Hello" / "How are you?" | Greeting |
| "Goodbye" / "Exit" | Shutdown |

### Natural Language (Uses AI - Needs API key)

Any command not in the list above goes to Gemini AI:

| Example | What Happens |
|---------|--------------|
| "I'm bored, play something upbeat" | AI → play_music |
| "Who is the CEO of Google?" | AI → web_search |
| "Tell me a joke" | AI responds directly |
| "What do you think about AI?" | AI responds directly |

**Note:** AI commands need internet and `GEMINI_API_KEY` in `.env` file.

---

## How It Works

JARVIS uses a simple **two-step** approach:

1. **Check Local Commands First** - Direct keyword matching for speed
2. **Ask AI If Needed** - Falls back to Gemini for anything else

### Command Flow

```
User speaks
    ↓
Direct match? (time, date, open, weather, etc.)
    ↓ Yes → Execute instantly (~1 second)
    ↓ No
Check AI available?
    ↓ Yes → Ask Gemini to choose command → Execute (~3-4 seconds)
    ↓ No
Suggest available commands
```

### Why This Works

- **Fast**: Common commands execute immediately
- **Smart**: AI understands natural language like "play something upbeat"
- **Simple**: Easy to add new commands
- **Free**: Uses Gemini's generous free tier (1,500 requests/day)

## Project Structure

\`\`\`
jarvis-assistant/
├── main.py              # Entry point - run this file
├── core.py              # Main JARVIS class with simple routing
├── date_time.py         # Time & date handler
├── applications.py      # Application launcher
├── music.py             # Music player (YouTube, Spotify, local)
├── web_search.py        # Google search handler
├── alarm.py             # Alarm & reminder handler
├── weather.py           # Weather API handler
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variables template
├── .gitignore          # Git ignore rules
└── README.md            # This file
\`\`\`

---

## Configuration

### Environment Variables

Copy \`.env.example\` to \`.env\` and configure:

| Variable | Required | Description |
|----------|----------|-------------|
| \`WEATHER_API_KEY\` | Optional | OpenWeatherMap API key for weather features |

### Customization

You can customize JARVIS behavior in \`core.py\`:

- **Speech Rate:** Adjust \`engine.setProperty('rate', 175)\`
- **Voice:** Change voice selection in the \`__init__\` method
- **Listening Timeout:** Modify \`timeout\` and \`phrase_time_limit\` in \`listen()\`

---

## Security

- **Never commit your \`.env\` file** - it contains private API keys
- The \`.env\` file is automatically ignored by Git (see \`.gitignore\`)
- Use \`.env.example\` as a template for other developers

---

## Technologies Used

| Technology | Purpose | Free Tier |
|------------|---------|-----------|
| **Python 3.7+** | Core language | Free |
| **SpeechRecognition** | Speech-to-text | Free |
| **pyttsx3** | Text-to-speech | Free |
| **Google Gemini** | AI language model | 1,500 req/day |
| **OpenWeatherMap** | Weather data | 1,000 calls/day |
| **requests** | HTTP requests | Free |
| **python-dotenv** | Environment management | Free |

**Total cost to run: $0** (with free tiers)

---

## License

This project is open source and available under the MIT License.

---

## Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest new features
- Submit pull requests

---

## Acknowledgments

Inspired by J.A.R.V.I.S. from the Marvel Cinematic Universe's Iron Man series.

---

**Made with Python**
