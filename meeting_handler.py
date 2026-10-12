#!/usr/bin/env python3
"""
Meeting Handler
Top-level JARVIS handler that bridges the meeting bot, scheduler,
and dashboard interface into the core command dispatch system.

Follows the same pattern as AlarmHandler, WeatherHandler, etc.:
  - __init__(self, jarvis) stores the reference
  - Public methods called from core.py's process_command / _execute_ai_command
"""

import re
import threading
import webbrowser
from datetime import datetime

# Import meeting sub-modules
from modules.meeting_scheduler import MeetingScheduler
from modules.meeting_bot import MeetingBot, PLAYWRIGHT_AVAILABLE
from modules.schedule_interface import ScheduleInterface, FASTAPI_AVAILABLE


class MeetingHandler:
    """Handles meeting-related voice commands and manages all meeting subsystems."""

    def __init__(self, jarvis):
        self.jarvis = jarvis

        # ── Subsystems ────────────────────────────
        self.bot = MeetingBot() if PLAYWRIGHT_AVAILABLE else None
        self.scheduler = MeetingScheduler(meeting_bot=self.bot)
        self.dashboard = ScheduleInterface(
            scheduler=self.scheduler,
            meeting_bot=self.bot,
        )

        # Start the web dashboard in a daemon thread
        if FASTAPI_AVAILABLE:
            self.dashboard.start()

        print("[✓] Meeting attendant module ready")

    # ─── Voice Commands ───────────────────────────────────────────

    def schedule_meeting(self, command: str):
        """
        Parse a voice/chat scheduling command and add the meeting.
        e.g. "schedule Team Standup at 2:30 PM with link https://meet.google.com/abc"
        """
        result = self.scheduler.parse_schedule_command(command)
        if result:
            meeting = self.scheduler.add_meeting(
                title=result["title"],
                meeting_url=result["meeting_url"],
                start_time=result["start_time"],
            )
            time_str = result["start_time"].strftime("%I:%M %p")
            self.jarvis.speak(
                f"Meeting '{meeting['title']}' scheduled for {time_str}, sir. "
                f"I'll join automatically 60 seconds beforehand."
            )
        else:
            self.jarvis.speak(
                "I couldn't parse that schedule command, sir. "
                "Please include a meeting URL and a time. For example: "
                "'Schedule standup at 2:30 PM with link https://meet.google.com/abc'."
            )

    def list_today_meetings(self):
        """Read out today's meetings."""
        meetings = self.scheduler.get_today()
        if not meetings:
            self.jarvis.speak("You have no meetings scheduled for today, sir.")
            return

        pending = [m for m in meetings if m["status"] == "pending"]
        active = [m for m in meetings if m["status"] == "active"]

        parts = []
        if active:
            parts.append(f"You are currently in {len(active)} active meeting{'s' if len(active) > 1 else ''}.")
        if pending:
            parts.append(f"You have {len(pending)} upcoming meeting{'s' if len(pending) > 1 else ''}:")
            for m in sorted(pending, key=lambda x: x["start_time"]):
                t = datetime.fromisoformat(m["start_time"]).strftime("%I:%M %p")
                parts.append(f"  {m['title']} at {t}.")
        if not pending and not active:
            completed = len([m for m in meetings if m["status"] == "completed"])
            parts.append(f"All {completed} meeting{'s' if completed > 1 else ''} for today are completed, sir.")

        self.jarvis.speak(" ".join(parts))

    def cancel_next_meeting(self):
        """Cancel the next pending meeting."""
        cancelled = self.scheduler.cancel_next_pending()
        if cancelled:
            t = datetime.fromisoformat(cancelled["start_time"]).strftime("%I:%M %p")
            self.jarvis.speak(f"Cancelled '{cancelled['title']}' at {t}, sir.")
        else:
            self.jarvis.speak("There are no upcoming meetings to cancel, sir.")

    def leave_meeting(self):
        """Force-leave the currently active meeting."""
        if self.bot and self.bot.is_in_meeting():
            self.bot.leave_meeting()
            # Mark active meetings as completed
            for m in self.scheduler.get_active():
                self.scheduler.mark_completed(m["id"])
            self.jarvis.speak("Leaving the meeting, sir.")
        else:
            self.jarvis.speak("You're not in any active meeting, sir.")

    def join_next_meeting(self):
        """Immediately join the next pending meeting."""
        pending = self.scheduler.get_pending()
        if not pending:
            self.jarvis.speak("No pending meetings to join, sir.")
            return

        meeting = pending[0]
        self.jarvis.speak(f"Joining '{meeting['title']}' now, sir.")
        self.scheduler.mark_active(meeting["id"])

        if self.bot:
            end_time = datetime.fromisoformat(meeting["end_time"])
            threading.Thread(
                target=self._run_join,
                args=(meeting, end_time),
                daemon=True,
            ).start()
        else:
            # Fallback: open in default browser
            webbrowser.open(meeting["meeting_url"])
            self.jarvis.speak("Opened the meeting link in your browser, sir.")

    def _run_join(self, meeting, end_time):
        """Thread target for joining a meeting via the bot."""
        try:
            self.bot.join_meeting(
                url=meeting["meeting_url"],
                end_time=end_time,
                auto_leave=meeting.get("auto_leave", True),
            )
        except Exception as e:
            print(f"[MeetingHandler] Join error: {e}")
        finally:
            self.scheduler.mark_completed(meeting["id"])

    def open_dashboard(self):
        """Open the schedule dashboard in the default browser."""
        if FASTAPI_AVAILABLE:
            import os
            port = int(os.getenv("MEETING_DASHBOARD_PORT", "5050"))
            url = f"http://127.0.0.1:{port}"
            webbrowser.open(url)
            self.jarvis.speak("Opening the meeting dashboard, sir.")
        else:
            self.jarvis.speak("The meeting dashboard is not available, sir. Please install FastAPI and uvicorn.")

    # ─── Command Router ───────────────────────────────────────────

    def process_meeting_command(self, command: str):
        """
        Route a meeting-related voice command to the appropriate handler.
        Called from core.py when a meeting intent is detected.
        """
        cmd = command.lower()

        # Leave meeting
        if any(phrase in cmd for phrase in ['leave the meeting', 'leave meeting', 'exit meeting', 'hang up', 'end the call']):
            self.leave_meeting()
            return

        # Cancel meeting
        if any(phrase in cmd for phrase in ['cancel my next meeting', 'cancel next meeting', 'cancel meeting']):
            self.cancel_next_meeting()
            return

        # List meetings
        if any(phrase in cmd for phrase in [
            'what meetings', 'my meetings', 'today\'s meetings',
            'meetings today', 'meeting schedule', 'show meetings',
            'list meetings', 'upcoming meetings',
        ]):
            self.list_today_meetings()
            return

        # Open dashboard
        if any(phrase in cmd for phrase in ['open schedule', 'open dashboard', 'meeting dashboard', 'schedule dashboard']):
            self.open_dashboard()
            return

        # Join next meeting
        if any(phrase in cmd for phrase in ['join meeting', 'join the meeting', 'join next meeting', 'join now']):
            self.join_next_meeting()
            return

        # Schedule a meeting (contains a URL)
        if re.search(r'https?://(?:meet\.google\.com|teams\.microsoft\.com|teams\.live\.com)', cmd):
            self.schedule_meeting(command)
            return

        # Fallback: try to parse as schedule command
        if any(word in cmd for word in ['schedule', 'add meeting', 'book meeting', 'create meeting']):
            self.schedule_meeting(command)
            return

        self.jarvis.speak("I didn't understand that meeting command, sir. You can ask me to schedule, list, join, or cancel meetings.")

    # ─── Shutdown ─────────────────────────────────────────────────

    def shutdown(self):
        """Clean up all meeting subsystems."""
        self.scheduler.shutdown()
        if self.bot:
            self.bot.close()
