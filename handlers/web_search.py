#!/usr/bin/env python3
"""
Web Search Module
Handles web search functionality
"""

import webbrowser


class WebSearchHandler:
    """Handles web search operations"""

    def __init__(self, jarvis):
        self.jarvis = jarvis

    def web_search(self, command):
        """Perform web search"""
        query = command.replace('search', '').replace('web search', '').replace('google', '').strip()
        if 'for' in query:
            query = query.split('for', 1)[1].strip()

        if query:
            url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            webbrowser.open(url)
            self.jarvis.speak(f"Searching Google for {query}")
        else:
            self.jarvis.speak("What would you like me to search for?")
            follow_up = self.jarvis.listen()
            if follow_up:
                url = f"https://www.google.com/search?q={follow_up.replace(' ', '+')}"
                webbrowser.open(url)
                self.jarvis.speak(f"Searching Google for {follow_up}")
