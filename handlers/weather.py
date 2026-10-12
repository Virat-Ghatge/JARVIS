#!/usr/bin/env python3
"""
Weather Module
Handles weather information using OpenWeatherMap API
"""

import requests
import datetime


class WeatherHandler:
    """Handles weather operations"""

    def __init__(self, jarvis, api_key):
        self.jarvis = jarvis
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.default_city = None  # Will try to detect or ask user

        # Test API key on startup (for debugging)
        if self.api_key:
            print("Debug: Testing weather API key...")
            self.test_api_key()
        else:
            print("Debug: No weather API key provided.")

    def _get_location(self, command):
        """Extract city name from command string."""
        import re as _re

        location = command.lower().strip().rstrip('?.,!')

        # Longest prefix first so 'weather in' does not shadow
        # 'what is the weather in', etc.
        prefixes = [
            'what is the weather in', "what's the weather in",
            'whats the weather in', 'how is the weather in',
            'current weather in', 'weather forecast for',
            'forecast for', 'forecast in',
            'weather in', 'weather for', 'weather at',
            'temperature in', 'temperature at',
            'weather', 'temperature',
        ]
        for prefix in prefixes:
            if location.startswith(prefix):
                location = location[len(prefix):].strip()
                break  # apply only the first (longest) match

        # Remove filler words with word boundaries ONLY.
        # NEVER use plain .replace() on short words like 'a' — it deletes
        # every occurrence of that character from the entire string.
        for word in ['today', 'tomorrow', 'now', 'please', 'currently']:
            location = _re.sub(r'' + word + r'', '', location)

        location = ' '.join(location.split()).strip().rstrip('?.,!')
        return location if location else self.default_city

    def _kelvin_to_celsius(self, kelvin):
        """Convert Kelvin to Celsius"""
        return round(kelvin - 273.15, 1)

    def _kelvin_to_fahrenheit(self, kelvin):
        """Convert Kelvin to Fahrenheit"""
        return round((kelvin - 273.15) * 9/5 + 32, 1)

    def get_current_weather(self, command):
        """Get current weather for a location"""
        if not self.api_key:
            self.jarvis.speak("Weather API key is not configured. Please set up your API key.")
            return

        location = self._get_location(command)

        if not location:
            self.jarvis.speak("Which city would you like the weather for?")
            location = self.jarvis.listen()
            if not location:
                self.jarvis.speak("I didn't catch that. Please try again.")
                return

        try:
            url = f"{self.base_url}/weather"
            params = {
                'q': location,
                'appid': self.api_key,
                'units': 'metric'  # Use metric for Celsius
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

                # Format the response
                weather_report = (
                    f"Current weather in {city}, {country}: "
                    f"{description}. Temperature is {temp} degrees Celsius, "
                    f"feels like {feels_like} degrees. "
                    f"Humidity is {humidity} percent with wind speed of {wind_speed} meters per second."
                )
                self.jarvis.speak(weather_report)

            elif response.status_code == 401:
                self.jarvis.speak("The weather API key is invalid. Please check your API key.")
                print(f"Debug: API Error - {data.get('message', 'Unknown error')}")
            elif response.status_code == 429:
                self.jarvis.speak("Weather API rate limit exceeded. Please try again in a few minutes.")
            elif response.status_code == 404:
                self.jarvis.speak(f"I couldn't find weather data for {location}. Please check the city name.")
            else:
                error_msg = data.get('message', 'Unknown error')
                print(f"Debug: Weather API Error {response.status_code} - {error_msg}")
                self.jarvis.speak(f"I'm having trouble fetching the weather data. Error: {response.status_code}")

        except requests.exceptions.RequestException:
            self.jarvis.speak("I'm unable to connect to the weather service. Please check your internet connection.")
        except Exception as e:
            self.jarvis.speak("An error occurred while fetching weather data.")

    def get_forecast(self, command):
        """Get weather forecast for a location"""
        if not self.api_key:
            self.jarvis.speak("Weather API key is not configured. Please set up your API key.")
            return

        location = self._get_location(command)

        if not location:
            self.jarvis.speak("Which city would you like the forecast for?")
            location = self.jarvis.listen()
            if not location:
                self.jarvis.speak("I didn't catch that. Please try again.")
                return

        try:
            url = f"{self.base_url}/forecast"
            params = {
                'q': location,
                'appid': self.api_key,
                'units': 'metric',
                'cnt': 8  # Get next 24 hours (3-hour intervals x 8)
            }

            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if response.status_code == 200:
                city = data['city']['name']
                country = data['city']['country']

                # Get forecast for tomorrow
                tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
                tomorrow_date = tomorrow.strftime('%Y-%m-%d')

                # Filter for tomorrow's forecast
                tomorrow_forecast = []
                for item in data['list']:
                    if tomorrow_date in item['dt_txt']:
                        tomorrow_forecast.append(item)

                if tomorrow_forecast:
                    # Get average/min/max temps for tomorrow
                    temps = [item['main']['temp'] for item in tomorrow_forecast]
                    avg_temp = round(sum(temps) / len(temps), 1)
                    min_temp = round(min(temps), 1)
                    max_temp = round(max(temps), 1)

                    # Get most common weather description
                    descriptions = [item['weather'][0]['description'] for item in tomorrow_forecast]
                    main_description = max(set(descriptions), key=descriptions.count)

                    forecast_report = (
                        f"Weather forecast for {city}, {country} tomorrow: "
                        f"{main_description}. Average temperature of {avg_temp} degrees Celsius, "
                        f"ranging from {min_temp} to {max_temp} degrees."
                    )
                    self.jarvis.speak(forecast_report)
                else:
                    # Just give next available forecast
                    next_item = data['list'][0]
                    time_str = next_item['dt_txt'].split()[1][:5]
                    temp = next_item['main']['temp']
                    desc = next_item['weather'][0]['description']
                    self.jarvis.speak(
                        f"Next forecast for {city} at {time_str}: {desc}, "
                        f"temperature {temp} degrees Celsius."
                    )

            elif response.status_code == 401:
                self.jarvis.speak("The weather API key is invalid. Please check your API key.")
                print(f"Debug: API Error - {data.get('message', 'Unknown error')}")
            elif response.status_code == 429:
                self.jarvis.speak("Weather API rate limit exceeded. Please try again in a few minutes.")
            elif response.status_code == 404:
                self.jarvis.speak(f"I couldn't find forecast data for {location}. Please check the city name.")
            else:
                error_msg = data.get('message', 'Unknown error')
                print(f"Debug: Forecast API Error {response.status_code} - {error_msg}")
                self.jarvis.speak(f"I'm having trouble fetching the forecast data. Error: {response.status_code}")

        except requests.exceptions.RequestException:
            self.jarvis.speak("I'm unable to connect to the weather service. Please check your internet connection.")
        except Exception as e:
            self.jarvis.speak("An error occurred while fetching forecast data.")

    def test_api_key(self):
        """Test if the API key is working"""
        try:
            url = f"{self.base_url}/weather"
            params = {'q': 'London', 'appid': self.api_key}
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                print("Debug: API key is working correctly!")
                return True
            else:
                data = response.json()
                print(f"Debug: API Test Failed - Status {response.status_code}: {data.get('message', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"Debug: API Test Exception - {e}")
            return False

    def process_weather_command(self, command):
        """Process weather-related commands"""
        if 'forecast' in command or 'tomorrow' in command:
            self.get_forecast(command)
        else:
            self.get_current_weather(command)
