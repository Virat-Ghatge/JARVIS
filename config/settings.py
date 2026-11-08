import os
import json
import socket
import time
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR
ROOT_DIR = BASE_DIR
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
API_VAULT_FILE = VAULT_PATH

MEETINGS_PATH = CONFIG_DIR / "meetings.json"
MEETINGS_FILE = MEETINGS_PATH

SUMMARIES_PATH = CONFIG_DIR / "meeting_summaries.json"
SUMMARIES_FILE = SUMMARIES_PATH
MEETING_SUMMARIES_FILE = SUMMARIES_PATH
MEETING_SUMMARIES_PATH = SUMMARIES_PATH

ALARMS_PATH = CONFIG_DIR / "alarms.json"
ALARMS_FILE = ALARMS_PATH

SKILLS_PATH = CONFIG_DIR / "skills.json"
SKILLS_FILE = SKILLS_PATH

MCP_PATH = CONFIG_DIR / "mcp_servers.json"
MCP_SERVERS_FILE = MCP_PATH
MCP_SERVERS_PATH = MCP_PATH
MCP_CONFIG_FILE = MCP_PATH

QA_CACHE_PATH = BASE_DIR / "qa_cache.json"
QA_CACHE_FILE = QA_CACHE_PATH

# Embedded Local GGUF Model Constants (Llama 3.2 3B Instruct, ~2.0 GB RAM)
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
INTENT_MODEL_PATH = MODELS_DIR / "intent_model.onnx"
INTENT_VOCAB_PATH = MODELS_DIR / "intent_vocab.json"
LOCAL_MODEL_NAME = "llama-3.2-3b-instruct"
LOCAL_MODEL_FILENAME = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
LOCAL_MODEL_PATH = MODELS_DIR / LOCAL_MODEL_FILENAME
LOCAL_MODEL_REPO = "bartowski/Llama-3.2-3B-Instruct-GGUF"
LOCAL_MODEL_URL = f"https://huggingface.co/{LOCAL_MODEL_REPO}/resolve/main/{LOCAL_MODEL_FILENAME}"
LOCAL_MODEL_THREADS = min(6, max(2, (os.cpu_count() or 4) - 2))

# Server, Audio & Assistant Constants
SERVER_HOST = os.environ.get("JARVIS_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("JARVIS_PORT", "5050"))
HUD_HOST = SERVER_HOST
HUD_PORT = SERVER_PORT
HOST = SERVER_HOST
PORT = SERVER_PORT

ASSISTANT_NAME = "JARVIS"
WAKE_WORDS = ["jarvis", "hey jarvis", "ok jarvis"]
DEFAULT_CITY = os.environ.get("JARVIS_DEFAULT_CITY", "Jaipur")

TTS_NEURAL_VOICE = os.environ.get("JARVIS_TTS_VOICE", "en-GB-RyanNeural")
TTS_VOICE = TTS_NEURAL_VOICE
TTS_FALLBACK_RATE = int(os.environ.get("JARVIS_TTS_RATE", "185"))
TTS_RATE = TTS_FALLBACK_RATE
TTS_DEFAULT_VOLUME = 1.0

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.5-flash"
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")

SPEECH_RECOGNITION_TIMEOUT = 5
SPEECH_PHRASE_TIME_LIMIT = 12
MIC_ENERGY_THRESHOLD = 300
MIC_DYNAMIC_ENERGY = True

HUD_THEME = {
    "bg_void": "#060A12",
    "arc_cyan": "#00E5FF",
    "reactor_gold": "#FFB300",
    "crimson_alert": "#FF1744",
    "emerald_online": "#00E676",
}

DEFAULT_PROVIDERS: Dict[str, Any] = {
    "local": {
        "keys": ["local-in-process"],
        "active_index": 0,
        "default_model": LOCAL_MODEL_NAME,
        "models": [LOCAL_MODEL_NAME, "qwen-2.5-3b-instruct"]
    },
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
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]
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
}

DEFAULT_ROLE_MAPPINGS: Dict[str, Any] = {
    "chat": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "router": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "coding": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "code_synth": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "vision": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "vision_agent": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "summarizer": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "meeting_summarizer": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "qa_chat": {"provider": "gemini", "model": "gemini-2.5-flash"},
}

DEFAULT_VAULT: Dict[str, Any] = {
    "providers": json.loads(json.dumps(DEFAULT_PROVIDERS)),
    "custom_endpoints": [],
    "role_mappings": json.loads(json.dumps(DEFAULT_ROLE_MAPPINGS)),
    "cloud_api_enabled": True,
    "local_first_mode": True,
    "safety": {
        "require_approval_for_high_risk": True,
        "auto_approve_safe": True
    }
}


