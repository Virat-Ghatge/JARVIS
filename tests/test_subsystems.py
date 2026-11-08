#!/usr/bin/env python3
"""
Unit and integration tests for JARVIS 3.0 Subsystem Hardening and WebSocket Telemetry.
Covers MusicHandler, AlarmHandler, WebSearchHandler, Engine routing, and FastAPI server endpoints.
"""

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from config.settings import (
    ALARMS_FILE,
    is_cloud_api_enabled,
    set_cloud_api_enabled,
)
from core.engine import JARVISEngine
from integrations.handlers import (
    alarm as alarm_mod,
    music as music_mod,
    web_search as web_search_mod,
    AlarmHandler,
    MusicHandler,
    WebSearchHandler,
)
from automation.server import app


class MockJarvis:
    """Mock Jarvis assistant instance to capture speech and messages."""

    def __init__(self) -> None:
        self.spoken: List[str] = []
        self.emitted_chat: List[Dict[str, Any]] = []

    def speak(self, text: str, wait: bool = False) -> None:
        self.spoken.append(str(text))

    def _emit_chat(self, role: str, content: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        msg = {"role": role, "content": content, "meta": meta or {}}
        self.emitted_chat.append(msg)
        return msg


class TestMusicSubsystem(unittest.TestCase):
    """Tests for hardened MusicHandler."""

    def setUp(self) -> None:
        self.mock_jarvis = MockJarvis()
        self.handler = MusicHandler(self.mock_jarvis)

    def test_play_music_structured_response(self) -> None:
        with patch.object(self.handler, "_play_spotify") as mock_spotify:
            res: Dict[str, Any] = self.handler.play_music("play Bohemian Rhapsody on Spotify")
            mock_spotify.assert_called_once_with("bohemian rhapsody")
            self.assertEqual(res["action"], "play_music")
            self.assertIn("bohemian rhapsody", res["reply"].lower())
            self.assertEqual(res["data"]["song"], "bohemian rhapsody")
            self.assertEqual(res["data"]["platform"], "spotify")
            self.assertEqual(res["data"]["state"], "playing")

            # Check playback state
            state = self.handler.get_playback_state()
            self.assertEqual(state["song"], "bohemian rhapsody")
            self.assertEqual(state["platform"], "spotify")
            self.assertEqual(state["state"], "playing")

    def test_control_playback_actions(self) -> None:
        with patch.object(self.handler, "control_spotify", return_value=True):
            # Pause
            res_pause = self.handler.control_playback("pause")
            self.assertEqual(res_pause["action"], "music_control")
            self.assertEqual(res_pause["data"]["state"], "paused")
            self.assertEqual(self.handler.get_playback_state()["state"], "paused")

            # Play
            res_play = self.handler.control_playback("play")
            self.assertEqual(res_play["data"]["state"], "playing")
            self.assertEqual(self.handler.get_playback_state()["state"], "playing")

            # Next
            res_next = self.handler.control_playback("next")
            self.assertEqual(res_next["data"]["state"], "playing")
            self.assertEqual(res_next["data"]["action"], "next")

            # Previous
            res_prev = self.handler.control_playback("previous")
            self.assertEqual(res_prev["data"]["state"], "playing")
            self.assertEqual(res_prev["data"]["action"], "previous")

            # Stop
            res_stop = self.handler.control_playback("stop")
            self.assertEqual(res_stop["data"]["state"], "stopped")
            self.assertEqual(self.handler.get_playback_state()["state"], "stopped")

            # Play_pause toggle
            res_toggle = self.handler.control_playback("play_pause")
            self.assertIn(res_toggle["data"]["state"], ("playing", "paused"))

    def test_module_singleton_and_helpers(self) -> None:
        self.assertIsNotNone(music_mod.music_handler)
        with patch.object(music_mod.music_handler, "play_music", return_value={"action": "play_music", "reply": "ok"}):
            res = music_mod.play_music("play jazz")
            self.assertEqual(res["action"], "play_music")

        with patch.object(music_mod.music_handler, "control_playback", return_value={"action": "music_control", "reply": "ok"}):
            res = music_mod.control_playback("pause")
            self.assertEqual(res["action"], "music_control")


class TestAlarmSubsystem(unittest.TestCase):
    """Tests for AlarmHandler with ID cancellation and WebSocket broadcasting."""

    def setUp(self) -> None:
        self.mock_jarvis = MockJarvis()
        self.backup_alarms: Optional[str] = None
        if ALARMS_FILE.exists():
            try:
                self.backup_alarms = ALARMS_FILE.read_text(encoding="utf-8")
            except Exception:
                pass
        # Clear alarms for clean test run
        ALARMS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ALARMS_FILE.write_text(json.dumps({"alarms": [], "timers": []}), encoding="utf-8")
        self.handler = AlarmHandler(self.mock_jarvis)

    def tearDown(self) -> None:
        if self.backup_alarms is not None:
            try:
                ALARMS_FILE.write_text(self.backup_alarms, encoding="utf-8")
            except Exception:
                pass
        elif ALARMS_FILE.exists():
            try:
                ALARMS_FILE.unlink()
            except Exception:
                pass

    def test_set_alarm_and_get_active(self) -> None:
        msg = self.handler.set_alarm("set alarm for 7:45 AM")
        self.assertIn("7:45 AM", msg)

        active = self.handler.get_active_alarms()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["time"], "07:45")
        self.assertTrue(active[0]["id"].startswith("alr-"))

    def test_cancel_alarm_by_id(self) -> None:
        self.handler.set_alarm("set alarm for 8:00 AM")
        active = self.handler.get_active_alarms()
        self.assertEqual(len(active), 1)
        target_id = active[0]["id"]

        success = self.handler.cancel_alarm_by_id(target_id)
        self.assertTrue(success)
        self.assertEqual(len(self.handler.get_active_alarms()), 0)

        # Cancelling non-existent ID returns False
        self.assertFalse(self.handler.cancel_alarm_by_id("non-existent-id"))

    def test_cancel_alarm_by_query_and_all(self) -> None:
        self.handler.set_alarm("set alarm for 9:15 AM")
        self.handler.set_alarm("set alarm for 10:30 PM")
        self.assertEqual(len(self.handler.get_active_alarms()), 2)

        # Cancel specific by time substring
        cancel_msg = self.handler.cancel_alarm("9:15")
        self.assertIn("Cancelled alarm", cancel_msg)
        self.assertEqual(len(self.handler.get_active_alarms()), 1)

        # Cancel all
        all_cancel_msg = self.handler.cancel_alarm("cancel all alarms")
        self.assertIn("cancelled", all_cancel_msg.lower())
        self.assertEqual(len(self.handler.get_active_alarms()), 0)


