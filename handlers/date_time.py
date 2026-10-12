#!/usr/bin/env python3
"""
Date and Time Module
Handles time-related functionality
"""

import datetime


class DateTimeHandler:
    """Handles date and time operations"""

    def __init__(self, jarvis):
        self.jarvis = jarvis

    def wish_me(self):
        """Greet based on time of day"""
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            self.jarvis.speak("Good morning, sir.")
        elif 12 <= hour < 17:
            self.jarvis.speak("Good afternoon, sir.")
        elif 17 <= hour < 22:
            self.jarvis.speak("Good evening, sir.")
        else:
            self.jarvis.speak("Good night, sir.")
        self.jarvis.speak("JARVIS at your service. How may I assist you?")

    def tell_time(self):
        """Tell current time"""
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        self.jarvis.speak(f"The current time is {current_time}")

    def tell_date(self):
        """Tell current date"""
        current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
        self.jarvis.speak(f"Today is {current_date}")
