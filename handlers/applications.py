"""
Backward-compatibility shim for ApplicationHandler.
Canonical location is integrations.handlers.applications.
"""
from integrations.handlers.applications import ApplicationHandler

__all__ = ["ApplicationHandler"]
