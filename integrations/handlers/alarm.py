#!/usr/bin/env python3
"""
Alarm Module
Handles alarm and timer functionality synchronized with config/alarms.json.
"""

import datetime
import json
import os
import re
import threading
import time
from typing import Any, Dict, List

from config.settings import ALARMS_FILE


class AlarmHandler:
    """Handles alarm and countdown timer operations synchronized with config/alarms.json."""

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self._lock = threading.Lock()
        self.alarms: List[Dict[str, Any]] = []
        self.timers: List[Dict[str, Any]] = []
        self._load_from_disk()
        self.alarm_thread = threading.Thread(target=self._alarm_checker, daemon=True, name="AlarmChecker")
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

    def set_alarm(self, command: str) -> str:
        """
        Set an alarm from a voice or text command and persist to config/alarms.json.
        e.g. 'set alarm for 7:30 AM', 'set alarm for 14:00', 'set alarm for 8 pm'
        """
        time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', command, re.IGNORECASE)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            period = time_match.group(3)

            if period:
                if period.lower() == 'pm' and hour != 12:
                    hour += 12
                elif period.lower() == 'am' and hour == 12:
                    hour = 0

            time_24 = f"{hour:02d}:{minute:02d}"
            # Friendly 12-hour display string
            dt_dummy = datetime.datetime.now().replace(hour=hour, minute=minute, second=0)
            time_display = dt_dummy.strftime("%I:%M %p").lstrip("0")
            label = f"Alarm for {time_display}"

            alarm_entry = {
                "id": f"alr-{int(time.time() * 1000)}",
                "label": label,
                "time": time_24,
                "type": "alarm",
            }

            self._load_from_disk()
            with self._lock:
                self.alarms.append(alarm_entry)
            self._save_to_disk()

            msg = f"Alarm set for {time_display}, sir."
            self.jarvis.speak(msg)
            return msg
        else:
            msg = "Please specify the time, sir. For example, 'set alarm for 7:30 AM'."
            self.jarvis.speak(msg)
            return msg

    def _alarm_checker(self):
        """Background thread to poll and check alarms and timers from config/alarms.json."""
        while True:
            try:
                self._load_from_disk()
                now = datetime.datetime.now()
                now_hm = now.strftime("%H:%M")
                triggered_alarms = []

                with self._lock:
                    remaining_alarms = []
                    for alarm in self.alarms:
                        alarm_time = alarm.get("time", "").strip()
                        triggered = False
                        if alarm_time:
                            if alarm_time == now_hm:
                                triggered = True
                            else:
                                try:
                                    if "am" in alarm_time.lower() or "pm" in alarm_time.lower():
                                        parsed_t = datetime.datetime.strptime(alarm_time.strip(), "%I:%M %p").time()
                                    else:
                                        parts = alarm_time.split(":")
                                        parsed_t = datetime.time(int(parts[0]), int(parts[1]))
                                    if parsed_t.hour == now.hour and parsed_t.minute == now.minute:
                                        triggered = True
                                except Exception:
                                    pass

                        if triggered:
                            triggered_alarms.append(alarm)
                        else:
                            remaining_alarms.append(alarm)

                    if triggered_alarms:
                        self.alarms = remaining_alarms

                if triggered_alarms:
                    self._save_to_disk()
                    for t_alr in triggered_alarms:
                        label = t_alr.get("label", "Alarm")
                        self.jarvis.speak(f"Sir, your alarm '{label}' is going off!")

            except Exception as e:
                print(f"[AlarmChecker] Error: {e}")

            time.sleep(2)  # Check every 2 seconds

    def cancel_alarm(self):
        """Cancel all active alarms."""
        self._load_from_disk()
        if not self.alarms:
            self.jarvis.speak("No active alarms to cancel, sir.")
            return

        with self._lock:
            count = len(self.alarms)
            self.alarms.clear()
        self._save_to_disk()
        self.jarvis.speak(f"All {count} active alarm{'s have' if count > 1 else ' has'} been cancelled, sir.")
