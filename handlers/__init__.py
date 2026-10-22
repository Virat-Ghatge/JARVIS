"""
Backward-compatibility shims for JARVIS handlers.
Canonical locations are integrations.handlers.*
"""
from integrations.handlers.alarm import AlarmHandler
from integrations.handlers.applications import ApplicationHandler
from integrations.handlers.date_time import DateTimeHandler
from integrations.handlers.music import MusicHandler
from integrations.handlers.qa_handler import QAHandler
from integrations.handlers.system_controls import SystemControls
from integrations.handlers.system_info import SystemInfoHandler
from integrations.handlers.weather import WeatherHandler
from integrations.handlers.web_search import WebSearchHandler

__all__ = [
    "AlarmHandler",
    "ApplicationHandler",
    "DateTimeHandler",
    "MusicHandler",
    "QAHandler",
    "SystemControls",
    "SystemInfoHandler",
    "WeatherHandler",
    "WebSearchHandler",
]
