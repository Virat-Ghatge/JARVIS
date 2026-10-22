#!/usr/bin/env python3
"""
Unified Text-to-Speech Engine for JARVIS 2.0
Supports edge-tts neural voices with pyttsx3 offline fallback.
Includes independent thread-safe tts_active state controls to allow silent GUI operation.
"""

import asyncio
import os
import queue
import tempfile
import threading
import time
from typing import Optional

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

from config.settings import TTS_NEURAL_VOICE, TTS_FALLBACK_RATE, is_internet_connected


class TTSEngine:
    """
    Unified speech synthesis engine for JARVIS.
    Features:
    - Thread-safe independent tts_active toggle
    - edge-tts neural voice primary synthesis (when online)
    - pyttsx3 offline fallback (when offline or edge-tts fails)
    - Non-blocking background worker queue
    """

    def __init__(
        self,
        tts_active: bool = True,
        voice: str = TTS_NEURAL_VOICE,
        rate: int = TTS_FALLBACK_RATE,
        enabled: Optional[bool] = None,
        **kwargs,
    ):
        if enabled is not None:
            tts_active = enabled
        self._tts_active = bool(tts_active)
        self._lock = threading.Lock()
        self.voice = voice
        self.rate = rate

        # Audio queue and worker thread
        self._speech_queue: queue.Queue = queue.Queue()
        self._is_speaking = False

        # Initialize pygame mixer if available
        self._pygame_initialized = False
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.init()
                self._pygame_initialized = True
            except Exception as e:
                print(f"[TTS] pygame mixer init warning: {e}")

        # Start background worker thread
        self._worker_thread = threading.Thread(target=self._speech_worker, daemon=True, name="TTS-Worker")
        self._worker_thread.start()

    # ── State Controls ────────────────────────────────────────────────
    @property
    def tts_active(self) -> bool:
        with self._lock:
            return self._tts_active

    def get_tts_active(self) -> bool:
        """Return True if TTS speech output is active."""
        with self._lock:
            return self._tts_active

    def set_tts_active(self, active: bool) -> None:
        """Enable or disable TTS speech output."""
        with self._lock:
            self._tts_active = bool(active)
            if not self._tts_active:
                self.stop()

    def toggle_tts(self) -> bool:
        """Toggle TTS speech output state and return new state."""
        with self._lock:
            self._tts_active = not self._tts_active
            if not self._tts_active:
                self.stop()
            return self._tts_active

    # Aliases for backward compatibility
    def is_enabled(self) -> bool:
        return self.get_tts_active()

    def enable(self) -> None:
        self.set_tts_active(True)

    def disable(self) -> None:
        self.set_tts_active(False)

    def toggle(self) -> bool:
        return self.toggle_tts()

    def is_speaking(self) -> bool:
        """Check if audio playback is currently running."""
        return self._is_speaking

    def stop(self) -> None:
        """Stop current speech playback immediately."""
        if PYGAME_AVAILABLE and self._pygame_initialized:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

    # ── Speech Ingestion ──────────────────────────────────────────────
    def speak(self, text: str, wait: bool = False) -> None:
        """
        Synthesize and speak text.
        If tts_active is False, skips audio synthesis completely and returns immediately.
        If wait is True, blocks until speech audio finishes.
        """
        if not text or not text.strip():
            return

        with self._lock:
            if not self._tts_active:
                return

        done_event = threading.Event() if wait else None
        self._speech_queue.put((text.strip(), done_event))

        if wait and done_event:
            done_event.wait()

    # ── Background Worker ─────────────────────────────────────────────
    def _speech_worker(self) -> None:
        """Worker thread processing queued speech items."""
        while True:
            try:
                item = self._speech_queue.get()
                if item is None:
                    break
                text, done_event = item

                with self._lock:
                    active = self._tts_active

                if active:
                    self._is_speaking = True
                    try:
                        self._play_speech(text)
                    except Exception as e:
                        print(f"[TTS Worker Error] {e}")
                    finally:
                        self._is_speaking = False

                if done_event:
                    done_event.set()
                self._speech_queue.task_done()
            except Exception as e:
                print(f"[TTS Loop Error] {e}")

    def _play_speech(self, text: str) -> None:
        """Synthesize and play speech via edge-tts (if online) or pyttsx3 fallback."""
        success = False
        online = is_internet_connected()

        if online and EDGE_TTS_AVAILABLE and PYGAME_AVAILABLE and self._pygame_initialized:
            try:
                success = self._synthesize_edge_tts(text)
            except Exception as e:
                print(f"[TTS] edge-tts error: {e}, falling back to pyttsx3")
                success = False

        if not success:
            self._synthesize_pyttsx3(text)

    def _synthesize_edge_tts(self, text: str) -> bool:
        """Synthesize via edge-tts and play via pygame."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmpfile = f.name

        try:
            communicate = edge_tts.Communicate(
                text,
                voice=self.voice,
                rate="+25%",
                pitch="-5Hz",
            )
            asyncio.run(communicate.save(tmpfile))

            if os.path.exists(tmpfile) and os.path.getsize(tmpfile) > 0:
                pygame.mixer.music.load(tmpfile)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    with self._lock:
                        if not self._tts_active:
                            pygame.mixer.music.stop()
                            break
                    time.sleep(0.04)
                return True
            return False
        except Exception as e:
            print(f"[TTS edge_tts] {e}")
            return False
        finally:
            try:
                if os.path.exists(tmpfile):
                    os.unlink(tmpfile)
            except OSError:
                pass

    def _synthesize_pyttsx3(self, text: str) -> None:
        """Offline fallback using pyttsx3."""
        if not PYTTSX3_AVAILABLE:
            return
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self.rate)
            engine.say(text)
            engine.runAndWait()
            del engine
        except Exception as e:
            print(f"[TTS pyttsx3] {e}")


# Global TTS instance
tts_engine = TTSEngine()
