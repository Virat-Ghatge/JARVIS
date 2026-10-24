import sys
import json
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Dict, Any, Optional

from agent_os.os_actuator import os_actuator
from agent_os.safety_interceptor import safety_interceptor as default_safety_interceptor

BASE_DIR = Path(__file__).resolve().parent.parent


class OSAgentStateMachine:
    """
    Tier 3 OS Agent Supervisor.
    Spawns `agent_os/worker_proc.py` in a child Python process so COM/UIA/mss/pynput
    never block the FastAPI asyncio loop or share the main process GIL.
    """

    def __init__(
        self,
        safety_interceptor: Optional[Any] = None,
        actuator: Optional[Any] = None,
        distiller: Optional[Any] = None,
        som_vision: Optional[Any] = None,
        llm_router: Optional[Any] = None,
        max_steps: int = 8,
    ):
        self.safety_interceptor = safety_interceptor or default_safety_interceptor
        self.actuator = actuator or os_actuator
        self.distiller = distiller
        self.som_vision = som_vision
        self.llm_router = llm_router
        self.max_steps = max_steps
        self._step_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._active_proc: Optional[subprocess.Popen] = None
        self._proc_lock = threading.Lock()
        self.running: bool = False
        self.state: str = "IDLE"

    def register_step_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback not in self._step_listeners:
            self._step_listeners.append(callback)

    def _emit_step(self, payload: Dict[str, Any]) -> None:
        if "phase" in payload:
            self.state = str(payload["phase"])
        for cb in list(self._step_listeners):
            try:
                cb(payload)
            except Exception:
                pass

    def abort(self) -> bool:
        return self.abort_current_task()

    def abort_current_task(self) -> bool:
        self.actuator.trigger_abort()
        with self._proc_lock:
            self.running = False
            self.state = "ABORTED"
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

    def run(self, goal: str, max_steps: Optional[int] = None) -> Dict[str, Any]:
        return self.execute_goal(goal=goal, max_steps=max_steps or self.max_steps)

    def run_goal(self, goal: str, max_steps: Optional[int] = None) -> Dict[str, Any]:
        return self.execute_goal(goal=goal, max_steps=max_steps or self.max_steps)

    def execute_task(self, goal: str, max_steps: Optional[int] = None) -> Dict[str, Any]:
        return self.execute_goal(goal=goal, max_steps=max_steps or self.max_steps)

    def execute_goal(self, goal: str, max_steps: int = 8) -> Dict[str, Any]:
        if self.actuator.is_aborted:
            self.state = "ABORTED"
            return {"status": "aborted", "success": False, "summary": "Aborted by kill-switch."}

        if self.safety_interceptor is not None:
            if hasattr(self.safety_interceptor, "check_and_request_approval"):
                approved, reason = self.safety_interceptor.check_and_request_approval(
                    tier="TIER_3_VISION", command_desc=goal
                )
                if not approved:
                    msg = f"Action blocked by Safety Interceptor: {reason}"
                    self._emit_step({"tier": "TIER_3_VISION", "phase": "BLOCKED", "message": msg})
                    return {"status": "blocked", "success": False, "summary": msg}
            elif hasattr(self.safety_interceptor, "evaluate_command"):
                check = self.safety_interceptor.evaluate_command(goal, tier="TIER_3_VISION")
                if isinstance(check, dict) and check.get("blocked"):
                    msg = f"Action blocked by Safety Interceptor: {check.get('reason', 'Restricted')}"
                    self._emit_step({"tier": "TIER_3_VISION", "phase": "BLOCKED", "message": msg})
                    return {"status": "blocked", "success": False, "summary": msg}

        self.abort_current_task()
        self.actuator.reset_abort()

        cmd = [sys.executable, "-m", "agent_os.worker_proc"]
        final_result: Dict[str, Any] = {
            "status": "completed",
            "success": True,
            "summary": "OS Agent task finished.",
        }

        with self._proc_lock:
            self.running = True
            self.state = "OBSERVE"
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
                    final_result.setdefault("success", final_result.get("status") == "completed")

            proc.wait(timeout=5.0)
        except Exception as exc:
            final_result = {"status": "error", "success": False, "summary": f"OS Agent supervisor error: {exc}"}
        finally:
            with self._proc_lock:
                self.running = False
                if self.state != "ABORTED":
                    self.state = "IDLE"
                if self._active_proc is proc:
                    self._active_proc = None

        return final_result


OSStateMachine = OSAgentStateMachine
os_agent = OSAgentStateMachine()
