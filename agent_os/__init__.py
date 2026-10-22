"""
Autonomous Agent OS Package for JARVIS 2.0
Provides 3-Tier OS interaction:
- Tier 1: Dynamic Python & Shell Code Synthesizer (code_executor)
- Tier 2: Model Context Protocol Client Hub (integrations.mcp_client)
- Tier 3: Set-of-Mark Vision & Accessibility GUI Agent (state_machine, som_vision, ui_distiller, os_actuator)
Protected by the Safety Interceptor gatekeeper.
"""

from .safety_interceptor import SafetyInterceptor, safety_interceptor
from .code_executor import CodeExecutor, code_executor
from .ui_distiller import UIDistiller, ui_distiller
from .som_vision import SOMVision, som_vision
from .os_actuator import OSActuator, os_actuator
from .state_machine import OSAgentStateMachine, os_agent

__all__ = [
    "SafetyInterceptor",
    "safety_interceptor",
    "CodeExecutor",
    "code_executor",
    "UIDistiller",
    "ui_distiller",
    "SOMVision",
    "som_vision",
    "OSActuator",
    "os_actuator",
    "OSAgentStateMachine",
    "os_agent",
]
