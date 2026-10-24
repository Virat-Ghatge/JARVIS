import time
import threading
from typing import Callable, Optional, Dict, Any

try:
    import speech_recognition as sr
except Exception:
    sr = None


class VoiceListener:
    """
    Thread-safe SpeechRecognition listener with lazy start (no import-time thread spawning),
    independent `mic_active` toggle, and meeting auto-mute interlock with manual user override.
    """

    def __init__(self, on_transcript: Optional[Callable[[str], None]] = None):
        self.on_transcript = on_transcript
        self.mic_active: bool = False
        self.in_meeting_auto_muted: bool = False
        self.status_detail: str = "Standby"
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._state_listener: Optional[Callable[[Dict[str, Any]], None]] = None

    def register_state_listener(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        self._state_listener = cb

    def get_state(self) -> Dict[str, Any]:
        return {
            "mic_active": self.mic_active,
            "in_meeting_auto_muted": self.in_meeting_auto_muted,
            "status_detail": self.status_detail,
        }

    def _notify(self) -> None:
        if self._state_listener:
            try:
                self._state_listener(self.get_state())
            except Exception:
                pass

    def ensure_worker_started(self) -> None:
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._worker_thread.start()

    def set_mic_active(self, active: bool, manual_override: bool = True) -> Dict[str, Any]:
        with self._lock:
            self.mic_active = bool(active)
            if manual_override and active:
                self.in_meeting_auto_muted = False
            self.status_detail = "Listening" if self.mic_active else "Muted"
            if self.mic_active:
                self.ensure_worker_started()
            self._notify()
            return self.get_state()

    def enter_meeting_auto_mute(self) -> Dict[str, Any]:
        """Auto-mutes JARVIS mic when joining a meeting; user can still manually unmute anytime."""
        with self._lock:
            self.in_meeting_auto_muted = True
            self.mic_active = False
            self.status_detail = "Auto-Muted (In Meeting)"
            self._notify()
            return self.get_state()

    def shutdown(self) -> None:
        self._stop_event.set()
        self.mic_active = False

    def _listen_loop(self) -> None:
        if sr is None:
            self.status_detail = "SpeechRecognition Unavailable"
            self._notify()
            return

        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True

        while not self._stop_event.is_set():
            if not self.mic_active:
                time.sleep(0.25)
                continue

            try:
                with sr.Microphone() as source:
                    audio = recognizer.listen(source, timeout=3.0, phrase_time_limit=10.0)
                if not self.mic_active:
                    continue
                text = recognizer.recognize_google(audio).strip()
                if text and self.on_transcript:
                    self.on_transcript(text)
            except Exception:
                time.sleep(0.2)
