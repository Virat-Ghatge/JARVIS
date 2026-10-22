#!/usr/bin/env python3
"""
Test Suite for Loop 0: Project Structure & Clean Packaging Verification
"""
import os
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class TestLoop0Structure(unittest.TestCase):
    def test_directories_exist(self):
        expected_dirs = [
            "config",
            "core",
            "core/adapters",
            "audio",
            "agent_os",
            "integrations",
            "integrations/handlers",
            "automation",
            "ui",
            "scripts",
            "tests",
        ]
        for d in expected_dirs:
            p = BASE_DIR / d
            self.assertTrue(p.exists() and p.is_dir(), f"Directory missing: {d}")

    def test_config_files_exist(self):
        expected_files = [
            "config/api_vault.json",
            "config/meetings.json",
            "config/alarms.json",
            "config/skills.json",
            "config/mcp_servers.json",
            "config/settings.py",
        ]
        for f in expected_files:
            p = BASE_DIR / f
            self.assertTrue(p.exists() and p.is_file(), f"File missing: {f}")

    def test_audio_imports(self):
        from audio.tts_engine import TTSEngine
        from audio.voice_listener import VoiceListener
        self.assertIsNotNone(TTSEngine)
        self.assertIsNotNone(VoiceListener)

    def test_integrations_handlers_imports(self):
        from integrations.handlers import (
            DateTimeHandler,
            ApplicationHandler,
            MusicHandler,
            WebSearchHandler,
            AlarmHandler,
            WeatherHandler,
            SystemControls,
            SystemInfoHandler,
            QAHandler,
        )
        self.assertIsNotNone(DateTimeHandler)
        self.assertIsNotNone(ApplicationHandler)
        self.assertIsNotNone(MusicHandler)
        self.assertIsNotNone(WebSearchHandler)
        self.assertIsNotNone(AlarmHandler)
        self.assertIsNotNone(WeatherHandler)
        self.assertIsNotNone(SystemControls)
        self.assertIsNotNone(SystemInfoHandler)
        self.assertIsNotNone(QAHandler)

    def test_backward_compatibility_shims(self):
        from core.tts_engine import TTSEngine as CoreTTSEngine
        from core.voice_listener import VoiceListener as CoreVoiceListener
        from audio.tts_engine import TTSEngine as AudioTTSEngine
        from audio.voice_listener import VoiceListener as AudioVoiceListener
        self.assertIs(CoreTTSEngine, AudioTTSEngine)
        self.assertIs(CoreVoiceListener, AudioVoiceListener)

    def test_automation_modules_import(self):
        from automation.meeting_scheduler import MeetingScheduler
        self.assertIsNotNone(MeetingScheduler)


if __name__ == "__main__":
    unittest.main()
