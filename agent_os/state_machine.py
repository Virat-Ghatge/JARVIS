#!/usr/bin/env python3
"""
Tier 3 — Autonomous OS Vision & Accessibility GUI Agent for JARVIS 2.0
Executes the Observe -> Think -> Act -> Verify loop using Multimodal Vision LLMs,
Set-of-Mark visual grounding, accessibility tree controls, and OS actuation.
"""

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from agent_os.os_actuator import os_actuator
from agent_os.som_vision import som_vision
from agent_os.ui_distiller import ui_distiller
from core.adapters.base import ChatMessage
from core.llm_router import router


class OSAgentStateMachine:
    """
    Tier-3 Autonomous Visual Operating System Agent.
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
        """Broadcast AGENT_STEP event to HUD."""
        payload = {
            "step": step,
            "tier": "vision_gui",
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
                print(f"[OSAgent] Step listener error: {e}")

    def abort(self) -> None:
        """Immediately halt the running state machine."""
        os_actuator.abort()

    def run_task(self, task_description: str, max_steps: int = 10) -> Dict[str, Any]:
        """
        Executes the iterative Observe -> Think -> Act -> Verify autonomous loop.
        """
        os_actuator.reset_abort()
        print(f"\n[OSAgent] Commencing Tier-3 GUI autonomous task: '{task_description}'")

        history: List[str] = []

        for step_num in range(1, max_steps + 1):
            # Check for kill-switch
            if os_actuator.is_aborted():
                self._emit_step(
                    step=step_num,
                    thought="Autonomous execution halted by user abort / [ESC] kill-switch.",
                    action="abort",
                    status="aborted",
                    output="Emergency abort triggered.",
                )
                return {"ok": False, "summary": "Task aborted by user, sir.", "steps": step_num}

            # 1. OBSERVE: Distill active UI controls & capture SoM screenshot
            elements = ui_distiller.get_interactive_elements(max_elements=30)
            img, screenshot_b64 = som_vision.capture_and_annotate(elements)

            elements_summary = [
                f"[{el['id']}] {el['type']} '{el['name']}' at ({el['center'][0]}, {el['center'][1]})"
                for el in elements[:15]
            ]
            elements_text = "\n".join(elements_summary)

            self._emit_step(
                step=step_num,
                thought=f"Observing screen (Step {step_num}/{max_steps}). Found {len(elements)} interactive elements.",
                action="observe",
                status="running",
                screenshot_b64=screenshot_b64,
            )

            # 2. THINK: Vision LLM reasons over SoM screenshot and element coordinates
            system_prompt = (
                "You are JARVIS Tier-3 OS Vision Agent operating desktop applications visually like a human.\n"
                "You receive an image of the desktop screen with numbered Set-of-Mark cyan boxes [ID] and a list of elements.\n"
                "Return a JSON object in this exact schema:\n"
                "{\n"
                '  "thought": "<brief analysis of the active window and what to do next>",\n'
                '  "action": "click" | "double_click" | "type" | "hotkey" | "scroll" | "done",\n'
                '  "target_id": <int or null>,\n'
                '  "x": <int or null>,\n'
                '  "y": <int or null>,\n'
                '  "text": <string or null>,\n'
                '  "keys": <string or null>,\n'
                '  "done": <boolean>\n'
                "}\n"
            )

            user_prompt = (
                f"Goal: {task_description}\n"
                f"Current Step: {step_num} of {max_steps}\n"
                f"Previous steps: {'; '.join(history[-3:]) if history else 'None'}\n"
                f"Visible UI Elements:\n{elements_text}\n"
                "Analyze the screen and output your next action JSON."
            )

            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt, image_b64=screenshot_b64),
            ]

            resp = router.dispatch_role("vision_agent", messages, json_mode=True)
            plan = resp.raw_json or {}

            thought = plan.get("thought", f"Proceeding with step {step_num}")
            action_name = plan.get("action", "click")
            is_done = bool(plan.get("done", False))

            history.append(f"Step {step_num}: {thought} -> {action_name}")

            # Check abort before acting
            if os_actuator.is_aborted():
                self._emit_step(
                    step=step_num,
                    thought="Execution aborted by user.",
                    action="abort",
                    status="aborted",
                    screenshot_b64=screenshot_b64,
                )
                return {"ok": False, "summary": "Task aborted by user, sir.", "steps": step_num}

            # 3. ACT: Execute the planned action
            act_output = ""
            target_id = plan.get("target_id")
            x = plan.get("x")
            y = plan.get("y")

            # Resolve coordinates from target_id if not explicitly provided
            if target_id is not None and (x is None or y is None):
                for el in elements:
                    if el.get("id") == target_id:
                        x, y = el["center"][0], el["center"][1]
                        break

            if action_name == "click" and x is not None and y is not None:
                os_actuator.click(x, y)
                act_output = f"Clicked at ({x}, {y})"
            elif action_name == "double_click" and x is not None and y is not None:
                os_actuator.double_click(x, y)
                act_output = f"Double-clicked at ({x}, {y})"
            elif action_name == "type" and plan.get("text"):
                if x is not None and y is not None:
                    os_actuator.click(x, y)
                    time.sleep(0.1)
                text_to_type = plan.get("text", "")
                os_actuator.type_text(text_to_type)
                act_output = f"Typed: '{text_to_type}'"
            elif action_name == "hotkey" and plan.get("keys"):
                hotkey_str = plan.get("keys", "")
                os_actuator.press_hotkey(hotkey_str)
                act_output = f"Pressed hotkey: {hotkey_str}"
            elif action_name == "scroll":
                amount = int(plan.get("y", -300) or -300)
                os_actuator.scroll(amount)
                act_output = f"Scrolled {amount}"
            elif is_done or action_name == "done":
                self._emit_step(
                    step=step_num,
                    thought=thought,
                    action="finish",
                    status="done",
                    output="Task successfully completed.",
                    screenshot_b64=screenshot_b64,
                )
                return {
                    "ok": True,
                    "summary": thought or "Task completed successfully, sir.",
                    "steps": step_num,
                }

            self._emit_step(
                step=step_num,
                thought=thought,
                action=action_name,
                status="running",
                output=act_output,
                screenshot_b64=screenshot_b64,
            )

            # 4. VERIFY: Pause briefly for GUI response
            time.sleep(0.6)

        return {
            "ok": True,
            "summary": f"Completed {max_steps} visual automation steps for: '{task_description}'",
            "steps": max_steps,
        }


# Global OS agent state machine singleton
os_agent = OSAgentStateMachine()
