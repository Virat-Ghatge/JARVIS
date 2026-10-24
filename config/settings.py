import os
import json
import socket
import time
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Directory & File Path Constants (all aliases supported across Loop 0 - Loop 6)
UI_DIR = BASE_DIR / "ui"
UI_DIST_DIR = UI_DIR / "dist"
BROWSER_PROFILE_DIR = BASE_DIR / ".browser_profile"
WORKSPACE_DIR = BASE_DIR / "workspace"

VAULT_PATH = CONFIG_DIR / "api_vault.json"
VAULT_FILE = VAULT_PATH
API_VAULT_PATH = VAULT_PATH

MEETINGS_PATH = CONFIG_DIR / "meetings.json"
MEETINGS_FILE = MEETINGS_PATH

SUMMARIES_PATH = CONFIG_DIR / "meeting_summaries.json"
SUMMARIES_FILE = SUMMARIES_PATH
MEETING_SUMMARIES_FILE = SUMMARIES_PATH

ALARMS_PATH = CONFIG_DIR / "alarms.json"
ALARMS_FILE = ALARMS_PATH

SKILLS_PATH = CONFIG_DIR / "skills.json"
SKILLS_FILE = SKILLS_PATH

MCP_PATH = CONFIG_DIR / "mcp_servers.json"
MCP_SERVERS_FILE = MCP_PATH
MCP_CONFIG_FILE = MCP_PATH

QA_CACHE_PATH = BASE_DIR / "qa_cache.json"
QA_CACHE_FILE = QA_CACHE_PATH

# Server, Audio & Assistant Constants
SERVER_HOST = os.environ.get("JARVIS_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("JARVIS_PORT", "5050"))
HUD_HOST = SERVER_HOST
HUD_PORT = SERVER_PORT

ASSISTANT_NAME = "JARVIS"
WAKE_WORDS = ["jarvis", "hey jarvis", "ok jarvis"]
DEFAULT_CITY = os.environ.get("JARVIS_DEFAULT_CITY", "Mumbai")

TTS_NEURAL_VOICE = os.environ.get("JARVIS_TTS_VOICE", "en-GB-RyanNeural")
TTS_FALLBACK_RATE = int(os.environ.get("JARVIS_TTS_RATE", "185"))
TTS_DEFAULT_VOLUME = 1.0

SPEECH_RECOGNITION_TIMEOUT = 5
SPEECH_PHRASE_TIME_LIMIT = 12

# HUD Theme Palette Constants
HUD_THEME = {
    "bg_void": "#060A12",
    "arc_cyan": "#00E5FF",
    "reactor_gold": "#FFB300",
    "crimson_alert": "#FF1744",
    "emerald_online": "#00E676",
}

DEFAULT_VAULT: Dict[str, Any] = {
    "providers": {
        "gemini": {
            "keys": [],
            "active_index": 0,
            "default_model": "gemini-2.5-flash",
            "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
        },
        "groq": {
            "keys": [],
            "active_index": 0,
            "default_model": "llama-3.3-70b-versatile",
            "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
        },
        "anthropic": {
            "keys": [],
            "active_index": 0,
            "default_model": "claude-3-5-sonnet-latest",
            "models": ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"]
        },
        "openai": {
            "keys": [],
            "active_index": 0,
            "default_model": "gpt-4o-mini",
            "models": ["gpt-4o-mini", "gpt-4o"]
        }
    },
    "custom_endpoints": [
        {
            "id": "freellmapi_local",
            "name": "FREELLMAPI Local Server",
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key": "sk-local-free",
            "default_model": "default",
            "model": "default",
            "enabled": True,
            "min_request_interval_ms": 65
        }
    ],
    "role_mappings": {
        "chat": "custom:freellmapi_local",
        "router": "custom:freellmapi_local",
        "code_synth": "custom:freellmapi_local",
        "coding": "custom:freellmapi_local",
        "vision": "gemini",
        "vision_agent": "gemini",
        "summarizer": "custom:freellmapi_local",
        "meeting_summarizer": "custom:freellmapi_local"
    },
    "safety": {
        "require_approval_for_high_risk": True,
        "auto_approve_safe": True
    }
}

_vault_lock = threading.RLock()
_net_cache = {"online": True, "last_checked": 0.0, "checking": False}


def ensure_json_file(path: Path, default_data: Any) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2)


