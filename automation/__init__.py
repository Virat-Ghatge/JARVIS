"""Automation package for JARVIS meetings and scheduler."""
from .meeting_bot import MeetingBot, PLAYWRIGHT_AVAILABLE
from .meeting_scheduler import MeetingScheduler, APSCHEDULER_AVAILABLE
from .schedule_interface import ScheduleInterface, FASTAPI_AVAILABLE
from .meeting_handler import MeetingHandler

__all__ = [
    "MeetingBot",
    "PLAYWRIGHT_AVAILABLE",
    "MeetingScheduler",
    "APSCHEDULER_AVAILABLE",
    "ScheduleInterface",
    "FASTAPI_AVAILABLE",
    "MeetingHandler",
]
