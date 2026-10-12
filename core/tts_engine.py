#!/usr/bin/env python3
"""
Unified Text-to-Speech Engine for JARVIS
Supports edge-tts neural voices with pyttsx3 offline fallback.
Includes an explicit thread-safe enabled switch to suppress audio synthesis when TTS is toggled off.
"""

import asyncio
import os
import queue
import tempfile
import threading
import time

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

from config.settings import TTS_NEURAL_VOICE, TTS_FALLBACK_RATE


class TTSEngine:
    """
    Unified speech synthesis engine for JARVIS.
    Features:
    - Thread-safe enabled toggle (mic vs tts independent state)
    - edge-tts neural voice primary synthesis
    - pyttsx3 offline fallback
    - Non-blocking background worker queue to prevent UI freezing
    """

    def __init__(self, enabled: bool = True, voice: str = TTS_NEURAL_VOICE, rate: int = TTS_FALLBACK_RATE):
        self._enabled = bool(enabled)
        self._lock = threading.Lock()
        self.voice = voice
        self.rate = rate

        # Audio queue and worker thread
        self._speech_queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._speech_worker, daemon=True, name="TTS-Worker")
        self._is_speaking = False

        # Initialize pygame mixer if available
        self._pygame_initialized = False
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.init()
                self._pygame_initialized = True
            except Exception as e:
                print(f"[TTS] pygame mixer init warning: {e}")

        # Start worker thread
        self._worker_thread.start()

    # ── State Controls ────────────────────────────────────────────────
    def is_enabled(self) -> bool:
        """Return True if TTS audio synthesis is active."""
        with self._lock:
            return self._enabled

    def enable(self):
        """Enable speech output."""
        with self._lock:
            self._enabled = True

    def disable(self):
        """Disable speech output (silent mode)."""
        with self._lock:
            self._enabled = False

    def toggle(self) -> bool:
        """Toggle speech output state and return new state."""
        with self._lock:
            self._enabled = not self._enabled
            return self._enabled

    def is_speaking(self) -> bool:
        """Check if speech audio is currently playing."""
        return self._is_speaking

    def stop(self):
        """Stop current speech playback if possible."""
        if PYGAME_AVAILABLE and self._pygame_initialized:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

    # ── Speech Ingestion ──────────────────────────────────────────────
    def speak(self, text: str, wait: bool = False):
        """
        Synthesize and speak text.
        If disabled, skips speech silently and returns immediately.
        If wait is True, blocks until speech finishes.
        """
        if not text or not text.strip():
            return

        with self._lock:
            if not self._enabled:
                # TTS disabled; silent mode
                return

        done_event = threading.Event() if wait else None
        self._speech_queue.put((text.strip(), done_event))

        if wait and done_event:
            done_event.wait()

    # ── Background Worker ─────────────────────────────────────────────
    def _speech_worker(self):
        """Worker thread processing queued speech items."""
        while True:
            try:
                text, done_event = self._speech_queue.get()
                if text is None:
                    break

                with self._lock:
                    currently_enabled = self._enabled

                if currently_enabled:
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
                print(f"[TTS Worker Loop Error] {e}")

    def _play_speech(self, text: str):
        """Synthesize and play speech via edge-tts or pyttsx3."""
        success = False

        if EDGE_TTS_AVAILABLE and PYGAME_AVAILABLE and self._pygame_initialized:
            try:
                success = self._synthesize_edge_tts(text)
            except Exception as e:
                print(f"[TTS] edge-tts failed ({e}), falling back to pyttsx3")
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
                pitch="-5Hz"
            )
            # Run async call in isolated event loop
            asyncio.run(communicate.save(tmpfile))

            if os.path.exists(tmpfile) and os.path.getsize(tmpfile) > 0:
                pygame.mixer.music.load(tmpfile)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    with self._lock:
                        if not self._enabled:
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

    def _synthesize_pyttsx3(self, text: str):
        """Offline fallback using pyttsx3."""
        if not PYTTSX3_AVAILABLE:
            return
        try:
            # Create a localized engine instance for thread isolation
            engine = pyttsx3.init()
            engine.setProperty('rate', self.rate)
            engine.say(text)
            engine.runAndWait()
            del engine
        except Exception as e:
            print(f"[TTS pyttsx3] {e}")