def _normalize_key_entry(entry: Any, provider: str, idx: int) -> Dict[str, Any]:
    if isinstance(entry, dict):
        key_val = str(entry.get("key", entry.get("api_key", ""))).strip()
        return {
            "id": entry.get("id") or f"{provider}_{idx + 1}",
            "label": entry.get("label") or f"{provider.upper()} Key #{idx + 1}",
            "key": key_val,
            "status": entry.get("status", "standby"),
            "calls": int(entry.get("calls", 0)),
            "errors": int(entry.get("errors", 0)),
            "last_error": entry.get("last_error"),
        }
    key_val = str(entry).strip()
    return {
        "id": f"{provider}_{idx + 1}",
        "label": f"{provider.upper()} Key #{idx + 1}",
        "key": key_val,
        "status": "standby",
        "calls": 0,
        "errors": 0,
        "last_error": None,
    }


def _normalize_vault_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = json.loads(json.dumps(DEFAULT_VAULT))

    providers = data.setdefault("providers", {})
    for prov_name, default_prov in DEFAULT_VAULT["providers"].items():
        if prov_name not in providers or not isinstance(providers[prov_name], dict):
            providers[prov_name] = json.loads(json.dumps(default_prov))
        else:
            p_obj = providers[prov_name]
            raw_keys = p_obj.get("keys", [])
            p_obj["keys"] = [
                _normalize_key_entry(k, prov_name, idx)
                for idx, k in enumerate(raw_keys)
                if (k.get("key") if isinstance(k, dict) else k)
            ]
            p_obj.setdefault("active_index", 0)
            p_obj.setdefault("default_model", default_prov["default_model"])
            p_obj.setdefault("models", default_prov.get("models", [default_prov["default_model"]]))
            if p_obj["keys"]:
                p_obj["active_index"] = max(0, min(int(p_obj["active_index"]), len(p_obj["keys"]) - 1))
            else:
                p_obj["active_index"] = 0

    data.setdefault("custom_endpoints", json.loads(json.dumps(DEFAULT_VAULT["custom_endpoints"])))
    for ep in data["custom_endpoints"]:
        if isinstance(ep, dict):
            ep.setdefault("id", f"custom_{int(time.time())}")
            ep.setdefault("name", ep["id"])
            ep.setdefault("base_url", "http://127.0.0.1:8000/v1")
            ep.setdefault("api_key", "sk-local")
            ep.setdefault("default_model", ep.get("model", "default"))
            ep.setdefault("model", ep.get("default_model", "default"))
            ep.setdefault("enabled", True)

    roles = data.setdefault("role_mappings", {})
    for role_k, role_v in DEFAULT_VAULT["role_mappings"].items():
        roles.setdefault(role_k, role_v)

    data.setdefault("safety", json.loads(json.dumps(DEFAULT_VAULT["safety"])))
    return data


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
        "GOOGLE_API_KEY": "gemini",
        "GROQ_API_KEY": "groq",
        "ANTHROPIC_API_KEY": "anthropic",
        "OPENAI_API_KEY": "openai",
    }
    for env_var, provider in env_map.items():
        val = os.environ.get(env_var, "").strip()
        if val and provider in vault.get("providers", {}):
            keys = vault["providers"][provider].get("keys", [])
            if not any((k.get("key") if isinstance(k, dict) else k) == val for k in keys):
                keys.append(_normalize_key_entry(
                    {"id": f"env_{provider}_{len(keys)+1}", "label": f"ENV {env_var}", "key": val},
                    provider,
                    len(keys),
                ))
                vault["providers"][provider]["keys"] = keys
                changed = True
    if changed:
        save_vault(vault)


def load_vault(vault_path: Optional[Path] = None) -> Dict[str, Any]:
    target_path = Path(vault_path) if vault_path else VAULT_PATH
    with _vault_lock:
        ensure_json_file(target_path, DEFAULT_VAULT)
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return _normalize_vault_schema(raw)
        except Exception:
            return _normalize_vault_schema(json.loads(json.dumps(DEFAULT_VAULT)))


def get_vault(vault_path: Optional[Path] = None) -> Dict[str, Any]:
    return load_vault(vault_path=vault_path)


def save_vault(vault_data: Dict[str, Any], vault_path: Optional[Path] = None) -> Dict[str, Any]:
    target_path = Path(vault_path) if vault_path else VAULT_PATH
    with _vault_lock:
        normalized = _normalize_vault_schema(vault_data)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)
        return normalized


def mask_key(key: str) -> str:
    if not key:
        return ""
    s = str(key).strip()
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"


def get_masked_vault(vault_path: Optional[Path] = None) -> Dict[str, Any]:
    vault = json.loads(json.dumps(load_vault(vault_path=vault_path)))
    for prov in vault.get("providers", {}).values():
        for k in prov.get("keys", []):
            if isinstance(k, dict) and "key" in k:
                k["masked_key"] = mask_key(k["key"])
    return vault


