import sys
import json
import time
import threading
import traceback
from pathlib import Path
from typing import Dict, Any, List

from config.settings import BROWSER_PROFILE_DIR

_command_state = {"leave_requested": False, "setup_mode": False}


def emit(event_type: str, payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps({"event": event_type, "payload": payload}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _stdin_watcher() -> None:
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            cmd = json.loads(raw)
            if cmd.get("command") == "leave":
                _command_state["leave_requested"] = True
                break
        except Exception:
            continue


def _mute_and_join_google_meet(page: Any) -> None:
    time.sleep(2.5)
    for hotkey in ("Control+d", "Control+e"):
        try:
            page.keyboard.press(hotkey)
            time.sleep(0.3)
        except Exception:
            pass

    join_selectors = [
        "button:has-text('Join now')",
        "button:has-text('Ask to join')",
        "button:has-text('Switch here')",
    ]
    for sel in join_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                loc.click()
                break
        except Exception:
            continue


def _mute_and_join_teams(page: Any) -> None:
    time.sleep(3.0)
    join_selectors = [
        "button:has-text('Join now')",
        "button[data-tid='prejoin-join-button']",
    ]
    for sel in join_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2000):
                loc.click()
                break
        except Exception:
            continue


def _scrape_live_captions(page: Any, transcript_log: List[Dict[str, str]], seen_lines: set) -> None:
    selectors = [
        "div[jscontroller] span",
        "[ data-tid='closed-captions-renderer'] span",
        ".iOzk7",
        ".a4cQT",
    ]
    for sel in selectors:
        try:
            nodes = page.locator(sel).all_inner_texts()
            for text in nodes[-6:]:
                cleaned = " ".join(text.strip().split())
                if len(cleaned) > 4 and cleaned not in seen_lines:
                    seen_lines.add(cleaned)
                    entry = {"timestamp": time.strftime("%H:%M:%S"), "text": cleaned}
                    transcript_log.append(entry)
                    emit("CAPTION", entry)
        except Exception:
            continue


def run_meeting_session(config: Dict[str, Any]) -> None:
    url = config.get("url", "https://accounts.google.com")
    meeting_id = config.get("meeting_id", f"mtg_{int(time.time())}")
    title = config.get("title", "Live Meeting")
    setup_only = bool(config.get("setup_only", False))

    watcher = threading.Thread(target=_stdin_watcher, daemon=True)
    watcher.start()

    transcript_log: List[Dict[str, str]] = []
    seen_lines: set = set()

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        emit("ERROR", {"meeting_id": meeting_id, "error": f"Playwright import failed: {exc}"})
        return

    try:
        with sync_playwright() as p:
            BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_PROFILE_DIR),
                headless=False,
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--disable-notifications",
                    "--mute-audio",
                ],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)

            emit(
                "STATUS",
                {
                    "status": "setup" if setup_only else "in_meeting",
                    "meeting_id": meeting_id,
                    "title": title,
                    "url": url,
                },
            )

            if not setup_only:
                if "meet.google.com" in url:
                    _mute_and_join_google_meet(page)
                elif "teams.microsoft.com" in url or "teams.live.com" in url:
                    _mute_and_join_teams(page)

            while not _command_state["leave_requested"]:
                if page.is_closed():
                    break
                if not setup_only:
                    _scrape_live_captions(page, transcript_log, seen_lines)
                time.sleep(1.5)

            try:
                context.close()
            except Exception:
                pass

        emit(
            "FINISHED",
            {
                "meeting_id": meeting_id,
                "title": title,
                "url": url,
                "setup_only": setup_only,
                "transcript": transcript_log,
            },
        )
    except Exception as exc:
        emit(
            "ERROR",
            {
                "meeting_id": meeting_id,
                "title": title,
                "error": str(exc),
                "trace": traceback.format_exc(),
                "transcript": transcript_log,
            },
        )


if __name__ == "__main__":
    first_line = sys.stdin.readline()
    cfg = json.loads(first_line) if first_line.strip() else {}
    run_meeting_session(cfg)
