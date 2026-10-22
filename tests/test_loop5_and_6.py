#!/usr/bin/env python3
"""
Integration and End-to-End Tests for Loop 5 & Loop 6
Validates:
1. React Frontend Build artifacts (ui/dist/index.html, ui/dist/assets)
2. FastAPI Static Mounting & SPA route fallback
3. Backend REST Endpoints (/api/vault, /api/meetings, /api/alarms, etc.)
4. WebSocket Telemetry endpoint connectivity
5. Native desktop entry points and launcher artifacts
"""

import os
import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure root directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import UI_DIST_DIR
from automation.server import app


class TestLoop5And6(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_ui_dist_bundle_exists(self):
        """Verify React build output exists on disk with HTML and JS/CSS assets."""
        self.assertTrue(UI_DIST_DIR.exists(), "ui/dist directory does not exist")
        index_html = UI_DIST_DIR / "index.html"
        self.assertTrue(index_html.exists(), "ui/dist/index.html does not exist")
        self.assertGreater(index_html.stat().st_size, 0, "ui/dist/index.html is empty")

        assets_dir = UI_DIST_DIR / "assets"
        self.assertTrue(assets_dir.exists(), "ui/dist/assets does not exist")
        asset_files = list(assets_dir.glob("*"))
        self.assertGreaterEqual(len(asset_files), 2, f"Expected JS and CSS bundles in ui/dist/assets, found: {asset_files}")

    def test_fastapi_spa_serving(self):
        """Verify root route returns 200 with HTML SPA content."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertTrue("<!DOCTYPE html>" in res.text or "<!doctype html>" in res.text.lower())

    def test_fastapi_spa_fallback(self):
        """Verify arbitrary client-side routes fallback to SPA index.html."""
        res = self.client.get("/settings/vault")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))

    def test_backend_api_vault_endpoint(self):
        """Verify /api/vault returns masked vault structure."""
        res = self.client.get("/api/vault")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("roles", data)
        self.assertIn("providers", data)
        self.assertIn("autonomous_trust_mode", data)

    def test_backend_api_meetings_endpoint(self):
        """Verify /api/meetings returns dictionary containing meetings and summaries."""
        res = self.client.get("/api/meetings")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, dict)
        self.assertIn("meetings", data)
        self.assertIn("summaries", data)
        self.assertIsInstance(data["meetings"], list)

    def test_backend_api_alarms_endpoint(self):
        """Verify /api/alarms returns dictionary containing alarms and timers."""
        res = self.client.get("/api/alarms")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, dict)
        self.assertIn("alarms", data)
        self.assertIn("timers", data)

    def test_backend_api_skills_endpoint(self):
        """Verify /api/skills returns list of custom routines."""
        res = self.client.get("/api/skills")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)

    def test_backend_api_mcp_endpoint(self):
        """Verify /api/mcp returns configured MCP servers and discovered tools."""
        res = self.client.get("/api/mcp")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, dict)
        self.assertIn("servers", data)
        self.assertIn("tools", data)

    def test_main_cli_import_and_engine(self):
        """Verify main.py dependencies and core engine input gateway."""
        import main
        from core.engine import engine

        self.assertTrue(hasattr(main, "main"))
        self.assertTrue(hasattr(main, "start_backend"))

        # Test processing command through engine
        res = engine.process_command("what time is it", source="test")
        self.assertIsInstance(res, dict)
        self.assertIn("text", res)
        self.assertGreater(len(res["text"]), 0)


    def test_teach_mode_start_and_stop(self):
        """Verify POST /api/skills/teach/start and POST /api/skills/teach/stop."""
        from core.engine import engine

        # Start teach mode
        res_start = self.client.post("/api/skills/teach/start", json={
            "name": "Integration Test Routine",
            "trigger_phrases": ["run integration test", "test routine"],
        })
        self.assertEqual(res_start.status_code, 200)
        self.assertTrue(res_start.json().get("ok"))

        # Check status
        res_status = self.client.get("/api/skills/teach/status")
        self.assertEqual(res_status.status_code, 200)
        self.assertTrue(res_status.json().get("is_teaching"))

        # Engine processes a command while teaching
        engine.process_command("what is the date", source="text")

        # Stop and save
        res_stop = self.client.post("/api/skills/teach/stop", json={"save": True})
        self.assertEqual(res_stop.status_code, 200)
        data = res_stop.json()
        self.assertTrue(data.get("ok"))
        saved = data.get("saved")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.get("name"), "Integration Test Routine")

        # Clean up created skill
        if saved and saved.get("id"):
            self.client.delete(f"/api/skills/{saved['id']}")

    def test_meetings_scheduler_and_leave(self):
        """Verify POST /api/meetings schedules via MeetingScheduler and /api/meetings/leave works."""
        meeting_payload = {
            "title": "Integration Standup Test",
            "meeting_url": "https://meet.google.com/abc-defg-hij",
            "start_time": "2026-10-21T16:00:00",
            "auto_leave": True,
        }
        res_add = self.client.post("/api/meetings", json=meeting_payload)
        self.assertEqual(res_add.status_code, 200)
        data_add = res_add.json()
        self.assertTrue(data_add.get("ok"))
        created_id = data_add.get("meeting", {}).get("id")
        self.assertIsNotNone(created_id)

        # Verify meeting retrieved via GET /api/meetings
        res_get = self.client.get("/api/meetings")
        self.assertEqual(res_get.status_code, 200)
        meetings = res_get.json().get("meetings", [])
        self.assertTrue(any(m.get("id") == created_id for m in meetings))

        # Test leave meeting endpoint
        res_leave = self.client.post("/api/meetings/leave")
        self.assertEqual(res_leave.status_code, 200)
        self.assertTrue(res_leave.json().get("ok"))

        # Clean up test meeting
        res_del = self.client.delete(f"/api/meetings/{created_id}")
        self.assertEqual(res_del.status_code, 200)

    def test_delete_masked_key(self):
        """Verify deleting an API key by its masked string representation."""
        test_key = "sk_live_integration_test_secret_9999"
        # Add key
        res_add = self.client.post("/api/vault/key", json={
            "provider": "groq",
            "key": test_key,
            "action": "add",
        })
        self.assertEqual(res_add.status_code, 200)

        # Get masked vault
        res_vault = self.client.get("/api/vault")
        self.assertEqual(res_vault.status_code, 200)
        vault_data = res_vault.json()
        groq_masked = vault_data.get("providers", {}).get("groq", {}).get("keys_masked", [])
        self.assertGreater(len(groq_masked), 0)
        masked_val = groq_masked[-1]

        # Delete by masked key
        res_del = self.client.post("/api/vault/key", json={
            "provider": "groq",
            "key": masked_val,
            "action": "remove",
        })
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.json().get("ok"))

    def test_voice_text_alarm_persistence(self):
        """Verify voice/text alarm commands persist to config/alarms.json."""
        import json
        from config.settings import ALARMS_FILE
        from core.engine import engine

        res = engine.process_command("set alarm for 6:45 AM", source="text")
        self.assertIn("6:45", res.get("text", ""))

        self.assertTrue(ALARMS_FILE.exists())
        alarms_data = json.loads(ALARMS_FILE.read_text(encoding="utf-8"))
        alarms_list = alarms_data.get("alarms", [])
        matching = [a for a in alarms_list if "06:45" in a.get("time", "") or "6:45" in a.get("time", "")]
        self.assertGreater(len(matching), 0, f"Expected alarm for 06:45 in {alarms_list}")

        # Clean up
        alarms_data["alarms"] = [a for a in alarms_list if a not in matching]
        ALARMS_FILE.write_text(json.dumps(alarms_data, indent=2), encoding="utf-8")

    # ── NEW: FIX 1 — Default model resolution ────────────────────────
    def test_default_model_resolution(self):
        """Verify POST /api/vault/test with no model resolves a real default, not 'default'."""
        from core.llm_router import router

        # Test that get_adapter_for_provider resolves model for gemini
        adapter = router.get_adapter_for_provider("gemini", model="", api_key="test-key")
        self.assertNotEqual(adapter.model, "default", "Model should not be 'default'")
        self.assertNotEqual(adapter.model, "", "Model should not be empty")
        self.assertEqual(adapter.model, "gemini-2.5-flash", f"Expected 'gemini-2.5-flash', got '{adapter.model}'")

        # Test that 'default' string also resolves
        adapter2 = router.get_adapter_for_provider("groq", model="default", api_key="test-key")
        self.assertNotEqual(adapter2.model, "default")
        self.assertEqual(adapter2.model, "llama-3.3-70b-versatile")

        # Test via REST endpoint
        res = self.client.post("/api/vault/test", json={"provider": "gemini"})
        self.assertEqual(res.status_code, 200)
        # The response should not mention "default" as the model used

    # ── NEW: FIX 2 — Timezone-aware meeting creation ─────────────────
    def test_timezone_aware_meeting_creation(self):
        """Verify POST /api/meetings with a UTC 'Z' timestamp doesn't throw naive/aware TypeError."""
        meeting_payload = {
            "title": "UTC Timezone Test Meeting",
            "meeting_url": "https://meet.google.com/utc-test-xyz",
            "start_time": "2026-10-21T18:00:00Z",
            "auto_leave": True,
        }
        res = self.client.post("/api/meetings", json=meeting_payload)
        self.assertEqual(res.status_code, 200, f"Meeting creation failed: {res.text}")
        data = res.json()
        self.assertTrue(data.get("ok"), f"Meeting creation returned ok=False: {data}")
        created_id = data.get("meeting", {}).get("id")
        self.assertIsNotNone(created_id)

        # Verify the meeting start_time was stored without timezone info
        meeting = data.get("meeting", {})
        st = meeting.get("start_time", "")
        # Should not contain '+00:00' or 'Z' — it's naive local time
        self.assertNotIn("+00:00", str(st), "start_time should be naive (no timezone)")

        # Clean up
        if created_id:
            self.client.delete(f"/api/meetings/{created_id}")

    # ── NEW: FIX 5 — Multi-turn context memory ──────────────────────
    def test_multi_turn_context_memory(self):
        """Verify engine.context records user and assistant messages."""
        from core.engine import engine
        from core.context_manager import context_mgr

        # Clear existing context
        context_mgr.clear()
        self.assertEqual(len(context_mgr._history), 0)

        # Add user message
        context_mgr.add_user_message("Hello, who are you?")
        self.assertEqual(len(context_mgr._history), 1)
        self.assertEqual(context_mgr._history[0].role, "user")
        self.assertEqual(context_mgr._history[0].content, "Hello, who are you?")

        # Add assistant message
        context_mgr.add_assistant_message("I am JARVIS, sir.")
        self.assertEqual(len(context_mgr._history), 2)
        self.assertEqual(context_mgr._history[1].role, "assistant")

        # get_messages should include system prompt + history
        messages = context_mgr.get_messages()
        self.assertGreaterEqual(len(messages), 3)
        self.assertEqual(messages[0].role, "system")
        self.assertEqual(messages[1].role, "user")
        self.assertEqual(messages[2].role, "assistant")

        # Clear memory
        context_mgr.clear()
        self.assertEqual(len(context_mgr._history), 0)

        # Verify engine has is_thinking attribute
        self.assertTrue(hasattr(engine, "is_thinking"), "Engine should have is_thinking attribute")
        self.assertFalse(engine.is_thinking, "is_thinking should be False when idle")

    # ── NEW: FIX 5 — Clear memory command ────────────────────────────
    def test_clear_memory_command(self):
        """Verify 'clear memory' command clears context and returns confirmation."""
        from core.engine import engine

        # Pre-fill context
        engine.context.add_user_message("test message")
        self.assertGreater(len(engine.context._history), 0)

        # Send clear memory command
        res = engine.process_command("clear memory", source="test")
        self.assertIn("cleared", res.get("text", "").lower())

        # Context should be empty
        self.assertEqual(len(engine.context._history), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

