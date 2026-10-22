#!/usr/bin/env python3
"""
Configuration and Environment Settings for JARVIS 2.0
Loads environment variables, manages persistent API Vault, and seeds credentials.
"""

import json
import os
import socket
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv

# Root Directory of the Project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from root
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)

# Directory & File Paths
CONFIG_DIR = BASE_DIR / "config"
API_VAULT_FILE = CONFIG_DIR / "api_vault.json"
MEETINGS_FILE = CONFIG_DIR / "meetings.json"
ALARMS_FILE = CONFIG_DIR / "alarms.json"
SKILLS_FILE = CONFIG_DIR / "skills.json"
MCP_SERVERS_FILE = CONFIG_DIR / "mcp_servers.json"
UI_DIR = BASE_DIR / "ui"
UI_DIST_DIR = UI_DIR / "dist"
STYLES_FILE = UI_DIR / "styles.qss"
ASSETS_DIR = UI_DIR / "assets"
BROWSER_PROFILE_DIR = BASE_DIR / ".browser_profile"
QA_CACHE_FILE = BASE_DIR / "qa_cache.json"

# Server Settings
MEETING_DASHBOARD_PORT = int(os.getenv("MEETING_DASHBOARD_PORT", "5050"))
MEETING_DASHBOARD_HOST = os.getenv("MEETING_DASHBOARD_HOST", "127.0.0.1")

# Speech & TTS Settings
TTS_NEURAL_VOICE = os.getenv("JARVIS_VOICE", "en-GB-RyanNeural")
TTS_FALLBACK_RATE = int(os.getenv("JARVIS_TTS_RATE", "175"))
MIC_PHRASE_TIME_LIMIT = 5
MIC_TIMEOUT = 5

# Legacy / Environment Fallbacks
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
JARVIS_FORCE_ONLINE = os.getenv("JARVIS_FORCE_ONLINE", "false").lower() == "true"

# Global reentrant lock for vault file operations
_vault_lock = threading.RLock()

DEFAULT_VAULT_STRUCTURE = {
    "autonomous_trust_mode": False,
    "workspace_path": str(BASE_DIR),
    "roles": {
        "intent_router": {"provider": "gemini", "model": "gemini-2.5-flash"},
        "qa_chat": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "vision_agent": {"provider": "gemini", "model": "gemini-2.5-flash"},
        "offline_fallback": {"provider": "ollama", "model": "qwen2.5:7b"},
    },
    "providers": {
        "gemini": {
            "keys": [],
            "active_index": 0,
            "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        },
        "groq": {
            "keys": [],
            "active_index": 0,
            "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        },
        "anthropic": {
            "keys": [],
            "active_index": 0,
            "models": ["claude-3-5-sonnet-latest"],
        },
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "keys": [],
            "active_index": 0,
            "models": ["openai/gpt-4o-mini", "deepseek/deepseek-chat"],
        },
        "ollama": {
            "base_url": "http://127.0.0.1:11434/v1",
            "keys": ["ollama"],
            "active_index": 0,
            "models": ["qwen2.5:7b", "llama3.2:latest"],
        },
        "custom_endpoints": [
            {
                "id": "custom-default",
                "name": "Custom OpenAI Endpoint",
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "gpt-4o-mini",
                "available_models": ["gpt-4o-mini", "gpt-4o"],
            }
        ],
    },
    "services": {
        "openweathermap": "",
    },
}


def mask_key(key: str) -> str:
    """Masks key for secure UI presentation."""
    if not key:
        return ""
    key = key.strip()
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}{'•' * (len(key) - 8)}{key[-4:]}"


