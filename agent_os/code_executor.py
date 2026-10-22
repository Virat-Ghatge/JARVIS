#!/usr/bin/env python3
"""
Tier 1 — Dynamic Code & Shell Synthesizer for JARVIS 2.0
Synthesizes self-contained Python and shell scripts on the fly for file management,
data processing, PDF tasks, media conversions, and OS diagnostics.
Executes scripts inside isolated subprocesses with timeout protection and safety checks.
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from agent_os.safety_interceptor import safety_interceptor
from core.llm_router import router


class CodeExecutor:
    """
    Tier-1 Autonomous OS Agent: Code Synthesizer and Subprocess Runner.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._step_listeners: List[Callable[[Dict[str, Any]], None]] = []

    def register_step_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for AGENT_STEP events."""
        with self._lock:
            if callback not in self._step_listeners:
                self._step_listeners.append(callback)

    def _emit_step(
        self,
        step: int,
        thought: str,
        action: str,
        status: str = "running",
        output: str = "",
        screenshot_b64: str = "",
    ) -> None:
        """Broadcast AGENT_STEP event to frontend."""
        payload = {
            "step": step,
            "tier": "code",
            "thought": thought,
            "action": action,
            "status": status,
            "screenshot_b64": screenshot_b64,
            "output": output,
        }
        with self._lock:
            listeners = list(self._step_listeners)
        for cb in listeners:
            try:
                cb(payload)
            except Exception as e:
                print(f"[CodeExecutor] Step listener error: {e}")

    def synthesize_script(self, task_description: str) -> str:
        """
        Prompts the LLM to write a clean, self-contained Python script to accomplish the task.
        """
        system_prompt = (
            "You are an expert Python OS automation engineer for JARVIS.\n"
            "Write a single, self-contained, robust Python 3 script to accomplish the user's task.\n"
            "Rules:\n"
            "1. Output ONLY executable Python code inside a ```python ``` block. No conversational filler.\n"
            "2. Use standard libraries (os, sys, pathlib, json, shutil, subprocess, math, re, csv, etc.) or popular libraries.\n"
            "3. Print meaningful output to stdout so the user can understand the results.\n"
            "4. Handle errors cleanly with try/except.\n"
        )
        prompt = f"User Request: {task_description}"
        raw = router.query_text("intent_router", prompt, system_prompt=system_prompt)

        # Extract code from markdown block
        code = raw.strip()
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()

        return code

    def execute_task(self, task_description: str, timeout_sec: int = 30) -> Dict[str, Any]:
        """
        Full Tier-1 Pipeline:
        1. Synthesize script from user description.
        2. Pass code through SafetyInterceptor.
        3. Execute script in subprocess with timeout.
        4. Capture stdout/stderr and return structured result.
        """
        self._emit_step(
            step=1,
            thought=f"Synthesizing Python automation script for: '{task_description}'",
            action="synthesize_code",
            status="running",
        )

        code = self.synthesize_script(task_description)
        if not code:
            self._emit_step(
                step=1,
                thought="Failed to synthesize script",
                action="synthesize_code",
                status="error",
                output="LLM returned empty code.",
            )
            return {"ok": False, "summary": "Failed to synthesize script for task.", "output": ""}

        # Safety Check
        is_safe, risk_reason = safety_interceptor.inspect_code(code)
        if not is_safe:
            self._emit_step(
                step=2,
                thought=f"Safety warning: {risk_reason}. Requesting user confirmation.",
                action="safety_intercept",
                status="running",
                output=code,
            )
            approved = safety_interceptor.request_approval(
                action_type="python_code_execution",
                description=f"{risk_reason} in synthesized task: '{task_description}'",
                preview=code[:400] + ("..." if len(code) > 400 else ""),
                timeout_sec=15,
            )
            if not approved:
                self._emit_step(
                    step=2,
                    thought="Operation was aborted by safety gatekeeper or user denial.",
                    action="safety_intercept",
                    status="aborted",
                    output="Execution denied by user safety policy.",
                )
                return {
                    "ok": False,
                    "summary": "Execution was denied by safety policy, sir.",
                    "output": "Aborted by user.",
                }

        self._emit_step(
            step=2,
            thought="Code verified safe. Launching runner subprocess.",
            action="execute_subprocess",
            status="running",
            output=code,
        )

        # Write to temporary file and execute
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as f:
            f.write(code)
            tmp_path = f.name

        try:
            start_t = time.time()
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            duration_ms = int((time.time() - start_t) * 1000)

            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()
            returncode = proc.returncode

            combined_output = stdout
            if stderr:
                combined_output = f"{combined_output}\n[STDERR]: {stderr}".strip()

            if returncode == 0:
                summary = stdout or "Script executed successfully with zero errors."
                self._emit_step(
                    step=3,
                    thought="Script completed successfully.",
                    action="finish",
                    status="done",
                    output=combined_output,
                )
                return {
                    "ok": True,
                    "summary": summary,
                    "output": combined_output,
                    "duration_ms": duration_ms,
                    "code": code,
                }
            else:
                summary = f"Script returned exit code {returncode}."
                self._emit_step(
                    step=3,
                    thought=f"Script failed with exit code {returncode}.",
                    action="finish",
                    status="error",
                    output=combined_output,
                )
                return {
                    "ok": False,
                    "summary": f"{summary} Details: {stderr or stdout}",
                    "output": combined_output,
                    "duration_ms": duration_ms,
                    "code": code,
                }

        except subprocess.TimeoutExpired:
            self._emit_step(
                step=3,
                thought=f"Script timed out after {timeout_sec}s.",
                action="finish",
                status="error",
                output=f"TimeoutExpired ({timeout_sec}s)",
            )
            return {
                "ok": False,
                "summary": f"Script execution timed out after {timeout_sec} seconds, sir.",
                "output": "TimeoutExpired",
            }
        except Exception as e:
            self._emit_step(
                step=3,
                thought=f"Subprocess runner exception: {e}",
                action="finish",
                status="error",
                output=str(e),
            )
            return {
                "ok": False,
                "summary": f"Subprocess runner error: {e}",
                "output": str(e),
            }
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass


# Global code executor singleton
code_executor = CodeExecutor()
