import unittest
from pathlib import Path
from typing import Dict, Any

from config.settings import (
    is_cloud_api_enabled,
    set_cloud_api_enabled,
    INTENT_MODEL_PATH,
    INTENT_VOCAB_PATH,
)
from core.intent_classifier import IntentClassifier, IntentResult
from core.llm_router import LLMRouter
from core.engine import JARVISEngine


class TestIntentClassification(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.classifier = IntentClassifier()

    def test_classifier_initialization(self) -> None:
        self.assertIsNotNone(self.classifier)
        self.assertGreaterEqual(len(self.classifier.intents), 15)

    def test_music_play_intent_and_slots(self) -> None:
        res: IntentResult = self.classifier.classify("play bohemian rhapsody on spotify")
        self.assertEqual(res.intent, "music.play")
        self.assertGreaterEqual(res.confidence, 0.65)
        self.assertIn("bohemian rhapsody", res.slots.get("song", "").lower())
        self.assertEqual(res.slots.get("platform"), "spotify")

    def test_music_control_intent(self) -> None:
        res: IntentResult = self.classifier.classify("pause the music please")
        self.assertEqual(res.intent, "music.control")
        self.assertGreaterEqual(res.confidence, 0.65)
        self.assertEqual(res.slots.get("action"), "pause")

    def test_alarm_set_intent_and_slots(self) -> None:
        res: IntentResult = self.classifier.classify("set an alarm for 7:30 am")
        self.assertEqual(res.intent, "alarm.set")
        self.assertGreaterEqual(res.confidence, 0.65)
        self.assertIn("7:30", res.slots.get("time", ""))

    def test_alarm_cancel_intent(self) -> None:
        res: IntentResult = self.classifier.classify("cancel all alarms")
        self.assertEqual(res.intent, "alarm.cancel")
        self.assertGreaterEqual(res.confidence, 0.65)
        self.assertTrue(res.slots.get("all", False))

    def test_system_volume_intent_and_slots(self) -> None:
        res: IntentResult = self.classifier.classify("set volume to 80%")
        self.assertEqual(res.intent, "system.volume")
        self.assertGreaterEqual(res.confidence, 0.65)
        self.assertEqual(res.slots.get("level"), 80)
        self.assertEqual(res.slots.get("action"), "set")

    def test_system_brightness_intent(self) -> None:
        res: IntentResult = self.classifier.classify("dim the screen brightness")
        self.assertEqual(res.intent, "system.brightness")
        self.assertGreaterEqual(res.confidence, 0.65)
        self.assertEqual(res.slots.get("action"), "down")

    def test_system_status_intent(self) -> None:
        res: IntentResult = self.classifier.classify("check system status and cpu usage")
        self.assertEqual(res.intent, "system.status")
        self.assertGreaterEqual(res.confidence, 0.65)

    def test_app_open_intent_and_slots(self) -> None:
        res: IntentResult = self.classifier.classify("open visual studio code")
        self.assertEqual(res.intent, "app.open")
        self.assertGreaterEqual(res.confidence, 0.65)
        self.assertIn("visual studio code", res.slots.get("app_name", "").lower())

    def test_meeting_join_intent_and_slots(self) -> None:
        url = "https://meet.google.com/abc-defg-hij"
        res: IntentResult = self.classifier.classify(f"join meeting {url}")
        self.assertEqual(res.intent, "meeting.join")
        self.assertGreaterEqual(res.confidence, 0.65)
        self.assertEqual(res.slots.get("url"), url)

    def test_web_search_intent_and_slots(self) -> None:
        res: IntentResult = self.classifier.classify("search the web for quantum computing advances")
        self.assertEqual(res.intent, "web.search")
        self.assertGreaterEqual(res.confidence, 0.65)
        self.assertIn("quantum computing", res.slots.get("query", "").lower())

    def test_date_time_intent(self) -> None:
        res: IntentResult = self.classifier.classify("what time is it right now")
        self.assertEqual(res.intent, "date_time.get")
        self.assertGreaterEqual(res.confidence, 0.65)
        self.assertEqual(res.slots.get("type"), "time")

    def test_intent_result_dict_interface(self) -> None:
        res: IntentResult = self.classifier.classify("open calculator")
        self.assertEqual(res["intent"], "app.open")
        self.assertEqual(res.get("intent"), "app.open")
        d: Dict[str, Any] = res.to_dict()
        self.assertEqual(d["intent"], "app.open")
        self.assertIn("slots", d)


class TestCloudApiToggle(unittest.TestCase):
    def test_toggle_state(self) -> None:
        original = is_cloud_api_enabled()
        try:
            set_cloud_api_enabled(False)
            self.assertFalse(is_cloud_api_enabled())

            router = LLMRouter()
            chain = router._build_candidate_chain("chat")
            # Verify no standard cloud provider in candidate chain
            cloud_provs = {"groq", "gemini", "anthropic", "openai", "openrouter", "deepseek"}
            for c in chain:
                self.assertNotIn(c["provider"], cloud_provs)

            set_cloud_api_enabled(True)
            self.assertTrue(is_cloud_api_enabled())
        finally:
            set_cloud_api_enabled(original)


class TestEngineIntegration(unittest.TestCase):
    def test_engine_routes_via_intent_classifier(self) -> None:
        engine = JARVISEngine()
        self.assertIsNotNone(engine.intent_classifier)
        resp = engine.process_command("what time is it", source="unit_test")
        self.assertEqual(resp["action"], "get_time")
        self.assertEqual(resp["tier"], "LOCAL_NN")


if __name__ == "__main__":
    unittest.main()

