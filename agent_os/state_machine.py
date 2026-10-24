import sys
import json
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent


class OSAgentStateMachine:
    """
     Tier 3 OS Agent Supervisor.
    Spawns `agent_os/worker_proc.py` in a child Python process so COM/UIA/mss/pynput
    never block the FastAPI asyncio loop or share the main process GIL.
    """

    def __init__(self, safety_interceptor: Optional[Any] = None):
        self.safety_interceptor = safety_interceptor
        self._step_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._active_proc: Optional[subprocess.Popen] = None
        self._proc_lock = threading.Lock()

    def register_step_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback not in self._step_listeners:
            self._step_listeners.append(callback)

    def _emit_step(self, payload: Dict[str, Any]) -> None:
        for cb in list(self._step_listeners):
            try:
                cb(payload)
            except Exception:
                pass

    def abort_current_task(self) -> bool:
        with self._proc_lock:
            if self._active_proc and self._active_proc.poll() is None:
                try:
                    self._active_proc.terminate()
                    self._active_proc.wait(timeout=2.0)
                except Exception:
                    try:
                        self._active_proc.kill()
                    except Exception:
                        pass
                self._active_proc = None
                self._emit_step(
                    {
                        "tier": "TIER_3_VISION",
                        "phase": "ABORTED",
                        "message": "OS Agent subprocess terminated by user abort.",
                    }
                )
                return True
        return False

    def execute_goal(self, goal: str, max_steps: int = 8) -> Dict[str, Any]:
        if self.safety_interceptor is not None:
            approved, reason = self.safety_interceptor.check_and_request_approval(
                tier="TIER_3_VISION", command_desc=goal
            )
            if not approved:
                msg = f"Action blocked by Safety Interceptor: {reason}"
                self._emit_step({"tier": "TIER_3_VISION", "phase": "BLOCKED", "message": msg})
                return {"status": "blocked", "summary": msg}

        self.abort_current_task()

        cmd = [sys.executable, "-m", "agent_os.worker_proc"]
        final_result: Dict[str, Any] = {"status": "completed", "summary": "OS Agent task finished."}

        with self._proc_lock:
            self._active_proc = subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            proc = self._active_proc

        try:
            assert proc.stdin is not None
            assert proc.stdout is not None
            proc.stdin.write(json.dumps({"goal": goal, "max_steps": max_steps}) + "\n")
            proc.stdin.flush()
            proc.stdin.close()

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
                if ev == "AGENT_STEP":
                    self._emit_step(payload)
                elif ev == "RESULT":
                    final_result = payload

            proc.wait(timeout=5.0)
        except Exception as exc:
            final_result = {"status": "error", "summary": f"OS Agent supervisor error: {exc}"}
        finally:
            with self._proc_lock:
                if self._active_proc is proc:
                    self._active_proc = None

        return final_result
