#!/usr/bin/env python3
"""
Meeting Scheduler Module
Handles meeting schedule persistence, CRUD operations, background trigger engine,
and conversational intent parsing for voice/chat-based schedule management.
"""

import json
import os
import re
import uuid
import threading
from datetime import datetime, timedelta

# APScheduler for background trigger engine
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.date import DateTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    print("[!] APScheduler not installed. Meeting auto-join disabled.")


# ─── Schema ───────────────────────────────────────────────────────
# Each meeting entry:
# {
#   "id": "uuid",
#   "title": "Team Standup",
#   "platform": "google_meet" | "teams",
#   "meeting_url": "https://meet.google.com/abc-defg-hij",
#   "start_time": "2026-10-12T14:00:00",   (ISO 8601 local)
#   "end_time":   "2026-10-12T15:00:00",
#   "auto_leave": true,
#   "status": "pending" | "active" | "completed" | "cancelled"
# }
# ──────────────────────────────────────────────────────────────────

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULE_FILE = os.path.join(BASE_DIR, "config", "meetings.json")


class MeetingScheduler:
    """Manages meeting schedules with JSON persistence and APScheduler triggers."""

    def __init__(self, meeting_bot=None):
        """
        Args:
            meeting_bot: Optional MeetingBot instance. When provided the scheduler
                         auto-triggers bot.join_meeting() ahead of each event.
        """
        self.meeting_bot = meeting_bot
        self._lock = threading.Lock()
        self._meetings: list[dict] = []

        # Ensure config dir exists
        os.makedirs(os.path.dirname(SCHEDULE_FILE), exist_ok=True)

        # Load persisted schedule
        self._load()

        # Background scheduler
        self.scheduler = None
        if APSCHEDULER_AVAILABLE:
            self.scheduler = BackgroundScheduler(daemon=True)
            self.scheduler.start()
            # Re-schedule all future pending meetings that were persisted
            self._reschedule_all_pending()

    # ─── Persistence ──────────────────────────────────────────────

    def _load(self):
        """Load meetings from JSON file."""
        if os.path.exists(SCHEDULE_FILE):
            try:
                with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                    self._meetings = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._meetings = []
        else:
            self._meetings = []

    def _save(self):
        """Persist meetings to JSON file."""
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(self._meetings, f, indent=2, ensure_ascii=False)

    # ─── CRUD ─────────────────────────────────────────────────────

    def add_meeting(self, title: str, meeting_url: str,
                    start_time: datetime, end_time: datetime = None,
                    auto_leave: bool = True) -> dict:
        """Add a new meeting and schedule its trigger."""
        platform = self._detect_platform(meeting_url)
        if end_time is None:
            end_time = start_time + timedelta(hours=1)

        meeting = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "platform": platform,
            "meeting_url": meeting_url,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "auto_leave": auto_leave,
            "status": "pending",
        }

        with self._lock:
            self._meetings.append(meeting)
            self._save()

        # Schedule the trigger
        self._schedule_trigger(meeting)
        return meeting

    def cancel_meeting(self, meeting_id: str) -> bool:
        """Mark a meeting as cancelled and remove its trigger."""
        with self._lock:
            for m in self._meetings:
                if m["id"] == meeting_id:
                    m["status"] = "cancelled"
                    self._save()
                    # Remove APScheduler job
                    if self.scheduler:
                        try:
                            self.scheduler.remove_job(f"meeting_{meeting_id}")
                        except Exception:
                            pass
                    return True
        return False

    def cancel_next_pending(self) -> dict | None:
        """Cancel the nearest pending meeting. Returns cancelled entry or None."""
        pending = self.get_pending()
        if not pending:
            return None
        target = pending[0]
        self.cancel_meeting(target["id"])
        return target

    def mark_active(self, meeting_id: str):
        """Set status to active."""
        with self._lock:
            for m in self._meetings:
                if m["id"] == meeting_id:
                    m["status"] = "active"
                    self._save()
                    return

    def mark_completed(self, meeting_id: str):
        """Set status to completed."""
        with self._lock:
            for m in self._meetings:
                if m["id"] == meeting_id:
                    m["status"] = "completed"
                    self._save()
                    return

    def get_all(self) -> list[dict]:
        return list(self._meetings)

    def get_pending(self) -> list[dict]:
        """Return pending meetings sorted by start_time (soonest first)."""
        now = datetime.now().isoformat()
        return sorted(
            [m for m in self._meetings if m["status"] == "pending" and m["start_time"] >= now],
            key=lambda m: m["start_time"],
        )

    def get_today(self) -> list[dict]:
        """Return today's meetings (all statuses)."""
        today = datetime.now().date().isoformat()
        return [
            m for m in self._meetings
            if m["start_time"].startswith(today)
        ]

    def get_active(self) -> list[dict]:
        """Return currently active meetings."""
        return [m for m in self._meetings if m["status"] == "active"]

    def get_by_id(self, meeting_id: str) -> dict | None:
        for m in self._meetings:
            if m["id"] == meeting_id:
                return m
        return None

    def bulk_import(self, entries: list[dict]) -> int:
        """Import a list of meeting dicts. Returns count of successfully imported."""
        count = 0
        for entry in entries:
            try:
                start = datetime.fromisoformat(entry["start_time"])
                end = datetime.fromisoformat(entry["end_time"]) if entry.get("end_time") else None
                self.add_meeting(
                    title=entry.get("title", "Untitled Meeting"),
                    meeting_url=entry.get("meeting_url", ""),
                    start_time=start,
                    end_time=end,
                    auto_leave=entry.get("auto_leave", True),
                )
                count += 1
            except Exception as e:
                print(f"[Meeting Import] Skipping invalid entry: {e}")
        return count

    # ─── Platform Detection ───────────────────────────────────────

    @staticmethod
    def _detect_platform(url: str) -> str:
        if "meet.google.com" in url:
            return "google_meet"
        elif "teams.microsoft.com" in url or "teams.live.com" in url:
            return "teams"
        return "unknown"

    # ─── APScheduler Trigger Engine ───────────────────────────────

    def _schedule_trigger(self, meeting: dict):
        """Schedule the bot to join 60 seconds before start_time."""
        if not self.scheduler or not self.meeting_bot:
            return

        start = datetime.fromisoformat(meeting["start_time"])
        trigger_time = start - timedelta(seconds=60)

        # Don't schedule past events
        if trigger_time <= datetime.now():
            return

        self.scheduler.add_job(
            func=self._trigger_join,
            trigger=DateTrigger(run_date=trigger_time),
            id=f"meeting_{meeting['id']}",
            args=[meeting],
            replace_existing=True,
            misfire_grace_time=120,
        )
        print(f"[Scheduler] Trigger set for '{meeting['title']}' at {trigger_time.strftime('%H:%M:%S')}")

    def _reschedule_all_pending(self):
        """Re-register triggers for all future pending meetings (on startup)."""
        for m in self.get_pending():
            self._schedule_trigger(m)

    def _trigger_join(self, meeting: dict):
        """Callback fired by APScheduler — launches the Playwright bot."""
        if meeting["status"] != "pending":
            return
        print(f"\n[Scheduler] ▶ Auto-joining '{meeting['title']}'")
        self.mark_active(meeting["id"])
        try:
            end_time = datetime.fromisoformat(meeting["end_time"])
            self.meeting_bot.join_meeting(
                url=meeting["meeting_url"],
                end_time=end_time,
                auto_leave=meeting.get("auto_leave", True),
            )
        except Exception as e:
            print(f"[Scheduler] Join failed: {e}")
        finally:
            self.mark_completed(meeting["id"])

    # ─── Conversational Intent Parsing ────────────────────────────

    def parse_schedule_command(self, command: str) -> dict | None:
        """
        Parse a natural-language scheduling command and return meeting dict.
        Patterns:
            "schedule Team Standup at 2:30 PM with link https://meet.google.com/abc"
            "add meeting Daily Sync at 14:00 link https://teams.microsoft.com/l/..."
            "schedule Lecture in 15 minutes with https://meet.google.com/xyz"
        Returns None if the command doesn't match a scheduling pattern.
        """
        # Extract URL
        url_match = re.search(
            r'(https?://(?:meet\.google\.com|teams\.microsoft\.com|teams\.live\.com)\S+)',
            command, re.IGNORECASE,
        )
        if not url_match:
            return None
        meeting_url = url_match.group(1)

        # Extract time
        start_time = self._parse_time(command)
        if start_time is None:
            return None

        # Extract title (text between schedule/add and the time/link keywords)
        title = self._extract_title(command)

        return {
            "title": title,
            "meeting_url": meeting_url,
            "start_time": start_time,
        }

    def _parse_time(self, text: str) -> datetime | None:
        """
        Parse time from natural language.
        Supports: "at 2:30 PM", "at 14:00", "in 15 minutes", "in 1 hour"
        """
        now = datetime.now()

        # Relative: "in X minutes/hours"
        rel_match = re.search(r'in\s+(\d+)\s+(minute|minutes|min|mins|hour|hours|hr|hrs)', text, re.IGNORECASE)
        if rel_match:
            amount = int(rel_match.group(1))
            unit = rel_match.group(2).lower()
            if unit.startswith("hour") or unit.startswith("hr"):
                return now + timedelta(hours=amount)
            else:
                return now + timedelta(minutes=amount)

        # Absolute: "at HH:MM AM/PM" or "at HH:MM"
        abs_match = re.search(r'at\s+(\d{1,2}):(\d{2})\s*(am|pm)?', text, re.IGNORECASE)
        if abs_match:
            hour = int(abs_match.group(1))
            minute = int(abs_match.group(2))
            period = abs_match.group(3)
            if period:
                if period.lower() == "pm" and hour != 12:
                    hour += 12
                elif period.lower() == "am" and hour == 12:
                    hour = 0
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # If the time has already passed today, schedule for tomorrow
            if target <= now:
                target += timedelta(days=1)
            return target

        # Bare hour: "at 2 PM"
        bare_match = re.search(r'at\s+(\d{1,2})\s*(am|pm)', text, re.IGNORECASE)
        if bare_match:
            hour = int(bare_match.group(1))
            period = bare_match.group(2)
            if period.lower() == "pm" and hour != 12:
                hour += 12
            elif period.lower() == "am" and hour == 12:
                hour = 0
            target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

        return None

    @staticmethod
    def _extract_title(command: str) -> str:
        """Extract the meeting title from the command string."""
        # Remove common prefixes
        text = re.sub(
            r'^(jarvis\s*,?\s*)?(schedule|add|create|set up|book)\s+(a\s+)?(meeting\s+)?',
            '', command, flags=re.IGNORECASE,
        ).strip()
        # Remove time/link parts
        text = re.sub(r'\b(at|in)\s+\d.*', '', text, flags=re.IGNORECASE).strip()
        text = re.sub(r'(with\s+)?(link\s+)?https?://\S+', '', text, flags=re.IGNORECASE).strip()
        # Clean up trailing keywords
        text = re.sub(r'\s+(with|link|at|for)\s*$', '', text, flags=re.IGNORECASE).strip()
        return text if text else "Untitled Meeting"

    # ─── Shutdown ─────────────────────────────────────────────────

    def shutdown(self):
        """Gracefully stop the scheduler."""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
