"""
Sentinel Independent Victory Verification Script
Tests all requirements and acceptance criteria in ORIGINAL_REQUEST.md independently.
"""
import sys
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path("d:/Projects, hackathons/JARVIS").resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from automation.server import app
import main

def test_sentinel_victory():
    print("=== RUNNING SENTINEL AUDITOR INDEPENDENT VERIFICATION ===")
    
    # 1. Check Root Cause 1: Audio state destructuring and payload contracts
    print("\n[Audit Test 1] Verifying WebSocket payload contract for AUDIO_STATE, MEETING_STATE, SYSTEM_TELEMETRY...")
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        msg1 = json.loads(ws.receive_text())
        assert msg1.get("type") == "AUDIO_STATE"
        assert "payload" in msg1, "msg1 must contain 'payload' for App.tsx destructuring"
        assert "data" in msg1, "msg1 must contain 'data' for legacy consumers"
        assert isinstance(msg1["payload"], dict)
        assert "mic_active" in msg1["payload"]
        assert "tts_active" in msg1["payload"]
        print("  -> PASS: AUDIO_STATE payload contract valid.")

        msg2 = json.loads(ws.receive_text())
        assert msg2.get("type") == "MEETING_STATE"
        assert "payload" in msg2
        assert "data" in msg2
        assert isinstance(msg2["payload"], dict)
        print("  -> PASS: MEETING_STATE payload contract valid.")

        msg3 = json.loads(ws.receive_text())
        assert msg3.get("type") == "SYSTEM_TELEMETRY"
        assert "payload" in msg3
        assert "data" in msg3
        assert isinstance(msg3["payload"], dict)
        assert "cpu" in msg3["payload"]
        assert "ram" in msg3["payload"]
        assert "online" in msg3["payload"]
        assert "token_stats" in msg3["payload"]
        print("  -> PASS: SYSTEM_TELEMETRY payload contract valid.")

    # 2. Check Root Cause 2: Static asset routing and 404 behavior (strict MIME enforcement)
    print("\n[Audit Test 2] Verifying static asset serving and strict 404 for missing assets...")
    root_res = client.get("/")
    assert root_res.status_code == 200
    assert "text/html" in root_res.headers.get("content-type", "")
    assert '<div id="root"></div>' in root_res.text
    print("  -> PASS: GET / returns valid HTML with #root container.")

    missing_asset_res = client.get("/assets/non_existent_file.js")
    assert missing_asset_res.status_code == 404, f"Expected 404 for missing asset, got {missing_asset_res.status_code}"
    print("  -> PASS: Missing assets return 404 instead of fallback index.html.")

    # 3. Check Root Cause 3: Supervisor readiness probing (HTTP 200 vs TCP socket)
    print("\n[Audit Test 3] Verifying supervisor readiness probing and crash abort...")
    mock_ok = MagicMock()
    mock_ok.status = 200
    mock_ok.__enter__.return_value = mock_ok
    with patch("urllib.request.urlopen", return_value=mock_ok):
        assert main.is_server_ready("127.0.0.1", 5050) is True
        assert main.wait_for_server_ready("127.0.0.1", 5050, max_wait_sec=1.0) is True
    print("  -> PASS: wait_for_server_ready succeeds when server returns HTTP 200.")

    # Verify immediate abort if backend proc crashes
    mock_dead = MagicMock()
    mock_dead.poll.return_value = 1
    t0 = time.time()
    assert main.wait_for_server_ready("127.0.0.1", 5050, max_wait_sec=10.0, proc=mock_dead) is False
    elapsed = time.time() - t0
    assert elapsed < 0.5, f"Expected instant return on dead process, took {elapsed:.2f}s"
    print("  -> PASS: wait_for_server_ready immediately aborts if backend process terminates.")

    # 4. Check Root Cause 4: ErrorBoundary wrapper in main.tsx and defensive destructuring
    print("\n[Audit Test 4] Verifying ErrorBoundary and UI source code protections...")
    main_tsx = (REPO_ROOT / "ui" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "class ErrorBoundary extends Component" in main_tsx
    assert "<ErrorBoundary>" in main_tsx
    assert "SYSTEM ALERT: HUD RECOVERY" in main_tsx
    print("  -> PASS: ErrorBoundary present in ui/src/main.tsx.")

    app_tsx = (REPO_ROOT / "ui" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "audioState?.mic_active" in app_tsx
    assert "audioState?.tts_active" in app_tsx
    assert "const type = parsed?.type || parsed?.event;" in app_tsx
    assert "const payload = parsed?.payload !== undefined ? parsed?.payload : parsed?.data;" in app_tsx
    print("  -> PASS: Null-safe destructuring and fallback present in ui/src/App.tsx.")

    # 5. Check Production Built Bundle on disk
    print("\n[Audit Test 5] Verifying production built bundle artifacts...")
    dist_dir = REPO_ROOT / "ui" / "dist"
    assert (dist_dir / "index.html").exists()
    js_files = list((dist_dir / "assets").glob("*.js"))
    css_files = list((dist_dir / "assets").glob("*.css"))
    assert len(js_files) > 0, "No JS files in ui/dist/assets"
    assert len(css_files) > 0, "No CSS files in ui/dist/assets"
    print(f"  -> PASS: Production build verified ({len(js_files)} JS, {len(css_files)} CSS).")

    print("\n=== ALL SENTINEL AUDITOR INDEPENDENT VERIFICATIONS PASSED ===")

if __name__ == "__main__":
    test_sentinel_victory()
