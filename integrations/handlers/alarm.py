#!/usr/bin/env python3
"""
Alarm Module
Handles alarm and timer functionality synchronized with config/alarms.json and WebSocket telemetry.
"""

import datetime
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Set

from config.settings import ALARMS_FILE


class AlarmHandler:
    """Handles alarm and countdown timer operations synchronized with config/alarms.json."""

    def __init__(self, jarvis: Optional[Any] = None) -> None:
        self.jarvis: Optional[Any] = jarvis
        self._lock = threading.RLock()
        self.alarms: List[Dict[str, Any]] = []
        self.timers: List[Dict[str, Any]] = []
        self._load_from_disk()
        self.alarm_thread = threading.Thread(
            target=self._alarm_checker, daemon=True, name="AlarmChecker"
        )
        self.alarm_thread.start()

    def _load_from_disk(self) -> None:
        """Loads alarms and timers from config/alarms.json."""
        with self._lock:
            if not ALARMS_FILE.exists():
                self.alarms = []
                self.timers = []
                return
            try:
                data = json.loads(ALARMS_FILE.read_text(encoding="utf-8"))
                self.alarms = data.get("alarms", [])
                self.timers = data.get("timers", [])
            except Exception as e:
                print(f"[AlarmHandler] Load error: {e}")
                self.alarms = []
                self.timers = []

    def _save_to_disk(self) -> None:
        """Persists alarms and timers to config/alarms.json."""
        with self._lock:
            try:
                os.makedirs(ALARMS_FILE.parent, exist_ok=True)
                data = {"alarms": self.alarms, "timers": self.timers}
                ALARMS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[AlarmHandler] Save error: {e}")

    def get_active_alarms(self) -> List[Dict[str, Any]]:
        """Returns list of all active alarms loaded from disk."""
        self._load_from_disk()
        with self._lock:
            return [dict(a) for a in self.alarms]

    def set_alarm(self, command: str) -> str:
        """
        Set an alarm from a voice or text command and persist to config/alarms.json.
        e.g. 'set alarm for 7:30 AM', 'set alarm for 14:00', 'set alarm for 8 pm'
        """
        time_match = re.search(r"(\d{1,2}):?(\d{2})?\s*(am|pm)?", command, re.IGNORECASE)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            period = time_match.group(3)

            if period:
                if period.lower() == "pm" and hour != 12:
                    hour += 12
                elif period.lower() == "am" and hour == 12:
                    hour = 0

            time_24 = f"{hour:02d}:{minute:02d}"
            # Friendly 12-hour display string
            dt_dummy = datetime.datetime.now().replace(hour=hour, minute=minute, second=0)
            time_display = dt_dummy.strftime("%I:%M %p").lstrip("0")
            label = f"Alarm for {time_display}"

            alarm_entry: Dict[str, Any] = {
                "id": f"alr-{int(time.time() * 1000)}",
                "label": label,
                "time": time_24,
                "type": "alarm",
            }

            self._load_from_disk()
            with self._lock:
                self.alarms.append(alarm_entry)
            self._save_to_disk()

            # Broadcast WebSocket event
            try:
                from automation.server import broadcast_ws_sync
                broadcast_ws_sync("ALARM_CREATED", alarm_entry)
            except Exception:
                pass

            msg = f"Alarm set for {time_display}, sir."
            if self.jarvis and hasattr(self.jarvis, "speak"):
                self.jarvis.speak(msg)
            return msg
        else:
            msg = "Please specify the time, sir. For example, 'set alarm for 7:30 AM'."
            if self.jarvis and hasattr(self.jarvis, "speak"):
                self.jarvis.speak(msg)
            return msg

    def cancel_alarm_by_id(self, alarm_id: str) -> bool:
        """Cancel a specific alarm by its unique id."""
        self._load_from_disk()
        with self._lock:
            initial_count = len(self.alarms)
            self.alarms = [a for a in self.alarms if str(a.get("id")) != str(alarm_id)]
            removed = len(self.alarms) < initial_count

        if removed:
            self._save_to_disk()
            try:
                from automation.server import broadcast_ws_sync
                broadcast_ws_sync("ALARM_CANCELLED", {"alarm_id": alarm_id})
            except Exception:
                pass
        return removed

    def cancel_alarm(self, command: str = "") -> str:
        """
        Cancel alarm by ID, label match, or cancel all active alarms if none specified.
        """
        self._load_from_disk()
        if not self.alarms:
            msg = "No active alarms to cancel, sir."
            if self.jarvis and hasattr(self.jarvis, "speak"):
                self.jarvis.speak(msg)
            return msg

        cmd_clean = command.strip().lower()

        # If no specific alarm specified or 'all' requested: cancel all
        if not cmd_clean or cmd_clean in (
            "all", "all alarms", "every alarm", "cancel all", "cancel all alarms"
        ):
            with self._lock:
                count = len(self.alarms)
                self.alarms.clear()
            self._save_to_disk()
            try:
                from automation.server import broadcast_ws_sync
                broadcast_ws_sync("ALL_ALARMS_CANCELLED", {"count": count})
            except Exception:
                pass
            msg = f"All {count} active alarm{'s have' if count > 1 else ' has'} been cancelled, sir."
            if self.jarvis and hasattr(self.jarvis, "speak"):
                self.jarvis.speak(msg)
            return msg

        # Try matching by ID first
        matched_ids: Set[Any] = set()
        labels: str = ""
        matched: bool = False
        with self._lock:
            matched_items = [a for a in self.alarms if str(a.get("id", "")).lower() == cmd_clean]

            if not matched_items:
                # Clean command prefix to search for time or label
                search_term = cmd_clean
                for prefix in ("cancel alarm for", "cancel alarm", "delete alarm", "remove alarm", "cancel"):
                    if search_term.startswith(prefix):
                        search_term = search_term[len(prefix):].strip()

                matched_items = [
                    a for a in self.alarms
                    if search_term and (
                        search_term in a.get("label", "").lower()
                        or search_term in a.get("time", "").lower()
                        or str(a.get("id", "")).lower() == search_term
                    )
                ]

            if matched_items:
                matched_ids = {m.get("id") for m in matched_items}
                self.alarms = [a for a in self.alarms if a.get("id") not in matched_ids]
                labels = ", ".join(m.get("label", "Alarm") for m in matched_items)
                matched = True

        if matched:
            self._save_to_disk()
            msg = f"Cancelled alarm '{labels}', sir."
            try:
                from automation.server import broadcast_ws_sync
                for mid in matched_ids:
                    broadcast_ws_sync("ALARM_CANCELLED", {"alarm_id": mid})
            except Exception:
                pass
        else:
            msg = f"No active alarm found matching '{command}', sir."

        if self.jarvis and hasattr(self.jarvis, "speak"):
            self.jarvis.speak(msg)
        return msg

    def _alarm_checker(self) -> None:
        """Background thread to poll and check alarms and timers from config/alarms.json."""
        while True:
            try:
                self._load_from_disk()
                now = datetime.datetime.now()
                now_hm = now.strftime("%H:%M")
                triggered_alarms: List[Dict[str, Any]] = []

                with self._lock:
                    remaining_alarms: List[Dict[str, Any]] = []
                    for alarm_item in self.alarms:
                        alarm_time = alarm_item.get("time", "").strip()
                        triggered = False
                        if alarm_time:
                            if alarm_time == now_hm:
                                triggered = True
                            else:
                                try:
                                    if "am" in alarm_time.lower() or "pm" in alarm_time.lower():
                                        parsed_t = datetime.datetime.strptime(
                                            alarm_time.strip(), "%I:%M %p"
                                        ).time()
                                    else:
                                        parts = alarm_time.split(":")
                                        parsed_t = datetime.time(int(parts[0]), int(parts[1]))
                                    if parsed_t.hour == now.hour and parsed_t.minute == now.minute:
                                        triggered = True
                                except Exception:
                                    pass

                        if triggered:
                            triggered_alarms.append(alarm_item)
                        else:
                            remaining_alarms.append(alarm_item)

                    if triggered_alarms:
                        self.alarms = remaining_alarms

                if triggered_alarms:
                    self._save_to_disk()
                    for t_alr in triggered_alarms:
                        label = t_alr.get("label", "Alarm")
                        alarm_id = t_alr.get("id")
                        alarm_time_val = t_alr.get("time")

                        # TTS feedback
                        if self.jarvis and hasattr(self.jarvis, "speak"):
                            self.jarvis.speak(f"Sir, your alarm '{label}' is going off!")

                        # WebSocket Broadcast
                        try:
                            from automation.server import broadcast_ws_sync
                            broadcast_ws_sync(
                                "ALARM_TRIGGERED",
                                {
                                    "alarm_id": alarm_id,
                                    "label": label,
                                    "time": alarm_time_val,
                                },
                            )
                        except Exception:
                            pass

            except Exception:
                pass

            time.sleep(2)  # Check every 2 seconds


