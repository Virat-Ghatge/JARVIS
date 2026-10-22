#!/usr/bin/env python3
"""
OS Actuator for JARVIS 2.0
Executes low-level mouse, keyboard, and window controls via PyAutoGUI and pynput.
Includes an emergency [ESC] hardware kill-switch and instant programmatic abort.
"""

import threading
import time
from typing import List, Optional, Union

try:
    import pyautogui
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    pyautogui.PAUSE = 0.05
    PYAUTOGUI_AVAILABLE = True
except Exception:
    PYAUTOGUI_AVAILABLE = False


class OSActuator:
    """
    Direct OS actuator controlling mouse clicks, keyboard keystrokes, and hotkeys.
    Provides an emergency [ESC] kill-switch to immediately halt automated actions.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._aborted: bool = False
        self._esc_listener = None
        self._start_esc_listener()

    def _start_esc_listener(self) -> None:
        """Starts a background pynput listener monitoring for the [ESC] key."""
        try:
            from pynput import keyboard

            def on_press(key):
                if key == keyboard.Key.esc:
                    print("\n🚨 [OSActuator] EMERGENCY [ESC] KILL-SWITCH TRIGGERED! Halting autonomous agent.")
                    self.abort()

            self._esc_listener = keyboard.Listener(on_press=on_press)
            self._esc_listener.daemon = True
            self._esc_listener.start()
        except Exception as e:
            print(f"[OSActuator] Emergency key listener notice: {e}")

    # ── Abort Controls ────────────────────────────────────────────────
    def abort(self) -> None:
        """Trigger emergency abort."""
        with self._lock:
            self._aborted = True

    def is_aborted(self) -> bool:
        """Check if abort kill-switch has been triggered."""
        with self._lock:
            return self._aborted

    def reset_abort(self) -> None:
        """Reset the abort flag before starting a new autonomous task."""
        with self._lock:
            self._aborted = False

    # ── Actuator Actions ──────────────────────────────────────────────
    def click(self, x: int, y: int) -> bool:
        """Left click at screen coordinates (x, y)."""
        if self.is_aborted():
            return False
        if not PYAUTOGUI_AVAILABLE:
            print(f"[OSActuator Mock] Click at ({x}, {y})")
            return True
        try:
            pyautogui.click(x, y)
            return True
        except Exception as e:
            print(f"[OSActuator] Click error: {e}")
            return False

    def double_click(self, x: int, y: int) -> bool:
        """Double click at screen coordinates (x, y)."""
        if self.is_aborted():
            return False
        if not PYAUTOGUI_AVAILABLE:
            print(f"[OSActuator Mock] Double-click at ({x}, {y})")
            return True
        try:
            pyautogui.doubleClick(x, y)
            return True
        except Exception as e:
            print(f"[OSActuator] Double-click error: {e}")
            return False

    def right_click(self, x: int, y: int) -> bool:
        """Right click at screen coordinates (x, y)."""
        if self.is_aborted():
            return False
        if not PYAUTOGUI_AVAILABLE:
            print(f"[OSActuator Mock] Right-click at ({x}, {y})")
            return True
        try:
            pyautogui.rightClick(x, y)
            return True
        except Exception as e:
            print(f"[OSActuator] Right-click error: {e}")
            return False

    def type_text(self, text: str, interval: float = 0.02) -> bool:
        """Type string into focused element."""
        if self.is_aborted():
            return False
        if not PYAUTOGUI_AVAILABLE:
            print(f"[OSActuator Mock] Type text: '{text}'")
            return True
        try:
            pyautogui.typewrite(text, interval=interval)
            return True
        except Exception as e:
            print(f"[OSActuator] Type text error: {e}")
            return False

    def press_hotkey(self, keys: Union[List[str], str]) -> bool:
        """Press key combination (e.g. ['ctrl', 'c'] or 'enter')."""
        if self.is_aborted():
            return False
        if isinstance(keys, str):
            key_list = [k.strip() for k in keys.split("+")]
        else:
            key_list = keys

        if not PYAUTOGUI_AVAILABLE:
            print(f"[OSActuator Mock] Hotkey: {key_list}")
            return True
        try:
            pyautogui.hotkey(*key_list)
            return True
        except Exception as e:
            print(f"[OSActuator] Hotkey error: {e}")
            return False

    def scroll(self, amount: int) -> bool:
        """Scroll mouse wheel (positive up, negative down)."""
        if self.is_aborted():
            return False
        if not PYAUTOGUI_AVAILABLE:
            print(f"[OSActuator Mock] Scroll: {amount}")
            return True
        try:
            pyautogui.scroll(amount)
            return True
        except Exception as e:
            print(f"[OSActuator] Scroll error: {e}")
            return False


# Global actuator singleton
os_actuator = OSActuator()
