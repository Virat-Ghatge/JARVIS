#!/usr/bin/env python3
"""
Applications Module
Handles opening various applications
"""

import os
import subprocess


class ApplicationHandler:
    """Handles opening applications"""

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.app_mapping = {
            'notepad': 'notepad.exe',
            'calculator': 'calc.exe',
            'chrome': 'chrome.exe',
            'firefox': 'firefox.exe',
            'edge': 'msedge.exe',
            'word': 'winword.exe',
            'excel': 'excel.exe',
            'powerpoint': 'powerpnt.exe',
            'outlook': 'outlook.exe',
            'spotify': 'spotify.exe',
            'vscode': 'code',
            'vs code': 'code',
            'command prompt': 'cmd.exe',
            'terminal': 'cmd.exe',
            'explorer': 'explorer.exe',
            'settings': 'ms-settings:',
            'paint': 'mspaint.exe',
            'task manager': 'taskmgr.exe',
            'whatsapp': 'whatsapp:',
            'antigravity': 'antigravity',
        }

    def open_application(self, command):
        """Open applications or websites based on command"""
        import webbrowser
        cmd = command.lower()

        # 1. Handle YouTube and YouTube searches specifically
        if 'youtube' in cmd:
            query = cmd.replace('open', '').replace('youtube', '').replace('on', '').replace('channel', '').replace("'s", '').strip()
            if query:
                url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
                self.jarvis.speak(f"Opening YouTube search for {query}")
            else:
                url = "https://www.youtube.com"
                self.jarvis.speak("Opening YouTube")
            webbrowser.open(url)
            return

        # 2. Handle common websites
        websites = {
            'google': 'https://www.google.com',
            'gmail': 'https://mail.google.com',
            'facebook': 'https://www.facebook.com',
            'twitter': 'https://www.twitter.com',
            'instagram': 'https://www.instagram.com',
            'reddit': 'https://www.reddit.com',
            'github': 'https://www.github.com',
            'chatgpt': 'https://chatgpt.com',
            'netflix': 'https://www.netflix.com',
        }
        for site, url in websites.items():
            if site in cmd:
                self.jarvis.speak(f"Opening {site}")
                webbrowser.open(url)
                return

        # 3. Handle local applications from predefined mapping
        app_name = None
        for app in self.app_mapping:
            if app in cmd:
                app_name = app
                break

        if app_name:
            try:
                if app_name in ['settings', 'whatsapp']:
                    os.system(f'start {self.app_mapping[app_name]}')
                else:
                    subprocess.Popen(self.app_mapping[app_name], shell=True)
                self.jarvis.speak(f"Opening {app_name}")
            except Exception:
                self.jarvis.speak(f"I'm unable to open {app_name}")
        else:
            # 4. Smart fallback: strip filler words, search Start Menu shortcuts
            filler = ['open', 'launch', 'start', 'run', 'load', 'pull up']
            guessed_name = cmd
            for word in filler:
                guessed_name = guessed_name.replace(word, '').strip()

            if guessed_name:
                shortcut = self._find_in_start_menu(guessed_name)
                if shortcut:
                    self.jarvis.speak(f"Opening {guessed_name}, sir.")
                    os.startfile(shortcut)
                else:
                    # Last resort: try shell (works for PATH/registry-registered apps)
                    self.jarvis.speak(f"Attempting to open {guessed_name}, sir.")
                    result = os.system(f'start {guessed_name}')
                    if result != 0:
                        self.jarvis.speak(f"I couldn't find {guessed_name} on this system, sir.")
            else:
                self.jarvis.speak("I'm not sure which application you want me to open. Could you be more specific?")

    def _find_in_start_menu(self, app_name):
        """Search Windows Start Menu folders for a matching .lnk shortcut.
        Returns the full path to the best matching shortcut, or None if not found.
        """
        start_menu_dirs = [
            os.path.join(
                os.environ.get('PROGRAMDATA', r'C:\ProgramData'),
                'Microsoft', 'Windows', 'Start Menu', 'Programs'
            ),
            os.path.join(
                os.environ.get('APPDATA', ''),
                'Microsoft', 'Windows', 'Start Menu', 'Programs'
            ),
        ]

        best_match = None
        best_score = 0
        app_lower = app_name.lower()

        for directory in start_menu_dirs:
            if not os.path.isdir(directory):
                continue
            for root, _, files in os.walk(directory):
                for filename in files:
                    if not filename.lower().endswith('.lnk'):
                        continue
                    name = filename[:-4].lower()  # strip .lnk extension
                    full_path = os.path.join(root, filename)

                    if name == app_lower:
                        return full_path  # Perfect match — return immediately
                    elif name.startswith(app_lower) and len(name) > best_score:
                        best_match = full_path
                        best_score = len(name)
                    elif app_lower in name and best_score == 0:
                        best_match = full_path

        return best_match
