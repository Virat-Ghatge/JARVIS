#!/usr/bin/env python3
"""
Music Module
Handles music playback functionality on various platforms
"""

import os
import webbrowser
import subprocess
import re
import time
from pathlib import Path
from urllib.parse import quote

# Optional imports
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Windows media control
try:
    import ctypes
    from ctypes import wintypes
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False


class MusicHandler:
    """Handles music playback on Spotify, YouTube, YouTube Music"""

    def __init__(self, jarvis):
        self.jarvis = jarvis

    def play_music(self, command):
        """
        Play music on specified platform
        Examples:
        - "play attention on spotify"
        - "play shape of you on youtube"
        - "play blinding lights on yt music"
        - "play some music" (opens default)
        """
        command = command.lower().strip()

        # Extract platform and song name
        platform = self._detect_platform(command)
        song_name = self._extract_song_name(command, platform)

        print(f"[Music] Platform: {platform}, Song: {song_name}")

        # Route to appropriate handler
        if platform == 'spotify':
            self._play_spotify(song_name)
        elif platform == 'youtube_music':
            self._play_youtube_music(song_name)
        elif platform == 'youtube':
            self._play_youtube(song_name)
        else:
            # Default: try local music, fallback to Spotify
            self._play_default(song_name)

    def _detect_platform(self, command):
        """Detect which platform user wants"""
        # Check for platform mentions
        if 'spotify' in command:
            return 'spotify'
        elif 'yt music' in command or 'ytmusic' in command or 'youtube music' in command:
            return 'youtube_music'
        elif 'youtube' in command or 'yt' in command:
            return 'youtube'
        return 'default'

    def _extract_song_name(self, command, platform):
        """Extract song name from command"""
        # Remove common prefixes
        name = command
        prefixes = ['play', 'the song', 'the track', 'music']
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):].strip()

        # Remove platform mentions
        platform_words = ['on spotify', 'on youtube', 'on yt music', 'on ytmusic',
                         'on youtube music', 'on yt', 'from spotify', 'from youtube']
        for word in platform_words:
            name = name.replace(word, '').strip()

        # Clean up
        name = name.strip('"\'')

        return name if name else ''

    def _play_spotify(self, song_name):
        """Play on Spotify - tries desktop app first, falls back to web"""
        if song_name:
            encoded = quote(song_name)

            # Method 1: Try Spotify URI scheme (opens desktop app with search)
            try:
                spotify_uri = f"spotify:search:{encoded}"
                # Use explorer to handle the URI scheme
                subprocess.Popen(['explorer', spotify_uri], shell=True)

                # Wait a moment then check if Spotify is running
                time.sleep(1)

                # If URI didn't work, try opening Spotify app directly
                if not self._is_spotify_running():
                    self._open_spotify_app()

                self.jarvis.speak(f"Searching for {song_name} on Spotify desktop, sir.")

            except Exception as e:
                # Fallback to web
                webbrowser.open(f"https://open.spotify.com/search/{encoded}")
                self.jarvis.speak(f"Opening Spotify web for {song_name}, sir.")
        else:
            # Just open Spotify app
            if not self._open_spotify_app():
                webbrowser.open("https://open.spotify.com/")
                self.jarvis.speak("Opening Spotify web, sir.")
            else:
                self.jarvis.speak("Opening Spotify, sir.")

    def _open_spotify_app(self):
        """Try to open Spotify desktop app"""
        try:
            # Try multiple methods to open Spotify
            methods = [
                ['start', 'spotify'],  # Using start command
                ['cmd', '/c', 'start', 'spotify'],  # Alternative
                ['explorer', 'spotify:'],  # URI scheme
            ]

            for method in methods:
                try:
                    subprocess.Popen(method, shell=True)
                    return True
                except:
                    continue

            # Try to find Spotify in common install locations
            spotify_paths = [
                os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
                r"C:\Program Files\WindowsApps\SpotifyAB.SpotifyMusic_*\Spotify.exe",
            ]

            for path in spotify_paths:
                if os.path.exists(path):
                    subprocess.Popen([path])
                    return True

            return False
        except:
            return False

    def _is_spotify_running(self):
        """Check if Spotify is currently running"""
        if not PSUTIL_AVAILABLE:
            # If psutil not available, assume it might be running
            return True

        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and 'spotify' in proc.info['name'].lower():
                    return True
            return False
        except:
            return True

    def _play_youtube_music(self, song_name):
        """Play on YouTube Music"""
        if song_name:
            encoded = quote(song_name)
            url = f"https://music.youtube.com/search?q={encoded}"
            webbrowser.open(url)
            self.jarvis.speak(f"Searching for {song_name} on YouTube Music, sir.")
        else:
            webbrowser.open("https://music.youtube.com/")
            self.jarvis.speak("Opening YouTube Music, sir.")

    def _play_youtube(self, song_name):
        """Play on YouTube"""
        if song_name:
            encoded = quote(song_name)
            url = f"https://www.youtube.com/results?search_query={encoded}"
            webbrowser.open(url)
            self.jarvis.speak(f"Searching for {song_name} on YouTube, sir.")
        else:
            webbrowser.open("https://www.youtube.com/")
            self.jarvis.speak("Opening YouTube, sir.")

    def _play_default(self, song_name):
        """Default: try local music first, then Spotify"""
        if song_name:
            # If specific song requested but no platform, use YouTube (most likely to have it)
            self._play_youtube(song_name)
            return

        # Try local music folders
        music_paths = [
            str(Path.home() / "Music"),
            str(Path.home() / "Documents" / "Music"),
            str(Path.home() / "Downloads" / "Music"),
        ]

        music_found = False
        for path in music_paths:
            if os.path.exists(path):
                try:
                    os.startfile(path)
                    self.jarvis.speak("Opening your music folder, sir.")
                    music_found = True
                    break
                except:
                    pass

        if not music_found:
            # Fallback to Spotify
            webbrowser.open("https://open.spotify.com/")
            self.jarvis.speak("Opening Spotify for you, sir.")

    def _open_app(self, app_name):
        """Try to open a desktop application"""
        try:
            subprocess.Popen(['start', '', app_name], shell=True)
            return True
        except:
            return False

    # Media Control Methods
    def control_spotify(self, action):
        """
        Control Spotify playback using Windows media keys
        Works globally - doesn't require Spotify to be focused
        """
        if not WINDOWS_AVAILABLE:
            if self.jarvis:
                self.jarvis.speak("Media control requires Windows, sir.")
            return False

        # Windows virtual key codes for media
        VK_MEDIA_PLAY_PAUSE = 0xB3
        VK_MEDIA_NEXT_TRACK = 0xB0
        VK_MEDIA_PREV_TRACK = 0xB1
        VK_MEDIA_STOP = 0xB2

        try:
            # Use keybd_event to simulate media keys
            user32 = ctypes.windll.user32

            if action == 'play' or action == 'pause' or action == 'play_pause':
                self._send_media_key(VK_MEDIA_PLAY_PAUSE)
                return True
            elif action == 'next':
                self._send_media_key(VK_MEDIA_NEXT_TRACK)
                return True
            elif action == 'previous' or action == 'prev':
                self._send_media_key(VK_MEDIA_PREV_TRACK)
                return True
            elif action == 'stop':
                self._send_media_key(VK_MEDIA_STOP)
                return True
            elif action == 'volume_up':
                self._send_media_key(0xAF)  # VK_VOLUME_UP
                return True
            elif action == 'volume_down':
                self._send_media_key(0xAE)  # VK_VOLUME_DOWN
                return True
            else:
                return False
        except Exception as e:
            print(f"Media control error: {e}")
            return False

    def _send_media_key(self, vk_code):
        """Send a media key press to Windows"""
        try:
            user32 = ctypes.windll.user32
            # Key down
            user32.keybd_event(vk_code, 0, 0, 0)
            time.sleep(0.1)
            # Key up
            user32.keybd_event(vk_code, 0, 2, 0)
        except Exception as e:
            print(f"Key send error: {e}")

    def process_control_command(self, command):
        """
        Process playback control commands
        Examples:
        - "pause music"
        - "play next song"
        - "previous track"
        - "resume"
        """
        command = command.lower().strip()

        # Map commands to actions
        play_keywords = ['play', 'resume', 'continue', 'start']
        pause_keywords = ['pause', 'stop']
        next_keywords = ['next', 'skip', 'forward']
        prev_keywords = ['previous', 'prev', 'back', 'last']

        action = None

        # Check for play/resume
        if any(kw in command for kw in play_keywords):
            if 'next' in command or 'forward' in command:
                action = 'next'
            elif 'previous' in command or 'back' in command:
                action = 'previous'
            else:
                action = 'play_pause'

        # Check for pause/stop
        elif any(kw in command for kw in pause_keywords):
            action = 'play_pause'

        # Check for next
        elif any(kw in command for kw in next_keywords):
            action = 'next'

        # Check for previous
        elif any(kw in command for kw in prev_keywords):
            action = 'previous'

        if action:
            success = self.control_spotify(action)
            if success:
                self._speak_control_feedback(action)
            return success

        return False

    def _speak_control_feedback(self, action):
        """Provide voice feedback for control actions"""
        feedback = {
            'play_pause': "Done, sir.",
            'next': "Skipping to next track, sir.",
            'previous': "Going back to previous track, sir.",
            'stop': "Stopping music, sir.",
        }
        message = feedback.get(action, "Done, sir.")
        if self.jarvis:
            self.jarvis.speak(message)
