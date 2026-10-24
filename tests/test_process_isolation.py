import unittest
from config.settings import is_local_endpoint_url, is_internet_connected
from agent_os.os_actuator import OSActuator
from audio.voice_listener import VoiceListener


class TestJarvisProcessIsolation(unittest.TestCase):
    def test_local_endpoint_detection(self):
        self.assertTrue(is_local_endpoint_url("http://127.0.0.1:8000/v1"))
        self.assertTrue(is_local_endpoint_url("http://localhost:11434/v1"))
        self.assertFalse(is_local_endpoint_url("https://api.openai.com/v1"))

    def test_actuator_does_not_hook_on_import_or_init(self):
        actuator = OSActuator()
        self.assertIsNone(actuator._listener)
        actuator.start_esc_guard()
        actuator.stop_esc_guard()
        self.assertIsNone(actuator._listener)

    def test_meeting_auto_mute_and_manual_override(self):
        vl = VoiceListener()
        vl.set_mic_active(True)
        self.assertTrue(vl.get_state()["mic_active"])

        # Auto-mute when meeting starts
        vl.enter_meeting_auto_mute()
        self.assertFalse(vl.get_state()["mic_active"])
        self.assertTrue(vl.get_state()["in_meeting_auto_muted"])

        # User can manually unmute during meeting
        vl.set_mic_active(True, manual_override=True)
        self.assertTrue(vl.get_state()["mic_active"])
        self.assertFalse(vl.get_state()["in_meeting_auto_muted"])
        vl.shutdown()

    def test_non_blocking_connectivity_check(self):
        res = is_internet_connected(role="chat")
        self.assertIsInstance(res, bool)


if __name__ == "__main__":
    unittest.main()
