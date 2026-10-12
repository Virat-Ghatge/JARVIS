#!/usr/bin/env python3
"""
Test Suite for LOOP 1: InputGateway & Reorganized Project Structure
Confirms that execute_command succeeds offline without audio devices or import errors.
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.engine import JARVISEngine
from core.tts_engine import TTSEngine


def test_gateway_offline_time():
    print("[1] Initializing TTSEngine with enabled=False (silent test mode)...")
    tts = TTSEngine(enabled=False)
    assert not tts.is_enabled(), "TTS should be disabled"

    print("[2] Initializing JARVISEngine...")
    engine = JARVISEngine(tts_engine=tts)

    print("[3] Testing 'what time is it' via execute_command(source='text')...")
    result = engine.execute_command("what time is it", source="text")
    print(f"    Result: {result}")

    assert result["status"] == "ok", f"Expected status 'ok', got {result['status']}"
    assert result["action"] == "get_time", f"Expected action 'get_time', got {result['action']}"
    assert result["source"] == "text", f"Expected source 'text', got {result['source']}"
    assert "time" in result["response"].lower(), f"Expected 'time' in response: {result['response']}"
    print("[OK] 'what time is it' test passed!")

    print("[4] Testing 'what is the date'...")
    res_date = engine.execute_command("what is the date", source="text")
    assert res_date["status"] == "ok"
    assert res_date["action"] == "get_date"
    print("[OK] 'what is the date' test passed!")

    print("[5] Testing greeting...")
    res_greet = engine.execute_command("hello", source="text")
    assert res_greet["status"] == "ok"
    assert res_greet["action"] == "greet"
    print("[OK] 'hello' greeting test passed!")

    print("[6] Testing meeting intent...")
    res_meet = engine.execute_command("what meetings do i have today", source="text")
    assert res_meet["status"] == "ok"
    assert res_meet["action"] == "meeting_command"
    print("[OK] Meeting intent test passed!")

    print("\n[ALL LOOP 1 GATEWAY TESTS PASSED SUCCESSFULLY!]")


if __name__ == "__main__":
    test_gateway_offline_time()
