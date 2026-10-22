"""
Integrations package for JARVIS 2.0.
Provides MCP Client Hub, Skill Store, Workspace RAG, and Handlers.
"""

from .mcp_client import MCPClientHub, mcp_client
from .skill_store import SkillStore, skill_store
from .workspace_rag import WorkspaceRAG, workspace_rag
from .handlers.clipboard_copilot import ClipboardCopilot, clipboard_copilot

__all__ = [
    "MCPClientHub",
    "mcp_client",
    "SkillStore",
    "skill_store",
    "WorkspaceRAG",
    "workspace_rag",
    "ClipboardCopilot",
    "clipboard_copilot",
]
