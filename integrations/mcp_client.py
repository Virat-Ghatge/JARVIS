#!/usr/bin/env python3
"""
Tier 2 — Model Context Protocol (MCP) Client Hub for JARVIS 2.0
Connects to configured MCP servers from config/mcp_servers.json.
Dynamically discovers external tools (tools/list) and executes them (tools/call).
"""

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from config.settings import MCP_SERVERS_FILE


class MCPClientHub:
    """
    Tier-2 Autonomous OS Agent: MCP Client Hub.
    Manages external tool integrations defined in config/mcp_servers.json.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._servers: Dict[str, Dict[str, Any]] = {}
        self._tools: Dict[str, Dict[str, Any]] = {}
        self.reload_servers()

    def reload_servers(self) -> Dict[str, Any]:
        """Loads or reloads server configurations from config/mcp_servers.json."""
        with self._lock:
            if not MCP_SERVERS_FILE.exists():
                return {}
            try:
                data = json.loads(MCP_SERVERS_FILE.read_text(encoding="utf-8"))
                self._servers = data.get("mcpServers", {})
            except Exception as e:
                print(f"[MCPClient] Error reading {MCP_SERVERS_FILE}: {e}")
                self._servers = {}
            return dict(self._servers)

    def get_servers(self) -> Dict[str, Dict[str, Any]]:
        """Return configured MCP servers."""
        with self._lock:
            return dict(self._servers)

    def add_server(self, name: str, server_config: Dict[str, Any]) -> bool:
        """Add or update an MCP server configuration."""
        with self._lock:
            self._servers[name] = server_config
            try:
                data = {"mcpServers": self._servers}
                MCP_SERVERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return True
            except Exception as e:
                print(f"[MCPClient] Error saving server: {e}")
                return False

    def remove_server(self, name: str) -> bool:
        """Remove an MCP server configuration."""
        with self._lock:
            if name in self._servers:
                del self._servers[name]
                try:
                    data = {"mcpServers": self._servers}
                    MCP_SERVERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    return True
                except Exception:
                    return False
        return False

    def list_tools(self, server_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Discovers tools available across configured MCP servers.
        Returns a list of tools with name, description, and input schema.
        """
        with self._lock:
            servers_to_query = (
                {server_name: self._servers[server_name]}
                if server_name and server_name in self._servers
                else self._servers
            )

        discovered: List[Dict[str, Any]] = []

        for s_name, s_conf in servers_to_query.items():
            if s_conf.get("disabled", False):
                continue

            # If HTTP / SSE server
            if "url" in s_conf:
                try:
                    resp = requests.post(
                        f"{s_conf['url']}/tools/list",
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        tools_data = resp.json().get("result", {}).get("tools", [])
                        for t in tools_data:
                            t["server"] = s_name
                            discovered.append(t)
                except Exception:
                    pass

            # Stdio / local CLI tools
            elif "command" in s_conf:
                # Registered standard filesystem / shell tools
                cmd = s_conf.get("command", "")
                args = s_conf.get("args", [])
                discovered.append({
                    "name": f"{s_name}_execute",
                    "server": s_name,
                    "description": f"Executes operations on {s_name} ({cmd} {' '.join(args)})",
                    "inputSchema": {"type": "object", "properties": {"action": {"type": "string"}}},
                })

        return discovered

    def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes an MCP tool call on the specified server.
        """
        with self._lock:
            s_conf = self._servers.get(server_name)

        if not s_conf:
            return {"ok": False, "error": f"Server '{server_name}' not configured"}

        if "url" in s_conf:
            try:
                resp = requests.post(
                    f"{s_conf['url']}/tools/call",
                    json={
                        "jsonrpc": "2.0",
                        "id": int(time.time()),
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": arguments},
                    },
                    timeout=30,
                )
                if resp.status_code == 200:
                    result = resp.json().get("result", {})
                    return {"ok": True, "result": result}
                return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        elif "command" in s_conf:
            # Stdio tool execution
            cmd = s_conf.get("command", "")
            args = s_conf.get("args", [])
            full_cmd = [cmd] + args
            try:
                proc = subprocess.run(
                    full_cmd,
                    input=json.dumps({"tool": tool_name, "arguments": arguments}),
                    text=True,
                    capture_output=True,
                    timeout=30,
                    shell=(os.name == "nt"),
                )
                return {"ok": proc.returncode == 0, "output": proc.stdout or proc.stderr}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        return {"ok": False, "error": "Unknown server transport type"}


# Global MCP hub singleton
mcp_client = MCPClientHub()
