#!/usr/bin/env python3
"""
Test Suite for JARVIS LLM Features
Verifies Groq Q&A, Gemini fallback, intent classification, and caching.
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.engine import JARVISEngine
from core.tts_engine import TTSEngine


def test_llm_suite():
    print("=" * 60)
    print("VERIFYING JARVIS LLM CAPABILITIES (GROQ & GEMINI)")
    print("=" * 60)

    # Initialize silent engine
    tts = TTSEngine(enabled=False)
    engine = JARVISEngine(tts_engine=tts)

    # 1. Verify Groq & Gemini clients or Keyless Fallback
    print("\n[1] Checking Client Initialization...")
    has_groq_key = bool(os.getenv("GROQ_API_KEY"))
    has_gemini_key = bool(os.getenv("GEMINI_API_KEY"))

    if has_groq_key:
        assert engine.qa_handler.groq_client is not None, "Groq client must be initialized when GROQ_API_KEY is set"
        print("  [OK] Groq client initialized.")
    else:
        print("  [OK] Keyless Q&A active (GROQ_API_KEY not set — routed via local/unified router).")

    if has_gemini_key:
        assert engine.genai_client is not None, "Gemini client must be initialized when GEMINI_API_KEY is set"
        print("  [OK] Gemini client initialized.")
    else:
        print("  [OK] Keyless intent routing active (GEMINI_API_KEY not set).")

    # 2. Test Groq Q&A via QAHandler (or keyless router)
    print("\n[2] Testing Q&A via QAHandler...")
    query = "Who was Albert Einstein?"
    res_q = engine.execute_command(query, source="text")
    print(f"  Query: '{query}'")
    print(f"  Response: {res_q['response']}")
    assert res_q["status"] == "ok", f"Expected status 'ok', got {res_q['status']}"
    assert res_q["action"] == "answer_question"
    assert len(res_q["response"]) > 10, "Response should be substantive"
    print("  [OK] Q&A answered successfully!")

    # 3. Test Local Cache Hit
    print("\n[3] Testing Q&A Cache Hit...")
    res_cached = engine.execute_command(query, source="text")
    print(f"  Cached Response: {res_cached['response']}")
    assert res_cached["status"] == "ok"
    assert res_cached["response"] == res_q["response"], "Cached response should match original"
    print("  [OK] Cache hit verified!")

    # 4. Test Gemini Direct Q&A or Keyless Fallback
    print("\n[4] Testing Gemini Q&A Fallback / Local Router...")
    if has_gemini_key and engine.genai_client and getattr(engine, "ai_model", None):
        gemini_ans = engine.qa_handler._ask_gemini("What is quantum entanglement?")
        print(f"  Gemini Answer: {gemini_ans}")
        assert gemini_ans is not None and len(gemini_ans) > 10, "Gemini should return an answer"
        print("  [OK] Gemini Q&A answered successfully!")
    else:
        router_ans = engine.router.query_text("qa_chat", "What is quantum entanglement?")
        print(f"  Unified Router Answer: {router_ans[:80]}...")
        assert router_ans and len(router_ans) > 10, "Router should return substantive answer"
        print("  [OK] Keyless Q&A fallback answered successfully!")

    # 5. Test AI Intent Classification
    print("\n[5] Testing AI Intent Classification (non-local command)...")
    command_query = "I am bored, play something upbeat on youtube"
    res_intent = engine.execute_command(command_query, source="text")
    print(f"  Query: '{command_query}'")
    print(f"  Result Action: {res_intent['action']}")
    print(f"  Response: {res_intent['response']}")
    assert res_intent["status"] == "ok"
    print("  [OK] Intent classification executed successfully!")

    print("\n" + "=" * 60)
    print("[ALL LLM FEATURES ARE WORKING PERFECTLY!]")
    print("=" * 60)


if __name__ == "__main__":
    test_llm_suite()
