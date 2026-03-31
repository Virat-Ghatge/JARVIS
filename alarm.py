#!/usr/bin/env python3
"""
Alarm Module
Handles alarm functionality
"""

import re
import threading
import time
import datetime


class AlarmHandler:
    """Handles alarm operations"""

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.alarms = []
        self.alarm_thread = threading.Thread(target=self._alarm_checker, daemon=True)
        self.alarm_thread.start()

    def set_alarm(self, command):
        """Set an alarm"""
        # Extract time from command
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

            alarm_time = datetime.time(hour, minute)
            self.alarms.append(alarm_time)
            time_str = alarm_time.strftime("%I:%M %p")
            self.jarvis.speak(f"Alarm set for {time_str}")
        else:
            self.jarvis.speak("Please specify the time. For example, 'set alarm for 7:30 AM'")

    def _alarm_checker(self):
        """Background thread to check alarms"""
        while True:
            now = datetime.datetime.now().time()
            for alarm in self.alarms[:]:
                if now.hour == alarm.hour and now.minute == alarm.minute:
                    self.jarvis.speak("Sir, your alarm is going off!")
                    self.alarms.remove(alarm)
            time.sleep(30)  # Check every 30 seconds
