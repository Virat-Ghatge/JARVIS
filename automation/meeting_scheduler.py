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
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List

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
            # Register periodic poller to catch imminent/due meetings every 10s
            self.scheduler.add_job(
                func=self._poll_and_trigger_due_meetings,
                trigger="interval",
                seconds=10,
                id="meeting_poll_daemon",
                replace_existing=True,
            )
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
        if end_time is None or end_time <= start_time:
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
                st_raw = entry["start_time"]
                if isinstance(st_raw, str):
                    start = datetime.fromisoformat(st_raw.replace("Z", "+00:00"))
                elif isinstance(st_raw, datetime):
                    start = st_raw
                else:
                    continue

                if start.tzinfo is not None:
                    start = start.astimezone().replace(tzinfo=None)

                et_raw = entry.get("end_time")
                end = None
                if isinstance(et_raw, str):
                    end = datetime.fromisoformat(et_raw.replace("Z", "+00:00"))
                elif isinstance(et_raw, datetime):
                    end = et_raw

                if end is not None and end.tzinfo is not None:
                    end = end.astimezone().replace(tzinfo=None)

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
        end = datetime.fromisoformat(meeting["end_time"]) if meeting.get("end_time") else start + timedelta(hours=1)
        now = datetime.now()
        trigger_time = start - timedelta(seconds=60)

        # Don't schedule past events that are completely over
        if now >= end:
            return

        # If meeting is starting now, imminent, or already in progress: trigger immediately
        if trigger_time <= now < end:
            if meeting.get("status") == "pending":
                print(f"[Scheduler] Meeting '{meeting['title']}' is starting now or in progress -- auto-joining immediately!")
                threading.Thread(target=self._trigger_join, args=[meeting], daemon=True).start()
            return

        self.scheduler.add_job(
            func=self._trigger_join,
            trigger=DateTrigger(run_date=trigger_time),
            id=f"meeting_{meeting['id']}",
            args=[meeting],
            replace_existing=True,
            misfire_grace_time=300,
        )
        print(f"[Scheduler] Trigger set for '{meeting['title']}' at {trigger_time.strftime('%H:%M:%S')}")

    def _poll_and_trigger_due_meetings(self):
        """Periodic poller running every 10s ensuring imminent or due meetings are never missed."""
        if not self.meeting_bot:
            return
        now = datetime.now()
        with self._lock:
            # Refresh from disk
            self._load()
            for m in list(self._meetings):
                if m.get("status") == "pending":
                    try:
                        start = datetime.fromisoformat(m["start_time"])
                        end = datetime.fromisoformat(m["end_time"]) if m.get("end_time") else start + timedelta(hours=1)
                        if now >= end:
                            m["status"] = "completed"
                            self._save()
                        elif (start - timedelta(seconds=60)) <= now < end:
                            if self.meeting_bot.is_in_meeting():
                                continue
                            print(f"[Scheduler Poller] Auto-joining due meeting: '{m['title']}'")
                            threading.Thread(target=self._trigger_join, args=[m], daemon=True).start()
                    except Exception as e:
                        pass

    def _reschedule_all_pending(self):
        """Re-register triggers for all future pending meetings (on startup)."""
        for m in self.get_pending():
            self._schedule_trigger(m)

    def _trigger_join(self, meeting: dict):
        """Callback fired by APScheduler or poller — launches the Playwright bot."""
        with self._lock:
            if meeting.get("status") != "pending":
                return
            meeting["status"] = "active"
            self._save()

        print(f"\n[Scheduler] [>] Auto-joining '{meeting['title']}'")
        try:
            end_time = datetime.fromisoformat(meeting["end_time"]) if meeting.get("end_time") else None
            self.meeting_bot.join_meeting(
                url=meeting["meeting_url"],
                end_time=end_time,
                auto_leave=meeting.get("auto_leave", True),
                title=meeting.get("title", "Online Meeting"),
            )
        except Exception as e:
            print(f"[Scheduler] Join failed: {e}")
        finally:
            self.mark_completed(meeting["id"])

    # ─── Conversational Intent Parsing ────────────────────────────

    @staticmethod
    def _parse_target_date(text: str, ref_date) -> Optional[date]:
        """Parse natural end date like '13th nov', 'nov 13', '2026-11-13'."""
        text = text.strip().rstrip('.,;)"\'')
        # ISO / standard date formats
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except Exception:
                pass

        # Strip ordinals: 13th -> 13
        cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text, flags=re.IGNORECASE).strip()
        month_map = {
            "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
            "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
            "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
            "nov": 11, "november": 11, "dec": 12, "december": 12,
        }

        # Pattern: "13 nov" or "13 november"
        m1 = re.search(r'(\d{1,2})\s*([a-zA-Z]+)', cleaned)
        if m1:
            day = int(m1.group(1))
            m_str = m1.group(2).lower()
            m_num = month_map.get(m_str[:3]) or month_map.get(m_str)
            if m_num:
                y = ref_date.year
                try:
                    d = datetime(y, m_num, day).date()
                    if d < ref_date:
                        d = datetime(y + 1, m_num, day).date()
                    return d
                except Exception:
                    pass

        # Pattern: "nov 13" or "november 13"
        m2 = re.search(r'([a-zA-Z]+)\s*(\d{1,2})', cleaned)
        if m2:
            m_str = m2.group(1).lower()
            day = int(m2.group(2))
            m_num = month_map.get(m_str[:3]) or month_map.get(m_str)
            if m_num:
                y = ref_date.year
                try:
                    d = datetime(y, m_num, day).date()
                    if d < ref_date:
                        d = datetime(y + 1, m_num, day).date()
                    return d
                except Exception:
                    pass

        return None

    def parse_schedule_command(self, command: str) -> dict | None:
        """
        Parse a natural-language scheduling command and return meeting dict.
        Supports:
            - URLs with quotes or punctuation stripped
            - Quoted titles and smart title extraction
            - Duration ('for 45 minutes', 'for 2 hours')
            - Recurrence ('daily', 'every day', 'till 13th nov', 'for 5 days')
        """
        # Extract URL and strip trailing quotes or punctuation
        url_match = re.search(
            r'(https?://(?:meet\.google\.com|teams\.microsoft\.com|teams\.live\.com)\S+)',
            command, re.IGNORECASE,
        )
        if not url_match:
            return None
        meeting_url = url_match.group(1).rstrip('"\'.,;)>]')

        # Extract time
        start_time = self._parse_time(command)
        if start_time is None:
            return None

        # Extract duration
        duration_minutes = 60
        dur_match = re.search(r'\bfor\s+(\d+)\s*(minute|minutes|min|mins|hour|hours|hr|hrs)\b', command, re.IGNORECASE)
        if dur_match:
            val = int(dur_match.group(1))
            unit = dur_match.group(2).lower()
            if unit.startswith("hour") or unit.startswith("hr"):
                duration_minutes = val * 60
            else:
                duration_minutes = val
        end_time = start_time + timedelta(minutes=duration_minutes)

        # Extract recurrence
        recurrence_days = 1
        if re.search(r'\b(daily|every\s+day)\b', command, re.IGNORECASE):
            for_days_match = re.search(r'for\s+(\d+)\s+days?', command, re.IGNORECASE)
            if for_days_match:
                recurrence_days = min(int(for_days_match.group(1)), 30)
            else:
                till_match = re.search(r'\b(?:till|until)\s+([a-zA-Z0-9\s\-_,]+)', command, re.IGNORECASE)
                if till_match:
                    target_date = self._parse_target_date(till_match.group(1), start_time.date())
                    if target_date:
                        diff = (target_date - start_time.date()).days + 1
                        recurrence_days = max(1, min(diff, 30))
                    else:
                        recurrence_days = 7
                else:
                    recurrence_days = 7

        # Extract title
        title = self._extract_title(command)

        return {
            "title": title,
            "meeting_url": meeting_url,
            "start_time": start_time,
            "end_time": end_time,
            "duration_minutes": duration_minutes,
            "recurrence_days": recurrence_days,
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
        # 1. Check for quoted title following named/called/titled
        named_q = re.search(r'(?:named|called|titled)\s+["\']([^"\']+)["\']', command, re.IGNORECASE)
        if named_q:
            return named_q.group(1).strip()

        # 2. Check for any quoted string that is not a URL and not a time
        for q in re.findall(r'["\']([^"\']+)["\']', command):
            q_clean = q.strip()
            if not (q_clean.startswith("http://") or q_clean.startswith("https://") or "meet.google.com" in q_clean or "teams.microsoft.com" in q_clean or "teams.live.com" in q_clean):
                if not re.match(r'^\d{1,2}(:\d{2})?\s*(am|pm)?$', q_clean, re.IGNORECASE):
                    return q_clean

        # 3. Check for unquoted 'named X' or 'called X' or 'titled X'
        unquoted_named = re.search(
            r'(?:named|called|titled)\s+([^,]+?)(?=\s+(?:with|link|at|in|for|daily|every|https?://)|$)',
            command, re.IGNORECASE,
        )
        if unquoted_named:
            cand = unquoted_named.group(1).strip('"\' ,')
            if cand:
                return cand

        # 4. Fallback stripping
        text = command
        # Remove URLs
        text = re.sub(r'https?://\S+', '', text)
        # Remove recurrence phrases
        text = re.sub(r'\b(daily|every\s+day|till\s+.*|until\s+.*)$', '', text, flags=re.IGNORECASE)
        # Remove time phrases
        text = re.sub(r'\b(at\s+\d.*|in\s+\d+\s*(?:minute|minutes|min|mins|hour|hours|hr|hrs)|for\s+\d+\s*(?:minute|minutes|min|mins|hour|hours|hr|hrs)).*$', '', text, flags=re.IGNORECASE)
        # Remove with link / link
        text = re.sub(r'\b(with\s+link|link|with)\b.*$', '', text, flags=re.IGNORECASE)
        # Remove prefixes
        text = re.sub(r'^(jarvis\s*,?\s*)?(schedule|add|create|set up|book)\s+(a\s+)?(meeting\s+)?(named\s+|called\s+|titled\s+)?', '', text, flags=re.IGNORECASE)
        text = text.strip('"\' ,;:-')
        return text if text else "Untitled Meeting"

    # ─── Shutdown ─────────────────────────────────────────────────

    def shutdown(self):
        """Gracefully stop the scheduler."""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