class RoleTarget(dict):
    """
    Hybrid dict + 2-tuple (provider, model) return object for get_role_target().
    Supports:
      - target["provider"], target.get("model"), target.get("base_url")
      - provider, model = get_role_target("chat")
      - target[0], target[1]
    """
    def __iter__(self):
        yield self.get("provider", "gemini")
        yield self.get("model", "gemini-2.5-flash")

    def __getitem__(self, key):
        if key == 0:
            return self.get("provider", "gemini")
        if key == 1:
            return self.get("model", "gemini-2.5-flash")
        return super().__getitem__(key)


_vault_lock = threading.RLock()
_net_cache = {"online": True, "last_checked": 0.0, "checking": False}


def ensure_json_file(path: Path, default_data: Any) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2)


def mask_key(key: str) -> str:
    if not key:
        return ""
    s = str(key).strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "•" * len(s)
    return f"{s[:4]}••••••••{s[-4:]}"


mask_api_key = mask_key


class KeyStr(str):
    """
    Hybrid str subclass representing an API key.
    Satisfies string comparisons ('test_key in keys' == True) while implementing
    .get(k, default=None) and __getitem__(k) so callers expecting a dict work seamlessly.
    """
    def __new__(cls, val, meta=None):
        if isinstance(val, KeyStr):
            s = super().__new__(cls, str(val))
            s._meta = dict(val._meta)
            if meta:
                s._meta.update(meta)
            return s
        val_str = str(val.get("key") or val.get("value") or val.get("api_key") or "") if isinstance(val, dict) else str(val).strip()
        s = super().__new__(cls, val_str)
        s._meta = dict(val) if isinstance(val, dict) else dict(meta or {})
        s._meta["key"] = val_str
        s._meta["value"] = val_str
        s._meta.setdefault("masked", mask_key(val_str))
        s._meta.setdefault("masked_key", mask_key(val_str))
        s._meta.setdefault("preview", mask_key(val_str))
        s._meta.setdefault("status", "active")
        s._meta.setdefault("is_active", True)
        s._meta.setdefault("calls", 0)
        s._meta.setdefault("errors", 0)
        s._meta.setdefault("last_error", None)
        s._meta.setdefault("added_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        return s

    def get(self, k, default=None):
        if k in ("key", "value"):
            return str(self)
        return self._meta.get(k, default)

    def __getitem__(self, k):
        if isinstance(k, str):
            if k in ("key", "value"):
                return str(self)
            if k in self._meta:
                return self._meta[k]
        return super().__getitem__(k)

    def __setitem__(self, k, v):
        self._meta[k] = v

    def __contains__(self, k):
        if isinstance(k, str) and k in self._meta:
            return True
        return super().__contains__(k)

    def keys(self):
        return self._meta.keys()

    def values(self):
        return self._meta.values()

    def items(self):
        return self._meta.items()

    def to_dict(self):
        d = dict(self._meta)
        d["key"] = str(self)
        d["value"] = str(self)
        return d


def _normalize_key_entry(entry: Any, provider: str, idx: int, active_idx: int = 0) -> KeyStr:
    if isinstance(entry, KeyStr):
        entry["index"] = idx
        entry["is_active"] = (idx == active_idx)
        if idx == active_idx and entry.get("status") == "standby":
            entry["status"] = "active"
        return entry

    if isinstance(entry, dict):
        key_val = str(entry.get("key") or entry.get("value") or entry.get("api_key") or "").strip()
        status = entry.get("status", "active" if idx == active_idx else "standby")
        if idx == active_idx and status == "standby":
            status = "active"
        meta = {
            "id": str(entry.get("id") or f"{provider}_{idx + 1}"),
            "index": idx,
            "label": str(entry.get("label") or f"{provider.upper()} Key #{idx + 1}"),
            "key": key_val,
            "value": key_val,
            "masked": mask_key(key_val),
            "masked_key": mask_key(key_val),
            "preview": mask_key(key_val),
            "status": status,
            "is_active": idx == active_idx,
            "calls": int(entry.get("calls", 0)),
            "errors": int(entry.get("errors", 0)),
            "last_error": entry.get("last_error"),
            "added_at": entry.get("added_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        return KeyStr(key_val, meta)

    key_val = str(entry).strip()
    meta = {
        "id": f"{provider}_{idx + 1}",
        "index": idx,
        "label": f"{provider.upper()} Key #{idx + 1}",
        "key": key_val,
        "value": key_val,
        "masked": mask_key(key_val),
        "masked_key": mask_key(key_val),
        "preview": mask_key(key_val),
        "status": "active" if idx == active_idx else "standby",
        "is_active": idx == active_idx,
        "calls": 0,
        "errors": 0,
        "last_error": None,
        "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return KeyStr(key_val, meta)


def _normalize_vault_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = json.loads(json.dumps(DEFAULT_VAULT))

    providers = data.setdefault("providers", {})
    if "custom_endpoints" in providers:
        nested_ce = providers.pop("custom_endpoints")
        if isinstance(nested_ce, list):
            data.setdefault("custom_endpoints", []).extend([e for e in nested_ce if isinstance(e, dict)])
    for prov_name, default_prov in DEFAULT_PROVIDERS.items():
        if prov_name not in providers:
            providers[prov_name] = json.loads(json.dumps(default_prov))
        elif isinstance(providers[prov_name], list):
            raw_list = providers[prov_name]
            providers[prov_name] = {
                "keys": [_normalize_key_entry(k, prov_name, i, 0) for i, k in enumerate(raw_list) if k],
                "active_index": 0,
                "default_model": default_prov["default_model"],
                "models": default_prov["models"],
            }
        elif isinstance(providers[prov_name], dict):
            p_obj = providers[prov_name]
            raw_keys = p_obj.get("keys", [])
            active_idx = int(p_obj.get("active_index", 0) or 0)
            cleaned_keys = []
            for k in raw_keys:
                val = k.get("key") or k.get("value") or k.get("api_key") if isinstance(k, dict) else k
                if val and str(val).strip():
                    cleaned_keys.append(k)
            if prov_name == "local" and not cleaned_keys:
                cleaned_keys = ["local-in-process"]
            if cleaned_keys:
                active_idx = max(0, min(active_idx, len(cleaned_keys) - 1))
            else:
                active_idx = 0
            p_obj["active_index"] = active_idx
            p_obj["keys"] = [
                _normalize_key_entry(k, prov_name, idx, active_idx)
                for idx, k in enumerate(cleaned_keys)
            ]
            p_obj.setdefault("default_model", default_prov["default_model"])
            p_obj.setdefault("models", default_prov.get("models", [default_prov["default_model"]]))

    raw_eps = data.get("custom_endpoints", [])
    normalized_eps: List[Dict[str, Any]] = []
    if isinstance(raw_eps, dict):
        for ep_key, ep_val in raw_eps.items():
            if isinstance(ep_val, dict):
                ep_copy = dict(ep_val)
                ep_copy.setdefault("id", ep_key)
                ep_copy.setdefault("name", ep_key)
                normalized_eps.append(ep_copy)
    elif isinstance(raw_eps, list):
        for ep in raw_eps:
            if isinstance(ep, dict):
                normalized_eps.append(dict(ep))

    for ep in normalized_eps:
        ep_id = str(ep.get("id") or ep.get("name") or f"custom_{int(time.time())}").strip()
        ep["id"] = ep_id
        ep["name"] = str(ep.get("name") or ep_id).strip()
        ep["base_url"] = str(ep.get("base_url") or ep.get("url") or "http://127.0.0.1:8000/v1").strip()
        ep["url"] = ep["base_url"]
        raw_k = str(ep.get("api_key") or ep.get("key") or "sk-local").strip()
        ep["api_key"] = raw_k
        ep["masked_key"] = mask_key(raw_k)
        model_name = str(ep.get("default_model") or ep.get("model") or "default").strip()
        ep["default_model"] = model_name
        ep["model"] = model_name
        ep["enabled"] = bool(ep.get("enabled", True))
        ep["min_request_interval_ms"] = int(ep.get("min_request_interval_ms", 65))

    data["custom_endpoints"] = normalized_eps

    roles = data.setdefault("role_mappings", {})
    for role_k, role_v in DEFAULT_ROLE_MAPPINGS.items():
        if role_k not in roles:
            roles[role_k] = json.loads(json.dumps(role_v))
        elif isinstance(roles[role_k], str):
            prov_str = roles[role_k]
            default_m = DEFAULT_PROVIDERS.get(prov_str, {}).get("default_model", "default")
            roles[role_k] = {"provider": prov_str, "model": default_m}
        elif isinstance(roles[role_k], dict):
            prov_str = str(roles[role_k].get("provider", "gemini"))
            default_m = DEFAULT_PROVIDERS.get(prov_str, {}).get("default_model", "gemini-2.5-flash")
            roles[role_k].setdefault("provider", prov_str)
            roles[role_k].setdefault("model", default_m)

    data.setdefault("cloud_api_enabled", True)
    data.setdefault("local_first_mode", True)
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
    seed_vault_from_env()


def seed_vault_from_env(vault_path: Optional[Path] = None) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
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
        return save_vault(vault, vault_path=vault_path)
    return vault


_seed_env_keys = seed_vault_from_env


def load_vault(vault_path: Optional[Path] = None) -> Dict[str, Any]:
    target_path = Path(vault_path) if vault_path else VAULT_PATH
    with _vault_lock:
        if not target_path.exists():
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
        disk_data = json.loads(json.dumps(normalized, default=lambda o: o.to_dict() if hasattr(o, "to_dict") else str(o)))
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(disk_data, f, indent=2)
        return normalized


def get_masked_vault(vault_path: Optional[Path] = None) -> Dict[str, Any]:
    raw_vault = load_vault(vault_path=vault_path)
    vault = json.loads(json.dumps(raw_vault, default=lambda o: o.to_dict() if hasattr(o, "to_dict") else str(o)))
    providers = vault.get("providers", {})
    for prov_name, prov in list(providers.items()):
        if isinstance(prov, list):
            providers[prov_name] = {
                "keys": prov,
                "active_index": 0,
                "default_model": DEFAULT_PROVIDERS.get(prov_name, {}).get("default_model", "default"),
                "models": DEFAULT_PROVIDERS.get(prov_name, {}).get("models", ["default"]),
            }
            prov = providers[prov_name]
        elif not isinstance(prov, dict):
            continue

        active_idx = int(prov.get("active_index", 0) or 0)
        keys_list = prov.get("keys", [])
        masked_keys = []
        rich_keys = []
        for idx, k in enumerate(keys_list):
            raw_k = k.get("key") if isinstance(k, dict) else str(k)
            m = mask_key(raw_k)
            masked_keys.append(m)
            if isinstance(k, dict):
                k_copy = dict(k)
                k_copy["id"] = k_copy.get("id") or f"{prov_name}_{idx + 1}"
                k_copy["index"] = idx
                k_copy["label"] = k_copy.get("label") or f"{prov_name.upper()} Key #{idx + 1}"
                k_copy["key"] = m
                k_copy["value"] = m
                k_copy["masked"] = m
                k_copy["masked_key"] = m
                k_copy["preview"] = m
                k_copy["is_active"] = (idx == active_idx)
                k_copy["status"] = "active" if idx == active_idx else (k_copy.get("status") or "standby")
                k_copy["calls"] = int(k_copy.get("calls", 0))
                k_copy["errors"] = int(k_copy.get("errors", 0))
                rich_keys.append(k_copy)
            else:
                rich_keys.append({
                    "id": f"{prov_name}_{idx + 1}",
                    "index": idx,
                    "label": f"{prov_name.upper()} Key #{idx + 1}",
                    "key": m,
                    "value": m,
                    "masked": m,
                    "masked_key": m,
                    "preview": m,
                    "status": "active" if idx == active_idx else "standby",
                    "is_active": idx == active_idx,
                    "calls": 0,
                    "errors": 0,
                    "last_error": None,
                })
        prov["keys"] = rich_keys
        prov["keys_masked"] = masked_keys

    for ep in vault.get("custom_endpoints", []):
        if isinstance(ep, dict):
            raw_k = ep.get("api_key", "")
            ep["masked_key"] = mask_key(raw_k)

    vault["roles"] = vault.get("role_mappings", {})
    vault["autonomous_trust_mode"] = vault.get("safety", {}).get("auto_approve_safe", True)
    vault["cloud_api_enabled"] = is_cloud_api_enabled(vault_path=vault_path)
    vault["local_first_mode"] = raw_vault.get("local_first_mode", True)
    vault["local_model"] = get_local_model_status()
    return vault


def get_local_model_status() -> Dict[str, Any]:
    downloaded = LOCAL_MODEL_PATH.exists() and LOCAL_MODEL_PATH.stat().st_size > 100 * 1024 * 1024
    size_bytes = LOCAL_MODEL_PATH.stat().st_size if LOCAL_MODEL_PATH.exists() else 0
    size_mb = round(size_bytes / (1024 * 1024), 2)
    is_loaded = False
    runtime_available = False
    download_state = {
        "downloading": False,
        "progress": 0.0,
        "downloaded_bytes": 0,
        "total_bytes": 0,
        "error": None,
    }
    try:
        from core.adapters.local_gguf_adapter import LocalGGUFAdapter
        runtime_available = LocalGGUFAdapter.is_available()
        is_loaded = LocalGGUFAdapter.is_loaded()
        download_state = LocalGGUFAdapter.get_download_status()
    except Exception:
        pass

    ram_usage_mb = 0.0
    if is_loaded:
        try:
            import psutil
            ram_usage_mb = round(psutil.Process().memory_info().rss / (1024 * 1024), 1)
        except Exception:
            ram_usage_mb = 2100.0

    return {
        "model_name": LOCAL_MODEL_NAME,
        "filename": LOCAL_MODEL_FILENAME,
        "path": str(LOCAL_MODEL_PATH),
        "repo": LOCAL_MODEL_REPO,
        "url": LOCAL_MODEL_URL,
        "downloaded": downloaded,
        "runtime_available": runtime_available,
        "ready": bool(downloaded and runtime_available),
        "size_bytes": size_bytes,
        "size_mb": size_mb,
        "loaded": is_loaded,
        "ram_usage_mb": ram_usage_mb,
        "threads": LOCAL_MODEL_THREADS,
        "download_state": download_state,
    }


def is_cloud_api_enabled(vault_path: Optional[Path] = None) -> bool:
    vault = load_vault(vault_path=vault_path)
    return bool(vault.get("cloud_api_enabled", True))


def set_cloud_api_enabled(enabled: bool, vault_path: Optional[Path] = None) -> None:
    vault = load_vault(vault_path=vault_path)
    vault["cloud_api_enabled"] = bool(enabled)
    save_vault(vault, vault_path=vault_path)


def is_local_first_mode(vault_path: Optional[Path] = None) -> bool:
    vault = load_vault(vault_path=vault_path)
    return bool(vault.get("local_first_mode", True))


def set_local_first_mode(enabled: bool, vault_path: Optional[Path] = None) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    vault["local_first_mode"] = bool(enabled)
    return save_vault(vault, vault_path=vault_path)


def _auto_bind_roles_if_needed(vault: Dict[str, Any], newly_added_provider: str, default_model: str) -> None:
    """
    If any role currently points to a provider that has 0 keys (and isn't a valid custom endpoint),
    automatically point that role to `newly_added_provider` so AI systems work immediately after adding a key.
    """
    roles = vault.setdefault("role_mappings", {})
    providers = vault.get("providers", {})
    custom_ids = {ep.get("id") for ep in vault.get("custom_endpoints", [])} | {
        ep.get("name") for ep in vault.get("custom_endpoints", [])
    }

    for role_name, mapping in list(roles.items()):
        curr_prov = mapping.get("provider") if isinstance(mapping, dict) else str(mapping)
        clean_curr = curr_prov.split(":", 1)[1] if str(curr_prov).startswith("custom:") else str(curr_prov)
        has_keys = False
        if clean_curr in providers and len(providers[clean_curr].get("keys", [])) > 0:
            has_keys = True
        elif clean_curr in custom_ids:
            has_keys = True

        if not has_keys:
            roles[role_name] = {"provider": newly_added_provider, "model": default_model}


def add_provider_key(
    provider: str,
    key: str = "",
    label: str = "",
    vault_path: Optional[Path] = None,
    **kwargs: Any,
) -> bool:
    clean_provider = str(provider).strip().lower()
    clean_key = str(key or kwargs.get("api_key") or kwargs.get("value") or "").strip()
    if not clean_key:
        return False

    vault = load_vault(vault_path=vault_path)
    default_prov = DEFAULT_PROVIDERS.get(
        clean_provider,
        {"keys": [], "active_index": 0, "default_model": "default", "models": ["default"]},
    )
    prov = vault.setdefault("providers", {}).setdefault(
        clean_provider, json.loads(json.dumps(default_prov))
    )
    keys = prov.setdefault("keys", [])

    existing_idx = None
    for idx, k in enumerate(keys):
        k_val = k.get("key") if isinstance(k, (dict, KeyStr)) else str(k)
        if k_val == clean_key:
            existing_idx = idx
            break

    if existing_idx is None:
        new_idx = len(keys)
        is_first = new_idx == 0
        meta = {
            "id": f"{clean_provider}_{new_idx + 1}_{int(time.time() * 1000) % 100000}",
            "index": new_idx,
            "label": label or f"{clean_provider.upper()} Key #{new_idx + 1}",
            "key": clean_key,
            "value": clean_key,
            "masked": mask_key(clean_key),
            "masked_key": mask_key(clean_key),
            "preview": mask_key(clean_key),
            "status": "active" if is_first else "standby",
            "is_active": is_first,
            "calls": 0,
            "errors": 0,
            "last_error": None,
            "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        keys.append(KeyStr(clean_key, meta))
        if is_first:
            prov["active_index"] = 0
    else:
        if isinstance(keys[existing_idx], (dict, KeyStr)):
            keys[existing_idx]["status"] = "active"
            keys[existing_idx]["last_error"] = None
            if label:
                keys[existing_idx]["label"] = label
        prov["active_index"] = existing_idx

    _auto_bind_roles_if_needed(
        vault,
        newly_added_provider=clean_provider,
        default_model=prov.get("default_model", "gemini-2.5-flash"),
    )
    save_vault(vault, vault_path=vault_path)
    return True


add_api_key = add_provider_key


def remove_provider_key(
    provider: str,
    key_or_index: Any,
    vault_path: Optional[Path] = None,
) -> bool:
    clean_provider = str(provider).strip().lower()
    vault = load_vault(vault_path=vault_path)
    removed = False
    if clean_provider in vault.get("providers", {}):
        prov = vault["providers"][clean_provider]
        if isinstance(prov, dict):
            keys = prov.get("keys", [])
            target = str(key_or_index).strip()
            idx_to_pop = None
            if isinstance(key_or_index, int) or (isinstance(key_or_index, str) and key_or_index.isdigit() and int(key_or_index) < len(keys)):
                idx = int(key_or_index)
                if 0 <= idx < len(keys):
                    idx_to_pop = idx
            if idx_to_pop is not None:
                keys.pop(idx_to_pop)
                removed = True
            else:
                new_keys = []
                for k in keys:
                    val = str(k)
                    k_id = k.get("id") if isinstance(k, (dict, KeyStr)) else ""
                    k_mask = k.get("masked") if isinstance(k, (dict, KeyStr)) else mask_key(val)
                    k_mask2 = k.get("masked_key") if isinstance(k, (dict, KeyStr)) else mask_key(val)
                    k_prev = k.get("preview") if isinstance(k, (dict, KeyStr)) else mask_key(val)
                    k_label = k.get("label") if isinstance(k, (dict, KeyStr)) else ""
                    if target in (val, k_id, k_mask, k_mask2, k_prev, k_label):
                        removed = True
                    else:
                        new_keys.append(k)
                if len(new_keys) != len(keys):
                    removed = True
                keys = new_keys
            prov["keys"] = keys
            if keys:
                prov["active_index"] = min(int(prov.get("active_index", 0)), len(keys) - 1)
            else:
                prov["active_index"] = 0
            save_vault(vault, vault_path=vault_path)
    return removed


remove_api_key = remove_provider_key


def get_active_key(provider: str, vault_path: Optional[Path] = None) -> Optional[str]:
    vault = load_vault(vault_path=vault_path)
    clean_prov = str(provider).strip()
    if clean_prov.startswith("custom:"):
        ep_id = clean_prov.split(":", 1)[1]
        for ep in vault.get("custom_endpoints", []):
            if ep.get("id") == ep_id or ep.get("name") == ep_id:
                return ep.get("api_key", "sk-local")
        return None

    for ep in vault.get("custom_endpoints", []):
        if ep.get("id") == clean_prov or ep.get("name") == clean_prov:
            return ep.get("api_key", "sk-local")

    prov = vault.get("providers", {}).get(clean_prov.lower(), {})
    if isinstance(prov, list):
        keys = prov
    elif isinstance(prov, dict):
        keys = prov.get("keys", [])
    else:
        keys = []
    if not keys:
        return None

    idx = int(prov.get("active_index", 0) or 0)
    if idx < 0 or idx >= len(keys):
        idx = 0

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
    prov = vault.get("providers", {}).get(str(provider).lower(), {})
    if isinstance(prov, list):
        keys = prov
        idx = 0
    elif isinstance(prov, dict):
        keys = prov.get("keys", [])
        idx = max(0, min(int(prov.get("active_index", 0) or 0), len(keys) - 1)) if keys else 0
    else:
        keys = []
        idx = 0
    if not keys:
        return None
    return keys[idx]


def set_active_key_index(provider: str, index: int, vault_path: Optional[Path] = None) -> Dict[str, Any]:
    clean_prov = str(provider).lower()
    vault = load_vault(vault_path=vault_path)
    if clean_prov in vault.get("providers", {}):
        keys = vault["providers"][clean_prov].get("keys", [])
        if keys:
            idx = max(0, min(int(index), len(keys) - 1))
            vault["providers"][clean_prov]["active_index"] = idx
            for i, k in enumerate(keys):
                if isinstance(k, dict):
                    k["status"] = "active" if i == idx else ("standby" if k.get("status") == "active" else k.get("status", "standby"))
                    k["is_active"] = i == idx
    return save_vault(vault, vault_path=vault_path)


def rotate_key(
    provider: str,
    reason: str = "rate_limit",
    vault_path: Optional[Path] = None,
) -> Optional[str]:
    clean_prov = str(provider).lower()
    vault = load_vault(vault_path=vault_path)
    prov = vault.get("providers", {}).get(clean_prov)
    if not prov:
        return None
    keys = prov.get("keys", []) if isinstance(prov, dict) else (prov if isinstance(prov, list) else [])
    if not keys:
        return None

    old_idx = max(0, min(int(prov.get("active_index", 0)), len(keys) - 1))
    if isinstance(keys[old_idx], dict):
        keys[old_idx]["status"] = "cooldown" if ("429" in str(reason) or "rate" in str(reason).lower()) else "exhausted"
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


rotate_provider_key = rotate_key


def mark_key_status(
    provider: str,
    key_or_index: Any,
    status: str,
    error_msg: Optional[str] = None,
    vault_path: Optional[Path] = None,
) -> Dict[str, Any]:
    clean_prov = str(provider).lower()
    vault = load_vault(vault_path=vault_path)
    prov = vault.get("providers", {}).get(clean_prov, {})
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
    if not endpoint_id:
        return None
    clean_id = endpoint_id.split(":", 1)[1] if str(endpoint_id).startswith("custom:") else str(endpoint_id)
    for ep in get_custom_endpoints(vault_path=vault_path):
        if ep.get("id") == clean_id or ep.get("name") == clean_id:
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
        ep_id = kwargs.get("id") or str(endpoint_or_name).strip().lower().replace(" ", "_")
        ep_data = {
            "id": ep_id,
            "name": str(endpoint_or_name).strip(),
            "base_url": kwargs.get("url") or base_url,
            "api_key": kwargs.get("key") or api_key or "sk-local",
            "default_model": kwargs.get("model") or default_model or "default",
            "model": kwargs.get("model") or default_model or "default",
            "enabled": kwargs.get("enabled", True),
        }
    ep_id = str(ep_data.get("id") or ep_data.get("name") or f"custom_{int(time.time())}").strip().lower().replace(" ", "_")
    ep_data["id"] = ep_id
    ep_data["name"] = str(ep_data.get("name") or ep_id).strip()
    ep_data["base_url"] = str(ep_data.get("base_url") or ep_data.get("url") or base_url).strip()
    ep_data["url"] = ep_data["base_url"]
    ep_data["api_key"] = str(ep_data.get("api_key") or ep_data.get("key") or api_key or "sk-local").strip()
    model_val = str(ep_data.get("default_model") or ep_data.get("model") or default_model or "default").strip()
    ep_data["default_model"] = model_val
    ep_data["model"] = model_val
    ep_data["enabled"] = bool(ep_data.get("enabled", True))

    eps = [e for e in eps if e.get("id") != ep_id and e.get("name") != ep_data["name"]]
    eps.append(ep_data)
    vault["custom_endpoints"] = eps

    _auto_bind_roles_if_needed(
        vault,
        newly_added_provider=f"custom:{ep_id}",
        default_model=model_val,
    )
    return save_vault(vault, vault_path=vault_path)


def remove_custom_endpoint(ep_id: str, vault_path: Optional[Path] = None) -> Dict[str, Any]:
    clean_id = ep_id.split(":", 1)[1] if str(ep_id).startswith("custom:") else str(ep_id)
    vault = load_vault(vault_path=vault_path)
    vault["custom_endpoints"] = [
        e for e in vault.get("custom_endpoints", [])
        if e.get("id") != clean_id and e.get("name") != clean_id
    ]
    return save_vault(vault, vault_path=vault_path)


def get_role_target(role: str, vault_path: Optional[Path] = None) -> RoleTarget:
    """
    Resolves a role ('chat', 'router', 'coding', 'vision', 'summarizer') into a RoleTarget.
    If the mapped provider has no keys configured, automatically falls back to the first
    provider or custom endpoint in the vault that has keys configured.
    """
    vault = load_vault(vault_path=vault_path)
    mappings = vault.get("role_mappings", {})
    raw_target = mappings.get(role) or mappings.get("chat") or {"provider": "gemini", "model": "gemini-2.5-flash"}

    if isinstance(raw_target, dict):
        provider = str(raw_target.get("provider", "gemini")).strip()
        model = raw_target.get("model")
    else:
        provider = str(raw_target).strip()
        model = None

    ep = get_custom_endpoint(provider, vault_path=vault_path)
    if ep and ep.get("enabled", True):
        return RoleTarget(
            provider=provider if provider.startswith("custom:") else f"custom:{ep['id']}",
            model=model or ep.get("default_model") or ep.get("model") or "default",
            base_url=ep.get("base_url"),
            api_key=ep.get("api_key", "sk-local"),
            is_custom=True,
            endpoint=ep,
        )

    clean_prov = provider.lower()
    prov_cfg = vault.get("providers", {}).get(clean_prov, {})
    if not isinstance(prov_cfg, dict):
        prov_cfg = {}

    if clean_prov == "local":
        return RoleTarget(
            provider="local",
            model=model or prov_cfg.get("default_model", LOCAL_MODEL_NAME),
            base_url=None,
            api_key="local-in-process",
            is_custom=False,
        )

    active_key = get_active_key(clean_prov, vault_path=vault_path)

    if active_key:
        return RoleTarget(
            provider=clean_prov,
            model=model or prov_cfg.get("default_model", "gemini-2.5-flash"),
            base_url=prov_cfg.get("base_url"),
            api_key=active_key,
            is_custom=False,
        )

    # Automatic fallback: find ANY cloud provider in the vault that has an active key
    for cand_prov, cand_cfg in vault.get("providers", {}).items():
        if cand_prov in ("custom_endpoints", "local") or not (isinstance(cand_cfg, dict) or isinstance(cand_cfg, list)):
            continue
        cand_key = get_active_key(cand_prov, vault_path=vault_path)
        if cand_key:
            return RoleTarget(
                provider=cand_prov,
                model=cand_cfg.get("default_model", "default") if isinstance(cand_cfg, dict) else "default",
                base_url=cand_cfg.get("base_url") if isinstance(cand_cfg, dict) else None,
                api_key=cand_key,
                is_custom=False,
            )

    # Or any enabled custom endpoint
    for cand_ep in vault.get("custom_endpoints", []):
        if cand_ep.get("enabled", True):
            return RoleTarget(
                provider=f"custom:{cand_ep['id']}",
                model=cand_ep.get("default_model") or cand_ep.get("model") or "default",
                base_url=cand_ep.get("base_url"),
                api_key=cand_ep.get("api_key", "sk-local"),
                is_custom=True,
                endpoint=cand_ep,
            )

    # Fall back to embedded local model
    local_cfg = vault.get("providers", {}).get("local", {})
    return RoleTarget(
        provider="local",
        model=model or (local_cfg.get("default_model") if isinstance(local_cfg, dict) else LOCAL_MODEL_NAME) or LOCAL_MODEL_NAME,
        base_url=None,
        api_key="local-in-process",
        is_custom=False,
    )


def set_role_target(
    role: str,
    provider: Any,
    model: Optional[str] = None,
    vault_path: Optional[Path] = None,
) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    if isinstance(provider, dict):
        vault.setdefault("role_mappings", {})[role] = provider
    elif model is not None and str(model).strip():
        vault.setdefault("role_mappings", {})[role] = {"provider": str(provider).strip(), "model": str(model).strip()}
    else:
        ep = get_custom_endpoint(str(provider), vault_path=vault_path)
        if ep:
            vault.setdefault("role_mappings", {})[role] = {
                "provider": f"custom:{ep['id']}",
                "model": ep.get("default_model", "default"),
            }
        else:
            prov_str = str(provider).strip().lower()
            prov_cfg = vault.get("providers", {}).get(prov_str, {})
            vault.setdefault("role_mappings", {})[role] = {
                "provider": prov_str,
                "model": prov_cfg.get("default_model", "gemini-2.5-flash"),
            }
    return save_vault(vault, vault_path=vault_path)


get_role_mapping = get_role_target
set_role_mapping = set_role_target


def update_role_mappings(mappings: Dict[str, Any], vault_path: Optional[Path] = None) -> Dict[str, Any]:
    vault = load_vault(vault_path=vault_path)
    for role, target in mappings.items():
        if isinstance(target, dict):
            vault.setdefault("role_mappings", {})[role] = target
        else:
            set_role_target(role, target, vault_path=vault_path)
            vault = load_vault(vault_path=vault_path)
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
    target = get_role_target(role, vault_path=vault_path)
    if target.get("provider") == "local":
        return True
    if target.get("base_url"):
        return is_local_endpoint_url(str(target["base_url"]))
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


def is_internet_connected(role: Optional[str] = None, timeout: float = 1.0, force_refresh: bool = False) -> bool:
    if role and is_role_bound_to_local_endpoint(role):
        return True
    now = time.time()
    if force_refresh or (now - _net_cache["last_checked"] > 15.0):
        _refresh_internet_status_async()
    return bool(_net_cache["online"])