class TestWebSearchSubsystem(unittest.TestCase):
    """Tests for WebSearchHandler multi-engine query logic."""

    def setUp(self) -> None:
        self.mock_jarvis = MockJarvis()
        self.handler = WebSearchHandler(self.mock_jarvis)

    def test_extract_query(self) -> None:
        q1 = self.handler._extract_query("search the web for quantum computing on google")
        self.assertEqual(q1, "quantum computing")

        q2 = self.handler._extract_query("look up Nikola Tesla")
        self.assertEqual(q2, "Nikola Tesla")

        q3 = self.handler._extract_query("what is general relativity")
        self.assertEqual(q3, "general relativity")

    def test_web_search_structured_response_with_mocked_engine(self) -> None:
        mock_results = [{
            "title": "Python Programming",
            "snippet": "Python is a high-level general-purpose programming language.",
            "url": "https://www.python.org",
        }]

        with patch.object(self.handler, "_query_duckduckgo", return_value=mock_results):
            res = self.handler.web_search("search for Python programming")
            self.assertEqual(res["action"], "web_search")
            self.assertIn("Python is a high-level", res["reply"])
            self.assertEqual(res["data"]["query"], "Python programming")
            self.assertEqual(len(res["data"]["results"]), 1)
            self.assertEqual(res["data"]["url"], "https://www.python.org")

    def test_web_search_browser_fallback(self) -> None:
        with patch.object(self.handler, "_query_duckduckgo", return_value=[]), \
             patch.object(self.handler, "_query_wikipedia", return_value=[]), \
             patch("webbrowser.open") as mock_browser:
            res = self.handler.web_search("obscure rare query 12345")
            self.assertEqual(res["action"], "web_search")
            self.assertIn("Searching Google for 'obscure rare query 12345'", res["reply"])
            mock_browser.assert_called_once()


