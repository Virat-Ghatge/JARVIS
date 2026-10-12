#!/usr/bin/env python3
"""
Test Suite for LOOP 2: Concurrency & Audio State Machine
Tests thread-safe controls, meeting-aware auto-mute, manual override during calls,
and restoration logic.
"""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.voice_listener import VoiceListener


def test_audio_state_machine():
    print("=" * 60)
    print("RUNNING LOOP 2: AUDIO STATE MACHINE VERIFICATION")
    print("=" * 60)

    status_changes = []
    meeting_alerts = []

    def on_status(active, msg):
        status_changes.append((active, msg))
        print(f"  [Status Event] active={active}, msg='{msg}'")

    def on_meeting(event, title):
        meeting_alerts.append((event, title))
        print(f"  [Meeting Event] event='{event}', title='{title}'")

    listener = VoiceListener(
        on_command=lambda cmd: None,
        on_status_change=on_status,
        on_meeting_alert=on_meeting
    )
    # Stop background mic recording for isolated state testing
    listener.stop()

    # ── Test 1: Basic Enable / Disable / Toggle ──────────────────────
    print("\n[Test 1] Testing basic Enable / Disable / Toggle...")
    listener.enable()
    assert listener.is_active() is True, "Mic should be active after enable()"

    listener.disable()
    assert listener.is_active() is False, "Mic should be inactive after disable()"

    toggled = listener.toggle()
    assert toggled is True and listener.is_active() is True, "Toggle should turn mic on"

    toggled = listener.toggle()
    assert toggled is False and listener.is_active() is False, "Toggle should turn mic off"
    print("  [OK] Test 1 passed!")

    # ── Test 2: Auto-Mute on Meeting Join & Auto-Restore on Leave ─────
    print("\n[Test 2] Testing auto-mute on meeting join & auto-restore on leave...")
    # Start with mic active
    listener.enable()
    assert listener.is_active() is True

    # Meeting joins
    listener.handle_meeting_joined("Sprint Review")
    assert listener.in_meeting is True, "Listener should be in_meeting"
    assert listener.is_active() is False, "Mic MUST auto-mute upon joining meeting!"
    assert listener.auto_muted_by_meeting is True, "auto_muted_by_meeting flag should be True"
    assert ("joined", "Sprint Review") in meeting_alerts, "Meeting alert for joined should have emitted"
    print("  [OK] Auto-mute triggered on join verified!")

    # Meeting leaves without user override
    listener.handle_meeting_left("Sprint Review")
    assert listener.in_meeting is False, "Listener should no longer be in_meeting"
    assert listener.is_active() is True, "Mic MUST auto-restore to active state after meeting ends!"
    assert listener.auto_muted_by_meeting is False, "auto_muted flag should be cleared"
    assert ("left", "Sprint Review") in meeting_alerts, "Meeting alert for left should have emitted"
    print("  [OK] Auto-restore on meeting exit verified!")

    # ── Test 3: Manual Override During Meeting ───────────────────────
    print("\n[Test 3] Testing manual override unmute during ongoing call...")
    # Start with mic active
    listener.enable()
    assert listener.is_active() is True

    # Meeting joins -> auto-mutes
    listener.handle_meeting_joined("Client Sync")
    assert listener.is_active() is False, "Mic should be auto-muted"

    # User manually overrides and unmutes during the call
    print("  Simulating user clicking Mic Unmute during call...")
    listener.toggle()  # or listener.enable(manual_override=True)
    assert listener.is_active() is True, "Manual override MUST unmute mic even while in meeting!"
    assert listener.manual_override is True, "manual_override flag should be set"

    # Meeting ends -> mic should stay active as chosen by user
    listener.handle_meeting_left("Client Sync")
    assert listener.in_meeting is False
    assert listener.is_active() is True, "Mic should remain active as manually chosen by user"
    print("  [OK] Manual override during call verified!")

    # ── Test 4: Mic was Already Muted Before Meeting ─────────────────
    print("\n[Test 4] Testing meeting when mic was already muted prior to call...")
    listener.disable()
    assert listener.is_active() is False

    listener.handle_meeting_joined("Quiet Meeting")
    assert listener.is_active() is False
    assert listener.auto_muted_by_meeting is False, "Should not flag auto-muted if mic was already off"

    listener.handle_meeting_left("Quiet Meeting")
    assert listener.is_active() is False, "Mic must remain muted if it was off prior to meeting"
    print("  [OK] Pre-muted state preservation verified!")

    print("\n" + "=" * 60)
    print("[ALL LOOP 2 AUDIO STATE TESTS PASSED SUCCESSFULLY!]")
    print("=" * 60)


if __name__ == "__main__":
    test_audio_state_machine()