def add_provider_key(
    provider: str,
    key: str,
    label: str = "",
    vault_path: Optional[Path] = None,
) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    prov = vault.setdefault("providers", {}).setdefault(
        provider,
        {"keys": [], "active_index": 0, "default_model": "default", "models": ["default"]},
    )
    keys = prov.setdefault("keys", [])
    clean_key = str(key).strip()
    if clean_key and not any((k.get("key") if isinstance(k, dict) else k) == clean_key for k in keys):
        keys.append({
            "id": f"{provider}_{len(keys) + 1}_{int(time.time() * 1000) % 100000}",
            "label": label or f"{provider.upper()} Key #{len(keys) + 1}",
            "key": clean_key,
            "status": "active" if len(keys) == 0 else "standby",
            "calls": 0,
            "errors": 0,
            "last_error": None,
        })
    return save_vault(vault, vault_path=vault_path)


add_api_key = add_provider_key


def remove_provider_key(
    provider: str,
    key_or_index: Any,
    vault_path: Optional[Path] = None,
) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    if provider in vault.get("providers", {}):
        keys = vault["providers"][provider].get("keys", [])
        if isinstance(key_or_index, int):
            if 0 <= key_or_index < len(keys):
                keys.pop(key_or_index)
        else:
            target = str(key_or_index)
            keys = [
                k for k in keys
                if (k.get("id") if isinstance(k, dict) else str(k)) != target
                and (k.get("key") if isinstance(k, dict) else str(k)) != target
            ]
        vault["providers"][provider]["keys"] = keys
        if keys:
            vault["providers"][provider]["active_index"] = min(
                vault["providers"][provider].get("active_index", 0), len(keys) - 1
            )
        else:
            vault["providers"][provider]["active_index"] = 0
    return save_vault(vault, vault_path=vault_path)


remove_api_key = remove_provider_key


def get_active_key(provider: str, vault_path: Optional[Path] = None) -> Optional[str]:
    vault = load_vault(vault_path=vault_path)
    if provider.startswith("custom:"):
        ep_id = provider.split(":", 1)[1]
        for ep in vault.get("custom_endpoints", []):
            if ep.get("id") == ep_id or ep.get("name") == ep_id:
                return ep.get("api_key", "sk-local")
        return None

    prov = vault.get("providers", {}).get(provider, {})
    keys = prov.get("keys", [])
    if not keys:
        return None

    idx = int(prov.get("active_index", 0))
    if idx < 0 or idx >= len(keys):
        idx = 0

    # Prefer non-exhausted key starting from active_index
    for offset in range(len(keys)):
        candidate_idx = (idx + offset) % len(keys)
        entry = keys[candidate_idx]
        if isinstance(entry, dict):
            if entry.get("status") != "exhausted" and entry.get("key"):
                return entry["key"]
        elif entry:
            return str(entry)

    first = keys[idx]
    return first.get("key") if isinstance(first, dict) else str(first)


