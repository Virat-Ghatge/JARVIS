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
            'vscode': 'code.exe',
            'command prompt': 'cmd.exe',
            'terminal': 'cmd.exe',
            'explorer': 'explorer.exe',
            'settings': 'ms-settings:',
            'paint': 'mspaint.exe',
            'task manager': 'taskmgr.exe',
        }

    def open_application(self, command):
        """Open applications based on command"""
        app_name = None
        for app in self.app_mapping:
            if app in command:
                app_name = app
                break

        if app_name:
            try:
                if app_name == 'settings':
                    os.system(f'start {self.app_mapping[app_name]}')
                else:
                    subprocess.Popen(self.app_mapping[app_name])
                self.jarvis.speak(f"Opening {app_name}")
            except Exception as e:
                self.jarvis.speak(f"I'm unable to open {app_name}")
        else:
            self.jarvis.speak("I'm not sure which application you want me to open. Could you be more specific?")
