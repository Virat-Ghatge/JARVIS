import sys
import json
import time
import traceback
from typing import Dict, Any

from agent_os.os_actuator import OSActuator
from agent_os.ui_distiller import UIDistiller
from agent_os.som_vision import SoMVision
from core.llm_router import LLMRouter
from core.adapters.base import extract_json_from_text


def emit_event(event_type: str, payload: Dict[str, Any]) -> None:
    line = json.dumps({"event": event_type, "payload": payload}, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def run_worker_loop(goal: str, max_steps: int = 8) -> None:
    router = LLMRouter()
    distiller = UIDistiller()
    som = SoMVision()
    actuator = OSActuator(
        on_abort_callback=lambda: emit_event(
            "AGENT_STEP",
            {
                "tier": "TIER_3_VISION",
                "phase": "ABORTED",
                "message": "Emergency [ESC] kill-switch pressed by user.",
                "timestamp": time.time(),
            },
        )
    )

    actuator.start_esc_guard()
    try:
        emit_event(
            "AGENT_STEP",
            {
                "tier": "TIER_3_VISION",
                "phase": "OBSERVE",
                "message": f"Starting isolated OS Agent worker for goal: {goal}",
                "timestamp": time.time(),
            },
        )

        history = []
        for step_idx in range(1, max_steps + 1):
            if actuator.is_aborted:
                emit_event("RESULT", {"status": "aborted", "summary": "Task aborted via [ESC]."})
                return

            ui_elements = distiller.extract_interactive_elements()
            som_snapshot = som.capture_and_annotate(ui_elements)

            emit_event(
                "AGENT_STEP",
                {
                    "tier": "TIER_3_VISION",
                    "phase": "THINK",
                    "step": step_idx,
                    "elements_count": len(ui_elements),
                    "screenshot_b64": som_snapshot.get("image_b64", ""),
                    "message": f"Step {step_idx}: Distilled {len(ui_elements)} interactive UI elements.",
                    "timestamp": time.time(),
                },
            )

            prompt = (
                f"You are the JARVIS Tier 3 OS GUI Agent.\n"
                f"User Goal: {goal}\n"
                f"Current Step: {step_idx}/{max_steps}\n"
                f"Previous Steps: {json.dumps(history[-4:])}\n"
                f"Visible UI Elements (Set-of-Mark IDs with center coordinates):\n"
                f"{json.dumps(ui_elements[:60], ensure_ascii=False)}\n\n"
                "Respond ONLY with a valid JSON object matching one of:\n"
                '{"action": "click", "x": 120, "y": 340, "reason": "..."}\n'
                '{"action": "type", "x": 120, "y": 340, "text": "...", "press_enter": true, "reason": "..."}\n'
                '{"action": "hotkey", "keys": ["ctrl", "l"], "reason": "..."}\n'
                '{"action": "wait", "seconds": 1.5, "reason": "..."}\n'
                '{"action": "done", "reason": "Goal completed"}'
            )

            raw_reply = router.generate(
                role="vision_agent",
                prompt=prompt,
                image_b64=som_snapshot.get("image_b64"),
            )
            decision = extract_json_from_text(raw_reply) or {"action": "done", "reason": str(raw_reply)}

            if str(decision.get("action", "")).lower() in ("done", "complete", "finish"):
                emit_event(
                    "AGENT_STEP",
                    {
                        "tier": "TIER_3_VISION",
                        "phase": "VERIFY",
                        "step": step_idx,
                        "message": decision.get("reason", "OS Agent task complete."),
                        "timestamp": time.time(),
                    },
                )
                emit_event(
                    "RESULT",
                    {"status": "completed", "summary": decision.get("reason", "Task completed.")},
                )
                return

            emit_event(
                "AGENT_STEP",
                {
                    "tier": "TIER_3_VISION",
                    "phase": "ACT",
                    "step": step_idx,
                    "action": decision,
                    "message": decision.get("reason", f"Executing {decision.get('action')}"),
                    "timestamp": time.time(),
                },
            )

            outcome = actuator.execute_action(decision)
            history.append({"step": step_idx, "decision": decision, "outcome": outcome})
            time.sleep(0.45)

        emit_event(
            "RESULT",
            {"status": "max_steps", "summary": f"Reached maximum steps ({max_steps}) for goal: {goal}"},
        )
    except Exception as exc:
        emit_event(
            "RESULT",
            {
                "status": "error",
                "summary": f"OS Agent worker failed: {exc}",
                "trace": traceback.format_exc(),
            },
        )
    finally:
        actuator.stop_esc_guard()


if __name__ == "__main__":
    raw_in = sys.stdin.readline()
    params = json.loads(raw_in) if raw_in.strip() else {}
    run_worker_loop(
        goal=params.get("goal", ""),
        max_steps=int(params.get("max_steps", 8)),
    )
