#!/usr/bin/env python3
"""
Weather Module
Handles weather information using OpenWeatherMap API
"""

import requests
import datetime


WMO_WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow fall",
    73: "moderate snow fall",
    75: "heavy snow fall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


class WeatherHandler:
    """Handles weather operations with OpenWeatherMap and keyless Open-Meteo / wttr.in fallback."""

    def __init__(self, jarvis, api_key=None):
        self.jarvis = jarvis
        self._custom_api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"
        try:
            from config.settings import DEFAULT_CITY
            self.default_city = DEFAULT_CITY or "Jaipur"
        except Exception:
            self.default_city = "Jaipur"

    @property
    def api_key(self):
        # An explicit empty string is meaningful: callers can force the
        # keyless Open-Meteo path even when a machine-level weather key is
        # configured. ``None`` means "resolve the configured key".
        if self._custom_api_key is not None:
            return str(self._custom_api_key).strip()
        try:
            from config.settings import load_vault
            vault_key = load_vault().get("services", {}).get("openweathermap", "")
            if vault_key:
                return vault_key
        except Exception:
            pass
        from config.settings import WEATHER_API_KEY
        return WEATHER_API_KEY

    def _get_location(self, command):
        """Extract city name from command string."""
        import re as _re

        location = command.lower().strip().rstrip('?.,!')

        # Longest prefix first so 'weather in' does not shadow
        prefixes = [
            'what will the weather be like in', 'what will the weather be in',
            'what will be the weather in', "what's the weather like in",
            'what is the weather like in', 'whats the weather like in',
            'what is the weather in', "what's the weather in",
            'whats the weather in', 'how is the weather in',
            "how's the weather in", 'how is the weather for',
            'tell me the weather in', 'tell me the weather for',
            'current weather in', 'weather forecast for',
            'weather forecast in', 'forecast for', 'forecast in',
            'weather in', 'weather for', 'weather at',
            'temperature in', 'temperature at',
            'weather', 'temperature', 'forecast',
        ]
        matched = False
        for prefix in prefixes:
            if location.startswith(prefix):
                location = location[len(prefix):].strip()
                matched = True
                break

        if not matched:
            m = _re.search(r'\b(?:weather|forecast|temperature)\b.*?\b(?:in|for|at)\s+([^?.,!]+)', command, _re.IGNORECASE)
            if m:
                location = m.group(1).strip()

        location = _re.sub(r'\b(?:today|tomorrow|now|please|currently)\b', '', location, flags=_re.IGNORECASE).strip()
        location = ' '.join(location.split()).strip().rstrip('?.,!')
        return location if location else self.default_city

    def _geocode_keyless(self, location: str):
        """Geocode location to (lat, lon, city, country) using Open-Meteo."""
        import urllib.parse
        clean_loc = location.strip()
        try:
            url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(clean_loc)}&count=1&language=en&format=json"
            res = requests.get(url, headers={"User-Agent": "JARVIS-Weather/1.0"}, timeout=6)
            if res.status_code == 200:
                data = res.json()
                results = data.get("results", [])
                if results:
                    first = results[0]
                    return (
                        first["latitude"],
                        first["longitude"],
                        first.get("name", clean_loc),
                        first.get("country", ""),
                    )
        except Exception as e:
            print(f"[Weather] Keyless geocode error: {e}")
        return None

    def _get_weather_keyless(self, location: str) -> bool:
        """Fetch current weather without an API key using Open-Meteo (or wttr.in fallback)."""
        geo = self._geocode_keyless(location)
        if geo:
            lat, lon, city, country = geo
            try:
                url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m&timezone=auto"
                res = requests.get(url, headers={"User-Agent": "JARVIS-Weather/1.0"}, timeout=8)
                if res.status_code == 200:
                    data = res.json()
                    curr = data.get("current", {})
                    temp = curr.get("temperature_2m", 0.0)
                    feels_like = curr.get("apparent_temperature", temp)
                    humidity = curr.get("relative_humidity_2m", 0)
                    wind_speed = curr.get("wind_speed_10m", 0.0)
                    w_code = curr.get("weather_code", 0)
                    desc = WMO_WEATHER_CODES.get(w_code, "partly cloudy")
                    country_suffix = f", {country}" if country else ""
                    report = (
                        f"Current weather in {city}{country_suffix}: "
                        f"{desc}. Temperature is {temp} degrees Celsius, "
                        f"feels like {feels_like} degrees. "
                        f"Humidity is {humidity} percent with wind speed of {wind_speed} meters per second."
                    )
                    self.jarvis.speak(report)
                    return True
            except Exception as e:
                print(f"[Weather] Open-Meteo current weather error: {e}")

        # Fallback to wttr.in
        try:
            import urllib.parse
            url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
            res = requests.get(url, headers={"User-Agent": "JARVIS-Weather/1.0"}, timeout=8)
            if res.status_code == 200:
                data = res.json()
                current = data.get("current_condition", [{}])[0]
                temp = current.get("temp_C", "N/A")
                feels_like = current.get("FeelsLikeC", temp)
                humidity = current.get("humidity", "N/A")
                desc = current.get("weatherDesc", [{}])[0].get("value", "clear")
                report = (
                    f"Current weather in {location}: "
                    f"{desc}. Temperature is {temp} degrees Celsius, "
                    f"feels like {feels_like} degrees. "
                    f"Humidity is {humidity} percent."
                )
                self.jarvis.speak(report)
                return True
        except Exception as e:
            print(f"[Weather] wttr.in fallback error: {e}")

        self.jarvis.speak(f"I couldn't find weather data for {location}. Please check the city name.")
        return False

    def _get_forecast_keyless(self, location: str) -> bool:
        """Fetch tomorrow's forecast without an API key using Open-Meteo."""
        geo = self._geocode_keyless(location)
        if geo:
            lat, lon, city, country = geo
            try:
                url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=auto"
                res = requests.get(url, headers={"User-Agent": "JARVIS-Weather/1.0"}, timeout=8)
                if res.status_code == 200:
                    data = res.json()
                    daily = data.get("daily", {})
                    if len(daily.get("time", [])) > 1:
                        max_temp = daily["temperature_2m_max"][1]
                        min_temp = daily["temperature_2m_min"][1]
                        avg_temp = round((max_temp + min_temp) / 2.0, 1)
                        w_code = daily["weather_code"][1]
                        desc = WMO_WEATHER_CODES.get(w_code, "fair conditions")
                        country_suffix = f", {country}" if country else ""
                        report = (
                            f"Weather forecast for {city}{country_suffix} tomorrow: "
                            f"{desc}. Average temperature of {avg_temp} degrees Celsius, "
                            f"ranging from {min_temp} to {max_temp} degrees."
                        )
                        self.jarvis.speak(report)
                        return True
            except Exception as e:
                print(f"[Weather] Open-Meteo forecast error: {e}")

        # Fallback to wttr.in
        try:
            import urllib.parse
            url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
            res = requests.get(url, headers={"User-Agent": "JARVIS-Weather/1.0"}, timeout=8)
            if res.status_code == 200:
                data = res.json()
                weather_days = data.get("weather", [])
                if len(weather_days) > 1:
                    tmrw = weather_days[1]
                    avg_temp = tmrw.get("avgtempC", "N/A")
                    min_temp = tmrw.get("mintempC", "N/A")
                    max_temp = tmrw.get("maxtempC", "N/A")
                    hourly = tmrw.get("hourly", [{}])
                    mid_h = hourly[len(hourly) // 2] if hourly else {}
                    desc = mid_h.get("weatherDesc", [{}])[0].get("value", "fair conditions")
                    report = (
                        f"Weather forecast for {location} tomorrow: "
                        f"{desc}. Average temperature of {avg_temp} degrees Celsius, "
                        f"ranging from {min_temp} to {max_temp} degrees."
                    )
                    self.jarvis.speak(report)
                    return True
        except Exception as e:
            print(f"[Weather] wttr.in forecast fallback error: {e}")

        self.jarvis.speak(f"I couldn't find forecast data for {location}. Please check the city name.")
        return False

    def get_current_weather(self, command):
        """Get current weather for a location with automatic keyless fallback."""
        location = self._get_location(command)

        if not location:
            if hasattr(self.jarvis, "listen"):
                self.jarvis.speak("Which city would you like the weather for?")
                location = self.jarvis.listen()
            if not location:
                location = self.default_city

        if not self.api_key:
            self._get_weather_keyless(location)
            return

        try:
            url = f"{self.base_url}/weather"
            params = {
                'q': location,
                'appid': self.api_key,
                'units': 'metric'
            }

            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if response.status_code == 200:
                city = data['name']
                country = data['sys']['country']
                temp = data['main']['temp']
                feels_like = data['main']['feels_like']
                description = data['weather'][0]['description']
                humidity = data['main']['humidity']
                wind_speed = data['wind']['speed']

                weather_report = (
                    f"Current weather in {city}, {country}: "
                    f"{description}. Temperature is {temp} degrees Celsius, "
                    f"feels like {feels_like} degrees. "
                    f"Humidity is {humidity} percent with wind speed of {wind_speed} meters per second."
                )
                self.jarvis.speak(weather_report)
            elif response.status_code in (401, 429):
                # Fallback to keyless Open-Meteo when API key fails or rate-limits
                self._get_weather_keyless(location)
            elif response.status_code == 404:
                self.jarvis.speak(f"I couldn't find weather data for {location}. Please check the city name.")
            else:
                self._get_weather_keyless(location)

        except requests.exceptions.RequestException:
            self._get_weather_keyless(location)
        except Exception:
            self._get_weather_keyless(location)

    def get_forecast(self, command):
        """Get weather forecast for a location with automatic keyless fallback."""
        location = self._get_location(command)

        if not location:
            if hasattr(self.jarvis, "listen"):
                self.jarvis.speak("Which city would you like the forecast for?")
                location = self.jarvis.listen()
            if not location:
                location = self.default_city

        if not self.api_key:
            self._get_forecast_keyless(location)
            return

        try:
            url = f"{self.base_url}/forecast"
            params = {
                'q': location,
                'appid': self.api_key,
                'units': 'metric',
                'cnt': 8
            }

            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if response.status_code == 200:
                city = data['city']['name']
                country = data['city']['country']

                tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
                tomorrow_date = tomorrow.strftime('%Y-%m-%d')

                tomorrow_forecast = []
                for item in data['list']:
                    if tomorrow_date in item['dt_txt']:
                        tomorrow_forecast.append(item)

                if tomorrow_forecast:
                    temps = [item['main']['temp'] for item in tomorrow_forecast]
                    avg_temp = round(sum(temps) / len(temps), 1)
                    min_temp = round(min(temps), 1)
                    max_temp = round(max(temps), 1)

                    descriptions = [item['weather'][0]['description'] for item in tomorrow_forecast]
                    main_description = max(set(descriptions), key=descriptions.count)

                    forecast_report = (
                        f"Weather forecast for {city}, {country} tomorrow: "
                        f"{main_description}. Average temperature of {avg_temp} degrees Celsius, "
                        f"ranging from {min_temp} to {max_temp} degrees."
                    )
                    self.jarvis.speak(forecast_report)
                else:
                    next_item = data['list'][0]
                    time_str = next_item['dt_txt'].split()[1][:5]
                    temp = next_item['main']['temp']
                    desc = next_item['weather'][0]['description']
                    self.jarvis.speak(
                        f"Next forecast for {city} at {time_str}: {desc}, "
                        f"temperature {temp} degrees Celsius."
                    )
            elif response.status_code in (401, 429):
                self._get_forecast_keyless(location)
            elif response.status_code == 404:
                self.jarvis.speak(f"I couldn't find forecast data for {location}. Please check the city name.")
            else:
                self._get_forecast_keyless(location)

        except requests.exceptions.RequestException:
            self._get_forecast_keyless(location)
        except Exception:
            self._get_forecast_keyless(location)

    def test_api_key(self):
        """Test if the API key is working or keyless fallback is available."""
        if not self.api_key:
            geo = self._geocode_keyless("London")
            return geo is not None
        try:
            url = f"{self.base_url}/weather"
            params = {'q': 'London', 'appid': self.api_key}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return True
            else:
                # Check keyless fallback
                geo = self._geocode_keyless("London")
                return geo is not None
        except Exception:
            geo = self._geocode_keyless("London")
            return geo is not None

    def process_weather_command(self, command):
        """Process weather-related commands"""
        if 'forecast' in command or 'tomorrow' in command:
            self.get_forecast(command)
        else:
            self.get_current_weather(command)


# Backward-compatible capture mock and module-level functions
class _SpeechCaptureJarvis:
    def __init__(self):
        self.last_speech = ""

    def speak(self, text: str) -> None:
        self.last_speech = text


def get_weather(location: str = "") -> str:
    mock = _SpeechCaptureJarvis()
    handler = WeatherHandler(mock)
    cmd = f"weather in {location}" if location else "weather"
    handler.get_current_weather(cmd)
    return mock.last_speech


def handle_weather(location: str = "") -> str:
    return get_weather(location)


def fetch_weather(location: str = "") -> str:
    return get_weather(location)
