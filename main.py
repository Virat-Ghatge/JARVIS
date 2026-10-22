#!/usr/bin/env python3
"""
JARVIS 2.0 Main Entry Point
Launches the FastAPI backend server, background APScheduler, and VoiceListener,
then opens the Marvel Holographic HUD inside a native PyWebView frameless window.
Supports --cli for headless terminal-only mode.
"""

import sys
import os
import threading
import time
import uvicorn

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from automation.server import app as fastapi_app
from audio.voice_listener import voice_listener
from audio.tts_engine import tts_engine
from core.engine import engine

class JarvisWindowApi:
    def __init__(self):
        self.window = None

    def set_mini_mode(self, enabled: bool):
        if not self.window:
            return False
        try:
            if enabled:
                self.window.resize(520, 140)
                self.window.on_top = True
            else:
                self.window.resize(1360, 860)
                self.window.on_top = False
            return True
        except Exception as e:
            print(f"[JarvisWindowApi] set_mini_mode error: {e}")
            return False


def start_backend():
    """Runs the FastAPI server in a background thread."""
    uvicorn.run(fastapi_app, host="127.0.0.1", port=5050, log_level="warning")

def main():
    print("=" * 60)
    print(" J.A.R.V.I.S. 2.0 — Autonomous OS Agent & Holographic HUD")
    print("=" * 60)

    # 1. Start FastAPI Backend in background thread
    server_thread = threading.Thread(target=start_backend, daemon=True, name="FastAPI-Server")
    server_thread.start()
    print("[Main] Backend server operational at http://127.0.0.1:5050")

    # 2. Wire Meeting Handler (single source of truth on engine — no duplicate instances)
    meeting_handler = getattr(engine, "meeting_handler", None)
    print("[Main] Meeting scheduler & Playwright attendant online")

    # 3. Start Voice Listener
    voice_listener.start()
    print("[Main] Voice listener active")

    # Check CLI mode flag
    if "--cli" in sys.argv:
        print("[Main] Running in CLI terminal mode. Type commands below (Ctrl+C to exit):")
        try:
            while True:
                q = input("\nOperator > ")
                if q.lower() in ("exit", "quit", "shutdown"):
                    break
                res = engine.process_command(q, source="text")
                print(f"JARVIS > {res.get('text', '')}")
        except KeyboardInterrupt:
            pass
        finally:
            voice_listener.stop()
            if meeting_handler:
                meeting_handler.shutdown()
            print("\n[Main] JARVIS shutdown complete.")
        return

    # 4. Launch Native PyWebView Desktop HUD Window
    try:
        import webview
        print("[Main] Launching native PyWebView Desktop HUD...")
        
        js_api = JarvisWindowApi()
        # Create frameless/styled native window pointing to FastAPI server
        window = webview.create_window(
            title="J.A.R.V.I.S. 2.0",
            url="http://127.0.0.1:5050",
            width=1360,
            height=860,
            min_size=(400, 120),
            background_color="#060A12",
            resizable=True,
            confirm_close=False,
            js_api=js_api,
        )
        js_api.window = window

        webview.start(debug=False)
    except Exception as e:
        print(f"[Main] PyWebView launch notice ({e}). Falling back to browser app mode...")
        import webbrowser
        webbrowser.open("http://127.0.0.1:5050")
        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        voice_listener.stop()
        if meeting_handler:
            meeting_handler.shutdown()
        print("[Main] JARVIS shutdown complete.")

if __name__ == "__main__":
    main()

