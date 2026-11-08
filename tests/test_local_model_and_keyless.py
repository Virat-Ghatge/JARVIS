#!/usr/bin/env python3
"""
Unit and Integration Test Suite for Local GGUF Engine and Keyless Auxiliary Services.
Verifies LocalGGUFAdapter, Router local-first priority and failover, keyless Open-Meteo weather, and keyless Q&A.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config.settings import (
    LOCAL_MODEL_NAME,
    LOCAL_MODEL_FILENAME,
    LOCAL_MODEL_PATH,
    get_role_target,
    load_vault,
    save_vault,
    get_vault,
    is_local_first_mode,
    set_local_first_mode,
    get_local_model_status,
)
from core.adapters.base import ChatMessage, LLMResponse
from core.adapters.local_gguf_adapter import LocalGGUFAdapter
from core.llm_router import LLMRouter
from integrations.handlers.weather import WeatherHandler, WMO_WEATHER_CODES
from integrations.handlers.qa_handler import QAHandler


class TestLocalGGUFAdapter(unittest.TestCase):
    def setUp(self):
        # Save previous instance
        self._prev_instance = LocalGGUFAdapter._model_instance
        LocalGGUFAdapter._model_instance = None

    def tearDown(self):
        LocalGGUFAdapter._model_instance = self._prev_instance

    def test_adapter_availability(self):
        self.assertTrue(LocalGGUFAdapter.is_available(), "llama-cpp-python should be detected as installed")

    def test_uninitialized_model_error_when_file_missing(self):
        adapter = LocalGGUFAdapter()
        with patch.object(LocalGGUFAdapter, "is_downloaded", return_value=False):
            res = adapter.generate([ChatMessage(role="user", content="Hello")])
            self.assertIn("not downloaded", res.error.lower())
            self.assertEqual(res.provider, "local")

    def test_mock_generation_with_llama_engine(self):
        adapter = LocalGGUFAdapter()
        mock_llama = MagicMock()
        mock_llama.create_chat_completion.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "I am JARVIS, fully operational."}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        }

        with patch.object(LocalGGUFAdapter, "is_downloaded", return_value=True), \
             patch.object(LocalGGUFAdapter, "load_model", return_value=mock_llama):
            messages = [
                ChatMessage(role="system", content="You are JARVIS."),
                ChatMessage(role="user", content="System check"),
            ]
            res = adapter.generate(messages, temperature=0.3, max_tokens=64)

            self.assertIsNone(res.error)
            self.assertEqual(res.text, "I am JARVIS, fully operational.")
            self.assertEqual(res.prompt_tokens, 12)
            self.assertEqual(res.completion_tokens, 8)
            self.assertEqual(res.total_tokens, 20)
            self.assertEqual(res.provider, "local")

    def test_json_mode_extraction(self):
        adapter = LocalGGUFAdapter()
        mock_llama = MagicMock()
        mock_llama.create_chat_completion.return_value = {
            "choices": [{"message": {"role": "assistant", "content": '```json\n{"status": "ready", "code": 200}\n```'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }

        with patch.object(LocalGGUFAdapter, "is_downloaded", return_value=True), \
             patch.object(LocalGGUFAdapter, "load_model", return_value=mock_llama):
            res = adapter.generate([ChatMessage(role="user", content="JSON")], json_mode=True)
            self.assertIsNone(res.error)
            self.assertIsNotNone(res.raw_json)
            self.assertEqual(res.raw_json.get("status"), "ready")
            self.assertEqual(res.raw_json.get("code"), 200)

    def test_connection_test_when_not_downloaded(self):
        adapter = LocalGGUFAdapter()
        with patch.object(LocalGGUFAdapter, "is_downloaded", return_value=False):
            conn = adapter.test_connection()
            self.assertFalse(conn["ok"])
            self.assertIn("not downloaded", conn["error"].lower())

    def test_generate_accepts_raw_dict_messages(self):
        adapter = LocalGGUFAdapter()
        mock_llama = MagicMock()
        mock_llama.create_chat_completion.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Online, sir."}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
        }
        with patch.object(LocalGGUFAdapter, "is_downloaded", return_value=True), \
             patch.object(LocalGGUFAdapter, "load_model", return_value=mock_llama):
            res = adapter.generate([{"role": "user", "content": "hello"}])
            self.assertIsNone(res.error)
            self.assertEqual(res.text, "Online, sir.")

    def test_unload_model_calls_close_safely(self):
        mock_instance = MagicMock()
        LocalGGUFAdapter._model_instance = mock_instance
        LocalGGUFAdapter.unload_model()
        mock_instance.close.assert_called_once()
        self.assertIsNone(LocalGGUFAdapter._model_instance)


class TestLLMRouterLocalAndFailover(unittest.TestCase):
    def setUp(self):
        self.original_vault = get_vault()

    def tearDown(self):
        save_vault(self.original_vault)

    def test_local_first_candidate_chain_ordering(self):
        router = LLMRouter()
        v = get_vault()
        v["local_first_mode"] = True
        save_vault(v)

        candidates = router._build_candidate_chain("chat")
        self.assertTrue(len(candidates) > 0)
        # When local_first_mode is True, local should be first for conversational chat
        self.assertEqual(candidates[0]["provider"], "local")

    def test_cloud_failover_to_local_when_cloud_rate_limited(self):
        router = LLMRouter()
        v = get_vault()
        v["local_first_mode"] = False
        # Configure a dummy groq key
        v["providers"]["groq"]["keys"] = ["test_groq_key"]
        v["role_mappings"]["chat"] = {"provider": "groq", "model": "llama-3.3-70b-versatile"}
        save_vault(v)

        mock_local_res = LLMResponse(
            text="Local failover response",
            prompt_tokens=5,
            completion_tokens=5,
            total_tokens=10,
            latency_ms=45,
            provider="local",
            model=LOCAL_MODEL_NAME,
        )

        # Mock groq raising 429 and local succeeding
        with patch.object(router, "_call_openai_compatible", side_effect=RuntimeError("HTTP 429: Rate limit exceeded")), \
             patch.object(LocalGGUFAdapter, "generate", return_value=mock_local_res):
            res = router.chat("Hello test", role="chat")
            self.assertTrue(res["success"])
            self.assertEqual(res["provider"], "local")
            self.assertEqual(res["content"], "Local failover response")

    def test_zero_cloud_keys_routes_locally(self):
        router = LLMRouter()
        v = get_vault()
        # Empty all cloud keys
        for p in ("gemini", "groq", "openai", "anthropic"):
            v["providers"][p]["keys"] = []
        v["custom_endpoints"] = []
        save_vault(v)

        candidates = router._build_candidate_chain("chat")
        self.assertTrue(any(c["provider"] == "local" for c in candidates))

        mock_local_res = LLMResponse(
            text="Offline response with zero cloud keys",
            prompt_tokens=6,
            completion_tokens=7,
            total_tokens=13,
            latency_ms=50,
            provider="local",
            model=LOCAL_MODEL_NAME,
        )

        with patch.object(LocalGGUFAdapter, "generate", return_value=mock_local_res):
            res = router.chat("What can you do?", role="chat")
            self.assertTrue(res["success"])
            self.assertEqual(res["provider"], "local")
            self.assertEqual(res["content"], "Offline response with zero cloud keys")


class TestKeylessWeather(unittest.TestCase):
    def test_wmo_weather_codes_coverage(self):
        self.assertIn(0, WMO_WEATHER_CODES)
        self.assertEqual(WMO_WEATHER_CODES[0], "clear sky")
        self.assertIn(3, WMO_WEATHER_CODES)
        self.assertEqual(WMO_WEATHER_CODES[3], "overcast")
        self.assertIn(61, WMO_WEATHER_CODES)
        self.assertIn("rain", WMO_WEATHER_CODES[61])

    def test_keyless_current_weather_open_meteo(self):
        mock_jarvis = MagicMock()
        handler = WeatherHandler(mock_jarvis, api_key="")
        self.assertEqual(handler.api_key, "")

        mock_geo_resp = MagicMock()
        mock_geo_resp.status_code = 200
        mock_geo_resp.json.return_value = {
            "results": [{"name": "Tokyo", "country": "Japan", "latitude": 35.6895, "longitude": 139.6917}]
        }

        mock_meteo_resp = MagicMock()
        mock_meteo_resp.status_code = 200
        mock_meteo_resp.json.return_value = {
            "current": {
                "temperature_2m": 18.5,
                "apparent_temperature": 18.0,
                "relative_humidity_2m": 60,
                "weather_code": 1,
                "wind_speed_10m": 4.5,
            }
        }

        def mock_requests_get(url, *args, **kwargs):
            if "geocoding-api" in url:
                return mock_geo_resp
            return mock_meteo_resp

        with patch("requests.get", side_effect=mock_requests_get):
            handler.get_current_weather("weather in Tokyo")
            mock_jarvis.speak.assert_called_once()
            report = mock_jarvis.speak.call_args[0][0]
            self.assertIn("Tokyo", report)
            self.assertIn("18.5", report)
            self.assertIn("mainly clear", report)

    def test_keyless_forecast_open_meteo(self):
        mock_jarvis = MagicMock()
        handler = WeatherHandler(mock_jarvis, api_key="")

        mock_geo_resp = MagicMock()
        mock_geo_resp.status_code = 200
        mock_geo_resp.json.return_value = {
            "results": [{"name": "Paris", "country": "France", "latitude": 48.8534, "longitude": 2.3488}]
        }

        mock_forecast_resp = MagicMock()
        mock_forecast_resp.status_code = 200
        mock_forecast_resp.json.return_value = {
            "daily": {
                "time": ["2026-11-01", "2026-11-02"],
                "temperature_2m_max": [16.0, 18.0],
                "temperature_2m_min": [10.0, 12.0],
                "weather_code": [0, 2],
            }
        }

        def mock_requests_get(url, *args, **kwargs):
            if "geocoding-api" in url:
                return mock_geo_resp
            return mock_forecast_resp

        with patch("requests.get", side_effect=mock_requests_get):
            handler.get_forecast("forecast in Paris tomorrow")
            mock_jarvis.speak.assert_called_once()
            report = mock_jarvis.speak.call_args[0][0]
            self.assertIn("Paris", report)
            self.assertIn("15.0", report)  # avg of 18 and 12
            self.assertIn("partly cloudy", report)

    def test_weather_location_extraction_edge_cases(self):
        mock_jarvis = MagicMock()
        handler = WeatherHandler(mock_jarvis, api_key="")
        self.assertEqual(handler._get_location("weather in London tomorrow"), "london")
        self.assertEqual(handler._get_location("forecast for Paris today"), "paris")
        self.assertEqual(handler._get_location("what will the weather be in Tokyo tomorrow"), "tokyo")
        self.assertEqual(handler._get_location("tell me the weather in Berlin please"), "berlin")

    def test_forecast_wttr_in_fallback(self):
        mock_jarvis = MagicMock()
        handler = WeatherHandler(mock_jarvis, api_key="")

        mock_wttr_resp = MagicMock()
        mock_wttr_resp.status_code = 200
        mock_wttr_resp.json.return_value = {
            "weather": [
                {},
                {
                    "avgtempC": "14",
                    "mintempC": "10",
                    "maxtempC": "18",
                    "hourly": [{"weatherDesc": [{"value": "Sunny"}]}],
                },
            ]
        }

        # Mock geocoding returning None to trigger wttr.in fallback
        with patch.object(handler, "_geocode_keyless", return_value=None), \
             patch("requests.get", return_value=mock_wttr_resp):
            success = handler._get_forecast_keyless("London")
            self.assertTrue(success)
            mock_jarvis.speak.assert_called_once()
            report = mock_jarvis.speak.call_args[0][0]
            self.assertIn("London", report)
            self.assertIn("14", report)


class TestKeylessQA(unittest.TestCase):
    def test_qa_handler_uses_router_when_no_groq_key(self):
        mock_jarvis = MagicMock()
        qa = QAHandler(mock_jarvis)
        # In this test, ensure groq client is None
        qa.groq_client = None

        mock_router_answer = "Sir, light travels at approximately 300,000 kilometers per second."

        with patch("core.llm_router.router.query_text", return_value=mock_router_answer):
            success = qa.answer_question("What is the speed of light?")
            self.assertTrue(success)
            mock_jarvis.speak.assert_called_with(mock_router_answer)


class TestSettingsAndVaultLocalIntegration(unittest.TestCase):
    def setUp(self):
        self.original_vault = get_vault()

    def tearDown(self):
        save_vault(self.original_vault)

    def test_local_model_status_structure(self):
        status = get_local_model_status()
        self.assertIn("model_name", status)
        self.assertIn("filename", status)
        self.assertIn("downloaded", status)
        self.assertIn("loaded", status)
        self.assertIn("threads", status)
        self.assertEqual(status["filename"], LOCAL_MODEL_FILENAME)

    def test_local_first_mode_toggle(self):
        set_local_first_mode(True)
        self.assertTrue(is_local_first_mode())

        set_local_first_mode(False)
        self.assertFalse(is_local_first_mode())

    def test_get_role_target_resolves_local(self):
        v = get_vault()
        v["role_mappings"]["chat"] = {"provider": "local", "model": LOCAL_MODEL_NAME}
        save_vault(v)

        target = get_role_target("chat")
        self.assertEqual(target.get("provider"), "local")
        self.assertEqual(target.get("api_key"), "local-in-process")
        # Test tuple unpacking compatibility
        prov, model = target
        self.assertEqual(prov, "local")


if __name__ == "__main__":
    unittest.main()
