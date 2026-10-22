#!/usr/bin/env python3
"""
Thread-Safe Voice Listener & Concurrency Manager for JARVIS 2.0
Wraps SpeechRecognition in a background worker thread with:
- Instant mic_active toggle controls (set_mic_active, get_mic_active, toggle_mic)
- Meeting Auto-Mute Interlock (on_meeting_state_change) with manual override
- Push-to-Talk hotkey listener support
- Headless and permission-safe microphone fallback
"""

import os
import sys
import time
import threading
from typing import Callable, Optional

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

from config.settings import MIC_TIMEOUT, MIC_PHRASE_TIME_LIMIT, get_active_key


class VoiceListener:
    """
    Background worker managing microphone ingestion, meeting auto-mute,
    and voice command dispatching.
    """

    def __init__(
        self,
        on_command: Optional[Callable[[str], None]] = None,
        on_status_change: Optional[Callable[[bool, str], None]] = None,
        on_meeting_alert: Optional[Callable[[str, str], None]] = None,
    ):
        self.on_command = on_command
        self.on_status_change = on_status_change
        self.on_meeting_alert = on_meeting_alert

        # Thread synchronization
        self._lock = threading.Lock()
        self._active_event = threading.Event()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._ptt_listener = None

        # State flags
        self._mic_active: bool = False
        self.in_meeting: bool = False
        self.meeting_auto_muted: bool = False
        self.manual_override: bool = False

        # Speech recognition components
        self.recognizer = sr.Recognizer() if SR_AVAILABLE else None
        if self.recognizer:
            self.recognizer.energy_threshold = 4000
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8

        # Start worker thread
        self.start()

    # ── State Controls ────────────────────────────────────────────────
    @property
    def mic_active(self) -> bool:
        with self._lock:
            return self._mic_active

    def get_mic_active(self) -> bool:
        """Return True if microphone is actively listening."""
        with self._lock:
            return self._mic_active

    def set_mic_active(self, active: bool) -> None:
        """Explicitly set mic listening state."""
        with self._lock:
            self._mic_active = bool(active)
            if self._mic_active:
                self._active_event.set()
                if self.in_meeting:
                    self.manual_override = True
                    self.meeting_auto_muted = False
            else:
                self._active_event.clear()

        if self.on_status_change:
            msg = "Microphone active" if active else "Microphone muted"
            self.on_status_change(active, msg)

    def toggle_mic(self) -> bool:
        """Toggle microphone state and return new state."""
        new_state = not self.get_mic_active()
        self.set_mic_active(new_state)
        return new_state

    # Aliases for backward compatibility
    def is_active(self) -> bool:
        return self.get_mic_active()

    def enable(self, manual_override: bool = False):
        self.set_mic_active(True)

    def disable(self, auto_meeting: bool = False):
        if auto_meeting:
            with self._lock:
                self.meeting_auto_muted = True
                self.manual_override = False
        self.set_mic_active(False)

    def toggle(self) -> bool:
        return self.toggle_mic()

    @property
    def auto_muted_by_meeting(self) -> bool:
        return self.meeting_auto_muted

    @auto_muted_by_meeting.setter
    def auto_muted_by_meeting(self, val: bool) -> None:
        self.meeting_auto_muted = val

    # ── Meeting Auto-Mute Interlock ───────────────────────────────────
    def on_meeting_state_change(self, in_meeting: bool, meeting_title: str = "Online Meeting") -> None:
        """
        Meeting Interlock:
        When in_meeting is True: automatically mute microphone (meeting_auto_muted = True),
        while allowing manual unmute override via set_mic_active(True).
        When in_meeting is False: restore mic listening if it was auto-muted and not overridden.
        """
        with self._lock:
            self.in_meeting = in_meeting

        if in_meeting:
            was_active = self.get_mic_active()
            if was_active:
                with self._lock:
                    self.meeting_auto_muted = True
                    self.manual_override = False
                self.set_mic_active(False)
                print(f"[AudioInterlock] Auto-muted microphone for meeting: {meeting_title}")
            else:
                with self._lock:
                    self.meeting_auto_muted = False
                    self.manual_override = False

            if self.on_meeting_alert:
                self.on_meeting_alert("joined", meeting_title)
        else:
            should_restore = False
            with self._lock:
                if self.meeting_auto_muted and not self.manual_override:
                    should_restore = True
                self.meeting_auto_muted = False
                self.manual_override = False

            if should_restore:
                print(f"[AudioInterlock] Meeting left ({meeting_title}). Restoring microphone.")
                self.set_mic_active(True)
            else:
                print(f"[AudioInterlock] Meeting left ({meeting_title}). Retaining microphone state.")

            if self.on_meeting_alert:
                self.on_meeting_alert("left", meeting_title)

    def handle_meeting_joined(self, meeting_title: str = "Online Meeting"):
        self.on_meeting_state_change(True, meeting_title)

    def handle_meeting_left(self, meeting_title: str = "Online Meeting"):
        self.on_meeting_state_change(False, meeting_title)

    # ── Push-To-Talk Hotkey Listener ──────────────────────────────────
    def start_push_to_talk(self, hotkey_str: str = "<ctrl>+<shift>+<space>") -> bool:
        """Registers global background hotkey listener for Push-to-Talk."""
        try:
            from pynput import keyboard

            def on_activate():
                print("[VoiceListener] Push-to-Talk hotkey triggered!")
                self.toggle_mic()

            self._ptt_listener = keyboard.GlobalHotKeys({
                hotkey_str: on_activate
            })
            self._ptt_listener.daemon = True
            self._ptt_listener.start()
            return True
        except Exception as e:
            print(f"[VoiceListener] Push-to-talk hotkey registration warning: {e}")
            return False

    def stop_push_to_talk(self) -> None:
        """Stops Push-to-Talk listener if active."""
        if self._ptt_listener:
            try:
                self._ptt_listener.stop()
            except Exception:
                pass
            self._ptt_listener = None

    # ── Thread Lifecycle ──────────────────────────────────────────────
    def start(self) -> None:
        """Start the background worker thread."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._listen_worker,
                daemon=True,
                name="VoiceListener-Worker",
            )
            self._worker_thread.start()

    def stop(self) -> None:
        """Terminate the background worker thread."""
        self._stop_event.set()
        self._active_event.set()
        self.stop_push_to_talk()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
        with self._lock:
            self._mic_active = False

    # ── Background Worker Loop ────────────────────────────────────────
    def _listen_worker(self) -> None:
        """Background worker looping while active."""
        while not self._stop_event.is_set():
            if not self._active_event.is_set():
                self._active_event.wait(timeout=0.3)
                continue

            if self._stop_event.is_set() or not self.get_mic_active():
                continue

            if not SR_AVAILABLE or not self.recognizer:
                time.sleep(0.5)
                continue

            try:
                with sr.Microphone() as source:
                    try:
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    except Exception:
                        pass

                    while self.get_mic_active() and not self._stop_event.is_set():
                        try:
                            audio = self.recognizer.listen(
                                source,
                                timeout=MIC_TIMEOUT,
                                phrase_time_limit=MIC_PHRASE_TIME_LIMIT,
                            )
                        except (sr.WaitTimeoutError, TimeoutError):
                            continue
                        except Exception as mic_err:
                            print(f"[VoiceListener] Mic read notice: {mic_err}")
                            time.sleep(0.5)
                            break

                        if audio and self.get_mic_active():
                            text = self._transcribe(audio)
                            if text and text.strip() and self.get_mic_active():
                                print(f"[VoiceListener] Spoken query: '{text}'")
                                if self.on_command:
                                    self.on_command(text.strip())

            except Exception:
                # Microphone unavailable or headless environment
                time.sleep(1.0)

    def _transcribe(self, audio) -> str:
        """Transcribe audio using Groq Whisper if key present, else Google STT."""
        groq_key = get_active_key("groq")
        if groq_key:
            try:
                from groq import Groq
                import tempfile
                client = Groq(api_key=groq_key)
                wav_bytes = audio.get_wav_data()
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(wav_bytes)
                    tmp_name = f.name
                try:
                    with open(tmp_name, "rb") as f:
                        res = client.audio.transcriptions.create(
                            model="whisper-large-v3",
                            file=("audio.wav", f, "audio/wav"),
                            response_format="text",
                            language="en",
                        )
                    txt = res.strip() if isinstance(res, str) else res.text.strip()
                    if txt:
                        return txt
                finally:
                    if os.path.exists(tmp_name):
                        os.unlink(tmp_name)
            except Exception:
                pass

        try:
            return self.recognizer.recognize_google(audio).lower()
        except Exception:
            return ""


# Global voice listener singleton
voice_listener = VoiceListener()
