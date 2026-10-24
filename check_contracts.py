import sys
import traceback

MODULES = [
    "config.settings",
    "core.adapters.base",
    "core.llm_router",
    "core.context_manager",
    "core.engine",
    "audio.tts_engine",
    "audio.voice_listener",
    "agent_os.safety_interceptor",
    "agent_os.code_executor",
    "agent_os.ui_distiller",
    "agent_os.som_vision",
    "agent_os.os_actuator",
    "agent_os.state_machine",
    "integrations.mcp_client",
    "integrations.skill_store",
    "integrations.workspace_rag",
    "automation.meeting_bot",
    "automation.meeting_scheduler",
    "automation.meeting_handler",
    "automation.web_agent",
    "automation.server",
]

failed = 0
for mod in MODULES:
    try:
        __import__(mod)
        print(f"[OK] {mod}")
    except Exception as exc:
        failed += 1
        print(f"[FAIL] {mod}: {exc}")
        traceback.print_exc()

sys.exit(1 if failed else 0)
