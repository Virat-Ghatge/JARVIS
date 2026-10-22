"""
Integrations Handlers package for JARVIS command execution.
"""
from .date_time import DateTimeHandler
from .applications import ApplicationHandler
from .music import MusicHandler
from .web_search import WebSearchHandler
from .alarm import AlarmHandler
from .weather import WeatherHandler
from .system_controls import SystemControls
from .system_info import SystemInfoHandler
from .qa_handler import QAHandler

__all__ = [
    "DateTimeHandler",
    "ApplicationHandler",
    "MusicHandler",
    "WebSearchHandler",
    "AlarmHandler",
    "WeatherHandler",
    "SystemControls",
    "SystemInfoHandler",
    "QAHandler",
]
