#!/usr/bin/env python3
"""
Test Suite for LOOP 3 & LOOP 4: PySide6 GUI Construction & Signal-Slot Integration
Tests widget instantiation, HUD layout rendering, asynchronous command wiring,
and audio toggling without DPI or overlap issues.
"""

import sys
import os
import time
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Use offscreen platform for automated test execution if headless, or standard platform
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from ui.app_window import MainWindow
from core.engine import JARVISEngine
from core.tts_engine import TTSEngine


def test_ui_construction_and_wiring():
    print("=" * 60)
    print("RUNNING LOOP 3 & 4: PYSIDE6 GUI & ASYNC WIRING VERIFICATION")
    print("=" * 60)

    app = QApplication.instance() or QApplication(sys.argv)

    print("[1] Instantiating silent TTSEngine and JARVISEngine...")
    tts = TTSEngine(enabled=False)
    engine = JARVISEngine(tts_engine=tts)

    print("[2] Creating MainWindow...")
    window = MainWindow(engine=engine)
    window.show()

    # Verify essential HUD widgets exist
    print("[3] Verifying UI components...")
    assert window.chat_feed is not None, "ChatFeed must be initialized"
    assert window.input_bar is not None, "InputBar must be initialized"
    assert window.telemetry_dock is not None, "TelemetryDock must be initialized"
    assert window.btn_mic is not None, "Mic button must be initialized"
    assert window.btn_tts is not None, "TTS button must be initialized"
    assert window.badge_status is not None, "Online status badge must be initialized"
    print("  [OK] All HUD components initialized successfully!")

    # Verify Audio Toggles
    print("[4] Testing Audio Toggle Controls...")
    initial_mic = window.voice_listener.is_active()
    window._toggle_mic()
    assert window.voice_listener.is_active() != initial_mic, "Mic toggle should invert state"
    window._toggle_mic()  # restore
    assert window.voice_listener.is_active() == initial_mic

    initial_tts = window.tts_engine.is_enabled()
    window._toggle_tts()
    assert window.tts_engine.is_enabled() != initial_tts, "TTS toggle should invert state"
    window._toggle_tts()  # restore
    print("  [OK] Dual audio toggles verified!")

    # Test Asynchronous Command Execution
    print("[5] Testing Asynchronous Command Wiring (text input -> execution -> chat bubble)...")
    initial_bubble_count = window.chat_feed.layout.count()

    # Simulate text command submission
    window._on_text_command("what time is it")

    # Process events to allow QThreadPool / QRunnable to run
    start_time = time.time()
    while time.time() - start_time < 3.0:
        app.processEvents()
        if window.chat_feed.layout.count() >= initial_bubble_count + 2:
            break
        time.sleep(0.05)

    final_bubble_count = window.chat_feed.layout.count()
    print(f"  Bubble count: initial={initial_bubble_count}, final={final_bubble_count}")
    assert final_bubble_count >= initial_bubble_count + 2, "Both user bubble and JARVIS response bubble must be added!"
    print("  [OK] Async command execution and ChatFeed logging verified!")

    # Test Meeting Interlock UI signal
    print("[6] Testing Meeting Interlock UI signal...")
    window._on_meeting_event("joined", "Sprint Planning")
    app.processEvents()
    assert window.badge_meeting.isVisible() is True, "Meeting badge should be visible when meeting joined"

    window._on_meeting_event("left", "Sprint Planning")
    app.processEvents()
    assert window.badge_meeting.isVisible() is False, "Meeting badge should be hidden when meeting left"
    print("  [OK] Meeting interlock UI events verified!")

    window.close()
    app.processEvents()

    print("\n" + "=" * 60)
    print("[ALL LOOP 3 & 4 GUI TESTS PASSED SUCCESSFULLY!]")
    print("=" * 60)


if __name__ == "__main__":
    test_ui_construction_and_wiring()
