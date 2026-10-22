"""
Backward-compatibility shim for AlarmHandler.
Canonical location is integrations.handlers.alarm.
"""
from integrations.handlers.alarm import AlarmHandler

__all__ = ["AlarmHandler"]
