#!/usr/bin/env python3
"""
Music Module
Handles music playback functionality on various platforms with structured telemetry.
"""

import os
import webbrowser
import subprocess
import re
import time
from pathlib import Path
from urllib.parse import quote
from typing import Dict, Any, Optional

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
    """Handles music playback on Spotify, YouTube, YouTube Music with state tracking and telemetry."""

    def __init__(self, jarvis: Optional[Any] = None) -> None:
        self.jarvis: Optional[Any] = jarvis
        self.current_state: Dict[str, Any] = {
            "song": "",
            "platform": "default",
            "state": "stopped",
        }

    def play_music(self, command: str) -> Dict[str, Any]:
        """
        Play music on specified platform
        Examples:
        - "play attention on spotify"
        - "play shape of you on youtube"
        - "play blinding lights on yt music"
        - "play some music" (opens default)
        """
        command_clean = command.lower().strip()

        # Extract platform and song name
        platform = self._detect_platform(command_clean)
        song_name = self._extract_song_name(command_clean, platform)

        print(f"[Music] Platform: {platform}, Song: {song_name}")

        # Route to appropriate playback executor
        if platform == "spotify":
            self._play_spotify(song_name)
        elif platform == "youtube_music":
            self._play_youtube_music(song_name)
        elif platform == "youtube":
            self._play_youtube(song_name)
        else:
            self._play_default(song_name)

        display_name = song_name if song_name else "music"
        reply = (
            f"Playing {display_name} on {platform}, sir."
            if song_name
            else f"Opening {platform}, sir."
        )

        self.current_state = {
            "song": song_name,
            "platform": platform,
            "state": "playing",
        }

        self._broadcast_state()

        return {
            "reply": reply,
            "action": "play_music",
            "data": {
                "song": song_name,
                "platform": platform,
                "state": "playing",
            },
        }

    def control_playback(self, action: str) -> Dict[str, Any]:
        """
        Control playback for play, pause, play_pause, next, previous, stop
        """
        act = action.lower().strip()

        if act in ("pause", "stop", "halt"):
            norm_action = "stop" if act in ("stop", "halt") else "pause"
            new_state = "stopped" if act in ("stop", "halt") else "paused"
        elif act in ("play", "resume", "continue", "start"):
            norm_action = "play"
            new_state = "playing"
        elif act in ("next", "skip", "forward"):
            norm_action = "next"
            new_state = "playing"
        elif act in ("previous", "prev", "back", "last"):
            norm_action = "previous"
            new_state = "playing"
        elif act in ("play_pause", "toggle"):
            norm_action = "play_pause"
            new_state = "paused" if self.current_state.get("state") == "playing" else "playing"
        else:
            norm_action = act
            new_state = self.current_state.get("state", "paused")

        success = self.control_spotify(norm_action)
        if success:
            self._speak_control_feedback(norm_action)

        self.current_state["state"] = new_state
        self._broadcast_state()

        feedback = {
            "play": "Resuming playback, sir.",
            "pause": "Music paused, sir.",
            "play_pause": "Playback toggled, sir.",
            "next": "Skipping to next track, sir.",
            "previous": "Going back to previous track, sir.",
            "stop": "Stopping music, sir.",
        }
        reply = feedback.get(norm_action, f"Playback {norm_action} executed, sir.")

        return {
            "reply": reply,
            "action": "music_control",
            "data": {
                "action": norm_action,
                "state": new_state,
                "song": self.current_state.get("song", ""),
                "platform": self.current_state.get("platform", "default"),
                "success": bool(success),
            },
        }

    def get_playback_state(self) -> Dict[str, Any]:
        """Returns the current playback state dictionary."""
        return dict(self.current_state)

    def _broadcast_state(self) -> None:
        """Broadcasts MUSIC_STATE_CHANGED over WebSocket and to Jarvis chat listeners."""
        payload = {
            "song": self.current_state.get("song", ""),
            "platform": self.current_state.get("platform", "default"),
            "state": self.current_state.get("state", "stopped"),
        }
        try:
            from automation.server import broadcast_ws_sync
            broadcast_ws_sync("MUSIC_STATE_CHANGED", payload)
        except Exception:
            pass

        if self.jarvis and hasattr(self.jarvis, "_emit_chat"):
            try:
                self.jarvis._emit_chat(
                    role="assistant",
                    content="",
                    meta={"action": "music_state", "data": payload},
                )
            except Exception:
                pass

    def _detect_platform(self, command: str) -> str:
        """Detect which platform user wants"""
        if "spotify" in command:
            return "spotify"
        elif "yt music" in command or "ytmusic" in command or "youtube music" in command:
            return "youtube_music"
        elif "youtube" in command or "yt" in command:
            return "youtube"
        return "default"

    def _extract_song_name(self, command: str, platform: str) -> str:
        """Extract song name from command"""
        name = command
        prefixes = ["play", "the song", "the track", "music"]
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):].strip()

        platform_words = [
            "on spotify", "on youtube", "on yt music", "on ytmusic",
            "on youtube music", "on yt", "from spotify", "from youtube"
        ]
        for word in platform_words:
            name = name.replace(word, "").strip()

        name = name.strip("\"'")
        return name if name else ""

    def _play_spotify(self, song_name: str) -> None:
        """Play on Spotify - tries desktop app first, falls back to web"""
        if song_name:
            encoded = quote(song_name)
            try:
                spotify_uri = f"spotify:search:{encoded}"
                subprocess.Popen(["explorer", spotify_uri], shell=True)
                time.sleep(1)

                if not self._is_spotify_running():
                    self._open_spotify_app()

                if self.jarvis and hasattr(self.jarvis, "speak"):
                    self.jarvis.speak(f"Searching for {song_name} on Spotify desktop, sir.")
            except Exception:
                webbrowser.open(f"https://open.spotify.com/search/{encoded}")
                if self.jarvis and hasattr(self.jarvis, "speak"):
                    self.jarvis.speak(f"Opening Spotify web for {song_name}, sir.")
        else:
            if not self._open_spotify_app():
                webbrowser.open("https://open.spotify.com/")
                if self.jarvis and hasattr(self.jarvis, "speak"):
                    self.jarvis.speak("Opening Spotify web, sir.")
            else:
                if self.jarvis and hasattr(self.jarvis, "speak"):
                    self.jarvis.speak("Opening Spotify, sir.")

    def _open_spotify_app(self) -> bool:
        """Try to open Spotify desktop app"""
        try:
            methods = [
                ["start", "spotify"],
                ["cmd", "/c", "start", "spotify"],
                ["explorer", "spotify:"],
            ]
            for method in methods:
                try:
                    subprocess.Popen(method, shell=True)
                    return True
                except Exception:
                    continue

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
        except Exception:
            return False

    def _is_spotify_running(self) -> bool:
        """Check if Spotify is currently running"""
        if not PSUTIL_AVAILABLE:
            return True
        try:
            for proc in psutil.process_iter(["name"]):
                if proc.info["name"] and "spotify" in proc.info["name"].lower():
                    return True
            return False
        except Exception:
            return True

    def _play_youtube_music(self, song_name: str) -> None:
        """Play on YouTube Music"""
        if song_name:
            encoded = quote(song_name)
            url = f"https://music.youtube.com/search?q={encoded}"
            webbrowser.open(url)
            if self.jarvis and hasattr(self.jarvis, "speak"):
                self.jarvis.speak(f"Searching for {song_name} on YouTube Music, sir.")
        else:
            webbrowser.open("https://music.youtube.com/")
            if self.jarvis and hasattr(self.jarvis, "speak"):
                self.jarvis.speak("Opening YouTube Music, sir.")

    def _play_youtube(self, song_name: str) -> None:
        """Play on YouTube"""
        if song_name:
            encoded = quote(song_name)
            url = f"https://www.youtube.com/results?search_query={encoded}"
            webbrowser.open(url)
            if self.jarvis and hasattr(self.jarvis, "speak"):
                self.jarvis.speak(f"Searching for {song_name} on YouTube, sir.")
        else:
            webbrowser.open("https://www.youtube.com/")
            if self.jarvis and hasattr(self.jarvis, "speak"):
                self.jarvis.speak("Opening YouTube, sir.")

    def _play_default(self, song_name: str) -> None:
        """Default: try local music first, then Spotify"""
        if song_name:
            self._play_youtube(song_name)
            return

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
                    if self.jarvis and hasattr(self.jarvis, "speak"):
                        self.jarvis.speak("Opening your music folder, sir.")
                    music_found = True
                    break
                except Exception:
                    pass

        if not music_found:
            webbrowser.open("https://open.spotify.com/")
            if self.jarvis and hasattr(self.jarvis, "speak"):
                self.jarvis.speak("Opening Spotify for you, sir.")

    def _open_app(self, app_name: str) -> bool:
        """Try to open a desktop application"""
        try:
            subprocess.Popen(["start", "", app_name], shell=True)
            return True
        except Exception:
            return False

    def control_spotify(self, action: str) -> bool:
        """
        Control playback using Windows media keys.
        Supports play, pause, play_pause, next, previous, stop, volume_up, volume_down.
        """
        if not WINDOWS_AVAILABLE:
            if self.jarvis and hasattr(self.jarvis, "speak"):
                self.jarvis.speak("Media control requires Windows, sir.")
            return True

        VK_MEDIA_PLAY_PAUSE = 0xB3
        VK_MEDIA_NEXT_TRACK = 0xB0
        VK_MEDIA_PREV_TRACK = 0xB1
        VK_MEDIA_STOP = 0xB2

        try:
            if action in ("play", "pause", "play_pause"):
                self._send_media_key(VK_MEDIA_PLAY_PAUSE)
                return True
            elif action == "next":
                self._send_media_key(VK_MEDIA_NEXT_TRACK)
                return True
            elif action in ("previous", "prev"):
                self._send_media_key(VK_MEDIA_PREV_TRACK)
                return True
            elif action == "stop":
                self._send_media_key(VK_MEDIA_STOP)
                return True
            elif action == "volume_up":
                self._send_media_key(0xAF)
                return True
            elif action == "volume_down":
                self._send_media_key(0xAE)
                return True
            else:
                return False
        except Exception as e:
            print(f"[Music] Media control error: {e}")
            return False

    def _send_media_key(self, vk_code: int) -> None:
        """Send a media key press to Windows"""
        try:
            user32 = ctypes.windll.user32
            user32.keybd_event(vk_code, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(vk_code, 0, 2, 0)
        except Exception as e:
            print(f"[Music] Key send error: {e}")

    def process_control_command(self, command: str) -> bool:
        """
        Process playback control commands
        Examples:
        - "pause music"
        - "play next song"
        - "previous track"
        - "resume"
        """
        command_clean = command.lower().strip()

        play_keywords = ["play", "resume", "continue", "start"]
        pause_keywords = ["pause", "stop"]
        next_keywords = ["next", "skip", "forward"]
        prev_keywords = ["previous", "prev", "back", "last"]

        action: Optional[str] = None

        if any(kw in command_clean for kw in play_keywords):
            if "next" in command_clean or "forward" in command_clean:
                action = "next"
            elif "previous" in command_clean or "back" in command_clean:
                action = "previous"
            else:
                action = "play_pause"
        elif any(kw in command_clean for kw in pause_keywords):
            action = "play_pause"
        elif any(kw in command_clean for kw in next_keywords):
            action = "next"
        elif any(kw in command_clean for kw in prev_keywords):
            action = "previous"

        if action:
            res = self.control_playback(action)
            return bool(res.get("data", {}).get("success", True))

        return False

    def _speak_control_feedback(self, action: str) -> None:
        """Provide voice feedback for control actions"""
        feedback = {
            "play_pause": "Done, sir.",
            "play": "Resuming music, sir.",
            "pause": "Pausing music, sir.",
            "next": "Skipping to next track, sir.",
            "previous": "Going back to previous track, sir.",
            "stop": "Stopping music, sir.",
        }
        message = feedback.get(action, "Done, sir.")
        if self.jarvis and hasattr(self.jarvis, "speak"):
            self.jarvis.speak(message)


# Module-level singleton and helper functions for functional routing
music_handler: MusicHandler = MusicHandler(None)

def play_music(command: str) -> Dict[str, Any]:
    """Module-level entry point to play music."""
    return music_handler.play_music(command)

def control_playback(action: str) -> Dict[str, Any]:
    """Module-level entry point to control playback."""
    return music_handler.control_playback(action)

def control_music(action: str) -> Dict[str, Any]:
    """Alias for control_playback."""
    return music_handler.control_playback(action)

def handle_music(command: str) -> Dict[str, Any]:
    """Alias for play_music."""
    return music_handler.play_music(command)

def get_playback_state() -> Dict[str, Any]:
    """Module-level entry point to get current playback state."""
    return music_handler.get_playback_state()