# Module-level singleton and helper functions for functional routing
_default_alarm_handler: Optional[AlarmHandler] = None

def get_alarm_handler(jarvis: Optional[Any] = None) -> AlarmHandler:
    global _default_alarm_handler
    if _default_alarm_handler is None:
        _default_alarm_handler = AlarmHandler(jarvis)
    elif jarvis and _default_alarm_handler.jarvis is None:
        _default_alarm_handler.jarvis = jarvis
    return _default_alarm_handler

alarm_handler: AlarmHandler = get_alarm_handler()

def set_alarm(command: str) -> str:
    return get_alarm_handler().set_alarm(command)

def handle_alarm(command: str) -> str:
    return get_alarm_handler().set_alarm(command)

def handle_alarm_command(command: str) -> str:
    return get_alarm_handler().set_alarm(command)

def cancel_alarm(command: str = "") -> str:
    return get_alarm_handler().cancel_alarm(command)

def cancel_alarm_by_id(alarm_id: str) -> bool:
    return get_alarm_handler().cancel_alarm_by_id(alarm_id)

def get_active_alarms() -> List[Dict[str, Any]]:
    return get_alarm_handler().get_active_alarms()

def list_alarms() -> List[Dict[str, Any]]:
    return get_alarm_handler().get_active_alarms()