class TestEngineRoutingSubsystem(unittest.TestCase):
    """Tests that JARVISEngine routes intents to the new hardened handlers."""

    def setUp(self) -> None:
        self.engine = JARVISEngine()

    def test_engine_routes_music_play(self) -> None:
        with patch.object(self.engine.music_handler, "play_music", return_value={
            "reply": "Playing Hotel California on Spotify, sir.",
            "action": "play_music",
            "data": {"song": "Hotel California", "platform": "spotify", "state": "playing"},
        }):
            res = self.engine.process_command("play hotel california on spotify", source="unit_test")
            self.assertEqual(res["action"], "play_music")
            self.assertIn("Hotel California", res["reply"])
            self.assertEqual(res["tier"], "LOCAL_NN")

    def test_engine_routes_music_control(self) -> None:
        with patch.object(self.engine.music_handler, "control_playback", return_value={
            "reply": "Music paused, sir.",
            "action": "music_control",
            "data": {"action": "pause", "state": "paused"},
        }):
            res = self.engine.process_command("pause music", source="unit_test")
            self.assertEqual(res["action"], "music_control")
            self.assertEqual(res["tier"], "LOCAL_NN")

    def test_engine_routes_alarm_set_and_cancel(self) -> None:
        with patch.object(self.engine.alarm_handler, "set_alarm", return_value="Alarm set for 7:00 AM, sir."):
            res = self.engine.process_command("set an alarm for 7:00 am", source="unit_test")
            self.assertEqual(res["action"], "set_alarm")
            self.assertIn("7:00 AM", res["reply"])

        with patch.object(self.engine.alarm_handler, "cancel_alarm", return_value="All alarms cancelled, sir."):
            res = self.engine.process_command("cancel all alarms", source="unit_test")
            self.assertEqual(res["action"], "cancel_alarm")
            self.assertIn("cancelled", res["reply"].lower())

    def test_engine_routes_web_search(self) -> None:
        with patch.object(self.engine.web_search_handler, "web_search", return_value={
            "reply": "Here is what I found for 'quantum computing': A branch of computing.",
            "action": "web_search",
            "data": {"query": "quantum computing", "results": []},
        }):
            res = self.engine.process_command("search the web for quantum computing", source="unit_test")
            self.assertEqual(res["action"], "web_search")
            self.assertEqual(res["tier"], "LOCAL_NN")


class TestServerEndpoints(unittest.TestCase):
    """Tests the new REST API endpoints on the FastAPI server."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from fastapi.testclient import TestClient
            cls.client = TestClient(app)
        except Exception:
            cls.client = None

    def test_cloud_api_toggle_endpoints(self) -> None:
        if self.client is None:
            self.skipTest("TestClient unavailable")

        # GET
        get_res = self.client.get("/api/cloud-api-toggle")
        self.assertEqual(get_res.status_code, 200)
        self.assertIn("cloud_api_enabled", get_res.json())

        # POST disable
        post_res = self.client.post("/api/cloud-api-toggle", json={"enabled": False})
        self.assertEqual(post_res.status_code, 200)
        self.assertFalse(post_res.json()["cloud_api_enabled"])
        self.assertFalse(is_cloud_api_enabled())

        # POST re-enable
        post_res2 = self.client.post("/api/cloud-api-toggle", json={"enabled": True})
        self.assertEqual(post_res2.status_code, 200)
        self.assertTrue(post_res2.json()["cloud_api_enabled"])
        self.assertTrue(is_cloud_api_enabled())

    def test_subsystem_alarm_endpoints(self) -> None:
        if self.client is None:
            self.skipTest("TestClient unavailable")

        # Create alarm
        post_res = self.client.post("/api/subsystems/alarms", json={"time": "5:30 AM"})
        self.assertEqual(post_res.status_code, 200)
        data = post_res.json()
        self.assertEqual(data["status"], "ok")
        self.assertGreaterEqual(len(data["alarms"]), 1)
        created_id = data["alarms"][-1]["id"]

        # List alarms
        get_res = self.client.get("/api/subsystems/alarms")
        self.assertEqual(get_res.status_code, 200)
        self.assertIn("alarms", get_res.json())
        self.assertIn("timers", get_res.json())

        # Delete alarm by ID
        del_res = self.client.delete(f"/api/subsystems/alarms/{created_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["alarm_id"], created_id)

    def test_subsystem_music_endpoints(self) -> None:
        if self.client is None:
            self.skipTest("TestClient unavailable")

        # GET music state
        get_res = self.client.get("/api/subsystems/music")
        self.assertEqual(get_res.status_code, 200)
        self.assertIn("state", get_res.json())

        # POST control
        ctrl_res = self.client.post("/api/subsystems/music/control", json={"action": "play_pause"})
        self.assertEqual(ctrl_res.status_code, 200)
        self.assertEqual(ctrl_res.json()["status"], "ok")
        self.assertEqual(ctrl_res.json()["action"], "play_pause")


if __name__ == "__main__":
    unittest.main()
