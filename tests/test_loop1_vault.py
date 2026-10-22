#!/usr/bin/env python3
"""
Test Suite for Loop 1: Multi-Key API Vault, Adapters & Role Router
"""

import json
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from config.settings import (
    add_provider_key,
    get_active_key,
    get_masked_vault,
    get_role_target,
    get_vault,
    load_vault,
    mask_key,
    remove_provider_key,
    rotate_provider_key,
    save_vault,
)
from core.adapters.base import ChatMessage, LLMResponse
from core.adapters.openai_compat import OpenAICompatAdapter, fetch_models
from core.llm_router import LLMRouter


class TestLoop1Vault(unittest.TestCase):
    def setUp(self):
        # Backup vault state
        self.original_vault = get_vault()

    def tearDown(self):
        # Restore original vault
        save_vault(self.original_vault)

    def test_mask_key(self):
        self.assertEqual(mask_key(""), "")
        self.assertEqual(mask_key("short"), "•••••")
        self.assertEqual(mask_key("12345678"), "••••••••")
        long_key = "AIzaSy1234567890abcdef"
        masked = mask_key(long_key)
        self.assertTrue(masked.startswith("AIza"))
        self.assertTrue(masked.endswith("cdef"))
        self.assertIn("•", masked)

    def test_vault_seeding_and_masking(self):
        masked_vault = get_masked_vault()
        self.assertIn("providers", masked_vault)
        self.assertIn("roles", masked_vault)
        gemini_data = masked_vault["providers"].get("gemini", {})
        if gemini_data.get("keys"):
            self.assertIn("keys_masked", gemini_data)
            self.assertEqual(len(gemini_data["keys"]), len(gemini_data["keys_masked"]))

    def test_add_and_remove_provider_key(self):
        test_key = "test-mock-key-12345678"
        added = add_provider_key("groq", test_key)
        self.assertTrue(added)
        vault = get_vault()
        self.assertIn(test_key, vault["providers"]["groq"]["keys"])

        removed = remove_provider_key("groq", test_key)
        self.assertTrue(removed)
        vault_after = get_vault()
        self.assertNotIn(test_key, vault_after["providers"]["groq"]["keys"])

    def test_key_rotation(self):
        # Setup 3 dummy keys for anthropic (unseeded by .env)
        v = get_vault()
        v["providers"]["anthropic"]["keys"] = ["key_alpha", "key_beta", "key_gamma"]
        v["providers"]["anthropic"]["active_index"] = 0
        save_vault(v)

        self.assertEqual(get_active_key("anthropic"), "key_alpha")
        next_k = rotate_provider_key("anthropic")
        self.assertEqual(next_k, "key_beta")
        self.assertEqual(get_active_key("anthropic"), "key_beta")

        next_k = rotate_provider_key("anthropic")
        self.assertEqual(next_k, "key_gamma")

        # Wraps around
        next_k = rotate_provider_key("anthropic")
        self.assertEqual(next_k, "key_alpha")

    def test_custom_openai_endpoint_and_fetch_models(self):
        adapter = OpenAICompatAdapter(
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
            model="qwen2.5:7b",
        )
        self.assertEqual(adapter.base_url, "http://127.0.0.1:11434/v1")
        self.assertEqual(adapter.model, "qwen2.5:7b")

        # Test fetch_models mock
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "data": [{"id": "gpt-4o-mini"}, {"id": "deepseek-chat"}]
            }
            mock_get.return_value = mock_resp

            models = fetch_models("https://api.example.com/v1", "test-key")
            self.assertIn("gpt-4o-mini", models)
            self.assertIn("deepseek-chat", models)

    def test_adapter_connection_signature(self):
        adapter = OpenAICompatAdapter(
            base_url="http://127.0.0.1:9999/v1",
            api_key="mock",
            model="mock-model",
        )
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"choices": [{"message": {"content": "pong"}}]}
            mock_post.return_value = mock_resp

            res = adapter.test_connection()
            self.assertIn("ok", res)
            self.assertIn("latency_ms", res)
            self.assertIn("error", res)
            self.assertTrue(res["ok"])
            self.assertIsNone(res["error"])

    def test_automatic_key_rotation_on_429(self):
        router = LLMRouter()
        v = get_vault()
        v["providers"]["groq"]["keys"] = ["rate_limited_key", "good_key"]
        v["providers"]["groq"]["active_index"] = 0
        save_vault(v)

        call_count = 0

        def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            current_active = get_active_key("groq")
            if current_active == "rate_limited_key":
                return LLMResponse(
                    text="",
                    latency_ms=45,
                    provider="groq",
                    model="llama-3.3-70b-versatile",
                    error="429 Rate limit exceeded. Try again later.",
                )
            else:
                return LLMResponse(
                    text="Success from good key",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                    latency_ms=60,
                    provider="groq",
                    model="llama-3.3-70b-versatile",
                )

        with patch.object(OpenAICompatAdapter, "generate", side_effect=mock_generate), \
             patch.object(LLMRouter, "get_adapter_for_provider") as mock_get_adapter:

            mock_adapter = MagicMock()
            mock_adapter.generate.side_effect = mock_generate
            mock_get_adapter.return_value = mock_adapter

            messages = [ChatMessage(role="user", content="Hello")]
            resp = router.generate_with_failover("groq", "llama-3.3-70b-versatile", messages)

            self.assertEqual(resp.text, "Success from good key")
            self.assertIsNone(resp.error)
            self.assertEqual(get_active_key("groq"), "good_key")
            self.assertEqual(call_count, 2)

    def test_telemetry_emission(self):
        router = LLMRouter()
        telemetry_events = []

        def listener(data):
            telemetry_events.append(data)

        router.register_telemetry_listener(listener)

        with patch.object(LLMRouter, "get_adapter_for_provider") as mock_get_adapter:
            mock_adapter = MagicMock()
            mock_adapter.generate.return_value = LLMResponse(
                text="Telemetry test response",
                prompt_tokens=25,
                completion_tokens=15,
                total_tokens=40,
                latency_ms=120,
                provider="gemini",
                model="gemini-2.5-flash",
            )
            mock_get_adapter.return_value = mock_adapter

            messages = [ChatMessage(role="user", content="Ping")]
            router.generate_with_failover("gemini", "gemini-2.5-flash", messages)

            self.assertEqual(len(telemetry_events), 1)
            event = telemetry_events[0]
            self.assertEqual(event["provider"], "gemini")
            self.assertEqual(event["model"], "gemini-2.5-flash")
            self.assertEqual(event["prompt_tokens"], 25)
            self.assertEqual(event["completion_tokens"], 15)
            self.assertEqual(event["total_session_tokens"], 40)
            self.assertEqual(event["latency_ms"], 120)


if __name__ == "__main__":
    unittest.main()
