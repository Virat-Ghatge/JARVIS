#!/usr/bin/env python3
"""
Test script to verify OpenWeatherMap API key is working
"""

import requests

API_KEY = "7bac7ec1ce4f6c70f158623f12251665"
BASE_URL = "https://api.openweathermap.org/data/2.5"

def test_api():
    """Test the API key"""
    print("Testing OpenWeatherMap API key...")
    print(f"API Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    print("-" * 50)

    try:
        url = f"{BASE_URL}/weather"
        params = {
            'q': 'London',
            'appid': API_KEY,
            'units': 'metric'
        }

        print(f"\nRequesting: {url}")
        print(f"Parameters: {params}")

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {data}")

        if response.status_code == 200:
            print("\n✓ API key is working!")
            print(f"City: {data['name']}")
            print(f"Temperature: {data['main']['temp']}°C")
            print(f"Weather: {data['weather'][0]['description']}")
        elif response.status_code == 401:
            print("\n✗ API key is invalid or not activated yet.")
            print(f"Error: {data.get('message', 'Unknown error')}")
            print("\nIf you just created the key, wait 10-15 minutes for activation.")
        elif response.status_code == 429:
            print("\n✗ Rate limit exceeded. Free tier allows 60 calls/minute.")
        else:
            print(f"\n✗ Error: {data.get('message', 'Unknown error')}")

    except requests.exceptions.RequestException as e:
        print(f"\n✗ Network error: {e}")
        print("Please check your internet connection.")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")

if __name__ == "__main__":
    test_api()
