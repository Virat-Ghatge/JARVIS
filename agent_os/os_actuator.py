import time
import threading
from typing import Optional, Callable, Dict, Any

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    PYAUTOGUI_AVAILABLE = True
except Exception:
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except Exception:
    keyboard = None
    PYNPUT_AVAILABLE = False


class OSActuator:
    """
    Tier 3 OS GUI Actuator with strictly task-scoped [ESC] emergency kill-switch.
    Never registers a global WH_KEYBOARD_LL hook at module import time.
    """

    def __init__(self, on_abort_callback: Optional[Callable[[], None]] = None):
        self._abort_event = threading.Event()
        self._listener: Optional[Any] = None
        self._lock = threading.Lock()
        self._on_abort_callback = on_abort_callback

    @property
    def is_aborted(self) -> bool:
        return self._abort_event.is_set()

    @property
    def aborted(self) -> bool:
        return self._abort_event.is_set()

    @property
    def kill_switch_triggered(self) -> bool:
        return self._abort_event.is_set()

    def reset_abort(self) -> None:
        self._abort_event.clear()

    def reset(self) -> None:
        self._abort_event.clear()

    def reset_kill_switch(self) -> None:
        self._abort_event.clear()

    def trigger_abort(self) -> None:
        self._abort_event.set()
        if self._on_abort_callback:
            try:
                self._on_abort_callback()
            except Exception:
                pass

    def abort(self) -> None:
        self.trigger_abort()

    def trigger_kill_switch(self) -> None:
        self.trigger_abort()

    def press_escape(self) -> None:
        self.trigger_abort()

    def start_esc_guard(self) -> None:
        """Starts the low-level [ESC] listener ONLY while an active OS Agent task is running."""
        with self._lock:
            self._abort_event.clear()
            if keyboard is None or self._listener is not None:
                return

            def _on_press(key):
                try:
                    if key == keyboard.Key.esc:
                        self.trigger_abort()
                        return False
                except Exception:
                    pass
                return True

            self._listener = keyboard.Listener(on_press=_on_press)
            self._listener.daemon = True
            self._listener.start()

    def stop_esc_guard(self) -> None:
        """Unhooks WH_KEYBOARD_LL immediately when the OS Agent task finishes."""
        with self._lock:
            if self._listener is not None:
                try:
                    self._listener.stop()
                except Exception:
                    pass
                self._listener = None

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> Dict[str, Any]:
        return self.execute_action({"action": "click", "x": x, "y": y, "button": button, "clicks": clicks})

    def type_text(self, text: str, press_enter: bool = False, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"action": "type", "text": text, "press_enter": press_enter}
        if x is not None and y is not None:
            payload["x"] = x
            payload["y"] = y
        return self.execute_action(payload)

    def hotkey(self, *keys: str) -> Dict[str, Any]:
        return self.execute_action({"action": "hotkey", "keys": list(keys)})

    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if self.is_aborted:
            return {"status": "aborted", "success": False, "detail": "Emergency [ESC] kill-switch triggered."}

        act_type = str(action.get("action", action.get("type", ""))).lower().strip()
        if act_type in ("done", "complete", "finish"):
            return {"status": "done", "success": True, "detail": action.get("reason", "Goal achieved.")}

        if act_type == "wait":
            seconds = float(action.get("seconds", 1.0))
            time.sleep(min(seconds, 10.0))
            return {"status": "ok", "success": True, "detail": f"Waited {seconds}s"}

        if pyautogui is None:
            return {"status": "simulated", "success": True, "detail": f"Simulated {act_type} (PyAutoGUI unavailable)"}

        try:
            if act_type == "click":
                x = int(action.get("x", 0))
                y = int(action.get("y", 0))
                button = str(action.get("button", "left"))
                clicks = int(action.get("clicks", 1))
                pyautogui.click(x=x, y=y, clicks=clicks, button=button)
                return {"status": "ok", "success": True, "detail": f"Clicked ({x}, {y}) [{button} x{clicks}]"}

            elif act_type == "double_click":
                x = int(action.get("x", 0))
                y = int(action.get("y", 0))
                pyautogui.doubleClick(x=x, y=y)
                return {"status": "ok", "success": True, "detail": f"Double-clicked ({x}, {y})"}

            elif act_type in ("type", "type_text"):
                text = str(action.get("text", ""))
                press_enter = bool(action.get("press_enter", False))
                if "x" in action and "y" in action and action["x"] is not None and action["y"] is not None:
                    pyautogui.click(x=int(action["x"]), y=int(action["y"]))
                    time.sleep(0.1)
                pyautogui.write(text, interval=0.02)
                if press_enter:
                    pyautogui.press("enter")
                return {"status": "ok", "success": True, "detail": f"Typed {len(text)} chars"}

            elif act_type == "hotkey":
                keys = action.get("keys", [])
                if isinstance(keys, str):
                    keys = [k.strip() for k in keys.split("+") if k.strip()]
                pyautogui.hotkey(*keys)
                return {"status": "ok", "success": True, "detail": f"Hotkey {'+'.join(keys)}"}

            elif act_type == "scroll":
                amount = int(action.get("amount", -300))
                pyautogui.scroll(amount)
                return {"status": "ok", "success": True, "detail": f"Scrolled {amount}"}

            return {"status": "error", "success": False, "detail": f"Unknown OS action type: {act_type}"}
        except Exception as exc:
            return {"status": "error", "success": False, "detail": f"Actuator exception: {exc}"}


os_actuator = OSActuator()
