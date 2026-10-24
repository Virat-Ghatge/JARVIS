import os
import json
import socket
import time
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

VAULT_PATH = CONFIG_DIR / "api_vault.json"
MEETINGS_PATH = CONFIG_DIR / "meetings.json"
SUMMARIES_PATH = CONFIG_DIR / "meeting_summaries.json"
ALARMS_PATH = CONFIG_DIR / "alarms.json"
SKILLS_PATH = CONFIG_DIR / "skills.json"
MCP_PATH = CONFIG_DIR / "mcp_servers.json"
BROWSER_PROFILE_DIR = BASE_DIR / ".browser_profile"

DEFAULT_VAULT: Dict[str, Any] = {
    "providers": {
        "gemini": {"keys": [], "active_index": 0, "default_model": "gemini-2.5-flash"},
        "groq": {"keys": [], "active_index": 0, "default_model": "llama-3.3-70b-versatile"},
        "anthropic": {"keys": [], "active_index": 0, "default_model": "claude-3-5-sonnet-latest"},
        "openai": {"keys": [], "active_index": 0, "default_model": "gpt-4o-mini"}
    },
    "custom_endpoints": [
        {
            "id": "freellmapi_local",
            "name": "FREELLMAPI Local Server",
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key": "sk-local-free",
            "default_model": "default",
            "enabled": True,
            "min_request_interval_ms": 65
        }
    ],
    "role_mappings": {
        "chat": "custom:freellmapi_local",
        "router": "custom:freellmapi_local",
        "code_synth": "custom:freellmapi_local",
        "vision_agent": "gemini",
        "meeting_summarizer": "custom:freellmapi_local"
    }
}

_vault_lock = threading.RLock()
_net_cache = {"online": True, "last_checked": 0.0, "checking": False}


def ensure_json_file(path: Path, default_data: Any) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2)


def init_config_files() -> None:
    ensure_json_file(VAULT_PATH, DEFAULT_VAULT)
    ensure_json_file(MEETINGS_PATH, [])
    ensure_json_file(SUMMARIES_PATH, [])
    ensure_json_file(ALARMS_PATH, [])
    ensure_json_file(SKILLS_PATH, [])
    ensure_json_file(MCP_PATH, [])
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _seed_env_keys()


def _seed_env_keys() -> None:
    vault = load_vault()
    changed = False
    env_map = {
        "GEMINI_API_KEY": "gemini",
        "GROQ_API_KEY": "groq",
        "ANTHROPIC_API_KEY": "anthropic",
        "OPENAI_API_KEY": "openai",
    }
    for env_var, provider in env_map.items():
        val = os.environ.get(env_var, "").strip()
        if val and provider in vault.get("providers", {}):
            keys = vault["providers"][provider].get("keys", [])
            if not any(k.get("key") == val for k in keys):
                keys.append({
                    "id": f"env_{provider}_1",
                    "label": f"ENV {env_var}",
                    "key": val,
                    "status": "standby",
                    "calls": 0,
                    "errors": 0
                })
                vault["providers"][provider]["keys"] = keys
                changed = True
    if changed:
        save_vault(vault)


def load_vault() -> Dict[str, Any]:
    with _vault_lock:
        ensure_json_file(VAULT_PATH, DEFAULT_VAULT)
        try:
            with open(VAULT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULT_VAULT.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            return json.loads(json.dumps(DEFAULT_VAULT))


def save_vault(vault_data: Dict[str, Any]) -> Dict[str, Any]:
    with _vault_lock:
        with open(VAULT_PATH, "w", encoding="utf-8") as f:
            json.dump(vault_data, f, indent=2)
        return vault_data


def is_local_endpoint_url(url: str) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return (
        "127.0.0.1" in lowered
        or "localhost" in lowered
        or "0.0.0.0" in lowered
        or "192.168." in lowered
        or "10." in lowered
    )


def is_role_bound_to_local_endpoint(role: str = "chat") -> bool:
    vault = load_vault()
    target = vault.get("role_mappings", {}).get(role, "")
    if target.startswith("custom:"):
        ep_id = target.split(":", 1)[1]
        for ep in vault.get("custom_endpoints", []):
            if ep.get("id") == ep_id and ep.get("enabled", True):
                return is_local_endpoint_url(ep.get("base_url", ""))
    return False


def _refresh_internet_status_async() -> None:
    if _net_cache["checking"]:
        return
    _net_cache["checking"] = True

    def _probe():
        online = False
        for host in ("1.1.1.1", "8.8.8.8"):
            try:
                with socket.create_connection((host, 53), timeout=1.2):
                    online = True
                    break
            except OSError:
                continue
        _net_cache["online"] = online
        _net_cache["last_checked"] = time.time()
        _net_cache["checking"] = False

    t = threading.Thread(target=_probe, daemon=True)
    t.start()


def is_internet_connected(role: Optional[str] = None) -> bool:
    """
    Non-blocking connectivity check.
    Never blocks the FastAPI event loop and never marks local custom endpoints offline.
    """
    if role and is_role_bound_to_local_endpoint(role):
        return True

    now = time.time()
    if now - _net_cache["last_checked"] > 15.0:
        _refresh_internet_status_async()
    return bool(_net_cache["online"])
