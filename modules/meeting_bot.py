#!/usr/bin/env python3
"""
Meeting Bot Module
Headed Playwright browser automation for Google Meet and Microsoft Teams.

Uses a persistent browser profile so Google/Microsoft accounts stay logged in
across runs (bypassing 2FA/bot-detection). The browser launches in headed mode
so the user can verbally take over calls at any moment.

One-time setup:
    python -m modules.meeting_bot --setup
    (Opens a browser window for you to manually log in to Google & Microsoft.)
"""

import os
import sys
import time
import threading
import re
from datetime import datetime

# Playwright
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[!] Playwright not installed. Meeting bot disabled.")

# ─── Paths ────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSER_PROFILE_DIR = os.path.join(BASE_DIR, ".browser_profile")

# Browser launch flags
CHROMIUM_FLAGS = [
    "--use-fake-ui-for-media-stream",   # auto-grant mic/camera permission dialogs
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-notifications",
]


class MeetingBot:
    """
    Headed Playwright bot for joining Google Meet / Microsoft Teams calls.

    Key design decisions:
    - `headless=False` so the user can see and take over the call.
    - Persistent browser context so logins survive across restarts.
    - Mic & camera forced OFF before clicking "Join".
    - 30-second polling loop to auto-leave when participants < 2 or end_time arrives.
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._active_page = None
        self._monitor_thread = None
        self._should_leave = threading.Event()
        self._lock = threading.Lock()

        # Ensure profile directory exists
        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)

    # ─── Lifecycle ────────────────────────────────────────────────

    def _ensure_browser(self):
        """Lazily start the Playwright browser (persistent context)."""
        if self._context is not None:
            return

        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE_DIR,
            headless=False,
            args=CHROMIUM_FLAGS,
            ignore_default_args=["--enable-automation"],
            channel="chrome",  # use locally installed Chrome
            viewport={"width": 1280, "height": 720},
            permissions=["microphone", "camera"],
        )
        print("[MeetingBot] Browser launched (Chrome, persistent context)")

    def close(self):
        """Shut down the browser and Playwright."""
        self._should_leave.set()
        try:
            if self._context:
                self._context.close()
                self._context = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
        except Exception:
            pass

    # ─── Platform Detection ───────────────────────────────────────

    @staticmethod
    def detect_platform(url: str) -> str:
        if "meet.google.com" in url:
            return "google_meet"
        elif "teams.microsoft.com" in url or "teams.live.com" in url:
            return "teams"
        return "unknown"

    # ─── Join Meeting ─────────────────────────────────────────────

    def join_meeting(self, url: str, end_time: datetime = None,
                     auto_leave: bool = True):
        """
        Navigate to the meeting URL, disable mic/camera, click Join,
        and start the monitoring loop.

        This method BLOCKS until the meeting ends (participant count drops
        below 2, end_time is reached, or leave_meeting() is called externally).
        Run it in a daemon thread to avoid blocking JARVIS's main loop.
        """
        if not PLAYWRIGHT_AVAILABLE:
            print("[MeetingBot] Playwright not installed — cannot join.")
            return

        self._should_leave.clear()
        self._ensure_browser()

        platform = self.detect_platform(url)
        page = self._context.new_page()
        self._active_page = page

        try:
            print(f"[MeetingBot] Navigating to {platform} meeting...")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            if platform == "google_meet":
                self._join_google_meet(page)
            elif platform == "teams":
                self._join_teams(page)
            else:
                print(f"[MeetingBot] Unknown platform for URL: {url}")
                page.close()
                return

            # Start monitoring loop
            if auto_leave:
                self._monitor_call(page, end_time, platform)

        except Exception as e:
            print(f"[MeetingBot] Error during meeting: {e}")
        finally:
            self._active_page = None
            try:
                if not page.is_closed():
                    page.close()
            except Exception:
                pass

    # ─── Google Meet ──────────────────────────────────────────────

    def _join_google_meet(self, page):
        """
        Handle the Google Meet pre-join lobby:
        1. Wait for the lobby to load
        2. Toggle mic and camera OFF
        3. Click "Join now" or "Ask to join"
        """
        # Wait for the pre-join lobby to settle
        page.wait_for_timeout(4000)

        # ── Mic OFF ──
        # Google Meet mic toggle: aria-label contains "microphone"
        try:
            mic_btn = page.locator('[aria-label*="microphone" i][data-is-muted]').first
            if mic_btn.count() > 0:
                is_muted = mic_btn.get_attribute("data-is-muted")
                if is_muted == "false":
                    mic_btn.click()
                    print("[MeetingBot] Mic toggled OFF")
            else:
                # Fallback: look for the mic button by tooltip text
                mic_fallback = page.locator('[aria-label*="Turn off microphone" i]').first
                if mic_fallback.count() > 0:
                    mic_fallback.click()
                    print("[MeetingBot] Mic toggled OFF (fallback)")
        except Exception:
            print("[MeetingBot] Could not detect mic state — proceeding")

        # ── Camera OFF ──
        try:
            cam_btn = page.locator('[aria-label*="camera" i][data-is-muted]').first
            if cam_btn.count() > 0:
                is_muted = cam_btn.get_attribute("data-is-muted")
                if is_muted == "false":
                    cam_btn.click()
                    print("[MeetingBot] Camera toggled OFF")
            else:
                cam_fallback = page.locator('[aria-label*="Turn off camera" i]').first
                if cam_fallback.count() > 0:
                    cam_fallback.click()
                    print("[MeetingBot] Camera toggled OFF (fallback)")
        except Exception:
            print("[MeetingBot] Could not detect camera state — proceeding")

        page.wait_for_timeout(1000)

        # ── Click "Join now" or "Ask to join" ──
        join_clicked = False
        for selector in [
            'button:has-text("Join now")',
            'button:has-text("Ask to join")',
            'button:has-text("Join")',
            '[data-idom-class*="join"]',
        ]:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    join_clicked = True
                    print(f"[MeetingBot] Clicked: {selector}")
                    break
            except Exception:
                continue

        if not join_clicked:
            print("[MeetingBot] Could not find Join button — page may need manual intervention")

        # Allow time for the call to connect
        page.wait_for_timeout(5000)
        print("[MeetingBot] ✓ Joined Google Meet")

    # ─── Microsoft Teams ──────────────────────────────────────────

    def _join_teams(self, page):
        """
        Handle Microsoft Teams join flow:
        1. If prompted "Continue on this browser", click it
        2. Toggle mic/camera OFF
        3. Click "Join now"
        """
        page.wait_for_timeout(5000)

        # Teams often shows "Continue on this browser" for non-app users
        try:
            continue_btn = page.locator('button:has-text("Continue on this browser")').first
            if continue_btn.count() > 0 and continue_btn.is_visible():
                continue_btn.click()
                page.wait_for_timeout(3000)
                print("[MeetingBot] Clicked 'Continue on this browser'")
        except Exception:
            pass

        # Alternatively: "Join on the web instead"
        try:
            web_btn = page.locator('a:has-text("Join on the web instead")').first
            if web_btn.count() > 0 and web_btn.is_visible():
                web_btn.click()
                page.wait_for_timeout(3000)
                print("[MeetingBot] Clicked 'Join on the web instead'")
        except Exception:
            pass

        page.wait_for_timeout(3000)

        # ── Mic OFF ──
        try:
            mic_btn = page.locator('[aria-label*="Mic" i]').first
            if mic_btn.count() > 0:
                # Check if mic is on (Teams uses aria-checked or toggle state)
                aria = mic_btn.get_attribute("aria-checked") or mic_btn.get_attribute("aria-pressed")
                if aria == "true":
                    mic_btn.click()
                    print("[MeetingBot] Teams mic toggled OFF")
        except Exception:
            # Fallback: toggle by finding the mute button
            try:
                toggle = page.locator('#microphone-joiner-button, [data-tid="toggle-mute"]').first
                if toggle.count() > 0:
                    toggle.click()
                    print("[MeetingBot] Teams mic toggled OFF (fallback)")
            except Exception:
                print("[MeetingBot] Could not detect Teams mic state")

        # ── Camera OFF ──
        try:
            cam_btn = page.locator('[aria-label*="Camera" i]').first
            if cam_btn.count() > 0:
                aria = cam_btn.get_attribute("aria-checked") or cam_btn.get_attribute("aria-pressed")
                if aria == "true":
                    cam_btn.click()
                    print("[MeetingBot] Teams camera toggled OFF")
        except Exception:
            try:
                toggle = page.locator('#video-joiner-button, [data-tid="toggle-video"]').first
                if toggle.count() > 0:
                    toggle.click()
                    print("[MeetingBot] Teams camera toggled OFF (fallback)")
            except Exception:
                print("[MeetingBot] Could not detect Teams camera state")

        page.wait_for_timeout(1000)

        # ── Click Join ──
        join_clicked = False
        for selector in [
            'button:has-text("Join now")',
            'button:has-text("Join")',
            '#join-btn',
            '[data-tid="prejoin-join-button"]',
        ]:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    join_clicked = True
                    print(f"[MeetingBot] Clicked: {selector}")
                    break
            except Exception:
                continue

        if not join_clicked:
            print("[MeetingBot] Could not find Teams Join button")

        page.wait_for_timeout(5000)
        print("[MeetingBot] ✓ Joined Microsoft Teams")

    # ─── In-Call Monitoring ───────────────────────────────────────

    def _monitor_call(self, page, end_time: datetime, platform: str):
        """
        Poll every 30 seconds. Leave when:
        - Participant count drops below 2
        - Scheduled end_time is reached
        - _should_leave event is set (external leave command)
        - Call end modal appears
        """
        print("[MeetingBot] Monitoring call...")
        while not self._should_leave.is_set():
            time.sleep(30)

            # Check if page was closed externally
            try:
                if page.is_closed():
                    print("[MeetingBot] Page closed — exiting monitor")
                    return
            except Exception:
                return

            # Check end_time
            if end_time and datetime.now() >= end_time:
                print("[MeetingBot] End time reached — leaving meeting")
                self._leave_page(page, platform)
                return

            # Check participant count
            count = self._get_participant_count(page, platform)
            if count is not None and count < 2:
                print(f"[MeetingBot] Participants dropped to {count} — leaving meeting")
                self._leave_page(page, platform)
                return

            # Check for "call ended" overlay
            if self._is_call_ended(page, platform):
                print("[MeetingBot] Call ended detected — closing page")
                return

    def _get_participant_count(self, page, platform: str) -> int | None:
        """Try to read the participant counter from the DOM."""
        try:
            if platform == "google_meet":
                # Google Meet shows participant count in various locations
                for selector in [
                    '[data-participant-id]',
                    '[aria-label*="participant" i]',
                    '.uGOf1d',  # participant counter chip
                ]:
                    elements = page.locator(selector)
                    count = elements.count()
                    if count > 0:
                        # If it's a counter chip, read the text
                        text = elements.first.inner_text()
                        nums = re.findall(r'\d+', text)
                        if nums:
                            return int(nums[0])
                        return count

            elif platform == "teams":
                # Teams participant roster count
                for selector in [
                    '[data-tid="roster-header-count"]',
                    '[aria-label*="participant" i]',
                    '.roster-count',
                ]:
                    el = page.locator(selector).first
                    if el.count() > 0:
                        text = el.inner_text()
                        nums = re.findall(r'\d+', text)
                        if nums:
                            return int(nums[0])
        except Exception:
            pass
        return None

    def _is_call_ended(self, page, platform: str) -> bool:
        """Detect if the call has ended (overlay / redirect)."""
        try:
            if platform == "google_meet":
                # Google Meet shows "You left the meeting" or "The meeting has ended"
                ended = page.locator('text="You left the meeting"').first
                if ended.count() > 0:
                    return True
                ended2 = page.locator('text="The meeting has ended"').first
                if ended2.count() > 0:
                    return True

            elif platform == "teams":
                ended = page.locator('text="You left the meeting"').first
                if ended.count() > 0:
                    return True
        except Exception:
            pass
        return False

    def _leave_page(self, page, platform: str):
        """Click the leave/hang-up button, then close the page."""
        try:
            if platform == "google_meet":
                # Red hang-up button
                leave_btn = page.locator('[aria-label*="Leave call" i]').first
                if leave_btn.count() > 0:
                    leave_btn.click()
                    page.wait_for_timeout(1000)

            elif platform == "teams":
                leave_btn = page.locator('[aria-label*="Leave" i], #hangup-button, [data-tid="hangup-button"]').first
                if leave_btn.count() > 0:
                    leave_btn.click()
                    page.wait_for_timeout(1000)
        except Exception as e:
            print(f"[MeetingBot] Leave button click failed: {e}")

        try:
            if not page.is_closed():
                page.close()
        except Exception:
            pass

    # ─── External Controls ────────────────────────────────────────

    def leave_meeting(self):
        """Force-leave the currently active meeting (called by voice command)."""
        self._should_leave.set()
        if self._active_page and not self._active_page.is_closed():
            try:
                self._active_page.close()
            except Exception:
                pass
        print("[MeetingBot] Force-left meeting")

    def is_in_meeting(self) -> bool:
        return self._active_page is not None and not self._active_page.is_closed()

    # ─── Interactive Setup ────────────────────────────────────────

    @staticmethod
    def interactive_setup():
        """
        Open a headed browser session for the user to manually log in
        to Google and Microsoft accounts. The session is saved to the
        persistent profile so future bot runs don't need re-authentication.
        """
        if not PLAYWRIGHT_AVAILABLE:
            print("ERROR: Playwright is not installed.")
            print("Run: pip install playwright && python -m playwright install chromium")
            return

        print("=" * 60)
        print("Meeting Bot — One-Time Account Setup")
        print("=" * 60)
        print()
        print("A browser window will open. Please log in to:")
        print("  1. Your Google account (for Google Meet)")
        print("  2. Your Microsoft account (for Teams)")
        print()
        print("Once logged in, close the browser window to save the session.")
        print()

        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)

        pw = sync_playwright().start()
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE_DIR,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
            ignore_default_args=["--enable-automation"],
            channel="chrome",  # use locally installed Chrome
            viewport={"width": 1280, "height": 900},
        )

        # Open helpful tabs
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://accounts.google.com")
        teams_page = ctx.new_page()
        teams_page.goto("https://login.microsoftonline.com")

        print("Waiting for you to finish logging in... (close the browser when done)")

        try:
            # Block until the user closes the browser
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass

        try:
            ctx.close()
        except Exception:
            pass
        pw.stop()

        print()
        print("✓ Session saved! The meeting bot will use these credentials automatically.")
        print()


# ─── CLI Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    if "--setup" in sys.argv:
        MeetingBot.interactive_setup()
    else:
        print("Usage:")
        print("  python -m modules.meeting_bot --setup   # One-time login setup")
