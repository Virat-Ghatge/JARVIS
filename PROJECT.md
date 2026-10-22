# PROJECT: JARVIS 2.0 — Autonomous 3-Tier OS Agent, Multi-Provider API Vault & Holographic Desktop HUD

## Overview
JARVIS 2.0 is an autonomous desktop AI operating system and hybrid voice/text assistant. It combines local deterministic capabilities with dynamic multi-tier autonomy, resilient multi-key LLM routing, and a Marvel-inspired Holographic Desktop HUD (without copyrighted logos) packaged via PyWebView and FastAPI WebSockets.

## Architecture Highlights
- **Unified InputGateway**: Text + Voice command processing with independent microphone listening and TTS speech toggles.
- **Dynamic Multi-Key API Vault**: Multi-key rotation on 429/quota limits, custom OpenAI-compatible endpoints (Ollama, LM Studio, vLLM, DeepSeek, custom proxies), live token telemetry, and role-based model assignment.
- **3-Tier Dynamic OS Operation**:
  - *Tier 1*: Dynamic Python & Shell Code Synthesizer (`agent_os/code_executor.py`).
  - *Tier 2*: Model Context Protocol (MCP) Client Hub (`integrations/mcp_client.py`).
  - *Tier 3*: Set-of-Mark (SoM) Vision & Accessibility GUI Agent (`agent_os/state_machine.py`, `ui_distiller.py`, `som_vision.py`, `os_actuator.py`) with instant `[ESC]` hardware kill-switch.
- **High-Impact Assistant Modules**:
  - Safety Interceptor & Approval Modal (`agent_os/safety_interceptor.py`).
  - Smart Meeting Attendant 2.0 with DOM caption scraping & post-meeting LLM summaries (`automation/meeting_bot.py`).
  - Autonomous Web Researcher (`automation/web_agent.py`).
  - Universal Clipboard & Selection Copilot (`integrations/handlers/clipboard_copilot.py`).
  - Skills, Macros & Teach Mode (`integrations/skill_store.py`).
  - Contextual Workspace RAG (`integrations/workspace_rag.py`).
- **Frameless Holographic Desktop HUD**:
  - React + Vite + Tailwind CSS + Lucide-React frontend.
  - PyWebView frameless window with Ghost Mini-HUD mode and browser fallback.
  - Programmatic geometric Arc-Cyan HUD desktop icon generator (`scripts/create_desktop_icon.py`).
