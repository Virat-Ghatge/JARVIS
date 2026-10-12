#!/usr/bin/env python3
"""
Thread-Safe Voice Listener & Concurrency Manager for JARVIS
Wraps SpeechRecognition in a background worker thread with:
- Instant enable/disable/toggle controls via threading.Event
- Meeting-aware audio interlocking (auto-mute on meeting join, manual override, auto-restore on leave)
- Dynamic callbacks for UI indicators and command routing
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

from config.settings import MIC_TIMEOUT, MIC_PHRASE_TIME_LIMIT, GROQ_API_KEY


class VoiceListener:
    """
    Background worker managing microphone ingestion and audio interlocking.
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

        # State flags
        self._mic_active: bool = False
        self.in_meeting: bool = False
        self.auto_muted_by_meeting: bool = False
        self.manual_override: bool = False

        # Speech recognition components
        self.recognizer = sr.Recognizer() if SR_AVAILABLE else None
        if self.recognizer:
            self.recognizer.energy_threshold = 4000
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8

        # Whisper client for high-accuracy STT
        self.whisper_client = None
        self._init_whisper()

        # Start background worker
        self.start()

    def _init_whisper(self):
        """Initialize Groq Whisper client if available."""
        if not GROQ_API_KEY:
            return
        try:
            from groq import Groq
            self.whisper_client = Groq(api_key=GROQ_API_KEY)
        except Exception:
            self.whisper_client = None

    # ── State Controls ────────────────────────────────────────────────
    def is_active(self) -> bool:
        """Return True if microphone is actively listening."""
        with self._lock:
            return self._mic_active

    def enable(self, manual_override: bool = False):
        """Activate microphone listening stream."""
        with self._lock:
            self._mic_active = True
            self._active_event.set()
            if self.in_meeting:
                self.manual_override = True
                self.auto_muted_by_meeting = False

        if self.on_status_change:
            msg = "Microphone active (manual override during meeting)" if (self.in_meeting and manual_override) else "Microphone active"
            self.on_status_change(True, msg)

    def disable(self, auto_meeting: bool = False):
        """Halt microphone listening stream without terminating thread."""
        with self._lock:
            self._mic_active = False
            self._active_event.clear()
            if auto_meeting:
                self.auto_muted_by_meeting = True
                self.manual_override = False
            else:
                self.auto_muted_by_meeting = False
                self.manual_override = False

        if self.on_status_change:
            msg = "Microphone auto-muted: Meeting active" if auto_meeting else "Microphone muted"
            self.on_status_change(False, msg)

    def toggle(self) -> bool:
        """Toggle microphone state and return new state."""
        if self.is_active():
            self.disable(auto_meeting=False)
            return False
        else:
            self.enable(manual_override=self.in_meeting)
            return True

    # ── Meeting Interlocking State Machine ────────────────────────────
    def handle_meeting_joined(self, meeting_title: str = "Online Meeting"):
        """
        Triggered when a meeting is joined.
        Auto-mutes microphone to prevent meeting audio cross-talk.
        Allows manual unmuting override.
        """
        was_active = self.is_active()
        with self._lock:
            self.in_meeting = True
            self.manual_override = False

        if was_active:
            self.disable(auto_meeting=True)
            print(f"[AudioInterlock] Auto-muted microphone for: {meeting_title}")
        else:
            with self._lock:
                self.auto_muted_by_meeting = False

        if self.on_meeting_alert:
            self.on_meeting_alert("joined", meeting_title)

    def handle_meeting_left(self, meeting_title: str = "Online Meeting"):
        """
        Triggered when a meeting ends or user leaves call.
        Restores previous microphone state if auto-muted and not overridden.
        """
        should_restore = False
        with self._lock:
            self.in_meeting = False
            if self.auto_muted_by_meeting and not self.manual_override:
                should_restore = True
            self.auto_muted_by_meeting = False
            self.manual_override = False

        if should_restore:
            print(f"[AudioInterlock] Meeting left ({meeting_title}). Restoring microphone.")
            self.enable()
        else:
            print(f"[AudioInterlock] Meeting left ({meeting_title}). Microphone state retained.")

        if self.on_meeting_alert:
            self.on_meeting_alert("left", meeting_title)

    # ── Thread Lifecycle ──────────────────────────────────────────────
    def start(self):
        """Start the background worker thread."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._listen_worker,
                daemon=True,
                name="VoiceListener-Worker"
            )
            self._worker_thread.start()

    def stop(self):
        """Terminate the background worker thread."""
        self._stop_event.set()
        self._active_event.set()  # unblock wait
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
        self._mic_active = False

    # ── Background Worker Loop ────────────────────────────────────────
    def _listen_worker(self):
        """Background worker looping while active."""
        while not self._stop_event.is_set():
            # Wait until active or stopped
            if not self._active_event.is_set():
                self._active_event.wait(timeout=0.3)
                continue

            if self._stop_event.is_set() or not self._mic_active:
                continue

            if not SR_AVAILABLE:
                time.sleep(0.5)
                continue

            try:
                with sr.Microphone() as source:
                    # Quick ambient noise adjustment
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.4)

                    while self._mic_active and not self._stop_event.is_set():
                        try:
                            audio = self.recognizer.listen(
                                source,
                                timeout=MIC_TIMEOUT,
                                phrase_time_limit=MIC_PHRASE_TIME_LIMIT
                            )
                        except (sr.WaitTimeoutError, TimeoutError):
                            continue
                        except Exception as mic_err:
                            print(f"[VoiceListener Mic Error] {mic_err}")
                            time.sleep(0.5)
                            break

                        # Transcribe audio
                        if audio and self._mic_active:
                            text = self._transcribe(audio)
                            if text and text.strip() and self._mic_active:
                                print(f"[VoiceListener] Detected: '{text}'")
                                if self.on_command:
                                    self.on_command(text.strip())

            except Exception as e:
                # Device unavailable or permission denied
                time.sleep(1.0)

    def _transcribe(self, audio) -> str:
        """Transcribe audio using Whisper or Google STT."""
        # Try Groq Whisper
        if self.whisper_client:
            try:
                import tempfile
                wav_bytes = audio.get_wav_data()
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(wav_bytes)
                    tmp_name = f.name
                try:
                    with open(tmp_name, "rb") as f:
                        res = self.whisper_client.audio.transcriptions.create(
                            model="whisper-large-v3",
                            file=("audio.wav", f, "audio/wav"),
                            response_format="text",
                            language="en",
                        )
                    txt = res.strip() if isinstance(res, str) else res.text.strip()
                    if len(txt.split()) >= 2:
                        return txt
                finally:
                    if os.path.exists(tmp_name):
                        os.unlink(tmp_name)
            except Exception:
                pass

        # Google STT fallback
        try:
            return self.recognizer.recognize_google(audio).lower()
        except Exception:
            return ""