def load_vault() -> Dict[str, Any]:
    """Loads api_vault.json, seeding from .env if needed."""
    with _vault_lock:
        if not API_VAULT_FILE.exists():
            data = json.loads(json.dumps(DEFAULT_VAULT_STRUCTURE))
            API_VAULT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        else:
            try:
                data = json.loads(API_VAULT_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = json.loads(json.dumps(DEFAULT_VAULT_STRUCTURE))

        # Ensure all baseline keys exist
        for key, val in DEFAULT_VAULT_STRUCTURE.items():
            if key not in data:
                data[key] = val

        # Ensure providers exist
        if "providers" not in data:
            data["providers"] = {}
        for prov, pconf in DEFAULT_VAULT_STRUCTURE["providers"].items():
            if prov not in data["providers"]:
                data["providers"][prov] = pconf
            else:
                if isinstance(pconf, dict):
                    for subk, subv in pconf.items():
                        if subk not in data["providers"][prov]:
                            data["providers"][prov][subk] = subv

        # Seed from .env
        modified = False
        gemini_env = os.getenv("GEMINI_API_KEY", "").strip()
        if gemini_env:
            gem_keys = data["providers"].setdefault("gemini", {}).setdefault("keys", [])
            if gemini_env not in gem_keys:
                gem_keys.append(gemini_env)
                modified = True

        groq_env = os.getenv("GROQ_API_KEY", "").strip()
        if groq_env:
            groq_keys = data["providers"].setdefault("groq", {}).setdefault("keys", [])
            if groq_env not in groq_keys:
                groq_keys.append(groq_env)
                modified = True

        weather_env = os.getenv("WEATHER_API_KEY", "").strip()
        if weather_env:
            current_weather = data.setdefault("services", {}).get("openweathermap", "")
            if not current_weather:
                data["services"]["openweathermap"] = weather_env
                modified = True

        weather_val = data.get("services", {}).get("openweathermap", "")
        data.setdefault("providers", {})["openweathermap"] = {
            "keys": [weather_val] if weather_val else [],
            "keys_masked": [mask_key(weather_val)] if weather_val else [],
        }

        if modified:
            try:
                API_VAULT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[Settings] Error saving seeded vault: {e}")

        return data


def save_vault(data: Dict[str, Any]) -> None:
    """Saves updated vault dictionary to disk."""
    with _vault_lock:
        API_VAULT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_vault() -> Dict[str, Any]:
    """Retrieve the current vault structure."""
    return load_vault()


def get_masked_vault() -> Dict[str, Any]:
    """Returns a deep-copy of the vault with sensitive API keys masked."""
    raw = load_vault()
    masked = json.loads(json.dumps(raw))
    providers = masked.get("providers", {})
    for prov_name, prov_data in providers.items():
        if isinstance(prov_data, dict) and "keys" in prov_data:
            prov_data["keys_masked"] = [mask_key(k) for k in prov_data["keys"]]
        elif prov_name == "custom_endpoints" and isinstance(prov_data, list):
            for ep in prov_data:
                if "api_key" in ep:
                    ep["api_key_masked"] = mask_key(ep["api_key"])

    weather_val = masked.get("services", {}).get("openweathermap", "")
    masked.setdefault("providers", {})["openweathermap"] = {
        "keys": [weather_val] if weather_val else [],
        "keys_masked": [mask_key(weather_val)] if weather_val else [],
    }

    if "services" in masked and "openweathermap" in masked["services"]:
        masked["services"]["openweathermap_masked"] = mask_key(masked["services"]["openweathermap"])

    return masked


def get_active_key(provider: str) -> Optional[str]:
    """Returns the current active key for a given provider."""
    vault = load_vault()
    prov_data = vault.get("providers", {}).get(provider, {})
    keys = prov_data.get("keys", [])
    if not keys:
        return None
    idx = prov_data.get("active_index", 0)
    if idx >= len(keys) or idx < 0:
        idx = 0
    return keys[idx]


def rotate_provider_key(provider: str) -> Optional[str]:
    """
    Rotates to the next key in the pool for the specified provider.
    Returns the new active key, or None if no keys exist.
    """
    with _vault_lock:
        vault = load_vault()
        prov_data = vault.get("providers", {}).get(provider, {})
        keys = prov_data.get("keys", [])
        if not keys:
            return None
        current_idx = prov_data.get("active_index", 0)
        new_idx = (current_idx + 1) % len(keys)
        prov_data["active_index"] = new_idx
        API_VAULT_FILE.write_text(json.dumps(vault, indent=2), encoding="utf-8")
        return keys[new_idx]


def add_provider_key(provider: str, key: str) -> bool:
    """Adds a key to the specified provider's pool."""
    key = key.strip()
    if not key:
        return False
    with _vault_lock:
        vault = load_vault()
        if provider == "openweathermap":
            vault.setdefault("services", {})["openweathermap"] = key
            API_VAULT_FILE.write_text(json.dumps(vault, indent=2), encoding="utf-8")
            return True

        prov_data = vault.setdefault("providers", {}).setdefault(provider, {"keys": [], "active_index": 0})
        keys = prov_data.setdefault("keys", [])
        if key not in keys:
            keys.append(key)
            API_VAULT_FILE.write_text(json.dumps(vault, indent=2), encoding="utf-8")
        return True


def remove_provider_key(provider: str, key_or_index: Any = None, key_index: Optional[int] = None) -> bool:
    """Removes a key from the specified provider's pool by key string, masked string, or index."""
    with _vault_lock:
        vault = load_vault()
        if provider == "openweathermap":
            vault.setdefault("services", {})["openweathermap"] = ""
            API_VAULT_FILE.write_text(json.dumps(vault, indent=2), encoding="utf-8")
            return True

        prov_data = vault.get("providers", {}).get(provider, {})
        keys = prov_data.get("keys", [])

        # Check explicit key_index or integer key_or_index
        idx = key_index if key_index is not None else (key_or_index if isinstance(key_or_index, int) else None)
        if idx is not None and 0 <= idx < len(keys):
            keys.pop(idx)
            prov_data["active_index"] = 0
            API_VAULT_FILE.write_text(json.dumps(vault, indent=2), encoding="utf-8")
            return True

        # String match raw or masked
        target_str = str(key_or_index).strip() if key_or_index is not None else ""
        if target_str:
            match_idx = None
            for i, k in enumerate(keys):
                if k == target_str or mask_key(k) == target_str:
                    match_idx = i
                    break
            if match_idx is not None:
                keys.pop(match_idx)
                prov_data["active_index"] = 0
                API_VAULT_FILE.write_text(json.dumps(vault, indent=2), encoding="utf-8")
                return True

        return False


def get_role_target(role: str) -> Tuple[str, str]:
    """
    Returns (provider, model) assigned to a given role.
    Fallback to defaults if not specified.
    """
    vault = load_vault()
    roles = vault.get("roles", {})
    if role in roles:
        return roles[role].get("provider", "gemini"), roles[role].get("model", "gemini-2.5-flash")
    default_role = DEFAULT_VAULT_STRUCTURE["roles"].get(role, {"provider": "gemini", "model": "gemini-2.5-flash"})
    return default_role["provider"], default_role["model"]


def is_internet_connected(timeout: float = 1.0) -> bool:
    """Quick socket ping to determine if external network is accessible."""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(("1.1.1.1", 53))
        return True
    except Exception:
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


# Initialize vault on module import
_initial_vault = load_vault()
