#!/usr/bin/env python3
"""
Music Module
Handles music playback functionality
"""

import os
import webbrowser
from pathlib import Path


class MusicHandler:
    """Handles music playback"""

    def __init__(self, jarvis):
        self.jarvis = jarvis

    def play_music(self, command):
        """Play music - opens YouTube Music or local music"""
        if 'on youtube' in command or 'youtube' in command:
            query = command.replace('play', '').replace('music', '').replace('on youtube', '').strip()
            if query:
                url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
                webbrowser.open(url)
                self.jarvis.speak(f"Searching for {query} on YouTube")
            else:
                webbrowser.open("https://www.youtube.com/")
                self.jarvis.speak("Opening YouTube")
        else:
            # Try to open local music or Spotify
            music_paths = [
                str(Path.home() / "Music"),
                str(Path.home() / "Documents" / "Music"),
            ]

            music_found = False
            for path in music_paths:
                if os.path.exists(path):
                    try:
                        os.startfile(path)
                        self.jarvis.speak("Opening your music folder")
                        music_found = True
                        break
                    except:
                        pass

            if not music_found:
                # Fallback to Spotify web
                webbrowser.open("https://open.spotify.com/")
                self.jarvis.speak("Opening Spotify for you")
