import time
import threading
from typing import Callable, Optional, Dict, Any, List

try:
    import speech_recognition as sr
except Exception:
    sr = None


class VoiceListener:
    """
    Thread-safe SpeechRecognition listener with lazy start (zero import-time threads),
    independent `mic_active` toggle, and meeting auto-mute interlock with manual user override.
    """

    def __init__(self, on_transcript: Optional[Callable[[str], None]] = None, mic_active: bool = False):
        self.on_transcript = on_transcript
        self.mic_active: bool = bool(mic_active)
        self.in_meeting: bool = False
        self.in_meeting_auto_muted: bool = False
        self.auto_muted_by_meeting: bool = False
        self._pre_meeting_mic_state: bool = False
        self.status_detail: str = "Listening" if self.mic_active else "Muted"
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._state_listeners: List[Callable[[Dict[str, Any]], None]] = []

    def set_callback(self, callback: Callable[[str], None]) -> None:
        self.on_transcript = callback

    def register_state_listener(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        if cb not in self._state_listeners:
            self._state_listeners.append(cb)

    def get_state(self) -> Dict[str, Any]:
        return {
            "mic_active": self.mic_active,
            "in_meeting": self.in_meeting,
            "in_meeting_auto_muted": self.in_meeting_auto_muted,
            "auto_muted_by_meeting": self.auto_muted_by_meeting,
            "status_detail": self.status_detail,
        }

    def get_status(self) -> Dict[str, Any]:
        return self.get_state()

    def _notify(self) -> None:
        state = self.get_state()
        for cb in list(self._state_listeners):
            try:
                cb(state)
            except Exception:
                pass

    def start_background(self, callback: Optional[Callable[[str], None]] = None) -> None:
        if callback is not None:
            self.on_transcript = callback
        self.ensure_worker_started()

    def ensure_worker_started(self) -> None:
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._worker_thread.start()

    def toggle_mic(self, active: Optional[bool] = None) -> bool:
        with self._lock:
            target = (not self.mic_active) if active is None else bool(active)
            self.set_mic_active(target, manual_override=True)
            return self.mic_active

    def set_mic_active(self, active: bool, manual_override: bool = True) -> Dict[str, Any]:
        with self._lock:
            self.mic_active = bool(active)
            if manual_override and active:
                self.in_meeting_auto_muted = False
                self.auto_muted_by_meeting = False
            self.status_detail = "Listening" if self.mic_active else "Muted"
            if self.mic_active:
                self.ensure_worker_started()
            self._notify()
            return self.get_state()

    def enter_meeting_auto_mute(self) -> Dict[str, Any]:
        """Auto-mutes JARVIS mic when joining a meeting; user can still manually unmute anytime."""
        with self._lock:
            self._pre_meeting_mic_state = self.mic_active
            self.in_meeting = True
            self.in_meeting_auto_muted = True
            self.auto_muted_by_meeting = True
            self.mic_active = False
            self.status_detail = "Auto-Muted (In Meeting)"
            self._notify()
            return self.get_state()

    def on_meeting_start(self) -> Dict[str, Any]:
        return self.enter_meeting_auto_mute()

    def on_meeting_end(self, restore_previous: bool = False) -> Dict[str, Any]:
        with self._lock:
            self.in_meeting = False
            self.in_meeting_auto_muted = False
            self.auto_muted_by_meeting = False
            if restore_previous:
                self.mic_active = self._pre_meeting_mic_state
            self.status_detail = "Listening" if self.mic_active else "Muted"
            self._notify()
            return self.get_state()

    def stop(self) -> None:
        self.shutdown()

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


voice_listener = VoiceListener()
