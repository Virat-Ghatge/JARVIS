import sys
import json
import time
import threading
import subprocess
from datetime import datetime
from typing import Callable, Dict, Any, List, Optional

from config.settings import BASE_DIR, SUMMARIES_PATH, ensure_json_file


class MeetingBot:
    """
    Subprocess-isolated Meeting Bot supervisor.
    Launches `automation.meeting_worker` in its own Python process so sync_playwright
    greenlets never collide with FastAPI/uvicorn or freeze the main process.
    """

    def __init__(self, llm_router: Optional[Any] = None, voice_listener: Optional[Any] = None):
        self.llm_router = llm_router
        self.voice_listener = voice_listener
        self._state_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._current_state: Dict[str, Any] = {
            "status": "idle",
            "meeting_id": None,
            "title": None,
            "url": None,
            "captions": [],
            "mic_auto_muted": False,
        }
        ensure_json_file(SUMMARIES_PATH, [])

    def register_state_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback not in self._state_listeners:
            self._state_listeners.append(callback)

    def _broadcast_state(self) -> None:
        snapshot = dict(self._current_state)
        for cb in list(self._state_listeners):
            try:
                cb(snapshot)
            except Exception:
                pass

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._current_state)

    def open_login_setup(self, url: str = "https://accounts.google.com") -> Dict[str, Any]:
        return self.join_meeting(
            url=url,
            meeting_id="browser_profile_setup",
            title="Browser Profile Login Setup",
            setup_only=True,
        )

    def join_meeting(
        self,
        url: str,
        meeting_id: Optional[str] = None,
        title: str = "Instant Meeting",
        setup_only: bool = False,
    ) -> Dict[str, Any]:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return {"status": "busy", "message": "Meeting bot is already active.", "state": self.get_state()}

            mid = meeting_id or f"mtg_{int(time.time())}"

            # Auto-mute JARVIS listening microphone on meeting join while still allowing manual user unmute
            auto_muted = False
            if not setup_only and self.voice_listener is not None:
                try:
                    if hasattr(self.voice_listener, "enter_meeting_auto_mute"):
                        self.voice_listener.enter_meeting_auto_mute()
                    elif hasattr(self.voice_listener, "set_mic_active"):
                        self.voice_listener.set_mic_active(False)
                    auto_muted = True
                except Exception:
                    pass

            self._current_state = {
                "status": "joining",
                "meeting_id": mid,
                "title": title,
                "url": url,
                "captions": [],
                "mic_auto_muted": auto_muted,
            }
            self._broadcast_state()

            proc = subprocess.Popen(
                [sys.executable, "-m", "automation.meeting_worker"],
                cwd=str(BASE_DIR),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            self._proc = proc

            assert proc.stdin is not None
            proc.stdin.write(
                json.dumps(
                    {
                        "url": url,
                        "meeting_id": mid,
                        "title": title,
                        "setup_only": setup_only,
                    }
                )
                + "\n"
            )
            proc.stdin.flush()

            monitor = threading.Thread(target=self._monitor_worker, args=(proc,), daemon=True)
            monitor.start()

            return {"status": "started", "meeting_id": mid, "state": self.get_state()}

    def leave_meeting(self) -> Dict[str, Any]:
        with self._lock:
            proc = self._proc
            if not proc or proc.poll() is None is False:
                self._current_state["status"] = "idle"
                self._broadcast_state()
                return {"status": "idle", "message": "No active meeting session."}

            try:
                if proc.stdin:
                    proc.stdin.write(json.dumps({"command": "leave"}) + "\n")
                    proc.stdin.flush()
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass

        return {"status": "leaving", "state": self.get_state()}

    def _monitor_worker(self, proc: subprocess.Popen) -> None:
        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue

                ev = msg.get("event")
                payload = msg.get("payload", {})

                if ev == "STATUS":
                    with self._lock:
                        self._current_state["status"] = payload.get("status", "in_meeting")
                        self._broadcast_state()
                elif ev == "CAPTION":
                    with self._lock:
                        caps = self._current_state.get("captions", [])
                        caps.append(payload)
                        self._current_state["captions"] = caps[-100:]
                        self._broadcast_state()
                elif ev == "FINISHED":
                    self._handle_post_call(payload)
                elif ev == "ERROR":
                    with self._lock:
                        self._current_state["status"] = "error"
                        self._current_state["error"] = payload.get("error", "Unknown meeting worker error")
                        self._broadcast_state()
        finally:
            with self._lock:
                if self._proc is proc:
                    self._proc = None
                self._current_state["status"] = "idle"
                self._current_state["mic_auto_muted"] = False
                self._broadcast_state()

    def _handle_post_call(self, payload: Dict[str, Any]) -> None:
        if payload.get("setup_only"):
            return

        transcript_items = payload.get("transcript", [])
        full_text = "\n".join(f"[{c.get('timestamp', '')}] {c.get('text', '')}" for c in transcript_items)
        summary_text = "No live captions were captured during this session."

        if full_text.strip() and self.llm_router is not None:
            try:
                prompt = (
                    "Summarize the following meeting transcript with:\n"
                    "1. Executive Summary\n2. Key Decisions\n3. Action Items\n\n"
                    f"Transcript:\n{full_text[:12000]}"
                )
                summary_text = self.llm_router.generate(role="meeting_summarizer", prompt=prompt)
            except Exception as exc:
                summary_text = f"Automated summary generation failed: {exc}"

        record = {
            "id": f"sum_{int(time.time())}",
            "meeting_id": payload.get("meeting_id"),
            "title": payload.get("title", "Meeting"),
            "url": payload.get("url", ""),
            "ended_at": datetime.now().isoformat(),
            "captions_count": len(transcript_items),
            "summary": summary_text,
            "transcript": transcript_items,
        }

        try:
            with open(SUMMARIES_PATH, "r", encoding="utf-8") as f:
                summaries = json.load(f)
        except Exception:
            summaries = []

        summaries.insert(0, record)
        with open(SUMMARIES_PATH, "w", encoding="utf-8") as f:
            json.dump(summaries[:100], f, indent=2)

    def list_summaries(self) -> List[Dict[str, Any]]:
        try:
            with open(SUMMARIES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
