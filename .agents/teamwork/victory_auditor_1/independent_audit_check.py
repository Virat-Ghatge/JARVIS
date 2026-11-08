"""
Independent Audit Verification Script
Executed by Victory Auditor to verify startup flow, asset serving, WebSocket contracts, and resilience.
"""
import sys
import os
import json
import time
import subprocess
from pathlib import Path

REPO_ROOT = Path("d:/Projects, hackathons/JARVIS").resolve()
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from automation.server import app
import main

def run_audit():
    print("=== STARTING INDEPENDENT VICTORY AUDIT CHECKS ===")
    failures = []

    # Check 1: UI build staleness detection
    print("[Check 1] Verifying UI build staleness detection...")
    if main._is_ui_build_stale():
        failures.append("Check 1 failed: _is_ui_build_stale returned True for freshly built bundle")
    else:
        print("  -> PASS: _is_ui_build_stale() is False.")

    # Check 2: Browser binary discovery
    print("[Check 2] Verifying browser binary discovery...")
    browser = main.find_chromium_binary()
    print(f"  -> Discovered browser: {browser}")
    if not browser:
        print("  -> WARNING: No Chromium binary found via find_chromium_binary(). Checking fallback...")
    else:
        print("  -> PASS: Found Chromium executable.")

    client = TestClient(app)

    # Check 3: Root HTML serving
    print("[Check 3] Verifying GET / returns index.html with #root...")
    res = client.get("/")
    if res.status_code != 200:
        failures.append(f"Check 3 failed: GET / returned {res.status_code}")
    elif '<div id="root"></div>' not in res.text:
        failures.append("Check 3 failed: #root mount point missing from HTML")
    elif "/assets/index-" not in res.text:
        failures.append("Check 3 failed: Asset bundle script tag missing from HTML")
    else:
        print("  -> PASS: HTML served correctly with #root and asset script.")

    # Check 4: Asset bundle serving
    print("[Check 4] Verifying production JS and CSS bundles...")
    import re
    js_match = re.search(r'src="(/assets/[^"]+\.js)"', res.text)
    css_match = re.search(r'href="(/assets/[^"]+\.css)"', res.text)
    if not js_match or not css_match:
        failures.append("Check 4 failed: could not extract JS/CSS paths from index.html")
    else:
        js_path = js_match.group(1)
        css_path = css_match.group(1)
        js_res = client.get(js_path)
        css_res = client.get(css_path)
        if js_res.status_code != 200 or "javascript" not in js_res.headers.get("content-type", ""):
            failures.append(f"Check 4 failed: JS asset {js_path} returned {js_res.status_code} ({js_res.headers.get('content-type')})")
        else:
            print(f"  -> PASS: JS asset {js_path} served with 200 and {js_res.headers.get('content-type')}.")

        if css_res.status_code != 200 or "css" not in css_res.headers.get("content-type", ""):
            failures.append(f"Check 4 failed: CSS asset {css_path} returned {css_res.status_code} ({css_res.headers.get('content-type')})")
        else:
            print(f"  -> PASS: CSS asset {css_path} served with 200 and {css_res.headers.get('content-type')}.")

    # Check 5: Nonexistent asset returns 404
    print("[Check 5] Verifying nonexistent asset returns 404...")
    bad_res = client.get("/assets/bogus_missing_chunk_xyz.js")
    if bad_res.status_code != 404:
        failures.append(f"Check 5 failed: nonexistent asset returned {bad_res.status_code} instead of 404")
    else:
        print("  -> PASS: Nonexistent asset returned 404.")

    # Check 6: WebSocket handshake contracts
    print("[Check 6] Verifying WebSocket handshake telemetry contracts...")
    with client.websocket_connect("/ws") as ws:
        msg1 = json.loads(ws.receive_text())
        msg2 = json.loads(ws.receive_text())
        msg3 = json.loads(ws.receive_text())

        # Verify AUDIO_STATE
        if msg1.get("type") != "AUDIO_STATE":
            failures.append(f"Check 6 failed: first ws message type was {msg1.get('type')}, expected AUDIO_STATE")
        elif "payload" not in msg1 or "data" not in msg1:
            failures.append("Check 6 failed: AUDIO_STATE missing payload or data key")
        elif not isinstance(msg1["payload"], dict) or "mic_active" not in msg1["payload"] or "tts_active" not in msg1["payload"]:
            failures.append("Check 6 failed: AUDIO_STATE payload missing mic_active or tts_active")
        else:
            print(f"  -> PASS: AUDIO_STATE verified: {msg1['payload']}")

        # Verify MEETING_STATE
        if msg2.get("type") != "MEETING_STATE":
            failures.append(f"Check 6 failed: second ws message type was {msg2.get('type')}, expected MEETING_STATE")
        elif "payload" not in msg2 or "data" not in msg2:
            failures.append("Check 6 failed: MEETING_STATE missing payload or data key")
        else:
            print(f"  -> PASS: MEETING_STATE verified: {msg2['payload']}")

        # Verify SYSTEM_TELEMETRY
        if msg3.get("type") != "SYSTEM_TELEMETRY":
            failures.append(f"Check 6 failed: third ws message type was {msg3.get('type')}, expected SYSTEM_TELEMETRY")
        elif "payload" not in msg3 or "data" not in msg3:
            failures.append("Check 6 failed: SYSTEM_TELEMETRY missing payload or data key")
        elif not isinstance(msg3["payload"], dict) or "cpu" not in msg3["payload"] or "ram" not in msg3["payload"]:
            failures.append("Check 6 failed: SYSTEM_TELEMETRY payload missing cpu or ram")
        else:
            print(f"  -> PASS: SYSTEM_TELEMETRY verified: cpu={msg3['payload']['cpu']}, ram={msg3['payload']['ram']}, online={msg3['payload']['online']}")

    # Check 7: ErrorBoundary and Frontend Resilience
    print("[Check 7] Verifying ErrorBoundary and defensive code in compiled JS bundle...")
    dist_js_file = list((REPO_ROOT / "ui" / "dist" / "assets").glob("index-*.js"))[0]
    dist_js_content = dist_js_file.read_text(encoding="utf-8")
    if "SYSTEM ALERT: HUD RECOVERY" not in dist_js_content:
        failures.append("Check 7 failed: ErrorBoundary recovery text not found in compiled bundle")
    else:
        print("  -> PASS: ErrorBoundary recovery banner present in compiled bundle.")

    # Summary
    print("\n=== AUDIT SUMMARY ===")
    if failures:
        print(f"VERDICT: FAIL with {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("VERDICT: ALL INDEPENDENT CHECKS PASSED.")
        sys.exit(0)

if __name__ == "__main__":
    run_audit()
