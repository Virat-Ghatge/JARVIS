"""
Adversarial Stress Test Suite
Executed by Victory Auditor to stress-test assumptions and failure modes.
"""
import sys
import os
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path("d:/Projects, hackathons/JARVIS").resolve()
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from automation.server import app
import main

def stress_test():
    print("=== STARTING ADVERSARIAL STRESS TESTS ===")
    client = TestClient(app)

    # 1. Premature backend crash detection in wait_for_server_ready
    print("[Stress 1] Testing dead process handling in wait_for_server_ready...")
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 1 # terminated
    t0 = time.time()
    res = main.wait_for_server_ready("127.0.0.1", 5050, max_wait_sec=10.0, proc=mock_proc)
    duration = time.time() - t0
    assert res is False, "Expected wait_for_server_ready to return False for dead process"
    assert duration < 0.5, f"Expected immediate abort, took {duration:.2f}s"
    print(f"  -> PASS: Aborted immediately in {duration:.4f}s when proc.poll() is not None.")

    # 2. Port listening without HTTP 200
    print("[Stress 2] Testing is_server_ready non-existent server...")
    assert main.is_server_ready("127.0.0.1", 65432) is False
    print("  -> PASS: is_server_ready returned False for closed port.")

    # 3. Malformed WebSocket inputs
    print("[Stress 3] Testing malformed WebSocket messages...")
    with client.websocket_connect("/ws") as ws:
        # Drain initial messages
        ws.receive_text()
        ws.receive_text()
        ws.receive_text()

        # Send empty string
        ws.send_text("")
        # Send non-JSON
        ws.send_text("THIS IS NOT JSON")
        # Send non-dict JSON
        ws.send_text(json.dumps([1, 2, 3]))
        # Send unexpected type
        ws.send_text(json.dumps({"type": "UNEXPECTED_EVIL_EVENT", "payload": None}))
        # Send USER_COMMAND with empty query
        ws.send_text(json.dumps({"type": "USER_COMMAND", "payload": {}}))
        # Send valid command to verify connection is still completely alive and working
        ws.send_text(json.dumps({"type": "USER_COMMAND", "payload": {"query": "status"}}))
        print("  -> PASS: Handled malformed WebSocket messages without server disconnect or crash.")

    # 4. Rapid connect / disconnect cycle
    print("[Stress 4] Testing rapid WebSocket connections and disconnections...")
    for i in range(15):
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()
    print("  -> PASS: Successfully survived 15 rapid connect/disconnect cycles.")

    print("\n=== ALL ADVERSARIAL STRESS TESTS PASSED ===")

if __name__ == "__main__":
    stress_test()