def get_active_key_entry(provider: str, vault_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    vault = load_vault(vault_path=vault_path)
    prov = vault.get("providers", {}).get(provider, {})
    keys = prov.get("keys", [])
    if not keys:
        return None
    idx = max(0, min(int(prov.get("active_index", 0)), len(keys) - 1))
    return keys[idx]


def set_active_key_index(provider: str, index: int, vault_path: Optional[Path] = None) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    if provider in vault.get("providers", {}):
        keys = vault["providers"][provider].get("keys", [])
        if keys:
            idx = max(0, min(int(index), len(keys) - 1))
            vault["providers"][provider]["active_index"] = idx
            for i, k in enumerate(keys):
                if isinstance(k, dict) and k.get("status") != "exhausted":
                    k["status"] = "active" if i == idx else "standby"
    return save_vault(vault, vault_path=vault_path)


def rotate_key(
    provider: str,
    reason: str = "rate_limit",
    vault_path: Optional[Path] = None,
) -> Optional[str]:
    vault = load_vault(vault_path=vault_path)
    prov = vault.get("providers", {}).get(provider)
    if not prov:
        return None
    keys = prov.get("keys", [])
    if not keys:
        return None

    old_idx = max(0, min(int(prov.get("active_index", 0)), len(keys) - 1))
    if isinstance(keys[old_idx], dict):
        keys[old_idx]["status"] = "cooldown" if "429" in str(reason) or "rate" in str(reason).lower() else "exhausted"
        keys[old_idx]["errors"] = int(keys[old_idx].get("errors", 0)) + 1
        keys[old_idx]["last_error"] = str(reason)

    if len(keys) == 1:
        save_vault(vault, vault_path=vault_path)
        return keys[0].get("key") if isinstance(keys[0], dict) else str(keys[0])

    new_idx = (old_idx + 1) % len(keys)
    for offset in range(1, len(keys) + 1):
        cand_idx = (old_idx + offset) % len(keys)
        cand = keys[cand_idx]
        if isinstance(cand, dict) and cand.get("status") != "exhausted":
            new_idx = cand_idx
            break

    prov["active_index"] = new_idx
    if isinstance(keys[new_idx], dict):
        keys[new_idx]["status"] = "active"

    save_vault(vault, vault_path=vault_path)
    return keys[new_idx].get("key") if isinstance(keys[new_idx], dict) else str(keys[new_idx])


def mark_key_status(
    provider: str,
    key_or_index: Any,
    status: str,
    error_msg: Optional[str] = None,
    vault_path: Optional[Path] = None,
) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    prov = vault.get("providers", {}).get(provider, {})
    keys = prov.get("keys", [])
    for idx, k in enumerate(keys):
        if not isinstance(k, dict):
            continue
        match = (idx == key_or_index) or (k.get("key") == key_or_index) or (k.get("id") == key_or_index)
        if match:
            k["status"] = status
            if status == "active":
                k["calls"] = int(k.get("calls", 0)) + 1
            if error_msg:
                k["errors"] = int(k.get("errors", 0)) + 1
                k["last_error"] = error_msg
            break
    return save_vault(vault, vault_path=vault_path)


def get_custom_endpoints(vault_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    vault = load_vault(vault_path=vault_path)
    return vault.get("custom_endpoints", [])


def get_custom_endpoint(endpoint_id: str, vault_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    for ep in get_custom_endpoints(vault_path=vault_path):
        if ep.get("id") == endpoint_id or ep.get("name") == endpoint_id:
            return ep
    return None


def add_custom_endpoint(
    endpoint_or_name: Any,
    base_url: str = "http://127.0.0.1:8000/v1",
    api_key: str = "sk-local",
    default_model: str = "default",
    vault_path: Optional[Path] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    eps = vault.setdefault("custom_endpoints", [])
    if isinstance(endpoint_or_name, dict):
        ep_data = dict(endpoint_or_name)
    else:
        ep_id = kwargs.get("id") or str(endpoint_or_name).lower().replace(" ", "_")
        ep_data = {
            "id": ep_id,
            "name": str(endpoint_or_name),
            "base_url": base_url,
            "api_key": api_key,
            "default_model": kwargs.get("model", default_model),
            "model": kwargs.get("model", default_model),
            "enabled": kwargs.get("enabled", True),
        }
    ep_id = ep_data.get("id") or f"custom_{int(time.time())}"
    ep_data["id"] = ep_id
    ep_data.setdefault("name", ep_id)
    ep_data.setdefault("base_url", base_url)
    ep_data.setdefault("api_key", api_key)
    ep_data.setdefault("default_model", ep_data.get("model", default_model))
    ep_data.setdefault("model", ep_data.get("default_model", default_model))
    ep_data.setdefault("enabled", True)

    eps = [e for e in eps if e.get("id") != ep_id]
    eps.append(ep_data)
    vault["custom_endpoints"] = eps
    return save_vault(vault, vault_path=vault_path)


def remove_custom_endpoint(ep_id: str, vault_path: Optional[Path] = None) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    vault["custom_endpoints"] = [
        e for e in vault.get("custom_endpoints", [])
        if e.get("id") != ep_id and e.get("name") != ep_id
    ]
    return save_vault(vault, vault_path=vault_path)


def get_role_mapping(role: str, vault_path: Optional[Path] = None) -> str:
    vault = load_vault(vault_path=vault_path)
    mappings = vault.get("role_mappings", {})
    return mappings.get(role, mappings.get("chat", "gemini"))


def set_role_mapping(role: str, provider_or_endpoint: str, vault_path: Optional[Path] = None) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    vault.setdefault("role_mappings", {})[role] = provider_or_endpoint
    return save_vault(vault, vault_path=vault_path)


def update_role_mappings(mappings: Dict[str, str], vault_path: Optional[Path] = None) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    vault.setdefault("role_mappings", {}).update(mappings)
    return save_vault(vault, vault_path=vault_path)


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


def is_role_bound_to_local_endpoint(role: str = "chat", vault_path: Optional[Path] = None) -> bool:
    vault = load_vault(vault_path=vault_path)
    target = vault.get("role_mappings", {}).get(role, "")
    if target.startswith("custom:"):
        ep_id = target.split(":", 1)[1]
        for ep in vault.get("custom_endpoints", []):
            if (ep.get("id") == ep_id or ep.get("name") == ep_id) and ep.get("enabled", True):
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
                with socket.create_connection((host, 53), timeout=1.0):
                    online = True
                    break
            except OSError:
                continue
        _net_cache["online"] = online
        _net_cache["last_checked"] = time.time()
        _net_cache["checking"] = False

    t = threading.Thread(target=_probe, daemon=True)
    t.start()


def is_internet_connected(role: Optional[str] = None, timeout: float = 1.0) -> bool:
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
