#!/usr/bin/env python3
"""
Test Suite for Loop 2: Audio State Machine, Meeting Interlock & Unified Input Gateway
"""

import unittest
from unittest.mock import MagicMock, patch
from audio.tts_engine import TTSEngine
from audio.voice_listener import VoiceListener
from core.engine import JARVISEngine


class TestLoop2AudioEngine(unittest.TestCase):
    def setUp(self):
        # Create isolated instances
        self.tts = TTSEngine(tts_active=True)
        self.listener = VoiceListener()
        # Keep listener inactive for test isolation
        self.listener.set_mic_active(False)
        # Use silent TTS for engine so process_command tests do not queue real speech
        self.silent_tts = TTSEngine(tts_active=False)
        self.engine = JARVISEngine(tts=self.silent_tts, listener=self.listener)

    def tearDown(self):
        self.tts.stop()
        self.silent_tts.stop()
        self.listener.stop()

    def test_tts_toggle_independent(self):
        self.assertTrue(self.tts.get_tts_active())
        self.tts.set_tts_active(False)
        self.assertFalse(self.tts.get_tts_active())

        # Calling speak while inactive does not crash and returns immediately
        self.tts.speak("This is silent test speech", wait=False)
        self.assertFalse(self.tts.is_speaking())

        # Toggle back to active
        new_state = self.tts.toggle_tts()
        self.assertTrue(new_state)
        self.assertTrue(self.tts.get_tts_active())

    def test_mic_toggle_independent(self):
        self.assertFalse(self.listener.get_mic_active())
        self.listener.set_mic_active(True)
        self.assertTrue(self.listener.get_mic_active())

        new_state = self.listener.toggle_mic()
        self.assertFalse(new_state)
        self.assertFalse(self.listener.get_mic_active())

    def test_meeting_auto_mute_and_manual_override(self):
        # 1. Start with mic active
        self.listener.set_mic_active(True)
        self.assertTrue(self.listener.get_mic_active())

        # 2. Join meeting -> auto-mutes
        self.listener.on_meeting_state_change(True, "Sprint Planning")
        self.assertFalse(self.listener.get_mic_active())
        self.assertTrue(self.listener.meeting_auto_muted)

        # 3. User manually overrides unmute in meeting
        self.listener.set_mic_active(True)
        self.assertTrue(self.listener.get_mic_active())
        self.assertTrue(self.listener.manual_override)

        # 4. Leave meeting -> retains manual state
        self.listener.on_meeting_state_change(False, "Sprint Planning")
        self.assertTrue(self.listener.get_mic_active())

    def test_meeting_auto_restore(self):
        # 1. Start with mic active
        self.listener.set_mic_active(True)
        self.assertTrue(self.listener.get_mic_active())

        # 2. Join meeting -> auto-mutes
        self.listener.on_meeting_state_change(True, "Board Review")
        self.assertFalse(self.listener.get_mic_active())
        self.assertTrue(self.listener.meeting_auto_muted)

        # 3. Leave meeting without manual override -> auto-restores
        self.listener.on_meeting_state_change(False, "Board Review")
        self.assertTrue(self.listener.get_mic_active())

    def test_engine_process_command_time(self):
        res = self.engine.process_command("What time is it?", source="text")
        self.assertEqual(res["sender"], "jarvis")
        self.assertEqual(res["source"], "text")
        self.assertEqual(res["action"], "get_time")
        self.assertIn("time", res["text"].lower())

    def test_engine_process_command_system_status(self):
        res = self.engine.process_command("check system status", source="text")
        self.assertEqual(res["sender"], "jarvis")
        self.assertEqual(res["action"], "system_info")
        self.assertIn("systems nominal", res["text"].lower())
        self.assertIn("cpu", res["data"])
        self.assertIn("ram", res["data"])

    def test_engine_skill_macro_trigger(self):
        with patch.object(self.engine.app_handler, "open_application"):
            res = self.engine.process_command("start work mode", source="text")
            self.assertEqual(res["sender"], "jarvis")
            self.assertEqual(res["action"], "skill_macro")
            self.assertIn("Start Work Mode", res["text"])

    def test_chat_listener_broadcast(self):
        broadcasted = []

        def on_msg(evt):
            broadcasted.append(evt)

        self.engine.register_chat_listener(on_msg)
        self.engine.process_command("what day is it today", source="voice")

        # Must have broadcasted user input and jarvis response
        self.assertGreaterEqual(len(broadcasted), 2)
        user_evt = broadcasted[0]
        jarvis_evt = broadcasted[1]

        self.assertEqual(user_evt["sender"], "user")
        self.assertEqual(user_evt["source"], "voice")
        self.assertEqual(jarvis_evt["sender"], "jarvis")
        self.assertEqual(jarvis_evt["action"], "get_date")


if __name__ == "__main__":
    unittest.main()
