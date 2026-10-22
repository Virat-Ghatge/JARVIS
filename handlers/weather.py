"""
Backward-compatibility shim for WeatherHandler.
Canonical location is integrations.handlers.weather.
"""
from integrations.handlers.weather import WeatherHandler

__all__ = ["WeatherHandler"]
